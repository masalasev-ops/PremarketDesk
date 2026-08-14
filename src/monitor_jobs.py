"""The watchdog: did every scheduled job run, and does anything need a rerun?

Three sources of truth, checked against each other. Task Scheduler's own record
(last run time, last result, status) says whether the machine fired the task.
The job's dated log says whether the work finished, because every .bat writes
a "===== <step> finished rc=0 =====" marker as its last act. A task that never
fired reads differently from a task that fired and died, and the fix differs
too, so both are reported by name.

The third is the step records in data/job-status.jsonl, and it was added
because the first two agreed on a lie. The nightly reported OK every night for
a week while pool_recall raised NameError inside it: the task fired, and the
marker belongs to the archive, which runs after pool_recall and really did
finish. A marker answers "did the job reach its end", which is a different
question from "did everything in it work". Both are asked now, and neither
replaces the other: the step records catch a step that failed, the marker
catches a job that died before writing any record at all.

Rerun policy lives in CRITERIA.md [monitor] and follows one principle: only
rerun what is idempotent, and never start a second live collector, because
two collectors folding the same tape write duplicate minutes and double the
premarket volume downstream. Reruns launch the job's own .bat detached, so
the rerun writes the same dated log the scheduled run would have.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import config
import criteria
import ettime
import job_status

_CRIT = criteria.load()

STATE_PATH = config.DATA_DIR / "monitor-reruns.json"
TASK_FOLDER = "\\PremarketDesk\\"

# job key -> (task name, bat file, log prefix, final success marker)
JOBS = {
    "discover": ("\\PremarketDesk\\discover", "job_discover.bat", "discover",
                 r"===== baseline warm finished rc=0"),
    "collector": ("\\PremarketDesk\\collector", "job_collector.bat", "collector",
                  r"===== collector finished rc=0"),
    "chain": ("\\PremarketDesk\\morning-chain", "job_morning_chain.bat", "morning-chain",
              r"===== archive finished rc=0"),
    "nightly": ("\\PremarketDesk\\nightly", "job_nightly.bat", "nightly",
                r"===== archive finished rc=0"),
}

# This module's job key -> the PMD_JOB name the .bat stamps on every status
# record its steps write. They differ for exactly one job and the mapping is
# explicit rather than derived, because a silent mismatch here would mean the
# step records for a job are never read and the watchdog quietly returns to
# reading only the final marker.
JOB_STATUS_NAMES = {
    "discover": "discover",
    "collector": "collector",
    "chain": "morning-chain",
    "nightly": "nightly",
}


# ------------------------------------------------------- task scheduler side

def query_task(task_name: str) -> dict[str, Any]:
    """Last run time, last result and status straight from schtasks."""
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/V", "/FO", "CSV"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    if proc.returncode != 0:
        return {"exists": False, "error": proc.stderr.strip()[:200]}
    rows = list(csv.DictReader(io.StringIO(proc.stdout)))
    if not rows:
        return {"exists": False, "error": "schtasks returned no rows"}
    row = rows[0]
    raw_last = (row.get("Last Run Time") or "").strip()
    last_run = None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try:
            last_run = dt.datetime.strptime(raw_last, fmt).replace(tzinfo=ettime.ET)
            break
        except ValueError:
            continue
    if last_run is not None and last_run.year < 2001:
        last_run = None  # the 1999 sentinel for never ran
    return {
        "exists": True,
        "status": (row.get("Status") or "").strip(),
        "last_run": last_run,
        "last_result": (row.get("Last Result") or "").strip(),
    }


# ---------------------------------------------------------------- log side

def failed_steps(job: str, day: str) -> list[str]:
    """Steps of this job that recorded a failure today, as readable phrases.

    The final step marker answers "did the job reach the end", which is not
    the same question as "did everything in it work". The nightly reported OK
    every night for a week with pool_recall raising NameError inside it,
    because the marker belongs to the archive and the archive really did
    finish. Both checks are kept: this one sees a step that failed, the marker
    sees a job that died before writing any record at all.

    A step that failed and was later rerun successfully on the same day is not
    reported, because the last record for that step is the one that describes
    the state the machine is now in.
    """
    wanted = JOB_STATUS_NAMES.get(job)
    if wanted is None:
        return []

    latest: dict[str, dict[str, Any]] = {}
    for row in job_status.records():
        if row.get("job") != wanted:
            continue
        if str(row.get("started_at") or "")[:10] != day:
            continue
        latest[str(row.get("step"))] = row

    out = []
    for step, row in sorted(latest.items()):
        if row.get("status") == job_status.STATUS_OK:
            continue
        reason = row.get("exception") or f"exit {row.get('exit_code')}"
        out.append(f"{step} recorded {row.get('status')}: {reason}")
    return out


def log_verdict(prefix: str, marker: str, day: str) -> str:
    """finished | skipped_closed | started_not_finished | no_log"""
    path = config.LOGS_DIR / f"{prefix}-{day}.log"
    if not path.exists():
        return "no_log"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "no_log"
    if re.search(marker, text):
        return "finished"
    if "market closed today" in text:
        return "skipped_closed"
    return "started_not_finished"


# ------------------------------------------------------------- rerun state

def _load_state(day: str) -> dict[str, int]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        state = {}  # the ordinary first run of the day, not a failure
    except (OSError, ValueError) as exc:
        # An unreadable state file reads as "nothing has been rerun today",
        # which silently stops max_reruns_per_job_per_day being enforced and
        # lets a hard failure loop. The watchdog still runs, so the exit code
        # is unchanged.
        print(f"monitor: rerun state unreadable ({type(exc).__name__}: {exc}), "
              "treating today as having no reruns yet; the per day rerun cap "
              "is not being enforced on this pass")
        job_status.failed(f"{type(exc).__name__}: the rerun state file is "
                          "unreadable, so the per day rerun cap is not enforced")
        state = {}
    return state.get(day, {})


def _record_rerun(day: str, job: str) -> None:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        state = {}
    state = {day: state.get(day, {})}  # keep only today, the past is in the logs
    state[day][job] = state[day].get(job, 0) + 1
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def launch_bat(bat_name: str, dry_run: bool) -> None:
    bat = config.PROJECT_ROOT / "tasks" / bat_name
    if dry_run:
        print(f"monitor: DRY RUN, would launch {bat.name} detached")
        return
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(config.PROJECT_ROOT),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    print(f"monitor: launched {bat.name} detached, it writes its own dated log")


# ------------------------------------------------------------- the checks

def _minutes(clock: tuple[int, int]) -> int:
    return clock[0] * 60 + clock[1]


def _collector_alive(now: dt.datetime) -> bool:
    """A live collector shows either a Running task or a recently touched file."""
    task = query_task(JOBS["collector"][0])
    if task.get("exists") and task.get("status", "").lower() == "running":
        return True
    stale_after = _CRIT.integer("monitor", "collector_stale_after_s")
    for path in (
        config.PREMARKET_DIR / f"{now.date().isoformat()}.jsonl",
        config.PREMARKET_DIR / f"{now.date().isoformat()}-stats.jsonl",
    ):
        if path.exists():
            age = now.timestamp() - path.stat().st_mtime
            # The lower bound guards the --at simulation and clock skew: a
            # file from this evening must not look alive at a simulated 08:00.
            if -60 <= age <= stale_after:
                return True
    return False


def check_all(now: dt.datetime, dry_run: bool) -> int:
    day = now.date().isoformat()
    now_m = now.hour * 60 + now.minute
    reruns_done = _load_state(day)
    max_reruns = _CRIT.integer("monitor", "max_reruns_per_job_per_day")
    problems = 0
    actions = 0

    def report(job: str, verdict: str, detail: str) -> None:
        print(f"monitor: {job:<10} {verdict:<12} {detail}")

    def steps_ok(job: str) -> bool:
        """Did every step inside this job record success today.

        Asked in addition to the final step marker, never instead of it. The
        marker says the job reached its end; this says nothing inside it
        failed on the way. The nightly answered yes to the first and no to
        the second every night for a week.
        """
        nonlocal problems
        broken = failed_steps(job, day)
        if not broken:
            return True
        problems += 1
        for line in broken:
            report(job, "STEP FAILED", line)
        return False

    def maybe_rerun(job: str, reason: str) -> None:
        nonlocal actions
        if reruns_done.get(job, 0) >= max_reruns:
            report(job, "GAVE UP", f"{reason}; already rerun "
                   f"{reruns_done[job]} time(s) today, a human should look")
            return
        report(job, "RERUNNING", reason)
        launch_bat(JOBS[job][1], dry_run)
        if not dry_run:
            _record_rerun(day, job)
        actions += 1

    # ---- universe freshness, the weekly job the weekday monitor can save
    try:
        universe_payload = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
        generated = dt.datetime.fromisoformat(universe_payload["generated_at"])
        age_days = (now - generated).total_seconds() / 86400.0
    except (OSError, ValueError, KeyError):
        age_days = None
    limit_days = _CRIT.integer("monitor", "universe_rerun_after_days")
    if age_days is None or age_days >= limit_days:
        problems += 1
        maybe_rerun_universe = age_days is None or age_days >= limit_days
        if maybe_rerun_universe:
            if reruns_done.get("universe", 0) >= max_reruns:
                report("universe", "GAVE UP", "stale and already rerun today")
            else:
                report("universe", "RERUNNING",
                       f"universe.json is {age_days:.1f} days old" if age_days is not None
                       else "universe.json is missing or unreadable")
                launch_bat("job_universe.bat", dry_run)
                if not dry_run:
                    _record_rerun(day, "universe")
                actions += 1
    else:
        report("universe", "OK", f"{age_days:.1f} days old")

    # ---- discover
    discover_due = _minutes(_CRIT.clock("monitor", "discover_due"))
    collector_start = _minutes(_CRIT.clock("collector", "start_time"))
    if now_m < discover_due:
        report("discover", "NOT DUE", "")
    else:
        verdict = log_verdict("discover", JOBS["discover"][3], day)
        if verdict in ("finished", "skipped_closed"):
            if steps_ok("discover"):
                report("discover", "OK", verdict)
        else:
            problems += 1
            task = query_task(JOBS["discover"][0])
            fired = task.get("last_run") is not None and task["last_run"].date() == now.date()
            detail = ("fired but did not finish" if fired
                      else "never fired today, the machine was probably asleep")
            if now_m < collector_start:
                maybe_rerun("discover", detail)
            else:
                report("discover", "FAILED", detail + ". Not rerun: the collector "
                       "window has opened or passed, and a rewritten watchlist would "
                       "desync it from what was actually subscribed. Scan flags the "
                       "holes honestly.")

    # ---- collector
    collector_stop = _minutes(_CRIT.clock("collector", "stop_time"))
    if now_m < collector_start:
        report("collector", "NOT DUE", "")
    elif now_m < collector_stop:
        if _collector_alive(now):
            report("collector", "RUNNING", "bar file moving or task running")
        else:
            problems += 1
            maybe_rerun("collector", "inside the window with no live collector; "
                        "restart is safe, it resumes the bar file")
    else:
        verdict = log_verdict("collector", JOBS["collector"][3], day)
        if verdict in ("finished", "skipped_closed"):
            if steps_ok("collector"):
                report("collector", "OK", verdict)
        else:
            problems += 1
            report("collector", "FAILED", f"window over, log says {verdict}. "
                   "Nothing to rerun; tonight's backfill still writes the true window.")

    # ---- morning chain
    chain_due = _minutes(_CRIT.clock("monitor", "chain_due"))
    chain_until = _minutes(_CRIT.clock("monitor", "rerun_chain_until"))
    if now_m < chain_due:
        report("chain", "NOT DUE", "")
    else:
        verdict = log_verdict("morning-chain", JOBS["chain"][3], day)
        if verdict in ("finished", "skipped_closed"):
            if steps_ok("chain"):
                report("chain", "OK", verdict)
        else:
            problems += 1
            task = query_task(JOBS["chain"][0])
            fired = task.get("last_run") is not None and task["last_run"].date() == now.date()
            detail = "fired but did not finish" if fired else "never fired today"
            if now_m <= chain_until:
                maybe_rerun("chain", detail + "; the chain is idempotent")
            else:
                report("chain", "FAILED", detail + f". Past "
                       f"{_CRIT.clock_text('monitor', 'rerun_chain_until')} ET, a premarket "
                       "report is history; run tasks\\job_morning_chain.bat by hand if "
                       "still wanted.")

    # ---- nightly
    nightly_due = _minutes(_CRIT.clock("monitor", "nightly_due"))
    if now_m < nightly_due:
        report("nightly", "NOT DUE", "")
    else:
        verdict = log_verdict("nightly", JOBS["nightly"][3], day)
        task = query_task(JOBS["nightly"][0])
        fired = task.get("last_run") is not None and task["last_run"].date() == now.date()
        # A finished log alone is not enough here: an ad hoc afternoon run
        # also writes the marker, and it must not mask a scheduled run that
        # never fired or died before the bat even started (the 0x80070002
        # quoting failure looked exactly like that). The job is idempotent,
        # so the extra rerun is cheap.
        fired_ok = fired and task.get("last_result") == "0"
        if verdict == "skipped_closed" or (verdict == "finished" and fired_ok):
            if steps_ok("nightly"):
                report("nightly", "OK", verdict)
        else:
            problems += 1
            maybe_rerun("nightly", ("fired but did not finish" if fired
                                    else "the scheduled task never fired today")
                        + "; fully idempotent")

    print(f"monitor: {problems} problem(s), {actions} action(s) taken")
    job_status.produced("jobs checked", len(JOBS))
    return 0 if problems == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the scheduled jobs, rerun what is safe.")
    parser.add_argument("--at", metavar="HH:MM", default=None,
                        help="Evaluate as if the clock read this ET time today, for testing.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Decide and report, launch nothing, record nothing.")
    args = parser.parse_args(argv)

    now = ettime.now_et()
    if args.at:
        hour, minute = (int(part) for part in args.at.split(":"))
        now = now.replace(hour=hour, minute=minute)
        print(f"monitor: pretending the clock reads {args.at} ET")

    config.ensure_dirs()
    return check_all(now, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(job_status.run("monitor", main))
