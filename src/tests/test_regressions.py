"""One claim per defect found by the 2026-08-20 audit, so none of them returns.

An adversarial read of the whole scheduled path raised forty findings and
twenty survived independent verification. Every one of those twenty is fixed
and every one of them is here. They have nothing in common except how they were
found, which is why they are grouped by that rather than scattered across the
themed suites: a reader asking "what did that audit actually catch" gets one
file, and a reader asking "is it still caught" runs it.

The pattern across them, worth naming because it will recur. Almost none was a
wrong algorithm. They were seams: a UTC clock relabelled instead of converted,
an instrument sharing a function with the thing it measures, a write that
marked its work done before doing it, a guard whose docstring described a
stricter test than the code made. Each looked correct in isolation and was
wrong in composition.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import contextlib
import os
import pathlib
import sys
import tempfile
from typing import Any

from core import config
from core import ettime


# --------------------------------------------------------------- the clock

def claim_the_november_transition(failures: list[str]) -> None:
    """The fixed rule fallback lands both transitions on the right instant.

    zoneinfo is unavailable on this machine, so _USEasternFallback is
    load bearing rather than decorative. dt.tzinfo's default fromutc() runs the
    daylight test on the standard time clock, which is right in March and an
    hour out in November, where the rule is written in daylight time. Every UTC
    instant from 06:00 to 06:59 on the November Sunday came back as 02:xx EST
    when it is 01:xx EST, so 02:00 EST was produced twice and 01:00 EST never.
    """
    expected = {
        # 2026-11-01, the first Sunday: 01:59:59 EDT becomes 01:00:00 EST at 06:00 UTC.
        (2026, 11, 1, 5, 59): ("01:59", "EDT"),
        (2026, 11, 1, 6, 0): ("01:00", "EST"),
        (2026, 11, 1, 6, 59): ("01:59", "EST"),
        (2026, 11, 1, 7, 0): ("02:00", "EST"),
        # 2026-03-08, the second Sunday: 01:59:59 EST becomes 03:00:00 EDT at 07:00 UTC.
        (2026, 3, 8, 6, 59): ("01:59", "EST"),
        (2026, 3, 8, 7, 0): ("03:00", "EDT"),
    }
    for parts, (clock, name) in expected.items():
        got = dt.datetime(*parts, tzinfo=dt.timezone.utc).astimezone(ettime.ET)
        if (got.strftime("%H:%M"), got.tzname()) != (clock, name):
            failures.append(
                f"{parts} UTC converted to {got.strftime('%H:%M %Z')}, expected "
                f"{clock} {name}")

    # Every hour of a year, because a transition fix that breaks an ordinary
    # Tuesday is worse than the bug.
    moment = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    broken = 0
    while moment < end:
        if moment.astimezone(ettime.ET).astimezone(dt.timezone.utc) != moment:
            broken += 1
        moment += dt.timedelta(hours=1)
    if broken:
        failures.append(f"{broken} instant(s) in 2026 do not round trip through ET")
    print("  clock        both 2026 transitions land on the right instant and "
          "all 8,760 hours round trip")


# ------------------------------------------------------- the economic clock

class _EventsApi:
    """Just enough EodhdClient for economic_events, serving UTC stamps."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.asked: tuple[Any, ...] | None = None

    def economic_events(self, country, start, end, limit=1000):
        self.asked = (country, start, end, limit)
        return self.rows, None


def claim_economic_events_are_converted_not_relabelled(failures: list[str]) -> None:
    """The macro line is in ET because it was converted, not because it says ET.

    The vendor stamps this feed UTC with no offset on the string, and the parse
    was fromisoformat(raw).replace(tzinfo=ET), which keeps the digits and
    changes their meaning. Every archived packet carries the shift: 2026-08-19
    has FOMC Minutes at 18:00 ET against a real 14:00 release, and Initial
    Jobless Claims at 12:30 against a real 08:30. A premarket briefing that
    moves the morning's only macro print from an hour before the open to after
    lunch has inverted the one thing that section is for.
    """
    from morning import scan

    today = ettime.today_et()
    # 12:30 UTC is 08:30 ET in daylight time, which is when this actually prints.
    api = _EventsApi([{
        "country": "US", "type": "Initial Jobless Claims",
        "date": f"{today.isoformat()} 12:30:00",
        "estimate": 1.0, "previous": 2.0, "actual": None, "period": "weekly",
    }])
    packet = scan.Packet()
    result = scan.economic_events(api, packet)
    events = result.get("events") or []
    if not events:
        failures.append("the stubbed high importance event was dropped entirely")
        return

    stamped = str(events[0].get("time_et") or "")
    hhmm = stamped[11:16]
    offset = ettime.stamp(ettime.at(today, 0, 0))[19:]
    expected = "08:30" if offset == "-04:00" else "07:30"
    if hhmm != expected:
        failures.append(
            f"a 12:30 UTC event was published as {hhmm} ET, expected {expected}. "
            "The feed is UTC and must be converted with ettime.to_et, never "
            "relabelled with replace(tzinfo=ET).")
    if not result.get("time_source"):
        failures.append("the packet does not record that these times are a "
                        "conversion, so a reader cannot tell them from the "
                        "pre 2026-08-20 packets that are four hours out")
    if api.asked and api.asked[2] <= today + dt.timedelta(
            days=int(scan._CRIT.integer("scan", "economic_days_ahead"))):
        failures.append("the fetch window was not widened past the ET window, so "
                        "an event late in the ET evening carries the next UTC "
                        "date and is never seen")
    print(f"  macro clock  a 12:30 UTC print publishes as {hhmm} ET, and the "
          "packet says it was converted")


# ------------------------------------------------- the rerun that knew less

def claim_a_thinner_rerun_stands_down(failures: list[str]) -> None:
    """A rerun that knows less does not replace what knows more.

    The guard asserted exactly this and tested only one way of being thin, a
    quota degraded preflight. The way the schedule actually produces is the
    clock: [scan] rvol_cutoff_snap_minutes snaps the RVOL cutoff to run_time
    only within ten minutes of 08:45, while [picks] live_window runs 07:00 to
    09:30 and [monitor] rerun_chain_until lets the watchdog rerun a broken
    chain until 09:30. A 09:25 rerun therefore finds no warmed baseline row,
    nulls every pm_rvol, flips day_eligible false for every candidate, and
    upserts that over the 08:45 rows as source 'live'.
    """
    from morning import scan

    with conftest_activate() as _sandbox:
        day = ettime.today_str()
        full = {
            "session_date": day,
            "quota_preflight": {"degraded": False},
            "candidates": [
                {"symbol": f"AAA{n}.US", "price": 10.0, "pm_rvol": 3.0, "score": 7.0}
                for n in range(12)
            ],
        }
        scan.write_packet(full)

        # The 09:25 rerun: same names, same prices, no RVOL, nothing scored.
        thin = {
            "session_date": day,
            "quota_preflight": {"degraded": False},
            "candidates": [
                {"symbol": f"AAA{n}.US", "price": 10.0, "pm_rvol": None, "score": None}
                for n in range(12)
            ],
        }
        if not scan.thin_rerun_stands_down(thin):
            failures.append(
                "a rerun with no pm_rvol and nothing scored was allowed to "
                "replace a packet that had both, which is what a 09:25 watchdog "
                "rerun produces")
        side = config.run_dir(day) / "packet_degraded.json"
        if not side.is_file():
            failures.append("the thinner rerun was refused but not preserved "
                            "beside the packet it did not replace")
        on_disk = json.loads((config.run_dir(day) / "packet.json").read_text(encoding="utf-8"))
        if on_disk["candidates"][0]["pm_rvol"] != 3.0:
            failures.append("the fuller packet was overwritten anyway")

        # An equal rerun is not a thinner one, or a legitimate 08:50 rerun of a
        # broken chain could never write.
        if scan.thin_rerun_stands_down(dict(full)):
            failures.append("a rerun carrying identical evidence was refused, "
                            "which would break the watchdog's ordinary rerun")

        # And one that gains on any axis is a better morning, not a degraded copy.
        wider = json.loads(json.dumps(full))
        wider["candidates"].append(
            {"symbol": "ZZZ.US", "price": 5.0, "pm_rvol": 1.0, "score": 4.0})
        if scan.thin_rerun_stands_down(wider):
            failures.append("a rerun that found MORE was refused")
    print("  thin rerun   a rerun with no RVOL stands down, an equal one and a "
          "wider one do not")


# ------------------------------------------------------ the quiet morning

def claim_an_empty_packet_is_not_a_failed_step(failures: list[str]) -> None:
    """A morning with no candidates is quiet, not broken.

    print_table returned 1 on an empty candidate list against OK_CODES (0,), so
    a thin premarket day recorded the verify step as failed, the watchdog
    counted it as a problem, and the next morning's disclaimer named a
    scheduled step that had done nothing wrong. A false alarm on a quiet
    morning is how a real alarm stops being read.
    """
    from morning import verify_morning

    with conftest_activate() as _sandbox:
        day = ettime.today_str()
        path = config.run_dir(day) / "packet.json"
        path.write_text(json.dumps({"session_date": day, "candidates": []}),
                        encoding="utf-8")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = verify_morning.print_table(path)
        if code != 0:
            failures.append(f"an empty packet returned {code}; a quiet morning "
                            "must not record the verify step as failed")
        if "no candidates" not in printed.getvalue():
            failures.append("the empty case said nothing about why it tabled "
                            f"nothing: {printed.getvalue().strip()[:120]!r}")
    print("  quiet gate   a zero candidate packet exits 0 and says why")


# ------------------------------------------------------- the second email

def claim_delivery_happens_once(failures: list[str]) -> None:
    """The chain's rerun does not send the morning twice.

    The watchdog reruns the WHOLE chain on the stated reasoning that it is
    idempotent, and the chain's finish marker is written by the archive step
    after deliver. So an archive that fails leaves a chain that has already
    emailed looking unfinished, and the 09:25 pass relaunches it.
    """
    from morning import deliver, verify_morning

    with conftest_activate() as _sandbox:
        day = ettime.today_str()
        html = config.run_dir(day) / "report.html"
        html.write_text("<p>morning</p>", encoding="utf-8")
        verify_morning.UNVERIFIED_MARKER.unlink(missing_ok=True)

        record = deliver.delivery_record_path(html)
        record.write_text(json.dumps({
            "sent_at": ettime.stamp(ettime.now_et()),
            "recipients": ["someone@example.invalid"],
            "message_id": "re_stub",
        }), encoding="utf-8")

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = deliver.deliver(html)
        text = printed.getvalue()
        if code != 0:
            failures.append(f"a second delivery attempt returned {code}, expected 0")
        if "already emailed" not in text:
            failures.append(f"a session with a delivery record was not recognised "
                            f"as already sent: {text.strip()[:160]!r}")

        # Without the record, the run proceeds far enough to reach the key check,
        # which is what proves the guard is the record and not something else.
        record.unlink()
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            deliver.deliver(html)
        if "already emailed" in printed.getvalue():
            failures.append("delivery was refused with no record on disk")

        # An unreadable record must not be able to suppress a morning's email.
        record.write_text("{ not json", encoding="utf-8")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            deliver.deliver(html)
        if "already emailed" in printed.getvalue():
            failures.append("a corrupt delivery record suppressed the email; a "
                            "second copy is a cheaper mistake than no copy")
    print("  send once    a delivered session is not re-sent, and a corrupt "
          "record cannot suppress one")


# ---------------------------------------------------------- the collector

def claim_replay_is_counted_once(failures: list[str]) -> None:
    """A resubscription does not multiply the replay measurement.

    The vendor replays a last trade per symbol on every subscription and this
    collector resubscribes on every reconnect, so the same replayed print was
    appended once per connection. replay_volume in the packet is the number a
    human reads to judge how much replay a session carried, which is the whole
    reason the tag exists, so inflating it by the reconnect count defeats the
    measurement it was introduced to make.
    """
    from collect.collect_premarket import BarBuilder, read_bars_file

    with tempfile.TemporaryDirectory(prefix="pmd-replay-") as raw:
        path = pathlib.Path(raw) / "bars.jsonl"
        base = 1_787_200_000 // 60 * 60
        builder = BarBuilder(path, source="ws", window=(base, base + 3600))
        for _ in range(3):  # three subscriptions, one replayed print
            builder.add_trade("AAA.US", 10.0, 100.0, base - 7200, False, "extended")
            builder.flush(base + 5000, force=True)
        _bars, stats = read_bars_file(path)
        if stats["replay_rows"] != 1 or stats["replay_volume"] != 100.0:
            failures.append(
                f"one replayed print across three subscriptions read as "
                f"{stats['replay_rows']} row(s) and {stats['replay_volume']:.0f} "
                "shares, expected 1 and 100")
        if builder.duplicate_replay_skipped != 2:
            failures.append(f"the two repeats were not counted as skipped "
                            f"({builder.duplicate_replay_skipped})")
    print("  replay once  one replayed print across three subscriptions counts once")


def claim_a_failed_write_holds_its_minutes(failures: list[str]) -> None:
    """Minutes that could not be appended are retried, not lost twice over.

    flush popped bars from open_bars and added their keys to `written` while
    building the batch, and only then opened the file. An OSError there lost
    those minutes twice: they never reached disk, and `written` then made
    add_trade refuse every later trade for them as a late print, so they could
    not be rebuilt from the tape still arriving. The OSError also reached
    run_websocket's socket handler, which reported a disk fault as a lost
    connection and resubscribed into a 50 slot pool known to refuse.
    """
    from collect.collect_premarket import BarBuilder

    with tempfile.TemporaryDirectory(prefix="pmd-write-") as raw:
        path = pathlib.Path(raw) / "nested" / "bars.jsonl"
        base = 1_787_200_000 // 60 * 60
        builder = BarBuilder(path, source="ws", window=(base, base + 3600))
        builder.add_trade("BBB.US", 10.0, 500.0, base + 10, False, "extended")

        real_mkdir = pathlib.Path.mkdir

        def explode(self, **kwargs):
            raise OSError("simulated disk full")

        pathlib.Path.mkdir = explode
        try:
            written = builder.flush(base + 5000, force=True)
        except OSError:
            failures.append("a write fault propagated out of flush; run_websocket "
                            "would report it as a lost connection and resubscribe")
            written = -1
        finally:
            pathlib.Path.mkdir = real_mkdir

        if written == 0:
            if not builder.open_bars:
                failures.append("the minute was not held for retry after the "
                                "write failed")
            if builder.written:
                failures.append("the minute was marked written despite never "
                                "reaching disk, so every later trade for it "
                                "would be refused as a late print")
            if builder.write_failures != 1:
                failures.append("the write fault was not counted")

        retried = builder.flush(base + 5000, force=True)
        if retried != 1 or builder.rows_written != 1 or not path.is_file():
            failures.append(f"the held minute did not land on the retry "
                            f"(lines {retried}, rows_written {builder.rows_written})")
    print("  write fault  a refused append holds its minutes and the next "
          "settle writes them")


# ------------------------------------------------------------- the outcomes

def claim_outcomes_refuse_a_pick_the_calendar_cannot_date(failures: list[str]) -> None:
    """A pick older than the session window is skipped, not measured wrongly.

    _session_calendar fetches 40 calendar days, about 27 sessions.
    _sessions_after took `[d for d in calendar if d > date][:count]` with no
    check that date was inside it, so for an older pick every entry qualified
    and the first one returned was the OLDEST session in the window rather than
    the session after the pick. The row was then filled with excursions
    measured against a tape weeks removed from the levels they are computed
    from, silently, into the table CRITERIA says its thresholds will one day be
    recalibrated against.
    """
    from night.fill_outcomes import CalendarTooShort, _sessions_after

    calendar = ["2026-07-10", "2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16"]
    if _sessions_after(calendar, "2026-07-13", 2) != ["2026-07-14", "2026-07-15"]:
        failures.append("a pick inside the window stopped resolving correctly")
    try:
        answer = _sessions_after(calendar, "2026-06-02", 2)
    except CalendarTooShort:
        pass
    else:
        failures.append(f"a pick dated before the calendar returned {answer} "
                        "instead of refusing")
    try:
        _sessions_after([], "2026-07-13", 2)
    except CalendarTooShort:
        pass
    else:
        failures.append("an empty calendar did not refuse")
    print("  outcomes cal a pick the calendar cannot date is refused, not guessed")


# ------------------------------------------------------------- the universe

def claim_a_missing_exchange_refuses_the_build(failures: list[str]) -> None:
    """Half the exchanges is half the market, and every later gate passes it.

    The bulk sweep, the market cap sweep and the funnel are all computed from
    this index, so a build missing NASDAQ comes out internally consistent: zero
    unswept, a count inside expected_count_range, admissible. Only the count
    fraction floor stands between it and the disk and it is 0.5, while the real
    file splits about 1,519 NYSE to 1,235 NASDAQ, so losing NASDAQ clears the
    floor by two points and losing NYSE does not. Which half the vendor dropped
    decided whether the gate spoke, and max_age_days is 10, so the monitor's
    age keyed relaunch never fires on a fresh bad file.
    """
    from selection import universe

    class _HalfIndex:
        def exchange_symbol_list(self, exchange):
            if exchange.upper().startswith("NASDAQ"):
                return None, "HTTP 503 from the vendor"
            return [{"Code": "AAA", "Type": "Common Stock", "Exchange": exchange}], None

    notes: list[str] = []
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            universe._common_stock_index(_HalfIndex(), notes)
    except universe.PartialBuildError as exc:
        if "NASDAQ" not in str(exc):
            failures.append(f"the refusal does not name the exchange that failed: {exc}")
    else:
        failures.append("a build with one exchange list missing was allowed to "
                        "continue, and nothing downstream can tell that from a "
                        "real universe")

    class _WholeIndex:
        def exchange_symbol_list(self, exchange):
            return [{"Code": "AAA", "Type": "Common Stock", "Exchange": exchange}], None

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            universe._common_stock_index(_WholeIndex(), [])
    except universe.PartialBuildError as exc:
        failures.append(f"a build with every exchange answering was refused: {exc}")
    print("  universe     a build missing an exchange refuses rather than "
          "replacing last week's")


def claim_the_watchlist_is_written_atomically(failures: list[str]) -> None:
    """An interrupted discover leaves yesterday's watchlist, not a truncated one.

    A plain write_text truncates the existing 500 KB file before writing a
    byte. load_watchlist reads the result as missing, and at 07:20 the
    collector exits 1 with no premarket tape for any name, which cannot be
    fetched afterwards. Yesterday's file WOULD have served: the collector
    applies no freshness test and subscribed_symbols is written to keep an
    older file readable. The watchdog cannot repair it either, because it
    refuses to rerun discover once the collector window has opened.
    """
    from selection import discover, universe

    with conftest_activate() as _sandbox:
        good = {"generated_at": "2026-08-19T07:15:00-04:00",
                "symbols": [{"symbol": "OLD.US", "subscribed": True}]}
        config.WATCHLIST_PATH.write_text(json.dumps(good), encoding="utf-8")

        # A payload json.dumps cannot serialise fails inside the temporary file,
        # which is the same place an interruption would.
        try:
            universe.write_atomically({"symbols": {1, 2, 3}}, config.WATCHLIST_PATH)
        except TypeError:
            pass
        else:
            failures.append("an unserialisable payload did not raise")

        survived = discover.load_watchlist()
        if survived.get("missing"):
            failures.append("a failed write destroyed the previous watchlist, so "
                            "the collector would have had nothing to subscribe to")
        elif discover.subscribed_symbols(survived) != ["OLD.US"]:
            failures.append(f"the previous watchlist did not survive intact: {survived}")

        universe.write_atomically({"generated_at": "now", "symbols": []},
                                  config.WATCHLIST_PATH)
        if discover.load_watchlist().get("symbols") != []:
            failures.append("the successful write did not land")
    print("  watchlist    a failed write leaves the previous watchlist readable")


# ------------------------------------------------------------- the gap stats

def claim_the_stdev_window_is_its_own_name(failures: list[str]) -> None:
    """return_stdev_20d is twenty sessions, and a hole costs one gap not two.

    Two findings in one function. The stdev was taken over every return in the
    250 session list, so the column named for twenty sessions held a trailing
    year; min_sessions_for_move_sigma was doing duty as the window and it is a
    floor. And a bar missing an open was dropped whole, which removed its CLOSE
    from the chain, so the session after a hole had its gap measured against a
    close two sessions back: a two session move stored as a one session gap, in
    the very column 42 subscription slots are ordered by.
    """
    from selection import gap_stats

    if gap_stats.RETURN_STDEV_SESSIONS >= gap_stats.LOOKBACK_SESSIONS:
        failures.append("the stdev window is not shorter than the lookback, so "
                        "it is still a trailing year by another name")

    # A year of dead flat closes with one violent month at the start. A twenty
    # session window must not see the violence; a 250 session one cannot miss it.
    bars = []
    day = dt.date(2025, 1, 1)
    for n in range(260):
        close = 100.0 + (10.0 if n < 30 and n % 2 else 0.0)
        bars.append({"date": (day + dt.timedelta(days=n)).isoformat(),
                     "open": close, "high": close, "low": close, "close": close})
    row = gap_stats.compute(bars, dt.date(2025, 1, 1) + dt.timedelta(days=259))
    if row.get("return_stdev_20d") not in (0.0, None):
        failures.append(
            f"a name flat for its last 230 sessions reported a return stdev of "
            f"{row['return_stdev_20d']}, so the window is still the whole history")

    # A hole in the middle: one bar with no open. The gap after it must not be
    # measured across two sessions.
    holed = []
    price = 100.0
    for n in range(120):
        price += 1.0
        bar = {"date": (day + dt.timedelta(days=n)).isoformat(),
               "open": price, "high": price, "low": price, "close": price}
        if n == 60:
            bar["open"] = None
        holed.append(bar)
    row = gap_stats.compute(holed, dt.date(2025, 1, 1) + dt.timedelta(days=119))
    # Every real gap here is exactly 0 percent, because each open equals the
    # prior close. A broken chain manufactures one of about +1 percent.
    if (row.get("median_abs_gap_pct") or 0) > 0.001:
        failures.append(
            f"a single bar with no open manufactured a gap "
            f"(median_abs_gap_pct {row['median_abs_gap_pct']}), so the close "
            "chain is still being broken by the drop")
    print("  gap stats    the stdev is a twenty session window and a hole costs "
          "one gap, not the next one")


# ---------------------------------------------------------------- the ops

def claim_the_watchdog_survives_a_hung_schtasks(failures: list[str]) -> None:
    """A hung or missing schtasks reads as a task that could not be queried.

    query_task's return shape shows it means to absorb a failure and it did so
    only for a non-zero exit. TimeoutExpired and OSError propagated through
    _collector_alive and check_all and killed the whole pass, so the watchdog
    did none of its other work either: no collector restart, no chain rerun, no
    flag backlog line, just a traceback. The next chance was thirty minutes
    later. A watchdog that dies when the machine is unwell is absent exactly
    when it is needed.
    """
    import subprocess

    from ops import monitor_jobs

    real = monitor_jobs.subprocess.run
    for fault in (subprocess.TimeoutExpired(cmd="schtasks", timeout=60),
                  FileNotFoundError("schtasks is not on PATH")):
        monitor_jobs.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(fault)
        try:
            answer = monitor_jobs.query_task("\\PremarketDesk\\collector")
        except BaseException as exc:  # noqa: BLE001
            failures.append(f"{type(fault).__name__} propagated out of query_task "
                            f"as {type(exc).__name__}, killing the whole pass")
            continue
        finally:
            monitor_jobs.subprocess.run = real
        if answer.get("exists") is not False or not answer.get("error"):
            failures.append(f"{type(fault).__name__} produced {answer}, expected "
                            "exists False with the reason recorded")
    if 1 not in monitor_jobs.OK_CODES:
        failures.append("the watchdog still records a pass that FOUND something "
                        "as a failed step, so a week old unjudged flag makes the "
                        "morning report declare the watchdog itself dead")
    print("  watchdog     a hung or missing schtasks is absorbed, and finding a "
          "problem is not a failed step")


def claim_the_baseline_counts_what_it_warmed(failures: list[str]) -> None:
    """The warm step reports warms, not the length of its request.

    main discarded warm()'s result and recorded len(tickers), so a run in which
    every ticker failed recorded "tickers warmed 42" and exit 0. That
    contradicts the stand down branch beside it, whose whole argument is that
    zero warmed is worth reading, which it can only be if it counts warms. On
    the morning it mattered the scan would publish a null pm_rvol for the
    entire watchlist and the trail would say the baseline job did its job.
    """
    import inspect

    from collect import baseline

    source = inspect.getsource(baseline.main)
    if 'produced("tickers warmed", len(tickers))' in source:
        failures.append("baseline still records the length of its request as the "
                        "number it warmed")
    if "result = warm(" not in source:
        failures.append("baseline still discards warm()'s counts")
    if "job_status.failed" not in source:
        failures.append("a warm in which every ticker failed still records as a "
                        "clean run")
    print("  baseline     the trail records warms, not requests")


# --------------------------------------------------------------- the analyst

def claim_vendor_text_cannot_break_a_table(failures: list[str]) -> None:
    """A pipe in a headline does not eat the rest of the headline.

    python-markdown's tables extension does not error on a row with more cells
    than its header; it discards the extras. So a headline reading "Q2 beat |
    guidance raised" reached the delivered HTML as "Q2 beat" and the rest was
    gone with nothing said. Feeds put pipes in headlines constantly, and this
    is the FALLBACK report, which is what a reader gets on the mornings the
    narrative already failed.
    """
    from morning import analyst

    escaped = analyst._cell("Q2 beat | revenue up 12% | guidance raised")
    if "|" in escaped.replace("\\|", ""):
        failures.append(f"an unescaped pipe survived into a table cell: {escaped!r}")
    if "guidance raised" not in escaped:
        failures.append("the escape dropped part of the headline")
    if "\n" in analyst._cell("two\nlines"):
        failures.append("a newline survived into a table cell")
    print("  table cells  a pipe in vendor text is escaped, not truncated")


def claim_the_quantifier_guard_reads_headings(failures: list[str]) -> None:
    """A set-wide claim in a heading is flagged like one in a sentence.

    Headings were skipped alongside table rows and the docstring only ever
    accounted for the table skip. A heading is not a table row: it is prose in
    the most prominent position on the page, and it is exactly where a model
    summarising an empty screen puts a claim about the whole candidate set. The
    skip also meant the flag rate the warn mode is being measured on
    undercounted by however many flags lived in headings.
    """
    from morning import analyst

    if not analyst.quantifier_violations("## No candidates cleared the day screen"):
        failures.append("a quantifier over the candidate set in a heading was "
                        "not flagged")
    if analyst.quantifier_violations("| none | | | | | | | |"):
        failures.append("a table row was flagged, which fails every empty morning")
    if not analyst.quantifier_violations("Every candidate failed the screen."):
        failures.append("ordinary prose stopped being scanned")
    print("  guard scope  a heading is scanned, a table row is not")


def claim_no_comment_describes_a_helper_that_does_not_exist(failures: list[str]) -> None:
    """The containment comment describes the filter the code actually has.

    It claimed single character tokens were "additionally required to be real
    listings, which _single_letter_listings supplies from universe.json" and
    were "dropped before" becoming claims. No such function exists or ever did,
    and one letter tokens are treated exactly like six letter ones. This
    project generates its architecture pages from comments like this one by
    hand, and coverage['claims_checked'] means something different under the
    two readings.
    """
    import inspect

    from morning import analyst

    lines = inspect.getsource(analyst).splitlines()
    if hasattr(analyst, "_single_letter_listings"):
        print("  comments     the helper now exists, so the comment is true again")
        return
    for number, line in enumerate(lines):
        if "_single_letter_listings" not in line:
            continue
        # A mention is allowed only inside a correction. The convention this
        # project uses everywhere is to quote the wrong sentence and mark it,
        # so the guard has to permit the quote and refuse a fresh assertion.
        window = " ".join(lines[max(0, number - 8):number + 1])
        if "[corrected" not in window:
            failures.append(
                f"analyst.py line {number + 1} names _single_letter_listings "
                "outside a correction marker, and no such function exists")
    print("  comments     the phantom helper is named only inside its correction")


# ------------------------------------------- the 2026-08-20 report audit

def claim_the_volume_check_reaches_the_packet(failures: list[str]) -> None:
    """The measured collector shortfall is read by the morning and stated.

    verify_against_intraday is the definitive measure of what the socket
    misses, the nightly writes it to runs/<date>/verify_intraday.json, and
    until 2026-08-20 nothing under src/morning read that file. So the
    2026-08-20 report told its reader premarket RVOL was a lower bound and
    named only the window shortfall, which is arithmetic and small, while the
    feed shortfall measured 90.0 percent across 73 symbols the night before and
    reached nobody. The numerator comes from the collector and the denominator
    from the vendor, so that disagreement is IN every ratio the report prints.

    Three states are proved, because the wrong one is silence: a fresh check is
    read and quoted, a stale one is called stale rather than dropped, and no
    check at all is itself said out loud. An unmeasured feed is not a clean one.
    """
    from collect import collect_premarket
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    with conftest_activate():
        # activate() copies the real runs/ in, and the real tree carries
        # written checks. Cleared first so the three states below are the
        # fixture's rather than the machine's.
        for existing in config.RUNS_DIR.glob("*/verify_intraday.json"):
            existing.unlink()

        # No check written at all.
        sink = Sink()
        if scan.volume_check("2026-08-20", sink) is not None:
            failures.append("a volume check was returned when none is on disk")
        if not any("never been written" in g for g in sink.gaps):
            failures.append(
                "no check on disk and the packet says nothing: "
                f"{sink.gaps}")

        def write(day: str, payload: dict) -> None:
            target = config.run_dir(day)
            target.mkdir(parents=True, exist_ok=True)
            (target / "verify_intraday.json").write_text(
                json.dumps(payload), encoding="utf-8")

        fresh = {"day": "2026-08-19", "compared": 73, "within_one_percent": 0,
                 "median_abs_pct": 90.0, "unavailable": 0}
        write("2026-08-19", fresh)

        read = collect_premarket.latest_volume_check("2026-08-20")
        if not read or read.get("median_abs_pct") != 90.0:
            failures.append(f"the written check was not read back: {read}")
        elif read["age_days"] != 1 or read["stale"]:
            failures.append(f"a one day old check read as {read['age_days']} "
                            f"days and stale={read['stale']}")

        sink = Sink()
        returned = scan.volume_check("2026-08-20", sink)
        if not returned or returned.get("compared") != 73:
            failures.append(f"volume_check did not return the summary: {returned}")
        stated = [g for g in sink.gaps if "90.0 percent" in g and "73" in g]
        if not stated:
            failures.append(
                "the measured disagreement is not in gaps_to_fill, so the "
                f"disclaimer cannot carry it: {sink.gaps}")
        elif "LARGER than the window" not in stated[0]:
            failures.append(
                "the gap does not say the feed shortfall is the bigger of the "
                f"two, which is the whole correction: {stated[0]}")

        # A check older than the CRITERIA limit is named as stale, not dropped.
        far = ettime.parse_date("2026-08-19") + dt.timedelta(days=40)
        sink = Sink()
        stale = scan.volume_check(far.isoformat(), sink)
        if not stale or not stale["stale"]:
            failures.append(f"a 40 day old check did not read as stale: {stale}")
        if not any("days old" in g and "unmeasured" in g for g in sink.gaps):
            failures.append(f"a stale check was not called stale: {sink.gaps}")

    print("  volume check the measured collector shortfall is read, quoted, and "
          "called stale or absent when it is")


def claim_a_trap_is_the_balance_not_the_worst_headline(failures: list[str]) -> None:
    """One mis-scored headline inside a positive set cannot carry a trap call.

    Until 2026-08-20 REPORT_TEMPLATE.md asked the MODEL whether a gap up was
    contradicted by its news, and the model answered with the worst single
    headline. That morning it published MSTR as a trap on "Bitcoin tops $71K as
    crypto rally gains momentum", which the vendor scored -0.914 against that
    same name's +0.963 and +0.833, and FUTU on a neutral earnings listing at
    -0.422 against +0.836 and +0.691. Two vendor scoring errors reached a
    reader as statements about the market, and neither the containment checker
    nor the quantifier guard could see it: the tickers were real and the
    polarity was quoted correctly.

    The real MSTR row is the fixture here, on purpose. A claim written from
    invented numbers proves the rule; this one proves the case.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    def headline(polarity):
        return {"title": "t", "sentiment": None if polarity is None
                else {"polarity": polarity}}

    cases = [
        # The 2026-08-20 MSTR row, verbatim polarities.
        ("MSTR.US", 9.0647, [0.963, -0.914, 0.833], False, "one negative in three"),
        # The 2026-08-20 FUTU row.
        ("FUTU.US", 9.4772, [0.691, 0.836, -0.422], False, "one negative in three"),
        # Genuinely negative coverage still trips it.
        ("BAD.US", 9.0, [-0.8, -0.6, 0.9], True, "two negative in three"),
        # A gap DOWN is not the question a trap asks.
        ("DOWN.US", -9.0, [-0.8, -0.6], None, "gap down"),
        # One scored headline IS the worst single headline. Refused.
        ("THIN.US", 9.0, [-0.9], None, "below the balance minimum"),
        # Unscored headlines do not count toward the balance.
        ("UNSC.US", 9.0, [None, None, -0.9], None, "one scored of three"),
    ]
    candidates = [
        {"symbol": symbol, "gap_pct": gap, "catalyst_found": True,
         "headlines": [headline(v) for v in polarities]}
        for symbol, gap, polarities, _want, _why in cases
    ]
    sink = Sink()
    scan.attach_traps(candidates, sink)

    for candidate, (symbol, _gap, _pol, want, why) in zip(candidates, cases):
        got = candidate.get("trap")
        if got is not want:
            failures.append(
                f"{symbol} ({why}) came back trap={got!r}, expected {want!r}: "
                f"{candidate.get('trap_why')}")
        if not candidate.get("trap_why"):
            failures.append(f"{symbol} carries a trap verdict with no reason")
        basis = candidate.get("trap_basis") or {}
        for field in ("negative", "positive", "headlines_scored", "rule"):
            if field not in basis:
                failures.append(f"{symbol} trap_basis carries no {field}: {basis}")

    # A failed news call is unknown, never a clean False.
    unknown = [{"symbol": "ERR.US", "gap_pct": 9.0, "catalyst_found": None,
                "headlines": []}]
    scan.attach_traps(unknown, Sink())
    if unknown[0].get("trap") is not None:
        failures.append("a failed news call produced a trap verdict rather than "
                        f"unknown: {unknown[0].get('trap')}")

    named = [g for g in sink.gaps if "BAD.US" in g]
    if not named:
        failures.append(f"the flagged trap is not in gaps_to_fill: {sink.gaps}")
    elif "MSTR.US" in named[0] or "FUTU.US" in named[0]:
        failures.append(f"a cleared name was flagged as a trap: {named[0]}")

    # The template must not ask for the judgment it no longer makes.
    template = (config.PROJECT_ROOT / "doc" / "REPORT_TEMPLATE.md").read_text(
        encoding="utf-8")
    if "sentiment is negative is a trap" in template:
        failures.append(
            "REPORT_TEMPLATE.md still asks the model to judge a trap from "
            "headline sentiment, which is the instruction that produced the "
            "2026-08-20 MSTR and FUTU calls")
    if "trap_why" not in template:
        failures.append("REPORT_TEMPLATE.md does not tell the report to quote "
                        "the packet's trap_why")
    print("  trap balance a mis-scored headline inside a positive set is not a "
          "trap, and the template no longer asks the model to decide")


def claim_the_day_screen_names_what_rvol_alone_blocked(failures: list[str]) -> None:
    """Which names an understating numerator cost, counted rather than narrated.

    The companion to the volume check, and the reason it is worth carrying. On
    2026-08-20 seven of twelve candidates cleared price, gap, market cap and
    the prior session high and failed on premarket RVOL by itself, against a
    numerator the nightly had already measured at roughly a tenth of the
    vendor's for the same minutes. The report published "the day screen
    produced nothing today" as an observation about the market.

    Counted here rather than left to the model for the reason screen_tally
    argues: it has exactly one right answer, and the model was getting counts
    wrong in prose.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    candidates = [
        {"symbol": "ONLY.US", "day_failed_conditions": ["premarket_rvol"]},
        {"symbol": "ALSO.US", "day_failed_conditions": ["premarket_rvol"]},
        {"symbol": "BOTH.US", "day_failed_conditions": ["premarket_rvol",
                                                        "market_cap"]},
        {"symbol": "OTHER.US", "day_failed_conditions": ["market_cap"]},
        {"symbol": "CLEAN.US", "day_failed_conditions": []},
    ]
    sink = Sink()
    blocked = scan.rvol_only_day_failures(candidates, sink)
    if blocked != ["ONLY.US", "ALSO.US"]:
        failures.append(f"rvol-only blocking named {blocked}, expected the two "
                        "that failed on nothing else")
    if not sink.gaps or "ONLY.US" not in sink.gaps[0]:
        failures.append(f"the blocked names are not in gaps_to_fill: {sink.gaps}")
    elif "instrument reading" not in sink.gaps[0]:
        failures.append("the gap does not tell the reader an empty day list may "
                        f"be the instrument: {sink.gaps[0]}")

    # Silent when nothing was blocked on RVOL alone, so the list stays readable.
    quiet = Sink()
    if scan.rvol_only_day_failures(
            [{"symbol": "X.US", "day_failed_conditions": ["market_cap"]}], quiet):
        failures.append("a name failing on market cap was called rvol blocked")
    if quiet.gaps:
        failures.append(f"a morning with nothing blocked still gapped: {quiet.gaps}")
    print("  rvol blocked the names the day screen lost to RVOL alone are counted "
          "and named, and a quiet morning stays silent")


def claim_a_truncated_name_is_not_a_rejected_one(failures: list[str]) -> None:
    """The rank cap names what it cut, so the two counts stop being a riddle.

    "18 cleared the price and gap floors and 12 were kept" is arithmetic a
    reader can do and an explanation they cannot. The six that vanished on
    2026-08-20 were cut by [Scan] candidate_count, not rejected by a screen,
    and candidate_provenance.ranking recorded kept: 12 without recording that a
    cap did it.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    def rows(count: int) -> list[dict[str, Any]]:
        # Descending gaps, every one clear of the discovery floors, so the ONLY
        # thing that removes a name here is the cap. A fixture where some fell
        # to the floor would prove nothing about truncation.
        return [{"symbol": f"T{i:02d}.US", "price": 50.0,
                 "pool_prior_close": 50.0 / (1 + (count - i + 6) / 100.0)}
                for i in range(count)]

    sink = Sink()
    kept, stats = scan.rank_by_measured_gap(rows(8), sink, 3)
    if stats["kept"] != 3 or stats["cleared_floors"] != 8:
        failures.append(f"the cap did not keep 3 of 8: {stats}")
    if stats["capped_out"] != 5:
        failures.append(f"capped_out counted {stats['capped_out']}, expected 5")
    cut = [row["symbol"] for row in stats["capped_out_symbols"]]
    if len(cut) != 5 or set(cut) & {c["symbol"] for c in kept}:
        failures.append(f"capped_out_symbols overlaps what was kept: {cut}")
    if stats.get("cap") != 3 or "candidate_count" not in (stats.get("cap_source") or ""):
        failures.append(f"the cap and its source are not recorded: {stats}")
    named = [g for g in sink.gaps if "RANK CAP" in g]
    if not named:
        failures.append(f"the cap said nothing in gaps_to_fill: {sink.gaps}")
    elif not all(symbol in named[0] for symbol in cut):
        failures.append(f"the gap does not name what was cut: {named[0]}")

    # Nothing cut, nothing said. A gaps list that always speaks is not read.
    quiet = Sink()
    scan.rank_by_measured_gap(rows(3), quiet, 12)
    if any("RANK CAP" in g for g in quiet.gaps):
        failures.append(f"a run under the cap still reported one: {quiet.gaps}")
    print("  rank cap    the names a cap truncated are counted and named, and a "
          "short morning stays silent")


def claim_the_bucket_roll_is_complete_and_signed(failures: list[str]) -> None:
    """Every scored name is in the roll, and each carries its direction.

    Two 2026-08-20 sentences, one cause. "MSTR and WMT green at 7" omitted SCSC,
    which also scored 7.0 green, because the model was enumerating a set the
    packet already knew. And "the strongest scored names, both green at 8, are
    AAP and FUTU" ranked by a score that has no sign, on a morning AAP was down
    21.75 percent.
    """
    from morning import scan

    candidates = [
        {"symbol": "AAP.US", "score": 8.0, "conviction": "green", "gap_pct": -21.7515},
        {"symbol": "FUTU.US", "score": 8.0, "conviction": "green", "gap_pct": 9.4772},
        {"symbol": "SCSC.US", "score": 7.0, "conviction": "green", "gap_pct": 16.3361},
        {"symbol": "MSTR.US", "score": 7.0, "conviction": "green", "gap_pct": 9.0647},
        {"symbol": "WMT.US", "score": 7.0, "conviction": "green", "gap_pct": -7.2616},
        {"symbol": "ASST.US", "score": 2.0, "conviction": "red", "gap_pct": 6.5173},
        {"symbol": "DARK.US", "score": None, "conviction": None, "gap_pct": 4.0},
    ]
    roll = scan.score_roll(candidates)

    scored = {c["symbol"] for c in candidates if c["score"] is not None}
    rolled = {row["symbol"] for rows in roll["by_bucket"].values() for row in rows}
    if rolled != scored:
        failures.append(f"the roll is not the scored set: {sorted(rolled ^ scored)}")
    if roll["unscored"] != ["DARK.US"]:
        failures.append(f"the unscored name is not held apart: {roll['unscored']}")

    # The specific omission. SCSC scored 7.0 green and was left out of the
    # 2026-08-20 sentence; it cannot be left out of a roll built from the set.
    if "SCSC.US" not in roll["summary"]:
        failures.append(f"SCSC is missing from the roll summary: {roll['summary']}")
    for symbol in ("AAP.US", "FUTU.US", "MSTR.US", "WMT.US"):
        if symbol not in roll["summary"]:
            failures.append(f"{symbol} is missing from the roll summary")

    if not roll.get("score_is_direction_blind"):
        failures.append("the roll does not say the score is unsigned")
    if "down 21.75 percent" not in roll["summary"]:
        failures.append("AAP's direction is not carried beside its score: "
                        f"{roll['summary']}")
    if "up 9.48 percent" not in roll["summary"]:
        failures.append("FUTU's direction is not carried beside its score")

    green = [row["symbol"] for row in roll["by_bucket"]["green"]]
    if green[:2] != ["AAP.US", "FUTU.US"]:
        failures.append(f"the bucket is not ordered strongest first: {green}")

    template = (config.PROJECT_ROOT / "doc" / "REPORT_TEMPLATE.md").read_text(
        encoding="utf-8")
    if "score_roll.summary" not in template:
        failures.append("REPORT_TEMPLATE.md does not tell the report to quote "
                        "score_roll rather than enumerate the buckets")
    print("  bucket roll every scored name is in the roll with its direction, "
          "and the template quotes it rather than counting")


def claim_an_unmeasured_condition_is_not_a_failed_one(failures: list[str]) -> None:
    """A screen condition that was never measured is counted apart.

    "premarket_rvol 10 of 12" on 2026-08-20 folded AAP and SCSC, whose RVOL is
    null because the baseline denominator is unusable, in with eight names that
    were measured and read low. Withholding them from the screen is right.
    Reporting a missing instrument and a verdict under one number is the thing
    the rest of scan.py exists to prevent.
    """
    from morning import scan

    measured = {
        "symbol": "LOW.US", "price": 40.0, "gap_pct": 9.0,
        "quote": {"marketCap": 5e9, "twoHundredDayAveragePrice": 10.0},
        "prior_high": 39.0, "pm_rvol": 0.2, "catalyst_found": True,
    }
    unmeasured = {
        "symbol": "NULL.US", "price": 40.0, "gap_pct": 9.0,
        "quote": {"marketCap": 5e9, "twoHundredDayAveragePrice": 10.0},
        "prior_high": 39.0, "pm_rvol": None, "catalyst_found": True,
        "pm_rvol_reason": "baseline median volume is zero or missing",
    }
    candidates = [measured, unmeasured]
    for candidate in candidates:
        scan.evaluate_eligibility(candidate)

    if "premarket_rvol" not in (measured.get("day_failed_conditions") or []):
        failures.append("a measured low RVOL did not fail the day screen")
    if measured.get("day_failed_unmeasured"):
        failures.append("a measured RVOL was recorded as never measured: "
                        f"{measured['day_failed_unmeasured']}")
    if unmeasured.get("day_failed_unmeasured") != ["premarket_rvol"]:
        failures.append("a null RVOL was not recorded as never measured: "
                        f"{unmeasured.get('day_failed_unmeasured')}")
    why = " ".join(unmeasured.get("day_failed") or [])
    if "never measured" not in why:
        failures.append(f"the null RVOL's reason does not say so: {why}")

    tally = scan.screen_tally(candidates)
    rvol = tally["day"]["failed_by_condition"]["premarket_rvol"]
    if rvol != {"failed": 2, "cleared": 0, "unmeasured": 1, "measured_and_failed": 1}:
        failures.append(f"the tally does not split the two failures: {rvol}")
    if "never measured" not in tally["day"]["failed_summary"]:
        failures.append("the summary sentence hides the unmeasured failure: "
                        f"{tally['day']['failed_summary']}")

    # Eligibility itself is untouched: both still fail, only the reporting differs.
    if measured["day_eligible"] or unmeasured["day_eligible"]:
        failures.append("splitting the count changed an eligibility decision")
    print("  unmeasured  a null input and a measured miss are counted apart, and "
          "the screen decision is unchanged")


def claim_a_thin_window_is_not_merely_a_late_one(failures: list[str]) -> None:
    """Four bars and fifty bars stop sharing the word partial.

    SCSC on 2026-08-20 carried a 16.34 percent gap, a VWAP and a high off FOUR
    one minute bars holding 1,487 shares. AAP's window also opened late and
    held fifty. Both were "partial".
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    def bars(count: int, start_minute: int) -> list[dict[str, Any]]:
        base = int(ettime.epoch_s(dt.datetime(
            2026, 8, 20, 7, start_minute, tzinfo=ettime.ET)))
        return [{"minute_epoch": base + 60 * i, "h": 10.0, "l": 9.0, "c": 9.5,
                 "v": 100.0, "pv": 950.0} for i in range(count)]

    thin = {"symbol": "THIN.US", "on_watchlist": True}
    full = {"symbol": "FULL.US", "on_watchlist": True}
    watchlist = {"symbols": [{"symbol": "THIN.US", "subscribed": True},
                             {"symbol": "FULL.US", "subscribed": True},
                             {"symbol": "GONE.US", "subscribed": True}]}
    sink = Sink()
    scan.attach_premarket_path(
        [thin, full], watchlist, sink,
        {"THIN.US": bars(4, 42), "FULL.US": bars(50, 26)})

    if thin.get("pm_window_thin") is not True:
        failures.append(f"a four bar window was not called thin: "
                        f"{thin.get('pm_window_thin')}")
    if full.get("pm_window_thin") is not False:
        failures.append(f"a fifty bar window was called thin: "
                        f"{full.get('pm_window_thin')}")
    if thin.get("pm_window_bars") != 4 or full.get("pm_window_bars") != 50:
        failures.append("the bar count is not carried beside the flag")
    if "4 minute" not in (thin.get("pm_window_thin_reason") or ""):
        failures.append(f"the thin reason gives no count: "
                        f"{thin.get('pm_window_thin_reason')}")
    # Late and thin are independent. Both of these opened late.
    if not (thin.get("pm_window_starts_late") and full.get("pm_window_starts_late")):
        failures.append("the fixture did not exercise two late windows, so the "
                        "independence of the two flags is untested")

    # A candidate with no window at all carries the keys, so a reader of the
    # packet cannot mistake a missing key for a full window.
    absent = {"symbol": "GONE.US", "on_watchlist": True}
    scan.attach_premarket_path([absent], watchlist, Sink(), {})
    if "pm_window_thin" not in absent or absent["pm_window_thin"] is not None:
        failures.append("an absent window does not carry a null thin flag: "
                        f"{absent.get('pm_window_thin')}")
    if "INSIDE THE COLLECTION WINDOW" not in (absent.get("pm_reason") or ""):
        failures.append("the no-bars reason still claims the socket was silent "
                        f"all morning: {absent.get('pm_reason')}")
    print("  thin window a four bar window is called thin, a fifty bar one is "
          "not, and lateness is a separate flag")


def claim_a_replayed_print_is_not_silence(failures: list[str]) -> None:
    """A symbol that delivered one replayed print is told from one that did not.

    Both are absent from the bars, because the replay filter sits in
    read_bars_file for good reasons. They are not the same failure: a replayed
    print proves the subscription was accepted. On 2026-08-20 NBTX delivered
    one 04:23 print of 20 shares and UUP one 07:00 print of 1 share, and the
    report said the socket "delivered no trade for them" alongside two symbols
    that really had produced nothing.
    """
    from collect import collect_premarket
    from morning import scan

    with conftest_activate():
        day = "2026-08-20"
        rows = [
            {"symbol": "LIVE.US", "minute_epoch": 1787224800, "h": 1.0, "l": 1.0,
             "c": 1.0, "v": 10.0, "pv": 10.0, "minute_et": "2026-08-20T07:20:00-04:00"},
            {"symbol": "REPLAY.US", "minute_epoch": 1787214000, "h": 1.0, "l": 1.0,
             "c": 1.0, "v": 20.0, "pv": 20.0, "replay": True,
             "minute_et": "2026-08-20T04:23:00-04:00"},
        ]
        path = config.PREMARKET_DIR / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (config.PREMARKET_DIR / f"{day}-subscriptions.json").write_text(
            json.dumps({"symbols": ["LIVE.US", "REPLAY.US", "MUTE.US"],
                        "socket_cap": 50, "subscribed_at": "2026-08-20T07:20:03-04:00"}),
            encoding="utf-8")

        bars, stats = collect_premarket.read_bars_file(path)
        if stats.get("replay_by_symbol") != {"REPLAY.US": 1}:
            failures.append(f"replay is not counted per symbol: "
                            f"{stats.get('replay_by_symbol')}")

        coverage = scan.collector_coverage(bars, day, stats.get("replay_by_symbol"))
        if coverage["silent_with_replay_only"] != ["REPLAY.US"]:
            failures.append("a replay-only symbol is not held apart: "
                            f"{coverage.get('silent_with_replay_only')}")
        if coverage["silent_with_nothing"] != ["MUTE.US"]:
            failures.append("a truly silent symbol is not held apart: "
                            f"{coverage.get('silent_with_nothing')}")
        if sorted(coverage["silent_symbols"]) != ["MUTE.US", "REPLAY.US"]:
            failures.append("the combined silent list changed meaning: "
                            f"{coverage.get('silent_symbols')}")
    print("  replay only a symbol that sent one replayed print is told apart "
          "from one that sent nothing")


def claim_the_two_prior_closes_are_compared(failures: list[str]) -> None:
    """The end of day close and the quoted close stop disagreeing in silence.

    On 2026-08-20 SCSC's were 1.67 percent apart, 51.42 against 52.2909. The
    gap was measured from the first and published as 16.34 percent; from the
    second it is 14.4. Nothing said they differed. The end of day record still
    wins, because this is a disclosure and not a tiebreak.
    """
    from morning import scan

    if scan.PRIOR_CLOSE_DISAGREEMENT_PCT <= 0:
        failures.append("the disagreement floor is not a positive percentage")

    class Api:
        def eod(self, symbol, start, end):
            return [{"date": "2026-08-19", "close": 51.42, "high": 53.0573,
                     "volume": 100.0}], None

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    disagreeing = {"symbol": "SCSC.US", "quote": {"previousClosePrice": 52.2909}}
    agreeing = {"symbol": "OK.US", "quote": {"previousClosePrice": 51.42}}
    sink = Sink()
    scan.attach_daily_history(Api(), [disagreeing, agreeing], sink)

    if disagreeing.get("prior_close") != 51.42:
        failures.append("the end of day record stopped winning: "
                        f"{disagreeing.get('prior_close')}")
    drift = disagreeing.get("prior_close_disagreement_pct")
    if drift is None or not (1.6 < drift < 1.7):
        failures.append(f"the 2026-08-20 SCSC disagreement measured {drift}, "
                        "expected about 1.67 percent")
    if agreeing.get("prior_close_disagreement_pct") != 0.0:
        failures.append("two agreeing closes did not measure zero: "
                        f"{agreeing.get('prior_close_disagreement_pct')}")
    named = [g for g in sink.gaps if "SCSC.US" in g and "prior closes" in g]
    if not named:
        failures.append(f"the disagreement said nothing: {sink.gaps}")
    elif "OK.US" in " ".join(sink.gaps):
        failures.append("an agreeing pair was reported as a disagreement")
    print("  prior close two vendor closes 1.67 percent apart are reported, the "
          "end of day one still wins, and an agreeing pair stays quiet")


def claim_the_baseline_age_travels_with_the_rvol(failures: list[str]) -> None:
    """A denominator warmed six days ago is not presented as this morning's.

    Reusing a cached baseline inside [Baseline] refresh_after_days is the
    design. On 2026-08-20 BLSH's denominator was computed on 08-14, BABA's on
    08-17 and ASST's on 08-18, and the report set those RVOLs beside COIN's,
    computed that morning, with nothing to tell them apart.
    """
    from morning import scan

    today = ettime.today_et()
    if scan._baseline_age_days(None) is not None:
        failures.append("a missing computed_at did not read as an unknown age")
    if scan._baseline_age_days(today.isoformat() + "T07:15:00-04:00") != 0:
        failures.append("a baseline warmed today did not read as zero days old")
    six = (today - dt.timedelta(days=6)).isoformat()
    if scan._baseline_age_days(six + "T07:15:16-04:00") != 6:
        failures.append("a six day old baseline did not read as six days old")
    if scan._baseline_age_days("not a date") is not None:
        failures.append("an unparseable computed_at raised or guessed")

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    stale = {"symbol": "OLD.US", "pm_rvol": 0.19,
             "baseline": {"age_days": 6, "computed_today": False}}
    fresh = {"symbol": "NEW.US", "pm_rvol": 0.29,
             "baseline": {"age_days": 0, "computed_today": True}}
    sink = Sink()
    scan._gap_for_stale_baselines([stale, fresh], sink)
    if not sink.gaps:
        failures.append("a six day old denominator was not reported")
    elif "OLD.US 6 day" not in sink.gaps[0]:
        failures.append(f"the age is not named beside the symbol: {sink.gaps[0]}")
    elif "NEW.US" in sink.gaps[0]:
        failures.append("a denominator warmed this morning was reported as reused")

    quiet = Sink()
    scan._gap_for_stale_baselines([fresh], quiet)
    if quiet.gaps:
        failures.append(f"a fully fresh morning still reported one: {quiet.gaps}")
    print("  baseline age a reused denominator is named with its age, and a "
          "fully warmed morning stays silent")


def claim_a_hand_run_of_one_suite_cannot_touch_real_data(failures: list[str]) -> None:
    """Running a suite module directly sandboxes itself.

    run_tests.py wraps the suite in conftest.activate() and nothing else did,
    so `python -m tests.test_containment` ran every claim against the real
    data/, runs/, logs/ and site/. On 2026-08-20 exactly that appended sixteen
    of test_containment's own fixtures to the real quantifier flag log, two of
    them carrying a verdict, and the next SANDBOXED run failed too because
    activate() copies data/ in and the fixtures came with it.

    The tree photograph cannot catch it: the path already existed and only its
    contents changed.
    """
    from tests import conftest

    if not hasattr(conftest, "standalone"):
        failures.append("conftest has no standalone() for a hand run to use")
        return

    # Every suite module routes its __main__ through it. A new suite added
    # without that line is the way this comes back.
    from tests import run_tests

    for module_name in run_tests.SUITE:
        path = config.PROJECT_ROOT / "src" / (module_name.replace(".", "/") + ".py")
        tail = path.read_text(encoding="utf-8")
        if "_conftest.standalone(main)" not in tail:
            failures.append(f"{path.name} runs main() directly under __main__, so "
                            "a hand run of it writes to the real data directory")

    # The flag tracks nesting rather than being set once, so an inner activate
    # hands it back instead of reporting the sandbox gone.
    # Relative, not absolute: run_tests already holds a sandbox around this
    # claim, so the assertion is that activate() RESTORES what it found rather
    # than that the flag starts false.
    outside = conftest.SANDBOX_ACTIVE
    with conftest_activate():
        if not conftest.SANDBOX_ACTIVE:
            failures.append("SANDBOX_ACTIVE is not set inside a sandbox")
        with conftest_activate():
            pass
        if not conftest.SANDBOX_ACTIVE:
            failures.append("a nested sandbox exit cleared the outer one, so "
                            "standalone() would wrap an already wrapped run")
    if conftest.SANDBOX_ACTIVE is not outside:
        failures.append("activate() did not restore the flag it found, leaving "
                        f"{conftest.SANDBOX_ACTIVE} against {outside}")

    # standalone runs the entry point, and does not open a second sandbox when
    # one is already up.
    seen: list[bool] = []
    with conftest_activate():
        conftest.standalone(lambda: seen.append(conftest.SANDBOX_ACTIVE) or 0)
    if seen != [True]:
        failures.append(f"standalone did not run its entry point sandboxed: {seen}")
    print("  hand run    every suite module sandboxes its own __main__, and the "
          "flag nests instead of being cleared by the inner exit")


# ------------------------------------------- the 2026-08-20 review: containment

def claim_an_abbreviation_is_not_a_ticker_claim(failures: list[str]) -> None:
    """S&P in Market trends invented two tickers and stopped the whole chain.

    _prose_tokens blanked ISO dates and clock times and nothing else before
    _TOKEN_RE ran, so capitals separated by punctuation came apart into single
    letters: "S&P 500 futures are flat" gave P and S, "U.S. equity futures are
    soft" gave S and U, "the P/E is stretched" gave E and P. universe.json
    carries 21 one letter listings and prose_token_stopwords stops only A and
    I, so each fragment became a ticker claim and then an INVENTED one unless
    the packet happened to quote a headline holding the same bare letter.
    Injecting one ordinary Market trends sentence into the four archived
    reports and checking each against its real packet invented P, S and U on
    2026-08-17 and 2026-08-20 and P on 2026-08-19; 08-18 escaped only because
    its packet quotes a headline containing "S&P 500". check_report exits 2 on
    an invented ticker, the chain stops on a non zero return, and containment
    has no regeneration path, so the morning lost render, verify, deliver and
    archive to an abbreviation any writer would use.

    Both directions are asserted, because the cheap fix was to stopword the
    letters and that would have blinded the guard to six real listings in
    prose, trading a false positive for a false negative in the one check that
    exists to catch invented evidence.
    """
    from morning import analyst
    from tests import conftest

    # The claim supplies its own universe rather than reading whatever is on
    # disk. Inside a full run the sandbox copy has already been REWRITTEN by
    # the entrypoints suite, whose scripted exchange-symbol-list holds neither
    # the one letter listings this defect turns on nor TSLA, so reading the
    # file made this claim pass or fail on suite ORDER. The real file is what
    # the defect was found against and its shape is asserted below, so nothing
    # is lost by pinning the fixture.
    real_universe = None
    if config.UNIVERSE_PATH.is_file():
        real_universe = config.UNIVERSE_PATH.read_bytes()
    listed = {"S", "P", "U", "D", "E", "R", "TSLA", "NVDA", "AAPL"}
    config.UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.UNIVERSE_PATH.write_text(json.dumps({
        "symbols": [{"symbol": f"{bare}.US"} for bare in sorted(listed)],
    }), encoding="utf-8")
    try:
        _abbreviation_body(failures, analyst, conftest, listed)
    finally:
        if real_universe is None:
            config.UNIVERSE_PATH.unlink(missing_ok=True)
        else:
            config.UNIVERSE_PATH.write_bytes(real_universe)


def _abbreviation_body(failures: list[str], analyst: Any, conftest: Any,
                       listed: set[str]) -> None:
    """The assertions, split out so the fixture universe is always restored."""
    # A claim that stops testing its defect has to say so rather than pass.
    fragments = sorted({"S", "P", "U", "D", "E", "R"} - listed)
    if fragments:
        failures.append(
            f"{fragments} are not universe listings in the fixture, so the "
            "pieces an abbreviation breaks into cannot become ticker claims "
            "and this claim no longer tests the defect it guards")
    if "TSLA" not in listed:
        failures.append("TSLA is not a fixture listing, so the invented half "
                        "of this claim proves nothing")

    packet_text = json.dumps({
        "session_date": "2026-01-02",
        "candidates": [{"symbol": "NVDA.US"}, {"symbol": "AAPL.US"}],
        "context": [{"symbol": "SPY.US"}, {"symbol": "QQQ.US"}],
    })
    headers = conftest.watchlist_headers()
    columns = len(headers["day watchlist"].strip().strip("|").split("|"))
    tables = [conftest.watchlist_table("day watchlist",
                                       ["| NVDA |" + " |" * (columns - 1)]),
              conftest.watchlist_table("swing watchlist")]
    abbreviations = (
        "S&P 500 futures are flat, U.S. equity futures are soft, and the P/E "
        "on the index is stretched after a year of heavy R&D spending. The "
        "SPY/QQQ spread widened."
    )
    tickers = (
        "AAPL held its bid and the cleanest move on the tape was the move in "
        "NVDA. TSLA traded above its prior day high."
    )
    without = "\n".join(["# PremarketDesk, 2026-01-02", "", "## Market trends",
                         "", tickers, "", *tables])
    with_abbreviations = "\n".join(
        ["# PremarketDesk, 2026-01-02", "", "## Market trends", "",
         abbreviations, "", tickers, "", *tables])

    plain_invented, plain_missing, plain_coverage = analyst.check_report(
        without, packet_text)
    invented, missing, coverage = analyst.check_report(
        with_abbreviations, packet_text)

    if invented != plain_invented:
        failures.append(
            f"one sentence of ordinary abbreviations changed the containment "
            f"verdict from {plain_invented} to {invented}")
    for verdict, label in ((plain_invented, "without"), (invented, "with")):
        if verdict != ["TSLA"]:
            failures.append(
                f"the report {label} abbreviations came back invented={verdict}, "
                "expected exactly ['TSLA'], which is the one name in it the "
                "packet does not carry")
    for token in ("SPY", "QQQ"):
        if token not in coverage["prose_claims"]:
            failures.append(
                f"{token} was lost from the prose claims, so the blanking ate a "
                f"slashed pair of real tickers: {coverage['prose_claims']}")
    for report_missing, label in ((plain_missing, "without"),
                                  (missing, "with")):
        if report_missing:
            failures.append(f"the fixture {label} abbreviations does not name "
                            f"its own candidates: {report_missing}")
    for report_coverage, label in ((plain_coverage, "without"),
                                   (coverage, "with")):
        if report_coverage["structure_failed"]:
            failures.append(f"the fixture {label} abbreviations failed on "
                            "structure, so containment never ran on it")
    print("  prose tokens an abbreviation in prose invents nothing, while a "
          "slashed pair of real tickers and an invented one both survive it")

def claim_the_two_documents_agree_on_who_decides_a_trap(
        failures: list[str]) -> None:
    """One document told the model to judge a trap the other forbade it to judge.

    _compose_stdin pipes prompt_analyst.md and REPORT_TEMPLATE.md into one
    document, so the model reads both at once. Commit f1b1fb9 moved the trap
    verdict into Python and rewrote the template to say "TRAPS ARE DECIDED IN
    THE PACKET AND YOU MUST NOT RE-DERIVE ONE", and prompt rule 5 was left
    reading "a candidate gapping up while its packet headlines carry negative
    sentiment is a trap. Say so plainly in Skips and traps". The two cannot
    both be obeyed and the state they disagree over is live: the 2026-08-20
    packet carries MSTR at a 9.06 percent gap with trap false and a headline
    scored -0.914, and FUTU at 9.48 with one at -0.422.

    The shape is the containment suite's instruction scan: read both documents
    the model will receive and refuse a sentence that asks for what the other
    forbids. A specimen inside backticks passes, by the same convention the
    quantifier guard already uses, because a document that teaches "never
    write this" has to be able to write it.
    """
    import re

    code_span = re.compile(r"`[^`\n]*`")
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    refusal = re.compile(r"\b(?:not|never|cannot|forbid|forbids|forbidden)\b")
    derived_from = ("sentiment", "polarity")

    documents = {
        "prompt_analyst.md": config.ANALYST_PROMPT_PATH,
        "REPORT_TEMPLATE.md": config.REPORT_TEMPLATE_PATH,
    }
    for label, path in documents.items():
        document = path.read_text(encoding="utf-8")
        # The sentence scan reads the document with its backticked specimens
        # blanked; the field names are looked for in the document itself,
        # because both files name them inside backticks.
        text = code_span.sub(" ", document)
        refuses = False
        for sentence in sentence_end.split(" ".join(text.split())):
            low = sentence.lower()
            if "trap" not in low:
                continue
            asks = [word for word in derived_from if word in low]
            if refusal.search(low):
                refuses = refuses or bool(asks)
                continue
            if asks:
                failures.append(
                    f"{label} tells the model to reach a trap verdict from "
                    f"{asks} instead of from the packet: {sentence[:160]!r}. "
                    "The other document forbids exactly that, and the model "
                    "reads both in one stdin.")
        if not refuses:
            failures.append(
                f"{label} never tells the model that a trap is decided in the "
                "packet rather than derived from headline sentiment, so the "
                "instruction the 2026-08-20 report followed is back")
        for field in ("trap_why", "trap_basis"):
            if field not in document:
                failures.append(
                    f"{label} does not point the report at the packet's {field}, "
                    "so a trap the packet decided is published without the "
                    "reason or the counts a reader would need to disagree")
    print("  trap rules   the prompt and the template both send the trap "
          "verdict to the packet, and neither asks for it from sentiment")

# ------------------------------------------------- the 2026-08-20 review: the packet

def claim_a_roundup_classifies_nobody(failures: list[str]) -> None:
    """A multi company wire roundup confers its class on none of the names in it.

    EODHD news tags are ARTICLE scoped, and classify_catalyst took the best
    paying CRITERIA tag over every tag on every kept headline, so a roundup
    handed its strongest class to whichever names the feed returned it for. On
    2026-08-20 the CNBC piece below carried 46 tags naming 45 issuers, EARNINGS
    among them, and EARNINGS belongs to Walmart. MSTR, COIN and MARA were all
    published class earnings off it and BLSH off "Biggest stock movers
    Thursday", while the earnings calendar that morning held AAP, BABA, FUTU,
    SCSC, WMT and WOLF and none of those four. Class earnings pays 3 of the
    score's 10 points, so MSTR published green at 7.0 and three more names
    published yellow at 6.0 on a catalyst they did not have.

    The obvious fix is not available: every roundup in that packet carried an
    EMPTY symbols array, so the symbol tag filter in attach_catalysts never
    fired and cannot be tightened. Breadth is measured instead, and both counts
    are proved here. TAGS catches a roundup handed to one candidate, which is
    SOLO below. SHARING catches a roundup tagged by topic rather than by
    issuer, which is the movers piece: seven topical tags, nothing unusual
    about the count, and the feed gave it to three names.

    DQ is the control and it is a true positive: "DAQO New Energy Non-GAAP
    EPADS misses" really is about DQ, it is simply not on the calendar, and it
    must still classify.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    # The real 2026-08-20 tag lists, because a claim written from invented
    # numbers proves the rule and this one proves the case.
    roundup_title = ("Stocks making the biggest moves premarket: Walmart, "
                     "Coinbase, Moderna, Alibaba &amp; more")
    roundup_tags = [
        "ADVANCE AUTO PA", "ADVANCE AUTO PARTS INC", "ALIBABA GROUP H",
        "ALIBABA GROUP HOLDING LTD", "AMERICAN BITCOI", "AMERICAN BITCOIN CORP",
        "BREAKING NEWS M", "BREAKING NEWS MARKETS", "BUSINESS", "CIRCLE INTERNET",
        "CIRCLE INTERNET GROUP INC", "CNBC US SOURCE", "CNBC US TEAM",
        "COINBASE GLOBAL", "CONSENSUS ESTIMATE", "COTY INC", "CRYPTO",
        "DONALD TRUMP", "EARNINGS", "ECONOMY", "FINANCE", "FOURTH QUARTER",
        "FOX PREMARKET M", "FOX PREMARKET MOVERS 260820", "GUIDANCE",
        "MARA HOLDINGS I", "MARA HOLDINGS INC", "MARKET INSIDER", "MARKETS",
        "MERCK CO INC", "MICHELLE FOX", "MODERNA INC", "NETEASE INC",
        "NORDSON CORP", "PHARMA", "QUARTERLY EARNINGS", "REGWALLMARKETMO",
        "REGWALLMARKETMOVERS", "SEMICONDUCTORS", "STOCK MARKETS", "STOCKS",
        "STRATEGY INC", "UNITED STATES", "US MARKETS", "WALMART INC",
        "WOLFSPEED INC",
    ]
    movers_title = "Biggest stock movers Thursday: Crypto stocks, WOLF, and more"
    movers_tags = ["CRYPTO", "EARNINGS", "FDA-APPROVAL", "GENE-THERAPY",
                   "ON THE MOVE", "OPERATING INCOME", "STOCK-MOVERS"]
    release_title = ("DAQO New Energy Non-GAAP EPADS of -$1.20 misses by $0.63, "
                     "revenue of $62.66M beats by $6.6M")
    release_tags = ["EARNINGS", "EARNINGS NEWS", "RATINGS"]

    now = ettime.now_et()

    def article(title: str, tags: list[str], link: str) -> dict[str, Any]:
        return {"date": (now - dt.timedelta(minutes=30)).isoformat(),
                "title": title, "link": link, "sentiment": {"polarity": 0.1},
                "tags": list(tags), "symbols": []}

    roundup = article(roundup_title, roundup_tags, "https://example.test/cnbc")
    movers = article(movers_title, movers_tags, "https://example.test/movers")
    release = article(release_title, release_tags, "https://example.test/daqo")
    # The same wire story under its own link, so the feed returned it to one
    # name only. Its tag list is the thing that gives it away.
    lone_roundup = article(roundup_title, roundup_tags, "https://example.test/solo")

    feed = {
        "MSTR.US": [roundup, movers],
        "COIN.US": [roundup],
        "MARA.US": [roundup],
        "WOLF.US": [movers],
        "BLSH.US": [movers],
        "SOLO.US": [lone_roundup],
        "DQ.US": [release],
    }
    expected = {"MSTR.US": "none", "COIN.US": "none", "MARA.US": "none",
                "WOLF.US": "none", "BLSH.US": "none", "SOLO.US": "none",
                "DQ.US": "earnings"}

    class FeedApi:
        def news(self, symbol, start=None, end=None):
            return [dict(row) for row in feed[symbol]], None

    candidates = [{"symbol": symbol} for symbol in feed]
    scan.attach_catalysts(FeedApi(), candidates, Sink())

    for candidate in candidates:
        symbol = candidate["symbol"]
        got, why = scan.classify_catalyst(candidate, set())
        if got != expected[symbol]:
            failures.append(
                f"{symbol} classified {got!r} from {len(feed[symbol])} "
                f"headline(s), expected {expected[symbol]!r}: {why}")
        # A roundup only morning is CHECKED and empty, which is class none with
        # catalyst_found true. Null would say the feed was never read.
        if candidate.get("catalyst_found") is not True:
            failures.append(
                f"{symbol} came back catalyst_found "
                f"{candidate.get('catalyst_found')!r}, but the feed answered")
        if not why:
            failures.append(f"{symbol} carries a class with no reason")

    paid = next(c for c in candidates if c["symbol"] == "DQ.US")
    _, why = scan.classify_catalyst(paid, set())
    if "DAQO" not in why:
        failures.append(f"the class DQ was paid does not name the headline that "
                        f"paid it: {why}")
    if "1 of this morning's 7 candidates" not in why:
        failures.append(f"the class DQ was paid does not say how wide the "
                        f"article was: {why}")

    refused = next(c for c in candidates if c["symbol"] == "MSTR.US")
    _, why = scan.classify_catalyst(refused, set())
    if "46 tag(s)" not in why or "biggest moves premarket" not in why:
        failures.append(f"MSTR does not name the widest roundup it refused, nor "
                        f"how many issuers that article named: {why}")

    scopes = {c["symbol"]: [(h.get("article_scope") or {}) for h in c["headlines"]]
              for c in candidates}
    if scopes["SOLO.US"][0].get("returned_for_candidates") != 1:
        failures.append(
            "the lone roundup was refused for being shared rather than for its "
            f"tag list, so the tag count test is not proved: {scopes['SOLO.US']}")
    if scopes["BLSH.US"][0].get("tag_count") != len(movers_tags):
        failures.append(
            f"the movers roundup reads as {scopes['BLSH.US']} tags, and the "
            "sharing test is what has to catch it")

    print("  roundup      a multi company roundup classifies none of the names "
          "it lists, and a single company release still does")

def claim_the_trap_balance_reads_the_whole_window(failures: list[str]) -> None:
    """The balance is counted over the window, not over the three on display.

    attach_catalysts stored recent[:news_keep] with news_keep at 3 and recorded
    the true count beside it as news_in_window, and attach_traps then weighed
    the truncated list. So the rule CRITERIA describes as "strictly more
    negative than positive among those the vendor scored" was decided on the
    three most recent items: on 2026-08-20 WMT published trap=False on 3 of 45
    headlines, COIN on 3 of 24 and BABA on 3 of 17. With
    min_headlines_for_balance at 2 and a sample that can never exceed 3, one
    negative against zero positives satisfies the rule, which is a verdict
    resting on one headline and is the exact reading the balance rule was
    written that same day to prevent.

    trap_basis compounded it, publishing headlines_scored and
    headlines_unscored as though the two partitioned the coverage: WMT read
    scored 3, unscored 0, with 42 counted nowhere.

    The fixture is the shape that breaks it. The three newest are two negatives
    and a neutral, so the displayed list alone says trap; the forty two behind
    them are overwhelmingly positive, so the window says it is not.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    now = ettime.now_et()

    def row(minutes_ago: int, polarity, title: str) -> dict[str, Any]:
        return {"date": (now - dt.timedelta(minutes=minutes_ago)).isoformat(),
                "title": title, "link": f"https://example.test/{title}",
                "sentiment": None if polarity is None else {"polarity": polarity},
                "tags": ["RETAIL"], "symbols": []}

    rows = [row(1, -0.9, "n1"), row(2, -0.8, "n2"), row(3, 0.0, "z1")]
    rows += [row(10 + i, 0.9, f"p{i}") for i in range(20)]
    rows += [row(40 + i, None, f"u{i}") for i in range(22)]

    class FeedApi:
        def news(self, symbol, start=None, end=None):
            return [dict(r) for r in rows], None

    candidates = [{"symbol": "WIDE.US", "gap_pct": 9.0}]
    scan.attach_catalysts(FeedApi(), candidates, Sink())
    scan.attach_traps(candidates, Sink())
    wide = candidates[0]

    if wide.get("trap") is not False:
        failures.append(
            f"a name with 2 negative and 20 positive headlines in the window "
            f"came back trap={wide.get('trap')!r}: {wide.get('trap_why')}")
    basis = wide.get("trap_basis") or {}
    if basis.get("headlines_in_window") != len(rows):
        failures.append(
            f"trap_basis counted over {basis.get('headlines_in_window')} "
            f"headlines, not the {len(rows)} in the window")
    if basis.get("headlines_scored", 0) + basis.get("headlines_unscored", 0) != \
            wide.get("news_in_window"):
        failures.append(
            f"trap_basis scored {basis.get('headlines_scored')} plus unscored "
            f"{basis.get('headlines_unscored')} does not account for the "
            f"{wide.get('news_in_window')} headlines in the window")
    if basis.get("headlines_displayed") != len(wide.get("headlines") or []):
        failures.append(
            f"trap_basis does not say how many headlines are on display: {basis}")

    # The same three headlines with no window count behind them are all a
    # caller has, and the basis has to say which list it read rather than
    # presenting three of forty five as the window.
    displayed = [{"symbol": "OLD.US", "gap_pct": 9.0, "catalyst_found": True,
                  "headlines": wide["headlines"]}]
    scan.attach_traps(displayed, Sink())
    if displayed[0].get("trap") is not True:
        failures.append(
            "the displayed three no longer produce the old verdict, so this "
            "fixture no longer demonstrates the defect")
    if "displayed headlines only" not in (
            displayed[0].get("trap_basis") or {}).get("counted_over", ""):
        failures.append(
            "a verdict taken off the displayed list does not say so: "
            f"{(displayed[0].get('trap_basis') or {}).get('counted_over')}")

    print("  full window  the trap balance is counted over every headline in "
          "the window, and the basis accounts for all of them")

def claim_the_volume_check_carries_its_sign(failures: list[str]) -> None:
    """The collector volume check reports which way it is wrong, and to whom.

    verify_against_intraday computed a signed per symbol difference and
    persisted only its magnitude, and three consumers then asserted a direction
    a magnitude cannot carry: scan.volume_check wrote "an RVOL below is
    understated by about that much again", analyst.py repeated it and
    REPORT_TEMPLATE.md ordered the model to say it plainly, which
    runs/2026-08-20/report.md published. doc/research/COLLECTOR_VOLUME.md had
    already recorded the collector wrong in BOTH directions: 2026-08-14 at 3.83
    times the vendor in aggregate against 2026-08-17 at -88.49 percent, and a
    signed median of -33.77 beside a ratio of 3.83 on the same session, which
    an absolute median hides completely.

    The measurement was biased the same way. The loop walks the collected bars,
    so a subscribed symbol the socket never answered for was in neither
    compared nor unavailable (LYTS.US and NBTX.US on 2026-08-20 were in
    neither), and a vendor volume of zero left the loop without incrementing
    anything. The four buckets now account for the whole subscription.

    Old summaries carrying no sign are still on disk and the morning must read
    them rather than crash on one, so the last case here is an old shape file
    reading as direction unknown and the packet refusing to call it
    understatement.
    """
    from collect import collect_premarket
    from core import eodhd
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    # The two readings in COLLECTOR_VOLUME.md, and the mixed session between
    # them that is the reason a direction is only claimed when both agree.
    directions = {
        (-88.49, 0.0994): "under",
        (40.0, 3.83): "over",
        (-33.77, 3.8257): "mixed",
    }
    direction_of = getattr(collect_premarket, "_volume_check_direction", None)
    if direction_of is None:
        failures.append(
            "the collector reads no direction off its own measurement, so "
            "nothing stops the packet calling an unmeasured sign understatement")
    else:
        for (median, ratio), want in directions.items():
            got, phrase = direction_of(median, ratio)
            if got != want:
                failures.append(
                    f"a signed median of {median} against an aggregate ratio of "
                    f"{ratio} read as {got!r}, expected {want!r}")
            if not phrase:
                failures.append(f"direction {got!r} came back with no phrase")

    day = "2026-08-19"
    minute = 1787236800
    collected = {"A.US": 1000.0, "B.US": 1000.0, "C.US": 100000.0,
                 "D.US": 500.0, "E.US": 500.0}
    vendor = {"A.US": 2000.0, "B.US": 2500.0, "C.US": 25000.0, "E.US": 0.0}

    class BarsApi:
        def intraday(self, symbol, start, end, interval):
            if symbol not in vendor:
                return [], None
            return [{"timestamp": minute, "volume": vendor[symbol]}], None

    with conftest_activate():
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        collect_premarket.bar_path(day).write_text(
            "".join(json.dumps({"symbol": symbol, "minute_epoch": minute,
                                "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0,
                                "v": volume, "trades": 1}) + "\n"
                    for symbol, volume in collected.items()),
            encoding="utf-8")
        collect_premarket.subscriptions_path(day).write_text(
            json.dumps({"symbols": sorted(list(collected) + ["F.US", "G.US"]),
                        "requested_count": 7, "socket_cap": 50}),
            encoding="utf-8")

        real_client = eodhd.client
        eodhd.client = lambda *a, **k: BarsApi()
        try:
            summary = collect_premarket.verify_against_intraday(day, quiet=True)
        finally:
            eodhd.client = real_client

        if not summary:
            failures.append("the volume check returned nothing for a day it "
                            "could compare three symbols on")
        elif summary.get("subscribed") is None:
            failures.append(
                "the volume check counts nothing about the subscription, so a "
                "symbol the socket never answered for is in no bucket at all: "
                f"{sorted(summary)}")
        else:
            buckets = (summary.get("compared", 0) + summary.get("unavailable", 0)
                       + summary.get("vendor_zero_volume", 0)
                       + summary.get("collector_silent", 0))
            if buckets != summary["subscribed"]:
                failures.append(
                    f"compared {summary.get('compared')}, unavailable "
                    f"{summary.get('unavailable')}, vendor zero "
                    f"{summary.get('vendor_zero_volume')} and silent "
                    f"{summary.get('collector_silent')} sum to {buckets} against "
                    f"a subscription of {summary['subscribed']}")
            if summary.get("collector_silent_symbols") != ["F.US", "G.US"]:
                failures.append(
                    "the symbols the collector never heard are not named: "
                    f"{summary.get('collector_silent_symbols')}")
            signed = summary.get("median_signed_pct")
            ratio = summary.get("aggregate_ratio")
            if signed is None or ratio is None:
                failures.append(
                    "the check publishes no signed median or no aggregate "
                    f"ratio, so its direction cannot be read: {sorted(summary)}")
            elif signed >= 0 or ratio <= 1:
                failures.append(
                    f"the fixture no longer disagrees with itself: signed median "
                    f"{signed}, aggregate ratio {ratio}")
            elif summary.get("direction") != "mixed":
                failures.append(
                    "a typical symbol below the vendor and an aggregate above it "
                    f"read as {summary.get('direction')!r}, not mixed")
            if (summary.get("minutes_compared_by_symbol") or {}).get("A.US") != 1:
                failures.append(
                    "the per symbol comparable minute counts are not published: "
                    f"{summary.get('minutes_compared_by_symbol')}")

        # What the packet says about it, on a mixed reading and on an old one.
        for existing in config.RUNS_DIR.glob("*/verify_intraday.json"):
            existing.unlink()
        target = config.run_dir(day)
        target.mkdir(parents=True, exist_ok=True)
        written = target / "verify_intraday.json"

        written.write_text(json.dumps(summary), encoding="utf-8")
        sink = Sink()
        scan.volume_check("2026-08-20", sink)
        stated = " ".join(sink.gaps)
        if "BOTH directions" not in stated:
            failures.append(f"a mixed reading is not reported as mixed: {stated}")
        if "understated" in stated.lower():
            failures.append(
                "a mixed reading is still described as understatement, which is "
                f"the assertion the sign was added to stop: {stated}")

        written.write_text(json.dumps(
            {"day": day, "compared": 73, "within_one_percent": 0,
             "median_abs_pct": 90.0, "unavailable": 0}), encoding="utf-8")
        old = collect_premarket.latest_volume_check("2026-08-20")
        if old is None or old.get("sign_recorded") is not False:
            failures.append(f"an old shape summary did not read as unsigned: {old}")
        elif old.get("direction") != "unknown":
            failures.append(
                f"an old shape summary claimed direction {old.get('direction')!r}")
        sink = Sink()
        scan.volume_check("2026-08-20", sink)
        stated = " ".join(sink.gaps)
        if "understated" in stated.lower():
            failures.append(
                "a reading with no sign in it is still called understatement: "
                f"{stated}")
        if "unknown" not in stated:
            failures.append(
                f"a reading with no sign does not say the direction is unknown: "
                f"{stated}")

    print("  volume sign  the collector check reports the direction it "
          "measured, accounts for both missing sides, and an unsigned reading "
          "says so")

def claim_a_skipped_quote_is_not_a_missing_float(failures: list[str]) -> None:
    """A call never made is not a vendor that answered without the field.

    On the thin quota path scan sets candidate["quote"] = {} for every
    candidate, one line after correctly recording catalyst_error as "news call
    skipped". attach_float_rotation runs outside that branch and could not tell
    an empty dict from a fetched quote missing sharesFloat, so it wrote "the
    delayed quote carried no sharesFloat" for the entire watchlist, and
    REPORT_TEMPLATE.md tells the model never to supply the reason a number is
    missing but to quote the packet's. The report therefore told its reader the
    vendor had no float data for any name on it. No number was wrong; the
    provenance was false. attach_traps had the same shape one function later,
    hard coding "the news call failed" over a call that was skipped.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    clause = "3,921 of 100,000 remaining on the shared key"
    skipped = {"symbol": "SKIP.US", "collector_covered": True, "pm_volume": 5000,
               "quote": {}, "quote_skipped": clause, "gap_pct": 9.0,
               "catalyst_found": None,
               "catalyst_error": f"news call skipped: {clause}", "headlines": []}
    answered = {"symbol": "THIN.US", "collector_covered": True, "pm_volume": 5000,
                "quote": {"marketCap": 2e9}, "gap_pct": 9.0,
                "catalyst_found": None, "headlines": []}
    sink = Sink()
    scan.attach_float_rotation([skipped, answered], sink)
    scan.attach_traps([skipped, answered], sink)

    reason = skipped.get("pm_float_rotation_reason") or ""
    if "never fetched" not in reason or clause not in reason:
        failures.append(
            f"a candidate whose quote was skipped for quota reports {reason!r}")
    if "carried no sharesFloat" in reason:
        failures.append(
            "a skipped quote is still reported as a vendor that answered "
            f"without the field: {reason!r}")
    if "carried no sharesFloat" not in (answered.get("pm_float_rotation_reason") or ""):
        failures.append(
            "a quote that really was fetched and really had no sharesFloat no "
            f"longer says so: {answered.get('pm_float_rotation_reason')!r}")
    if not any("never fetched" in note and "SKIP.US" in note for note in sink.gaps):
        failures.append(f"the skipped quote is not in gaps_to_fill: {sink.gaps}")

    if clause not in (skipped.get("trap_why") or ""):
        failures.append(
            "the trap verdict does not quote the reason the news was never "
            f"weighed: {skipped.get('trap_why')!r}")
    if "the news call failed" in (skipped.get("trap_why") or ""):
        failures.append(
            "a skipped news call is still reported as a failed one: "
            f"{skipped.get('trap_why')!r}")

    print("  skipped call a quote and a news call skipped for quota are "
          "reported as skipped, never as a vendor that answered empty")

# ---------------------------------------------------- the 2026-08-20 review: the calendar

def claim_a_missing_calendar_stands_the_vintage_gate_down(failures: list[str]) -> None:
    """A Monday with no exchange calendar degrades, rather than refusing the morning.

    market_today.is_trading_day had no "cannot answer" result. With no usable
    data/exchange-details.json it returned (True, "calendar unavailable,
    assuming the market is open") for every date, weekends included, and it did
    not raise, so vintage.previous_trading_session's except Exception never
    fired for the fault its own docstring names: a Monday's prior session came
    back as the Sunday. prior_session_date is read from the vendor's end of day
    bar rather than from the calendar, so checks (c) and (d) then failed every
    candidate and every prior_session_only snapshot row of a packet whose dates
    were all correct. The archived 2026-08-17 run, replayed with the cache
    removed, produced six violations that way. enforce() rewrote data/UNVERIFIED
    over the human's note and raised, scan.main returned 1, and the chain
    stopped before the analyst with no packet and no report, accusing the vendor
    of stale data when the only thing missing was a holiday list.

    The fault is installed the way production produces it, by making the cache
    absent and then unreadable, not by making is_trading_day raise: a raising
    guard is caught already and was never the shape of this failure.

    The fixture is that Monday's shape rather than that Monday's file, because
    a guard that only runs on the machine where the bug was found is not a
    guard.
    """
    from morning import vintage
    from morning import verify_morning
    from ops import market_today

    session, prior = dt.date(2026, 8, 17), dt.date(2026, 8, 14)

    def monday_packet() -> dict[str, Any]:
        """A clean Monday packet, in the shape the 2026-08-17 run wrote."""
        from core import criteria

        crit = criteria.load()
        # Read from the key check (a) reads, so the fixture cannot drift away
        # from the window it is supposed to sit inside.
        opens = ettime.at_hm(session, crit.clock("baseline", "session_start"))
        printed = ettime.stamp(opens + dt.timedelta(minutes=1))
        return {
            "session_date": session.isoformat(),
            "candidates": [
                {"symbol": "HTHT.US", "price": 44.16, "price_time": printed,
                 "prior_close": 41.88, "prior_high": 41.91,
                 "prior_session_date": prior.isoformat()},
                {"symbol": "KEEL.US", "price": 3.70, "price_time": printed,
                 "prior_close": 3.51, "prior_high": 3.55,
                 "prior_session_date": prior.isoformat()},
            ],
            "market_snapshot": [
                {"label": "spy", "symbol": "SPY.US", "last": 776.21,
                 "as_of": printed, "prior_close": 776.34,
                 "prior_session_date": prior.isoformat(),
                 "prior_session_only": False},
                {"label": "vix", "symbol": "VIX.INDX", "last": 14.53,
                 "as_of": prior.isoformat(), "prior_session_only": True},
                {"label": "dxy", "symbol": "DXY.INDX", "last": 97.4,
                 "as_of": prior.isoformat(), "prior_session_only": True},
            ],
            "notable_movers": {"rows": [
                {"symbol": "HTHT.US", "leg": "premarket",
                 "as_of_session": session.isoformat(), "price_time": printed},
                {"symbol": "KEEL.US", "leg": "prior_session",
                 "as_of_session": prior.isoformat()},
            ]},
        }

    calendar = {"Name": "USA Stocks", "Code": "US",
                "ExchangeHolidays": {"1": {"Date": "2026-12-25",
                                           "Holiday": "Christmas Day"}},
                "TradingHours": {"WorkingDays": "Mon,Tue,Wed,Thu,Fri"},
                "fetched_at": ettime.stamp(ettime.now_et())}

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="premarketdesk-calendar-"))
    marker = scratch / "UNVERIFIED"
    saved_path = market_today.CACHE_PATH
    saved_network = market_today.ALLOW_NETWORK
    saved_marker = verify_morning.UNVERIFIED_MARKER

    def install(state: str) -> None:
        """Point the guard at a cache that is good, absent, or unreadable."""
        path = scratch / f"exchange-details-{state}.json"
        if state == "good":
            path.write_text(json.dumps(calendar), encoding="utf-8")
        elif state == "unreadable":
            path.write_text("{not json", encoding="utf-8")
        market_today.CACHE_PATH = path
        market_today.reset_memo()

    # The morning chain runs with ALLOW_NETWORK false, and so does this: a
    # stale or missing cache must not send the claim to the vendor.
    market_today.ALLOW_NETWORK = False
    verify_morning.UNVERIFIED_MARKER = marker
    try:
        install("good")
        honest = vintage.check_packet(monday_packet())
        if honest:
            failures.append("the Monday fixture is not clean under a calendar that "
                            f"can answer, so nothing below tests the fault: {honest}")
            return

        for state in ("absent", "unreadable"):
            install(state)
            assumed, _why = market_today.is_trading_day(session - dt.timedelta(days=1))
            if assumed is not True:
                failures.append(f"an {state} cache no longer reads as open to the "
                                "exit code path, so this claim is installing a "
                                "different fault than production produces")
                continue
            found = vintage.check_packet(monday_packet())
            if found:
                failures.append(f"with the exchange calendar {state}, a Monday packet "
                                f"whose dates are all correct was refused on "
                                f"{sorted({v['check'] for v in found})}: {found}")
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    vintage.enforce(monday_packet())
            except Exception as exc:  # noqa: BLE001
                failures.append(f"with the exchange calendar {state}, enforce raised "
                                f"{type(exc).__name__}: {exc}. scan returns 1 on that "
                                "and the morning stops before the analyst")
            if marker.exists():
                failures.append(f"with the exchange calendar {state}, the delivery "
                                "gate was rewritten over whatever note a human had "
                                "left in it")
                marker.unlink()

        # Standing down is not going quiet. Everything that never needed a
        # session date still fires with the calendar dark, or a missing holiday
        # list would become a way to walk a genuinely stale packet past the gate.
        install("absent")
        broken = monday_packet()
        broken["candidates"][0]["prior_high"] = broken["candidates"][0]["prior_close"] - 1
        broken["market_snapshot"][0]["as_of"] = None
        still = {v["check"] for v in vintage.check_packet(broken)}
        if still != {"b", "d"}:
            failures.append("with the calendar dark, a prior_high below its own "
                            "prior_close and a snapshot row with no readable as_of "
                            f"produced {sorted(still)}, expected b and d")

        # And (c) bites again the moment the calendar can answer, which is the
        # half of this that a stand down could quietly cost.
        install("good")
        misdated = monday_packet()
        misdated["candidates"][0]["prior_session_date"] = "2026-08-16"
        caught = [v for v in vintage.check_packet(misdated) if v["check"] == "c"]
        if len(caught) != 1:
            failures.append("a prior_close dated to the Sunday was not caught by "
                            f"check (c) under a calendar that can answer: {caught}")
    finally:
        # Restored, and the restore is the point: run_tests imports every suite
        # into one process, so a CACHE_PATH left pointing at a temporary
        # directory belongs to every claim after this one.
        market_today.CACHE_PATH = saved_path
        market_today.ALLOW_NETWORK = saved_network
        verify_morning.UNVERIFIED_MARKER = saved_marker
        market_today.reset_memo()

    print("  dark cal     a Monday packet with no exchange-details.json passes the "
          "vintage gate instead of failing every dated row in it, and the checks "
          "that never needed a calendar still fire")

def claim_the_previous_session_helper_says_when_it_does_not_know(
        failures: list[str]) -> None:
    """The session walk answers unknown on a dark calendar, not the Sunday.

    is_trading_day assumes open when there is no holiday list, deliberately:
    every scheduled .bat runs `python -m ops.market_today` first and branches
    on its EXIT CODE, and a morning that refuses to run because a cache file is
    missing is worse than one that runs. What was wrong is that a caller asking
    which session was previous could not tell that answer from that assumption,
    so previous_trading_session walked one day back from a Monday, was told the
    Sunday trades, and returned the Sunday.

    Both halves are asserted here, because the fix is only correct if it
    changes one of them and not the other: the exit code path still assumes
    open, and trading_day_state says None instead.
    """
    from morning import vintage
    from ops import market_today

    if not hasattr(market_today, "trading_day_state"):
        failures.append("market_today has no trading_day_state, so no caller can "
                        "tell an answer about the calendar from an assumption")
        return

    monday, friday = dt.date(2026, 8, 17), dt.date(2026, 8, 14)
    sunday = dt.date(2026, 8, 16)
    calendar = {"Name": "USA Stocks", "Code": "US", "ExchangeHolidays": {},
                "TradingHours": {"WorkingDays": "Mon,Tue,Wed,Thu,Fri"},
                "fetched_at": ettime.stamp(ettime.now_et())}

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="premarketdesk-session-"))
    good = scratch / "exchange-details.json"
    good.write_text(json.dumps(calendar), encoding="utf-8")
    saved_path = market_today.CACHE_PATH
    saved_network = market_today.ALLOW_NETWORK
    market_today.ALLOW_NETWORK = False
    try:
        market_today.CACHE_PATH = good
        market_today.reset_memo()
        if market_today.trading_day_state(sunday)[0] is not False:
            failures.append("a calendar that CAN answer no longer says the Sunday is "
                            "closed, so the unknown below cannot be told from it")
        walked = vintage.previous_trading_session(monday)
        if walked != friday:
            failures.append(f"with the calendar in hand the session before Monday "
                            f"{monday} came back as {walked}, expected {friday}")

        market_today.CACHE_PATH = scratch / "no-such-cache.json"
        market_today.reset_memo()
        assumed = market_today.is_trading_day(sunday)
        if assumed[0] is not True:
            failures.append(f"is_trading_day stopped assuming the market is open on "
                            f"an unknown calendar: {assumed}. Every scheduled .bat "
                            "branches on that exit code, and each one would now "
                            "either be blocked or run on a closed market")
        state = market_today.trading_day_state(sunday)
        if state[0] is not None or not state[1]:
            failures.append(f"trading_day_state answered {state} for a Sunday with no "
                            "calendar at all, and an assumption is not an answer")
        for day, name in ((monday, "Monday"), (friday, "Friday")):
            got = vintage.previous_trading_session(day)
            if got is not None:
                failures.append(f"with no calendar the session before {name} {day} "
                                f"came back as {got}. On a Monday that is the Sunday, "
                                "and every dated row in the packet is then compared "
                                "against a day the market was shut")
        if vintage.sessions_back(monday, 0) != monday:
            failures.append("zero sessions back stopped being today under a dark "
                            "calendar, which stands check (e) down on the one leg it "
                            "can still date")
        if vintage.sessions_back(monday, 1) is not None:
            failures.append("one session back answered with a date under a dark "
                            "calendar, so the walk carried an assumption forward")
    finally:
        market_today.CACHE_PATH = saved_path
        market_today.ALLOW_NETWORK = saved_network
        market_today.reset_memo()

    print("  prev session the guard still assumes open for the exit code, and the "
          "session walk reports unknown rather than handing a Monday the Sunday")

# ----------------------------------------------------- the 2026-08-20 review: the watchdog

def claim_a_live_job_is_not_rerun_on_top_of_itself(failures: list[str]) -> None:
    """The chain and the nightly are checked for life before a second copy starts.

    maybe_rerun launched both on the absence of a finish marker in the dated
    log alone. A job that started seconds ago has not written that marker, so
    it was indistinguishable from one that died, and only the collector branch
    was gated. The trigger is a late machine wake: every task carries
    -StartWhenAvailable and two catching up 0.15 seconds apart is on record.
    Sleep through 08:45, wake at 09:05, and Scheduler fires the missed chain
    and the missed monitor together, so a second job_morning_chain.bat starts
    fifteen seconds into the first: two scans write packet.json at once and
    two analyst steps each spend a claude CLI completion. The nightly was
    easier still, because fired_ok wanted last_result "0" and a task that is
    still running reports 267009.
    """
    from ops import monitor_jobs

    def one_pass(now, answer):
        launched: list[str] = []
        real_query, real_launch = monitor_jobs.query_task, monitor_jobs.launch_bat
        monitor_jobs.query_task = lambda name: dict(answer)
        monitor_jobs.launch_bat = lambda bat, dry: launched.append(bat)
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                monitor_jobs.check_all(now, dry_run=True)
        finally:
            monitor_jobs.query_task = real_query
            monitor_jobs.launch_bat = real_launch
        return launched, printed.getvalue()

    with conftest_activate():
        day = ettime.today_str()
        # Quiet the branches this claim is not about. Today's watchlist with a
        # subscription list beside it is the one state in which discover is
        # never rerun, and an empty ledger keeps maybe_rerun off its daily cap.
        config.WATCHLIST_PATH.write_text(
            json.dumps({"generated_at": f"{day}T07:15:00-04:00", "symbols": []}),
            encoding="utf-8")
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        (config.PREMARKET_DIR / f"{day}-subscriptions.json").write_text(
            json.dumps({"symbols": []}), encoding="utf-8")
        (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        logs = {
            "chain": config.LOGS_DIR / f"morning-chain-{day}.log",
            # The nightly's marker is already on disk from the 07:00 catch-up
            # run, which is exactly the state that made a 22:15 nightly still
            # working through the backfill read as one that had failed.
            "nightly": config.LOGS_DIR / f"nightly-{day}.log",
        }
        logs["chain"].write_text("===== scan started =====\n", encoding="utf-8")
        logs["nightly"].write_text("===== archive finished rc=0 =====\n",
                                   encoding="utf-8")

        running = {"exists": True, "status": "Running",
                   "last_run": ettime.now_et(), "last_result": "267009"}
        finished_badly = {"exists": True, "status": "Ready",
                          "last_run": ettime.now_et(), "last_result": "1"}

        for label, answer, expect_rerun in (("live", running, False),
                                            ("dead", finished_badly, True)):
            for job, clock, bat in (("chain", (9, 5), "job_morning_chain.bat"),
                                    ("nightly", (22, 50), "job_nightly.bat")):
                now = ettime.now_et().replace(hour=clock[0], minute=clock[1],
                                              second=0, microsecond=0)
                age = 5 if label == "live" else 7200
                stamp = now.timestamp() - age
                os.utime(logs[job], (stamp, stamp))
                launched, printed = one_pass(now, answer)
                if (bat in launched) is not expect_rerun:
                    failures.append(
                        f"a {label} {job} at {clock[0]:02d}:{clock[1]:02d} "
                        f"{'was not' if expect_rerun else 'was'} rerun; the pass "
                        f"launched {launched or 'nothing'}")
                if label == "live" and f"{job:<10} RUNNING" not in printed:
                    failures.append(
                        f"a live {job} was not reported as running: {printed!r}")

        # 267009 is 0x41301, "the task is currently running". It is the value
        # the nightly branch read as a plain failure code, and Scheduler can
        # report it in Last Result with Status already back to Ready.
        today = ettime.now_et().date()
        for spelling in ("267009", "0x41301"):
            if not monitor_jobs._task_running(
                    {"exists": True, "status": "Ready",
                     "last_run": ettime.now_et(), "last_result": spelling}, today):
                failures.append(f"last_result {spelling} was not read as a task "
                                "that is still running")
        for settled in ("0", "1", "-2147024894", ""):
            if monitor_jobs._task_running(
                    {"exists": True, "status": "Ready",
                     "last_run": ettime.now_et(), "last_result": settled}, today):
                failures.append(f"last_result {settled!r} was read as a task "
                                "still running, so a job that really died would "
                                "never be rerun")

        # The two kinds of evidence are independent, so neither alone may be
        # load bearing. A task Scheduler cannot see (launch_bat Popens the .bat
        # rather than starting the task, and the FAILED branch invites a hand
        # run) is alive on its log alone.
        now = ettime.now_et().replace(hour=9, minute=5, second=0, microsecond=0)
        stamp = now.timestamp() - 5
        os.utime(logs["chain"], (stamp, stamp))
        launched, printed = one_pass(now, {"exists": False, "error": "no such task"})
        if "job_morning_chain.bat" in launched:
            failures.append("a chain whose log was written five seconds ago was "
                            "rerun because Task Scheduler had no record of it, "
                            "which is every hand run and every rerun this module "
                            "launched itself")
    print("  liveness     a chain or nightly whose task is running or whose log "
          "is warm is left alone, and a dead one is still rerun")

def claim_a_previous_session_watchlist_reruns_discover(failures: list[str]) -> None:
    """The discover rerun turns on the watchlist's session, not on the clock.

    maybe_rerun("discover") sat inside the else of "now_m < discover_due" and
    was guarded by "now_m < collector_start", so it needed 445 <= now_m < 440.
    With discover_due 07:25 and the collector starting 07:20 no clock value
    satisfies that, and register_tasks makes the monitor's earliest weekday
    firing 07:25 anyway, so the safety net CRITERIA and tasks/README both
    describe could never engage. Nothing else notices a stale watchlist
    either: the collector checks only that the file exists, load_watchlist
    applies no date test, and vintage never mentions it. The sharpest case is
    the morning that missed both jobs, where the same 07:25 pass restarted the
    dead collector onto yesterday's names while declining to refresh them.
    """
    from ops import monitor_jobs

    def one_pass(now, answer):
        launched: list[str] = []
        real_query, real_launch = monitor_jobs.query_task, monitor_jobs.launch_bat
        monitor_jobs.query_task = lambda name: dict(answer)
        monitor_jobs.launch_bat = lambda bat, dry: launched.append(bat)
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                monitor_jobs.check_all(now, dry_run=True)
        finally:
            monitor_jobs.query_task = real_query
            monitor_jobs.launch_bat = real_launch
        return launched, printed.getvalue()

    with conftest_activate():
        day = ettime.today_str()
        previous = (ettime.now_et().date() - dt.timedelta(days=1)).isoformat()
        config.WATCHLIST_PATH.write_text(
            json.dumps({"generated_at": f"{previous}T07:15:00-04:00", "symbols": []}),
            encoding="utf-8")
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        subscriptions = config.PREMARKET_DIR / f"{day}-subscriptions.json"
        subscriptions.unlink(missing_ok=True)
        # The both-missed morning: no discover log, no bars, nothing listening.
        for name in (f"{day}.jsonl", f"{day}-stats.jsonl"):
            (config.PREMARKET_DIR / name).unlink(missing_ok=True)
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (config.LOGS_DIR / f"discover-{day}.log").unlink(missing_ok=True)
        (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")

        asleep = {"exists": True, "status": "Ready",
                  "last_run": None, "last_result": "1"}

        # Every one of these is at or past the collector start, which is where
        # the old clock guard could not fire at any value.
        passes = []
        for clock in ((7, 25), (8, 25), (9, 5)):
            now = ettime.now_et().replace(hour=clock[0], minute=clock[1],
                                          second=0, microsecond=0)
            passes.append((clock,) + one_pass(now, asleep))
        for clock, launched, printed in passes:
            if "job_discover.bat" not in launched:
                failures.append(
                    f"a watchlist from {previous} did not rerun discover at "
                    f"{clock[0]:02d}:{clock[1]:02d}; the pass launched "
                    f"{launched or 'nothing'}")
        # The 07:25 pass is the both-missed morning, and the collector must not
        # be started in it: it would read the watchlist the rerun above is
        # replacing and hold those names for the whole window.
        if "job_collector.bat" in passes[0][1]:
            failures.append(
                "the collector was started in the same pass that relaunched "
                "discover, so it reads the watchlist being replaced")

        # Once the collector has written its subscription list there is
        # something to desync, and the pass says so rather than rewriting.
        subscriptions.write_text(json.dumps({"symbols": []}), encoding="utf-8")
        (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
        now = ettime.now_et().replace(hour=8, minute=25, second=0, microsecond=0)
        launched, printed = one_pass(now, asleep)
        if "job_discover.bat" in launched:
            failures.append("discover was rerun after the collector had written "
                            "its subscription list, which desyncs the watchlist "
                            "from what is actually being listened to")
        if "desync" not in printed:
            failures.append("the pass declined to rewrite the watchlist without "
                            f"saying why: {printed!r}")

        # A watchlist that IS today's is not a reason to rewrite it.
        subscriptions.unlink(missing_ok=True)
        config.WATCHLIST_PATH.write_text(
            json.dumps({"generated_at": f"{day}T07:15:00-04:00", "symbols": []}),
            encoding="utf-8")
        if monitor_jobs._watchlist_vintage(day)[0]:
            failures.append("today's own watchlist was read as a previous "
                            "session's, so discover would be rerun every pass")
    print("  discover     a watchlist from a previous session reruns discover "
          "at any hour, and the collector waits for the new one")

# -------------------------------------------------------- the 2026-08-20 review: the night

def claim_an_empty_bulk_day_is_not_an_empty_market(failures: list[str]) -> None:
    """A 200 carrying no rows is a failed fetch, not a session where nothing moved.

    prior_session_movers checked only the error slot of its two bulk end of day
    calls, so an empty array left prior_by empty and the source was filed
    FETCHED_EMPTY, this module's own wording for a source that succeeded with
    nothing. Nothing acts on that status: the gaps_to_fill loop, the empty pool
    gap and main's job_status.failed are all keyed on NOT_FETCHED, so the run
    exited 0 and was recorded ok. That source supplied 364 of the 628 pool names
    on 2026-08-20, and an empty closes map additionally strips pool_prior_close
    from every subscribed name and writes universe-closes-<date>.json with c1
    null on every row while still advertising names_with_at_least_one_close
    2,754 and third_session_available true.
    """
    from core import eodhd
    from selection import discover

    class _Bulk:
        """Records the days asked for. One assertion is about a call NOT made."""

        def __init__(self, empty_on: set[Any], rich_on: Any = None) -> None:
            self.empty_on = empty_on
            self.rich_on = rich_on
            self.days: list[Any] = []

        def eod_bulk_last_day(self, exchange="US", day=None, symbols=None,
                              extended=False):
            self.days.append(day)
            if day in self.empty_on:
                return eodhd.ApiResult([], None)
            close = 11.0 if day == self.rich_on else 10.0
            return eodhd.ApiResult(
                [{"code": "AAA", "close": close, "date": day.isoformat(),
                  "volume": 1_000_000}], None)

    with conftest_activate() as _sandbox:
        from morning import vintage

        today = ettime.today_et()
        prior = vintage.previous_trading_session(today)
        before = vintage.previous_trading_session(prior) if prior else None
        if prior is None or before is None:
            failures.append("the sandbox exchange calendar could not name the two "
                            "prior sessions, so this claim cannot run at all")
            return

        # The prior session comes back empty. previous_trading_session has
        # already had the calendar say that day was open, so this is the vendor
        # failing and the source must be NOT_FETCHED, which is the only status
        # anything downstream reads.
        api = _Bulk({prior}, rich_on=prior)
        source = discover.prior_session_movers(api, {"AAA.US"}, {}, today)
        if source["status"] != discover.NOT_FETCHED:
            failures.append(
                f"an empty prior session payload was filed {source['status']!r}, "
                "not not_fetched, so gaps_to_fill and job_status.failed never see it")
        if prior.isoformat() not in (source.get("error") or ""):
            failures.append(f"the recorded reason does not name the session that "
                            f"came back empty: {source.get('error')!r}")
        if api.days != [prior]:
            failures.append(f"the earlier session bulk was bought anyway after the "
                            f"prior one answered with nothing: {api.days!r}")

        # And the second call, which is the same defect one line down.
        api = _Bulk({before}, rich_on=prior)
        source = discover.prior_session_movers(api, {"AAA.US"}, {}, today)
        if source["status"] != discover.NOT_FETCHED:
            failures.append(f"an empty EARLIER session payload was filed "
                            f"{source['status']!r}, not not_fetched")

        # An ordinary morning is untouched, or the guard has eaten the source.
        # Redirected because this path reaches write_universe_closes, which
        # narrates the sidecar it writes.
        api = _Bulk(set(), rich_on=prior)
        with contextlib.redirect_stdout(io.StringIO()):
            source = discover.prior_session_movers(api, {"AAA.US"}, {}, today)
        if source["status"] != discover.FETCHED:
            failures.append(f"a real pair of bulk payloads came back "
                            f"{source['status']!r}, expected fetched")

        # The closes sidecar, whose denominators have to survive the same thing.
        # It takes the first two session maps as arguments and buys only the
        # third, which is the session before `before`.
        third = vintage.previous_trading_session(before)
        if third is None:
            failures.append("the sandbox calendar could not name the third "
                            "session, so the sidecar half of this claim is blind")
            return
        prior_by = {"AAA.US": {"code": "AAA", "close": 11.0}}
        before_by = {"AAA.US": {"code": "AAA", "close": 10.0},
                     "BBB.US": {"code": "BBB", "close": 9.0}}
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            payload = discover.write_universe_closes(
                _Bulk({third}), {"AAA.US", "BBB.US"}, prior_by, before_by,
                prior, before, today)
        said = printed.getvalue()
        if "no rows" not in said or "two session leg is absent" not in said:
            failures.append("an empty third session bulk payload was passed over "
                            f"without a word: {said.strip()[:160]!r}")
        if payload.get("names_with_close") != {"c1": 1, "c2": 2, "c3": 0}:
            failures.append(
                f"the closes file reports names_with_close "
                f"{payload.get('names_with_close')!r}, expected c1 1, c2 2, c3 0. "
                "names_with_at_least_one_close cannot tell a file whose c1 column "
                "is null on every row from a complete one.")
        if payload.get("names_with_both_closes_for_leg") != {
                "prior_session": 1, "two_session": 0}:
            failures.append(
                "the closes file does not say how many names carry both of the "
                "closes each leg needs: "
                f"{payload.get('names_with_both_closes_for_leg')!r}")
        if payload.get("names_with_at_least_one_close") != 2:
            failures.append("the old denominator changed meaning, which is not "
                            "the fix: it is still 'at least one'")
    print("  empty bulk   an empty bulk day is not_fetched with the date named, "
          "and the closes file counts each session")

def claim_recall_never_publishes_an_unknown_as_a_zero(failures: list[str]) -> None:
    """pool_recall writes nothing rather than a measured total failure.

    Two paths recorded missing evidence as measured zeros, both of them on disk
    in runs/2026-08-20/pool_recall.json, stamped 07:01:18. build() defaults the
    session to today and tasks/register_tasks.ps1 registers job_nightly.bat a
    second time at 07:00 with no --date, so the step asked the vendor for
    today's end of day bars before today's session had opened, an empty list is
    not an error, and it wrote gapped 0, addressable 0, pool_held 0, missed [].
    Separately published_symbols returned an empty set for both the missing and
    the unreadable packet, and measure() collapsed that unknown with
    `published = published or set()`, publishing published_gappers 0 and
    recall_addressable 0.0 against a real denominator. _rate's own docstring
    argues the opposite case for the denominator and nobody applied it to the
    numerator.
    """
    from core import eodhd
    from night import pool_recall
    from selection import discover, universe

    class _Api:
        def __init__(self, today_rows: list[dict[str, Any]]) -> None:
            self.today_rows = today_rows

        def eod_bulk_last_day(self, exchange="US", day=None, symbols=None,
                              extended=False):
            if day == ettime.today_et():
                return eodhd.ApiResult(self.today_rows, None)
            return eodhd.ApiResult(
                [{"code": "GAPPER", "open": 10.0, "close": 10.0, "volume": 900.0}],
                None)

    with conftest_activate() as _sandbox:
        # The sandbox is a copy of the real runs/, which already holds the
        # artifact this defect wrote. Removing it first is what makes the
        # "nothing was written" assertion below say anything.
        written = config.RUNS_DIR / ettime.today_str() / "pool_recall.json"
        written.unlink(missing_ok=True)

        saved = (eodhd.client, universe.load_universe, discover.load_watchlist)
        eodhd.client = lambda: _Api([])
        universe.load_universe = lambda require_fresh=True: {
            "symbols": [{"symbol": "GAPPER.US", "market_cap": 2_000_000_000}]}
        discover.load_watchlist = lambda: {"generated_at": None, "symbols": []}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pool_recall.build(write=True)
        except RuntimeError as exc:
            if "no rows" not in str(exc):
                failures.append(f"the refusal does not say what was wrong: {exc}")
            if "07:00" not in str(exc):
                failures.append("the refusal does not name the 07:00 catchup "
                                f"invocation that produces it: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"an empty bulk day raised {type(exc).__name__}: {exc}")
        else:
            failures.append("an empty bulk day was measured anyway and a payload "
                            "of zeros was written")
        finally:
            eodhd.client, universe.load_universe, discover.load_watchlist = saved
        if written.is_file():
            failures.append(f"{written} was written from an empty bulk day")

        # The packet nobody can read. An empty set is a measurement and this is
        # not one.
        missing, reason = pool_recall.published_symbols("2026-01-02")
        if missing is not None:
            failures.append(f"a missing packet published {missing!r} instead of "
                            "None, which is what an unknown looks like")
        if not reason:
            failures.append("a missing packet came back with no reason")

    gappers = {f"G{n}.US": {"symbol": f"G{n}.US", "gap_at_open_pct": 5.0,
                            "open": 10.0, "prior_close": 9.5, "volume": 1e6}
               for n in range(4)}
    addressable = {"G0.US": gappers["G0.US"], "G1.US": gappers["G1.US"]}
    pool_rows = [{"symbol": "G0.US", "pool_source": ["news"], "pool_tier": 2,
                  "pool_rank": 1, "subscribed": True}]

    unknown = pool_recall.measure(gappers, pool_rows, addressable, None,
                                  published_reason="no packet.json for 2026-08-20")
    for key in ("published_gappers", "published_addressable_gappers",
                "recall_addressable", "recall_all_gappers"):
        if unknown[key] is not None:
            failures.append(f"{key} came back {unknown[key]!r} for a session whose "
                            "packet could not be read, expected null")
    if not unknown["published_unknown_reason"]:
        failures.append("the null counts carry no reason beside them")
    # The measurements that never read the packet must survive it.
    if unknown["discovery_recall_addressable"] != 0.5 or unknown["pool_held"] != 1:
        failures.append("nulling the published counts also nulled the discovery "
                        f"ones: {unknown['discovery_recall_addressable']!r}")

    # A report that really did publish nothing is a different fact and still 0.
    nothing = pool_recall.measure(gappers, pool_rows, addressable, set())
    if nothing["published_gappers"] != 0 or nothing["recall_addressable"] != 0.0:
        failures.append("a report that published nothing no longer reads as zero: "
                        f"{nothing['published_gappers']!r}, "
                        f"{nothing['recall_addressable']!r}")
    if nothing["published_unknown_reason"] is not None:
        failures.append("a known empty publication was labelled unknown")
    print("  recall null  an empty bulk day refuses and an unreadable packet "
          "nulls every published count, with a measured zero still zero")

def claim_outcomes_refuse_a_split_they_cannot_measure_across(failures: list[str]) -> None:
    """A corporate action on D+1 leaves the row null instead of a fake excursion.

    mfe_pct, mae_pct and pm_high_broke_next_day subtract entry_ref, stop_ref and
    pm_high, the collector's raw live premarket levels from the pick date, from
    the high and low of the D+1 end of day bar. Retro-adjustment rewrites only
    bars dated BEFORE the ex date, so the D+1 bar is post event under either
    vendor convention, and a 4-for-1 forward split wrote mfe_pct and mae_pct
    near -75 percent with pm_high_broke_next_day 0, unflagged and
    indistinguishable from a real excursion, into the table CRITERIA.md says its
    seed thresholds will be recalibrated against. A 1-for-10 reverse split lands
    near +900 percent and the screen's price floor is only "> 3".
    """
    from core import criteria, eodhd, store
    from night import fill_outcomes

    pick_date, next_date = "2026-07-13", "2026-07-14"
    calendar = ["2026-07-10", pick_date, next_date, "2026-07-15", "2026-07-16",
                "2026-07-17", "2026-07-20"]
    calendar_symbol = criteria.load().text("universe", "session_calendar_symbol")

    def _bars(split: bool) -> list[dict[str, Any]]:
        """A ten dollar name, with a 4-for-1 split whose ex date is D+1.

        The vendor's shape: close is what printed that day, and adjusted_close
        is rewritten on the bars BEFORE the ex date and left alone from it on,
        so close over adjusted_close steps exactly once, at the ex date.
        """
        out = []
        for day in calendar:
            raw = 2.5 if (split and day >= next_date) else 10.0
            out.append({"date": day, "open": raw, "high": raw * 1.1,
                        "low": raw * 0.9, "close": raw,
                        "adjusted_close": 2.5 if split else 10.0,
                        "volume": 1_000_000})
        return out

    class _Api:
        def __init__(self, split: bool) -> None:
            self.split = split

        def eod(self, symbol, start=None, end=None, period="d"):
            if symbol == calendar_symbol:
                return eodhd.ApiResult([{"date": d} for d in calendar], None)
            return eodhd.ApiResult(_bars(self.split), None)

    def _run(split: bool) -> tuple[dict[str, Any], str]:
        with conftest_activate() as _sandbox:
            with store.session() as connection:
                store.init(connection)
                connection.execute(
                    "INSERT INTO picks (date, ticker, source, pm_high, entry_ref, "
                    "stop_ref) VALUES (?,?,?,?,?,?)",
                    (pick_date, "AAA.US", "live", 10.5, 10.5, 9.5))
                connection.commit()
            saved = eodhd.client
            eodhd.client = lambda: _Api(split)
            printed = io.StringIO()
            try:
                with contextlib.redirect_stdout(printed):
                    # day_limit keeps the sandbox copy's own live rows, which are
                    # dated later, out of this and off the stubbed feed.
                    fill_outcomes.fill(pick_date)
            finally:
                eodhd.client = saved
            with store.session() as connection:
                row = dict(connection.execute(
                    "SELECT next_day_close, mfe_pct, mae_pct, "
                    "pm_high_broke_next_day, day5_close FROM picks "
                    "WHERE date=? AND ticker=?", (pick_date, "AAA.US")).fetchone())
            return row, printed.getvalue()

    row, said = _run(split=True)
    for column in ("next_day_close", "mfe_pct", "mae_pct",
                   "pm_high_broke_next_day", "day5_close"):
        if row[column] is not None:
            failures.append(
                f"a 4-for-1 split on the session after the pick still wrote "
                f"{column} {row[column]!r}. The old code wrote mfe_pct -73.81 and "
                "mae_pct -76.32 here, which is the shape of a name that collapsed "
                "rather than one that split.")
    if "adjustment factor" not in said or "left alone" not in said:
        failures.append("the refused row was not explained: "
                        f"{said.strip()[:200]!r}")

    row, said = _run(split=False)
    if row["next_day_close"] is None or row["mfe_pct"] is None:
        failures.append("an ordinary session was refused as well, so the guard "
                        f"has stopped the fill rather than corrected it: {row!r}")
    elif abs(row["mfe_pct"] - 4.7619) > 0.001:
        failures.append(f"the ordinary excursion changed: mfe_pct {row['mfe_pct']!r}")
    print("  split units  a corporate action on D+1 leaves the row null with the "
          "reason recorded, and an ordinary session still fills")

def claim_an_unparsable_verification_is_not_a_measurement(failures: list[str]) -> None:
    """A corrupt verify_intraday.json reads as unmeasured, and the write is atomic.

    backfill decided a session had been measured with is_file(), while the only
    programmatic reader of that artifact, collect_premarket.latest_volume_check,
    skips any copy it cannot parse: "A half written or hand mangled summary is
    no measurement". The writer used Path.write_text, which truncates before it
    writes, when universe.write_atomically already existed for exactly this. A
    zero byte result then satisfied is_file() forever: unverified_sessions
    skipped that session every future night, _catchup_dates could not reach it
    because it only finds days with live picks rows whose pm_high_true is null,
    and no output named the file.
    """
    import inspect

    from night import backfill_premarket
    from collect import collect_premarket
    from selection import universe

    with conftest_activate() as _sandbox:
        # A collected session of this claim's own making, rather than whichever
        # archived one happens to be measured, so the claim keeps working after
        # runs/ is pruned. A day counts as collected only when the collector
        # wrote a subscription list for it, which is what tells a premarket run
        # from a bar file somebody produced by hand.
        limit = 50
        day = "2026-01-05"
        today = ettime.today_str()
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        (config.PREMARKET_DIR / f"{day}.jsonl").write_text(
            json.dumps({"symbol": "AAA.US", "minute_et": f"{day}T07:30:00-05:00",
                        "v": 1000.0}) + "\n", encoding="utf-8")
        collect_premarket.subscriptions_path(day).write_text(
            json.dumps({"symbols": ["AAA.US"]}), encoding="utf-8")

        target = config.RUNS_DIR / day / "verify_intraday.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        original = json.dumps({"day": day, "compared": 1, "within_one_percent": 0,
                               "median_abs_pct": 88.4}, indent=2).encode("utf-8")
        target.write_bytes(original)
        with contextlib.redirect_stdout(io.StringIO()):
            unverified = backfill_premarket.unverified_sessions(today, limit)
        if day in unverified:
            failures.append("a whole verification summary was not recognised as "
                            "one, so the fixture cannot demonstrate anything")

        # Exactly what an interrupted truncating write leaves behind.
        for label, content in (("zero byte", b""),
                               ("half written", original[:len(original) // 2])):
            target.write_bytes(content)
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                found = backfill_premarket.unverified_sessions(today, limit)
            if day not in found:
                failures.append(
                    f"a {label} verify_intraday.json for {day} still counts as a "
                    "measurement, so the sweep skips that session on every future "
                    "night and nothing ever measures it")
            if day not in printed.getvalue():
                failures.append(f"a {label} verify_intraday.json was passed over "
                                "without being named in any output")

        # A summary carrying keys this module has never seen must still count.
        # verify_against_intraday owns that schema and it is being widened.
        target.write_text(json.dumps({"day": day, "signed_median_pct": -88.49,
                                      "missing_from_collector": 3,
                                      "missing_from_vendor": 1}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            found = backfill_premarket.unverified_sessions(today, limit)
        if day in found:
            failures.append("a summary with a widened key set was called "
                            "unmeasured, which would re-measure every session "
                            "after the collector change")

        target.write_bytes(original)
        with contextlib.redirect_stdout(io.StringIO()):
            if day in backfill_premarket.unverified_sessions(today, limit):
                failures.append("the restored summary no longer reads as a "
                                "measurement")

    source = inspect.getsource(backfill_premarket.verify_volume)
    if "universe.write_atomically(summary, verify_path)" not in source:
        failures.append("verify_volume no longer writes through "
                        "universe.write_atomically, so an interruption truncates "
                        "the only record that a session was measured")
    if "os.replace" not in inspect.getsource(universe.write_atomically):
        failures.append("write_atomically stopped renaming into place")
    print("  verify parse a corrupt summary reads as unmeasured and is named, a "
          "widened one still counts, and the write renames into place")

# ------------------------------------------------------ the 2026-08-20 review: the harness

def claim_ensure_dirs_follows_a_redirected_config(failures: list[str]) -> None:
    """ensure_dirs creates the directories config names now, not at import.

    _ALL_DIRS was a tuple of Path objects built when config was imported.
    conftest.activate() rebinds config.DATA_DIR, PREMARKET_DIR, RUNS_DIR and
    LOGS_DIR and cannot rebind a tuple already built from them, so ensure_dirs
    was the one writer in the project a redirect could not reach: called from
    inside the sandbox, by store.connect() among others, it issued mkdir
    against the four REAL repository directories. No data followed it there,
    because every other writer reads the attribute at call time. What did
    follow was worse to diagnose. With the gitignored runs/ or logs/ cleared by
    hand, run_tests photographed the tree with them absent, the first
    store.connect() inside the sandbox created them for real, and the run
    failed its own whole-tree check on a created runs/ path: a breach caused by
    the harness and blamed on a test. test_entrypoints' ensure_dirs(), placed
    to materialise the SANDBOX directories, targeted the real tree too and did
    nothing for its stated purpose.
    """
    from tests import conftest

    watched = ("DATA_DIR", "PREMARKET_DIR", "RUNS_DIR", "LOGS_DIR")
    # PROJECT_ROOT is never redirected, so these are the real four whatever
    # sandbox this claim happens to be running inside.
    real = {config.PROJECT_ROOT / "data",
            config.PROJECT_ROOT / "data" / "premarket",
            config.PROJECT_ROOT / "runs",
            config.PROJECT_ROOT / "logs"}
    saved = {name: getattr(config, name) for name in watched}
    made: list[pathlib.Path] = []
    real_mkdir = pathlib.Path.mkdir

    def spy(self, *args, **kwargs):
        made.append(pathlib.Path(self))
        return real_mkdir(self, *args, **kwargs)

    try:
        with tempfile.TemporaryDirectory(prefix="pmd-dirs-") as raw:
            elsewhere = pathlib.Path(raw)
            config.DATA_DIR = elsewhere / "data"
            config.PREMARKET_DIR = elsewhere / "data" / "premarket"
            config.RUNS_DIR = elsewhere / "runs"
            config.LOGS_DIR = elsewhere / "logs"
            wanted = {getattr(config, name) for name in watched}

            pathlib.Path.mkdir = spy
            try:
                config.ensure_dirs()
            finally:
                pathlib.Path.mkdir = real_mkdir

            escaped = sorted(str(p) for p in set(made) & real)
            if escaped:
                failures.append(
                    "ensure_dirs mkdir'd the real repository directories while "
                    f"config pointed elsewhere: {escaped}")
            missing = sorted(str(p) for p in wanted - set(made))
            if missing:
                failures.append(
                    f"ensure_dirs did not create the redirected {missing}")
            unmade = sorted(str(p) for p in wanted if not p.is_dir())
            if unmade:
                failures.append(f"the redirected directories do not exist: {unmade}")
    finally:
        for name, value in saved.items():
            setattr(config, name, value)

    # Names, not paths, is what makes the redirect impossible to miss. A fifth
    # working directory added here that the sandbox does not rebind would
    # reintroduce the same class of escape, so the two lists are checked
    # against each other rather than trusted to stay in step.
    names = getattr(config, "_ALL_DIR_NAMES", None)
    if names is None:
        failures.append("config has no _ALL_DIR_NAMES, so ensure_dirs is walking "
                        "paths captured at import again")
    else:
        if set(names) != set(watched):
            failures.append(f"_ALL_DIR_NAMES is {sorted(names)}, expected "
                            f"{sorted(watched)}")
        unredirected = sorted(set(names) - set(conftest._CONFIG_PATHS))
        if unredirected:
            failures.append(f"ensure_dirs creates {unredirected}, which the test "
                            "sandbox does not rebind, so a sandboxed call would "
                            "create them in the real tree")
    print("  ensure dirs  a redirected config sends ensure_dirs to the redirected "
          "paths and never to the real tree")

# ------------------------------------------------------ the 2026-08-20 review: an instrument

def claim_a_refused_sweep_is_not_an_empty_feed(failures: list[str]) -> None:
    """A sweep nobody answered is reported as refused, not as an empty feed.

    probe_alpaca_live.sample() recorded its per chunk failures into
    record["errors"] and nothing downstream read that key, so a sweep whose
    every request came back 403 printed a zero active count and no lag,
    identical to a sweep that was answered and had nothing in it. write_table
    then reached for the reading written for the second case and printed "the
    free tier does not serve this session live".

    That is what the whole of 2026-08-17 was: 23 sweeps, 46 requests, every one
    refused with status 403 because the free tier will not serve the sip feed
    for a window ending at the wall clock. Nothing was ever served, so the
    emptiness measured nothing, and DECISIONS.md closed Alpaca as a live source
    on it. The conclusion survived the correction; the measurement did not.

    The refused fixture carries no served or refused counts, because that is
    the shape of the records already on disk: the fix has to read the old log,
    not only the new one.
    """
    from research import probe_alpaca_live as probe

    def sweep(clock: str, **extra: Any) -> dict[str, Any]:
        record = {
            "taken_at_et": f"2026-08-17T{clock}-04:00",
            "window": {"start": "2026-08-17T08:00:00Z", "end": "2026-08-17T11:30:00Z"},
            "symbols_requested": 2745,
            "symbols_with_bars": 0,
            "bars_total": 0,
            "newest_bar_et": None,
            "lag_minutes_newest": None,
            "lag_minutes_median": None,
            "gappers_over_3pct": 0,
            "top_gappers": [],
        }
        record.update(extra)
        return record

    refused = [sweep("07:30:00", errors=["chunk at 0: status 403",
                                         "chunk at 2000: status 403"]),
               sweep("07:35:00", errors=["chunk at 0: status 403",
                                         "chunk at 2000: status 403"])]
    served = [sweep("07:30:00", errors=[], requests_served=2, requests_refused=0,
                    refusal_status_codes=[]),
              sweep("07:35:00", errors=[], requests_served=2, requests_refused=0,
                    refusal_status_codes=[])]

    counted = getattr(probe, "sweep_requests", None)
    if counted is None:
        failures.append("the probe cannot count a sweep's served and refused "
                        "requests at all, so a refusal is invisible to the table")
    else:
        got = counted(refused[0])
        if (got["served"], got["refused"], got["codes"]) != (0, 2, [403]):
            failures.append(f"a wholly refused sweep counted as {got}, expected "
                            "0 served, 2 refused, status 403")

    with conftest_activate():
        refused_text = probe.write_table(refused, "2026-08-17").read_text(encoding="utf-8")
        served_text = probe.write_table(served, "2026-08-18").read_text(encoding="utf-8")

    if "403" not in refused_text:
        failures.append("the table for a wholly refused run never names the status "
                        "code every request came back with")
    if "were refused" not in refused_text:
        failures.append("the table for a wholly refused run does not say the "
                        "requests were refused")
    if "does not serve this session live" in refused_text:
        failures.append("the table read a refused sweep as an empty feed, which is "
                        "the 2026-08-17 misreport")
    if "| 0 | 2 | 403 |" not in refused_text:
        failures.append("the per sweep row does not carry served, refused and the "
                        "status code beside the zeros")

    # The reading the prose was written for is kept for the case it fits.
    if "does not serve this session live" not in served_text:
        failures.append("a sweep that WAS served and came back empty lost the "
                        "reading the prose was written for")
    if "403" in served_text:
        failures.append("a sweep with no refusals reported a refusal code anyway")
    if "WAS REFUSED" in served_text:
        failures.append("a sweep with no refusals carried the refusal banner")
    print("  alpaca probe  a sweep refused on every request reports as refused, "
          "and a served empty sweep keeps its original reading")

# ------------------------------------------------------- the 2026-08-20 review: the house rules

# The character and the entity this claim hunts for, spelled so that they do
# not appear literally in this file. A guard whose own source trips it is the
# shape already recorded on 2026-08-16, when the quantifier guard flagged the
# documents that describe it, and the answer there was the same: build the
# needle rather than write it.
_EM_DASH = chr(0x2014)
_EM_DASH_ENTITY = "&" + "mdash;"


def claim_no_em_dash_survives_anywhere(failures: list[str]) -> None:
    """Hard rule 4 is guarded by something other than good intentions.

    "No em dashes in code, comments, strings, or docs" is rule 4 of
    BUILD_PLAN.md's hard rules. It was enforced on the MODEL, through
    prompt_analyst.md rule 11 and the containment suite, and on nothing else.
    The 2026-08-20 review counted fifteen survivors in the repository's own
    text: three in Python at job_status.py, discover.py and gap_stats.py,
    eight in CHANGELOG.md and DECISIONS.md, and four written as an HTML entity
    on the two architecture pages, which render as em dashes on a page the
    owner reads.

    The entity is the half worth naming. Grepping the source for the character
    would never have found those four, and they were the ones a reader
    actually saw. So this walks the tracked tree for both spellings.

    A rule with no guard is a preference. This is the guard.
    """
    import subprocess

    root = config.PROJECT_ROOT
    # --no-optional-locks for the reason differences() records: git refreshes
    # and rewrites .git/index on an ordinary read, the tree photograph sees
    # the mtime move, and the suite fails on a file the check itself caused to
    # change. build_identifier() learned this on 2026-08-14 and this claim
    # reproduced it on the first full run after it was written.
    listing = subprocess.run(["git", "--no-optional-locks", "ls-files"],
                             cwd=str(root), capture_output=True, text=True)
    if listing.returncode != 0:
        failures.append("git ls-files failed, so the tree could not be walked: "
                        f"{listing.stderr.strip()[:200]}")
        return

    tracked = [name for name in listing.stdout.splitlines() if name.strip()]
    if len(tracked) < 50:
        failures.append(f"git ls-files returned only {len(tracked)} paths, which "
                        "is too few to be the whole tree; the walk proved nothing")
        return

    offences: list[str] = []
    for name in tracked:
        try:
            text = (root / name).read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue  # a binary or unreadable file carries no prose to check
        for number, line in enumerate(text.splitlines(), 1):
            if _EM_DASH in line:
                offences.append(f"{name}:{number} carries an em dash")
            if _EM_DASH_ENTITY in line:
                offences.append(f"{name}:{number} carries the entity, "
                                "which renders as one")

    if offences:
        shown = "; ".join(offences[:8])
        more = f", and {len(offences) - 8} more" if len(offences) > 8 else ""
        failures.append(f"hard rule 4 is broken in {len(offences)} "
                        f"place(s): {shown}{more}")

    # The needles have to be the real ones, or this is a walk over nothing that
    # passes because it can never match. This file is itself in the walk, so a
    # literal here would fail the claim: that is the point of building them.
    if _EM_DASH != "\N{EM DASH}" or _EM_DASH_ENTITY != "&mdash" + ";":
        failures.append("the needles are not an em dash and its entity, so the "
                        "walk above cannot detect either")
    if len(_EM_DASH) != 1 or ord(_EM_DASH) != 8212:
        failures.append(f"the em dash needle is {_EM_DASH!r}, not U+2014")

    print(f"  house rule  no em dash and no entity spelling anywhere in "
          f"{len(tracked)} tracked files")


# ---------------------------------------------------------------- plumbing

def conftest_activate():
    from tests import conftest

    return conftest.activate()


def main() -> int:
    failures: list[str] = []
    claim_the_november_transition(failures)
    claim_economic_events_are_converted_not_relabelled(failures)
    claim_a_thinner_rerun_stands_down(failures)
    claim_an_empty_packet_is_not_a_failed_step(failures)
    claim_delivery_happens_once(failures)
    claim_replay_is_counted_once(failures)
    claim_a_failed_write_holds_its_minutes(failures)
    claim_outcomes_refuse_a_pick_the_calendar_cannot_date(failures)
    claim_a_missing_exchange_refuses_the_build(failures)
    claim_the_watchlist_is_written_atomically(failures)
    claim_the_stdev_window_is_its_own_name(failures)
    claim_the_watchdog_survives_a_hung_schtasks(failures)
    claim_the_baseline_counts_what_it_warmed(failures)
    claim_vendor_text_cannot_break_a_table(failures)
    claim_the_quantifier_guard_reads_headings(failures)
    claim_no_comment_describes_a_helper_that_does_not_exist(failures)
    claim_the_volume_check_reaches_the_packet(failures)
    claim_a_trap_is_the_balance_not_the_worst_headline(failures)
    claim_the_day_screen_names_what_rvol_alone_blocked(failures)
    claim_a_truncated_name_is_not_a_rejected_one(failures)
    claim_the_bucket_roll_is_complete_and_signed(failures)
    claim_an_unmeasured_condition_is_not_a_failed_one(failures)
    claim_a_thin_window_is_not_merely_a_late_one(failures)
    claim_a_replayed_print_is_not_silence(failures)
    claim_the_two_prior_closes_are_compared(failures)
    claim_the_baseline_age_travels_with_the_rvol(failures)
    claim_a_hand_run_of_one_suite_cannot_touch_real_data(failures)

    claim_an_abbreviation_is_not_a_ticker_claim(failures)
    claim_the_two_documents_agree_on_who_decides_a_trap(failures)
    claim_a_roundup_classifies_nobody(failures)
    claim_the_trap_balance_reads_the_whole_window(failures)
    claim_the_volume_check_carries_its_sign(failures)
    claim_a_skipped_quote_is_not_a_missing_float(failures)
    claim_a_missing_calendar_stands_the_vintage_gate_down(failures)
    claim_the_previous_session_helper_says_when_it_does_not_know(failures)
    claim_a_live_job_is_not_rerun_on_top_of_itself(failures)
    claim_a_previous_session_watchlist_reruns_discover(failures)
    claim_an_empty_bulk_day_is_not_an_empty_market(failures)
    claim_recall_never_publishes_an_unknown_as_a_zero(failures)
    claim_outcomes_refuse_a_split_they_cannot_measure_across(failures)
    claim_an_unparsable_verification_is_not_a_measurement(failures)
    claim_ensure_dirs_follows_a_redirected_config(failures)
    claim_a_refused_sweep_is_not_an_empty_feed(failures)
    claim_no_em_dash_survives_anywhere(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  every defect the 2026-08-20 audit confirmed is still fixed")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
