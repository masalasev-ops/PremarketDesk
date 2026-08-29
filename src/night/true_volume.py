"""What premarket volume ACTUALLY was, from Alpaca's full SIP tape.

The morning has no choice but to estimate. It divides the collector's socket
volume by [Collector] premarket_capture_rate, one number, 0.1172, because the
socket carries a fraction of the consolidated tape and the baseline it divides
into is built from whole tape bars. That correction is better than the raw
socket count it replaced, and it is still wrong in a way that matters: the
socket's share was measured at 2.1 to 12.1 percent over the 2026-08-19 probe
window, a six fold spread, and a single divisor cannot correct a quantity that
varies six fold.

THE ERROR IS NOT RANDOM, which is the part worth being angry about. Thin names
capture least, so thin names are understated most, and thin names are exactly
the population premarket float rotation exists to rescue. The correction
therefore reinstates at a lower layer the bias the float rotation fallback was
built to remove.

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


def fetch_window(probe: probe_alpaca.Probe, symbols: list[str],
                 start: dt.datetime, end: dt.datetime,
                 ) -> tuple[dict[str, dict[str, Any]], str | None]:
    """(per symbol volume and bar count, error). One window, all symbols.

    Paged and batched. A page token still outstanding at the page cap is an
    INCOMPLETE fetch and is returned as an error rather than as a total,
    because a truncated volume is indistinguishable from a quiet session and
    this whole module exists to stop numbers being read for more than they are.
    """
    batch_size = _CRIT.integer("truth", "symbols_per_request")
    max_pages = _CRIT.integer("truth", "max_pages_per_request")
    feed = _CRIT.text("truth", "feed")
    out: dict[str, dict[str, Any]] = {
        symbol: {"volume": 0.0, "bars": 0} for symbol in symbols}

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
                if symbol not in out:
                    continue
                for row in rows or []:
                    out[symbol]["volume"] += float(row.get("v") or 0)
                    out[symbol]["bars"] += 1
            token = (payload or {}).get("next_page_token")
            if not token:
                break
            if pages >= max_pages:
                return out, (f"{max_pages} pages consumed with a page token "
                             "still outstanding, so this window is incomplete")
    return out, None


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


def _as_float(value: Any) -> float | None:
    """A number the vendor may not have sent, coerced or refused. Never raises.

    The same shape scan._as_float has. usable_float below is handed raw quote
    fields, and a string, a None or a malformed value must come back as "no
    number" rather than as an exception inside a night job.
    """
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _ratio(top: float | None, bottom: float | None) -> float | None:
    if top is None or not bottom:
        return None
    return round(top / bottom, 6)


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
            "SELECT ticker, pm_volume, pm_volume_estimated FROM picks "
            "WHERE date=? AND source='live' ORDER BY ticker", (day,),
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
    observed, error = fetch_window(probe, symbols, start, end)
    socket_start, socket_end = _window(session_day, cutoff,
                                       ("collector", "start_time"))
    on_socket, socket_error = fetch_window(probe, symbols, socket_start,
                                           socket_end)
    history, sessions_used = prior_sessions(probe, symbols, session_day, cutoff)

    min_bars = _CRIT.integer("truth", "min_true_bars")
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
            "ticker": ticker, "true_window": window_text,
            "truth_source": source, "truth_at": stamp,
            "true_bars": found["bars"] or None,
            "true_baseline_sessions": len(prior) or None,
            "pm_volume_true": None, "pm_rvol_true": None,
            "pm_float_rotation_true": None, "true_baseline_median": None,
            "capture_observed": None, "estimate_error": None,
            "true_volume_socket_window": None, "collector_window_share": None,
            "truth_reason": None,
        }
        if error:
            record["truth_reason"] = error
            out.append(record)
            continue
        if found["bars"] < min_bars:
            record["truth_reason"] = (
                f"alpaca returned {found['bars']} bars inside {window_text}, "
                f"below [Truth] min_true_bars of {min_bars}")
            out.append(record)
            continue

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
                "SELECT ticker, pm_volume_true FROM picks WHERE date = ?",
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
    windows = sorted(r["collector_window_share"] for r in rows
                     if r["collector_window_share"] is not None)
    if windows:
        print(f"truth: the collector's 07:20 start saw a median "
              f"{statistics.median(windows):.4f} of the 04:00 premarket tape, "
              f"range {windows[0]:.4f} to {windows[-1]:.4f}. That is the OTHER "
              "lower bound, the one called arithmetic since 2026-08-14 and "
              "never measured until now")


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
    report(result)
    job_status.produced("rows given a true volume", written)
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("truth", main, ok_codes=OK_CODES))
