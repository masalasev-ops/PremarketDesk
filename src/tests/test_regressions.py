"""One claim per defect found by the 2026-08-20 audit, so none of them returns.

An adversarial read of the whole scheduled path raised forty findings and
twenty survived independent verification, which is what this file started as:
sixteen claims. Three further reads of the same tree that same day, the report
audit, the nine smaller findings and the nineteen of the full review, added the
rest, arming the socket cap probe for 2026-08-21 added another, and the
2026-08-22 read added the three non atomic writes that could reopen a closed
defect or lose a session, the archive publishing a fixture as a morning, and a
read that created the directory it was reading, and six from a twelve reader
review, three in the collector and three in the night. It now carries eighty
seven claims, a count read off the file rather
than remembered, because it said forty four for a while after it held fifty
seven and a suite that miscounts itself is the first thing a reader stops
trusting.

They have nothing in common except how they were found, which is why they are
grouped by that rather than scattered across the themed suites: a reader asking
"what did those reads actually catch" gets one file, and a reader asking "is it
still caught" runs it.

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
from tests import conftest


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

def claim_a_briefing_gain_does_not_cancel_a_screen_loss(
        failures: list[str]) -> None:
    """A rerun that fills the briefing while the screen empties still stands down.

    thinner_than returns early on ANY axis where the rerun gained, on the
    reasoning that a rerun which knows more somewhere is a different and better
    morning rather than a degraded copy. That reasoning held while every axis
    was candidate derived: a rerun that priced more names also scored more of
    them, so a gain on one really was evidence the whole morning improved.

    Layer 4 added notable_rows on 2026-08-20 and broke the premise without
    touching the function. The section reads the closes sidecar and the
    universe file, neither of which the watchlist touches, so it can fill while
    every candidate axis collapses. Measured against the real 2026-08-20
    packet: a rerun that lost every price, every RVOL and every score and
    published ten notable rows came back NOT THINNER, so it would have
    overwritten the 08:45 packet and then upserted nulls over live picks rows
    as source='live'. The guard's own docstring names that as the harm it
    exists to prevent.

    The axis is kept, because a rerun that LOSES the whole section must still
    be seen as thinner. It is excluded from the cancelling set instead.
    """
    from morning import scan

    prior = {"candidates": 12, "priced": 12, "with_rvol": 10, "scored": 12,
             "notable_rows": 0}

    gutted = {"candidates": 12, "priced": 0, "with_rvol": 0, "scored": 0,
              "notable_rows": 10}
    thin = scan.thinner_than(gutted, prior)
    for axis in ("priced", "with_rvol", "scored"):
        if axis not in thin:
            failures.append(
                f"a rerun that lost every {axis} and gained ten notable rows is "
                f"not reported as thinner on {axis}: {thin}. It would overwrite "
                "the packet and upsert nulls over live picks rows.")

    # A genuine improvement is still not thinner, or the guard refuses good work.
    better = {"candidates": 14, "priced": 14, "with_rvol": 12, "scored": 14,
              "notable_rows": 0}
    if scan.thinner_than(better, prior):
        failures.append("a rerun that priced and scored more names is being "
                        f"called thinner: {scan.thinner_than(better, prior)}")

    # And losing the section is still a loss, which is why the axis exists.
    was_full = dict(prior, notable_rows=10)
    lost = dict(prior, notable_rows=0)
    if "notable_rows" not in scan.thinner_than(lost, was_full):
        failures.append("a rerun that lost the whole notable section is not "
                        "thinner on notable_rows, so the axis buys nothing")

    # The mixed case the early return is actually for: a candidate gain does
    # cancel, because those axes move together.
    mixed = {"candidates": 13, "priced": 11, "with_rvol": 10, "scored": 12,
             "notable_rows": 0}
    if scan.thinner_than(mixed, prior):
        failures.append("a rerun carrying one more candidate and one fewer "
                        "priced is being called thinner, so the early return "
                        "no longer works for the axes it was written for")

    print("  cancelling   a briefing gain cancels no screen loss, a candidate "
          "gain still cancels, and losing the section is still a loss")


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

        # THE ROUTE THE THREE CASES ABOVE DO NOT COVER, and the one this
        # machine actually produces. All three ask what happens with a record
        # present, absent or corrupt. None asks what happens when WRITING it
        # fails, and a plain write_text raised straight out of deliver(): the
        # email had gone, the chain stopped before build_archive wrote its
        # finish marker, the watchdog read an unfinished chain and relaunched
        # it, and the recipients got the morning twice. README records the
        # antivirus denying a first file write, so this needs no exotic fault.
        record.unlink(missing_ok=True)
        real_write = pathlib.Path.write_text

        def deny_the_record(self, *args, **kwargs):
            if self.name.startswith("delivered.json"):
                raise PermissionError(13, "Permission denied", str(self))
            return real_write(self, *args, **kwargs)

        posted: list[str] = []

        class _Response:
            status_code = 200
            text = '{"id": "re_stub"}'

            def json(self) -> dict[str, str]:
                return {"id": "re_stub"}

        class _Session:
            def post(self, url: str, **kwargs: Any) -> "_Response":
                posted.append(url)
                return _Response()

        from core import eodhd
        from ops import job_status

        real_session = eodhd.build_session
        real_key, real_to = config.resend_api_key, config.email_to
        real_failed = job_status.failed
        declared: list[str] = []
        eodhd.build_session = lambda *a, **k: _Session()
        config.resend_api_key = lambda: "re_test_key"
        config.email_to = lambda: ["someone@example.invalid"]
        job_status.failed = lambda message: declared.append(message)
        pathlib.Path.write_text = deny_the_record
        try:
            printed = io.StringIO()
            try:
                with contextlib.redirect_stdout(printed):
                    code = deliver.deliver(html)
            except BaseException as exc:
                code = None
                failures.append(
                    f"a denied send-once write raised {type(exc).__name__} out of "
                    "deliver(); the chain then stops before its finish marker and "
                    "the watchdog sends the morning a second time")
            text = printed.getvalue()
        finally:
            pathlib.Path.write_text = real_write
            eodhd.build_session = real_session
            config.resend_api_key, config.email_to = real_key, real_to
            job_status.failed = real_failed

        if code is not None and code != 0:
            failures.append(f"a denied send-once write returned {code}; a nonzero "
                            "exit stops the chain short of its finish marker, "
                            "which is what summons the second copy")
        if len(posted) != 1:
            failures.append(f"the denied-write case posted {len(posted)} emails, "
                            "expected exactly 1")
        if "WARNING the email WAS SENT" not in text:
            failures.append("a send whose record could not be written said nothing "
                            f"a reader would notice: {text.strip()[:160]!r}")
        if not declared:
            failures.append("a send whose record could not be written did not "
                            "declare the step failed, so the status trail reads "
                            "as an ordinary morning")
        if list(html.parent.glob("delivered.json.partial")):
            failures.append("a failed send-once write left its temporary sibling "
                            "behind")
    print("  send once    a delivered session is not re-sent, a corrupt record "
          "cannot suppress one, and a record that cannot be written warns "
          "instead of summoning a second copy")


def claim_a_half_written_calendar_is_not_a_missing_one(failures: list[str]) -> None:
    """An interrupted calendar refresh leaves the old holiday list standing.

    get_details' own docstring promises it: "The refresh used to delete the
    cache first and then fetch, which turned one 22:15 vendor outage into no
    holiday list at all ... The old file now stands until a new one is actually
    in hand." The delete-before-fetch was closed on 2026-08-20. The write beside
    it was not, and Path.write_text truncates the destination BEFORE it writes,
    so a refresh interrupted between the open and the flush leaves a file that
    parses as nothing.

    That is the same outcome the fix was for, by a shorter route. _load_cache
    answers a truncated file and a missing one identically, both None, and this
    module's whole failure direction is that no calendar reads as open: with the
    cache gone, is_trading_day returns True for Christmas Day and every weekday
    job runs the full pipeline against a closed market.

    The fault is installed the way a reboot, a full disk or a denied write
    produces it, by opening the destination and then dying, rather than by
    making the write raise before it touches anything. A write that never opens
    the file was never the shape of this failure.
    """
    from ops import market_today

    calendar = {
        "ExchangeHolidays": {"1": {"Date": "2026-12-25", "Holiday": "Christmas"}},
        "TradingHours": {"WorkingDays": "Mon,Tue,Wed,Thu,Fri"},
        "fetched_at": "2026-01-01T00:00:00-05:00",
    }

    def interrupted_write(target: pathlib.Path) -> None:
        """Open for writing, which truncates, then die partway through."""
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("{\"ExchangeHol")
            raise OSError(28, "No space left on device", str(target))

    with conftest_activate() as _sandbox:
        market_today.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        market_today.CACHE_PATH.write_text(json.dumps(calendar, indent=2),
                                           encoding="utf-8")

        # Drive the module's own writer, so the claim tracks the code rather
        # than a copy of it: a future rewrite of _write_cache_atomically is
        # caught here instead of passing against a re-implementation.
        real_write = pathlib.Path.write_text

        def die_on_the_cache(self, *args, **kwargs):
            if self.name.startswith("exchange-details.json"):
                return interrupted_write(self)
            return real_write(self, *args, **kwargs)

        pathlib.Path.write_text = die_on_the_cache
        try:
            market_today._write_cache_atomically(dict(calendar))
        except OSError:
            pass  # the caller sees it; what matters is what is left on disk
        finally:
            pathlib.Path.write_text = real_write

        market_today._MEMO.update({"details": None, "loaded": False})
        survived = market_today._load_cache()
        if survived is None:
            failures.append("an interrupted calendar refresh left no readable "
                            "holiday list; a truncated cache and a missing one "
                            "are the same thing to _load_cache, and a missing "
                            "one reads as open")
        elif not survived.get("ExchangeHolidays"):
            failures.append("an interrupted calendar refresh left a file that "
                            "parses and carries no holidays")

        trades, why = market_today.decide(survived, dt.date(2026, 12, 25))
        if trades is not False:
            failures.append(f"after an interrupted refresh Christmas Day reads "
                            f"as trades={trades} ({why}); every weekday job "
                            "would run against a closed market")

        leftover = sorted(p.name for p in market_today.CACHE_PATH.parent.glob(
            "exchange-details.json.partial*"))
        if leftover:
            failures.append(f"an interrupted calendar refresh left {leftover} "
                            "behind")
    print("  half calendar an interrupted refresh keeps the previous holiday "
          "list, and Christmas still reads as closed")


def claim_an_unrecorded_relaunch_is_reported_rather_than_raised(failures: list[str]) -> None:
    """A rerun the state file refused to record says so, and does not raise.

    _record_rerun is called AFTER launch_bat has already started the .bat, so
    its write is the one thing in the watchdog that cannot be answered by
    running the pass again: the job is up either way and only the count of it
    is at stake. _load_state already treats an unreadable state file as worth
    declaring the step failed, on the stated reasoning that a lost count stops
    max_reruns_per_job_per_day being enforced and lets a hard failure loop every
    thirty minutes. A failed WRITE leaves that same state, and until this it did
    so while raising through the rest of the pass, so the checks after it never
    ran.

    Both halves are asserted: the pass survives, and the reader is told the cap
    is off for that job rather than left to infer it from a count that silently
    stopped moving.
    """
    from ops import job_status
    from ops import monitor_jobs

    with conftest_activate() as _sandbox:
        monitor_jobs.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        monitor_jobs.STATE_PATH.unlink(missing_ok=True)

        real_write = pathlib.Path.write_text

        def deny_the_state(self, *args, **kwargs):
            if self.name.startswith("monitor-reruns.json"):
                raise PermissionError(13, "Permission denied", str(self))
            return real_write(self, *args, **kwargs)

        real_failed = job_status.failed
        declared: list[str] = []
        job_status.failed = lambda message: declared.append(message)
        pathlib.Path.write_text = deny_the_state
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                monitor_jobs._record_rerun("2026-08-22", "chain")
        except BaseException as exc:
            failures.append(f"a denied rerun-state write raised "
                            f"{type(exc).__name__} through the watchdog pass; "
                            "the job it had already launched stands and every "
                            "later check in that pass is skipped")
        finally:
            pathlib.Path.write_text = real_write
            job_status.failed = real_failed

        text = printed.getvalue()
        if "rerun cap is not being enforced" not in text:
            failures.append("a rerun that could not be recorded said nothing "
                            f"about the cap it just stopped enforcing: "
                            f"{text.strip()[:160]!r}")
        if not declared:
            failures.append("a rerun that could not be recorded did not declare "
                            "the watchdog step failed, so the status trail reads "
                            "as a clean pass")
        if list(monitor_jobs.STATE_PATH.parent.glob("monitor-reruns.json.partial")):
            failures.append("a failed rerun-state write left its temporary "
                            "sibling behind")

        # And the ordinary path still counts, so the guard above cannot be
        # satisfied by a writer that never writes.
        monitor_jobs._record_rerun("2026-08-22", "chain")
        if monitor_jobs._load_state("2026-08-22").get("chain") != 1:
            failures.append("an ordinary rerun was not counted, so the cap is "
                            "not enforced on the path that works either")
    print("  lost rerun   a rerun the state file refused is reported and the "
          "pass survives, and an ordinary one still counts")


def claim_an_interrupted_packet_write_leaves_no_half_packet(failures: list[str]) -> None:
    """The morning's evidence is never left half written.

    packet.json is one of the two files CRITERIA [Backup] says has no route
    back, and write_packet wrote it with a plain write_text, which truncates
    the destination before it writes. A run interrupted between the open and
    the flush left a packet that parses as nothing: analyst, render_report,
    verify_morning, the nightly backfill, the truth pass and pool_recall all
    read it, and _stands_down_from reads a corrupt one as "not thinner", so a
    later rerun overwrites the morning's evidence with a packet gathered off a
    different clock. The nightly backup answers this an hour too late.

    Installed the way a reboot, a full disk or a denied write produces it, by
    opening the destination and then dying. A write that never opens the file
    was never the shape of this failure.
    """
    from morning import scan

    day = "2026-08-22"
    good = {"session_date": day, "generated_at": "2026-08-22T08:45:00-04:00",
            "candidates": [{"symbol": "AAA.US", "gap_pct": 4.0}]}

    with conftest_activate() as _sandbox:
        first = scan.write_packet(dict(good))
        before = first.read_text(encoding="utf-8")

        real_write = pathlib.Path.write_text

        def die_partway(self, *args, **kwargs):
            if self.name.startswith("packet.json"):
                with open(self, "w", encoding="utf-8") as handle:
                    handle.write('{"session_da')
                    raise OSError(28, "No space left on device", str(self))
            return real_write(self, *args, **kwargs)

        pathlib.Path.write_text = die_partway
        try:
            scan.write_packet(dict(good, generated_at="2026-08-22T09:10:00-04:00"))
        except OSError:
            pass  # the caller sees it; what matters is what is left on disk
        finally:
            pathlib.Path.write_text = real_write

        after = first.read_text(encoding="utf-8")
        if after != before:
            failures.append("an interrupted packet write changed packet.json; "
                            "the morning's frozen evidence must survive a write "
                            "that did not complete")
        try:
            json.loads(after)
        except ValueError:
            failures.append("an interrupted packet write left a packet.json "
                            "that does not parse, which every later step reads "
                            "and _stands_down_from treats as not thinner")

        leftover = sorted(p.name for p in first.parent.glob("packet.json.partial*"))
        if leftover:
            failures.append(f"an interrupted packet write left {leftover} behind")

        # And the ordinary write still lands, so the guard cannot be satisfied
        # by a writer that never writes.
        scan.write_packet(dict(good, generated_at="2026-08-22T09:20:00-04:00"))
        landed = json.loads(first.read_text(encoding="utf-8"))
        if landed.get("generated_at") != "2026-08-22T09:20:00-04:00":
            failures.append("an ordinary packet write did not land, so the "
                            "atomic pair is not writing at all")
    print("  half packet  an interrupted packet write leaves the previous "
          "evidence intact, and an ordinary one still lands")


def claim_the_archive_does_not_publish_a_fixture_as_a_morning(failures: list[str]) -> None:
    """A session whose packet no build wrote is carried, and is labelled.

    On 2026-08-21 at 15:46 a sweep that invoked every claim directly wrote
    fixture data over that morning's packet, capture and report. The loss is
    recorded in three documents. What no document could do is stop
    site/PremarketDesk.html rendering the fixture as the seventh session,
    identical in the rail and in the pane to the six real ones: one candidate,
    AAPL at 100.00, gap +3.1 percent, RVOL 1.8, score 6.0 green, none of it
    measured from a market.

    The packet already carried the tell. config.build_identifier writes a
    resolved HEAD or null with a commit_reason, and never a third thing, so the
    "stub" that fixture wrote is a value no version of this code produces.
    Nothing read it.

    Labelled rather than dropped. A session removed from the archive leaves a
    gap in the rail that reads as a day the market was shut, and this file is
    the record: one that quietly omits what went wrong is the failure it exists
    to prevent.

    The two silences are asserted alongside, because the first draft of this
    guard reported them and accused 2026-08-13 and 2026-08-14, both real
    mornings written before the build field existed.
    """
    from night import build_archive

    packets = {
        "2026-08-21": {"build": {"commit": "stub", "dirty": False}},
        "2026-08-13": {"build": None},
        "2026-08-14": {},
        "2026-08-20": {"build": {"commit": "c" * 40, "dirty": False}},
        "2026-08-19": {"build": {"commit": None, "dirty": None,
                                 "commit_reason": "could not resolve HEAD"}},
    }
    expected_flagged = {"2026-08-21"}

    for date, packet in packets.items():
        reason = build_archive._fixture_reason(packet)
        if (reason is not None) != (date in expected_flagged):
            failures.append(
                f"{date} with build {packet.get('build')!r} was "
                f"{'flagged' if reason else 'passed'} and should have been "
                f"{'flagged' if date in expected_flagged else 'passed'}"
                + (f": {reason}" if reason else ""))

    with conftest_activate() as _sandbox:
        for date, packet in packets.items():
            run = config.run_dir(date)
            run.mkdir(parents=True, exist_ok=True)
            body = dict(packet)
            body["session_date"] = date
            body["candidates"] = [{"symbol": "AAA.US", "conviction": "green"}]
            (run / "packet.json").write_text(json.dumps(body), encoding="utf-8")
            (run / "report.md").write_text(f"# Premarket, {date}\n\nbody\n",
                                           encoding="utf-8")

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            # Embed everything. The sandbox carries the real tree's run
            # directories too, so a cap of len(packets) links the oldest of
            # these out instead of embedding them and the section ids below
            # would be missing for a reason that is not the one under test.
            out = build_archive.build(1000)
        page = out.read_text(encoding="utf-8")

        if "2026-08-21 is not a morning" not in page:
            failures.append("the archive rendered the destroyed session with no "
                            "label; a reader cannot tell it from the real ones")
        if page.count(">not a morning<") != 1:
            failures.append(f"the rail marked {page.count('>not a morning<')} "
                            "sessions, expected exactly 1")
        if "1 not a morning" not in page:
            failures.append("the archive subtitle did not count the labelled "
                            "session, so the fact is only visible inside the "
                            "day a reader happens to open")
        for date in packets:
            if f"day-{date}" not in page:
                failures.append(f"{date} was dropped from the archive; a gap in "
                                "the rail reads as a day the market was shut")
        if "2026-08-21" not in printed.getvalue():
            failures.append("the archive step said nothing in its log about "
                            "carrying a session that is not a morning")
    print("  not a morning a packet no build wrote is carried and labelled, and "
          "a packet written before the build field is not accused")


def claim_reading_a_run_directory_does_not_create_one(failures: list[str]) -> None:
    """Asking whether a session has a packet does not invent the session.

    config.run_dir mkdirs, which is right for a caller about to write and wrong
    for the thirteen that asked it for a path only to call .is_file() on
    something inside it. Every one of those left an empty directory behind, and
    a directory under runs/ is the thing build_archive walks to decide which
    mornings exist.

    It was not theoretical. runs/2026-08-15 and runs/2026-08-16 are a Saturday
    and a Sunday, deleted on 2026-08-21 as fixtures the claim sweep created, and
    both were back within hours with the 22:15 nightly's mtime on them, because
    weekly_page walks a calendar week and asks each day for its report. So did
    runs/2026-05-04, a date this project has never run a morning on, from the
    truth pass walking sessions. The archive logged a skip for each, every
    night, and the deletion looked like it had not held.

    Asserted as the property rather than as a list of call sites, because the
    list is what went wrong: backfill_premarket had already worked around this
    locally in 2026-08 with the comment "this is a read only", and the fix
    stayed where it was noticed while twelve other sites kept doing it.
    """
    from night import backup_evidence, pool_recall, true_volume, weekly_page
    from morning import scan

    # A date this project cannot have a run for, so the claim is not competing
    # with whatever the sandbox copied out of the real tree. runs/2026-05-04,
    # the real leftover, was the obvious choice and was the wrong one: it is
    # exactly the directory the bug leaves behind, so it was already there.
    absent = "1999-01-04"

    with conftest_activate() as _sandbox:
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in config.RUNS_DIR.iterdir() if p.is_dir()}
        if absent in before:
            failures.append(f"the fixture date {absent} already exists in the "
                            "sandbox, so this claim proves nothing")

        # run_path is the contract. It must answer and touch nothing.
        path = config.run_path(absent)
        if path.exists():
            failures.append("config.run_path created the directory it was asked "
                            "for the path of")
        if path != config.RUNS_DIR / absent:
            failures.append(f"config.run_path pointed at {path}, not at the "
                            "sandbox's runs directory, so it captured a root "
                            "instead of reading one")

        # And every read path that walks dates goes through it. Each of these
        # is driven with a date that has no run directory; none may leave one.
        readers = [
            ("weekly_page.did_it_run", lambda: weekly_page.did_it_run([absent])),
            ("weekly_page.is_it_trustworthy", lambda: weekly_page.is_it_trustworthy([absent])),
            ("pool_recall published", lambda: pool_recall.published_symbols(absent)),
            ("true_volume.measure", lambda: true_volume.measure(absent, dry_run=True)),
            ("backup_evidence artifacts", lambda: [f(absent) for _, f in backup_evidence._ARTIFACTS]),
            ("scan stand down", lambda: scan.thin_rerun_stands_down({"session_date": absent})),
        ]
        for name, call in readers:
            try:
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed):
                    call()
            except BaseException as exc:
                # A reader that cannot run on an absent date is not what this
                # claim is about, as long as it did not create anything.
                _ = exc
            if (config.RUNS_DIR / absent).exists():
                failures.append(f"{name} created runs/{absent} while reading it")
                (config.RUNS_DIR / absent).rmdir()

        after = {p.name for p in config.RUNS_DIR.iterdir() if p.is_dir()}
        if after != before:
            failures.append(f"reading created {sorted(after - before)} under "
                            "runs/, which is the directory listing that says "
                            "which mornings exist")
    print("  read only    asking whether a session has a packet leaves no "
          "directory behind, on six readers and on run_path itself")


def claim_a_partial_batch_writes_each_minute_once(failures: list[str]) -> None:
    """A settle batch that dies partway does not write its landed minutes twice.

    BarBuilder.flush writes its batch one line at a time and flushes each one,
    so the file never holds a buffered partial line while scan reads it at
    08:45. The OSError handler then restored EVERY bar in `pending` and printed
    "nothing has been marked written", which was true of the bookkeeping and
    false of the disk: a fault on line five of ten leaves four on disk and
    re-queues them, the next settle appends them again, and read_bars_file does
    not deduplicate on (symbol, minute). A duplicated minute is counted twice in
    pm_volume, which is the numerator of premarket RVOL and of premarket float
    rotation, so it reaches the day screen and the report.

    The fault is installed as production produces it, by failing the handle
    partway through the batch rather than before it. A write that never starts
    was never the shape of this failure.
    """
    from collect.collect_premarket import BarBuilder, read_bars_file

    base = 1_756_000_000
    with tempfile.TemporaryDirectory(prefix="pmd-partial-") as raw:
        path = pathlib.Path(raw) / "bars.jsonl"
        builder = BarBuilder(path, source="socket")
        for index in range(6):
            builder.add_trade(symbol=f"S{index}.US", price=10.0, volume=100.0,
                              epoch_s=base + index, dark_pool=False,
                              market_status="premarket")

        real_open = pathlib.Path.open
        seen = {"lines": 0}

        def fail_after_three(self, *args, **kwargs):
            handle = real_open(self, *args, **kwargs)
            mode = str(args[0] if args else kwargs.get("mode", ""))
            if "a" not in mode:
                return handle
            real_write = handle.write

            def counted(text):
                if text.strip():
                    seen["lines"] += 1
                    if seen["lines"] > 3:
                        raise OSError(28, "No space left on device", str(self))
                return real_write(text)

            handle.write = counted
            return handle

        pathlib.Path.open = fail_after_three
        try:
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                builder.flush(base + 400)
        finally:
            pathlib.Path.open = real_open
        first = printed.getvalue()

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            builder.flush(base + 800)

        bars, _stats = read_bars_file(path)
        counts = {symbol: len(rows) for symbol, rows in bars.items()}
        duplicated = {s: n for s, n in counts.items() if n > 1}
        if duplicated:
            failures.append(f"a partial batch wrote {duplicated} twice; a "
                            "duplicated minute doubles that minute in pm_volume")
        if sum(counts.values()) != 6:
            failures.append(f"{sum(counts.values())} minutes reached disk over "
                            "two settles, expected all 6 exactly once")
        if "reached disk and are marked written" not in first:
            failures.append("the partial write said nothing about how much of "
                            f"the batch landed: {first.strip()[:160]!r}")
    print("  partial batch a settle that dies partway writes each landed minute "
          "once and says how many landed")


def claim_a_torn_tail_is_closed_before_the_next_bar(failures: list[str]) -> None:
    """A restart after a torn final line does not destroy the first new minute.

    read_bars_file trusts only lines ending in a newline and discards an
    unterminated final one as the writer caught mid append, which is right for
    a reader. flush opens the file in APPEND mode, so the first bar of a
    restarted run was written straight onto that fragment: one unparseable line
    out of two real records, losing the new minute as well as the torn one, and
    the new minute is one nothing can refetch.
    """
    from collect.collect_premarket import BarBuilder, read_bars_file

    base = 1_756_000_000
    with tempfile.TemporaryDirectory(prefix="pmd-torn-") as raw:
        path = pathlib.Path(raw) / "bars.jsonl"
        path.write_text('{"symbol": "AAA.US", "minute_epoch": 1, "v": 1}\n'
                        '{"symbol": "BB', encoding="utf-8")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            builder = BarBuilder(path, source="socket")
            builder.add_trade(symbol="CCC.US", price=10.0, volume=500.0,
                              epoch_s=base, dark_pool=False,
                              market_status="premarket")
            builder.flush(base + 400)

        bars, stats = read_bars_file(path)
        if "CCC.US" not in bars:
            failures.append("the first minute written after a torn tail was "
                            "glued to the fragment and lost")
        if "AAA.US" not in bars:
            failures.append("the complete line before the torn one did not "
                            "survive")
        if stats["bad_lines_skipped"] != 1:
            failures.append(f"{stats['bad_lines_skipped']} bad lines after the "
                            "repair, expected exactly the one torn fragment")
        if not builder.torn_tails_terminated:
            failures.append("the torn tail was not counted, so a run that died "
                            "mid write leaves no trace of having done so")
    print("  torn tail    a restart onto an unterminated line keeps the new "
          "minute and leaves the fragment as the only bad line")


def claim_an_unplaceable_trade_is_not_a_lost_connection(failures: list[str]) -> None:
    """A trade this parser cannot place leaves the socket alone.

    The `t` field is milliseconds and _handle_message bounds the divided value
    only from BELOW. A value in microseconds or nanoseconds, or simply corrupt,
    reaches ettime.from_epoch_s, which raises OSError [Errno 22] on this
    platform. _handle_message is called inside run_websocket's message loop,
    whose handler is `except (ConnectionError, WebSocketException, OSError)`, so
    ONE bad message tore down a healthy connection, counted a reconnect and
    resubscribed into a 50 symbol pool the server is known to refuse while it
    still holds the slots this run just dropped. On a two hour window that is
    the difference between a thin morning and no tape at all.

    Driven with a window set, because the conversion that raises is the one
    recording an out of window example and a builder with no window never
    reaches it.
    """
    from collect.collect_premarket import BarBuilder, _handle_message

    base = 1_756_000_000
    for label, stamp in (("nanoseconds", 1_756_000_000_000_000_000),
                         ("microseconds", 1_756_000_000_000_000),
                         ("negative", -8_640_000_000_000_000)):
        with tempfile.TemporaryDirectory(prefix="pmd-stamp-") as raw:
            builder = BarBuilder(pathlib.Path(raw) / "bars.jsonl", source="socket",
                                 window=(base, base + 7200))
            message = json.dumps({"s": "AAA", "p": 10.0, "v": 100, "t": stamp})
            printed = io.StringIO()
            try:
                with contextlib.redirect_stdout(printed):
                    _handle_message(message, builder, [])
            except BaseException as exc:
                failures.append(
                    f"a {label} trade timestamp raised {type(exc).__name__} out "
                    "of _handle_message; run_websocket reads that as a lost "
                    "connection and resubscribes into a pool that refuses")
                continue
            if stamp > 0 and not builder.unparseable_trades:
                failures.append(f"a {label} trade timestamp was discarded "
                                "silently; a feed that changed units would look "
                                "like a quiet tape")

    # And an ordinary trade still lands, so the guard cannot be satisfied by a
    # handler that drops everything.
    with tempfile.TemporaryDirectory(prefix="pmd-stamp-ok-") as raw:
        builder = BarBuilder(pathlib.Path(raw) / "bars.jsonl", source="socket",
                             window=(base, base + 7200))
        _handle_message(json.dumps({"s": "AAA", "p": 10.0, "v": 100,
                                    "t": (base + 10) * 1000}), builder, [])
        if builder.trades_seen != 1 or builder.unparseable_trades:
            failures.append(f"an ordinary trade did not fold: seen "
                            f"{builder.trades_seen}, unparseable "
                            f"{builder.unparseable_trades}")
    print("  bad stamp    a trade the parser cannot place is counted and "
          "discarded, and the connection is left alone")


def claim_a_failed_truth_pass_erases_no_measurement(failures: list[str]) -> None:
    """A night the feed is down does not null the night it was up.

    Every record measure() returns carries the full column set, with the true
    columns left None when the Alpaca fetch errored or came back below
    min_true_bars, and store.upsert writes every key it is handed. So a second
    pass over a session already measured replaced real SIP volume with NULL on
    every row and left a truth_reason beside it, which store.py's own convention
    then reads back as "the pass reached this row and could not measure it".
    That is not what happened: it WAS measured, and the record is gone.

    A second pass is the ordinary case rather than an unusual one. The nightly
    sweeps unmeasured sessions, the 07:00 catch-up runs the same step, and
    --reread walks every session on purpose.

    The row is held back WHOLE rather than merged column by column, and that is
    asserted: the true columns are one measurement over one window, so keeping
    pm_volume_true from one pass beside a capture_observed from another would
    publish a ratio whose halves came from different nights.
    """
    from core import store
    from night import true_volume

    day = "2026-08-20"
    measured = {
        "_socket": 1000.0, "_estimated": 8532.0, "ticker": "AAA.US",
        "true_window": "04:00-08:45", "truth_source": "alpaca-sip",
        "truth_at": "2026-08-20T22:15:00-04:00", "true_bars": 120,
        "true_baseline_sessions": 20, "pm_volume_true": 9000.0,
        "pm_rvol_true": 2.5, "pm_float_rotation_true": 0.01,
        "true_baseline_median": 3600.0, "capture_observed": 0.11,
        "estimate_error": 0.95, "true_volume_socket_window": 9000.0,
        "collector_window_share": 0.52, "truth_reason": None,
    }
    empty = dict(measured, **{
        "true_bars": None, "true_baseline_sessions": None,
        "pm_volume_true": None, "pm_rvol_true": None,
        "pm_float_rotation_true": None, "true_baseline_median": None,
        "capture_observed": None, "estimate_error": None,
        "true_volume_socket_window": None, "collector_window_share": None,
        "truth_reason": "alpaca: HTTP 503 fetching the window",
    })

    with conftest_activate() as _sandbox:
        with store.session() as connection:
            store.init(connection)
            store.upsert(connection, "picks", ["date", "ticker"],
                         {"date": day, "ticker": "AAA.US", "source": "live",
                          "pm_volume": 1000.0})
            connection.commit()

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            true_volume.write({"day": day, "rows": [dict(measured)],
                               "skipped": None, "dry_run": False})
            failed = {"day": day, "rows": [dict(empty)], "skipped": None,
                      "dry_run": False}
            wrote = true_volume.write(failed)

        with store.session() as connection:
            row = connection.execute(
                "SELECT pm_volume_true, pm_rvol_true, capture_observed, "
                "true_baseline_median FROM picks WHERE date=? AND ticker=?",
                (day, "AAA.US")).fetchone()

        if row["pm_volume_true"] != 9000.0:
            failures.append(f"a failed truth pass overwrote pm_volume_true with "
                            f"{row['pm_volume_true']!r}; the measurement is gone "
                            "and the row now reads as one that could not be taken")
        for column, expected in (("pm_rvol_true", 2.5),
                                 ("capture_observed", 0.11),
                                 ("true_baseline_median", 3600.0)):
            if row[column] != expected:
                failures.append(f"a failed truth pass overwrote {column} with "
                                f"{row[column]!r}, expected {expected}")
        if wrote:
            failures.append(f"the failed pass reported writing {wrote} row(s); a "
                            "row it declined to touch is not a row it wrote")
        if "left as they stand" not in printed.getvalue():
            failures.append("the failed pass said nothing about the rows it held "
                            f"back: {printed.getvalue().strip()[:160]!r}")
        if failed.get("held") != ["AAA.US"]:
            failures.append(f"the result records held {failed.get('held')!r}, so "
                            "a caller cannot tell which rows were not retaken")

        # And a row with NO measurement yet still takes the reason, or a
        # session the feed refused would never record that it refused.
        with store.session() as connection:
            store.upsert(connection, "picks", ["date", "ticker"],
                         {"date": day, "ticker": "BBB.US", "source": "live"})
            connection.commit()
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            true_volume.write({"day": day, "rows": [dict(empty, ticker="BBB.US")],
                               "skipped": None, "dry_run": False})
        with store.session() as connection:
            fresh = connection.execute(
                "SELECT truth_reason FROM picks WHERE date=? AND ticker=?",
                (day, "BBB.US")).fetchone()
        if not fresh["truth_reason"]:
            failures.append("a row with no measurement yet did not record why "
                            "the pass could not take one")
    print("  truth held   a pass that could not measure leaves a measurement "
          "standing, names the rows it held, and still records a first refusal")


def claim_recall_refuses_a_pool_the_morning_did_not_read(failures: list[str]) -> None:
    """Recall is not measured against a watchlist that has since been rewritten.

    discover writes ONE undated data/watchlist.json and load_watchlist reads it
    unconditionally, so pool_recall.build(session_date=...) measured whatever
    that file held at 22:15 rather than at 07:15. Two of the seven recall
    artifacts on disk are that: runs/2026-08-21/pool_recall.json publishes
    discovery_recall_addressable 0.0 against 92 addressable gappers off a three
    symbol afternoon hand run, and runs/2026-08-13's names a watchlist generated
    the NEXT DAY. Both read as a morning that caught nothing and neither says so,
    while DECISIONS quotes recall as evidence for the tier ordering and for the
    subscription cap.

    The packet settles it, because scan stamps the file the collector actually
    subscribed against. Refused rather than corrected: an overwritten pool cannot
    be reconstructed.
    """
    from night import pool_recall

    with conftest_activate() as _sandbox:
        day = "2026-08-13"
        run = config.run_dir(day)
        run.mkdir(parents=True, exist_ok=True)

        def write_packet(stamp):
            body = {"session_date": day, "candidates": []}
            if stamp is not None:
                body["watchlist_generated_at"] = stamp
            (run / "packet.json").write_text(json.dumps(body), encoding="utf-8")

        write_packet("2026-08-13T07:15:00-04:00")
        stamp, why = pool_recall.watchlist_the_morning_read(day)
        if stamp != "2026-08-13T07:15:00-04:00" or why:
            failures.append(f"the packet's stamp read back as {stamp!r} ({why})")

        write_packet(None)
        stamp, why = pool_recall.watchlist_the_morning_read(day)
        if stamp is not None or "records no watchlist_generated_at" not in (why or ""):
            failures.append("a packet with no watchlist stamp did not say so: "
                            f"{stamp!r}, {why!r}")

        (run / "packet.json").unlink()
        stamp, why = pool_recall.watchlist_the_morning_read(day)
        if stamp is not None or "no packet.json" not in (why or ""):
            failures.append(f"a missing packet did not say so: {stamp!r}, {why!r}")

        # A packet under a nested candidate_provenance still answers, because
        # scan writes the stamp in both places and only one is guaranteed.
        (run / "packet.json").write_text(json.dumps({
            "session_date": day,
            "candidate_provenance": {"watchlist_generated_at": "2026-08-13T08:21:00-04:00"},
        }), encoding="utf-8")
        stamp, _why = pool_recall.watchlist_the_morning_read(day)
        if stamp != "2026-08-13T08:21:00-04:00":
            failures.append("the stamp under candidate_provenance was not read, "
                            "so a watchdog rerun of discover would refuse a "
                            "session it should measure")
    print("  wrong pool   the packet says which watchlist the morning read, and "
          "a missing stamp is told apart from a missing packet")


def claim_a_split_is_not_a_gap(failures: list[str]) -> None:
    """A corporate action does not enter the gapper set as the day's biggest move.

    actual_gappers divided raw open by raw prior close with no adjustment test,
    so a 4-for-1 forward split with its ex date on the measured session enters at
    -75 percent and a 1-for-10 reverse split at +900. Each one inflates `gapped`
    and `addressable`, which are the DENOMINATORS of discovery_recall, so the
    pool is charged with missing a name that never moved. CRITERIA's price units
    note makes the same argument for the outcome fill and calls a reverse split
    candidate "not an exotic case", the screen's price floor being only "> 3".

    Refused with the reason counted rather than rescaled, and a payload that
    cannot answer is reported as unchecked rather than as clean.
    """
    from night import pool_recall
    from core import criteria

    crit = criteria.load()
    gap_rule = crit.rule("discovery", "gap_pct")
    universe_symbols = {"SPLIT.US", "REAL.US", "QUIET.US", "NOADJ.US"}

    # close/adjusted_close is flat between actions and steps at one. SPLIT goes
    # 4-for-1 on the measured session; REAL just gapped; QUIET did neither.
    prior = {
        "SPLIT.US": {"code": "SPLIT", "close": 40.0, "adjusted_close": 40.0},
        "REAL.US": {"code": "REAL", "close": 10.0, "adjusted_close": 10.0},
        "QUIET.US": {"code": "QUIET", "close": 10.0, "adjusted_close": 10.0},
        "NOADJ.US": {"code": "NOADJ", "close": 10.0, "adjusted_close": None},
    }
    today = [
        {"code": "SPLIT", "open": 10.0, "close": 10.0, "adjusted_close": 40.0,
         "volume": 100.0},
        {"code": "REAL", "open": 12.0, "close": 12.0, "adjusted_close": 12.0,
         "volume": 100.0},
        {"code": "QUIET", "open": 10.0, "close": 10.0, "adjusted_close": 10.0,
         "volume": 100.0},
        {"code": "NOADJ", "open": 12.0, "close": 12.0, "volume": 100.0},
    ]
    closes = {s: r["close"] for s, r in prior.items()}

    gappers, census = pool_recall.actual_gappers(
        today, closes, universe_symbols, gap_rule, prior_rows_by_symbol=prior)

    if "SPLIT.US" in gappers:
        failures.append("a 4-for-1 split entered the gapper set at "
                        f"{gappers['SPLIT.US']['gap_at_open_pct']} percent, "
                        "inflating the denominator of discovery_recall")
    if "REAL.US" not in gappers:
        failures.append("a real 20 percent gap was refused, so the guard is "
                        "removing measurements rather than corporate actions")
    if "QUIET.US" in gappers:
        failures.append("a name that did not move entered the gapper set")
    refused = [r["symbol"] for r in census["refused_corporate_action"]]
    if refused != ["SPLIT.US"]:
        failures.append(f"the census names {refused} as corporate actions, "
                        "expected exactly SPLIT.US")
    if census["unchecked_for_corporate_action"] != 1:
        failures.append(f"{census['unchecked_for_corporate_action']} rows were "
                        "reported unchecked, expected the one carrying no "
                        "adjusted_close; a payload that cannot answer must not "
                        "read as clean")
    if "NOADJ.US" not in gappers:
        failures.append("a row that could not be checked was dropped; unchecked "
                        "is not the same as refused")
    print("  split guard  a corporate action is refused from the gapper set with "
          "its drift counted, and a row that cannot be checked says so")


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

        # Signed, because the sentence under test is the one the direction
        # selects, and an unsigned summary takes a different branch.
        fresh = {"day": "2026-08-19", "compared": 73, "within_one_percent": 0,
                 "median_abs_pct": 90.0, "unavailable": 0,
                 "median_signed_pct": -90.0, "direction": "under",
                 "direction_phrase": "the collector recorded LESS than the vendor",
                 "aggregate_ratio": 0.1, "sign_recorded": True}
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
        # It used to assert the opposite: that the gap says the feed
        # shortfall is LARGER than the window shortfall, which was right while
        # both sat uncorrected inside the ratio. Since 2026-08-21 the feed half
        # is divided out per symbol and the window half is not, so a packet
        # saying the feed error is still in the ratio double counts a nine
        # times correction in the reader's head. The first live report did
        # exactly that, twice.
        elif "divides out" not in stated[0]:
            failures.append(
                "the gap does not say the measured gap is what the capture "
                "correction divides out, so the reader is told to apply it a "
                f"second time: {stated[0]}")
        elif "UNDERSTATED" in stated[0] or "LARGER than the window" in stated[0]:
            failures.append(
                "the gap still describes the feed shortfall as an error left "
                f"inside the ratios, which it no longer is: {stated[0]}")

        # A check older than the CRITERIA limit is named as stale, not dropped.
        far = ettime.parse_date("2026-08-19") + dt.timedelta(days=40)
        sink = Sink()
        stale = scan.volume_check(far.isoformat(), sink)
        if not stale or not stale["stale"]:
            failures.append(f"a 40 day old check did not read as stale: {stale}")
        if not any("days old" in g and "past the" in g for g in sink.gaps):
            failures.append(f"a stale check was not called stale: {sink.gaps}")
        # And it says what a stale check COSTS now, which is not the same
        # sentence: the shares the ratios are built on are that old too.
        if not any("capture shares" in g for g in sink.gaps):
            failures.append(
                "a stale check does not say the per symbol capture shares are "
                f"that stale, which is what it now costs: {sink.gaps}")

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
    # It used to assert the gap calls an empty day list an instrument
    # reading. That was right while the numerator was raw socket volume. Since
    # 2026-08-21 the RVOL these names failed on already carries the capture
    # correction, so blaming the feed for them is the double count the
    # correction created: these are names the CORRECTED numerator could not
    # lift, which is a fact about the names.
    elif "already carries the capture correction" not in sink.gaps[0]:
        failures.append(
            "the gap does not say these names failed on a CORRECTED RVOL, so "
            "it still reads as though the feed shortfall cost them: "
            f"{sink.gaps[0]}")
    elif "instrument reading" in sink.gaps[0]:
        failures.append(
            "the gap still calls an empty day list an instrument reading, "
            "which invites the reader to discount a screen decision that was "
            f"made on a corrected number: {sink.gaps[0]}")

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

def claim_the_volume_check_puts_no_roster_in_the_packet(failures: list[str]) -> None:
    """The instrument that reports on the feed cannot widen the claim guard.

    Fixing the unsigned median on 2026-08-20 gave verify_against_intraday four
    per symbol structures: minutes_compared_by_symbol, unavailable_symbols,
    vendor_zero_volume_symbols and collector_silent_symbols. They exist for a
    human reading runs/<date>/verify_intraday.json, and latest_volume_check
    spreads the whole summary, so on the first run of the new shape they would
    have reached packet.json.

    That widens containment. analyst._packet_uppercase_tokens builds the
    allowed set from the raw packet TEXT and _TOKEN_RE finds AVGO inside the
    key "AVGO.US", so every symbol in the PREVIOUS session's collector roster,
    73 names on 2026-08-19, becomes a ticker this morning may claim while
    holding no evidence about any of them. Measured against the real
    2026-08-20 packet: AMAT, AVGO, DE, HOOD, MU, NOK, RIOT, SAP, TLT and TSM
    moved from invented to allowed, which is the exact set a model reaches for
    in a market context sentence. The guard that exists to catch invented
    evidence would have been widened by the instrument that reports on the
    feed it validates.

    So the packet carries the counts and the file keeps the names.
    """
    from morning import analyst
    from morning import scan

    roster = {
        "minutes_compared_by_symbol": {"MU.US": 125, "AVGO.US": 118, "TSM.US": 110},
        "unavailable_symbols": ["DE.US", "SAP.US"],
        "vendor_zero_volume_symbols": ["TLT.US"],
        "collector_silent_symbols": ["NOK.US", "RIOT.US"],
    }
    check = {
        "day": "2026-08-19", "compared": 73, "within_one_percent": 0,
        "median_abs_pct": 90.0, "median_signed_pct": -90.0,
        "aggregate_ratio": 0.1, "direction": "under",
        "direction_phrase": "the collector recorded less than the vendor",
        "collector_silent": 2, "vendor_zero_volume": 1, "unavailable": 2,
        "stale": False, "age_days": 1, "max_age_days": 5, "source": "nightly",
        **roster,
    }

    safe = scan._packet_safe_volume_check(check)
    leaked = sorted(set(roster) & set(safe))
    if leaked:
        failures.append(f"the packet carries per symbol rosters {leaked}, which "
                        "widens the containment allow list by the previous "
                        "session's collector names")

    # The counts must survive, or the fix traded one silence for another.
    for key in ("compared", "collector_silent", "vendor_zero_volume",
                "unavailable", "direction", "direction_phrase",
                "median_signed_pct", "aggregate_ratio"):
        if key not in safe:
            failures.append(f"{key} was dropped from the packet with the "
                            "rosters, so the reader loses the measurement too")

    # The whitelist has to be a whitelist. A key nobody has decided about must
    # not travel just because the check started returning it.
    invented = scan._packet_safe_volume_check({**check, "new_symbols": ["ZZZ.US"]})
    if "new_symbols" in invented:
        failures.append("an unrecognised key reached the packet, so the filter "
                        "is a blacklist and the next roster added to the check "
                        "travels with it")

    # And the thing it is all for: the allowed set must not grow.
    base_packet = {"session_date": "2026-08-19",
                   "candidates": [{"symbol": "NVDA.US"}],
                   "collector_volume_check": safe}
    wide_packet = {**base_packet, "collector_volume_check": check}
    allowed = analyst._packet_uppercase_tokens(json.dumps(base_packet))
    would_be = analyst._packet_uppercase_tokens(json.dumps(wide_packet))
    widened = sorted(would_be - allowed)
    if not widened:
        failures.append("the unfiltered check widened the allowed set by "
                        "nothing, so this claim cannot detect the defect it "
                        "guards and the fixture no longer names real listings")
    for token in ("MU", "AVGO", "TSM", "DE", "SAP", "TLT", "NOK", "RIOT"):
        if token in allowed:
            failures.append(f"{token} is claimable from the filtered packet, so "
                            "a roster reached containment anyway")
    print("  roster       the volume check puts its counts in the packet and "
          f"leaves {len(widened)} previous session names in the file")


# ------------------------------- the 2026-08-20 verification: what the fixes broke
#
# An adversarial pass over the nineteen fixes found eleven things they broke
# or left half done. These guard the second round.

def claim_a_finish_marker_outranks_a_fresh_log(failures: list[str]) -> None:
    """A job that exited is dead however recently its log was written.

    The liveness gate added on 2026-08-20 took any dated log written inside
    job_log_stale_after_s as proof of life, and a job that dies writes its last
    line at the instant it dies. A chain that failed its analyst step at 09:20
    read as fifteen seconds of healthy work at 09:25, and 09:25 is the ONLY
    pass that can act on it: register_tasks.ps1 fires the monitor 07:25 through
    09:25 every thirty minutes, chain_due is 09:00, so 08:55 reads NOT DUE and
    rerun_chain_until is past by the next firing. The rerun that used to happen
    there stopped happening, and the pass printed RUNNING and exited 0.

    Every .bat echoes "===== <step> finished rc=<n> =====" once a step has
    returned and exits on a non-zero one, so the log itself says which of the
    two states it is in. The marker is read before the mtime, and a log whose
    last marker is a finish is a job that is over.
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
        # Quiet the branches this claim is not about, exactly as the liveness
        # claim above does: today's watchlist with a subscription list beside
        # it, and an empty ledger so the daily rerun cap is not in the way.
        config.WATCHLIST_PATH.write_text(
            json.dumps({"generated_at": f"{day}T07:15:00-04:00", "symbols": []}),
            encoding="utf-8")
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        (config.PREMARKET_DIR / f"{day}-subscriptions.json").write_text(
            json.dumps({"symbols": []}), encoding="utf-8")
        (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        chain_log = config.LOGS_DIR / f"morning-chain-{day}.log"
        nightly_log = config.LOGS_DIR / f"nightly-{day}.log"
        asleep = {"exists": True, "status": "Ready",
                  "last_run": None, "last_result": "1"}

        # The marker reader first, on the lines a real log actually holds.
        chain_log.write_text(
            "===== scan started Thu 08/20/2026  8:45:01.16 ===== \n"
            "scan: 41 candidates\n"
            "===== scan finished rc=0 Thu 08/20/2026  8:45:22.03 ===== \n"
            "===== analyst started Thu 08/20/2026  8:45:22.03 ===== \n"
            "===== analyst finished rc=2 Thu 08/20/2026  8:49:14.14 ===== \n",
            encoding="utf-8")
        if monitor_jobs.last_step_marker("morning-chain", day) != ("analyst", 2):
            failures.append("the last step marker of a chain log that died in "
                            "the analyst step read "
                            f"{monitor_jobs.last_step_marker('morning-chain', day)!r}")
        # Lines that are not step boundaries say nothing about a running step
        # and must not be mistaken for one. Both of these are real .bat output.
        chain_log.write_text(
            "===== gate table Thu 08/20/2026  8:49:14.75 ===== \n"
            "===== market closed today, morning chain skipped Thu ===== \n",
            encoding="utf-8")
        if monitor_jobs.last_step_marker("morning-chain", day) is not None:
            failures.append("a gate table line or a market closed line was read "
                            "as a step boundary")

        # Now the same fact through the whole pass, at both clocks where the
        # chain can still be rerun. Five seconds old is the reading the gate
        # used to call life.
        for clock in ((9, 5), (9, 25)):
            chain_log.write_text(
                "===== scan started =====\n"
                "===== scan finished rc=0 =====\n"
                "===== analyst started =====\n"
                "===== analyst finished rc=2 =====\n", encoding="utf-8")
            nightly_log.write_text("===== backfill finished rc=1 =====\n",
                                   encoding="utf-8")
            now = ettime.now_et().replace(hour=clock[0], minute=clock[1],
                                          second=0, microsecond=0)
            stamp = now.timestamp() - 5
            os.utime(chain_log, (stamp, stamp))
            os.utime(nightly_log, (stamp, stamp))
            (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
            launched, printed = one_pass(now, asleep)
            where = f"{clock[0]:02d}:{clock[1]:02d}"
            if "job_morning_chain.bat" not in launched:
                failures.append(
                    f"a chain whose log ends in \"analyst finished rc=2\" five "
                    f"seconds ago was not rerun at {where}; the pass launched "
                    f"{launched or 'nothing'}")
            if "analyst finished rc=2" not in printed:
                failures.append(f"the {where} pass did not name the marker the "
                                "chain died on")

        # The mtime still governs a log whose last marker is a started one,
        # which is the state a healthy job spends nearly all its time in.
        chain_log.write_text("===== scan started =====\n"
                             "===== scan finished rc=0 =====\n"
                             "===== analyst started =====\n", encoding="utf-8")
        now = ettime.now_et().replace(hour=9, minute=5, second=0, microsecond=0)
        stamp = now.timestamp() - 5
        os.utime(chain_log, (stamp, stamp))
        launched, printed = one_pass(now, asleep)
        if "job_morning_chain.bat" in launched:
            failures.append("a chain between its analyst markers, written five "
                            "seconds ago, was rerun on top of itself")

        # The nightly half. A finish marker on the vendor-lag steps is the same
        # proof of death, and the nightly is where a duplicate is cheapest to
        # start and most expensive to explain.
        for tail, expect_rerun in (("===== backfill finished rc=1 =====\n", True),
                                   ("===== backfill started =====\n", False)):
            nightly_log.write_text(tail, encoding="utf-8")
            now = ettime.now_et().replace(hour=22, minute=45, second=0, microsecond=0)
            stamp = now.timestamp() - 60
            os.utime(nightly_log, (stamp, stamp))
            (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
            launched, printed = one_pass(now, asleep)
            if ("job_nightly.bat" in launched) is not expect_rerun:
                failures.append(
                    f"a nightly log ending {tail.strip()!r} a minute ago "
                    f"{'was not' if expect_rerun else 'was'} rerun; the pass "
                    f"launched {launched or 'nothing'}")
    print("  exit marker a log ending in a failing finish marker is dead however "
          "fresh, and one ending mid step is not")


def claim_a_hold_needs_a_pass_that_can_act(failures: list[str]) -> None:
    """The collector is held only while a later pass inside the window exists.

    The hold added on 2026-08-20 waits one pass rather than starting a
    collector on a watchlist discover is in the middle of rewriting, and it had
    no test that a later pass exists. The collector window ends at [Collector]
    stop_time 09:25 and the branch that starts a collector tests
    now < stop_time, so a hold at the 08:55 pass was answered by nobody: 09:25
    reported the window over and the morning ran with no collector at all and
    the collector's rerun budget unspent. Half a window of the previous
    session's names is worth more than no tape, and scan records
    watchlist_generated_at, so past the last pass that can act the collector is
    started instead of held.
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

    # The schedule the hold reasons about, read from CRITERIA rather than
    # assumed: register_tasks.ps1 fires the monitor at first_pass and repeats
    # it every pass_interval_min through last_pass, and monitor-night once.
    for now_m, expected in ((7 * 60 + 25, 7 * 60 + 55),
                            (8 * 60 + 25, 8 * 60 + 55),
                            (8 * 60 + 55, 9 * 60 + 25),
                            (9 * 60 + 25, 22 * 60 + 45),
                            (22 * 60 + 45, None)):
        got = monitor_jobs._next_pass_minute(now_m)
        if got != expected:
            failures.append(f"the pass after {now_m // 60:02d}:{now_m % 60:02d} "
                            f"was read as {got}, expected {expected}")

    with conftest_activate():
        day = ettime.today_str()
        previous = (ettime.now_et().date() - dt.timedelta(days=1)).isoformat()
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        asleep = {"exists": True, "status": "Ready",
                  "last_run": None, "last_result": "1"}

        # The both-missed morning: yesterday's watchlist, nothing listening,
        # no bars, no discover log. That is the one state that relaunches
        # discover, which is the only state that can hold the collector.
        def missed_morning():
            config.WATCHLIST_PATH.write_text(
                json.dumps({"generated_at": f"{previous}T07:15:00-04:00",
                            "symbols": []}), encoding="utf-8")
            (config.PREMARKET_DIR / f"{day}-subscriptions.json").unlink(missing_ok=True)
            for name in (f"{day}.jsonl", f"{day}-stats.jsonl"):
                (config.PREMARKET_DIR / name).unlink(missing_ok=True)
            (config.LOGS_DIR / f"discover-{day}.log").unlink(missing_ok=True)
            (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")

        for clock, hold_expected in (((7, 25), True), ((8, 25), True),
                                     ((8, 55), False), ((9, 5), False)):
            missed_morning()
            now = ettime.now_et().replace(hour=clock[0], minute=clock[1],
                                          second=0, microsecond=0)
            launched, printed = one_pass(now, asleep)
            where = f"{clock[0]:02d}:{clock[1]:02d}"
            if "job_discover.bat" not in launched:
                failures.append(f"the {where} pass did not relaunch discover on "
                                "a watchlist from the previous session, so the "
                                "hold this claim is about was never reached")
            held = "collector  HELD" in printed
            started = "job_collector.bat" in launched
            if held is not hold_expected:
                failures.append(
                    f"the {where} pass {'did not hold' if hold_expected else 'held'} "
                    "the collector; the next pass inside the window is "
                    f"{monitor_jobs._next_pass_minute(now.hour * 60 + now.minute)}")
            if started is hold_expected:
                failures.append(
                    f"the {where} pass "
                    f"{'started' if started else 'did not start'} the collector; "
                    f"it launched {launched or 'nothing'}")
    print("  hold gate    a collector is held only where a later pass inside the "
          "window can start it, and started rather than stranded after that")


def claim_the_last_pass_counts_what_it_cannot_resolve(failures: list[str]) -> None:
    """A liveness verdict nobody will revisit is counted, not reported clean.

    Task Scheduler settles the question for a job it started itself. A warm log
    does not: it is the same reading for a job writing now as for one that
    stopped writing nineteen minutes ago, and the gate added on 2026-08-20 read
    both as RUNNING, with no problem counted and no action taken. That is a
    verdict of "ask again later" in the two places where nobody asks again. The
    chain gets ONE pass inside [chain_due, rerun_chain_until], 09:25, because
    chain_due is 09:00 and the monitor's firings are 07:25 through 09:25. The
    nightly gets one too, monitor-night at 22:45, and by the next one the dated
    log path has rolled. So the pass with no successor inside the window
    reports UNRESOLVED and counts the job as a problem, which is what puts it
    in the exit code and in front of a reader.
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

    def problems(printed: str) -> int:
        for line in printed.splitlines():
            if "problem(s)" in line:
                return int(line.split()[1])
        return -1

    with conftest_activate():
        day = ettime.today_str()
        config.WATCHLIST_PATH.write_text(
            json.dumps({"generated_at": f"{day}T07:15:00-04:00", "symbols": []}),
            encoding="utf-8")
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        (config.PREMARKET_DIR / f"{day}-subscriptions.json").write_text(
            json.dumps({"symbols": []}), encoding="utf-8")
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        chain_log = config.LOGS_DIR / f"morning-chain-{day}.log"
        nightly_log = config.LOGS_DIR / f"nightly-{day}.log"
        asleep = {"exists": True, "status": "Ready",
                  "last_run": None, "last_result": "1"}
        # Mid step, so the marker cannot settle it and only the mtime is left.
        warm = "===== scan started =====\n===== analyst started =====\n"

        def pass_at(clock, log, tail, age):
            (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
            if tail is None:
                log.unlink(missing_ok=True)
            else:
                log.write_text(tail, encoding="utf-8")
            now = ettime.now_et().replace(hour=clock[0], minute=clock[1],
                                          second=0, microsecond=0)
            if tail is not None:
                stamp = now.timestamp() - age
                os.utime(log, (stamp, stamp))
            return one_pass(now, asleep)

        # 09:05 still has 09:25 after it, so a warm log is a fair RUNNING.
        nightly_log.write_text(warm, encoding="utf-8")
        launched, printed = pass_at((9, 5), chain_log, warm, 840)
        if "chain      RUNNING" not in printed or "job_morning_chain.bat" in launched:
            failures.append("a chain with a warm log at 09:05, which the 09:25 "
                            f"pass reads again, was not left alone: {printed!r}")

        # 09:25 has nobody after it inside rerun_chain_until. Same state, and
        # the verdict has to change: named, counted, and still not rerun on top
        # of what may be a live chain.
        launched, printed = pass_at((9, 25), chain_log, warm, 840)
        unresolved = problems(printed)
        if "chain      UNRESOLVED" not in printed:
            failures.append("a chain whose warm log nobody will read again was "
                            f"not reported UNRESOLVED at 09:25: {printed!r}")
        if "job_morning_chain.bat" in launched:
            failures.append("a chain that may still be running was rerun at "
                            "09:25 on evidence that cannot tell it from a dead "
                            "one")
        # The control: the same pass with no chain log at all counts one
        # problem for the chain and reruns it. The warm case must count the
        # same one, which is what "not a clean RUNNING" has to mean.
        launched, printed = pass_at((9, 25), chain_log, None, 0)
        if problems(printed) != unresolved:
            failures.append(
                f"the 09:25 pass counted {unresolved} problem(s) for a chain it "
                f"could not resolve and {problems(printed)} for a chain that "
                "never wrote a log, so the unresolved one is not being counted")
        if "job_morning_chain.bat" not in launched:
            failures.append("a chain with no log at all was not rerun at 09:25")

        # The nightly, where monitor-night is a single firing and there is no
        # later pass at any hour.
        chain_log.write_text(warm, encoding="utf-8")
        launched, printed = pass_at((22, 45), nightly_log, warm, 60)
        unresolved = problems(printed)
        if "nightly    UNRESOLVED" not in printed:
            failures.append("a nightly whose warm log nobody will read again "
                            f"was not reported UNRESOLVED at 22:45: {printed!r}")
        if "job_nightly.bat" in launched:
            failures.append("a nightly that may still be running was rerun at "
                            "22:45 on top of itself")
        launched, printed = pass_at((22, 45), nightly_log, None, 0)
        if problems(printed) != unresolved:
            failures.append(
                f"the 22:45 pass counted {unresolved} problem(s) for a nightly "
                f"it could not resolve and {problems(printed)} for one that "
                "never wrote a log")

        # Task Scheduler still settles it. A job Scheduler reports as running
        # is running, at the last pass as at any other, and must not be
        # dressed up as a problem.
        running = {"exists": True, "status": "Running",
                   "last_run": ettime.now_et(), "last_result": "267009"}
        (config.DATA_DIR / "monitor-reruns.json").write_text("{}", encoding="utf-8")
        chain_log.write_text(warm, encoding="utf-8")
        now = ettime.now_et().replace(hour=9, minute=25, second=0, microsecond=0)
        stamp = now.timestamp() - 840
        os.utime(chain_log, (stamp, stamp))
        launched, printed = one_pass(now, running)
        if "chain      RUNNING" not in printed:
            failures.append("a chain Task Scheduler reports as running was not "
                            f"reported RUNNING at the last pass: {printed!r}")
    print("  last pass    a warm log nobody will read again is counted and named "
          "rather than reported as a clean RUNNING")


def claim_the_long_leg_checks_the_units_it_writes(failures: list[str]) -> None:
    """A split inside D+2 to D+5 refuses day5_close instead of writing it.

    The corporate action guard added on 2026-08-20 sat inside "if wants_short",
    so it tested D+1 and nothing else, and the long leg wrote
    updates['day5_close'] on every path with no unit check on any of them. That
    is the ORDINARY cadence rather than an edge: the candidate query re-selects
    on "next_day_close IS NULL OR day5_close IS NULL" and wants_short tests
    next_day_close, so the short leg fills on the night of D+1 and the long leg
    five nights later, in a run where wants_short is already False and the
    guard never executes. A 4-for-1 split with its ex date at D+3 therefore put
    a post action close of 2.50 in the same row as the pre action entry_ref of
    10.50, stop_ref and pm_high it will be read against, silently and
    permanently, in the table CRITERIA.md names as the record its seed
    thresholds will be recalibrated from.

    The refusal is written down rather than left as a null, because a null
    day5_close is also what a fill that is not due yet looks like. It does not
    move outcomes_filled_at either: that column records when an outcome was
    obtained, and this row's outcome was obtained on the night of D+1.
    """
    from core import criteria, eodhd, store
    from night import fill_outcomes

    pick_date, ex_date = "2026-07-13", "2026-07-16"
    calendar = ["2026-07-10", pick_date, "2026-07-14", "2026-07-15", ex_date,
                "2026-07-17", "2026-07-20"]
    calendar_symbol = criteria.load().text("universe", "session_calendar_symbol")
    filled_at = "2026-07-14T20:00:00-04:00"

    def _bars(split: bool) -> list[dict[str, Any]]:
        """A ten dollar name whose 4-for-1 split has its ex date at D+3.

        The vendor's shape: close is what printed, adjusted_close is rewritten
        on the bars BEFORE the ex date and left alone from it on, so close over
        adjusted_close is flat until the ex date and steps once there. D+1 is
        on the near side of that step, which is what makes this the case the
        short leg's guard cannot see.
        """
        out = []
        for day in calendar:
            raw = 2.5 if (split and day >= ex_date) else 10.0
            out.append({"date": day, "open": raw, "high": raw * 1.1,
                        "low": raw * 0.9, "close": raw,
                        "adjusted_close": 2.5 if split else 10.0,
                        "volume": 1_000_000})
        return out

    class _Api:
        def __init__(self, split: bool) -> None:
            self.split = split
            self.name_calls = 0

        def eod(self, symbol, start=None, end=None, period="d"):
            if symbol == calendar_symbol:
                return eodhd.ApiResult([{"date": d} for d in calendar], None)
            self.name_calls += 1
            return eodhd.ApiResult(_bars(self.split), None)

    def _run(split: bool, runs: int = 1) -> tuple[dict[str, Any], str, int]:
        with conftest_activate():
            with store.session() as connection:
                store.init(connection)
                store.ensure_columns(connection, "picks",
                                     fill_outcomes._OUTCOME_COLUMNS)
                # The short leg already filled on the night of D+1, which is
                # the ordinary cadence and the run in which wants_short is
                # False and the old guard therefore never fired.
                connection.execute(
                    "INSERT INTO picks (date, ticker, source, pm_high, entry_ref, "
                    "stop_ref, next_day_open, next_day_high, next_day_low, "
                    "next_day_close, mfe_pct, mae_pct, pm_high_broke_next_day, "
                    "outcomes_filled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pick_date, "AAA.US", "live", 10.5, 10.5, 9.5, 10.0, 11.0,
                     9.0, 10.5, 4.7619, -5.2632, 1, filled_at))
                connection.commit()
            api = _Api(split)
            saved = eodhd.client
            eodhd.client = lambda: api
            printed = io.StringIO()
            try:
                with contextlib.redirect_stdout(printed):
                    for _ in range(runs):
                        # day_limit keeps the sandbox copy's own live rows,
                        # which are dated later, off the stubbed feed.
                        fill_outcomes.fill(pick_date)
            finally:
                eodhd.client = saved
            with store.session() as connection:
                # SELECT * rather than a column list, so a build where the
                # refusal column does not exist reads as a missing reason
                # rather than raising out of the claim.
                row = dict(connection.execute(
                    "SELECT * FROM picks WHERE date=? AND ticker=?",
                    (pick_date, "AAA.US")).fetchone())
            return row, printed.getvalue(), api.name_calls

    # Run twice: the second run also proves the refused row is not re-selected.
    row, said, calls = _run(split=True, runs=2)
    if row["day5_close"] is not None:
        failures.append(
            f"a 4-for-1 split at D+3 still wrote day5_close {row['day5_close']!r} "
            "beside an entry_ref of 10.5. That is the shape of a name that lost "
            "three quarters of its value over the week rather than one that split.")
    if not (row.get("day5_refused_reason") or ""):
        failures.append(
            "day5_close was left null with nothing recorded, so a refused fifth "
            "session cannot be told from one that is merely not due yet")
    elif "adjustment factor" not in row["day5_refused_reason"]:
        failures.append("the recorded refusal does not name what was measured: "
                        f"{row['day5_refused_reason']!r}")
    if row["outcomes_filled_at"] != filled_at:
        failures.append(
            f"outcomes_filled_at moved to {row['outcomes_filled_at']!r} on a run "
            f"that obtained no outcome, overwriting {filled_at}, so the column "
            "no longer records when the measurement was taken")
    if row["next_day_close"] != 10.5 or row["mfe_pct"] != 4.7619:
        failures.append("the short leg written five nights earlier was disturbed: "
                        f"{row!r}")
    if "refused" not in said:
        failures.append(f"the refusal was not reported to the operator: "
                        f"{said.strip()[:200]!r}")

    if calls != 1:
        failures.append(
            f"a refused row cost {calls} end of day call(s) over two runs, so it "
            "is re-selected every night to be refused again for as long as the "
            "session calendar reaches it")

    row, said, _ = _run(split=False)
    if row["day5_close"] != 10.0:
        failures.append("an ordinary week was refused as well, so the guard has "
                        f"stopped the long leg rather than corrected it: {row!r}")
    if row.get("day5_refused_reason") is not None:
        failures.append(f"an ordinary week recorded a refusal: "
                        f"{row.get('day5_refused_reason')!r}")
    if row["outcomes_filled_at"] == filled_at:
        failures.append("a run that did obtain the fifth session left "
                        "outcomes_filled_at at the short leg's stamp")
    print("  day5 units   a corporate action between D+2 and D+5 refuses "
          "day5_close in writing, and an ordinary week still fills")


def claim_the_buckets_say_what_they_sum_to(failures: list[str]) -> None:
    """The volume check totals its four buckets against the right number.

    verify_against_intraday said every subscribed symbol lands in exactly one
    of compared, unavailable, vendor_zero_volume or collector_silent and that
    the four sum to the subscription list. Three of the four are counted off
    the BAR FILE, and the list they were summed against is written by
    write_subscriptions, which rewrites it on every collector run by design, so
    a morning the collector restarted onto a different watchlist has a bar file
    holding every run's symbols and a list holding the last run's only.
    2026-08-19 is that morning and it is in the archive: the socket was refused
    at 08:35 because the account's own dropped connection still held the fifty
    slots, a hand restart at 08:37:14 subscribed to a different fifty, and 73
    symbols carry bars against a list of 50. The four buckets summed to 75
    there while the summary published subscribed 50 beside compared 73 and
    described the two as a partition.
    """
    from collect import collect_premarket
    from core import eodhd

    day, minute = "2026-07-13", 1787236800
    collected = {"A.US": 1000.0, "B.US": 1000.0, "C.US": 1000.0, "D.US": 500.0}
    vendor = {"A.US": 1000.0, "B.US": 2000.0, "C.US": 1000.0, "D.US": 0.0}

    class BarsApi:
        def intraday(self, symbol, start, end, interval):
            if symbol not in vendor:
                return [], None
            return [{"timestamp": minute, "volume": vendor[symbol]}], None

    def _measure(requested: list[str]) -> dict[str, Any]:
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        collect_premarket.bar_path(day).write_text(
            "".join(json.dumps({"symbol": symbol, "minute_epoch": minute,
                                "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0,
                                "v": volume, "trades": 1}) + "\n"
                    for symbol, volume in collected.items()),
            encoding="utf-8")
        collect_premarket.subscriptions_path(day).write_text(json.dumps({
            "symbols": sorted(requested), "requested_count": len(requested),
            "socket_cap": 50, "subscribed_at": f"{day}T08:37:14-04:00"}),
            encoding="utf-8")
        saved = eodhd.client
        eodhd.client = lambda *a, **k: BarsApi()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return collect_premarket.verify_against_intraday(day) or {}
        finally:
            eodhd.client = saved

    def _buckets(summary: dict[str, Any]) -> int:
        return (summary.get("compared", 0) + summary.get("unavailable", 0)
                + summary.get("vendor_zero_volume", 0)
                + summary.get("collector_silent", 0))

    with conftest_activate():
        # The restart: the list on disk is the second run's, and A and B were
        # collected by the first.
        restarted = _measure(["C.US", "D.US", "Z.US"])
        if not restarted:
            failures.append("the volume check returned nothing for a day it "
                            "could compare three symbols on")
        else:
            if _buckets(restarted) != restarted.get("symbols_accounted"):
                failures.append(
                    f"the four buckets sum to {_buckets(restarted)} and the "
                    f"summary says they account for "
                    f"{restarted.get('symbols_accounted')!r}, so the number "
                    "published beside them is not their total")
            if restarted.get("bars_outside_subscription") != 2:
                failures.append(
                    "two collected symbols the subscription list does not name "
                    "were not counted: "
                    f"{restarted.get('bars_outside_subscription')!r}")
            if restarted.get("bars_outside_subscription_symbols") != ["A.US", "B.US"]:
                failures.append(
                    "the symbols outside the list are not named in the file: "
                    f"{restarted.get('bars_outside_subscription_symbols')!r}")
            if _buckets(restarted) == restarted.get("subscribed"):
                failures.append(
                    "the fixture no longer restarts: the buckets and the "
                    "subscription count agree, so this claim proves nothing")
            reason = restarted.get("subscribed_reason") or ""
            if "rewrite" not in reason:
                failures.append(
                    "nothing on the summary says why compared is larger than "
                    f"subscribed on a restarted morning: {reason!r}")

        # And the ordinary morning, where the old sentence was true and has to
        # stay true: one run, one list, and the buckets do sum to it.
        ordinary = _measure(sorted(list(collected) + ["Z.US"]))
        if _buckets(ordinary) != ordinary.get("subscribed"):
            failures.append(
                f"on a morning with one collector run the buckets sum to "
                f"{_buckets(ordinary)} against a subscription of "
                f"{ordinary.get('subscribed')!r}")
        if ordinary.get("bars_outside_subscription") != 0:
            failures.append("an unrestarted morning reported symbols outside its "
                            "own subscription list")
        if ordinary.get("subscribed_reason") is not None:
            failures.append("an unrestarted morning was given a reason it does "
                            f"not need: {ordinary.get('subscribed_reason')!r}")

        # The archived morning the finding was raised on, where the files still
        # sit. Read rather than measured, because measuring it would cost one
        # intraday call per symbol.
        bars = collect_premarket.read_bars("2026-08-19")
        listed = set((collect_premarket.read_subscriptions("2026-08-19") or {})
                     .get("symbols") or [])
        if bars and listed and not (set(bars) - listed):
            failures.append(
                "2026-08-19 no longer shows the restart this claim is built on: "
                f"{len(bars)} symbols with bars, {len(listed)} on the list, none "
                "outside it. Check the archive before trusting the fixture above.")
    print("  bucket sum   the four buckets are totalled against the symbols "
          "they cover, and a restarted morning says why that is not the list")


def claim_a_matching_collector_is_not_called_a_disagreement(
    failures: list[str]
) -> None:
    """The direction word has a branch for agreement, and mixed says what it saw.

    _volume_check_direction returned "under" for a signed median below zero
    beside an aggregate ratio below one, "over" for the mirror of that, and
    "mixed" for everything else, so it had no branch at all for a collector
    that MATCHES the vendor, which is the outcome the measurement exists to
    work towards. A perfectly agreeing session came back "mixed: the two
    readings disagree, the typical symbol falling on one side of the vendor and
    the aggregate tape on the other". So did every pair with one reading on the
    vendor and the other off it: a signed median of exactly zero against an
    aggregate 0.75 times the vendor is a real disagreement, but the typical
    symbol is not on a side of anything. REPORT_TEMPLATE.md orders the model to
    quote direction_phrase verbatim, so each of those sentences was published
    as written.
    """
    from collect import collect_premarket
    from core import criteria

    band = criteria.load().number("collector", "volume_check_agreement_pct")
    read = getattr(collect_premarket, "VOLUME_CHECK_AGREEMENT_PCT", None)
    if read != band:
        failures.append(
            "the agreement band is not the one in CRITERIA.md [collector] "
            f"volume_check_agreement_pct: {read!r} against {band!r}")

    # The two readings in COLLECTOR_VOLUME.md, the mixed session between them,
    # and the cases that had no answer. Ratios are expressed through the band
    # so that moving the threshold moves the fixture with it.
    inside, outside = band / 2.0, band * 3.0
    expected = {
        (-88.49, 0.0994): "under",              # 2026-08-17
        (40.0, 3.83): "over",
        (-33.77, 3.8257): "mixed",              # 2026-08-14, genuinely straddling
        (0.0, 1.0): "agree",                    # the collector matches the vendor
        (-inside, 1.0 + inside / 100.0): "agree",
        (band * 0.9, 1.0 + band * 0.9 / 100.0): "agree",   # just inside it
        (outside, 1.0 + outside / 100.0): "over",
        (-outside, 1.0 - outside / 100.0): "under",
        (0.0, 0.75): "mixed",                   # typical on the vendor, tape below
        (-50.0, 1.0): "mixed",                  # typical below, tape on the vendor
        (-90.0, None): "unknown",
    }
    phrases: dict[str, str] = {}
    for (median, ratio), want in expected.items():
        got, phrase = collect_premarket._volume_check_direction(median, ratio)
        phrases[f"{median}|{ratio}"] = phrase
        if got != want:
            failures.append(
                f"a signed median of {median} against an aggregate ratio of "
                f"{ratio} read as {got!r}, expected {want!r}")
        if not phrase:
            failures.append(f"direction {got!r} came back with no phrase")

    agreeing = phrases["0.0|1.0"]
    if "disagree" in agreeing or "one side" in agreeing:
        failures.append(
            "a collector that matched the vendor on both readings is still "
            f"described as disagreeing, and the template quotes it: {agreeing!r}")
    straddle = phrases["0.0|0.75"]
    if "one side" in straddle or "on the other" in straddle:
        failures.append(
            "a signed median of exactly zero is still described as falling on a "
            f"side of the vendor: {straddle!r}")
    if "matched the vendor" not in straddle:
        failures.append("the mixed phrase does not say what the two readings "
                        f"actually were: {straddle!r}")
    print("  agreement    a collector matching the vendor reads as agreement, "
          "and mixed names which reading fell where")


def claim_the_hand_run_redirect_moves_a_captured_run_directory(
        failures: list[str]) -> None:
    """The redirect that keeps a hand run out of the evidence is itself asserted.

    standalone() wraps a direct `python -m tests.test_repricing` in the
    sandbox, and that was half of the fix. The module had already executed, so
    test_repricing.RUN_DIR still held the REAL runs/2026-08-14 while
    config.RUNS_DIR held the temporary copy, and claim_three sets
    config.DB_PATH to RUN_DIR / "test_repricing.db" and opens it in WAL mode. A
    hand run therefore created a SQLite database and its journal files inside
    the only copy of the first live morning's evidence.
    conftest.redirect_captured_paths is the other half, and NOTHING asserted
    it. The hand run claim above checks that standalone() exists, that every
    suite file routes __main__ through it, that SANDBOX_ACTIVE nests and is
    restored, and that the entry point runs sandboxed, every one of which stays
    true with the redirect deleted. run_tests.main() never enters standalone()
    at all, because it reloads each suite inside the sandbox and calls main()
    directly. So deleting the fix left the whole suite green, and the next hand
    run of test_repricing would have opened that database again.

    The neutered pass at the end is the load bearing part. The same assertions
    run a second time against a redirect that does nothing, and this claim
    fails if they do not fail. A claim that cannot fail is worse than no claim,
    and this one guards a function whose absence is invisible everywhere else.
    """
    import types

    from tests import conftest

    @contextlib.contextmanager
    def neutered(module: Any) -> Any:
        """The fix, deleted. Exactly what the suite failed to notice."""
        yield []

    def assertions(redirect: Any) -> list[str]:
        """Every assertion about the redirect, against whichever one is given."""
        found: list[str] = []
        module = types.ModuleType("premarketdesk_throwaway")
        # One path under a redirected root, and two that must not move: doc/
        # and src/ are read only to a test run, and a module that captured
        # CRITERIA.md's absolute path at import would be pointed at a file
        # that does not exist if this rebased it into the sandbox.
        module.RUN_DIR = conftest.REAL_RUNS / "2026-08-14"
        module.DOC = config.PROJECT_ROOT / "doc" / "CRITERIA.md"
        module.SRC = config.PROJECT_ROOT / "src" / "tests" / "conftest.py"
        # The two shapes the walk was widened to on 2026-08-20, when
        # standalone() was found printing an unqualified all clear over both.
        # __module__ is assigned by hand because type() takes it from the frame
        # that called it, which is this file, and the walk looks only at
        # classes defined in the module it was handed.
        module.RUN_DIRS = [conftest.REAL_RUNS / "2026-08-15"]
        holder = type("Holder", (), {"RUN_DIR": conftest.REAL_RUNS / "2026-08-16"})
        holder.__module__ = module.__name__
        module.Holder = holder
        before = {name: getattr(module, name)
                  for name in ("RUN_DIR", "DOC", "SRC", "RUN_DIRS")}
        was_held = holder.RUN_DIR

        with redirect(module) as moved:
            wanted = config.RUNS_DIR / "2026-08-14"
            if module.RUN_DIR != wanted:
                found.append(f"the captured run directory reads {module.RUN_DIR} "
                             f"inside the sandbox, expected {wanted}. A claim that "
                             "opens a database under it writes into the preserved "
                             "evidence of the first live morning")
            if module.RUN_DIRS != [config.RUNS_DIR / "2026-08-15"]:
                found.append("a run directory held in a module level list was not "
                             f"moved: {module.RUN_DIRS}")
            if holder.RUN_DIR != config.RUNS_DIR / "2026-08-16":
                found.append("a run directory held on a class defined in the "
                             f"module was not moved: {holder.RUN_DIR}")
            if module.DOC != before["DOC"] or module.SRC != before["SRC"]:
                found.append(f"a doc/ or src/ path was rewritten: {module.DOC} and "
                             f"{module.SRC}. Nothing writes to either, and a module "
                             "reading CRITERIA.md through the absolute path it "
                             "captured would find no file there")
            if sorted(moved) != ["Holder.RUN_DIR", "RUN_DIR", "RUN_DIRS"]:
                found.append(f"the redirect reported moving {sorted(moved)}, and "
                             "standalone() prints that list as its account of what "
                             "it did to the module it is about to run")
        restored = {name: getattr(module, name) for name in before}
        if restored != before or holder.RUN_DIR != was_held:
            found.append(f"the redirect left {restored} and {holder.RUN_DIR} behind, "
                         f"against the {before} and {was_held} it was handed")

        # Restored out of a body that RAISES, which is the case that matters: a
        # claim dying mid run must not leave the module pointing somewhere else
        # for whatever runs after it in the same process. A bare yield with no
        # try/finally around it passes every assertion above and fails this one.
        try:
            with redirect(module):
                raise RuntimeError("a suite module raising with the sandbox held")
        except RuntimeError:
            pass
        if module.RUN_DIR != before["RUN_DIR"]:
            found.append(f"a raising body left the module holding {module.RUN_DIR}, "
                         "so the next thing to run in this process reads a "
                         "directory it did not choose")
        return found

    with conftest_activate():
        if config.RUNS_DIR == conftest.REAL_RUNS:
            failures.append("the sandbox did not move config.RUNS_DIR, so nothing "
                            "below can tell a rebased path from an unmoved one")
            return
        # The root case, where relative_to gives Path("."). Joining that onto
        # the sandbox gives <sandbox>/runs/. rather than <sandbox>/runs, which
        # is a path that compares unequal to every path built from config.
        root = conftest._rebase(conftest.REAL_RUNS)
        if root != config.RUNS_DIR:
            failures.append(f"_rebase of the runs root gave {root}, expected "
                            f"{config.RUNS_DIR} exactly")
        for outside in (config.PROJECT_ROOT / "doc",
                        config.PROJECT_ROOT / "src" / "tests"):
            if conftest._rebase(outside) is not None:
                failures.append(f"_rebase moved {outside}, which sits under no "
                                "writable root and must be left exactly as it is")
        failures.extend(assertions(conftest.redirect_captured_paths))
        neutered_found = assertions(neutered)
        if not neutered_found:
            failures.append("every assertion above passes with the redirect "
                            "neutered, so they assert nothing: deleting "
                            "redirect_captured_paths would leave this claim green "
                            "and the hand run writing to the real runs directory")

    print(f"  redirect    a captured run directory, one in a list and one on a "
          f"class all move onto the sandbox, a doc/ and a src/ path do not, all "
          f"are restored out of a raising body, and {len(neutered_found)} of "
          "those assertions fail with the redirect neutered")


# ------------------------------------- the 2026-08-20 verification: the packet

def claim_an_unread_news_window_is_not_an_empty_one(failures: list[str]) -> None:
    """A window nobody checked publishes null counts, never a measured zero.

    attach_traps built trap_basis off the displayed headline list whenever
    attach_catalysts had left no window counts behind, and a candidate whose
    news call FAILED or was skipped for quota is exactly that candidate: its
    headline list is empty because nobody ever filled it. So it published
    headlines_scored 0, headlines_unscored 0 and headlines_in_window 0, which
    is what SCSC and ASST published in runs/2026-08-20/packet.json after their
    windows WERE read and held nothing. Every number in the two blocks matched.
    The one line that differed said the counts came from "the displayed
    headlines only, because no window count was recorded", which is the wording
    for a packet rescored before those counts existed and says nothing about a
    feed nobody asked.

    That is the substitution this project forbids everywhere else. trap is
    already null on both paths, so no verdict moved, but trap_basis is the
    evidence the report is told to quote beside a trap and a reader auditing it
    could not tell an unknown from a measurement.

    Both routes to unknown are driven, because they arrive from different
    places: attach_catalysts records catalyst_error when the call fails, and
    the thin quota path writes the same fields by hand having fetched nothing.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    class FeedApi:
        """Answers for one symbol and refuses for the other."""

        def news(self, symbol, start=None, end=None):
            if symbol == "READ.US":
                return [], None
            return None, "HTTP 500 from the news endpoint"

    candidates = [{"symbol": "READ.US", "gap_pct": 9.0},
                  {"symbol": "FAILED.US", "gap_pct": 9.0}]
    # The thin quota path builds this by hand in run(): no call is made at all,
    # so there is no error to quote and the reason is the skip itself.
    thin = {"symbol": "THIN.US", "gap_pct": 9.0, "catalyst_found": None,
            "catalyst_error": "news call skipped: quota preflight",
            "headlines": []}

    sink = Sink()
    scan.attach_catalysts(FeedApi(), candidates, sink)
    candidates.append(thin)
    scan.attach_traps(candidates, sink)

    basis = {c["symbol"]: (c.get("trap_basis") or {}) for c in candidates}
    counted = ("headlines_in_window", "headlines_scored", "headlines_unscored",
               "negative", "positive")

    # The window that WAS read and held nothing. Zero is the right answer here
    # and it has to stay zero, or this claim has traded one substitution for
    # the opposite one.
    for field in counted:
        if basis["READ.US"].get(field) != 0:
            failures.append(
                f"a window the feed answered with no headlines published "
                f"{field}={basis['READ.US'].get(field)!r}, expected a measured 0")
    if "every headline the feed returned" not in str(basis["READ.US"].get("counted_over")):
        failures.append("a window that was read does not say it was read: "
                        f"{basis['READ.US'].get('counted_over')!r}")

    # The two windows nobody read.
    for symbol, reason in (("FAILED.US", "HTTP 500 from the news endpoint"),
                           ("THIN.US", "news call skipped: quota preflight")):
        for field in counted:
            if basis[symbol].get(field, 0) is not None:
                failures.append(
                    f"{symbol} was never asked and published {field}="
                    f"{basis[symbol].get(field)!r}, which is a claim that the "
                    "window was counted")
        said = str(basis[symbol].get("counted_over"))
        if reason not in said:
            failures.append(f"{symbol} does not carry the reason its window went "
                            f"unread: {said!r}")
        if "unknown" not in said:
            failures.append(f"{symbol} does not say the counts are unknown: {said!r}")
        # Measured either way, and it really is zero: the packet displays no
        # headline for a name whose feed was never read.
        if basis[symbol].get("headlines_displayed") != 0:
            failures.append(
                f"{symbol} reports {basis[symbol].get('headlines_displayed')!r} "
                "displayed headlines with none on the candidate")

    # The load bearing one, stated the way the defect was: the two blocks were
    # the same bytes.
    if json.dumps(basis["READ.US"], sort_keys=True) == json.dumps(
            basis["FAILED.US"], sort_keys=True):
        failures.append(
            "a checked empty window and an unchecked one publish an identical "
            "trap_basis, so the packet cannot say which fact it holds")

    # And no verdict moved: both were null before and both are null now.
    for symbol in ("READ.US", "FAILED.US", "THIN.US"):
        candidate = next(c for c in candidates if c["symbol"] == symbol)
        if candidate.get("trap") is not None:
            failures.append(f"{symbol} came back trap={candidate.get('trap')!r}, "
                            "and nothing about this fix may move a verdict")

    print("  unread news  a news window nobody checked publishes null counts "
          "with the reason, not the zeros of a window that was")


def claim_the_sharing_count_names_the_set_it_was_taken_over(
    failures: list[str]
) -> None:
    """The roundup denominator counts the candidates whose news call answered.

    _scope_articles measures how many of this morning's candidates the feed
    handed one article to. The numerator can only come from `fetched`, which
    holds one entry per candidate whose news call ANSWERED; the denominator
    published beside it was len(candidates), the whole packet. On a morning
    that lost calls the two halves came from different populations, so three of
    four checked names read as "3 of this morning's 7 candidates" and a wire
    roundup looked narrower than it was. classify_catalyst quoted that same
    ratio into the why a reader audits the class from.

    Nothing about which articles are called roundups moves here and none is
    claimed to: max_candidates_sharing_article is an absolute threshold, not a
    fraction, so the last assertion below pins the verdicts in place.

    The floor clause is the other half. With a call missing, an article the
    feed WOULD have handed to an unchecked name cannot be seen to have been, so
    the sharing count is a floor rather than a count. It is said out loud
    rather than acted on: guessing the missing side would invent breadth, and
    the cost of being wrong here is a class withheld, never a class invented.
    """
    from morning import scan

    class Sink:
        def __init__(self) -> None:
            self.gaps: list[str] = []

        def gap(self, note: str) -> None:
            self.gaps.append(note)

    now = ettime.now_et()

    def article(title: str, tags: list[str], link: str) -> dict[str, Any]:
        return {"date": (now - dt.timedelta(minutes=30)).isoformat(),
                "title": title, "link": link, "sentiment": {"polarity": 0.1},
                "tags": list(tags), "symbols": []}

    roundup = article("Biggest stock movers Thursday", ["EARNINGS", "STOCK-MOVERS"],
                      "https://example.test/movers")
    release = article("DAQO New Energy Non-GAAP EPADS misses",
                      ["EARNINGS", "EARNINGS NEWS"], "https://example.test/daqo")

    # Four candidates the feed answers for, three it refuses. The roundup went
    # to three of the four that were asked, which is above
    # max_candidates_sharing_article either way.
    answered = {"AAA.US": [roundup], "BBB.US": [roundup], "CCC.US": [roundup],
                "DQ.US": [release]}
    refused = ["EEE.US", "FFF.US", "GGG.US"]

    class ThinnedApi:
        def news(self, symbol, start=None, end=None):
            if symbol in answered:
                return [dict(row) for row in answered[symbol]], None
            return None, "HTTP 429 from the news endpoint"

    candidates = [{"symbol": s} for s in list(answered) + refused]
    scan.attach_catalysts(ThinnedApi(), candidates, Sink())

    scopes = {}
    for candidate in candidates:
        for headline in candidate.get("headlines") or []:
            scopes[candidate["symbol"]] = headline.get("article_scope") or {}

    if len(scopes) != len(answered):
        failures.append(f"only {len(scopes)} of {len(answered)} answered candidates "
                        "carry an article scope, so the fixture proves nothing")
        return

    scope = scopes["AAA.US"]
    if scope.get("candidates_checked") != len(answered):
        failures.append(
            f"the sharing count was published over "
            f"{scope.get('candidates_checked')!r} candidates, not the "
            f"{len(answered)} whose news call answered")
    if scope.get("candidates_in_packet") != len(candidates):
        failures.append(
            f"the packet size is no longer recorded beside it: "
            f"{scope.get('candidates_in_packet')!r}, expected {len(candidates)}")
    if scope.get("returned_for_candidates") != 3:
        failures.append(f"the roundup was seen on "
                        f"{scope.get('returned_for_candidates')!r} candidates, "
                        "not the 3 the feed returned it for")
    why = str(scope.get("why"))
    if f"{len(answered)} candidate(s) whose news was checked" not in why:
        failures.append(f"the scope does not name the set it counted over: {why!r}")
    if f"{len(refused)} candidate(s) had no news call answered" not in why:
        failures.append(f"the scope does not say the sharing count is a floor on a "
                        f"morning that lost calls: {why!r}")
    if "floor" not in why:
        failures.append(f"the scope calls a floor something other than a floor: {why!r}")

    # The reason it matters: this is the sentence a reader audits the class from.
    _, paid = scan.classify_catalyst(
        next(c for c in candidates if c["symbol"] == "DQ.US"), set())
    if f"of this morning's {len(answered)} candidates" not in paid:
        failures.append(
            f"the class DQ was paid quotes a denominator other than the "
            f"{len(answered)} candidates the feed was asked about: {paid!r}")

    # A morning where every call answered says nothing about a floor, or the
    # clause is noise on every ordinary packet.
    class WholeApi:
        def news(self, symbol, start=None, end=None):
            return [dict(row) for row in answered.get(symbol, [release])], None

    whole = [{"symbol": s} for s in answered]
    scan.attach_catalysts(WholeApi(), whole, Sink())
    intact = ((whole[0].get("headlines") or [{}])[0].get("article_scope") or {})
    if intact.get("candidates_checked") != intact.get("candidates_in_packet"):
        failures.append("a morning that lost no call reports two different "
                        f"candidate counts: {intact!r}")
    if "floor" in str(intact.get("why")):
        failures.append("a morning that lost no call still calls its sharing "
                        f"count a floor: {intact.get('why')!r}")

    # And the verdicts themselves, which this must not move. The threshold is
    # absolute, so the thinned morning and the whole one agree.
    for symbol, expected in (("AAA.US", False), ("BBB.US", False),
                             ("CCC.US", False), ("DQ.US", True)):
        if scopes[symbol].get("about_this_name") is not expected:
            failures.append(
                f"{symbol} came back about_this_name "
                f"{scopes[symbol].get('about_this_name')!r}, expected {expected}: "
                "the denominator is published, never applied")

    print("  breadth      the roundup sharing count names the candidates whose "
          "news was checked, and says so when it is a floor")


# -------------------------------- the 2026-08-20 verification: the pool sources

def claim_a_lost_second_bulk_call_keeps_the_first(failures: list[str]) -> None:
    """A refusal on the earlier session does not throw the prior one away.

    prior_session_movers buys two bulk end of day days and needs both to name a
    mover, so either refusal leaves the source not_fetched and that is right.
    The two refusals do not cost the same thing, and until now they were
    written as though they did. When it is the SECOND call that comes back
    empty or errored, the prior session's closes are already bought and paid
    for, and the early return threw them out with it: the closes map went
    unreturned, so every subscribed name reached the 08:45 scan with
    pool_prior_close null and no close to measure a gap against, and the scan
    spent one end of day call per name buying back a number the 07:15 pass had
    been holding. The universe closes sidecar went unwritten too, and the
    briefing's two session leg is c3 against c1, which does not touch the
    session that failed at all.

    So the first refusal still returns with nothing, because there is nothing,
    and the second one carries c1 out with it. The status is not_fetched on
    both paths, which is the only value the gaps_to_fill loop, the empty pool
    gap and main's job_status.failed read.
    """
    from core import eodhd
    from selection import discover

    class _Bulk:
        """Records the days asked for, and can answer empty or error per day."""

        def __init__(self, empty_on: set[Any] = frozenset(),
                     error_on: set[Any] = frozenset()) -> None:
            self.empty_on = empty_on
            self.error_on = error_on
            self.days: list[Any] = []
            self.closes: dict[Any, float] = {}

        def eod_bulk_last_day(self, exchange="US", day=None, symbols=None,
                              extended=False):
            self.days.append(day)
            if day in self.error_on:
                return eodhd.ApiResult(None, "HTTP 503 from eod-bulk-last-day")
            if day in self.empty_on:
                return eodhd.ApiResult([], None)
            return eodhd.ApiResult(
                [{"code": "AAA", "close": self.closes.get(day, 10.0),
                  "date": day.isoformat(), "volume": 1_000_000}], None)

    with conftest_activate() as _sandbox:
        from morning import vintage

        today = ettime.today_et()
        prior = vintage.previous_trading_session(today)
        before = vintage.previous_trading_session(prior) if prior else None
        third = vintage.previous_trading_session(before) if before else None
        if prior is None or before is None or third is None:
            failures.append("the sandbox exchange calendar could not name three "
                            "prior sessions, so this claim cannot run at all")
            return

        sidecar = config.DATA_DIR / f"universe-closes-{today.isoformat()}.json"

        def run(api: _Bulk) -> dict[str, Any]:
            # The sandbox copies the real data/ in, and a live morning has
            # already written today's sidecar into it. Removed first, or the
            # assertion below reads yesterday's evidence as this run's work.
            if sidecar.exists():
                sidecar.unlink()
            api.closes = {prior: 11.0, before: 10.0, third: 9.0}
            with contextlib.redirect_stdout(io.StringIO()):
                return discover.prior_session_movers(api, {"AAA.US"}, {}, today)

        # The first call refused. Nothing is in hand, so nothing travels and
        # the second call is not bought either.
        first = _Bulk(empty_on={prior})
        source = run(first)
        if source["status"] != discover.NOT_FETCHED:
            failures.append(f"an empty prior session payload was filed "
                            f"{source['status']!r}, not not_fetched")
        if source.get("closes"):
            failures.append(f"the prior session call returned nothing and a closes "
                            f"map was published anyway: {source.get('closes')!r}")
        if first.days != [prior]:
            failures.append(f"calls were made after the prior session answered with "
                            f"nothing: {[str(d) for d in first.days]}")
        if sidecar.exists():
            failures.append("a closes sidecar was written from a prior session "
                            "payload that never arrived")

        # The second call refused, both ways it can be. c1 is in hand and has
        # to come out.
        for label, api in (("empty", _Bulk(empty_on={before})),
                           ("errored", _Bulk(error_on={before}))):
            source = run(api)
            if source["status"] != discover.NOT_FETCHED:
                failures.append(
                    f"an {label} earlier session payload was filed "
                    f"{source['status']!r}, not not_fetched, so nothing downstream "
                    "sees the loss")
            if before.isoformat() not in str(source.get("error")) and label == "empty":
                failures.append(f"the recorded reason does not name the session that "
                                f"came back empty: {source.get('error')!r}")
            closes = source.get("closes") or {}
            if (closes.get("AAA.US") or {}).get("close") != 11.0:
                failures.append(
                    f"the prior session close was discarded with the {label} "
                    f"earlier session call: {closes!r}. It was bought before that "
                    "call was made, and without it every subscribed name reaches "
                    "the scan with pool_prior_close null.")
            if not sidecar.exists():
                failures.append(f"no universe closes sidecar was written after the "
                                f"{label} earlier session call, so the briefing "
                                "loses the two session leg as well as the one that "
                                "failed")
                continue
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            row = (payload.get("closes") or {}).get("AAA.US") or {}
            if (row.get("c1"), row.get("c2"), row.get("c3")) != (11.0, None, 9.0):
                failures.append(
                    f"the sidecar rows read {row!r} after the {label} earlier "
                    "session call, expected c1 11.0, c2 null and c3 9.0")
            if payload.get("names_with_both_closes_for_leg") != {
                    "prior_session": 0, "two_session": 1}:
                failures.append(
                    "the sidecar does not count the legs apart after the "
                    f"{label} earlier session call: "
                    f"{payload.get('names_with_both_closes_for_leg')!r}. "
                    "two_session is c3 against c1 and does not touch the session "
                    "that failed.")
            if payload.get("names_with_close", {}).get("c2") != 0:
                failures.append(
                    f"the sidecar reports c2 closes it does not hold: "
                    f"{payload.get('names_with_close')!r}")

        # And an ordinary morning is untouched, or the separation has eaten the
        # source it was meant to rescue.
        whole = _Bulk()
        source = run(whole)
        if source["status"] != discover.FETCHED:
            failures.append(f"a complete pair of bulk payloads came back "
                            f"{source['status']!r}, expected fetched")
        if (source.get("closes") or {}).get("AAA.US", {}).get("close") != 11.0:
            failures.append("an ordinary morning lost its closes map: "
                            f"{source.get('closes')!r}")

    print("  bulk pair    a refused earlier session keeps the prior session's "
          "closes and still writes the sidecar")


def claim_the_watchlist_comment_matches_what_the_watchdog_does(
    failures: list[str]
) -> None:
    """No module tells a reader the watchdog cannot rebuild a broken watchlist.

    discover.build's note beside the atomic write ended with a sentence saying
    the watchdog could not repair a truncated watchlist either, because it
    declined to rerun discover once the collector window had opened. That was
    true when it was written and stopped being true on 2026-08-20, when the
    rerun moved off a clock comparison no value could satisfy and onto the
    file. The comment is where a maintainer reads what the safety net does, and
    it was describing a safety net that had been rebuilt underneath it.

    Both halves are checked, because deleting the sentence is not the fix on
    its own: the replacement has to be TRUE. The condition the watchdog turns
    on is driven here on the exact file the comment is about, a watchlist
    truncated mid write, with no subscription list on disk.

    The walk skips src/tests/ deliberately and it is worth saying why. The same
    retracted sentence was copied into this suite's own docstring for the
    atomic write claim, and that file belongs to whoever is editing it; a walk
    that included it would fail on somebody else's paragraph rather than on the
    code. It is a real second copy and it wants the same correction.
    """
    import re
    import subprocess

    from ops import monitor_jobs
    from collect import collect_premarket
    from selection import discover

    root = config.PROJECT_ROOT
    listing = subprocess.run(["git", "--no-optional-locks", "ls-files"],
                             cwd=str(root), capture_output=True, text=True)
    if listing.returncode != 0:
        failures.append("git ls-files failed, so the modules could not be walked: "
                        f"{listing.stderr.strip()[:200]}")
        return
    walked = [name for name in listing.stdout.splitlines()
              if name.startswith("src/") and name.endswith(".py")
              and not name.startswith("src/tests/")]
    if len(walked) < 20:
        failures.append(f"the walk found only {len(walked)} modules, which is too "
                        "few to be this project's source")
        return

    # Comments wrap, so the needle would never match the file as written.
    # Whitespace and comment hashes collapse to single spaces first.
    retracted = ("the watchdog cannot repair", "refuses to rerun discover",
                 "cannot rerun discover", "will not rerun discover")
    for name in walked:
        try:
            text = (root / name).read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        flat = re.sub(r"[\s#]+", " ", text).lower()
        for needle in retracted:
            if needle in flat:
                failures.append(
                    f"{name} still tells its reader {needle!r}, which the "
                    "2026-08-20 rerun fix made false")

    note = re.sub(r"[\s#]+", " ", (root / "src" / "selection" / "discover.py")
                  .read_bytes().decode("utf-8-sig"))
    if "_watchlist_vintage" not in note:
        failures.append(
            "discover.py no longer names the condition the rerun actually turns "
            "on, so the paragraph beside the atomic write says nothing about the "
            "safety net a maintainer is deciding against")

    # The second half: the replacement sentence has to be true of the code.
    with conftest_activate() as _sandbox:
        day = ettime.today_str()
        # A watchlist truncated mid write, which is the exact damage the
        # paragraph is about: valid JSON destroyed, nothing readable left.
        config.WATCHLIST_PATH.write_text('{"symbols": [{"sym', encoding="utf-8")
        if not discover.load_watchlist().get("missing"):
            failures.append("a truncated watchlist no longer reads as missing, so "
                            "this claim is not driving the damage it describes")

        stale, phrase = monitor_jobs._watchlist_vintage(day)
        if not stale:
            failures.append(f"the watchdog reads a truncated watchlist as usable: "
                            f"{phrase!r}")
        if "unreadable" not in phrase and "missing" not in phrase:
            failures.append(f"the watchdog does not say what is wrong with the file "
                            f"on disk: {phrase!r}")

        subscriptions = collect_premarket.subscriptions_path(day)
        if subscriptions.exists():
            subscriptions.unlink()
        if monitor_jobs._collector_has_subscribed(day):
            failures.append("the watchdog thinks the collector has subscribed with "
                            "no subscription list on disk, so the rerun it gates "
                            "would never fire")

        # And the gate closes again once something IS listening, which is the
        # half of the paragraph that survives: a rewrite then desyncs the
        # watchlist from what the socket was asked for.
        subscriptions.parent.mkdir(parents=True, exist_ok=True)
        subscriptions.write_text(json.dumps({"symbols": ["OLD.US"]}), encoding="utf-8")
        if not monitor_jobs._collector_has_subscribed(day):
            failures.append("a written subscription list does not close the rerun "
                            "gate, so the watchdog would rewrite the watchlist "
                            "under a running collector")

    print("  stale note   no module claims the watchdog cannot rebuild a broken "
          "watchlist, and the condition it does turn on is live")


# ----------------------------------- the 2026-08-20 verification: an instrument

def claim_a_partly_refused_sweep_is_reported_as_one(failures: list[str]) -> None:
    """A run where some chunks were refused says so, bars or no bars.

    The served versus refused split was added on 2026-08-20 for runs where the
    feed answers part of a sweep and turns the rest away, and it could not
    describe one. Every word about refusals sat under "No sweep returned a bar",
    so the only run shaped like the thing the split was for, some chunks 403,
    some served, bars found, took the other branch and printed best, median and
    worst lag with no mention of a refusal anywhere in the file. Those lags and
    the active count are readings of the part of the universe that answered.
    Unlabelled they read as readings of all of it, which is the 2026-08-17
    misreport with the sign flipped: there an unanswered sweep published as an
    empty feed, here a half answered one publishes as a whole one.

    The wholly refused and wholly served readings are pinned in place at the
    end, because a fix that reached them would be undoing the finding that
    produced them.
    """
    from research import probe_alpaca_live as probe

    def sweep(clock: str, **extra: Any) -> dict[str, Any]:
        record = {
            "taken_at_et": f"2026-08-21T{clock}-04:00",
            "window": {"start": "2026-08-21T11:00:00Z",
                       "end": "2026-08-21T11:30:00Z"},
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

    # One chunk refused, one served, and the served one came back full. This is
    # the shape the split exists for.
    with_bars = [
        sweep("07:30:00", errors=["chunk at 2000: status 403"], requests_served=1,
              requests_refused=1, refusal_status_codes=[403],
              symbols_with_bars=812, bars_total=9_000,
              newest_bar_et="2026-08-21T07:14:00-04:00",
              lag_minutes_newest=16.0, lag_minutes_median=18.0),
        sweep("07:35:00", errors=["chunk at 2000: status 403"], requests_served=1,
              requests_refused=1, refusal_status_codes=[403],
              symbols_with_bars=980, bars_total=11_000,
              newest_bar_et="2026-08-21T07:19:00-04:00",
              lag_minutes_newest=16.0, lag_minutes_median=17.0),
    ]
    # The same split with nothing served back, which already had prose and must
    # keep it.
    without_bars = [
        sweep("07:30:00", errors=["chunk at 2000: status 403"], requests_served=1,
              requests_refused=1, refusal_status_codes=[403]),
    ]
    # The 2026-08-17 shape: 46 requests, every one 403.
    wholly_refused = [
        sweep("07:30:00", errors=["chunk at 0: status 403",
                                  "chunk at 2000: status 403"]),
        sweep("07:35:00", errors=["chunk at 0: status 403",
                                  "chunk at 2000: status 403"]),
    ]
    wholly_served = [
        sweep("07:30:00", errors=[], requests_served=2, requests_refused=0,
              refusal_status_codes=[]),
    ]

    with conftest_activate() as _sandbox:
        bars_text = probe.write_table(with_bars, "2026-08-21").read_text(
            encoding="utf-8")
        dry_text = probe.write_table(without_bars, "2026-08-22").read_text(
            encoding="utf-8")
        refused_text = probe.write_table(wholly_refused, "2026-08-17").read_text(
            encoding="utf-8")
        served_text = probe.write_table(wholly_served, "2026-08-18").read_text(
            encoding="utf-8")

        printed = io.StringIO()
        log = probe.log_path("2026-08-21")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(json.dumps(r) for r in with_bars), encoding="utf-8")
        with contextlib.redirect_stdout(printed):
            probe.report("2026-08-21")
        said = printed.getvalue()

    # The branch that could not be reached: bars came back and so did a 403.
    if "PART OF THIS RUN WAS REFUSED" not in bars_text:
        failures.append("a run with bars and refusals carries no refusal banner, so "
                        "the columns below it read as the whole universe")
    if "Read the refusal column first" not in bars_text:
        failures.append("a run with bars and refusals never mentions the refusals "
                        "beside the lag it reports")
    if "403" not in bars_text:
        failures.append("a run with bars and refusals does not name the status code "
                        "the refused chunks came back with")
    if "floors for the universe" not in bars_text:
        failures.append("a run with bars and refusals presents its active count and "
                        "its lag as totals rather than as floors")
    # The measurement itself must survive: this adds a caveat, it does not
    # delete the reading.
    if "best 16.0 minutes" not in bars_text:
        failures.append("the observed lag section was lost from a run that has one: "
                        "the refusals qualify the reading, they do not remove it")
    if "does not serve this session live" in bars_text:
        failures.append("a partially refused run took the served empty reading, "
                        "which is the 2026-08-17 misreport")

    # The same split with nothing served back keeps the prose it had.
    if "Read the refusal column first" not in dry_text:
        failures.append("a partially refused run that returned no bars lost the note "
                        "written for it")
    if "does not serve this session live" in dry_text:
        failures.append("a partially refused run with no bars read as a served empty "
                        "feed")

    # And neither wholly refused nor wholly served may move.
    if "EVERY REQUEST IN EVERY SWEEP WAS REFUSED" not in refused_text:
        failures.append("the wholly refused banner was lost, which is the "
                        "2026-08-17 finding")
    if "PART OF THIS RUN WAS REFUSED" in refused_text:
        failures.append("a run where nothing was served reports as partly refused")
    if "does not serve this session live" not in served_text:
        failures.append("a sweep that WAS served and came back empty lost the "
                        "reading the prose was written for")
    if "403" in served_text or "PART OF THIS RUN WAS REFUSED" in served_text:
        failures.append("a sweep with no refusals reported a refusal anyway")

    # The terminal verdict is the other consumer, and it turns on the active
    # count, which is exactly the number a refusal makes a floor.
    if "part of this run was refused" not in said:
        failures.append(f"the printed verdict for a partially refused run says "
                        f"nothing about the refusals: {said.strip()[-300:]!r}")
    if "the verdict rests on two numbers" in said:
        failures.append("the printed verdict read a partially refused run as a "
                        "measurement of the feed's contents")

    print("  partial 403  a run with some chunks refused and bars from the rest "
          "reports as partly refused, with its lag a floor")


# ------------------------------------------------------- the 2026-08-20 review: the house rules

# The character and the entity this claim hunts for, spelled so that they do
# not appear literally in this file. A guard whose own source trips it is the
# shape already recorded on 2026-08-16, when the quantifier guard flagged the
# documents that describe it, and the answer there was the same: build the
# needle rather than write it.
_EM_DASH = chr(0x2014)
# All three ways HTML can spell it. The named form is the one that was
# actually in the architecture pages, but a numeric reference renders
# identically and a guard that knows only the name would pass a page full
# of the other two.
_EM_DASH_ENTITIES = ("&" + "mdash;", "&" + "#8212;", "&" + "#x2014;")


# ------------------------------ the 2026-08-21 arming: the instrument itself

def claim_a_flag_the_run_never_recorded_is_not_a_zero(
        failures: list[str]) -> None:
    """The probe's off exchange column says nothing rather than saying none.

    compare_to_vendor read the flagged count as
    run.get("off_exchange", {}).get(symbol, 0), which returns 0 for a run that
    HAD the counter and saw nothing and for a run that never had the counter
    at all. Those are opposite facts, and the whole off exchange question
    forks on which one it is: a small socket share with no flagged prints and
    no ignored condition code means the trades stream omits off exchange
    volume, which no collector change reaches, while the same share WITH
    flagged prints means the parser is dropping volume the feed delivered.

    data/socket-cap-probe-2026-08-19.json is the only probe result that
    exists and it predates the counter: its runs carry arm, counts, cycle,
    messages_total, refused, replayed, seconds, started_at, status, subscribed
    and volume, and nothing else. Read through the old expression it printed a
    flagged column of zero for every symbol in both arms. The comparison run
    on 2026-08-20 published that column, and the absence would have been read
    as the measurement that closes the fork.
    """
    from research import probe_socket_cap as probe

    absent = probe._flagged_over([{"counts": {}}, {"counts": {}}], "SPY.US")
    if absent != (0, False):
        failures.append("a run that never carried off_exchange reported "
                        f"{absent!r} rather than (0, False), so an absence is "
                        "still indistinguishable from a measured zero")

    measured = probe._flagged_over([{"off_exchange": {"SPY.US": 0}}], "SPY.US")
    if measured != (0, True):
        failures.append("a run that carried off_exchange and saw nothing "
                        f"reported {measured!r} rather than (0, True)")

    # One leg recording is enough to make the column meaningful, and the count
    # must be the sum over the legs that did.
    mixed = probe._flagged_over(
        [{"counts": {}}, {"off_exchange": {"SPY.US": 4}},
         {"off_exchange": {"SPY.US": 3}}], "SPY.US")
    if mixed != (7, True):
        failures.append(f"a partly recorded arm reported {mixed!r} rather "
                        "than (7, True)")

    print("  flagged      an off exchange count the run never took prints as "
          "not recorded, and a real zero still prints as zero")


def claim_a_partial_minute_counts_only_the_seconds_it_covered(
        failures: list[str]) -> None:
    """The socket cap probe charges the tape for the arm, not for whole bars.

    probe_socket_cap.compare_to_vendor produces the third number behind
    doc/research/COLLECTOR_VOLUME.md, which is the open question the delivery
    gate waits on: what EODHD's own one minute bars say the minutes an arm
    listened to actually traded. It summed every bar that overlapped the arm
    AT ALL and took each one whole. An arm is 120 seconds, and a 120 second
    arm that does not begin on a minute boundary overlaps three one minute
    bars, so 180 seconds of tape were charged against 120 seconds of socket.
    The published socket share was two thirds of the truth, decided by nothing
    but where the clock happened to fall when the arm started.

    That number is the whole output of the tool, and the guidance printed
    under it reads "far below 100%" as evidence the feed omits volume. A feed
    delivering every share would have been published at 67 percent, which is
    the reading that would have been acted on.

    The task was registered for 2026-08-21 before this was found, so this
    claim exists to keep the reading it takes and the reading it reports the
    same one.
    """
    from research import probe_socket_cap as probe

    # A 120 second arm starting 30 seconds into a minute, over four bars of
    # 600 shares each. Bars are keyed by the epoch second their minute starts,
    # which is the shape api.intraday returns.
    start = dt.datetime(2026, 8, 21, 6, 30, 30, tzinfo=ettime.ET)
    lo = ettime.epoch_s(start)
    bars = {lo - 30: 600.0, lo + 30: 600.0, lo + 90: 600.0, lo + 150: 600.0}

    measured = probe._vendor_shares_over(bars, start, 120.0)
    if abs(measured - 1200.0) > 0.001:
        failures.append(
            f"a misaligned 120 second arm charged {measured:,.0f} vendor shares "
            "against a tape carrying 600 a minute, where 1,200 is the whole of "
            "the two minutes it heard and 1,800 is the old whole bar sum")

    # The consequence in the terms the table prints: a socket that delivered
    # every share is 100 percent, and used to be published as 67.
    share = (1200.0 / measured * 100.0) if measured else float("nan")
    if abs(share - 100.0) > 0.1:
        failures.append("a socket that missed nothing would be published at "
                        f"{share:.1f} percent of the tape")

    # Alignment must not change the answer, or the fix has only moved the bias
    # rather than removed it.
    aligned = dt.datetime(2026, 8, 21, 6, 30, 0, tzinfo=ettime.ET)
    lo2 = ettime.epoch_s(aligned)
    bars2 = {lo2: 600.0, lo2 + 60: 600.0, lo2 + 120: 600.0}
    measured2 = probe._vendor_shares_over(bars2, aligned, 120.0)
    if abs(measured2 - 1200.0) > 0.001:
        failures.append(f"a minute aligned arm read {measured2:,.0f} rather than "
                        "1,200, so pro rating introduced a bias of its own")

    # And a bar the arm never reached contributes nothing at all.
    outside = probe._vendor_shares_over({lo + 600: 600.0}, start, 120.0)
    if outside != 0.0:
        failures.append(f"a bar ten minutes past the arm contributed {outside}")

    print("  denominator  the vendor side covers the seconds the arm listened, "
          "aligned or not, so the socket share is the socket's")


# ------------------- the 2026-08-20 review's two remaining research findings

_FAKE_CERT = ("-----BEGIN CERTIFICATE-----\n"
              "ZmFrZSwgYW5kIG5ldmVyIHRydXN0ZWQgYnkgYW55dGhpbmcu\n"
              "-----END CERTIFICATE-----\n")


def claim_the_trust_store_is_never_served_half_written(
        failures: list[str]) -> None:
    """A denied write leaves the old CA bundle, not a truncated one.

    config.ca_bundle() merges certifi with any local TLS inspection root and
    hands the result to requests as verify=. It wrote that file with a plain
    write_text and re-serves it on MTIME alone, so a truncated write carried a
    fresh mtime and was then served until certifi itself changed. The local
    root is appended LAST, which is the part that makes this specific: a
    truncation loses exactly the root that makes an intercepted connection
    verify, so every EODHD call fails TLS afterwards, at 07:15 on a weekday,
    for a reason nothing in the trace would name. tasks/README.md records that
    Norton on this machine occasionally denies the first write of a file, so
    the interruption is not hypothetical.

    Three properties, because the first two are the fix and the third is the
    hole beside it: a healthy merge lands whole and leaves no sibling behind, a
    refused rename leaves the PREVIOUS bundle exactly as it was, and a source
    that came back carrying no certificate refuses the merge rather than
    serving a trust store missing the root it exists to add. read_text with
    errors="replace" turns an unreadable byte into a character rather than
    raising, so that third case looks healthy at every size check.
    """
    import os as _os

    real_path = config.CA_BUNDLE_PATH
    real_extras = config._extra_ca_files
    real_replace = _os.replace
    with tempfile.TemporaryDirectory() as raw_box:
        box = pathlib.Path(raw_box)
        extra = box / "wscert.pem"
        extra.write_text(_FAKE_CERT, encoding="utf-8")
        target = box / "ca-bundle.pem"
        try:
            config.CA_BUNDLE_PATH = target
            config._extra_ca_files = lambda: [extra]

            served = config.ca_bundle()
            if served != str(target):
                failures.append(f"a healthy merge served {served!r} rather than "
                                "the merged bundle")
            body = target.read_text(encoding="utf-8") if target.is_file() else ""
            if body.count("BEGIN CERTIFICATE") < 2:
                failures.append("the merged bundle carries "
                                f"{body.count('BEGIN CERTIFICATE')} certificates, "
                                "so certifi and the local root are not both in it")
            leftover = [p.name for p in box.glob("*.partial")]
            if leftover:
                failures.append(f"a healthy merge left {leftover} behind")

            # A refused rename must not cost the bundle that was already there.
            #
            # The rebuild is triggered by pushing the BUNDLE's mtime into 1970
            # rather than by touching the source. ca_bundle() returns the file
            # unchanged when its mtime is >= the newest source, and a source
            # rewritten in the same instant as the bundle was written compares
            # equal on a filesystem whose timestamps are coarser than the two
            # writes. This claim passed by luck for one run and then failed on
            # the next with "a refused rename did not raise", because the
            # rebuild never happened and the patched os.replace was never
            # reached. An intermittent claim is worse than none: it teaches its
            # reader that a red suite means nothing.
            good = body
            extra.write_text(_FAKE_CERT * 2, encoding="utf-8")
            _os.utime(target, (0, 0))

            def refuse(src: Any, dst: Any) -> None:
                raise PermissionError("Norton denied the rename")

            _os.replace = refuse
            try:
                config.ca_bundle()
                failures.append("a refused rename did not raise, so the caller "
                                "would go on believing the bundle was rebuilt")
            except PermissionError:
                pass
            finally:
                _os.replace = real_replace
            after = target.read_text(encoding="utf-8") if target.is_file() else ""
            if after != good:
                failures.append("a refused rename changed the bundle on disk, "
                                f"so the served file is neither the old one nor "
                                f"a whole new one ({len(after)} bytes against "
                                f"{len(good)})")
            leftover = [p.name for p in box.glob("*.partial")]
            if leftover:
                failures.append(f"a refused rename left {leftover} behind")

            # A source with no certificate in it refuses the merge outright.
            target.unlink(missing_ok=True)
            extra.write_text("# this file lost its contents\n", encoding="utf-8")
            served = config.ca_bundle()
            if served is not True:
                failures.append("a source carrying no certificate still produced "
                                f"a bundle ({served!r}), so a trust store missing "
                                "the inspection root would be handed to requests")
            if target.exists():
                failures.append("a source carrying no certificate was written to "
                                "the bundle anyway")
        finally:
            config.CA_BUNDLE_PATH = real_path
            config._extra_ca_files = real_extras
            _os.replace = real_replace

    print("  trust store  a denied rename keeps the whole previous bundle, and "
          "a source with no certificate refuses the merge")


def claim_the_rotation_study_counts_no_warm_up_session(
        failures: list[str]) -> None:
    """The float rotation bands are not fitted on the script's own cold start.

    float_rotation_study builds its RVOL baseline from a `history` dict that
    starts EMPTY and is filled by the same loop that tallies. For the first
    [Baseline] min_sessions_for_rvol sessions nothing can clear the floor, so
    rvol is None for every name, so every addressable name with a usable float
    lands in `rescued`, which is the population the CRITERIA [Float rotation]
    band edges are read off. Not because the name has no baseline. Because the
    script has not warmed up.

    Measured on the archived payload DECISIONS.md quotes: 894 of 2,464 rescued
    rows, 36.3 percent, from the first ten sessions, at a rescue rate of 84 to
    93 percent against 7 to 22 percent from the eleventh onward. This replays
    that measurement so the decision entry stays reproducible from the file
    rather than from a number somebody wrote down, and it checks the gate that
    stops it recurring.
    """
    import ast as _ast

    from research import float_rotation_study as study

    floor = 10
    for rolled, wanted in ((0, False), (floor - 1, False),
                           (floor, True), (floor + 1, True)):
        got = study.warmup_over(rolled, floor)
        if got is not wanted:
            failures.append(f"warmup_over({rolled}, {floor}) is {got}, so the "
                            "boundary the whole correction turns on has moved")

    # The gate has to be IN run(), and the warm up branch has to roll the
    # history it declines to tally, or the boundary simply slides.
    source = pathlib.Path(study.__file__).read_bytes().decode("utf-8")
    tree = _ast.parse(source)
    run_def = next((node for node in tree.body
                    if isinstance(node, _ast.FunctionDef) and node.name == "run"),
                   None)
    if run_def is None:
        failures.append("float_rotation_study.run is gone, so nothing below "
                        "describes the module that exists")
        return
    called = [n.func.id for n in _ast.walk(run_def)
              if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)]
    if "warmup_over" not in called:
        failures.append("run() no longer calls warmup_over, so the warm up "
                        "sessions are being tallied again")
    if called.count("roll_forward") < 2:
        failures.append("run() calls roll_forward "
                        f"{called.count('roll_forward')} time(s). The warm up "
                        "branch must roll the history it refuses to count, or "
                        "the baseline never warms up at all")

    payload = (config.PROJECT_ROOT / "doc" / "research"
               / "float_rotation_study-2026-08-17-postfix.json")
    if not payload.is_file():
        failures.append(f"{payload.name} is gone, so the 2026-08-20 decision "
                        "entry can no longer be reproduced from the evidence")
        return
    rows = json.loads(payload.read_text(encoding="utf-8")).get("per_session") or []
    if len(rows) != 61:
        failures.append(f"the archived payload holds {len(rows)} sessions rather "
                        "than the 61 the decision entry was measured over")
        return
    total = sum(r["rescued_by_rotation"] for r in rows)
    warm = sum(r["rescued_by_rotation"] for r in rows[:floor])
    if total != 2464 or warm != 894:
        failures.append(f"the archived payload now reads {warm} of {total} "
                        "rescued rows from the first ten sessions, where the "
                        "decision entry says 894 of 2,464")
    rates = [r["rescued_by_rotation"] / r["addressable"]
             for r in rows if r.get("addressable")]
    if min(rates[:floor]) < 0.80:
        failures.append(f"the warm up sessions rescue as little as "
                        f"{min(rates[:floor]):.0%}, so the discontinuity the "
                        "entry rests on is not in the file")
    if max(rates[floor:floor + 10]) > 0.30:
        failures.append(f"the ten sessions after the warm up rescue up to "
                        f"{max(rates[floor:floor + 10]):.0%}, so there is no "
                        "discontinuity at the boundary after all")

    print(f"  warm up      the study refuses to tally a session it cannot score, "
          f"and the archive still shows {warm} of {total} rescued rows in the "
          "first ten")


def claim_both_volume_ratios_divide_the_same_tape(failures: list[str]) -> None:
    """Both volume measures divide a whole tape estimate, not the socket's share.

    The defect. premarket RVOL divided COLLECTOR socket volume by a baseline
    collect/baseline.py builds from the vendor's 1m intraday bars, and float
    rotation divided the same socket numerator by a company share count against
    bands fitted on Alpaca volume. Both denominators are whole tape
    measurements and the numerator was a fraction of one, so both ratios
    understated by about the reciprocal of that fraction. The [Day setup]
    premarket_rvol floor of 1.5 was being applied to a value that could not
    reach it: six mornings, 62 candidates, zero day eligible ever, 19 of them
    failing on that line alone.

    The correction, and what makes it legitimate rather than a fudge. The share
    is a stable property of a symbol: over the four sessions from 2026-08-17
    the median symbol varies by 1.48 times across sessions while the error
    being corrected is about nine. So the socket's shares are divided by the
    share to estimate what the consolidated tape would have shown, and both
    ratios divide THAT.

    Four things are asserted, and the last two are the ones that would let this
    go wrong quietly.

    That the arithmetic is the arithmetic, on both measures, so a future edit
    cannot put one of them back on the raw numerator while the other moves.

    That pm_volume still holds the shares the collector actually saw. It is an
    observation and the estimate is a separate field, because a project rule
    older than this correction says missing or inferred evidence is never
    substituted for the real thing under the same name.

    That a symbol the newest volume check measured uses its OWN share rather
    than the file default, since the default exists for symbols nothing has
    been measured for and silently preferring it would throw away the better
    number.

    And that a caller who skips attach_capture_estimate does not get the old
    broken arithmetic back. That was a real seam: attach_float_rotation is
    called directly in two other suites, and the first version of this
    correction returned a null rotation for them rather than a corrected one.
    A hard ordering dependency between two attach functions is exactly the kind
    of seam this file exists to catch, so the fallback computes the default
    estimate and records that it did.
    """
    from core import criteria as _criteria
    from morning import scan as _scan

    crit = _criteria.load()
    default = crit.number("collector", "premarket_capture_rate")
    floor = crit.rule("day_setup", "premarket_rvol")

    check = {
        "day": "2026-08-20",
        "aggregate_ratio": 0.09,
        # AAA's own share is deliberately NOT the default, so a lookup that
        # silently fell back would change the answer and be caught.
        # Well over CRITERIA [Collector] min_capture_vendor_volume, because
        # the point of this fixture is a symbol whose own share IS trusted.
        # It was 20 against 100 until 2026-08-21 and the evidence floor
        # correctly refused it, which is the floor working and the fixture
        # being wrong.
        "volume_by_symbol": {"AAA.US": {"collector": 20_000.0,
                                        "vendor": 100_000.0}},
        "minutes_compared_by_symbol": {"AAA.US": 90},
    }
    candidates = [
        {"symbol": "AAA.US", "pm_volume": 100_000.0, "collector_covered": True},
        {"symbol": "BBB.US", "pm_volume": 100_000.0, "collector_covered": True},
        {"symbol": "CCC.US", "pm_volume": None, "collector_covered": True},
    ]
    _scan.attach_capture_estimate(candidates, check, _scan.Packet())

    if candidates[0].get("pm_capture_share") != 0.2:
        failures.append(
            f"AAA used a capture share of {candidates[0].get('pm_capture_share')!r} "
            "where the check measured it at 0.2. A symbol the check carries must "
            "use its own share, not the file default")
    if candidates[0].get("pm_volume_consolidated") != 500_000.0:
        failures.append(
            f"AAA estimates {candidates[0].get('pm_volume_consolidated')!r} "
            "consolidated shares where 100,000 socket shares at a fifth of the "
            "tape is 500,000")
    if candidates[1].get("pm_capture_share") != round(default, 6):
        failures.append(
            f"BBB, which the check does not carry, used "
            f"{candidates[1].get('pm_capture_share')!r} rather than CRITERIA's "
            f"{default}")
    if candidates[0].get("pm_volume") != 100_000.0:
        failures.append(
            "pm_volume was overwritten with the estimate. It is what the "
            "collector saw, and an observation does not get replaced by an "
            "inference under its own name")
    if candidates[2].get("pm_volume_consolidated") is not None:
        failures.append(
            "a candidate with no collector volume was given an estimate "
            f"anyway, {candidates[2].get('pm_volume_consolidated')!r}")

    # RVOL through the REAL function, with a baseline row written for it.
    # Computing the ratio here instead was a hole: a mutation putting scan's
    # own line back on the raw socket numerator ran green against the first
    # version of this claim, because the test was checking its own arithmetic.
    from collect import baseline as _baseline
    from core import store as _store

    cutoff = "08:45"
    with _store.session() as connection:
        _store.init(connection)
        connection.execute(
            "INSERT OR REPLACE INTO baseline "
            "(ticker, cutoff_hhmm, median_volume, sessions_used, computed_at) "
            "VALUES (?,?,?,?,?)",
            ("AAA.US", _baseline.normalize_cutoff(cutoff), 250_000.0, 20,
             ettime.now_et().isoformat()))
        connection.commit()

    live = dict(candidates[0])
    _scan.attach_premarket_rvol([live], _scan.Packet(), cutoff)
    if live.get("pm_rvol") != 2.0:
        failures.append(
            f"attach_premarket_rvol gives {live.get('pm_rvol')!r} for 100,000 "
            "socket shares at a fifth of the tape against a 250,000 baseline, "
            "where 500,000 over 250,000 is 2.0. A value near 0.4 means the "
            f"numerator is back on the raw socket volume ({live.get('pm_rvol_reason')})")
    if not floor.test(live.get("pm_rvol")):
        failures.append(
            f"a name at {live.get('pm_rvol')!r} does not clear "
            f"{floor.describe()}, which is the whole thing this correction was "
            "made for")
    basis = live.get("pm_rvol_basis") or {}
    if basis.get("numerator_socket_shares") != 100_000.0:
        failures.append(
            "the RVOL basis does not publish the socket shares behind its "
            f"estimated numerator, it carries {basis.get('numerator_socket_shares')!r}. "
            "A corrected number whose raw input cannot be recovered is not "
            "auditable")

    # The default itself, against the measurement it came from rather than
    # against the file it is written in. Reading CRITERIA and comparing it to
    # CRITERIA was the second hole: setting the rate to 1.0, which asserts the
    # two tapes agree, moved both sides of that comparison together.
    payload = (config.PROJECT_ROOT / "doc" / "research" / "collector-capture.json")
    if not payload.is_file():
        failures.append(f"{payload.name} is gone, so the capture rate in "
                        "CRITERIA can no longer be traced to a measurement")
    else:
        import statistics as _stats

        clean = {"2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"}
        table = json.loads(payload.read_text(encoding="utf-8"))
        medians = []
        for rates in (table.get("per_symbol") or {}).values():
            kept = [v for k, v in rates.items() if k in clean]
            if kept:
                medians.append(_stats.median(kept))
        if not medians:
            failures.append("the capture table holds no rates on the four clean "
                            "sessions, so the default cannot be re-derived")
        else:
            wanted = round(_stats.median(medians), 4)
            if default != wanted:
                failures.append(
                    f"CRITERIA [Collector] premarket_capture_rate is {default} "
                    f"where the measurement it cites re-derives {wanted} over "
                    f"{len(medians)} symbols. A rate of 1.0 in particular "
                    "asserts the socket and the vendor see the same tape, "
                    "which is the claim this whole correction refutes")

    # The seam: attach_float_rotation called on its own, as two other suites do.
    alone = {"symbol": "DDD.US", "collector_covered": True,
             "pm_volume": 100_000.0,
             "quote": {"sharesFloat": 20_000_000.0,
                       "sharesOutstanding": 25_000_000.0, "marketCap": 3e9}}
    _scan.attach_float_rotation([alone], _scan.Packet())
    wanted = round(round(100_000.0 / default, 2) / 20_000_000.0, 8)
    if alone.get("pm_float_rotation") != wanted:
        failures.append(
            f"float rotation without attach_capture_estimate came back "
            f"{alone.get('pm_float_rotation')!r} rather than {wanted}. A caller "
            "that skips the attach step must get the default estimate, never "
            "the raw socket numerator and never a null")
    if not alone.get("pm_capture_basis"):
        failures.append(
            "the fallback estimate records no basis, so a reader cannot tell a "
            "per symbol measurement from a file wide default")

    # And the report that makes the correction auditable.
    priced = [dict(candidates[0], pm_rvol=2.0)]
    block = _scan.capture_correction_report(priced, _scan.Packet())
    if not block or block.get("carried_across_the_floor") != ["AAA.US"]:
        failures.append(
            f"the correction report does not name AAA as carried across "
            f"{floor.describe()}: {block!r}. Its raw ratio is 0.4 and its "
            "corrected one is 2.0, and a correction that moves a name onto a "
            "watchlist without saying so is worse than the defect it fixes")

    # What the code SAYS it divides, in the three places a reader looks it up.
    # Both docstrings and the day screen's own comment still called the
    # numerator "collector premarket volume" a day after commit a62429b made
    # both functions divide the estimate. A definition that names the wrong
    # tape is the defect this whole correction exists to fix, sitting in the
    # two functions doing the correcting and in the file that is the single
    # source of truth for the threshold.
    stale = "collector premarket volume divided"
    for where, text in (
            ("attach_premarket_rvol", _scan.attach_premarket_rvol.__doc__ or ""),
            ("attach_float_rotation",
             _scan.attach_float_rotation.__doc__ or ""),
            ("CRITERIA [Day setup]",
             (config.DOC_DIR / "CRITERIA.md").read_text(encoding="utf-8")
             .split("## Swing setup")[0])):
        if stale in text.lower():
            failures.append(
                f"{where} still defines the ratio as {stale!r}. It divides an "
                "ESTIMATE of the consolidated tape, and a reader who takes the "
                "definition at its word reapplies a nine times correction in "
                "their head, which is the exact error the first live report "
                "published")

    print("  one tape     RVOL and float rotation both divide the consolidated "
          "estimate, pm_volume still holds what the socket saw, the "
          "correction names what it moved, and all three definitions of the "
          "numerator name the estimate")


def claim_a_thin_capture_share_is_refused_rather_than_divided_by(
        failures: list[str]) -> None:
    """A capture share is a ratio of two volumes and inherits the smaller one.

    The correction divides the socket's shares by the symbol's measured share
    of the tape. That share is itself a measurement, and on 2026-08-20 three of
    the forty eight the check carried rested on almost nothing: UUP was ten
    vendor shares against ten collector shares over ONE minute, which produces
    a share of 1.0000 and therefore no correction at all for a symbol that
    ordinarily captures about a tenth. VNET on 2026-08-19 produced 1.1800,
    which is impossible: a socket carrying a subset of the tape cannot report
    more than all of it.

    A share of 1.0 is the whole defect back again for that one row, arriving
    through the fix. So the EVIDENCE is floored, never the ratio capped, which
    is the argument [Baseline]'s denominator floor note already makes: a cap
    turns a visible absurdity into an invisible one.

    Three refusals, each with its own reason recorded, and the fallback in
    every case is CRITERIA's measured default rather than a null, because a
    symbol with a thin measurement is not a symbol with no evidence at all.
    """
    from core import criteria as _criteria
    from morning import scan as _scan

    crit = _criteria.load()
    default = crit.number("collector", "premarket_capture_rate")
    min_vendor = crit.number("collector", "min_capture_vendor_volume")
    min_minutes = crit.integer("collector", "min_capture_minutes")

    check = {
        "day": "2026-08-20",
        "volume_by_symbol": {
            "GOOD.US": {"collector": 20_000.0, "vendor": 100_000.0},
            "THIN.US": {"collector": 1.0, "vendor": min_vendor - 1},
            "BRIEF.US": {"collector": 20_000.0, "vendor": 100_000.0},
            "IMPOSSIBLE.US": {"collector": 118_000.0, "vendor": 100_000.0},
        },
        "minutes_compared_by_symbol": {
            "GOOD.US": 90, "THIN.US": 90,
            "BRIEF.US": min_minutes - 1, "IMPOSSIBLE.US": 90,
        },
    }
    names = ["GOOD.US", "THIN.US", "BRIEF.US", "IMPOSSIBLE.US"]
    candidates = [{"symbol": s, "pm_volume": 100_000.0} for s in names]
    _scan.attach_capture_estimate(candidates, check, _scan.Packet())
    got = {c["symbol"]: c for c in candidates}

    if got["GOOD.US"]["pm_capture_share"] != 0.2:
        failures.append(
            f"a well measured share came back "
            f"{got['GOOD.US']['pm_capture_share']!r} rather than 0.2, so the "
            "floors are refusing measurements they should be admitting")
    if got["GOOD.US"].get("pm_capture_minutes") != 90:
        failures.append(
            "a trusted share does not record how many common minutes backed "
            f"it, it carries {got['GOOD.US'].get('pm_capture_minutes')!r}. A "
            "share measured over two minutes and one over ninety are not the "
            "same evidence and no reader can tell them apart without it")

    for symbol, why in (("THIN.US", "vendor share"),
                        ("BRIEF.US", "common minute"),
                        ("IMPOSSIBLE.US", "cannot report all of it")):
        row = got[symbol]
        if row["pm_capture_share"] != round(default, 6):
            failures.append(
                f"{symbol} kept a share of {row['pm_capture_share']!r} where "
                f"its measurement should have been refused and the default "
                f"{default} used instead")
        basis = str(row.get("pm_capture_basis") or "")
        if "refused" not in basis or why not in basis:
            failures.append(
                f"{symbol} fell back without saying why: {basis!r}. A silent "
                "fallback is indistinguishable from a symbol the check never "
                "carried, and those are different facts")
        if row.get("pm_capture_minutes") is not None:
            failures.append(
                f"{symbol} recorded {row['pm_capture_minutes']!r} common "
                "minutes for a share that was refused, which reads as though "
                "the refused measurement is the one in use")

    # The impossible value is refused for being impossible, not for being thin,
    # so it must still be refused when the volume behind it is ample.
    if got["IMPOSSIBLE.US"]["pm_capture_share"] == 1.18:
        failures.append(
            "a share of 1.18 survived on 100,000 vendor shares. A socket "
            "carrying a subset of the tape reporting more than all of it is a "
            "broken measurement at any volume")

    print("  thin share   a capture share on ten shares or one minute, or one "
          "above unity, is refused for the measured default and says which")


def claim_the_packet_never_asks_for_the_correction_to_be_applied_twice(
        failures: list[str]) -> None:
    """The measured feed gap is the correction's INPUT, not a residual on top.

    This is the defect the first live morning shipped. attach_capture_estimate
    divides the collector versus vendor disagreement out per symbol, and
    volume_check went on writing "Every RVOL and every float rotation in this
    packet is UNDERSTATED by about that much again" into the same gaps_to_fill
    list. The model narrates what the packet asserts, so runs/2026-08-21/report.md
    published it twice, telling a reader that MSTR's 3.38 understates by 87
    percent when 3.38 already carries that correction.

    Applying a nine times correction a second time in the reader's head is the
    same size of error as the defect the correction was built to fix, pointed
    the other way, and it is worse in kind: the first was a number nobody could
    see, this one is an instruction.

    So the packet is asserted to carry the correct relationship and NOT to
    carry the old one, in both the signed and unsigned branches, and the
    fallback report is checked for the same contradiction it published.
    """
    from morning import analyst as _analyst
    from morning import scan as _scan

    class Sink:
        def __init__(self):
            self.gaps = []

        def gap(self, text):
            self.gaps.append(text)

    def gaps_for(summary):
        day = summary["day"]
        target = config.run_dir(day)
        target.mkdir(parents=True, exist_ok=True)
        (target / "verify_intraday.json").write_text(
            json.dumps(summary), encoding="utf-8")
        sink = Sink()
        after = (ettime.parse_date(day) + dt.timedelta(days=1)).isoformat()
        _scan.volume_check(after, sink)
        return " ".join(sink.gaps)

    signed = gaps_for({
        "day": "2026-08-19", "compared": 73, "within_one_percent": 0,
        "median_abs_pct": 90.0, "unavailable": 0, "median_signed_pct": -90.0,
        "direction": "under", "aggregate_ratio": 0.1, "sign_recorded": True,
        "direction_phrase": "the collector recorded LESS than the vendor"})

    banned = ["UNDERSTATED by about that much again",
              "OVERSTATED by about that much",
              "passes straight into the ratios"]
    for phrase in banned:
        if phrase in signed:
            failures.append(
                f"the packet still tells the model {phrase!r}. The correction "
                "already divided that out, so the report applies it twice")
    if "divides out" not in signed:
        failures.append(
            "the packet does not say the measured gap is what the capture "
            f"correction divides out: {signed}")
    if "LOWER BOUND" not in signed or "window" not in signed:
        failures.append(
            "the packet no longer names the WINDOW as the remaining reason a "
            "ratio is a lower bound. That one is still true and is the only "
            f"one left: {signed}")

    # The fallback report is the other place the contradiction lived, and it
    # said both things inside one document.
    packet = {
        "session_date": "2026-08-20", "candidates": [],
        "collector_volume_check": {
            "day": "2026-08-19", "compared": 73, "within_one_percent": 0,
            "median_abs_pct": 90.0, "direction": "under",
            "direction_phrase": "the collector recorded LESS than the vendor",
            "aggregate_ratio": 0.1},
        "capture_correction": {
            "candidates": 3, "clear_on_socket_volume": 0,
            "clear_on_consolidated_estimate": 2,
            "carried_across_the_floor": ["AAA.US", "BBB.US"],
            "carried_onto_the_day_watchlist": ["AAA.US"], "floor": "> 1.5"},
    }
    text = _analyst.fallback_report(packet, "the claim asked for it")
    if "divide a collector numerator" in text:
        failures.append(
            "the fallback still says the RVOL figures divide a collector "
            "numerator, in the same document that says they are an estimate of "
            "consolidated volume. One report, two answers")

    # A floor is not a watchlist. BBB cleared the floor and is not on the list.
    if "put BBB on this list" in text or "AAA, BBB on this list" in text:
        failures.append(
            "the fallback claims BBB reached the day watchlist. It cleared the "
            "volume floor and failed another day condition, which is what the "
            "two sets exist to keep apart")
    if "BBB" not in text:
        failures.append(
            "the fallback drops BBB entirely. A name the correction carried "
            "across the floor and no further is worth one clause, or the "
            "correction's effect is understated")

    # And the two sets through the REAL function, because building the packet
    # dict by hand above tests this claim's own arithmetic. A mutation that
    # collapsed carried_onto_the_day_watchlist back into carried_across_the_floor
    # ran green until this was added.
    floor_only = {"symbol": "FLOOR.US", "pm_rvol": 2.0,
                  "pm_capture_share": 0.1, "day_eligible": False,
                  "day_failed_conditions": ["above_prior_high"]}
    made_it = {"symbol": "LIST.US", "pm_rvol": 2.0, "pm_capture_share": 0.1,
               "day_eligible": True, "day_failed_conditions": []}
    block = _scan.capture_correction_report([floor_only, made_it], Sink())
    if not block:
        failures.append("capture_correction_report returned nothing for two "
                        "candidates carrying an RVOL and a share")
        return
    if sorted(block.get("carried_across_the_floor") or []) != ["FLOOR.US", "LIST.US"]:
        failures.append(
            f"the floor set is {block.get('carried_across_the_floor')!r}. Both "
            "candidates went from 0.2 raw to 2.0 corrected, so both crossed it")
    if (block.get("carried_onto_the_day_watchlist") or []) != ["LIST.US"]:
        failures.append(
            f"the watchlist set is {block.get('carried_onto_the_day_watchlist')!r} "
            "rather than just LIST.US. FLOOR.US cleared the volume floor and "
            "failed the prior high, and collapsing the two sets is what "
            "published a false membership claim on 2026-08-21")

    print("  no rebound   the packet calls the measured feed gap the "
          "correction's input, keeps a floor apart from a watchlist, and "
          "neither report applies the correction a second time")


def claim_a_probe_reading_its_own_noise_cannot_beat_is_refused(
        failures: list[str]) -> None:
    """A ratio is not a reading unless it beats the instrument that made it.

    probe_socket_cap exists to answer one question: does the 50 symbol socket
    cap starve delivery. It answers by comparing message rates at 8 and 50
    subscriptions, and until 2026-08-21 it printed a median of those ratios
    with a sentence reading anything well below 1 as the cap starving
    delivery, and nothing at all about the sample behind it.

    Both existing runs fail that standard, in opposite ways. On 2026-08-21 the
    premarket tape carried 123 trade messages across 8 symbols in 14 minutes of
    arm time; IWM's printed 0.14 was 49 messages against 9 and UUP's 0.00 was
    one against none, and the median printed as 0.58. On 2026-08-19 the tape
    was 65 times richer, 8,056 messages, and the median printed as 0.87. A
    reader holding both would conclude the cap bites in premarket and not in
    the session, when the entire difference between them is how much tape there
    was.

    The instrument's own noise settles it and is measurable from what the probe
    already collects: recomputing each symbol's ratio per cycle, with nothing
    about the cap changing between them, the well measured symbols still moved
    by a factor of 2.4. The effect being looked for is the same size. So a
    median inside that spread separates nothing, and saying so is the reading.

    Two refusals, then, and both are asserted through _report_delivery rather
    than recomputed here: too few messages behind a ratio, and a median the
    run's own dispersion cannot beat.
    """
    from research import probe_socket_cap as _probe

    # The fixtures are the two runs that ACTUALLY HAPPENED, message counts
    # copied from data/socket-cap-probe-2026-08-19.json and -08-21.json. A
    # fixture derived from the floor moves when the floor does, and the first
    # version of this claim did exactly that: setting the floor to zero left
    # it green. These pin the floor into a corridor instead, above 2 so UUP's
    # three messages are refused and at or below 32 so USO's are not, without
    # the claim ever reading the value.
    watch = ["X.US"]

    def legs(pairs, seconds=(100.0, 100.0)):
        runs = []
        for cycle, (count_a, count_b) in enumerate(pairs, start=1):
            for arm, count, secs in (("A", count_a, seconds[0]),
                                     ("B", count_b, seconds[1])):
                runs.append({
                    "arm": arm, "cycle": cycle, "seconds": secs,
                    "counts": {"X.US": count},
                    "volume": {"X.US": float(count)},
                    "refused": False,
                })
        return runs

    def read(runs: list[dict[str, Any]], names=None) -> dict[str, Any]:
        with contextlib.redirect_stdout(io.StringIO()) as sink:
            verdict = _probe._report_delivery(runs, names or watch)
        verdict["printed"] = sink.getvalue()
        return verdict

    def session(counts: dict[str, tuple[int, int]], seconds):
        runs = []
        for arm, index, secs in (("A", 0, seconds[0]), ("B", 1, seconds[1])):
            runs.append({
                "arm": arm, "cycle": 1, "seconds": secs, "refused": False,
                "counts": {s: v[index] for s, v in counts.items()},
                "volume": {s: float(v[index]) for s, v in counts.items()},
            })
        return runs, list(counts)

    # 1. The premarket run of 2026-08-21, exactly as it came off the socket.
    #    123 messages over eight symbols, and it printed a median of 0.58.
    runs, names = session({
        "SPY.US": (11, 4), "QQQ.US": (18, 14), "IWM.US": (49, 9),
        "DIA.US": (0, 0), "TLT.US": (2, 9), "USO.US": (1, 4),
        "UUP.US": (1, 0), "VIXY.US": (0, 1),
    }, (360.0, 480.0))
    thin = read(runs, names)
    if thin["median_b_over_a"] is not None:
        failures.append(
            f"the 2026-08-21 premarket run published a median of "
            f"{thin['median_b_over_a']!r}. Its richest symbol was 49 messages "
            "against 9 and its whole tape was 123 messages, which measures "
            "when trades happened rather than whether the cap starved delivery")
    if "NO READING" not in thin["printed"]:
        failures.append(
            "the probe does not say it has no reading when no symbol carried "
            f"enough messages: {thin['printed']!r}")
    # QQQ is the best of them on 14, not IWM on 49: the ratio rests on the
    # SMALLER arm, and IWM's 49 against 9 is a nine message measurement wearing
    # a big number. The refusal has to lead with the right one or it tells a
    # reader the run came closer than it did. Not asserted against the floor's
    # value, which fixture 2 pins from the other side.
    refusal = thin["printed"].split("NO READING", 1)[-1]
    if "the best being QQQ.US on 14" not in refusal or "49" in refusal:
        failures.append(
            "the refusal does not lead with the SMALLER of the best symbol's "
            "two arms, which is the number a ratio rests on and the number "
            f"that says how far short the run fell: {refusal!r}")

    # 2. The regular hours run of 2026-08-19, 8,056 messages. Everything but
    #    UUP's three against two has to survive, or the floor has been raised
    #    to the point where the probe cannot answer anything.
    rich, rich_names = session({
        "SPY.US": (580, 544), "QQQ.US": (2342, 2863), "IWM.US": (413, 307),
        "DIA.US": (223, 164), "TLT.US": (223, 164), "USO.US": (32, 41),
        "UUP.US": (3, 2), "VIXY.US": (83, 72),
    }, (480.0, 480.0))
    session_run = read(rich, rich_names)
    if session_run["symbols_with_enough"] != 7:
        failures.append(
            f"the 2026-08-19 run admitted {session_run['symbols_with_enough']} "
            "of 8 symbols, not 7. UUP carried three messages against two and "
            "must be refused; USO carried 32 against 41 and must not be, or "
            "the floor has been raised until the probe cannot read anything")
    if session_run["median_b_over_a"] is None or not (
            0.86 < session_run["median_b_over_a"] < 0.88):
        failures.append(
            f"the 2026-08-19 median came out "
            f"{session_run['median_b_over_a']!r} rather than 0.87, so the "
            "reading this file has cited since that day is no longer what the "
            "code produces from the same counts")

    # 2. Enough messages, but the same symbol's ratio moves further across the
    #    run's own cycles than the median sits from 1. This is 2026-08-19.
    noisy = read(legs([(100, 50), (100, 200)]))
    if noisy["median_b_over_a"] is None:
        failures.append(
            "a symbol with 200 and 250 messages was refused as thin. The "
            "floor is meant to remove what cannot be a measurement, not "
            "everything that is imprecise")
    if noisy["own_noise_factor"] is None:
        failures.append(
            "the probe published a median with no measure of how far that "
            "same ratio moves on its own. The cycles it already ran are the "
            "measure and they cost nothing to read")
    if noisy["reading_supported"]:
        failures.append(
            f"a median of {noisy['median_b_over_a']!r} was reported as a "
            f"reading when the same symbol's own ratio moved by "
            f"{noisy['own_noise_factor']!r} across the run's cycles. The "
            "instrument cannot resolve the effect it is being asked about")
    if "INSIDE that noise" not in noisy["printed"]:
        failures.append(
            "the probe prints an unsupported median without saying it is "
            f"inside its own noise: {noisy['printed']!r}")
    for banned in ("cap does not starve delivery", "the fix is to subscribe"):
        if banned in noisy["printed"]:
            failures.append(
                f"the probe still offers {banned!r} off a median its own "
                "dispersion swallows, which is how a null result becomes a "
                "finding")

    # 3. A reading the instrument CAN resolve still gets published, or the
    #    refusals above have quietly turned the probe off.
    clean = read(legs([(1000, 100), (1000, 110)]))
    if not clean["reading_supported"]:
        failures.append(
            f"a median of {clean['median_b_over_a']!r} against a noise factor "
            f"of {clean['own_noise_factor']!r} was refused. A refusal that "
            "fires on a clean separation leaves the probe unable to answer "
            "anything, which is worse than the overclaim it replaced")
    if "cap does not starve delivery" not in clean["printed"]:
        failures.append(
            "a supported reading no longer carries the sentence that says how "
            f"to read it: {clean['printed']!r}")

    # 4. The census must not call the feed's own answer a parser bug. Every
    #    value on 2026-08-21 was c=[] or dp=False, an empty condition list and
    #    an explicit not a dark pool print, and the probe named "a code under
    #    IGNORED" as the fixable case underneath them.
    census_runs = [{
        "arm": "A", "cycle": 1, "seconds": 100.0, "refused": False,
        "counts": {"X.US": 10}, "volume": {"X.US": 10.0},
        "off_exchange": {"X.US": 0}, "off_exchange_volume": {"X.US": 0.0},
        "keys_seen": {"c": 10, "dp": 10, "p": 10, "s": 10, "t": 10, "v": 10},
        "census": {"X.US": {"c=[]": 10, "dp=False": 10}},
    }]
    with contextlib.redirect_stdout(io.StringIO()) as sink:
        _probe._report_off_exchange(census_runs, watch)
    census = sink.getvalue()
    if "fixable case" in census:
        failures.append(
            "an empty condition list and dp=False are read as a code the "
            "parser is dropping. They are the feed ANSWERING the question in "
            "the negative, and pointing at a parser fix that does not exist "
            "is the one mistake this census was built to prevent")
    if "STRUCTURAL" not in census:
        failures.append(
            "the census does not say the shortfall is structural when every "
            f"value the feed sent marks nothing: {census!r}")

    print("  probe noise  a socket cap ratio is refused when too few messages "
          "back it or the run's own cycles move it further than the effect")


def claim_the_prune_deletes_only_what_its_whitelist_names(
        failures: list[str]) -> None:
    """The first thing in this project that deletes on a schedule.

    Nothing under data/ was ever removed automatically before 2026-08-21, so
    this module is the only code in the tree that can destroy evidence without
    a person typing the command. Several things in that directory are the only
    copy: data/premarket holds the collector's own socket capture, which is a
    recording of a tape that no longer exists and cannot be refetched at any
    price, and is also the only record of the 2026-08-14 over count.
    data/backtest/eod is the population the shipped float rotation edges were
    fitted on.

    So what may be deleted is a WHITELIST and not a rule about age. A sweeper
    that took anything older than the window would have reached all of the
    above on its first run. This asserts the containment from the outside: an
    ancient file of every other kind is put in front of it and has to survive.

    It also asserts that the age comes from the FILENAME. The file describes
    the session its name carries whoever copied it and whenever, and an mtime
    rule would spare a file a backup had touched and take one it had not,
    which makes the retention window a property of the filesystem rather than
    of the data.
    """
    import shutil

    from core import criteria as _criteria
    from night import prune_data as _prune

    day = ettime.parse_date("2026-08-21")
    window = _criteria.load().integer("universe", "closes_retention_days")

    # The window has a FLOOR, and it is not derived from the window. The note
    # in CRITERIA argues 7 as margin for a human reading the file by hand, and
    # the shortest span that argument has to survive is a Friday file still
    # being there on Monday. Below three days the key is set to a number its
    # own justification does not support, and every boundary test below would
    # still pass, because a fixture built from the window moves with it. That
    # is how the first version of this claim let a window of zero through.
    if window < 3:
        failures.append(
            f"closes_retention_days is {window}. A Friday file is then gone "
            "before Monday, which is the one span the retention note's own "
            "argument has to cover, and nothing else in this claim can catch "
            "it because the fixtures scale with the window")
    box = pathlib.Path(tempfile.mkdtemp())
    original = config.DATA_DIR
    try:
        config.DATA_DIR = box
        (box / "premarket").mkdir()
        (box / "backtest" / "eod").mkdir(parents=True)

        # Named for a session, which is the only class the whitelist carries.
        over = f"universe-closes-{(day - dt.timedelta(days=window + 1))}.json"
        edge = f"universe-closes-{(day - dt.timedelta(days=window))}.json"
        today_file = f"universe-closes-{day}.json"
        undated = "universe-closes-.json"
        for name in (over, edge, today_file, undated):
            (box / name).write_text("{}", encoding="utf-8")

        # Everything else, all of it older than any window could ever be.
        bystanders = [
            box / "premarket" / "2026-05-01.jsonl",
            box / "premarket" / "2026-05-01-stats.jsonl",
            box / "backtest" / "eod" / "2026-05-01.json",
            box / "float_cache.json",
            box / "purged-picks-2026-05-01.jsonl",
            box / "socket-cap-probe-2026-05-01.json",
            box / "UNVERIFIED",
        ]
        for path in bystanders:
            path.write_text("keep me", encoding="utf-8")

        # The mtime says the opposite of the filename on both sides, so a rule
        # reading the clock instead of the name gets both of them wrong.
        ancient = 1000000000.0
        fresh = 1900000000.0
        os.utime(box / over, (fresh, fresh))
        os.utime(box / today_file, (ancient, ancient))

        result = _prune.prune(today=day)

        if (box / over).exists():
            failures.append(
                f"{over} is {window + 1} days old against a {window} day "
                "window and survived. Nothing in the tree can read it: it is "
                "written by discover for one session and read by that same "
                "session's scan, and there is no way to ask for a past one")
        if not (box / edge).exists():
            failures.append(
                f"{edge} is exactly {window} days old and was deleted. The "
                "window is how many days are KEPT, so the boundary day is "
                "inside it and a reader who counted back that far still finds "
                "the file")
        if not (box / today_file).exists():
            failures.append(
                "this morning's own closes file was deleted. Its mtime is "
                "ancient and its NAME is today, and the name is the session it "
                "describes. Deleting it mid morning would take out the file "
                "the 08:45 scan is about to read")
        if not (box / undated).exists():
            failures.append(
                "a file matching the glob but carrying no readable date was "
                "deleted on a guess. An unparseable name is a reason to leave "
                "it alone and say so, not to assume it is old")

        for path in bystanders:
            if not path.exists():
                failures.append(
                    f"{path.relative_to(box).as_posix()} was deleted. It is "
                    "months old and it is not in PRUNABLE, and several files "
                    "in that position are the only copy that exists")

        # And the report has to say what it left, or a night where the glob
        # silently stopped matching reads exactly like a night it did its job.
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            _prune.report(_prune.prune(dry_run=True, today=day))
        text = printed.getvalue()
        if "kept" not in text or edge not in text:
            failures.append(
                f"the prune reports what it took and not what it kept: {text!r}")
        if "were not looked at" not in text:
            failures.append(
                "the prune does not say which directories it never examined. "
                "That sentence is the difference between a whitelist and a "
                "sweeper that happened to find nothing")

        # A second run must be a no-op rather than an error, because the
        # monitor reruns the nightly and a step that cannot be rerun safely
        # cannot be in it.
        again = _prune.prune(today=day)
        if again["removed"] or again["failed"]:
            failures.append(
                f"a second prune on the same day did something: "
                f"{again['removed']} removed, {again['failed']} failed. The "
                "monitor reruns the nightly, so every step in it has to be "
                "idempotent")
    finally:
        config.DATA_DIR = original
        shutil.rmtree(box, ignore_errors=True)

    if result["freed"] <= 0:
        failures.append(
            "the prune reported no bytes freed on a run that deleted a file, "
            "so the one number telling a reader whether this step is worth "
            "its two meter calls is wrong")

    print("  prune        only the whitelisted file class is deletable, the "
          "date comes from the name, and an ancient file of every other kind "
          "survives")


def claim_the_truth_pass_writes_beside_the_morning_and_never_over_it(
        failures: list[str]) -> None:
    """The record's volume comes from Alpaca, not from a multiplier.

    The morning divides socket volume by one number, 0.1172. The night measures
    what the volume actually was. On the first session measured, 2026-08-21,
    the real per symbol capture ran 0.0288 to 0.3187 over the collector's own
    window: an eleven fold spread against a single divisor, with eight of the
    twelve names below the shipped figure and therefore understated by it.

    Four properties, each of which the first working version of this module got
    wrong or nearly did.

    THE WINDOW IS NOT GUESSED. It ends at the packet's rvol_cutoff_hhmm, which
    the morning snaps to [Scan] run_time only inside a snap window, so a rerun
    genuinely has a different clock. A truth measured over a wider window than
    the estimate is too large by whatever the extra minutes carried, and that
    error looks exactly like the socket missing more of the tape. With no
    packet the pass writes nothing and says why.

    CAPTURE IS MEASURED ON THE SOCKET'S OWN WINDOW. The collector starts at
    07:20 and the premarket opens at 04:00, so dividing what the socket
    recorded by the whole premarket folds its late start into a number meant to
    measure the feed. The first run of this module did exactly that and put the
    capture at 0.0254 for a symbol whose real same minutes capture was 0.0664.
    Two shortfalls, two fixes: one is a subscription question, the other a
    start time question, and collector_window_share measures the second for the
    first time.

    NOTHING THE MORNING WROTE IS TOUCHED. pm_rvol stays what was published at
    08:45 whatever the night finds, on the pm_high_true precedent.

    AND A MISSING MEASUREMENT IS NULL WITH A REASON, never zero. A window with
    no bars and a window nobody asked about are different facts.
    """
    import shutil

    from core import store
    from night import true_volume as _truth

    class Fake:
        """One canned answer per (start, end), and a record of what was asked."""

        def __init__(self, by_window):
            self.by_window = by_window
            self.asked: list[tuple[str, str]] = []
            self.request_count = 0

        def get(self, params):
            self.request_count += 1
            key = (params["start"][11:16], params["end"][11:16])
            self.asked.append((params["start"][:10], *key))
            bars = self.by_window.get(key, {})
            return 200, {"bars": {s: [{"v": v}] for s, v in bars.items()}}, 0.0

    day = "2026-08-21"
    # The isolation travels with the claim rather than with the runner. See
    # conftest.isolated_store: this claim is the reason it exists.
    with conftest.isolated_store():

        with store.session() as connection:
            store.init(connection)
            store.upsert(connection, "picks", ["date", "ticker"], {
                "date": day, "ticker": "AAA.US", "source": "live",
                "pm_volume": 1000.0, "pm_volume_estimated": 8532.0,
                "pm_rvol": 2.5,
            })
            store.upsert(connection, "picks", ["date", "ticker"], {
                "date": day, "ticker": "BBB.US", "source": "live",
                "pm_volume": 40.0, "pm_volume_estimated": 341.0,
                "pm_rvol": 0.9,
            })
            connection.commit()

        # No packet yet. The window is unknown and must not be invented.
        blind = _truth.measure(day, probe=Fake({}))
        if blind["rows"] or not blind["skipped"]:
            failures.append(
                f"the truth pass ran without a packet: {blind!r}. The window "
                "the morning used is in the packet and nowhere else, and a "
                "guessed window mismeasures precisely the sessions that went "
                "wrong")

        run_dir = config.run_dir(day)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "packet.json").write_text(json.dumps({
            "session_date": day,
            # NOT 08:45. A pass that reads a constant passes on the usual
            # morning and is wrong on exactly the reruns worth reading.
            "rvol_cutoff_hhmm": "09:10",
            "candidates": [
                {"symbol": "AAA.US", "quote": {"sharesFloat": 1_000_000.0}},
                {"symbol": "BBB.US", "quote": {"sharesFloat": None}},
            ],
        }), encoding="utf-8")

        # 10,000 shares over the whole premarket, 4,000 of them after 07:20.
        # A socket that saw 1,000 captured a QUARTER of the minutes it was
        # listening to, not a tenth of the session it was mostly absent for.
        probe = Fake({
            ("04:00", "09:10"): {"AAA": 10000.0, "BBB": 500.0},
            ("07:20", "09:10"): {"AAA": 4000.0, "BBB": 200.0},
        })
        result = _truth.measure(day, probe=probe)
        rows = {row["ticker"]: row for row in result["rows"]}

        if result["window"] != "04:00-09:10":
            failures.append(
                f"the measured window is {result['window']!r}, not the "
                "04:00-09:10 the packet asked for. The cutoff is the morning's "
                "own and reading a constant here mismeasures every rerun")
        windows = {(start, end) for _day, start, end in probe.asked}
        if ("07:20", "09:10") not in windows:
            failures.append(
                "the collector's own 07:20 window was never fetched, so "
                "capture_observed can only be socket volume over a window the "
                "socket was absent for most of, which is the late start and "
                "the feed gap added together and called one number")

        aaa = rows["AAA.US"]
        if aaa["capture_observed"] != 0.25:
            failures.append(
                f"capture_observed is {aaa['capture_observed']!r}, not 0.25. "
                "1,000 socket shares against the 4,000 that traded while the "
                "socket was listening is a quarter; against the 10,000 of the "
                "whole premarket it is a tenth, and only the first is "
                "comparable to CRITERIA's premarket_capture_rate")
        if aaa["collector_window_share"] != 0.4:
            failures.append(
                f"collector_window_share is {aaa['collector_window_share']!r}, "
                "not 0.4. That is the OTHER lower bound, called arithmetic "
                "since 2026-08-14 and unmeasured until this pass existed")
        if aaa["pm_volume_true"] != 10000.0:
            failures.append(
                f"pm_volume_true is {aaa['pm_volume_true']!r}, not the 10,000 "
                "of the true premarket window. The volume is the session's, "
                "even though the capture share is the socket window's")
        if aaa["estimate_error"] != round(8532.0 / 10000.0, 6):
            failures.append(
                f"estimate_error is {aaa['estimate_error']!r}. It is what the "
                "morning PUBLISHED over what was true, which is the number "
                "saying whether the screen admitted the right names")
        if aaa["pm_float_rotation_true"] != 0.01:
            failures.append(
                f"pm_float_rotation_true is {aaa['pm_float_rotation_true']!r}, "
                "not 10,000 over a million")
        if not str(aaa["truth_source"]).startswith("alpaca"):
            failures.append(
                f"truth_source is {aaa['truth_source']!r}. _true does not mean "
                "one vendor in this table: pm_high_true comes from EODHD and "
                "these come from Alpaca, so the row has to carry which")

        # BBB has no float. That nulls one column and must null no other.
        bbb = rows["BBB.US"]
        if bbb["pm_float_rotation_true"] is not None:
            failures.append(
                "a symbol with no sharesFloat got a float rotation anyway")
        if bbb["pm_volume_true"] != 500.0 or bbb["capture_observed"] != 0.2:
            failures.append(
                f"a missing float took the volume with it: {bbb!r}")

        _truth.write(result)
        with store.session() as connection:
            after = {row["ticker"]: row for row in connection.execute(
                "SELECT * FROM picks WHERE date=?", (day,)).fetchall()}
        if after["AAA.US"]["pm_rvol"] != 2.5:
            failures.append(
                f"the morning's pm_rvol became "
                f"{after['AAA.US']['pm_rvol']!r}. The night writes BESIDE the "
                "morning and never over it: a row carries what was known at "
                "08:45 and what was true that night, and which one a query "
                "used is then visible rather than assumed")
        if after["AAA.US"]["pm_volume"] != 1000.0:
            failures.append(
                "the morning's socket volume was overwritten by the truth pass")
        if after["AAA.US"]["pm_rvol_true"] is None:
            failures.append("the true rvol never reached the table")

        # A window with no bars is not a session with no volume.
        empty = _truth.measure(day, probe=Fake({}))
        blank = {row["ticker"]: row for row in empty["rows"]}["AAA.US"]
        if blank["pm_volume_true"] is not None:
            failures.append(
                f"a window with no bars produced {blank['pm_volume_true']!r} "
                "rather than null. Zero volume and no measurement are "
                "different facts and a screen cannot tell them apart")
        if not blank["truth_reason"]:
            failures.append(
                "a null true volume carries no reason, so a reader cannot tell "
                "a row the pass could not measure from one it never reached")
    print("  truth        the night measures volume from Alpaca over the "
          "morning's own window, divides capture by the socket's window, and "
          "writes beside the morning rather than over it")


def claim_the_weekly_page_reads_and_renders_and_nothing_else(
        failures: list[str]) -> None:
    """A reporting layer that fetches is a second pipeline to keep right.

    Everything on the weekly page was already on disk and unread: job status,
    the meter trail, the flag log, verify_intraday, picks. The constraint that
    makes it worth having is that it adds nothing. No vendor call, no new
    table, no measurement of its own. If a number is not already written down
    it does not appear.

    And it must not read the estimate where the measurement exists. pm_rvol is
    what was known at 08:45 and pm_rvol_true is what was true that night; over
    the two sessions measured so far the second ran between 1.4 and 19 times
    the first. volume_ratio returns the label with the value so a page cannot
    show the number without being able to say which one it is, and a mixed
    column with nothing to tell the two apart is the exact defect the truth
    pass was built to stop, one level up.

    Also asserted: an empty window renders a page that SAYS it is empty. A
    reporting page that renders blank sections on a week where nothing ran
    reads the same as a quiet week, and those are opposite facts.
    """
    import shutil

    from core import store
    from night import true_volume as _truth
    from night import weekly_page as _weekly

    # 1. The preference, on rows rather than on a description of rows.
    both = {"pm_rvol": 0.9, "pm_rvol_true": 7.3}
    value, which = _truth.volume_ratio(both)
    if value != 7.3 or which != "measured":
        failures.append(
            f"volume_ratio returned {value!r} as {which!r} for a row carrying "
            "both. The estimate is never the answer when the measurement is "
            "in the same row, and on 2026-08-20 that difference was ten names "
            "on the day watchlist against none")
    value, which = _truth.volume_ratio({"pm_rvol": 0.9, "pm_rvol_true": None})
    if value != 0.9 or which != "estimated":
        failures.append(
            f"volume_ratio returned {value!r} as {which!r} where only the "
            "estimate exists. A row the truth pass has not reached still has "
            "the morning's number and withholding it helps nobody")
    if _truth.volume_ratio({})[1] != "estimated":
        failures.append(
            "a row with neither number came back labelled as measured")

    # 2. The page, driven for real against an empty world.
    saved_out = _weekly.OUT_PATH
    with conftest.isolated_store() as box:
        _weekly.OUT_PATH = box / "site" / "Weekly.html"

        calls: list[str] = []
        import requests

        class Refuse:
            def __getattr__(self, name):
                def boom(*args, **kwargs):
                    calls.append(name)
                    raise AssertionError("the weekly page made a vendor call")
                return boom

        saved = requests.Session
        requests.Session = Refuse
        try:
            out = _weekly.build(7)
        finally:
            requests.Session = saved

        if calls:
            failures.append(
                f"the weekly page opened a session and called {calls!r}. It "
                "reads and renders: a reporting layer that fetches is a second "
                "pipeline to keep right and a second way for the record to be "
                "wrong")
        page = out.read_text(encoding="utf-8")

        for heading in ("Did it run", "Is the data trustworthy",
                        "What did it publish", "What did it cost"):
            if heading not in page:
                failures.append(
                    f"the page is missing the {heading!r} section. Four "
                    "sections and no more was the brief, and a page that "
                    "quietly drops one answers a question nobody asked")
        if "<title>" not in page:
            failures.append("the page carries no title")

        # An empty world has to look empty, not tidy.
        for expected in ("no verify_intraday.json in this window",
                         "no live picks rows in this window",
                         "has not written a capture_observed yet"):
            if expected not in page:
                failures.append(
                    f"a week with no data rendered without saying so: "
                    f"{expected!r} is absent. A blank section on a week where "
                    "nothing ran reads exactly like a quiet week")

        # 3. And with data, the true value is what reaches the page.
        with store.session() as connection:
            store.init(connection)
            store.upsert(connection, "picks", ["date", "ticker"], {
                "date": ettime.today_str(), "ticker": "ZZZ.US",
                "source": "live", "pm_rvol": 0.4, "pm_rvol_true": 9.9,
                "capture_observed": 0.04, "estimate_error": 0.2,
                "collector_window_share": 0.3, "day_eligible": 0,
            })
            connection.commit()
        page = _weekly.build(7).read_text(encoding="utf-8")
        if "0.0400" not in page:
            failures.append(
                "a measured capture share never reached the page, so the one "
                "section that turns CRITERIA's assumption into evidence shows "
                "nothing while the evidence sits in the table")
        if ">1<" not in page.replace(" ", ""):
            failures.append(
                "a name the morning failed on volume and the night cleared was "
                "not counted. That column is the cost of the estimate in "
                "names, which is the only unit anybody reads it in")
    _weekly.OUT_PATH = saved_out

    print("  weekly       four sections rendered from disk with no vendor "
          "call, an empty week says it is empty, and the measurement is read "
          "wherever it exists")


def claim_a_claim_cannot_reach_the_live_database(failures: list[str]) -> None:
    """Isolation belongs to the module, not to the harness.

    conftest rebinds config.DATA_DIR, RUNS_DIR and DB_PATH around the whole
    suite, so under run_tests no claim can reach the real premarketdesk.db.
    Call the same claim directly, which is the normal way to debug one, and the
    rebinding never happens. That was the one path with no guard on it, and on
    2026-08-21 claim 73 took it: written with DATA_DIR and RUNS_DIR rebound and
    DB_PATH left alone, checked by hand while it was being built, it wrote two
    fixture rows into the live picks table and its fake probe overwrote a real
    session's truth columns with nulls.

    A sweep of every claim in the tree, invoked directly, then found SEVEN more
    with the same gap. Claim 73 was found by damage; the other seven were found
    by looking, and they were there the whole time.

    So the refusal sits in store.connect, which every connection goes through,
    and it holds however the claim was invoked. It REFUSES rather than
    redirecting: a silent redirect would let a claim pass against a database it
    did not mean to open, trading a loud failure for a quiet one.
    """
    from core import store as _store

    # THE LIVE PATH IS DERIVED, not read off config.DB_PATH. Under run_tests
    # conftest has already pointed DB_PATH at the sandbox, so a claim that
    # treated "whatever DB_PATH is now" as the real database would test the
    # sandbox against itself and pass while proving nothing. That is the same
    # mistake the guard itself made in its first version, one level up.
    live = (config.PROJECT_ROOT / "data" / "premarketdesk.db").resolve()
    entry = config.DB_PATH

    # 1. Refused, by name, on the real file while a tests module is loaded.
    #    This module is one, so the condition is already true.
    config.DB_PATH = live
    try:
        _store.connect().close()
        failures.append(
            "store.connect opened the LIVE database from inside a test "
            "module. That is how a claim destroys the record it exists to "
            "protect, and it is not hypothetical: it happened on 2026-08-21")
    except _store.LiveDatabaseUnderTestError as refusal:
        text = str(refusal)
        if "isolated_store" not in text:
            failures.append(
                f"the refusal does not say what to do instead: {text!r}. A "
                "guard that stops the work without naming the fixture just "
                "moves the problem to whoever hits it next")
    except Exception as exc:  # noqa: BLE001
        failures.append(
            f"store.connect raised {type(exc).__name__} rather than "
            "LiveDatabaseUnderTestError, so the refusal cannot be told apart "
            f"from a broken database: {exc}")
    finally:
        config.DB_PATH = entry

    # 2. Not refused inside the fixture, or claims could not use the store at
    #    all and the guard would have replaced one problem with another.
    with conftest.isolated_store() as box:
        if config.DB_PATH.resolve() == live:
            failures.append(
                "isolated_store left DB_PATH pointing at the live database. "
                "Rebinding DATA_DIR alone is exactly the subset that caused "
                "this: config sets DB_PATH once at import, so it does not "
                "follow DATA_DIR")
        try:
            with _store.session() as connection:
                _store.init(connection)
                _store.upsert(connection, "picks", ["date", "ticker"], {
                    "date": "2026-01-01", "ticker": "SANDBOX.US",
                    "source": "test"})
                connection.commit()
        except _store.LiveDatabaseUnderTestError:
            failures.append(
                "the guard refused the SANDBOX database. It must refuse the "
                "real file and nothing else, or no claim can test the store")

        # 3. The guard reads the real root captured at import, not
        #    config.DATA_DIR at call time. A guard doing the latter would
        #    compare the sandbox against itself and refuse nothing, which is
        #    a guard that passes its own test and stops nothing.
        config.DB_PATH = live
        try:
            _store.connect().close()
            failures.append(
                "with DB_PATH pointed back at the real file from inside the "
                "sandbox, the guard allowed it. It is reading the CURRENT "
                "data root rather than the one captured before any rebinding, "
                "so it compares the sandbox with itself and protects nothing")
        except _store.LiveDatabaseUnderTestError:
            pass
        finally:
            config.DB_PATH = box / "data" / "premarketdesk.db"

    # 4. And the fixture puts everything back, or the claim after this one
    #    runs against a directory that has been deleted.
    if config.DB_PATH != entry:
        failures.append(
            f"isolated_store left DB_PATH as {config.DB_PATH!r} rather than "
            "restoring it. A fixture that does not restore is a fixture that "
            "breaks the next claim instead of this one")

    print("  isolation    the live database refuses any connection opened "
          "while a test module is loaded, the sandbox does not, and the "
          "fixture restores every name it rebound")


def claim_the_two_unrebuildable_artifacts_are_held_twice(
        failures: list[str]) -> None:
    """A backup that anything reads is a second input, not a backup.

    Two artifacts here have no route back. The premarket capture is a recording
    of a tape that no longer exists, and the packet is the frozen evidence a
    morning was judged on. Both live under gitignored directories, and on
    2026-08-21 at 15:46 one mistake wrote 258 fixture bars over roughly 3,200
    real ones and 762 bytes over a 125 KB packet. That session is gone.

    Four properties, and the last two matter more than the first two.

    IT COPIES. Given a capture and a packet it puts them under the backup root,
    dated, byte for byte.

    IT RESTORES WITHOUT A VENDOR. A deleted working copy comes back from the
    held copy, which is the entire point: the two things it holds cannot be
    asked for again at any price.

    IT NEVER OVERWRITES A DATED BACKUP, and reports a disagreement instead. A
    stale backup and a corrupted working copy are the same observation from
    inside the module, and resolving it automatically destroys the evidence
    needed to tell them apart. Copying the working file over the backup on
    2026-08-21 would have erased the last good capture.

    AND NOTHING IN THE PIPELINE READS IT. If any morning or nightly module
    reached into the backup root it would stop being a copy and become a second
    input, with a second way to be wrong and no guard on it.
    """
    import shutil

    from night import backup_evidence as _backup

    # OUTSIDE THE WORKING TREE, asserted against the real function before it
    # is stubbed for the rest of this claim. This is the property the whole
    # module rests on and it was the one thing unasserted: a mutation moving
    # the root to config.DATA_DIR/evidence left the suite green, and a copy
    # inside the directory that gets deleted is not a copy. The 15:46 sweep
    # wrote to nine paths under data/ and runs/; a backup living there would
    # have been the tenth.
    real_root = _backup.backup_root().resolve()
    tree = config.PROJECT_ROOT.resolve()
    if real_root == tree or tree in real_root.parents:
        failures.append(
            f"the backup root {real_root} is inside the working tree at "
            f"{tree}. Whatever deletes or overwrites the tree takes the copy "
            "with it, which is the one failure a backup exists to survive")

    # INDEPENDENT OF config.DATA_DIR, which is the check that bites. Testing
    # only "not under PROJECT_ROOT" passes for a root derived from DATA_DIR,
    # because under run_tests DATA_DIR is already the sandbox and the sandbox
    # is not under the tree. A root that follows DATA_DIR follows it into the
    # live data directory in production, which is exactly where the copy must
    # not be.
    moved = config.DATA_DIR
    try:
        config.DATA_DIR = pathlib.Path(tempfile.gettempdir()) / "pmd-not-here"
        if _backup.backup_root().resolve() != real_root:
            failures.append(
                "the backup root moved when config.DATA_DIR moved, so it is "
                "derived from the data directory. In production that puts the "
                "copy inside data/, alongside the nine paths the 2026-08-21 "
                "sweep overwrote")
    finally:
        config.DATA_DIR = moved

    box = pathlib.Path(tempfile.mkdtemp())
    saved_root = _backup.backup_root
    with conftest.isolated_store():
        try:
            _backup.backup_root = lambda: box / "evidence"
            day = "2026-08-20"
            capture = config.PREMARKET_DIR / f"{day}.jsonl"
            packet = config.run_dir(day) / "packet.json"
            capture.parent.mkdir(parents=True, exist_ok=True)
            packet.parent.mkdir(parents=True, exist_ok=True)
            capture.write_text('{"symbol":"AAA.US","v":1}\n', encoding="utf-8")
            packet.write_text('{"session_date":"2026-08-20"}', encoding="utf-8")

            first = _backup.run([day])
            if first["written"] != 2:
                failures.append(
                    f"the backup copied {first['written']} artifact(s), not the "
                    f"capture and the packet: {first['copy']!r}")

            # 1. It restores what the working tree lost, with no vendor call.
            original = capture.read_bytes()
            capture.unlink()
            outcome = _backup.restore(day)
            if "premarket" not in outcome["restored"]:
                failures.append(
                    f"a deleted capture was not restored: {outcome!r}. The "
                    "capture cannot be refetched at any price, so a backup "
                    "that cannot put it back is decoration")
            if capture.read_bytes() != original:
                failures.append("the restored capture is not byte identical")

            # 2. A second run copies nothing and leaves the held file alone.
            again = _backup.run([day])
            if again["written"] or len(again["held"]) != 2:
                failures.append(
                    f"a second backup of an unchanged session did work: "
                    f"{again['written']} written, held {again['held']!r}")

            # 3. A changed working copy is a DISAGREEMENT, not an update. This
            #    is the case that would have caught 2026-08-21 the same night.
            held_before = (box / "evidence" / day / "premarket.jsonl").read_bytes()
            capture.write_text('{"symbol":"AAPL.US","v":5000}\n', encoding="utf-8")
            third = _backup.run([day])
            if not third["disagree"]:
                failures.append(
                    "a working copy that no longer matches the backup was not "
                    "reported as a disagreement. That silence is what let a "
                    "destroyed capture go unnoticed for a day")
            if third["written"]:
                failures.append(
                    "the backup was overwritten by the changed working copy. A "
                    "stale backup and a corrupted working copy look identical "
                    "from here, and this direction erases the only good one")
            if (box / "evidence" / day / "premarket.jsonl").read_bytes() != held_before:
                failures.append("the held copy changed on disk")

            # 4. And restore refuses to resolve that disagreement by itself.
            refusal = _backup.restore(day)
            if "premarket" in refusal["restored"]:
                failures.append(
                    "restore overwrote a differing working copy without being "
                    "forced. Overwriting the newer of two disagreeing files is "
                    "the mistake this module exists to undo")
        finally:
            _backup.backup_root = saved_root
            shutil.rmtree(box, ignore_errors=True)

    # 5. Nothing in the pipeline reads it. Checked over the source rather than
    #    asserted, because this is the property that keeps it a copy.
    root_key = 'text("backup", "root")'
    readers = []
    for path in sorted((config.PROJECT_ROOT / "src").rglob("*.py")):
        if path.name == "backup_evidence.py" or "tests" in path.parts:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if root_key in body or "backup_evidence" in body or "backup_root" in body:
            readers.append(path.name)
    if readers:
        failures.append(
            f"{', '.join(readers)} reaches into the backup. It is a copy, and "
            "a copy anything reads is a second input with a second way to be "
            "wrong and no guard on it")

    print("  backup       the capture and the packet are held outside the "
          "tree, restore needs no vendor, a dated copy is never overwritten, "
          "and no pipeline module reads it")


def claim_the_documents_count_what_is_actually_here(failures: list[str]) -> None:
    """Three documents count the same three things, and nothing was checking them.

    On 2026-08-21 the arc page, the architecture page and BUILD_PLAN all said
    "twelve test_ modules" against thirteen on disk, two of them said seven job
    .bat files against eight, and BUILD_PLAN said two float rotation study
    payloads against four. Every one of those numbers went stale the moment a
    file was added, and the only thing that would have caught it is a reader
    who happened to count.

    That is a bad way to hold a fact. These counts are the first thing a new
    reader uses to decide whether a document describes the tree in front of
    them, so a document that miscounts is worse than one that omits: it reads
    as authoritative and is wrong in the cheapest possible way to check.

    So the counts are asserted here, in the words the documents use rather than
    in digits, because the prose is written in words and a claim that matched
    digits would pass over the sentence it is supposed to guard. When one of
    these fails, the fix is the document, not this claim.
    """
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
             12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
             16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
             20: "twenty"}

    root = config.PROJECT_ROOT
    suite = (root / "src" / "tests" / "run_tests.py").read_text(encoding="utf-8")
    counts = {
        "test_ modules": suite.count('"tests.test_'),
        "job .bat files": len(list((root / "tasks").glob("job_*.bat"))),
        "float rotation study": len(list(
            (root / "doc" / "research").glob("float_rotation_study-*.json"))),
    }
    for what, number in counts.items():
        if number not in words:
            failures.append(f"there are {number} {what}, which is off the end of "
                            "the word list this claim reads the documents with")
            return

    checks = [
        ("doc/Premarketdesk_ADayRunArc.html", "test_ modules"),
        ("doc/ArchitecturePremarketdesk.html", "test_ modules"),
        ("doc/BUILD_PLAN.md", "test_ modules"),
        ("doc/Premarketdesk_ADayRunArc.html", "job .bat files"),
        ("doc/BUILD_PLAN.md", "job .bat files"),
        ("doc/BUILD_PLAN.md", "float rotation study"),
    ]
    for rel, what in checks:
        path = root / rel
        if not path.is_file():
            failures.append(f"{rel} is gone, and it is one of the documents a "
                            "reader uses to decide whether the rest describes "
                            "this tree")
            continue
        text = path.read_text(encoding="utf-8")
        wanted = f"{words[counts[what]]} {what}"
        if wanted in text:
            continue
        # Name the wrong number rather than only the right one, so the fix is
        # a search rather than a hunt.
        found = [w for n, w in words.items()
                 if n != counts[what] and f"{w} {what}" in text]
        failures.append(
            f"{rel} does not say {wanted!r}"
            + (f", it says {found[0]!r} {what}" if found else "")
            + f". There are {counts[what]} on disk")

    print(f"  documents    the three counted things are counted right in three "
          f"documents: {counts['test_ modules']} test modules, "
          f"{counts['job .bat files']} job batch files, "
          f"{counts['float rotation study']} study payloads")


def claim_the_day_screen_and_the_volume_score_agree_on_one_number(
        failures: list[str]) -> None:
    """[Day setup]'s volume floor and the volume score's first point are one number.

    CRITERIA [Day setup] premarket_rvol is `> 1.5` and [Score premarket rvol]'s
    one point band is `>= 1.5`. Written twice, they say the same thing: the day
    screen already asks whether the volume slot scored at least one point, in
    RVOL's units only.

    That identity is load bearing and nothing was watching it. DECISIONS
    2026-08-21 measures the rotation floor that would match the day screen for
    a name with no baseline, gets 0.00014, and rests its whole argument on that
    being the rotation ONE POINT edge rather than a coincidence to be
    maintained by hand. If someone moves either 1.5 and not the other, the
    argument silently stops holding and the two measures start meaning
    different things in the same screen, which is the failure the band matching
    in [Score premarket float rotation] exists to prevent.

    So this asserts the identity itself, not either number. Both may move; they
    may not move apart. It also refuses the operators drifting, because
    `> 1.5` and `>= 1.5` differ on exactly the value they share, and a name
    landing precisely on it would be scored a point and screened out.
    """
    from core import criteria as _criteria

    crit = _criteria.load()
    floor = crit.rule("day_setup", "premarket_rvol")
    one_point = None
    for band in crit.bands("score_premarket_rvol"):
        if band.rule is not None and band.result.strip() == "1":
            one_point = band.rule
    if one_point is None:
        failures.append("[Score premarket rvol] has no one point band, so the "
                        "volume slot no longer has a first point for the day "
                        "screen to agree with")
        return

    if floor.value != one_point.value:
        failures.append(
            f"[Day setup] premarket_rvol is {floor.describe()} where the volume "
            f"score's first point is {one_point.describe()}. They were one "
            "number, and DECISIONS 2026-08-21 derives the matching float "
            "rotation floor from their being one number")
    if (floor.op, one_point.op) != (">", ">="):
        failures.append(
            f"the operators are {floor.op!r} and {one_point.op!r} rather than "
            "'>' and '>='. They differ on exactly the shared value, so a name "
            "landing on it is scored a point and screened out, and any other "
            "pairing changes which of those two happens")

    # And the study reports the matched floor from CRITERIA rather than from a
    # constant, which is what makes it re-derive when either of the two moves.
    payload = (config.PROJECT_ROOT / "doc" / "research"
               / "float_rotation_study-2026-08-21-eligibility.json")
    if not payload.is_file():
        failures.append(f"{payload.name} is gone, so the eligibility floor "
                        "DECISIONS quotes can no longer be reproduced")
        return
    block = ((json.loads(payload.read_text(encoding="utf-8"))
              .get("mapping_transfer") or {}).get("top_12_by_gap") or {})
    eligibility = block.get("day_setup_eligibility") or {}
    if eligibility.get("rvol_floor") != floor.describe():
        failures.append(
            f"the study measured against a floor of "
            f"{eligibility.get('rvol_floor')!r} where CRITERIA now says "
            f"{floor.describe()!r}, so the recorded rotation floor was matched "
            "to a screen that has since changed")
    rows = ((json.loads(payload.read_text(encoding="utf-8"))
             .get("rescued_rotation_values") or {}).get("top_by_gap") or [])
    share = eligibility.get("share_of_paired_rvol_admitted")
    edge = eligibility.get("rotation_edge_admitting_the_same_share")
    if rows and share and edge:
        ordered = sorted(rows, reverse=True)
        index = min(max(int(round(share * len(ordered))) - 1, 0), len(ordered) - 1)
        if not (edge <= ordered[index] < edge * 10):
            failures.append(
                f"the recorded eligibility edge {edge!r} is not a rounded down "
                f"form of the rescued value at the matched share, "
                f"{ordered[index]!r}, so the two numbers in the payload "
                "disagree with each other")

    print("  criteria     the day screen's volume floor and the volume score's "
          "first point are still one number, and the study matches against it")


def claim_the_universe_keeps_the_name_the_vendor_sent(
        failures: list[str]) -> None:
    """The build reads Type off a row and threw the rest of that row away.

    exchange-symbol-list answers Code, Name, Country, Exchange, Currency, Isin
    and Type in ONE row. _common_stock_index read Type to filter and Exchange
    to keep, and discarded the Name, which is the only field in the whole
    project that says what an instrument IS rather than what it did.

    That absence had a cost and it is dated. Layer 4's second list ranks market
    cap descending, so the largest caps on file are read by a human every
    morning. SPCX at 1.85 trillion and SKHY at 1.18 were written up in
    DECISIONS.md as implausible caps wanting a plausibility floor nobody had
    measured. Three offline discriminators were then measured against them,
    implied share count, vendor self consistency, and realised volatility
    against cap, and all three failed to separate the pair from real megacaps.
    A vendor call settled it in one response: Space Exploration Technologies
    Corp. Class A Common Stock, and SK Hynix Inc. American Depositary Shares.
    Both caps were right, the finding was wrong, and a plausibility floor would
    have quietly dropped SpaceX and SK Hynix from a list whose entire job is to
    surface the largest names that moved.

    This is the writer half. src/tests/test_notable.py holds the reader half.
    Without this one, deleting the field here would leave that reader reporting
    "the file predates the field" forever, with every claim green.
    """
    from selection import universe

    class _Vendor:
        def exchange_symbol_list(self, exchange):
            return [
                {"Code": "AAA", "Type": "Common Stock", "Exchange": exchange,
                 "Name": "Alpha Alpha Alpha Inc.", "Isin": "US0000000001"},
                # Sent with no Name at all, which has to read as absent rather
                # than as the empty string a template would print as a name.
                {"Code": "BBB", "Type": "Common Stock", "Exchange": exchange,
                 "Name": "   ", "Isin": ""},
                # Filtered out by Type, so its name must not reach the file.
                {"Code": "CCC", "Type": "ETF", "Exchange": exchange,
                 "Name": "Cee Cee Cee Fund", "Isin": "US0000000003"},
            ], None

    with contextlib.redirect_stdout(io.StringIO()):
        index = universe._common_stock_index(_Vendor(), [])

    if "CCC" in index:
        failures.append("a row the Type filter refused reached the index, so "
                        "the filter this function exists for has stopped")
    row = index.get("AAA")
    if not isinstance(row, dict):
        failures.append(f"the index maps AAA to {row!r} rather than to the row "
                        "the vendor sent, so the name is being thrown away "
                        "again and list 2 is back to bare tickers")
        return
    if row.get("name") != "Alpha Alpha Alpha Inc.":
        failures.append(f"AAA carries name {row.get('name')!r}, not the one the "
                        "vendor sent in the same row as its Type")
    if row.get("isin") != "US0000000001":
        failures.append(f"AAA carries isin {row.get('isin')!r}. It costs nothing "
                        "and it is the identifier a human can look up, which a "
                        "reused ticker is not")
    if row.get("exchange") is None:
        failures.append("the exchange was lost while the name was gained, and "
                        "the row shape is the whole point of carrying a dict")
    blank = index.get("BBB") or {}
    if blank.get("name") is not None or blank.get("isin") is not None:
        failures.append(f"a vendor row carrying whitespace produced "
                        f"{blank.get('name')!r} and {blank.get('isin')!r} rather "
                        "than nulls, so the report prints an empty name as a "
                        "name and a reader cannot tell it from a real one")

    print("  universe     the instrument name and isin the vendor sends in the "
          "same row as Type are kept rather than discarded")


def claim_the_shipped_rotation_edges_are_the_ones_the_study_fitted(
        failures: list[str]) -> None:
    """A band edge in CRITERIA is the number a fit produced, or it is a guess.

    CRITERIA [Score premarket float rotation] says in its own text that its
    edges are read off the rescued distribution at the quantiles reproducing
    what the RVOL bands pay, and it names the script and the payload key to
    read them back from. That makes the two numbers checkable against each
    other, and until 2026-08-20 nothing checked them. The shipped pair had been
    fitted on a population 36 percent of which was the study's own cold start,
    and the file went on describing itself as measured for a fortnight.

    So: read the edges out of CRITERIA, read the archived payload, and refuse
    any disagreement. Then re-derive the pair from the ROWS the payload now
    carries, with arithmetic written out here rather than imported, because
    checking the script against itself would pass whatever the script did.

    The rounding is asserted with them, and so is its cost. Rounding DOWN to
    one significant figure was harmless while the edges sat mid decade and
    costs 30 percent at 0.00014266, where the next figure down is a third of
    the value. The rule is two figures now, and the one figure answer is
    checked to be the WORSE of the two against the RVOL target, because a
    rounding rule nobody has watched go wrong is not known to be a rule.
    """
    import math as _math

    from core import criteria as _criteria

    payload_path = (config.PROJECT_ROOT / "doc" / "research"
                    / "float_rotation_study-2026-08-20-warmup-fixed.json")
    if not payload_path.is_file():
        failures.append(f"{payload_path.name} is gone, so the edges in CRITERIA "
                        "[Score premarket float rotation] can no longer be "
                        "traced to the fit they are supposed to come from")
        return
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    block = (payload.get("mapping_transfer") or {}).get("top_12_by_gap") or {}
    fitted = block.get("rederived_on_rescued") or {}
    rows = (payload.get("rescued_rotation_values") or {}).get("top_by_gap") or []
    target = block.get("rvol_target") or {}

    if len(rows) != block.get("rescued_n"):
        failures.append(
            f"the payload carries {len(rows)} rescued rows against a stated "
            f"rescued_n of {block.get('rescued_n')}. The rows exist so a re-fit "
            "needs no vendor call, which is worth nothing if they are not the "
            "rows the quantiles were taken from")
        return

    bands = _criteria.load().bands("score_premarket_float_rotation")
    shipped = {"2": None, "1": None}
    for band in bands:
        if band.rule is not None and band.result in shipped:
            shipped[band.result] = band.rule.value
    for result, key in (("2", "two_points"), ("1", "one_point")):
        if shipped[result] != fitted.get(key):
            failures.append(
                f"CRITERIA scores {result} above {shipped[result]!r} where the "
                f"archived fit re-derived {fitted.get(key)!r}. An edge that has "
                "drifted from its own measurement is a seeded threshold wearing "
                "a measured one's paperwork")

    def edge_at(values: list[float], share: float) -> float:
        ordered = sorted(values, reverse=True)
        index = min(max(int(round(share * len(ordered))) - 1, 0), len(ordered) - 1)
        return ordered[index]

    def round_down(value: float, figures: int) -> float:
        power = _math.floor(_math.log10(value)) - (figures - 1)
        return round(_math.floor(round(value / (10 ** power), 9)) * (10 ** power),
                     -power + 1)

    def miss(two: float, one: float) -> float:
        """How far a pair of edges lands from what the RVOL bands pay, in points."""
        count = len(rows)
        hi = sum(1 for v in rows if v > two) / count
        mid = sum(1 for v in rows if one <= v <= two) / count
        return 100 * (abs(hi - target["two_points"])
                      + abs(mid - target["one_point"]))

    exact_two = edge_at(rows, target["two_points"])
    exact_one = edge_at(rows, target["two_points"] + target["one_point"])
    for figures, wanted in ((2, fitted),):
        got = {"two_points": round_down(exact_two, figures),
               "one_point": round_down(exact_one, figures)}
        if got != {k: wanted.get(k) for k in got}:
            failures.append(
                f"re-deriving the edges from the carried rows gives {got}, "
                f"where the payload recorded {dict(wanted)}. Either the rows are "
                "not the ones fitted or the rounding has moved")

    two_figures, one_figure = miss(*[round_down(v, 2) for v in (exact_two, exact_one)]),         miss(*[round_down(v, 1) for v in (exact_two, exact_one)])
    if not two_figures < one_figure:
        failures.append(
            f"two significant figures miss the RVOL payout by {two_figures:.2f} "
            f"points and one figure by {one_figure:.2f}, so the reason CRITERIA "
            "gives for rounding to two is no longer true of this distribution")

    # The noise case that made this rule wrong the first time it was written.
    # 0.0006 scaled by 1e5 is 59.999999999999993, and a bare floor answers
    # 0.00059: a rounding rule for readability moving an edge by a sixtieth.
    for value, wanted in ((0.0006, 0.0006), (0.0003, 0.0003), (0.007, 0.007),
                          (0.00033763, 0.00033), (0.00014266, 0.00014)):
        if round_down(value, 2) != wanted:
            failures.append(f"round_down({value}) is {round_down(value, 2)} "
                            f"rather than {wanted}, which is binary floating "
                            "point eating a whole significant unit")

    print("  claim 64        the shipped rotation edges are the ones the fit "
          "produced, re-derivable from the rows the payload carries")


def claim_no_python_here_runs_a_git_fetch(failures: list[str]) -> None:
    """The one path the tree photograph exempts is still one nothing here writes.

    conftest exempts .git/FETCH_HEAD, because VSCode's git extension autofetches
    every 180 seconds on this machine and roughly one suite run in six straddled
    a fetch and failed on a file no test touches. That exemption is only safe
    while nothing in this project fetches, and an exemption whose precondition
    nobody rechecks is how a real write gets hidden.

    So this walks every tracked Python file for git invocations and holds two
    things about each: it is not a fetch or a pull, and it carries
    --no-optional-locks. The second is the 2026-08-14 lesson written down as a
    check rather than as a comment: `git status` without that flag refreshes and
    rewrites .git/index, and the suite then failed on a file the check itself
    had caused to change, which cost a day and was blamed on a virus scanner
    first.
    """
    import ast as _ast
    import subprocess

    root = config.PROJECT_ROOT
    listing = subprocess.run(["git", "--no-optional-locks", "ls-files", "*.py"],
                             cwd=str(root), capture_output=True, text=True)
    if listing.returncode != 0:
        failures.append("git ls-files failed, so no Python file was examined: "
                        f"{listing.stderr.strip()[:200]}")
        return
    tracked = [name for name in listing.stdout.splitlines() if name.strip()]
    if len(tracked) < 20:
        failures.append(f"git ls-files returned {len(tracked)} Python files, "
                        "which is too few to be this tree")
        return

    fetching = ("fetch", "pull", "remote", "clone", "submodule")
    seen = 0
    for name in tracked:
        try:
            tree = _ast.parse((root / name).read_bytes().decode("utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.List) or not node.elts:
                continue
            head = node.elts[0]
            if not (isinstance(head, _ast.Constant) and head.value == "git"):
                continue
            words = [e.value for e in node.elts
                     if isinstance(e, _ast.Constant) and isinstance(e.value, str)]
            seen += 1
            line = getattr(node, "lineno", 0)
            for word in words[1:]:
                if word in fetching:
                    failures.append(
                        f"{name}:{line} runs `git {word}`. conftest exempts "
                        ".git/FETCH_HEAD from the tree photograph on the grounds "
                        "that nothing here fetches, so that exemption is now "
                        "hiding a write this project makes. Remove the "
                        "invocation or remove the exemption.")
            if "--no-optional-locks" not in words:
                failures.append(
                    f"{name}:{line} runs git without --no-optional-locks. An "
                    "ordinary read refreshes and rewrites .git/index, and the "
                    "suite then fails on a file it caused to change itself. "
                    "This cost a day on 2026-08-14.")

    if seen < 3:
        failures.append(f"only {seen} git invocation(s) were found, where this "
                        "tree carries three. The walk did not reach them, so it "
                        "proved nothing.")

    print(f"  fetch guard  {seen} git invocations, none of them a fetch, all of "
          "them holding .git/index still")


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
            for entity in _EM_DASH_ENTITIES:
                if entity.lower() in line.lower():
                    offences.append(f"{name}:{number} carries an em dash "
                                    "entity, which renders as one")

    if offences:
        shown = "; ".join(offences[:8])
        more = f", and {len(offences) - 8} more" if len(offences) > 8 else ""
        failures.append(f"hard rule 4 is broken in {len(offences)} "
                        f"place(s): {shown}{more}")

    # The needles have to be the real ones, or this is a walk over nothing that
    # passes because it can never match. This file is itself in the walk, so a
    # literal here would fail the claim: that is the point of building them.
    if _EM_DASH != "\N{EM DASH}" or len(_EM_DASH_ENTITIES) != 3:
        failures.append("the needles are not an em dash and its three entity "
                        "spellings, so the walk above cannot detect them")
    for entity in _EM_DASH_ENTITIES:
        if not entity.startswith("&") or not entity.endswith(";"):
            failures.append(f"{entity!r} is not an HTML entity")
    if len(_EM_DASH) != 1 or ord(_EM_DASH) != 8212:
        failures.append(f"the em dash needle is {_EM_DASH!r}, not U+2014")

    print(f"  house rule  no em dash and none of its three entity spellings "
          f"anywhere in {len(tracked)} tracked files")


# ---------------------------------------------------------------- plumbing

def conftest_activate():
    from tests import conftest

    return conftest.activate()


def main() -> int:
    failures: list[str] = []
    claim_the_november_transition(failures)
    claim_economic_events_are_converted_not_relabelled(failures)
    claim_a_thinner_rerun_stands_down(failures)
    claim_a_briefing_gain_does_not_cancel_a_screen_loss(failures)
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
    claim_a_half_written_calendar_is_not_a_missing_one(failures)
    claim_an_unrecorded_relaunch_is_reported_rather_than_raised(failures)
    claim_an_interrupted_packet_write_leaves_no_half_packet(failures)
    claim_the_archive_does_not_publish_a_fixture_as_a_morning(failures)
    claim_reading_a_run_directory_does_not_create_one(failures)
    claim_a_partial_batch_writes_each_minute_once(failures)
    claim_a_torn_tail_is_closed_before_the_next_bar(failures)
    claim_an_unplaceable_trade_is_not_a_lost_connection(failures)
    claim_a_failed_truth_pass_erases_no_measurement(failures)
    claim_recall_refuses_a_pool_the_morning_did_not_read(failures)
    claim_a_split_is_not_a_gap(failures)
    claim_the_previous_session_helper_says_when_it_does_not_know(failures)
    claim_a_live_job_is_not_rerun_on_top_of_itself(failures)
    claim_a_previous_session_watchlist_reruns_discover(failures)
    claim_an_empty_bulk_day_is_not_an_empty_market(failures)
    claim_recall_never_publishes_an_unknown_as_a_zero(failures)
    claim_outcomes_refuse_a_split_they_cannot_measure_across(failures)
    claim_an_unparsable_verification_is_not_a_measurement(failures)
    claim_ensure_dirs_follows_a_redirected_config(failures)
    claim_a_refused_sweep_is_not_an_empty_feed(failures)
    claim_the_volume_check_puts_no_roster_in_the_packet(failures)
    claim_a_finish_marker_outranks_a_fresh_log(failures)
    claim_a_hold_needs_a_pass_that_can_act(failures)
    claim_the_last_pass_counts_what_it_cannot_resolve(failures)
    claim_the_long_leg_checks_the_units_it_writes(failures)
    claim_the_buckets_say_what_they_sum_to(failures)
    claim_a_matching_collector_is_not_called_a_disagreement(failures)
    claim_the_hand_run_redirect_moves_a_captured_run_directory(failures)
    claim_an_unread_news_window_is_not_an_empty_one(failures)
    claim_the_sharing_count_names_the_set_it_was_taken_over(failures)
    claim_a_lost_second_bulk_call_keeps_the_first(failures)
    claim_the_watchlist_comment_matches_what_the_watchdog_does(failures)
    claim_a_partly_refused_sweep_is_reported_as_one(failures)
    claim_no_em_dash_survives_anywhere(failures)
    claim_a_partial_minute_counts_only_the_seconds_it_covered(failures)
    claim_a_flag_the_run_never_recorded_is_not_a_zero(failures)
    claim_the_trust_store_is_never_served_half_written(failures)
    claim_the_rotation_study_counts_no_warm_up_session(failures)
    claim_no_python_here_runs_a_git_fetch(failures)
    claim_the_shipped_rotation_edges_are_the_ones_the_study_fitted(failures)
    claim_the_universe_keeps_the_name_the_vendor_sent(failures)
    claim_the_day_screen_and_the_volume_score_agree_on_one_number(failures)
    claim_the_documents_count_what_is_actually_here(failures)
    claim_a_thin_capture_share_is_refused_rather_than_divided_by(failures)
    claim_the_packet_never_asks_for_the_correction_to_be_applied_twice(failures)
    claim_a_probe_reading_its_own_noise_cannot_beat_is_refused(failures)
    claim_the_prune_deletes_only_what_its_whitelist_names(failures)
    claim_the_truth_pass_writes_beside_the_morning_and_never_over_it(failures)
    claim_the_weekly_page_reads_and_renders_and_nothing_else(failures)
    claim_a_claim_cannot_reach_the_live_database(failures)
    claim_the_two_unrebuildable_artifacts_are_held_twice(failures)
    claim_both_volume_ratios_divide_the_same_tape(failures)

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
