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

import config
import criteria
import ettime

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
    """
    import market_today

    if now <= day:
        return 0
    count = 0
    cursor = day
    while cursor < now:
        cursor += dt.timedelta(days=1)
        try:
            trades, _why = market_today.is_trading_day(cursor)
        except Exception:  # noqa: BLE001
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
    if not late:
        return None

    limit = _CRIT.integer("job_status", "max_steps_named_in_report")
    if len(late) > limit:
        # Past a certain number the list stops being a list of problems and
        # becomes one problem. Naming sixteen steps reads as noise; saying the
        # machine has stopped, and naming the worst few, reads as an alarm.
        worst = "; ".join(describe(row) for row in late[:limit])
        return (f"Scheduled jobs overdue: {len(late)} of {len(tracked_steps())} steps "
                f"have not succeeded inside their window, which usually means the "
                f"machine or the schedule stopped rather than any one step. "
                f"Worst: {worst}.")
    return "Scheduled jobs overdue: " + "; ".join(describe(row) for row in late) + "."


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
