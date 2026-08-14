"""The watchdog: did every scheduled job run, and does anything need a rerun?

Two sources of truth, checked against each other. Task Scheduler's own record
(last run time, last result, status) says whether the machine fired the task.
The job's dated log says whether the work finished, because every .bat writes
a "===== <step> finished rc=0 =====" marker as its last act. A task that never
fired reads differently from a task that fired and died, and the fix differs
too, so both are reported by name.

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
    except (OSError, ValueError):
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
        # never fired. The job is idempotent, so the extra rerun is cheap.
        if verdict == "skipped_closed" or (verdict == "finished" and fired):
            report("nightly", "OK", verdict)
        else:
            problems += 1
            maybe_rerun("nightly", ("fired but did not finish" if fired
                                    else "the scheduled task never fired today")
                        + "; fully idempotent")

    print(f"monitor: {problems} problem(s), {actions} action(s) taken")
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
    sys.exit(main())
