"""Every scheduled step records whether it succeeded, and the morning says so.

pool_recall raised NameError on every nightly run for a week and produced
nothing, and the record that cited its output as accumulating evidence was
wrong the whole time. Three things hid it and each of them was, on its own,
a deliberate decision:

  the nightly .bat ignores that step's exit code, so a diagnostic cannot
  fail the chain, which is right;
  its main caught RuntimeError only, so a NameError escaped, which was a
  mistake but a small one;
  the watchdog reads each job's final step marker, and pool_recall is not
  the final step, so the nightly looked finished every night, which is also
  right, because the archive after it really did finish.

None of those wants reversing. Not letting a diagnostic fail the chain is
correct. Not recording that it failed is what turned a missing measurement
into a false one. So this module adds the missing half: an append only record
of what every step did, written in a finally block so a step that dies still
records dying, and one line in the morning report when something has not
succeeded in longer than it should have.

Staleness is counted in trading sessions, not hours. A weekday job that last
succeeded on Friday is one session stale on Monday, not three days stale, so
a weekend cannot raise a false alarm and a Tuesday holiday cannot hide a real
one. The windows live in CRITERIA.md [job status].

Usage at the bottom of a scheduled module:

    if __name__ == "__main__":
        raise SystemExit(job_status.run("discover", main))

and anywhere inside it, once the work is done:

    job_status.produced("watchlist rows", len(rows))
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from core import config
from core import criteria
from core import ettime

_CRIT = criteria.load()

RECORD_PATH = config.DATA_DIR / "job-status.jsonl"

# The .bat files set this so a record can say which job the step ran under.
# A human running a module by hand records "manual", which is a fact worth
# keeping: an ad hoc rerun that succeeded is still a success, but a reader
# should be able to tell it from a scheduled one.
JOB_ENV_VAR = "PMD_JOB"

STATUS_OK = "ok"
STATUS_FAILED = "failed"        # ran to completion and returned non zero
STATUS_ERROR = "error"          # raised, including being killed

_produced: dict[str, Any] = {"label": None, "count": None}
_declared_failure: str | None = None


def failed(reason: str) -> None:
    """Record this run as a failure even though it will exit zero.

    This is the piece the pool_recall bug needed. A diagnostic must not fail
    the chain, so it swallows its exception and returns zero, and that zero is
    the correct exit code. It is not the correct status. Calling this keeps
    the exit code and corrects the record, which is the whole point: the exit
    code is for the scheduler, the record is for the human.
    """
    global _declared_failure
    _declared_failure = reason


def produced(label: str, count: int | None) -> None:
    """Declare what this run produced. The last call before exit is recorded.

    One count, not a structure: the question the record has to answer is "did
    this step do anything", and a single number answers it. Detail belongs in
    the step's own output.
    """
    _produced["label"] = label
    _produced["count"] = None if count is None else int(count)


def append(record: dict[str, Any]) -> None:
    """One JSON line, opened and closed per record.

    Appending a single short line in one write is atomic enough for the two
    jobs that can overlap here (the watchdog repeats through the morning while
    the collector runs), and it is the same pattern the collector already uses
    for its own run stats.
    """
    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RECORD_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
        handle.flush()


# --------------------------------------------------------------- meter trail

def meter_log_path(day: str | None = None) -> Path:
    """One file per quota day, holding every job's reading of the shared key."""
    from core import eodhd

    return config.LOGS_DIR / f"meter-{day or eodhd.quota_day()}.log"


def _last_trail_entry(path: Path) -> dict[str, Any] | None:
    """The previous job's reading, for the delta. None on the day's first."""
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def record_meter(step: str, when: str, source: str = "job",
                 reading: Any = None, extra: dict[str, Any] | None = None
                 ) -> dict[str, Any] | None:
    """Read the shared meter and append it to the day's trail.

    The shared EODHD key is spent by siblings this project cannot see, and on
    2026-08-16 one of them took it from 96,098 to 99,671 in an afternoon, which
    put discover below its refuse floor and would have killed the next morning
    outright. Nothing in this repository could say WHEN that happened or which
    of its own jobs contributed, because the only reading anyone took was the
    preflight inside three of the nine jobs.

    So every job now reads the meter at entry and again at exit, and writes the
    reading with the delta since the previous entry in the trail. A day of that
    attributes consumption to a time of day and to a step, which is the cheap
    half of what a second API token would buy, and it works without buying one.

    Costs one call per reading, so two per STEP, not per job. [corrected
    2026-08-20: was "two per job, about eighteen a day". run() wraps every
    step, and a weekday runs sixteen tracked steps spread over nine job
    firings plus six watchdog firings, which measures at 68 to 92 job readings
    a day in the trail itself, plus the sampler's 48. Call it 120 to 140, or
    about 0.13 percent of the shared 100,000, still small, but seven times
    what this sentence claimed, and this is the module whose whole job is to
    account for a shared key that a sibling project drains.] That is itself
    recorded rather than hidden: the reading moves the thing it reads, and a
    delta of two across a step that made no other call is this function
    looking at itself.

    Never raises. A meter that cannot be read is a missing line in an
    operational log, and must not be able to fail a job that was otherwise
    fine.
    """
    from core import eodhd

    try:
        # A caller that has already read the meter passes the reading in, so
        # writing two rows about one moment costs one call rather than two and
        # both rows describe the SAME reading. The sampler needs this: its
        # reset row and the sample that detected the reset are one observation
        # and must not disagree about the numbers.
        data, error = reading if reading is not None else eodhd.read_meter()
        entry: dict[str, Any] = {
            "at": ettime.stamp(ettime.now_et()),
            "quota_day": eodhd.quota_day(),
            # 'job' for an entry or exit reading taken around a scheduled
            # step, 'sampler' for a reading taken on the clock by
            # ops/meter_sampler.py, 'reset' for the boundary row the sampler
            # writes when the counter rolls. Job readings say WHICH step spent
            # what; sampler readings say WHEN, including across the overnight
            # window where the job schedule is silent for nine hours.
            "source": source,
            "step": step,
            "when": when,
            "job": os.environ.get(JOB_ENV_VAR) or "manual",
            "api_requests": None,
            "daily_limit": None,
            "remaining": None,
            # The date the METER puts on its own counter, which is not the
            # same thing as the quota day computed above. See the roll note in
            # the delta guard below.
            "meter_day": None,
            "meter_day_is_stale": None,
            "delta_since_previous": None,
            "previous_step": None,
            "previous_at": None,
            "error": error,
        }
        if not error and isinstance(data, dict):
            try:
                used = int(data.get("apiRequests"))
                limit = int(data.get("dailyRateLimit"))
            except (TypeError, ValueError):
                used = limit = -1
            if used >= 0 and limit > 0:
                entry.update({"api_requests": used, "daily_limit": limit,
                              "remaining": max(0, limit - used)})
            entry["meter_day"] = str(data.get("apiRequestsDate") or "").strip() or None
            if entry["meter_day"]:
                entry["meter_day_is_stale"] = entry["meter_day"] != entry["quota_day"]

        if extra:
            entry.update(extra)

        path = meter_log_path()
        previous = _last_trail_entry(path)
        # Only compare two readings the METER itself dates the same way.
        #
        # [corrected 2026-08-16: this guarded on quota_day(), the day computed
        # from the wall clock, and the first real trail immediately produced a
        # delta of -94,727. The vendor's counter does NOT roll at 00:00 UTC.
        # On 2026-08-16 the universe job read 99,671 used at 20:30:01 ET and
        # 4,944 at 20:31:49, so the roll landed 30 to 32 minutes after 00:00
        # UTC while quota_day() had already advanced. Both readings therefore
        # looked same-day to the old guard and the subtraction spanned a
        # reset.]
        #
        # apiRequestsDate is the counter's own dating and is the only
        # authoritative signal that it rolled. A missing date on either side
        # means no delta, because an unknown boundary is not a safe
        # subtraction.
        if (previous and entry["api_requests"] is not None
                and previous.get("api_requests") is not None
                and entry.get("meter_day") is not None
                and previous.get("meter_day") == entry["meter_day"]):
            entry["delta_since_previous"] = entry["api_requests"] - previous["api_requests"]
            entry["previous_step"] = f"{previous.get('step')}:{previous.get('when')}"
            entry["previous_at"] = previous.get("at")

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

        if entry["remaining"] is None:
            print(f"{step}: meter unreadable at {when} ({error})")
        else:
            delta = entry["delta_since_previous"]
            if delta is not None:
                since = (f", {delta:+,} since {entry['previous_step']} at "
                         f"{str(entry['previous_at'])[11:19]}")
            elif previous and previous.get("meter_day") is None:
                # Not a roll. The previous row was written before the trail
                # recorded apiRequestsDate, so there is nothing to compare its
                # boundary against, and guessing would be exactly the error
                # the date was added to prevent.
                since = (", no delta: the previous reading did not record which day "
                         "its counter belonged to")
            elif previous:
                since = (f", no delta: the counter is dated {entry['meter_day']} and "
                         f"the previous reading {previous.get('meter_day')}, so it "
                         "rolled between them")
            else:
                since = ", first reading against this counter"
            stale = ""
            if entry["meter_day_is_stale"]:
                stale = (f". NOTE the counter still dates itself {entry['meter_day']} "
                         f"while the quota day is {entry['quota_day']}, so this is the "
                         "previous day's spend and has not rolled yet")
            print(f"{step}: meter at {when} {entry['api_requests']:,} of "
                  f"{entry['daily_limit']:,} used, {entry['remaining']:,} remaining"
                  f"{since}{stale}")
        return entry
    except Exception as exc:  # noqa: BLE001
        print(f"{step}: the meter trail could not be written "
              f"({type(exc).__name__}: {config.scrub_secrets(exc)})")
        return None


def read_trail(day: str | None = None) -> list[dict[str, Any]]:
    """The day's trail, oldest first. For monitor_jobs and for a human."""
    path = meter_log_path(day)
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def run(step: str, main: Callable[..., int], argv: list[str] | None = None,
        ok_codes: tuple[int, ...] = (0,)) -> int:
    """Call a module's main and record what happened, whatever happened.

    Catches BaseException rather than Exception on purpose. A collector killed
    with Ctrl-C and a nightly killed by a reboot are exactly the cases the log
    is worst at showing, and both arrive as BaseException. The exception is
    always re-raised: this records, it does not swallow.

    ok_codes exists for the calendar guard, whose non zero exit means the
    market is shut, which is a correct outcome and not a failure.
    """
    global _declared_failure

    # In production one process runs one step, so this reset is never needed.
    # It is here because a test runs several through one interpreter, and a
    # count carried over from the previous step would be a false record, which
    # is the exact class of thing this module exists to stop.
    _produced.update({"label": None, "count": None})
    _declared_failure = None

    started = ettime.now_et()
    record_meter(step, "entry")
    status = STATUS_ERROR
    exception = None
    code: int | None = None
    try:
        code = main() if argv is None else main(argv)
        status = STATUS_OK if code in ok_codes else STATUS_FAILED
        if _declared_failure:
            status = STATUS_ERROR
            exception = _declared_failure
        return code
    except SystemExit as exc:
        # A module that exits through SystemExit rather than returning.
        raw = exc.code
        code = 0 if raw is None else (raw if isinstance(raw, int) else 1)
        status = STATUS_OK if code in ok_codes else STATUS_FAILED
        raise
    except BaseException as exc:
        exception = f"{type(exc).__name__}: {config.scrub_secrets(exc)}"
        status = STATUS_ERROR
        raise
    finally:
        ended = ettime.now_et()
        # After the step, so the delta between this and the entry reading is
        # what the step itself actually spent.
        record_meter(step, "exit")
        try:
            append({
                "job": os.environ.get(JOB_ENV_VAR) or "manual",
                "step": step,
                "started_at": ettime.stamp(started),
                "ended_at": ettime.stamp(ended),
                "seconds": round((ended - started).total_seconds(), 1),
                "status": status,
                "exit_code": code,
                "exception": exception,
                "produced_label": _produced["label"],
                "produced_count": _produced["count"],
            })
        except OSError as exc:
            # The recorder must never be the reason a job fails. It reports
            # its own failure to stdout, which is the one place left.
            print(f"job_status: could not record {step}, {type(exc).__name__}: {exc}")


# ------------------------------------------------------------------- reading

def records(path: Path | None = None) -> list[dict[str, Any]]:
    """Every record, oldest first. A damaged line is skipped, not fatal."""
    target = path or RECORD_PATH
    if not target.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("step"):
            out.append(row)
    return out


def _date_of(stamp: Any) -> dt.date | None:
    if not isinstance(stamp, str) or len(stamp) < 10:
        return None
    try:
        return ettime.parse_date(stamp[:10])
    except (ValueError, TypeError):
        return None


def sessions_between(day: dt.date, now: dt.date) -> int:
    """Trading sessions strictly after day, up to and including now.

    Zero when day is now. Uses the same exchange calendar the morning guard
    uses, so a holiday counts as no session rather than as a missed one. If
    the calendar cannot answer, weekdays are counted instead, which errs
    towards reporting a job as stale rather than towards silence.

    That promise used to be kept only when the guard RAISED. is_trading_day
    answers True with "calendar unavailable, assuming the market is open" for
    every date when data/exchange-details.json is missing or unreadable, which
    is how the calendar actually fails, and it does not raise, so the except
    branch below never ran for the real fault. Every weekend day then counted
    as a session: sessions_between(Friday, Monday) returned 3 rather than 1,
    which is the watchdog reading three sessions of silence into one weekend
    and calling healthy jobs overdue. trading_day_state answers None when the
    calendar cannot say, and None is what routes to the weekday fallback the
    docstring has always described.
    """
    from ops import market_today

    if now <= day:
        return 0
    count = 0
    cursor = day
    while cursor < now:
        cursor += dt.timedelta(days=1)
        try:
            trades, _why = market_today.trading_day_state(cursor)
        except Exception:  # noqa: BLE001
            trades = None
        if trades is None:
            trades = ettime.is_weekday(cursor)
        if trades:
            count += 1
    return count


def expected_sessions(step: str) -> int | None:
    """The window for a step, or None for a step CRITERIA.md does not name."""
    try:
        return _CRIT.integer("job_status_steps", step)
    except criteria.CriteriaError:
        return None


def tracked_steps() -> list[str]:
    """Every step the schedule is expected to run.

    The whole section, with no filtering, which is why that section holds
    nothing but steps.
    """
    return list(_CRIT.section("job_status_steps").singles())


def last_success(step: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    found = None
    for row in (rows if rows is not None else records()):
        if row.get("step") == step and row.get("status") == STATUS_OK:
            found = row
    return found


def last_attempt(step: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    found = None
    for row in (rows if rows is not None else records()):
        if row.get("step") == step:
            found = row
    return found


def overdue(now: dt.date | None = None,
            rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Steps with no success inside their window, worst first.

    A step that has never recorded a success is reported only once the record
    file itself is older than that step's window. Nothing can be overdue
    before there was anywhere to record it, and reporting every step as
    missing on the day this landed would have taught the reader to ignore the
    line, which is the failure this whole mechanism exists to prevent.
    """
    today = now or ettime.today_et()
    all_rows = rows if rows is not None else records()
    born = _date_of(all_rows[0].get("started_at")) if all_rows else None

    out: list[dict[str, Any]] = []
    for step in tracked_steps():
        window = expected_sessions(step)
        if window is None:
            continue
        success = last_success(step, all_rows)
        if success is None:
            if born is None or sessions_between(born, today) <= window:
                continue
            attempt = last_attempt(step, all_rows)
            out.append({
                "step": step,
                "sessions": sessions_between(born, today),
                "window": window,
                "last_success": None,
                "last_status": (attempt or {}).get("status"),
                "exception": (attempt or {}).get("exception"),
            })
            continue
        day = _date_of(success.get("started_at"))
        if day is None:
            continue
        stale_by = sessions_between(day, today)
        if stale_by <= window:
            continue
        attempt = last_attempt(step, all_rows)
        out.append({
            "step": step,
            "sessions": stale_by,
            "window": window,
            "last_success": success.get("started_at"),
            "last_status": (attempt or {}).get("status"),
            "exception": (attempt or {}).get("exception"),
        })
    out.sort(key=lambda row: row["sessions"] - row["window"], reverse=True)
    return out


def failures_today(now: dt.date | None = None,
                   rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Steps that recorded a non ok outcome today, in the order they happened.

    Separate from overdue() because it answers a different question, and the
    morning of 2026-08-19 is why it exists. overdue() measures staleness of
    last_success in whole trading sessions against a per step window, every one
    of which is one session or more. A step that failed at 08:16 and succeeded
    at 08:37 is therefore current by every measure it has, and so is a step
    that failed this morning having succeeded yesterday. That morning the
    collector died on a refused subscription and lost fifty minutes of window,
    and the packet's job_health block read {"line": null, "overdue": []}. The
    report said nothing about it, and its readers got the symptom, twelve names
    with premarket windows that started late, with no route to the cause.

    A failure is worth one line on the morning it happens even when a rerun
    fixed it, because the rerun is the thing a reader would otherwise have to
    guess at. A later success does not remove it: it is reported alongside.
    """
    today = now or ettime.today_et()
    all_rows = rows if rows is not None else records()
    out: list[dict[str, Any]] = []
    for row in all_rows:
        if _date_of(row.get("started_at")) != today:
            continue
        if row.get("status") in (None, STATUS_OK):
            continue
        out.append({
            "step": row.get("step"),
            "status": row.get("status"),
            "started_at": row.get("started_at"),
            "exit_code": row.get("exit_code"),
            "exception": row.get("exception"),
            # Whether anything picked the step back up afterwards. Read from
            # the same list rather than assumed, because "it failed and a rerun
            # fixed it" and "it failed and nothing ran since" are the two
            # readings and they call for different mornings.
            "recovered": any(
                other.get("step") == row.get("step")
                and other.get("status") == STATUS_OK
                and str(other.get("started_at") or "") > str(row.get("started_at") or "")
                for other in all_rows
            ),
        })
    return out


def _failure_kind(row: dict[str, Any]) -> str:
    """What went wrong, as the coarse label the grouping keys on."""
    if row.get("exception"):
        return str(row["exception"]).split(":")[0]
    if row.get("exit_code") not in (None, 0):
        return f"exit {row['exit_code']}"
    return str(row.get("status") or "failed")


def group_failures(failed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Today's failures collapsed to one entry per step and kind of failure.

    A step that retried three times inside one minute is one problem, and
    naming it three times reads as three. The overdue side of this line already
    caps how many steps it names for the same reason; this is the same argument
    applied to the same sentence, one layer down.

    Recovery is OR-ed across the group deliberately. Three failures of which
    the last was followed by a success is a step that came back, and reporting
    it as not having run again would be wrong about the state the reader cares
    about.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in failed:
        key = (str(row.get("step")), _failure_kind(row))
        found = groups.get(key)
        if found is None:
            groups[key] = {**row, "kind": key[1], "count": 1}
            continue
        found["count"] += 1
        found["recovered"] = found.get("recovered") or row.get("recovered")
    return list(groups.values())


def describe_failure(row: dict[str, Any]) -> str:
    """One of today's failure groups as a phrase."""
    when = str(row.get("started_at") or "")[11:16]
    count = int(row.get("count") or 1)
    kind = row.get("kind") or _failure_kind(row)
    if count > 1:
        text = f"{row['step']} failed {count} times from {when} ET"
    else:
        text = f"{row['step']} failed at {when} ET"
    if kind:
        text += f" ({kind})"
    text += ", and a later run succeeded" if row.get("recovered") else ", and has not run again since"
    return text


def describe(row: dict[str, Any]) -> str:
    """One step's overdue state as a phrase."""
    if row["last_success"] is None:
        text = f"{row['step']} has never recorded a success"
    else:
        sessions = row["sessions"]
        text = (f"{row['step']} last succeeded {sessions} "
                f"session{'s' if sessions != 1 else ''} ago "
                f"({row['last_success'][:10]})")
    if row.get("exception"):
        text += f", last attempt raised {row['exception'].split(':')[0]}"
    elif row.get("last_status") == STATUS_FAILED:
        text += ", last attempt returned non zero"
    return text


def report_line(now: dt.date | None = None,
                rows: list[dict[str, Any]] | None = None) -> str | None:
    """The one line for the morning report, or None when everything is current.

    Silence is the normal case and has to stay silent. A line that appears
    every morning is a line nobody reads.
    """
    all_rows = rows if rows is not None else records()
    if not all_rows:
        # Silence has to mean one thing. An empty record file is the loudest
        # possible state, not the quietest: it says nothing has recorded
        # anything, which includes the recorder itself not running. Returning
        # None here would have made it identical to sixteen healthy steps.
        return ("Scheduled jobs: no step has recorded anything at all, so nothing "
                "below can be vouched for. Either no job has run since the "
                "recorder was added, or the recorder is not writing "
                f"{RECORD_PATH.name}.")

    late = overdue(now, all_rows)
    failed = group_failures(failures_today(now, all_rows))
    if not late and not failed:
        return None
    limit = _CRIT.integer("job_status", "max_steps_named_in_report")
    if not late:
        if len(failed) > limit:
            worst = "; ".join(describe_failure(row) for row in failed[:limit])
            return (f"Scheduled jobs: {len(failed)} steps failed today and were "
                    f"rerun or left failed, which usually means the machine or "
                    f"the schedule stumbled rather than any one step. "
                    f"First {limit}: {worst}.")
        return ("Scheduled jobs: " + "; ".join(describe_failure(row) for row in failed)
                + ".")

    if len(late) > limit:
        # Past a certain number the list stops being a list of problems and
        # becomes one problem. Naming sixteen steps reads as noise; saying the
        # machine has stopped, and naming the worst few, reads as an alarm.
        worst = "; ".join(describe(row) for row in late[:limit])
        return (f"Scheduled jobs overdue: {len(late)} of {len(tracked_steps())} steps "
                f"have not succeeded inside their window, which usually means the "
                f"machine or the schedule stopped rather than any one step. "
                f"Worst: {worst}.")
    line = "Scheduled jobs overdue: " + "; ".join(describe(row) for row in late) + "."
    if failed:
        line += " Also today: " + "; ".join(
            describe_failure(row) for row in failed[:limit]) + "."
    return line


# ---------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="What every scheduled step last did.")
    parser.add_argument("--overdue-only", action="store_true",
                        help="Print only the morning report line, and nothing "
                             "at all when every job is current.")
    args = parser.parse_args(argv)

    rows = records()
    if args.overdue_only:
        line = report_line(rows=rows)
        if line:
            print(line)
        return 0

    print(f"job_status: {len(rows)} records in {RECORD_PATH}")
    if not rows:
        print("  nothing recorded yet")
        return 0

    print(f"  {'step':<14} {'window':>6} {'last ok':<12} {'age':>5}  "
          f"{'last run':<20} {'status':<7} produced")
    today = ettime.today_et()
    for step in tracked_steps():
        window = expected_sessions(step)
        success = last_success(step, rows)
        attempt = last_attempt(step, rows)
        day = _date_of((success or {}).get("started_at"))
        age = f"{sessions_between(day, today)}" if day else "-"
        count = (attempt or {}).get("produced_count")
        label = (attempt or {}).get("produced_label") or ""
        made = f"{count:,} {label}" if count is not None else label
        print(f"  {step:<14} {window:>6} {(success or {}).get('started_at', '-')[:10]:<12} "
              f"{age:>5}  {(attempt or {}).get('started_at', '-')[:19]:<20} "
              f"{(attempt or {}).get('status', '-'):<7} {made}")

    line = report_line(rows=rows)
    print("")
    print(line if line else "every scheduled step has succeeded inside its window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
