"""What premarket volume ACTUALLY was, from Alpaca's full SIP tape.

The morning has no choice but to estimate. It divides the collector's socket
volume by [Collector] premarket_capture_rate, one number, 0.1172, because the
socket carries a fraction of the consolidated tape and the baseline it divides
into is built from whole tape bars. That correction is better than the raw
socket count it replaced, and it is still wrong in a way that matters: the
socket's share was measured at 2.1 to 12.1 percent over the 2026-08-19 probe
window, a six fold spread, and a single divisor cannot correct a quantity that
varies six fold.

THE ERROR IS NOT RANDOM, and the direction written here was assumed rather
than measured. This paragraph used to read: "Thin names capture least, so thin
names are understated most, and thin names are exactly the population
premarket float rotation exists to rescue. The correction therefore reinstates
at a lower layer the bias the float rotation fallback was built to remove."

The record this module writes says the opposite. Over the 46 guarded rows in
data/research/capture_rate_study-2026-09-01.json, terciles of avg_volume_20d
give median capture shares of 0.178 thin, 0.087 mid and 0.084 thick, Spearman
rho -0.405 over 46 rows and 6 sessions. Thin names capture MORE. The spread is
still real and a single divisor still cannot correct it; what was wrong is the
sign of what it gets wrong. Six sessions is below [Truth] baseline_sessions, so
this is a contradicted assumption rather than a finding to act on, and
research/sweep_capture_rate.py re-asks it for nothing.

The RECORD does not have to estimate anything. Alpaca's free plan serves the
sip feed for a session that is over and refuses it with 403 for one that is
running, measured in doc/ALPACA_PROBE.md section 1. So this runs at night,
fetches the same window the morning used, and writes what was true BESIDE what
was estimated, never over it, exactly as backfill_premarket writes
pm_high_true beside pm_high.

_true DOES NOT MEAN ONE SOURCE. backfill_premarket's pm_high_true, pm_low_true
and pm_vwap_true come from EODHD intraday. Every column this module writes
comes from Alpaca. A column suffix is not a provenance, so truth_source carries
the vendor on every row.

BOTH SIDES OF EVERY RATIO COME FROM ONE TAPE. pm_rvol_true divides an Alpaca
window by an Alpaca baseline over the same window on the prior sessions.
Dividing the Alpaca numerator into the EODHD intraday baseline the morning uses
would repeat, one vendor down, the exact defect this module exists to correct.
Both are meant to be consolidated. This project has been wrong about "meant to
be" several times.

IT MEASURES THE REFERENCE LEVELS TOO, for the same reason and off the same
bars. entry_ref and stop_ref are the collector's raw live pm_high and pm_low,
which are the extremes of a sample that carried a median 0.0296 of the tape. A
sample understates a maximum and overstates a minimum, so entry_ref sits below
the true premarket high and stop_ref sits above the true premarket low.

THOSE TWO BIASES POINT IN OPPOSITE DIRECTIONS once they reach the excursions.
mfe_pct measures up from entry_ref, so too low an entry_ref makes the
favourable excursion look bigger than it was. mae_pct measures down from
stop_ref, so too high a stop_ref makes the adverse excursion look deeper than
it was. The record flatters its upside and overstates its downside at once, and
whether the two cancel, and by how much, is not knowable without measuring it.
entry_ref_true and stop_ref_true are the same references over the same window
off the whole tape, written beside the sampled pair and never over it, because
the gap between the pairs IS the measurement.

    PYTHONPATH=src .venv/Scripts/python.exe -m night.true_volume
    PYTHONPATH=src .venv/Scripts/python.exe -m night.true_volume --date 2026-08-21
    PYTHONPATH=src .venv/Scripts/python.exe -m night.true_volume --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from typing import Any

import probe_alpaca

from core import config
from core import criteria
from core import ettime
from core import store
from ops import job_status

_CRIT = criteria.load()


def _window(day: dt.date, cutoff_hhmm: str,
            start_key: tuple[str, str] | None = None,
            ) -> tuple[dt.datetime, dt.datetime]:
    """04:00 to the clock the morning actually used, on one day.

    start_key swaps the opening bound for [Collector] start_time, which is the
    SOCKET'S own window and the only one a capture share may be measured over.
    The socket cannot see 04:00 to 07:20 at all, so dividing what it recorded
    by the whole premarket folds its late start into a number that is supposed
    to measure the feed. Those are two different shortfalls with two different
    fixes: one is a subscription question and one is a start time question.

    The end is the packet's rvol_cutoff_hhmm and never a fixed 08:45. A truth
    measured over a wider window than the estimate is too large by whatever the
    extra minutes carried, and that error looks exactly like the socket missing
    more of the tape, which is the thing being measured. The morning cutoff
    snaps to [Scan] run_time only inside rvol_cutoff_snap_minutes, so a rerun
    genuinely has a different clock, and a fixed window here would mismeasure
    precisely the sessions that went wrong.
    """
    open_h, open_m = _CRIT.clock(*(start_key or ("baseline", "session_start")))
    hour, minute = (int(part) for part in cutoff_hhmm.split(":"))
    start = dt.datetime(day.year, day.month, day.day, open_h, open_m,
                        tzinfo=ettime.ET)
    end = dt.datetime(day.year, day.month, day.day, hour, minute,
                      tzinfo=ettime.ET)
    return start, end


def fetch_bars(probe: probe_alpaca.Probe, symbols: list[str],
               start: dt.datetime, end: dt.datetime,
               ) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    """(per symbol one minute bars in time order, error). One window.

    Paged and batched. A page token still outstanding at the page cap is an
    INCOMPLETE fetch and is returned as an error rather than as a total,
    because a truncated window is indistinguishable from a quiet session and
    this whole module exists to stop numbers being read for more than they are.

    The bars are returned RAW and in order. fetch_window below folds them into
    the sums it needs and night/paper_ledger.py walks them in sequence, and
    those are two different uses of one fetch. The paging and the refusal live
    here so there is one place either can be got wrong.
    """
    batch_size = _CRIT.integer("truth", "symbols_per_request")
    max_pages = _CRIT.integer("truth", "max_pages_per_request")
    feed = _CRIT.text("truth", "feed")
    out: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}

    for index in range(0, len(symbols), batch_size):
        chunk = symbols[index:index + batch_size]
        token = None
        pages = 0
        while True:
            params = {
                "symbols": ",".join(chunk),
                "timeframe": "1Min",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": probe_alpaca.PAGE_LIMIT,
                "feed": feed,
            }
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            pages += 1
            if status != 200:
                return out, (f"alpaca returned {status}: "
                             f"{probe_alpaca._error_text(payload)}")
            for symbol, rows in ((payload or {}).get("bars") or {}).items():
                if symbol in out:
                    out[symbol].extend(rows or [])
            token = (payload or {}).get("next_page_token")
            if not token:
                break
            if pages >= max_pages:
                return out, (f"{max_pages} pages consumed with a page token "
                             "still outstanding, so this window is incomplete")
    # The vendor returns each page in time order, and pages arrive in order, so
    # this is already sorted. Sorted again anyway because paper_ledger reads
    # the sequence as the record of what happened first, and an out of order
    # bar there would book a stop before the entry that preceded it.
    for symbol in out:
        out[symbol].sort(key=lambda row: str(row.get("t") or ""))
    return out, None


def fetch_window(probe: probe_alpaca.Probe, symbols: list[str],
                 start: dt.datetime, end: dt.datetime,
                 keep_minutes: bool = False,
                 ) -> tuple[dict[str, dict[str, Any]], str | None]:
    """(per symbol path over the window, error). One window, all symbols.

    Each entry carries volume, bar count, the high, the low and a volume
    weighted price sum. The three price fields cost one comparison per bar over
    bars that are being walked anyway, and they are what reference_level below
    turns into entry_ref_true and stop_ref_true. Fetching them separately would
    double the request count to answer a question these bars already answer.

    keep_minutes additionally retains one (high, low, volume) triple per bar,
    which band_stats needs because the band is centred on a level that is not
    known until the whole window has been walked. It is OFF by default and on
    for the two windows measure() reads: prior_sessions calls this twenty times
    a session for a median it takes at the end, and holding every minute of all
    of them would be twenty windows of tuples kept to answer nothing.

    THE EXTREMES ARE NULL, NOT ZERO, when nothing parsed. A high of 0.0 on a
    window with no readable bar would be a fabricated level in the column a
    reader is being invited to trust over the collector's, which is the exact
    failure this module exists to stop one level up.
    """
    out: dict[str, dict[str, Any]] = {
        symbol: {"volume": 0.0, "bars": 0, "high": None, "low": None,
                 "price_volume": 0.0, "minutes": [] if keep_minutes else None}
        for symbol in symbols}
    bars, error = fetch_bars(probe, symbols, start, end)
    for symbol, rows in bars.items():
        held = out[symbol]
        for row in rows:
            volume = float(row.get("v") or 0)
            held["volume"] += volume
            held["bars"] += 1
            high, low = _as_float(row.get("h")), _as_float(row.get("l"))
            if high is not None:
                held["high"] = (high if held["high"] is None
                                else max(held["high"], high))
            if low is not None:
                held["low"] = (low if held["low"] is None
                               else min(held["low"], low))
            # The vendor publishes a per bar VWAP. It is used where it is there
            # and hlc3 stands in where it is not, which is the same proxy
            # backfill_premarket builds off EODHD bars that carry no vw field.
            typical = _as_float(row.get("vw"))
            if typical is None and high is not None and low is not None:
                close = _as_float(row.get("c"))
                if close is not None:
                    typical = (high + low + close) / 3.0
            if typical is not None:
                held["price_volume"] += typical * volume
            if keep_minutes:
                held["minutes"].append((high, low, volume))
    return out, error


def prior_sessions(probe: probe_alpaca.Probe, symbols: list[str], day: dt.date,
                   cutoff_hhmm: str) -> tuple[dict[str, list[float]], list[str]]:
    """The same window on the prior trading sessions, walking back day by day.

    THE TRADING CALENDAR COMES FROM THE DATA. A day the exchange was shut
    returns no bars for anybody, so it is skipped without ever being asked
    about, and no holiday table has to be right for this to be right. The walk
    is bounded by [Truth] max_calendar_days_back so a symbol with no history
    cannot turn this into an unbounded crawl.

    Requesting a single wide date range instead would be one call rather than
    thirty, and would return every regular session minute of every day in it,
    which is the wrong window and about forty times the payload. The window is
    the point.
    """
    wanted = _CRIT.integer("truth", "baseline_sessions")
    horizon = _CRIT.integer("truth", "max_calendar_days_back")
    per_symbol: dict[str, list[float]] = {symbol: [] for symbol in symbols}
    used: list[str] = []

    back = 1
    while len(used) < wanted and back <= horizon:
        session = day - dt.timedelta(days=back)
        back += 1
        if not ettime.is_weekday(session):
            continue
        start, end = _window(session, cutoff_hhmm)
        found, error = fetch_window(probe, symbols, start, end)
        if error:
            # One refused session is not a reason to abandon the baseline. It
            # is a reason to say how many sessions the median actually rests
            # on, which true_baseline_sessions does on every row.
            continue
        if not any(row["bars"] for row in found.values()):
            continue
        used.append(session.isoformat())
        for symbol, row in found.items():
            if row["bars"]:
                per_symbol[symbol].append(row["volume"])
    return per_symbol, used


def volume_ratio(row: Any) -> tuple[float | None, str]:
    """(the relative volume to read for this row, which number that is).

    THE RULE THIS EXISTS TO ENFORCE: nothing reads the estimate where the true
    value exists. pm_rvol is what was known at 08:45 and pm_rvol_true is what
    was true that night, and on the two sessions measured so far the second ran
    between 1.4 and 19 times the first. A later reader picking pm_rvol because
    it is the older column name would be reading the worse of two numbers that
    are both right there in the row.

    It returns the LABEL as well as the value, so a page or a query cannot show
    the number without being able to say which one it is. A mixed column of
    estimates and measurements with nothing to tell them apart is the defect
    this whole pass was built to stop, one level up.
    """
    def _get(key: str) -> Any:
        try:
            return row[key]
        except (KeyError, IndexError, TypeError):
            return None

    true_value = _get("pm_rvol_true")
    if true_value is not None:
        return true_value, "measured"
    return _get("pm_rvol"), "estimated"


# A number the vendor may not have sent, coerced or refused, never raising:
# the shared reading in core/numbers.py. usable_float below is handed raw
# quote fields, and a string, a None, a NaN or a malformed value comes back as
# "no number" rather than as an exception inside a night job.
from core.numbers import as_float as _as_float  # noqa: E402


def _ratio(top: float | None, bottom: float | None) -> float | None:
    if top is None or not bottom:
        return None
    return round(top / bottom, 6)


# The three field names scan.write_picks allows for entry_ref_field and
# stop_ref_field. Repeated here rather than imported for the reason usable_float
# gives: importing scan pulls discover, universe, vintage, baseline and the
# collector into a night job that needs none of them.
REFERENCE_FIELDS = ("pm_high", "pm_low", "pm_vwap")


def reference_level(path: dict[str, Any], field: str) -> float | None:
    """One reference level off one fetched window, under one configured field.

    THE FIELD NAME IS READ, NEVER ASSUMED. [Picks] entry_ref_field and
    stop_ref_field are configuration, and the whole worth of entry_ref_true is
    that it is the SAME reference over the SAME window off a complete tape. A
    pair hard coded to high and low here would go on being written, silently
    and wrongly named, the day either key moved to pm_vwap, and the column that
    exists to measure a bias would then be measuring a different level.

    Null rather than zero on an empty window, and null rather than a fallback
    to another field on an unusable one. A level that was never observed is not
    a level, which is the sentence scan.write_picks already applies to
    entry_ref itself.
    """
    if field not in REFERENCE_FIELDS:
        raise criteria.CriteriaError(
            f"picks reference field {field!r} is not one of "
            f"{sorted(REFERENCE_FIELDS)}, so there is no true level to measure "
            "against it")
    if not path.get("bars"):
        return None
    if field == "pm_high":
        value = path.get("high")
    elif field == "pm_low":
        value = path.get("low")
    else:
        volume = path.get("volume") or 0.0
        value = (path["price_volume"] / volume) if volume else None
    return round(value, 4) if value is not None else None


def band_stats(path: dict[str, Any], level: float | None,
               band_pct: float) -> tuple[float | None, int | None]:
    """(volume upper bound, minutes) for trading within band_pct of one level.

    A REFERENCE LEVEL IS NOT A PRICE ANYONE COULD HAVE TRANSACTED AT. On a name
    whose entire premarket is a few hundred shares, entry_ref is a print rather
    than a market, and every excursion measured from it is arithmetic about a
    level nobody could have got. These two counts are what let a later reader
    tell that case from a real one.

    A MINUTE COUNTS WHEN ITS RANGE REACHES THE BAND, which is high >= the band
    floor and low <= the band ceiling. The minute count is then EXACT: that
    many minutes traded somewhere inside the band.

    THE VOLUME IS AN UPPER BOUND AND IS NOT A MEASUREMENT OF VOLUME AT THE
    LEVEL. One minute bar carries o, h, l, c and v and no distribution, so a
    minute that ran from well below up into the band contributes all of its
    volume here while only some of it transacted inside. Stated as a bound
    rather than corrected, the way this file already treats premarket RVOL,
    because the correction would need trade level data this plan does not buy.

    REJECTED: counting a minute by its own volume weighted price instead of its
    range. It was written that way first and calibrated on 2026-08-29, and it
    measured the wrong thing. entry_ref is a session HIGH, which is an extreme
    no whole minute averages near, so a wide ranging name scored zero however
    much it traded: BABA on 2026-08-20 has 2,986,339 premarket shares over 268
    minutes and came back with a band volume of 0. That is a measurement of how
    long a name sat at its top, and it called the most liquid names in the
    table the least fillable.

    Both are null, not zero, when the level is unknown or the window carried no
    minutes to look at. Zero volume at a level and no measurement of the volume
    at a level are different facts, and only the first is evidence.
    """
    if level is None or not level or not path.get("minutes"):
        return None, None
    floor, ceiling = level * (1.0 - band_pct), level * (1.0 + band_pct)
    volume = 0.0
    minutes = 0
    for high, low, size in path["minutes"]:
        if high is None or low is None or high < floor or low > ceiling:
            continue
        volume += size
        minutes += 1
    return round(volume, 2), minutes


# The three verdicts fill_plausible may carry. Named rather than spelled as
# literals through the module, so a claim can assert the set is closed and a
# typo cannot invent a fourth state that reads as a real one.
FILL_PLAUSIBLE = "plausible"
FILL_IMPLAUSIBLE = "implausible"
FILL_UNKNOWN = "unknown"
FILL_STATES = (FILL_PLAUSIBLE, FILL_IMPLAUSIBLE, FILL_UNKNOWN)


def fill_verdict(notional: float | None, volume: float | None,
                 minutes: int | None, level: float | None,
                 band_pct: float, floor: float,
                 ) -> tuple[str, str]:
    """(verdict, the numbers behind it). Three states, never two.

    NO ROW IS CALLED PLAUSIBLE ON ABSENT EVIDENCE. A window the feed could not
    reach, or one with no measured reference to centre a band on, is UNKNOWN
    and says which. Reading that as either of the other two is the failure this
    project keeps finding under other names: a missing answer wearing a
    measured one's clothes. A boolean has no room for the third state, which is
    why this column is text.

    THE VERDICT RESTS ON THE NOTIONAL ALONE. Requiring a minute count as well
    was written first and rejected on the 2026-08-29 calibration: MSTR on
    2026-08-20 traded 49,768 shares inside the band in a SINGLE minute, and
    KSS, TIGR, BBY and PLAB are the same shape. Half a million dollars changing
    hands at the level in one minute is a market, and a rule that called it a
    print because it lasted one bar would be measuring duration rather than
    liquidity. The minute count is recorded and reported because it says how
    loose the volume bound is, and it does not gate.

    Dollars rather than shares because this table holds prices from 5.64 to
    1,585. Ten thousand shares is 56,000 dollars of TIGR and 9,400,000 of MU,
    and one share floor cannot mean the same thing at both ends.
    """
    if level is None or notional is None:
        return FILL_UNKNOWN, (
            "there is no measured reference level to centre a band on"
            if level is None else
            "no alpaca minutes were held for this window, so nothing can be "
            "said about what traded near the level")
    numbers = (f"{volume:,.0f} shares over {minutes} minute(s) within "
               f"{band_pct * 100:g} percent of {level:g}, which is "
               f"{notional:,.0f} dollars")
    if notional < floor:
        return FILL_IMPLAUSIBLE, (
            f"{numbers}, below the {floor:,.0f} dollar floor in "
            f"{config.CRITERIA_PATH.name} [Truth] min_fill_band_notional. The "
            "level is closer to a print than to a market, and an excursion "
            "measured from it is arithmetic about a price that was not there")
    return FILL_PLAUSIBLE, (
        f"{numbers}, at or above the {floor:,.0f} dollar floor. The volume is "
        "an UPPER BOUND: a one minute bar carries no distribution, so a minute "
        "that ran from below up into the band counts whole")


def reference_fields() -> tuple[str, str]:
    """(entry field, stop field), validated once before any row is written."""
    entry = _CRIT.text("picks", "entry_ref_field")
    stop = _CRIT.text("picks", "stop_ref_field")
    for field in (entry, stop):
        if field not in REFERENCE_FIELDS:
            raise criteria.CriteriaError(
                f"picks reference field {field!r} is not one of "
                f"{sorted(REFERENCE_FIELDS)}")
    return entry, stop


def _only_failure_was_volume(candidate: dict[str, Any]) -> tuple[bool, bool]:
    """(was premarket_rvol the only day condition it failed, could we tell).

    day_failed_conditions did not exist before 2026-08-19, and reading a
    missing field as an empty list said "this name failed nothing" for every
    candidate in the three packets that predate it. The first run of --reread
    did exactly that and reported 2026-08-14, 08-17 and 08-18 as gaining zero
    names, which is an ABSENCE DRESSED AS A MEASUREMENT: the same failure this
    project has caught in the off exchange counter and in the socket cap
    reading.

    day_failed carries the same fact as prose in every packet ever written,
    and the one question here needs no mapping from prose to condition names:
    a single entry beginning "premarket_rvol" is exactly the case. Where
    neither field exists the answer is UNRESOLVABLE and says so, rather than
    defaulting either way.
    """
    conditions = candidate.get("day_failed_conditions")
    if conditions is not None:
        return list(conditions) == ["premarket_rvol"], True
    prose = candidate.get("day_failed")
    if prose is not None:
        return (len(prose) == 1
                and str(prose[0]).startswith("premarket_rvol")), True
    return False, False


def reread(day: str, probe: Any = None) -> dict[str, Any]:
    """What the morning admitted, against what the true volume would have.

    Reads the PACKET rather than picks, so it reaches sessions whose rows were
    purged on 2026-08-19, and it never writes to a table those rows were
    deliberately removed from. It writes nothing at all.

    A name changes side only when premarket_rvol was the ONLY condition it
    failed. That distinction is the whole value of this: on 2026-08-18 eleven
    of the twelve candidates also failed the prior day high, which no volume
    number touches, so an empty watchlist that reads as a volume story is
    mostly an honest one with a single name buried in it. Counting every name
    whose true RVOL clears the floor would overstate the defect by an order of
    magnitude, in the same direction and for the same reason the estimate
    understated it.

    Swing eligibility carries NO volume condition at all, so a swing watchlist
    cannot move here. Reported anyway, because "unchanged" is the answer to a
    question a reader would otherwise have to work out for themselves.
    """
    packet_path = config.run_path(day) / "packet.json"
    if not packet_path.is_file():
        return {"day": day, "skipped": f"no packet at {packet_path.name}"}
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return {"day": day, "skipped": f"packet unreadable: {type(exc).__name__}"}
    cutoff = packet.get("rvol_cutoff_hhmm")
    if not cutoff:
        return {"day": day, "skipped": "packet carries no rvol_cutoff_hhmm"}
    run_time = str(packet.get("run_time_et") or "")
    scheduled = _CRIT.clock_text("scan", "run_time")
    candidates = packet.get("candidates") or []
    if not candidates:
        return {"day": day, "skipped": "packet carries no candidates"}
    if run_time != scheduled:
        return {"day": day, "skipped":
                f"the packet was gathered at {run_time or 'an unrecorded time'}, "
                f"not the scheduled {scheduled}, so it describes a different "
                "market and its watchlists are not a morning's"}

    floor = _CRIT.rule("day_setup", "premarket_rvol")
    symbols = sorted({c["symbol"].split(".", 1)[0] for c in candidates})
    probe = probe if probe is not None else probe_alpaca.Probe()
    session_day = ettime.parse_date(day)
    start, end = _window(session_day, cutoff)
    observed, error = fetch_window(probe, symbols, start, end)
    history, sessions_used = prior_sessions(probe, symbols, session_day, cutoff)

    rows = []
    for candidate in candidates:
        symbol = candidate["symbol"]
        bare = symbol.split(".", 1)[0]
        found = observed.get(bare) or {"volume": 0.0, "bars": 0}
        prior = history.get(bare) or []
        failed, resolvable = _only_failure_was_volume(candidate)
        true_rvol = None
        if found["bars"] and prior:
            true_rvol = _ratio(found["volume"], statistics.median(prior))
        rows.append({
            "symbol": symbol,
            "was_day": bool(candidate.get("day_eligible")),
            "was_swing": bool(candidate.get("swing_eligible")),
            "pm_rvol": candidate.get("pm_rvol"),
            "pm_rvol_true": true_rvol,
            "failed": candidate.get("day_failed_conditions")
                      or candidate.get("day_failed") or [],
            "volume_was_the_only_failure": failed,
            "resolvable": resolvable,
            "clears_on_true": bool(true_rvol is not None and floor.test(true_rvol)),
            "true_volume": round(found["volume"], 2) if found["bars"] else None,
            "baseline_sessions": len(prior),
        })

    gained = [r["symbol"] for r in rows
              if not r["was_day"] and r["volume_was_the_only_failure"]
              and r["clears_on_true"]]
    # A name the morning ADMITTED whose true RVOL does not clear the floor.
    # Reported in both directions or this is advocacy rather than a re-read.
    lost = [r["symbol"] for r in rows if r["was_day"]
            and r["pm_rvol_true"] is not None and not r["clears_on_true"]]
    blocked = [r["symbol"] for r in rows
               if not r["was_day"] and r["clears_on_true"]
               and not r["volume_was_the_only_failure"]]
    return {
        "day": day, "skipped": None,
        "window": f"{start.strftime('%H:%M')}-{cutoff}",
        "run_time_et": run_time,
        "candidates": len(rows), "rows": rows,
        "admitted_day": [r["symbol"] for r in rows if r["was_day"]],
        "admitted_swing": [r["symbol"] for r in rows if r["was_swing"]],
        "would_gain": gained, "would_lose": lost, "clears_but_blocked": blocked,
        "baseline_sessions": len(sessions_used),
        "unresolvable": [r["symbol"] for r in rows if not r["resolvable"]],
        "fetch_error": error, "requests": getattr(probe, "request_count", 0),
    }


def reread_report(results: list[dict[str, Any]]) -> None:
    print("")
    print("ADMITTED, AGAINST WOULD HAVE BEEN ADMITTED ON TRUE VOLUME")
    print(f"  {'session':<12} {'cands':>5} {'day':>4} {'+true':>6} "
          f"{'-true':>6} {'swing':>6}  {'names that change side'}")
    for result in results:
        if result.get("skipped"):
            print(f"  {result['day']:<12} {result['skipped']}")
            continue
        change = ", ".join(f"+{s}" for s in result["would_gain"])
        if change and result["would_lose"]:
            change += ", "
        change += ", ".join(f"-{s}" for s in result["would_lose"])
        print(f"  {result['day']:<12} {result['candidates']:>5} "
              f"{len(result['admitted_day']):>4} {len(result['would_gain']):>6} "
              f"{len(result['would_lose']):>6} "
              f"{len(result['admitted_swing']):>6}  {change or 'none'}")
    print("")
    print("  +true means premarket_rvol was the ONLY day condition the name "
          "failed AND its true RVOL clears the floor.")
    print("  Swing setup carries no volume condition, so a swing watchlist "
          "cannot move on this and none does.")
    for result in results:
        if result.get("skipped") or not result.get("unresolvable"):
            continue
        print(f"  {result['day']}: UNRESOLVED for "
              f"{len(result['unresolvable'])} name(s). The packet records "
              "neither day_failed_conditions nor day_failed, so whether "
              "volume was the only thing that failed cannot be read: "
              f"{', '.join(result['unresolvable'])}")
    for result in results:
        if result.get("skipped") or not result["clears_but_blocked"]:
            continue
        print(f"  {result['day']}: cleared the volume floor on the true "
              f"numbers and still failed another condition, so it stays out: "
              f"{', '.join(result['clears_but_blocked'])}")


MIN_SHARES_FLOAT = _CRIT.number("float_rotation", "min_shares_float")
MIN_FLOAT_RATIO = _CRIT.number("float_rotation", "min_float_to_shares_outstanding")
MAX_FLOAT_RATIO = _CRIT.number("float_rotation", "max_float_to_shares_outstanding")


def usable_float(share_float: Any, outstanding: Any) -> tuple[float | None, str | None]:
    """The denominator pm_float_rotation_true may divide by, and why not.

    THE SAME FOUR REFUSALS scan.attach_float_rotation applies, and they have to
    be the same or this module breaks its own promise. It exists to write what
    was true BESIDE what the morning estimated so a reader can compare the two,
    and until 2026-08-28 it divided by whatever sharesFloat the quote carried
    with no check at all. A float the morning refused as a vendor artifact
    would therefore come back with a rotation beside the morning's null, and
    the comparison would read as the night measuring something the morning
    could not, when both had the same bad denominator and only one noticed.

    Rotation is volume over float, so an unchecked fabricated float of a few
    thousand shares does not produce a slightly wrong number. It produces a
    very large one, in the column a reader is being invited to trust over the
    estimate.

    Not imported from scan. Importing it would pull discover, universe,
    vintage, baseline and the collector into a night job that needs none of
    them, so the rule is spelled out here the way measure_baseline_floor
    spells out baseline.compute's window, and
    claim_the_night_refuses_the_floats_the_morning_refuses holds that the two
    agree over every shape a quote can take.
    """
    value = _as_float(share_float)
    cross = _as_float(outstanding)
    if value is None or value <= 0:
        return None, "the delayed quote carried no sharesFloat, so there is no denominator"
    if cross is not None and cross < 0:
        return None, (
            f"sharesOutstanding is reported as {cross:,.0f}, a negative share count, "
            "so the quote is corrupt rather than merely missing a cross check and "
            "the sharesFloat in it is not divided by")
    usable = cross is not None and cross > 0
    if usable and value > cross * MAX_FLOAT_RATIO:
        return None, (
            f"sharesFloat {value:,.0f} exceeds sharesOutstanding {cross:,.0f}, "
            "which is impossible, so the vendor figure is not divided by")
    if usable and value < cross * MIN_FLOAT_RATIO:
        return None, (
            f"sharesFloat {value:,.0f} is {value / cross * 100:.3f} percent of "
            f"sharesOutstanding {cross:,.0f}, below the {MIN_FLOAT_RATIO * 100:g} "
            "percent floor, so it reads as a vendor artifact rather than a small "
            "free float")
    if not usable and value < MIN_SHARES_FLOAT:
        no_cross_check = ("there is no sharesOutstanding to check it against"
                          if cross is None else
                          "sharesOutstanding is reported as zero, which is not a "
                          "share count and cannot check it")
        return None, (
            f"sharesFloat {value:,.0f} is below the {MIN_SHARES_FLOAT:,.0f} share "
            f"floor and {no_cross_check}")
    return value, None


def measure(day: str, dry_run: bool = False, probe: Any = None,
            ) -> dict[str, Any]:
    """Everything this pass writes for one session, computed before it writes."""
    packet_path = config.run_path(day) / "packet.json"
    if not packet_path.is_file():
        return {"day": day, "rows": [], "skipped":
                f"{packet_path.name} is absent, so the window the morning used "
                "is unknown and guessing it is the one thing this pass must "
                "not do"}
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return {"day": day, "rows": [], "skipped":
                f"{packet_path.name} is unreadable ({type(exc).__name__}), so "
                "the window the morning used is unknown"}
    cutoff = packet.get("rvol_cutoff_hhmm")
    if not cutoff:
        return {"day": day, "rows": [], "skipped":
                "the packet carries no rvol_cutoff_hhmm, so the window the "
                "morning used is unknown"}

    # The packet is the fallback for the morning's own two numbers as well as
    # the source of the float. picks only began carrying pm_volume and
    # pm_volume_estimated on 2026-08-21, so every session before that has the
    # observation and the estimate in the packet and nowhere else, and
    # capture_observed is exactly the quantity that cannot be computed without
    # them. Reading them here makes the whole existing record measurable
    # instead of only sessions from today forward.
    floats: dict[str, tuple[Any, Any]] = {}
    from_packet: dict[str, dict[str, Any]] = {}
    for candidate in packet.get("candidates", []):
        quote = candidate.get("quote") or {}
        # sharesOutstanding travels with it now. Three of usable_float's four
        # refusals are cross checks against it, so reading the float alone was
        # not a shortcut, it was most of the rule missing.
        floats[candidate["symbol"]] = (quote.get("sharesFloat"),
                                       quote.get("sharesOutstanding"))
        from_packet[candidate["symbol"]] = {
            "pm_volume": candidate.get("pm_volume"),
            "pm_volume_estimated": candidate.get("pm_volume_consolidated"),
        }

    with store.session() as connection:
        store.init(connection)
        rows = connection.execute(
            "SELECT ticker, pm_volume, pm_volume_estimated, entry_ref, stop_ref "
            "FROM picks WHERE date=? AND source='live' ORDER BY ticker", (day,),
        ).fetchall()
    tickers = [row["ticker"] for row in rows]
    if not tickers:
        return {"day": day, "rows": [], "skipped":
                "no live picks rows for this session"}

    # Alpaca takes bare symbols; the rest of this project carries the .US
    # suffix EODHD uses. The mapping is one sided and lossless in this
    # direction, and it is done once here rather than in three places.
    bare = {ticker: ticker.split(".", 1)[0] for ticker in tickers}
    symbols = sorted(set(bare.values()))

    # Injectable so a claim can drive this without a socket or a key. The
    # default is the real thing, so production reads exactly as before.
    probe = probe if probe is not None else probe_alpaca.Probe()
    session_day = ettime.parse_date(day)
    start, end = _window(session_day, cutoff)
    # keep_minutes only here. The band is centred on entry_ref_true, which is
    # the FULL window's own level, and the socket window and the twenty
    # baseline sessions are summed rather than looked through.
    observed, error = fetch_window(probe, symbols, start, end, keep_minutes=True)
    socket_start, socket_end = _window(session_day, cutoff,
                                       ("collector", "start_time"))
    on_socket, socket_error = fetch_window(probe, symbols, socket_start,
                                           socket_end)
    history, sessions_used = prior_sessions(probe, symbols, session_day, cutoff)

    min_bars = _CRIT.integer("truth", "min_true_bars")
    # Validated before the loop rather than inside it, so a bad key fails the
    # whole pass loudly instead of writing eleven good rows and then raising.
    entry_field, stop_field = reference_fields()
    band_pct = _CRIT.number("truth", "fill_band_pct")
    band_floor = _CRIT.number("truth", "min_fill_band_notional")
    window_text = f"{start.strftime('%H:%M')}-{cutoff}"
    stamp = ettime.stamp(ettime.now_et())
    source = f"{_CRIT.text('truth', 'source')}-{_CRIT.text('truth', 'feed')}"

    out: list[dict[str, Any]] = []
    for row in rows:
        ticker = row["ticker"]
        found = observed.get(bare[ticker]) or {"volume": 0.0, "bars": 0}
        prior = history.get(bare[ticker]) or []
        fallback = from_packet.get(ticker) or {}
        record: dict[str, Any] = {
            "_socket": row["pm_volume"] if row["pm_volume"] is not None
                       else fallback.get("pm_volume"),
            "_estimated": row["pm_volume_estimated"]
                          if row["pm_volume_estimated"] is not None
                          else fallback.get("pm_volume_estimated"),
            # The morning's own sampled pair, carried for the printout and the
            # gap arithmetic. Never written back: this pass writes BESIDE the
            # morning and never over it, which is what the underscore marks.
            "_entry_ref": row["entry_ref"], "_stop_ref": row["stop_ref"],
            "ticker": ticker, "true_window": window_text,
            "truth_source": source, "truth_at": stamp,
            "true_bars": found["bars"] or None,
            "true_baseline_sessions": len(prior) or None,
            "pm_volume_true": None, "pm_rvol_true": None,
            "pm_float_rotation_true": None, "true_baseline_median": None,
            "capture_observed": None, "estimate_error": None,
            "true_volume_socket_window": None, "collector_window_share": None,
            "truth_reason": None,
            "entry_ref_true": None, "stop_ref_true": None,
            "entry_ref_collector_window": None,
            "stop_ref_collector_window": None,
            "refs_true_reason": None,
            "fill_band_volume": None, "fill_band_minutes": None,
            "fill_band_notional": None, "fill_band_pct": band_pct,
            "fill_plausible": FILL_UNKNOWN, "fill_plausible_reason": None,
        }
        if error:
            record["truth_reason"] = error
            record["refs_true_reason"] = error
            record["fill_plausible_reason"] = error
            out.append(record)
            continue
        if found["bars"] < min_bars:
            reason = (f"alpaca returned {found['bars']} bars inside "
                      f"{window_text}, below [Truth] min_true_bars of {min_bars}")
            record["truth_reason"] = reason
            record["refs_true_reason"] = reason
            record["fill_plausible_reason"] = reason
            out.append(record)
            continue

        # The true references, gated on the same bar count as the volume below
        # and written whether or not the baseline or the float turns out to be
        # usable. They need neither: a high and a low are read off the window
        # itself, so a row with no baseline still carries a measured pair.
        record["entry_ref_true"] = reference_level(found, entry_field)
        record["stop_ref_true"] = reference_level(found, stop_field)
        if record["entry_ref_true"] is None or record["stop_ref_true"] is None:
            record["refs_true_reason"] = (
                f"alpaca returned {found['bars']} bars inside {window_text} and "
                f"none of them carried a readable {entry_field}/{stop_field} "
                "pair, so the level is null rather than a zero")

        # WHETHER THAT LEVEL WAS A PRICE ANYONE COULD HAVE TRANSACTED AT. A
        # different question from what the level was, and one nothing asked
        # before: an excursion from a level nobody could have got is arithmetic
        # rather than a measurement.
        level = record["entry_ref_true"]
        band_volume, band_minutes = band_stats(found, level, band_pct)
        record["fill_band_volume"] = band_volume
        record["fill_band_minutes"] = band_minutes
        if band_volume is not None and level is not None:
            record["fill_band_notional"] = round(band_volume * level, 2)
        record["fill_plausible"], record["fill_plausible_reason"] = fill_verdict(
            record["fill_band_notional"], band_volume, band_minutes, level,
            band_pct, band_floor)

        true_volume = found["volume"]
        record["pm_volume_true"] = round(true_volume, 2)
        if prior:
            median = statistics.median(prior)
            record["true_baseline_median"] = round(median, 2)
            record["pm_rvol_true"] = _ratio(true_volume, median)
        else:
            record["truth_reason"] = (
                "no prior session in the window carried an alpaca bar for this "
                "symbol, so there is no baseline to divide by and pm_rvol_true "
                "is null rather than computed against the morning's EODHD one")
        share_float, outstanding = floats.get(ticker) or (None, None)
        share_float, float_refused = usable_float(share_float, outstanding)
        if share_float:
            record["pm_float_rotation_true"] = _ratio(true_volume, share_float)
        elif float_refused and not record["truth_reason"]:
            # First wins, the same convention the two clauses below follow.
            # A refused float is a null rotation WITH a reason, never a null
            # nobody can tell from a pass that has not run.
            record["truth_reason"] = (
                f"pm_float_rotation_true is null: {float_refused}")
        # capture_observed divides by the socket's OWN window, so it is
        # directly comparable to [Collector] premarket_capture_rate, which was
        # measured on common minutes. collector_window_share is the other
        # shortfall, the one this project has called a lower bound in prose
        # since 2026-08-14 without ever measuring it.
        in_socket_window = (on_socket.get(bare[ticker]) or {}) if not socket_error else {}
        socket_true = in_socket_window.get("volume") if in_socket_window.get("bars") else None
        record["true_volume_socket_window"] = (
            round(socket_true, 2) if socket_true is not None else None)
        record["collector_window_share"] = _ratio(socket_true, true_volume)
        # The same two levels over the socket's OWN window. Full against this
        # is what the 04:00 to 07:20 stretch costs; this against the live level
        # is the sampling. Conflating them is the error backfill_premarket's
        # docstring records having made and had to correct.
        if in_socket_window.get("bars"):
            record["entry_ref_collector_window"] = reference_level(
                in_socket_window, entry_field)
            record["stop_ref_collector_window"] = reference_level(
                in_socket_window, stop_field)
        record["capture_observed"] = _ratio(record["_socket"], socket_true)
        record["estimate_error"] = _ratio(record["_estimated"], true_volume)
        if socket_error and not record["truth_reason"]:
            record["truth_reason"] = (
                f"the collector window could not be fetched ({socket_error}), "
                "so what the socket captured of the minutes it was actually "
                "listening to is unknown for this row")
        if record["capture_observed"] is None and not record["truth_reason"]:
            record["truth_reason"] = (
                "neither the picks row nor the packet carried the morning's "
                "socket volume, so what the socket captured cannot be computed "
                "for this row even though the true volume is known")
        out.append(record)

    return {"day": day, "rows": out, "skipped": None, "cutoff": cutoff,
            "window": window_text, "sessions_used": sessions_used,
            "requests": probe.request_count, "dry_run": dry_run}


def write(result: dict[str, Any]) -> int:
    """Write the measured rows, and never over a measurement already held.

    A FAILED PASS MUST NOT ERASE A SUCCESSFUL ONE. Every record carries the
    full column set, with the true columns left None when the Alpaca fetch
    errored or came back below min_true_bars, and store.upsert writes every key
    it is given. So a second run over a session already measured, on a night
    Alpaca was down, replaced real SIP volume with NULL for every row and left
    a truth_reason beside it. store.py's own convention then reads that back as
    "the pass reached this row and could not measure it", which is exactly what
    it now looks like and is not what happened: it WAS measured, and the record
    of it is gone.

    The nightly sweeps unmeasured sessions and the 07:00 catch-up runs the same
    step, so a second pass over a measured session is the ordinary case rather
    than an unusual one, and --reread walks every session on purpose.

    A row is held back whole rather than merged column by column. The true
    columns are one measurement taken over one window: keeping pm_volume_true
    from Tuesday beside a capture_observed from Wednesday's failed attempt would
    publish a ratio whose halves came from different passes, which is the defect
    this project has already fixed twice under other names.
    """
    if result.get("dry_run") or not result["rows"]:
        return 0
    written = 0
    held: list[str] = []
    with store.session() as connection:
        store.init(connection)
        existing = {
            row["ticker"]: row["pm_volume_true"]
            for row in connection.execute(
                # source='live' because this read decides whether a
                # measured volume already on the row is about to be replaced
                # by a null, and it must compare against the row the truth
                # pass is actually writing.
                "SELECT ticker, pm_volume_true FROM picks "
                "WHERE date = ? AND source='live'",
                (result["day"],))
        }
        for record in result["rows"]:
            if (record.get("pm_volume_true") is None
                    and existing.get(record["ticker"]) is not None):
                held.append(record["ticker"])
                continue
            # Leading underscore keys are the morning's own columns, carried
            # for the printout. Writing them back would be an overwrite, and
            # this pass writes BESIDE the morning and never over it.
            payload = {k: v for k, v in record.items() if not k.startswith("_")}
            store.upsert(connection, "picks", ["date", "ticker"],
                         {**payload, "date": result["day"]})
            written += 1
        connection.commit()
    if held:
        print(f"truth: {len(held)} row(s) of {result['day']} already carry a "
              f"measurement and this pass could not take one, so they were left "
              f"as they stand rather than nulled: {', '.join(sorted(held))}. "
              "Re-run when the feed is back.")
        result["held"] = sorted(held)
    return written


def report(result: dict[str, Any]) -> None:
    if result["skipped"]:
        print(f"truth: nothing written for {result['day']}: {result['skipped']}")
        return
    rows = result["rows"]
    measured = [r for r in rows if r["pm_volume_true"] is not None]
    shares = [r["capture_observed"] for r in rows
              if r["capture_observed"] is not None]
    print(f"truth: {result['day']} over {result['window']}, "
          f"{len(measured)} of {len(rows)} live rows measured against "
          f"{len(result['sessions_used'])} prior sessions, "
          f"{result['requests']} alpaca requests, no EODHD quota")
    print(f"  {'ticker':<10} {'socket':>12} {'estimated':>13} "
          f"{'TRUE 04:00':>14} {'TRUE 07:20':>13} {'captured':>9} "
          f"{'window':>8} {'est err':>8} {'rvol_true':>10}")
    for record in rows:
        print(f"  {record['ticker']:<10} "
              f"{record['_socket'] if record['_socket'] is not None else 'null':>12} "
              f"{record['_estimated'] if record['_estimated'] is not None else 'null':>13} "
              f"{record['pm_volume_true'] if record['pm_volume_true'] is not None else 'null':>14} "
              f"{record['true_volume_socket_window'] if record['true_volume_socket_window'] is not None else 'null':>13} "
              f"{record['capture_observed'] if record['capture_observed'] is not None else 'null':>9} "
              f"{record['collector_window_share'] if record['collector_window_share'] is not None else 'null':>8} "
              f"{record['estimate_error'] if record['estimate_error'] is not None else 'null':>8} "
              f"{record['pm_rvol_true'] if record['pm_rvol_true'] is not None else 'null':>10}")
        if record["truth_reason"]:
            print(f"             {record['truth_reason']}")
    if shares:
        shares = sorted(shares)
        low, high = shares[0], shares[-1]
        shipped = _CRIT.number("collector", "premarket_capture_rate")
        print(f"truth: capture_observed ran {low:.4f} to {high:.4f}, median "
              f"{statistics.median(shares):.4f}, against the single {shipped} "
              "the morning divided every name by. Both sides of that "
              "comparison are the collector's own 07:20 window")
        if high and low and high / low >= 2.0:
            print(f"truth: that is a {high / low:.1f} fold spread within one "
                  "session, which is what a single divisor cannot carry")
        outside = [s for s in shares if s > shipped] or []
        print(f"truth: {len(shares) - len(outside)} of {len(shares)} symbols "
              f"captured LESS than the shipped {shipped}, so the morning "
              "divided by too large a share and understated them")
    pairs = [r for r in rows
             if r["_entry_ref"] and r["entry_ref_true"] is not None]
    if pairs:
        print(f"  {'ticker':<10} {'entry_ref':>12} {'entry TRUE':>12} "
              f"{'gap %':>9} {'stop_ref':>12} {'stop TRUE':>12} {'gap %':>9}")
        for record in pairs:
            entry_gap = ((record["entry_ref_true"] - record["_entry_ref"])
                         / record["_entry_ref"] * 100.0)
            stop_gap = (((record["stop_ref_true"] - record["_stop_ref"])
                         / record["_stop_ref"] * 100.0)
                        if record["_stop_ref"] and record["stop_ref_true"]
                        is not None else None)
            print(f"  {record['ticker']:<10} {record['_entry_ref']:>12} "
                  f"{record['entry_ref_true']:>12} {entry_gap:>+8.3f}% "
                  f"{record['_stop_ref'] if record['_stop_ref'] is not None else 'null':>12} "
                  f"{record['stop_ref_true'] if record['stop_ref_true'] is not None else 'null':>12} "
                  f"{f'{stop_gap:+.3f}%' if stop_gap is not None else 'null':>9}")
    verdicts = [r for r in rows if r["fill_plausible"] != FILL_PLAUSIBLE]
    for record in verdicts:
        print(f"  {record['ticker']}: fill {record['fill_plausible']}. "
              f"{record['fill_plausible_reason']}")
    for record in rows:
        if record["refs_true_reason"] and not record["truth_reason"]:
            print(f"  {record['ticker']}: no true reference level. "
                  f"{record['refs_true_reason']}")

    windows = sorted(r["collector_window_share"] for r in rows
                     if r["collector_window_share"] is not None)
    if windows:
        print(f"truth: the collector's 07:20 start saw a median "
              f"{statistics.median(windows):.4f} of the 04:00 premarket tape, "
              f"range {windows[0]:.4f} to {windows[-1]:.4f}. That is the OTHER "
              "lower bound, the one called arithmetic since 2026-08-14 and "
              "never measured until now")


def _spread(values: list[float]) -> str:
    """median, then the range, for a list nobody has checked is non empty."""
    ordered = sorted(values)
    return (f"median {statistics.median(ordered):+.3f}%, "
            f"range {ordered[0]:+.3f}% to {ordered[-1]:+.3f}%")


def reference_gap_report() -> None:
    """How far the sampled reference levels sit from the measured ones.

    THE WHOLE TABLE, not tonight's session, because one morning of twelve
    correlated names is one observation and this number is meant to stand as
    the project's standing estimate of a bias. Both denominators are printed
    for the reason fill_outcomes prints both: rows are not observations.

    Three quantities, and keeping them apart is the point.

      full     (entry_ref_true - entry_ref) / entry_ref, the whole gap, which
               is what actually reaches mfe_pct.
      sampling (entry_ref_collector_window - entry_ref) / entry_ref, the part
               inside the minutes the socket was listening to. This is the
               only one of the three that is a statement about the FEED.
      window   (entry_ref_true - entry_ref_collector_window) / that, the part
               that comes from the collector starting at 07:20 rather than
               04:00. A start time question, not a feed question.

    Reported in both directions and never as a correction. The sampled columns
    stay exactly as the morning wrote them.
    """
    with store.session() as connection:
        store.init(connection)
        rows = [dict(row) for row in connection.execute(
            "SELECT date, ticker, entry_ref, stop_ref, entry_ref_true, "
            "stop_ref_true, entry_ref_collector_window, "
            "stop_ref_collector_window FROM picks WHERE source='live' "
            "AND entry_ref IS NOT NULL AND entry_ref_true IS NOT NULL")]
    if not rows:
        print("truth: no live row carries both a sampled and a measured "
              "entry_ref, so the reference gap is not yet computable")
        return

    sessions = len({row["date"] for row in rows})
    entry_full = [(r["entry_ref_true"] - r["entry_ref"]) / r["entry_ref"] * 100.0
                  for r in rows if r["entry_ref"]]
    print("")
    print(f"truth: THE REFERENCE GAP, over {len(entry_full)} live rows across "
          f"{sessions} session(s). The sample unit is the session.")
    print(f"  entry_ref  measured against sampled: {_spread(entry_full)}")
    stop_rows = [r for r in rows
                 if r["stop_ref"] and r["stop_ref_true"] is not None]
    if stop_rows:
        stop_full = [(r["stop_ref_true"] - r["stop_ref"]) / r["stop_ref"] * 100.0
                     for r in stop_rows]
        print(f"  stop_ref   measured against sampled: {_spread(stop_full)}")

    split = [r for r in rows if r["entry_ref"]
             and r["entry_ref_collector_window"]]
    if not split:
        print("  no row carries entry_ref_collector_window, so the sampling "
              "and window halves of that gap cannot be separated yet")
    else:
        sampling = [(r["entry_ref_collector_window"] - r["entry_ref"])
                    / r["entry_ref"] * 100.0 for r in split]
        window = [(r["entry_ref_true"] - r["entry_ref_collector_window"])
                  / r["entry_ref_collector_window"] * 100.0 for r in split]
        print(f"  of which sampling, inside the socket's own minutes: "
              f"{_spread(sampling)}")
        print(f"  of which the 04:00 to 07:20 start:                 "
              f"{_spread(window)}")
    print("  A positive entry gap means the true premarket high ran ABOVE the "
          "level the collector saw, which is the direction mfe_pct is "
          "overstated by. A negative stop gap means the true low ran BELOW "
          "stop_ref, which is the direction mae_pct is overstated by. The two "
          "do not cancel by construction and neither column is corrected.")


def mark_unmeasurable(day: str, reason: str) -> int:
    """Record a REFUSED session on its rows, rather than leaving them null.

    measure() refuses a session whose packet does not say which window the
    morning used, because guessing one mismeasures precisely the sessions that
    went wrong. It then writes nothing at all, which leaves every row of that
    session with a null fill_plausible: a FOURTH state, sitting outside the
    three the column promises, and indistinguishable from a row the pass has
    simply not reached yet. 2026-08-21 is twelve such rows.

    'unknown' is the state for exactly this, so the refusal is written into it
    with the reason beside. That is a record of a refusal and not a
    measurement, and it invents no window, no level and no count.

    ONLY ROWS WITH NO VERDICT. A row that carries one was measured on some
    earlier night, and overwriting a measurement with a refusal is the failure
    write() above exists to prevent, one column across.
    """
    with store.session() as connection:
        store.init(connection)
        changed = connection.execute(
            "UPDATE picks SET fill_plausible=?, fill_plausible_reason=? "
            "WHERE date=? AND source='live' AND fill_plausible IS NULL",
            (FILL_UNKNOWN, reason, day)).rowcount
        connection.commit()
    if changed:
        print(f"truth: {changed} row(s) of {day} marked fill "
              f"{FILL_UNKNOWN}: {reason}")
    return changed


def fill_plausibility_report() -> None:
    """How many reference levels were prices anyone could have transacted at.

    THE WHOLE TABLE, and both denominators, because twelve names from one
    morning share a tape and are one observation.

    The three states are counted separately and 'unknown' is never folded into
    either of the others. A row the feed could not reach and a row that was
    checked and failed are opposite facts, and a count that adds them is the
    defect this column's three states exist to prevent.
    """
    with store.session() as connection:
        store.init(connection)
        rows = [dict(row) for row in connection.execute(
            "SELECT date, ticker, fill_plausible, fill_band_volume, "
            "fill_band_minutes, fill_band_notional, fill_band_pct, "
            "entry_ref_true FROM picks WHERE source='live'")]
    if not rows:
        print("truth: no live picks row, so fill plausibility is not computable")
        return
    sessions = len({row["date"] for row in rows})
    counted = {state: [r for r in rows if r["fill_plausible"] == state]
               for state in FILL_STATES}
    unlabelled = [r for r in rows if r["fill_plausible"] not in FILL_STATES]

    print("")
    print(f"truth: FILL PLAUSIBILITY, over {len(rows)} live rows across "
          f"{sessions} session(s). The sample unit is the session.")
    for state in FILL_STATES:
        held = counted[state]
        print(f"  {state:<12} {len(held):>3} of {len(rows)}")
    if unlabelled:
        # A row written before the column existed, or by something that
        # invented a fourth state. Named rather than counted into a bucket it
        # does not belong to.
        print(f"  {'no verdict':<12} {len(unlabelled):>3} of {len(rows)}, rows "
              "the pass has not reached: "
              f"{', '.join(sorted({r['ticker'] for r in unlabelled}))[:90]}")

    thin = sorted((r for r in counted[FILL_IMPLAUSIBLE]
                   if r["fill_band_notional"] is not None),
                  key=lambda r: r["fill_band_notional"])
    if thin:
        floor = _CRIT.number("truth", "min_fill_band_notional")
        print(f"  the levels that are prints rather than markets, against the "
              f"{floor:,.0f} dollar floor:")
        for row in thin[:15]:
            print(f"    {row['date']} {row['ticker']:<9} "
                  f"{row['fill_band_volume']:>10,.0f} shares over "
                  f"{row['fill_band_minutes']:>3} minute(s) = "
                  f"{row['fill_band_notional']:>13,.0f} dollars within "
                  f"{row['fill_band_pct'] * 100:g}% of "
                  f"{row['entry_ref_true']:g}")
        if len(thin) > 15:
            print(f"    and {len(thin) - 15} more")
    print("  The band volume is an UPPER BOUND on what traded at the level: a "
          "one minute bar carries no distribution, so a minute that ran from "
          "below up into the band counts whole. The minute count is exact and "
          "says how loose that bound is. See CRITERIA [Truth] the fill "
          "plausibility note.")


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the true premarket volume into picks, from Alpaca.")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                        help="The session to measure. Defaults to today.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Measure and print, write nothing.")
    parser.add_argument("--reread", action="store_true",
                        help="Re-read past sessions from their packets and "
                             "print what the true volume would have admitted. "
                             "Writes nothing.")
    args = parser.parse_args(argv)
    if args.reread:
        days = ([args.date] if args.date else
                sorted(p.parent.name
                       for p in config.RUNS_DIR.glob("*/packet.json")))
        results = [reread(one) for one in days]
        reread_report(results)
        job_status.produced("sessions re-read", len(results))
        return 0
    day = args.date or ettime.today_str()
    result = measure(day, dry_run=args.dry_run)
    written = write(result)
    if result.get("skipped") and not args.dry_run:
        # A refused session still gets a verdict, because 'no verdict' is a
        # fourth state the column does not have. See mark_unmeasurable.
        mark_unmeasurable(day, result["skipped"])
    report(result)
    # Reads the whole table rather than tonight's rows, so it stands as the
    # project's estimate of the bias rather than as one morning's. Printed
    # after the write so tonight's session is in it.
    if not args.dry_run:
        reference_gap_report()
        fill_plausibility_report()
    job_status.produced("rows given a true volume", written)
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("truth", main, ok_codes=OK_CODES))
