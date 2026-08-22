"""The Monday test: is the free tier's premarket servable at 08:45, and what did the socket capture?

Two questions on one morning, because there is one morning a day and one
sweep answers both.

The first is entitlement, and DECISIONS.md 2026-08-22 says why it is still
open. Every request research/probe_alpaca_live.py has ever made built its
window's end from the wall clock, which reaches into the delay the free tier
documents, so all 46 of them were refused before the feed was ever consulted.
One request on Saturday 2026-08-22 asked for the window the delay ALLOWS and
was answered, HTTP 200, but that window held no trading, so what it measured
was the entitlement and not the feed. Nobody has yet asked this vendor a
question it would answer about a RUNNING session.

The second is the capture ratio, which has never been measured on the session
it is applied to. CRITERIA [Collector] premarket_capture_rate is 0.1172: the
median per symbol share of the consolidated tape the socket carries, derived
by comparing collector volume against EODHD 1m intraday over identical
minutes, hours after the fact, across four sessions. The morning divides by it
at 08:45 and cannot check it until the evening. One Alpaca sweep at 08:45
gives both sides of that ratio from the same tape, over the same minutes, on
the morning it is being used.

Why the two travel together. If the sweep is refused the second question does
not arise. If it is served, the second question is the one that decides
whether anything should change, and reading the first without the second is
how a design came to be written off a Saturday.

**The production window control, and why it is here rather than assumed.**
This test sweeps 04:00 to 08:30 at 08:45, and 08:30 is derived rather than
chosen: it is [Scan] run_time minus [Truth] documented_lag_minutes, the latest
end the free tier will serve at that clock. The morning's OWN window does not
end there. scan snaps rvol_cutoff_hhmm to run_time inside
rvol_cutoff_snap_minutes, so what production actually computes premarket RVOL
over is 04:00 to 08:45, ending AT the wall clock, which is precisely the shape
that has been refused 46 times. A served 08:30 window therefore does not on
its own mean the morning could use this feed. It means the morning would have
to accept a window fifteen minutes shorter than the one it uses, and those
fifteen minutes are the densest of the premarket. One extra request asks for
the production window at the production clock, so that gap is measured on this
morning rather than argued about after it.

**Cost, and what it touches.** About four requests for the sweep and one for
the control, all Alpaca, all free. Zero EODHD credits: no quota, no
competition with the morning chain. It reads the collector's own bar file and
writes two files under data/. It changes nothing in the production path, and
it is a one off that is meant to be deleted once DECISIONS carries its answer.

  python -m research.probe_capture_live              measure today
  python -m research.probe_capture_live --date D     measure a past session
  python -m research.probe_capture_live --report D   read a written result back
  python -m research.probe_capture_live --no-control skip the production window request
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from collect import collect_premarket
from core import config
from core import criteria
from core import ettime
import probe_alpaca

_CRIT = criteria.load()

# Symbols per request. doc/ALPACA_PROBE.md measured a full 2,745 name sweep at
# 4 requests, which is two chunks of this size and a page or two each. Named
# rather than left inline because the request count is part of what this file
# promises and a reader has to be able to check the promise.
CHUNK_SIZE = 2000

# Seconds past the production clock before the sweep is fired, and the reason
# it is not zero. The window's end is a FIXED clock, 08:30, while the vendor's
# refusal rule is relative to the wall clock at the moment of the request. Fire
# at 08:44:58 and the window is fourteen minutes fifty eight seconds old, which
# is inside the documented delay, and the answer is the 403 this whole test
# exists to step around. Task Scheduler jitter is real, clock skew between this
# machine and the vendor is real, and waiting half a minute costs nothing on a
# morning that cannot be repeated.
FIRE_GUARD_S = 30

# How long this will wait for that clock rather than refusing. A run started
# well before the production clock is asking for a window that has not closed
# yet, and sleeping an hour inside a scheduled task is worse than saying so.
MAX_WAIT_S = 20 * 60

PATH_STEM = "probe-capture-live"


def result_path(day: str) -> Path:
    return config.DATA_DIR / f"{PATH_STEM}-{day}.json"


def page_path(day: str) -> Path:
    return config.DATA_DIR / f"{PATH_STEM}-{day}.md"


def universe_codes() -> list[str]:
    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    return [row["code"] for row in payload["symbols"]]


def windows(day: dt.date) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    """(open, servable end, production end) for one session, all in ET.

    Every one of the three is derived from CRITERIA and none is a literal,
    because the whole point of the servable end is the arithmetic that
    produces it: it is the production end minus the documented delay, and if
    either of those moves this window has to move with it or the test silently
    stops matching production.
    """
    open_h, open_m = _CRIT.clock("baseline", "session_start")
    run_h, run_m = _CRIT.clock("scan", "run_time")
    lag = _CRIT.number("truth", "documented_lag_minutes")
    opened = dt.datetime(day.year, day.month, day.day, open_h, open_m, tzinfo=ettime.ET)
    production = dt.datetime(day.year, day.month, day.day, run_h, run_m, tzinfo=ettime.ET)
    return opened, production - dt.timedelta(minutes=lag), production


def _rfc3339(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sweep(
    probe: probe_alpaca.Probe,
    codes: list[str],
    start: dt.datetime,
    end: dt.datetime,
    watch: set[str],
) -> dict[str, Any]:
    """One window over the whole universe, with per minute detail for watch.

    Per minute volumes are kept ONLY for the symbols the collector subscribed
    to, and that is the whole reason this can answer the capture question
    inside four requests. The capture share has to be measured over the
    minutes both tapes carry, exactly as verify_against_intraday measures it
    against EODHD, and a second sweep restricted to the collector's clock
    window would cost four more requests to recover something the first sweep
    already returned and threw away.

    Served and refused are counted separately, on the precedent of
    probe_alpaca_live: a refused sweep and an empty one produce identical
    zeros, and until the counts were carried the 2026-08-17 run was read as an
    empty premarket for two days.
    """
    max_pages = _CRIT.integer("truth", "max_pages_per_request")
    feed = _CRIT.text("truth", "feed")
    totals: dict[str, dict[str, Any]] = {}
    minutes: dict[str, dict[int, float]] = {}
    served = refused = 0
    codes_seen: set[int] = set()
    errors: list[str] = []
    incomplete: str | None = None
    before = probe.request_count

    for index in range(0, len(codes), CHUNK_SIZE):
        chunk = codes[index:index + CHUNK_SIZE]
        token, pages = None, 0
        while True:
            params = {"symbols": ",".join(chunk), "timeframe": "1Min",
                      "start": _rfc3339(start), "end": _rfc3339(end),
                      "limit": probe_alpaca.PAGE_LIMIT, "feed": feed}
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            pages += 1
            if status != 200:
                refused += 1
                codes_seen.add(int(status))
                # The body, not just the number. The refusal sentence is the
                # only thing that says WHICH rule the vendor applied, and
                # discarding it is what let 46 refusals be read as one thing.
                errors.append(f"chunk at {index}: status {status}: "
                              f"{probe_alpaca._error_text(payload)}")
                break
            served += 1
            for symbol, rows in ((payload or {}).get("bars") or {}).items():
                bucket = totals.setdefault(symbol, {"volume": 0.0, "bars": 0})
                keep = symbol in watch
                for row in rows or []:
                    volume = float(row.get("v") or 0)
                    bucket["volume"] += volume
                    bucket["bars"] += 1
                    if not keep:
                        continue
                    stamp = row.get("t") or ""
                    try:
                        epoch = int(dt.datetime.fromisoformat(
                            stamp.replace("Z", "+00:00")).timestamp())
                    except (ValueError, AttributeError):
                        continue
                    per = minutes.setdefault(symbol, {})
                    per[epoch] = per.get(epoch, 0.0) + volume
            token = (payload or {}).get("next_page_token")
            if not token:
                break
            if pages >= max_pages:
                # An outstanding page token at the cap is an INCOMPLETE fetch,
                # and a truncated volume is indistinguishable from a quiet
                # session. true_volume.fetch_window refuses the same way and
                # for the same reason.
                incomplete = (f"{max_pages} pages consumed on the chunk at "
                              f"{index} with a page token still outstanding, "
                              "so this window is incomplete and its volumes "
                              "are floors rather than totals")
                break
        if incomplete:
            break

    return {
        "window": {"start": _rfc3339(start), "end": _rfc3339(end)},
        "window_et": {"start": ettime.stamp(start), "end": ettime.stamp(end)},
        "feed": feed,
        "symbols_requested": len(codes),
        "requests_made": probe.request_count - before,
        "requests_served": served,
        "requests_refused": refused,
        "refusal_status_codes": sorted(codes_seen),
        "errors": errors[:8],
        "incomplete": incomplete,
        "symbols_with_bars": sum(1 for row in totals.values() if row["bars"]),
        "bars_total": sum(row["bars"] for row in totals.values()),
        "_totals": totals,
        "_minutes": minutes,
    }


def control_request(
    probe: probe_alpaca.Probe,
    codes: list[str],
    start: dt.datetime,
    end: dt.datetime,
) -> dict[str, Any]:
    """ONE request for the window PRODUCTION uses, at the clock production uses it.

    One chunk, not a sweep. If this shape is refused the first chunk says so
    and the rest would only repeat it; if it is served, the fact that it is
    served is the whole finding and the bar counts are the sweep's job.
    """
    feed = _CRIT.text("truth", "feed")
    chunk = codes[:CHUNK_SIZE]
    before = probe.request_count
    fired_at = ettime.now_et()
    # A control fired late is not a control. The refusal rule is about how
    # recent the window's end is, so once the wall clock has moved a documented
    # delay past the production clock this same request becomes servable for a
    # reason that has nothing to do with production, and a 200 then says
    # nothing at all. Recorded rather than assumed, because a run at 09:30 and
    # a run at 08:45 produce identical looking records otherwise.
    lag = _CRIT.number("truth", "documented_lag_minutes")
    informative = fired_at < end + dt.timedelta(minutes=lag)
    status, payload, elapsed = probe.get({
        "symbols": ",".join(chunk), "timeframe": "1Min",
        "start": _rfc3339(start), "end": _rfc3339(end),
        "limit": probe_alpaca.PAGE_LIMIT, "feed": feed})
    body = json.dumps(payload, separators=(",", ":"), default=str)
    bars = ((payload or {}).get("bars") or {}) if isinstance(payload, dict) else {}
    return {
        "window": {"start": _rfc3339(start), "end": _rfc3339(end)},
        "window_et": {"start": ettime.stamp(start), "end": ettime.stamp(end)},
        "symbols_requested": len(chunk),
        "requests_made": probe.request_count - before,
        "fired_at_et": ettime.stamp(fired_at),
        "at_production_clock": bool(informative),
        "status": int(status),
        "elapsed_s": round(elapsed, 3),
        "body": body[:2000],
        "body_truncated": len(body) > 2000,
        "message": probe_alpaca._error_text(payload) if status != 200 else None,
        "symbols_with_bars": sum(1 for rows in bars.values() if rows),
    }


def capture_rows(
    day: str,
    minutes: dict[str, dict[int, float]],
    totals: dict[str, dict[str, Any]],
    requested_bare: set[str],
) -> dict[str, Any]:
    """The capture share per symbol, over the minutes both tapes carry.

    This is deliberately the same measurement collect_premarket
    .verify_against_intraday makes, with Alpaca's full SIP tape in place of
    EODHD's 1m intraday, so the number that comes out is directly comparable
    to CRITERIA [Collector] premarket_capture_rate rather than merely similar
    to it. Same intersection of minutes, same per symbol ratio, same four
    buckets, and the same refusal ladder scan applies before it will trust a
    measured share over the file wide default.

    A symbol lands in exactly one of compared, not_requested, alpaca_silent,
    alpaca_zero or collector_silent, and those five sum to symbols_accounted.
    That accounting exists because the version of this comparison that walked
    only the collected bars left a subscribed symbol the socket never answered
    for in no bucket at all, and the summary then read as though it had been
    measured and agreed.

    not_requested is the bucket this file was written without and needed on
    its first run. The collector subscribes to the market snapshot proxies,
    SPY, QQQ, DIA, IWM, TLT, USO, UUP and VIXY, and universe.json does not
    carry them, so a sweep built from the universe alone never asks Alpaca
    about them. Eleven symbols on 2026-08-20 then landed under "Alpaca had no
    overlapping minute", which is a statement about the vendor, when what
    happened was that this test never asked. measure() now adds them to the
    request list so the bucket should stay empty, and it is kept so that if it
    ever fills the symbols are named instead of being counted as vendor
    silence.
    """
    default = _CRIT.number("collector", "premarket_capture_rate")
    min_vendor = _CRIT.number("collector", "min_capture_vendor_volume")
    min_minutes = _CRIT.integer("collector", "min_capture_minutes")

    bars = collect_premarket.read_bars(day)
    subscriptions = collect_premarket.read_subscriptions(day) or {}
    requested = sorted(str(s) for s in (subscriptions.get("symbols") or []))

    rows: list[dict[str, Any]] = []
    not_requested: list[str] = []
    alpaca_silent: list[str] = []
    alpaca_zero: list[str] = []
    for symbol in sorted(bars):
        bare = symbol.split(".", 1)[0]
        if bare not in requested_bare:
            not_requested.append(symbol)
            continue
        mine = {int(bar["minute_epoch"]): float(bar.get("v") or 0)
                for bar in bars[symbol] if bar.get("minute_epoch") is not None}
        theirs = minutes.get(bare) or {}
        common = sorted(set(mine) & set(theirs))
        if not common:
            alpaca_silent.append(symbol)
            continue
        collector_volume = sum(mine[epoch] for epoch in common)
        alpaca_volume = sum(theirs[epoch] for epoch in common)
        if alpaca_volume <= 0:
            alpaca_zero.append(symbol)
            continue

        share = collector_volume / alpaca_volume
        # The same ladder as scan.apply_capture_correction, in the same order,
        # so a share this file reports as usable is one production would also
        # have trusted. Floor the evidence, never cap the ratio: a cap turns a
        # visible absurdity into an invisible one.
        refused = None
        if alpaca_volume < min_vendor:
            refused = (f"it rested on {alpaca_volume:,.0f} alpaca share(s), under "
                       f"the {min_vendor:,.0f} floor")
        elif len(common) < min_minutes:
            refused = (f"it rested on {len(common)} common minute(s), under the "
                       f"{min_minutes} floor")
        elif share >= 1.0:
            refused = (f"it came out at {share:.2f}, and a socket that carries a "
                       "subset of the tape cannot report all of it")

        whole = (totals.get(bare) or {}).get("volume")
        rows.append({
            "symbol": symbol,
            "common_minutes": len(common),
            "collector_volume": round(collector_volume, 2),
            "alpaca_volume_common": round(alpaca_volume, 2),
            "capture_share": round(share, 6),
            "usable": refused is None,
            "refused_reason": refused,
            "alpaca_volume_window": round(whole, 2) if whole is not None else None,
            # The other shortfall, and a different fix from the first. The
            # socket cannot see 04:00 to its own start time at all, so this
            # says how much of the premarket window the minutes it DID hear
            # were worth. A capture share and a window share are two ways to
            # be short of the tape and they are not interchangeable.
            "collector_window_share": (
                round(alpaca_volume / whole, 6) if whole else None),
        })

    collector_silent = sorted(set(requested) - set(bars))
    outside = sorted(set(bars) - set(requested))
    usable = [row["capture_share"] for row in rows if row["usable"]]
    return {
        "default_capture_rate": default,
        "min_capture_vendor_volume": min_vendor,
        "min_capture_minutes": min_minutes,
        "subscribed": len(requested),
        "symbols_accounted": len(set(bars) | set(requested)),
        "compared": len(rows),
        "usable_count": len(usable),
        "not_requested": not_requested,
        "alpaca_silent": alpaca_silent,
        "alpaca_zero": alpaca_zero,
        "collector_silent": collector_silent,
        "bars_outside_subscription": outside,
        "median_capture_share": round(statistics.median(usable), 6) if usable else None,
        "min_capture_share": round(min(usable), 6) if usable else None,
        "max_capture_share": round(max(usable), 6) if usable else None,
        "rows": sorted(rows, key=lambda row: row["symbol"]),
    }


def _wait_for_clock(production: dt.datetime) -> float:
    """Hold until FIRE_GUARD_S past the production clock, and say so.

    Returns the seconds waited. Zero when the clock is already past, which is
    every past session and any run started late. Refuses rather than sleeping
    when the target is further off than MAX_WAIT_S, because a run started at
    06:00 is asking for a window that has not closed yet and the honest answer
    is that it is too early, not a scheduled task asleep for two hours.
    """
    target = production + dt.timedelta(seconds=FIRE_GUARD_S)
    now = ettime.now_et()
    if now >= target:
        return 0.0
    seconds = (target - now).total_seconds()
    if seconds > MAX_WAIT_S:
        raise SystemExit(
            f"capture test: it is {ettime.stamp(now)} and the window does not "
            f"close until {ettime.stamp(production)}. Asking now would request a "
            f"window that has not happened yet. Start this within "
            f"{MAX_WAIT_S // 60:.0f} minutes of the production clock.")
    print(f"capture test: waiting {seconds:.0f}s for {ettime.stamp(target)}, "
          f"which is {FIRE_GUARD_S}s past the production clock. The window's end "
          "is a fixed 08:30 and the vendor's refusal rule is relative to the wall "
          "clock, so firing early asks for a window inside the documented delay.")
    time.sleep(seconds)
    return round(seconds, 1)


def measure(day: str, control: bool = True, probe: Any = None) -> dict[str, Any]:
    """Everything this test records for one session, computed before it writes."""
    session = ettime.parse_date(day)
    opened, servable, production = windows(session)
    bars = collect_premarket.read_bars(day)
    watch = {symbol.split(".", 1)[0] for symbol in bars}

    # The universe is the discovery population and it is NOT the collector's
    # subscription list. The collector also carries the market snapshot
    # proxies, SPY, QQQ, DIA, IWM, TLT, USO, UUP and VIXY, and universe.json
    # holds none of them, so a sweep built from the universe alone never asks
    # Alpaca about a quarter of the names the capture share is measured over.
    # On the 2026-08-20 shakedown that silently moved eleven symbols into a
    # bucket labelled as vendor silence. They cost nothing to add: the chunk
    # they join is already being sent.
    # universe.json carries BARE codes, "A" and "AAPL", because that is what
    # Alpaca takes. The collector carries the .US suffix EODHD uses. Anything
    # added here is added in Alpaca's form, and the first version of this line
    # appended "SPY.US", which the vendor cannot resolve, so the eight proxies
    # were requested under a name that does not exist and came back silent
    # exactly as if they had never been asked for.
    codes = universe_codes()
    known = set(codes)
    added = sorted({symbol.split(".", 1)[0] for symbol in bars} - known)
    codes = codes + added
    requested_bare = known | set(added)

    probe = probe if probe is not None else probe_alpaca.Probe()
    waited = _wait_for_clock(production)
    taken_at = ettime.now_et()
    swept = sweep(probe, codes, opened, servable, watch)
    totals = swept.pop("_totals")
    minutes = swept.pop("_minutes")

    result: dict[str, Any] = {
        "day": day,
        "taken_at_et": ettime.stamp(taken_at),
        "waited_for_clock_s": waited,
        "documented_lag_minutes": _CRIT.number("truth", "documented_lag_minutes"),
        "scan_run_time": _CRIT.clock_text("scan", "run_time"),
        "sweep": swept,
        "control": None,
        "capture": None,
        "collector_symbols_with_bars": len(bars),
        "collector_symbols_added_to_sweep": added,
        "requests_total": probe.request_count,
    }
    if control:
        result["control"] = control_request(probe, codes, opened, production)
        result["requests_total"] = probe.request_count

    if not swept["requests_served"]:
        result["capture_skipped"] = (
            "no request in the sweep was answered, so there is no Alpaca side "
            "to compare the collector against. A zero here is what a refused "
            "sweep returns and not what the tape held.")
        return result
    if not bars:
        result["capture_skipped"] = (
            f"the collector wrote no bars for {day}, so the socket side of the "
            "ratio does not exist. The sweep result above still stands on its own.")
        return result

    result["capture"] = capture_rows(day, minutes, totals, requested_bare)
    return result


# ---------------------------------------------------------------- reporting


def _served_phrase(swept: dict[str, Any]) -> str:
    if swept["requests_refused"] and not swept["requests_served"]:
        codes = ", ".join(str(c) for c in swept["refusal_status_codes"]) or "no status"
        return f"REFUSED, every one of {swept['requests_refused']} request(s), status {codes}"
    if swept["requests_refused"]:
        return (f"PARTLY SERVED, {swept['requests_served']} answered against "
                f"{swept['requests_refused']} refused")
    return f"SERVED, all {swept['requests_served']} request(s)"


def write_page(result: dict[str, Any]) -> Path:
    """The readable half, so the answer outlives a terminal it cannot be re-run into."""
    day = result["day"]
    swept = result["sweep"]
    capture = result.get("capture")
    lines = [
        f"# Alpaca live capture test, {day}",
        "",
        f"Taken at {result['taken_at_et']}. One sweep of "
        f"{swept['symbols_requested']:,} symbols over "
        f"{swept['window_et']['start']} to {swept['window_et']['end']}, "
        f"{result['requests_total']} Alpaca request(s), zero EODHD credits.",
        "",
        "## 1. Was the request served",
        "",
        f"**{_served_phrase(swept)}.**",
        "",
    ]
    if swept["errors"]:
        lines += ["The vendor's own words, kept rather than reduced to a status number:", ""]
        lines += [f"- `{text}`" for text in swept["errors"]]
        lines += [""]
    if swept["incomplete"]:
        lines += [f"> **INCOMPLETE.** {swept['incomplete']}", ""]

    control = result.get("control")
    if control:
        served = control["status"] == 200
        lines += [
            "### The production window, at the production clock",
            "",
            f"The morning computes premarket RVOL over 04:00 to "
            f"{result['scan_run_time']}, ending AT the wall clock, because scan "
            f"snaps its cutoff to [Scan] run_time. One request asked for exactly "
            f"that window at {control['fired_at_et']}: "
            f"**status {control['status']}**.",
            "",
        ]
        if not control.get("at_production_clock", True):
            lines += [
                "> **THIS CONTROL WAS FIRED TOO LATE TO MEAN ANYTHING.** It went "
                "out more than a documented delay past the production clock, so "
                "the window it asked for was no longer recent and the vendor had "
                "no reason to refuse it whatever it does at 08:45. Read the "
                "status above as a fact about when this ran, not about "
                "production.",
                "",
            ]
        elif served:
            lines += [
                "It was served, so the fifteen minute setback above is not "
                "needed and the morning's own window is reachable as it stands.",
                "",
            ]
        else:
            lines += [
                f"It was refused: `{control['message']}`. So the sweep above "
                "measures a window fifteen minutes SHORTER than the one the "
                "morning uses, and those are the densest fifteen minutes of the "
                "premarket. Any design that reads this feed at 08:45 has to "
                "either move the cutoff back or accept a window production does "
                "not currently use.",
                "",
            ]

    lines += [
        "## 2. How many symbols returned bars",
        "",
        f"- {swept['symbols_with_bars']:,} of {swept['symbols_requested']:,} "
        f"symbols carried at least one bar",
        f"- {swept['bars_total']:,} minute bars in total",
        f"- the collector heard {result['collector_symbols_with_bars']} symbol(s) "
        "on the same morning, which is the population the capture share can be "
        "measured over",
        "",
    ]

    if not capture:
        lines += ["## 3 and 4. The capture share", "",
                  result.get("capture_skipped", "not measured"), ""]
        path = page_path(day)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    default = capture["default_capture_rate"]
    lines += [
        "## 3. The per symbol capture, measured on this morning",
        "",
        "Collector volume over Alpaca SIP volume, over the minutes BOTH tapes "
        "carry, which is the same intersection verify_against_intraday uses "
        "against EODHD. A share is refused, and the reason recorded, on the "
        f"same ladder scan applies: under {capture['min_capture_vendor_volume']:,.0f} "
        f"vendor shares, under {capture['min_capture_minutes']} common minutes, "
        "or at or above 1.0, which is impossible for a venue subset.",
        "",
        "| symbol | common minutes | collector | alpaca | share | usable |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in capture["rows"]:
        mark = "yes" if row["usable"] else f"no, {row['refused_reason']}"
        lines.append(
            f"| {row['symbol']} | {row['common_minutes']} | "
            f"{row['collector_volume']:,.0f} | {row['alpaca_volume_common']:,.0f} | "
            f"{row['capture_share']:.4f} | {mark} |")
    lines += [
        "",
        f"- {capture['compared']} symbol(s) compared, {capture['usable_count']} of "
        "them passing the floors",
        f"- {len(capture.get('not_requested') or [])} carried collector bars but "
        "were never requested from Alpaca, which is this test's own blind spot "
        "and not the vendor's silence: "
        + (", ".join(capture.get("not_requested") or []) or "none"),
        f"- {len(capture['alpaca_silent'])} were requested and Alpaca had no "
        "overlapping minute for them",
        f"- {len(capture['alpaca_zero'])} had zero Alpaca volume over the common "
        "minutes and could not be compared",
        f"- {len(capture['collector_silent'])} subscribed symbol(s) the collector "
        "never heard: " + (", ".join(capture["collector_silent"]) or "none"),
        f"- the four buckets account for {capture['symbols_accounted']} symbol(s) "
        f"against {capture['subscribed']} on the subscription list",
        "",
        "## 4. Against the 0.1172 the correction assumes",
        "",
    ]
    if capture["median_capture_share"] is None:
        lines += ["No share survived the floors, so there is nothing to compare "
                  "and the default stands unexamined by this session.", ""]
    else:
        median = capture["median_capture_share"]
        lines += [
            f"- measured median this morning: **{median:.4f}** over "
            f"{capture['usable_count']} symbol(s), running "
            f"{capture['min_capture_share']:.4f} to {capture['max_capture_share']:.4f}",
            f"- CRITERIA [Collector] premarket_capture_rate: **{default:.4f}**",
            f"- ratio of the two: {median / default:.2f}",
            "",
            "What that does and does not license. This is ONE session against a "
            "number derived from four, and it is measured against a different "
            "vendor's tape than the four were. It is evidence about the default's "
            "size, not a replacement for it, and the correction should not move "
            "on one morning. What it does settle is whether the two tapes agree "
            "at all about what the socket is missing, which no reading so far "
            "has had.",
            "",
        ]
    path = page_path(day)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def report(result: dict[str, Any]) -> None:
    """The four answers, in the order they were asked for."""
    swept = result["sweep"]
    capture = result.get("capture")
    print(f"\ncapture test: {result['day']}, taken {result['taken_at_et']}, "
          f"{result['requests_total']} Alpaca request(s), 0 EODHD credits\n")

    print(f"1. served or refused    {_served_phrase(swept)}")
    print(f"   window               {swept['window_et']['start']} to "
          f"{swept['window_et']['end']}")
    for text in swept["errors"]:
        print(f"   vendor said          {text}")
    if swept["incomplete"]:
        print(f"   INCOMPLETE           {swept['incomplete']}")
    control = result.get("control")
    if control:
        print(f"   production window    04:00 to {result['scan_run_time']}, fired "
              f"{control['fired_at_et'][11:19]}, status {control['status']}"
              + (f", {control['message']}" if control["message"] else ""))
        if not control.get("at_production_clock", True):
            print("   CONTROL NOT VALID    fired more than a documented delay past "
                  "the production clock, so its window was no longer recent and "
                  "the status says nothing about what production would get")

    print(f"\n2. symbols with bars    {swept['symbols_with_bars']:,} of "
          f"{swept['symbols_requested']:,}, {swept['bars_total']:,} bars")
    print(f"   collector heard      {result['collector_symbols_with_bars']} symbol(s)")

    if not capture:
        print(f"\n3. capture              not measured: {result.get('capture_skipped')}")
        print("4. against 0.1172       nothing to compare")
        return

    print(f"\n3. per symbol capture   {capture['compared']} compared, "
          f"{capture['usable_count']} passing the floors")
    print(f"   {'symbol':<10} {'mins':>5} {'collector':>13} {'alpaca':>13} "
          f"{'share':>8}  note")
    for row in capture["rows"]:
        note = "" if row["usable"] else f"refused: {row['refused_reason']}"
        print(f"   {row['symbol']:<10} {row['common_minutes']:>5} "
              f"{row['collector_volume']:>13,.0f} "
              f"{row['alpaca_volume_common']:>13,.0f} "
              f"{row['capture_share']:>8.4f}  {note}")
    if capture.get("not_requested"):
        print(f"   {len(capture['not_requested'])} had collector bars and were "
              f"NEVER REQUESTED, so this test could not see them: "
              f"{', '.join(capture['not_requested'])}")
    if capture["alpaca_silent"]:
        print(f"   {len(capture['alpaca_silent'])} requested and Alpaca had no "
              f"overlapping minute: {', '.join(capture['alpaca_silent'])}")
    if capture["collector_silent"]:
        print(f"   {len(capture['collector_silent'])} subscribed and never heard: "
              f"{', '.join(capture['collector_silent'])}")

    default = capture["default_capture_rate"]
    median = capture["median_capture_share"]
    if median is None:
        print(f"\n4. against {default:.4f}       no share survived the floors")
        return
    print(f"\n4. against {default:.4f}       measured median {median:.4f} over "
          f"{capture['usable_count']} symbol(s), "
          f"{capture['min_capture_share']:.4f} to {capture['max_capture_share']:.4f}")
    print(f"   ratio                {median / default:.2f} times the assumed rate")
    print("   ONE session against a number derived from four, and against a "
          "different vendor's tape. Evidence about the default's size, not a "
          "replacement for it.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sweep Alpaca at 08:45 and measure what the socket captured.")
    parser.add_argument("--date", default=None, help="Which session. Defaults to today.")
    parser.add_argument("--report", action="store_true",
                        help="Read a written result back instead of measuring.")
    parser.add_argument("--no-control", action="store_true",
                        help="Skip the one extra request for the production window.")
    args = parser.parse_args(argv)
    day = args.date or ettime.today_str()

    if args.report:
        path = result_path(day)
        if not path.is_file():
            print(f"capture test: nothing written for {day} at {path}")
            return 0
        report(json.loads(path.read_text(encoding="utf-8")))
        return 0

    result = measure(day, control=not args.no_control)
    path = result_path(day)
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    page = write_page(result)
    report(result)
    print(f"\ncapture test: written to {path}")
    print(f"capture test: page written to {page}")
    return 0


if __name__ == "__main__":
    # Deliberately NOT wrapped in job_status.run. This is a one off probe and
    # not a scheduled step, and CRITERIA.md [job status steps] must not gain a
    # step that is meant to stop existing.
    sys.exit(main())
