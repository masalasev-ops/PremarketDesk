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

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  every defect the 2026-08-20 audit confirmed is still fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
