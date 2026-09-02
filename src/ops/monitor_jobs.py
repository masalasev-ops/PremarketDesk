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

Idempotent is not the same as safe to run TWICE AT ONCE, and until 2026-08-20
only the collector branch knew the difference. The chain and the nightly were
rerun on the absence of a finish marker alone, and a job that started seconds
ago has not written that marker, so it read exactly like one that died.
_job_alive is the gate the collector always had, now asked of every job before
any rerun.

That gate then made a mistake of its own, corrected the same day. It read any
dated log written inside job_log_stale_after_s as proof of life, and the chain
and nightly branches took that as a clean RUNNING: nothing counted, nothing
done, exit 0. Each of those two jobs is judged by exactly ONE monitor pass
inside the window it can still be fixed in, 09:25 for the chain and 22:45 for
the nightly, so a job that died in the twenty minutes before its one pass spent
that pass on a verdict of "ask again later" that nobody ever asks. A job that
EXITED says so in its log, so the log is now read for a finish marker before
its mtime is read for warmth; and where only the mtime answers, the pass with
no successor inside the window counts the job as a problem rather than
reporting it well.
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

from core import config
from core import criteria
from core import ettime
from ops import job_status

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
    # The 12:00 pass. Added 2026-08-31, having run since that morning watched
    # by nothing: the weekday monitor stops at last_pass and monitor-night is
    # at 22:45, so a midday failure was first named by job_status.overdue in
    # the NEXT morning's packet, about eighteen hours later, and never rerun.
    # The marker is the LAST step job_midday.bat writes, the render, because a
    # scan that succeeded and a render that failed is still a failed job.
    "midday": ("\\PremarketDesk\\midday", "job_midday.bat", "midday",
               r"===== midday render finished rc=0"),
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
    "midday": "midday",
}

# What Task Scheduler puts in the Last Result column while a task is still
# going: 0x41301, "the task is currently running", 267009 in decimal. It is
# not a failure code and the nightly branch used to read it as one, because it
# required last_result == "0" to accept a finished log. A nightly still running
# at 22:45 therefore counted as a nightly that had failed, and a second copy
# was launched on top of the first.
TASK_STILL_RUNNING = 267009


# ------------------------------------------------------- task scheduler side

def query_task(task_name: str) -> dict[str, Any]:
    """Last run time, last result and status straight from schtasks.

    Every failure comes back as {"exists": False, "error": ...}, which is what
    every caller already handles. The non-zero exit was absorbed from the
    start; TimeoutExpired and OSError were not, and they are the two that
    matter on a struggling machine. schtasks taking more than sixty seconds
    while the box is thrashing, or not being on PATH at all, raised straight
    through _collector_alive and check_all and killed the whole watchdog pass,
    which then did none of its other work either: no collector restart, no
    chain rerun, no flag backlog line, just a traceback in the log. The next
    chance was thirty minutes later, by which time the collector has lost half
    its window. A watchdog that dies when the machine is unwell is a watchdog
    absent exactly when it is needed.

    The same pair is caught the same way around config.build_identifier's
    subprocess call, which is the convention this now follows.
    """
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/V", "/FO", "CSV"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        # SubprocessError covers TimeoutExpired; OSError covers a missing or
        # unrunnable schtasks. Both mean the same thing to every caller: this
        # task could not be queried.
        return {"exists": False,
                "error": f"{type(exc).__name__}: {config.scrub_secrets(exc)}"[:200]}
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

def failed_steps(job: str, day: str) -> tuple[list[str], int]:
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

    Returns (failure phrases, number of step records read). The second is
    what stops an empty record set reading as a clean job.
    """
    wanted = JOB_STATUS_NAMES.get(job)
    if wanted is None:
        return [], 0

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
    # The count is the denominator: a caller cannot tell "every step passed"
    # from "no step recorded anything" without it.
    return out, len(latest)


def _log_path(prefix: str, day: str) -> Path:
    """The dated log a job appends to.

    One definition because three readers ask different questions of the same
    file: log_verdict reads its TEXT for the job's final step marker,
    last_step_marker reads the same text for the last boundary of ANY step,
    and _job_alive reads its MTIME for evidence that the job is still writing.
    """
    return config.LOGS_DIR / f"{prefix}-{day}.log"


def log_verdict(prefix: str, marker: str, day: str) -> str:
    """finished | skipped_closed | started_not_finished | no_log"""
    path = _log_path(prefix, day)
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


# The step boundaries every .bat writes around every step it runs:
# "===== scan started Thu 08/20/2026  8:45:01.16 =====" before, and
# "===== scan finished rc=0 Thu 08/20/2026  8:45:22.03 =====" after. Lines that
# are not step boundaries deliberately do not match, "===== gate table ====="
# and "===== market closed today, morning chain skipped =====" among them,
# because neither says anything about whether a step is running.
_STEP_MARKER_RE = re.compile(
    r"^===== (?P<step>.+?) (?:started|finished rc=(?P<rc>-?\d+))\b",
    re.MULTILINE)


def last_step_marker(prefix: str, day: str) -> tuple[str, int | None] | None:
    """The last step boundary in a job's dated log, as (step, exit code).

    The exit code is None for a "started" marker, which is the shape that means
    a step is between its two lines, and an integer for a "finished" one, which
    means the step returned and the .bat had control back when the line was
    written. None for a log with no boundary in it at all, which is the first
    seconds of a job: every .bat runs ops.market_today before its first marker.

    Scanned from the whole file rather than read off the tail, for two reasons.
    The python step writes its own output into the same log between the two
    markers, so the marker is rarely the last line. And a dated log can carry
    more than one run: the nightly appends both the 07:00 catch-up and the
    22:15 pass to the same file, and the LAST marker is the one that describes
    the state the machine is in now.
    """
    try:
        text = _log_path(prefix, day).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    last = None
    for match in _STEP_MARKER_RE.finditer(text):
        last = match
    if last is None:
        return None
    raw = last.group("rc")
    return last.group("step"), None if raw is None else int(raw)


def _exit_marker(job: str, day: str) -> str | None:
    """A phrase naming the FAILING finish marker this job's log ends in.

    None when the log ends in a started marker, in a clean finish, or in no
    marker at all. This is the fact "fired but did not finish" cannot carry:
    that sentence is the same one for a job that exited on a bad step, a job
    still working, and a job the machine lost power under, and the report used
    to print it for all three.
    """
    marker = last_step_marker(JOBS[job][2], day)
    if marker is None or marker[1] is None or marker[1] == 0:
        return None
    return (f'its log ends in "{marker[0]} finished rc={marker[1]}", so it '
            "exited on that step rather than being slow")


# ------------------------------------------------------------- rerun state

# How hard _record_rerun tries before it gives up and says so. Not CRITERIA
# keys: this file's threshold rule covers decision thresholds, and these are the
# retry shape of one write. Sized against the documented antivirus denial, which
# has cleared within a second every time it has been seen.
STATE_WRITE_ATTEMPTS = 4
STATE_WRITE_RETRY_S = 0.5


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
    """Count one rerun against today's cap. Called AFTER the job was launched.

    Which is what makes the write matter. _load_state above already treats an
    unreadable state file as serious enough to declare the step failed, because
    a lost count silently stops max_reruns_per_job_per_day being enforced and
    lets a hard failure loop every thirty minutes. A FAILED WRITE leaves exactly
    the same state, and until this it did so while also raising through the
    pass: the .bat was already running, so the launch stood and only the record
    of it was lost.

    Written through a temp sibling and os.replace so a reader never meets half a
    state file, retried because this machine's antivirus intermittently denies a
    first write, and reported rather than raised for the same reason the read
    path reports: the watchdog's remaining checks are worth more than its exit
    code.
    """
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        state = {}
    state = {day: state.get(day, {})}  # keep only today, the past is in the logs
    state[day][job] = state[day].get(job, 0) + 1

    body = json.dumps(state, indent=2)
    # core/files.py is the one atomic writer since 2026-09-02, retries included.
    from core import files

    last: Exception | None = None
    try:
        files.write_text_atomically(STATE_PATH, body, attempts=STATE_WRITE_ATTEMPTS,
                                    retry_s=STATE_WRITE_RETRY_S)
        return
    except OSError as exc:
        last = exc

    print(f"monitor: {job} was relaunched and the rerun could not be recorded "
          f"after {STATE_WRITE_ATTEMPTS} attempts ({type(last).__name__}: {last}); "
          "the per day rerun cap is not being enforced for it")
    job_status.failed(f"{type(last).__name__}: {job} was relaunched and the "
                      "rerun state file could not be written, so the per day "
                      "rerun cap is not enforced for it")


def launch_bat(bat_name: str, dry_run: bool, args: tuple[str, ...] = ()) -> None:
    """Start a job .bat detached, optionally with arguments.

    args exists for exactly one caller and is empty for every other. The
    collector refuses a watchlist that is not today's, and the last-resort
    branch below is the only place in this project entitled to overrule that,
    because it is the only one that knows no later pass falls inside the
    window. Passing it from anywhere else reintroduces the 2026-08-24 defect
    the refusal closed. See CRITERIA [Monitor], the stale watchlist note.
    """
    bat = config.PROJECT_ROOT / "tasks" / bat_name
    if dry_run:
        extra = f" with {' '.join(args)}" if args else ""
        print(f"monitor: DRY RUN, would launch {bat.name}{extra} detached")
        return
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["cmd", "/c", str(bat), *args],
        cwd=str(config.PROJECT_ROOT),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    said = f" with {' '.join(args)}" if args else ""
    print(f"monitor: launched {bat.name}{said} detached, it writes its own dated log")


# ----------------------------------------------------- the flag backlog

def flag_backlog(now: dt.datetime) -> dict[str, Any]:
    """The quantifier guard flags nobody has judged, and the oldest one's age.

    Not a job check. This asks whether a MEASUREMENT is still being taken,
    which is a different question, and one this project has already got wrong
    in exactly this shape: pool_recall raised every night for a week while
    writing nothing, and DECISIONS cited its evidence as accumulating the
    whole time. The quantifier flag log has the same failure available to it.
    Dispositions are recorded by hand, so a log that fills while nobody judges
    means the false positive rate never prints, and in a month the word list
    gets tuned on the same intuition it was written with.

    Nothing here can fail the watchdog's other work. An unreadable or
    undateable log is reported as its own problem rather than raised, because
    a missing measurement must not cost the checks that watch the jobs.
    """
    from ops import quantifier_flags

    try:
        flags = quantifier_flags.load_flags()
    except (OSError, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

    pending = [f for f in flags
               if f.get("disposition") not in quantifier_flags.VERDICTS]
    oldest_days = None
    oldest_session = None
    undated = 0
    for flag in pending:
        try:
            raised = dt.datetime.fromisoformat(str(flag.get("recorded_at")))
            # Clamped at zero because --at can wind the clock back to simulate
            # an earlier hour, and a flag raised later today must read as new
            # rather than as a negative age nobody can interpret.
            age = max(0.0, (now - raised).total_seconds() / 86400.0)
        except (TypeError, ValueError):
            undated += 1
            continue
        if oldest_days is None or age > oldest_days:
            oldest_days = age
            oldest_session = flag.get("session")
    return {
        "raised": len(flags),
        "pending": len(pending),
        "oldest_days": oldest_days,
        "oldest_session": oldest_session,
        "undated": undated,
    }


# ------------------------------------------------------------- the checks

def _minutes(clock: tuple[int, int]) -> int:
    return clock[0] * 60 + clock[1]


def _clock_text(minute_of_day: int) -> str:
    """Minutes past midnight back as HH:MM, for a line a human reads."""
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _next_pass_minute(now_m: int) -> int | None:
    """The next monitor firing after this one, in minutes past midnight, or None.

    Several verdicts below defer to "the next pass": the collector hold waits
    one pass rather than starting on a watchlist discover is rewriting, and the
    liveness gate leaves a warm log to be read again. Every one of those is a
    promise that a later pass acts, and a promise nobody keeps is worse than
    the verdict it replaced, so the promise is checked here before it is made.

    register_tasks.ps1 is the source of the schedule and CRITERIA holds the
    values, because a schedule literal in this module is exactly as unowned as
    a threshold literal would be. The weekday monitor starts at first_pass and
    repeats every pass_interval_min through last_pass, which is 07:25, 07:55,
    08:25, 08:55 and 09:25; monitor-midday starts at midday_first_pass and
    repeats on the same interval through midday_last_pass, which is 12:25,
    12:55 and 13:25; and monitor-night is one firing at night_pass with no
    repetition after it.

    [corrected 2026-09-01: the paragraph above named only the morning grid and
    ran straight from 09:25 to night_pass. It went on saying that after the
    body below gained midday_first_pass and midday_last_pass, and it is the
    schedule of record inside this module, so the next pass after 09:25 read
    as 22:45 in the prose where the body returns 12:25. Every verdict that
    defers work to "the next pass" is priced off that number.]

    Tomorrow's first_pass is deliberately not a successor. Every log this
    module reads is dated, so by tomorrow the job a deferred verdict was about
    is in yesterday's file, and job_status.overdue cannot surface it either
    because backfill, outcomes and pool_recall each carry a one session window.
    """
    first = _minutes(_CRIT.clock("monitor", "first_pass"))
    last = _minutes(_CRIT.clock("monitor", "last_pass"))
    night = _minutes(_CRIT.clock("monitor", "night_pass"))
    midday_first = _minutes(_CRIT.clock("monitor", "midday_first_pass"))
    midday_last = _minutes(_CRIT.clock("monitor", "midday_last_pass"))
    every = _CRIT.integer("monitor", "pass_interval_min")
    if every <= 0:
        # A monitor registered without a repetition has only its triggers.
        # Reading it that way is the safe direction: every caller then acts now
        # rather than deferring to a pass that is not going to come.
        candidates = [first, midday_first, night]
    else:
        candidates = (list(range(first, last + 1, every))
                      + list(range(midday_first, midday_last + 1, every))
                      + [night])
    later = [minute for minute in candidates if minute > now_m]
    return min(later) if later else None


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


def _task_running(task: dict[str, Any], today: dt.date) -> bool:
    """Does Task Scheduler say this task is running at this instant.

    Two spellings of one fact, because schtasks reports it in two columns.
    Status reads Running while the task is live. Last Result reads
    TASK_STILL_RUNNING, which is the column the nightly branch used to read as
    a plain result code. The column comes back decimal on this machine and
    0x41301 on some others, so the 0x form is parsed as hexadecimal and
    everything else as the signed decimal Windows actually reports.
    """
    if not task.get("exists"):
        return False
    if str(task.get("status") or "").strip().lower() == "running":
        return True
    last_run = task.get("last_run")
    if last_run is None or last_run.date() != today:
        # A still running code left over from a PREVIOUS day is a run
        # Scheduler never got a completion from, not one running now.
        return False
    raw = str(task.get("last_result") or "").strip()
    try:
        return int(raw, 16 if raw[:2].lower() == "0x" else 10) == TASK_STILL_RUNNING
    except ValueError:
        return False


def _job_alive(job: str, now: dt.datetime,
               task: dict[str, Any]) -> tuple[str | None, bool]:
    """Evidence that this job is running right now, and whether it settles it.

    Returns (phrase, settled). The phrase is None when nothing says the job is
    alive. settled qualifies the phrase and only means anything when there is
    one: True where the evidence answers the question outright, False where it
    is the reading a live job and a recently dead one both produce.

    The collector has had this gate since it was written, because two live
    collectors fold the same tape into duplicate minutes. The chain, the
    nightly and discover had none: they were rerun on the absence of a finish
    marker in the dated log, and a job that started seconds ago has not
    written that marker, so it was indistinguishable from one that died.

    The trigger is a late machine wake. Every task carries
    -StartWhenAvailable, and two of them catching up within 0.15 seconds of
    each other is already on record: monitor 08:21:18.56 and nightly-catchup
    08:21:18.71 on 2026-08-19. Sleep through 08:45, wake at 09:05, and
    Scheduler fires the missed chain and the missed monitor together. At
    09:05 chain_due has passed, rerun_chain_until has not, the log is fifteen
    seconds old, and a second job_morning_chain.bat starts: two scans write
    packet.json and premarket_snapshot.jsonl at once, two analyst steps each
    spend a claude CLI completion (0.5 USD and 231.7 seconds measured on
    2026-08-20), and two build_archive runs both do a non atomic write_text on
    site/PremarketDesk.html. scan.thin_rerun_stands_down does not help, because
    its "if not existing_path.is_file()" test is defeated by a concurrent
    original that has not written yet.

    Two kinds of evidence, the same two _collector_alive uses. Task Scheduler
    covers the copy Scheduler itself started. The dated log covers the copy it
    cannot see, since launch_bat Popens the .bat rather than starting the task:
    a rerun this module launched detached, and the hand run the chain's own
    FAILED message invites by name. job_log_stale_after_s has to clear the
    longest silence a healthy job can produce, which is the analyst step at
    [analyst] max_attempts times timeout_s.

    There is deliberately no lock file. The .bat files do not take one, so a
    lock held by this module alone would be a lie about what it protects.

    The two kinds of evidence are not equally good, and the first version of
    this gate treated them as if they were. Task Scheduler's Running settles it: the
    task is live at this instant. A warm log does not, because it is the SAME
    reading for a job writing now and for a job that stopped writing nineteen
    minutes ago, and the caller has to know which of those it is holding. What
    a log can settle is DEATH, and that is now asked first: every .bat echoes
    "===== <step> finished rc=<n> =====" once the step has returned, and exits
    on a non-zero one, so a log whose last marker is a finish belongs to a job
    that is over however fresh the line is. The chain that died at 09:20 reads
    as dead at 09:25 rather than as fifteen seconds of healthy work.
    """
    if _task_running(task, now.date()):
        return "Task Scheduler reports the task running", True
    day = now.date().isoformat()
    marker = last_step_marker(JOBS[job][2], day)
    if marker is not None and marker[1] is not None:
        # A finish marker of ANY rc means the .bat had control back when it was
        # written, so the job is not between two markers and the mtime is not
        # asked. rc=0 is included because the mid job case it describes lasts
        # only the microseconds between one echo and the next, while the whole
        # job case it also describes is a job that is genuinely finished. The
        # caller names a non-zero one through _exit_marker.
        return None, True
    stale_after = _CRIT.integer("monitor", "job_log_stale_after_s")
    path = _log_path(JOBS[job][2], day)
    try:
        age = now.timestamp() - path.stat().st_mtime
    except OSError:
        return None, True
    # The lower bound guards the --at simulation and clock skew exactly as it
    # does in _collector_alive: a log written this evening must not read as
    # alive at a simulated 08:00.
    if -60 <= age <= stale_after:
        return f"its dated log was written {age:.0f}s ago", False
    return None, True


def _watchlist_vintage(day: str) -> tuple[bool, str]:
    """Is data/watchlist.json the file today's collector should subscribe from.

    Returns (stale, a phrase naming what is on disk).

    This used to be the only thing in the pipeline that asked.
    [corrected 2026-08-24: two of the three clauses below are now false and are
    kept because the reasoning they justify is still the reason this helper
    exists. collect_premarket now REFUSES a watchlist that is not today's, and
    scan raises a gap both on a stale file and on a subscription list that does
    not match it. discover.load_watchlist still applies no date test and
    vintage.enforce still never mentions the watchlist.]

    The original: "collect_premarket checks only that the file exists,
    discover.load_watchlist applies no date test, scan records
    watchlist_generated_at into provenance and screens either way, and
    vintage.enforce never mentions the watchlist at all, so a PREVIOUS
    SESSION's names were nowhere detected as stale." That is the condition the
    discover rerun below actually turns on, and the clock it used to turn on
    was only ever a proxy for it.
    """
    from selection import discover

    watchlist = discover.load_watchlist()
    if watchlist.get("missing"):
        return True, "data/watchlist.json is missing or unreadable"
    generated = str(watchlist.get("generated_at") or "")
    if not generated:
        return True, "data/watchlist.json carries no generated_at, so its session is unknown"
    if generated[:10] != day:
        return True, (f"data/watchlist.json is from {generated[:10]}, a previous "
                      "session, so the names on disk are not today's")
    return False, f"data/watchlist.json is today's, written {generated[11:16]} ET"


def _rewriting_the_watchlist_is_free(day: str, now_m: int) -> tuple[bool, str]:
    """May discover be rerun without desyncing what is being listened to.

    Two ways it is free, and the second is new on 2026-09-02.

    NOTHING HAS SUBSCRIBED YET. write_subscriptions runs before the socket
    opens on every collector mode and names exactly what was asked for, so
    while that file is absent there is nothing to desync, whatever the clock
    reads. This is the question the collector start clock used to stand in
    for.

    OR THE COLLECTOR WILL READ IT AGAIN. The run is two phase now: it starts
    at 04:00 on the provisional pool and rereads data/watchlist.json every
    [Collector] pool_reload_check_s from resubscribe_time, resubscribing
    whenever the generated_at changes, up to max_pool_reloads times. A rewrite
    inside that window is not a desync, it is the mechanism. Before
    resubscribe_time a rewrite is free because the handover has not happened;
    the deliberate five minute gap between resubscribe_time and [Monitor]
    discover_due is what gives a watchdog rerun of a failed 07:15 pass
    somewhere to land.

    Returns (free, why) so the caller can say which of the two it was.
    """
    from collect import collect_premarket

    if not collect_premarket.subscriptions_path(day).is_file():
        return True, ("No subscription list has been written today, so nothing "
                      "is listening to the watchlist and a rewrite desyncs nothing")
    reload_end = (_minutes(_CRIT.clock("collector", "resubscribe_time"))
                  + int(_CRIT.number("collector", "pool_reload_check_s")
                        * _CRIT.integer("collector", "max_pool_reloads") / 60) + 1)
    stop = _minutes(_CRIT.clock("collector", "stop_time"))
    if now_m < min(reload_end, stop):
        return True, ("the collector is listening but rereads the watchlist "
                      "after its resubscribe time, so a rewrite now is picked "
                      "up rather than desynced")
    return False, ""


# ------------------------------------------------- schedule reconciliation

# THIS IS A MONITOR CHECK AND IT CANNOT BE A CLAIM. Every guard in this
# project reads the tree. Task Scheduler is state OUTSIDE the tree, and the
# suite runs in a sandbox with no scheduler in it at all, so no test can see
# what is registered. Do not move this into test_regressions: a claim that
# passes because it cannot see the machine is worse than no claim.
#
# It exists because this is the SECOND gap that has lived in that blind spot.
# The first was -WakeToRun, set in the script and absent from the live tasks.
# The second was monitor-midday, in the $jobs array since 2026-08-31 and never
# registered, so the three pass midday window existed in ops/monitor_jobs.py,
# in CRITERIA [Monitor], in both architecture pages and in a claim, and never
# fired once. Both were found by hand, months apart, by someone happening to
# count.
#
# The script is the specification and the machine is the fact. Disagreement in
# EITHER direction is a finding: a name the script knows and the machine lacks
# never runs, and a name the machine carries and the script does not is a task
# a full re-registration will not maintain and -Unregister may not remove.

REGISTER_SCRIPT = config.PROJECT_ROOT / "tasks" / "register_tasks.ps1"

# One $jobs entry. Start is required; the repetition pair is optional and is
# absent for the tasks that fire once.
_JOBS_ENTRY = re.compile(
    r'@\{\s*Name\s*=\s*"(?P<name>[^"]+)"(?P<rest>[^}]*)\}')
_FIELD_START = re.compile(r'Start\s*=\s*"(?P<value>\d{1,2}:\d{2})"')
_FIELD_REPEAT_MIN = re.compile(r'RepeatMin\s*=\s*(?P<value>\d+)')
_FIELD_REPEAT_HOURS = re.compile(r'RepeatHours\s*=\s*(?P<value>\d+)')

# schtasks renders a duration as "0 Hour(s), 30 Minute(s)", or the string
# Disabled when there is none. Locale dependent, which is why a parse failure
# reports NOT CHECKED rather than a disagreement.
_DURATION = re.compile(r"(?P<hours>\d+)\s*Hour\(s\),\s*(?P<minutes>\d+)\s*Minute\(s\)")


def _duration_minutes(text: str | None) -> int | None:
    """Minutes, 0 for Disabled, or None when the string is not understood."""
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned or cleaned.lower() == "disabled":
        return 0
    found = _DURATION.search(cleaned)
    if not found:
        return None
    return int(found.group("hours")) * 60 + int(found.group("minutes"))


def _clock_minutes(text: str | None) -> int | None:
    """Minutes past midnight from schtasks' "12:25:00 PM", or None."""
    if not text:
        return None
    for form in ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"):
        try:
            parsed = dt.datetime.strptime(text.strip(), form)
        except ValueError:
            continue
        return parsed.hour * 60 + parsed.minute
    return None


def script_jobs() -> tuple[dict[str, dict[str, Any]], str | None]:
    """The $jobs array as the script declares it, or a reason it is unknown."""
    if not REGISTER_SCRIPT.is_file():
        return {}, f"{REGISTER_SCRIPT} is not on disk"
    try:
        text = REGISTER_SCRIPT.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, f"{REGISTER_SCRIPT} could not be read: {exc}"
    out: dict[str, dict[str, Any]] = {}
    for entry in _JOBS_ENTRY.finditer(text):
        rest = entry.group("rest")
        start = _FIELD_START.search(rest)
        if not start:
            # A one off probe block, not a $jobs entry. Those are deliberately
            # outside the array so a plain run cannot resurrect them.
            continue
        hour, _, minute = start.group("value").partition(":")
        repeat_min = _FIELD_REPEAT_MIN.search(rest)
        repeat_hours = _FIELD_REPEAT_HOURS.search(rest)
        out[entry.group("name")] = {
            "start_minute": int(hour) * 60 + int(minute),
            "start_text": start.group("value"),
            "repeat_every_minutes": int(repeat_min.group("value")) if repeat_min else 0,
            "repeat_for_minutes": int(repeat_hours.group("value")) * 60 if repeat_hours else 0,
        }
    if not out:
        return {}, (f"no $jobs entries parsed out of {REGISTER_SCRIPT.name}, so "
                    "the specification could not be read")
    return out, None


def registered_tasks() -> tuple[dict[str, dict[str, Any]], str | None]:
    """Every task under the folder, from schtasks, or a reason it is unknown."""
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_FOLDER, "/FO", "CSV", "/V"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {}, f"schtasks did not answer: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return {}, (f"schtasks exited {proc.returncode}"
                    + (f": {detail[0]}" if detail else ""))
    try:
        rows = list(csv.DictReader(io.StringIO(proc.stdout)))
    except csv.Error as exc:
        return {}, f"schtasks output did not parse as CSV: {exc}"
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = (row.get("TaskName") or "").strip()
        if not name.startswith(TASK_FOLDER):
            continue
        out[name[len(TASK_FOLDER):]] = {
            "start_minute": _clock_minutes(row.get("Start Time")),
            "start_text": (row.get("Start Time") or "").strip(),
            "repeat_every_minutes": _duration_minutes(row.get("Repeat: Every")),
            "repeat_for_minutes": _duration_minutes(row.get("Repeat: Until: Duration")),
        }
    if not out:
        return {}, (f"schtasks returned no task under {TASK_FOLDER}, which is "
                    "either an empty folder or a query this could not read. "
                    "Those are different and this cannot tell them apart")
    return out, None


def reconcile_schedule() -> dict[str, Any]:
    """What the script says against what the machine has.

    NEVER reports agreement it did not establish. If either side could not be
    read the result is checked=False with the reason, and the caller prints NOT
    CHECKED. An empty result reading as "no differences" is the exact failure
    this project keeps finding.
    """
    spec, spec_error = script_jobs()
    if spec_error:
        return {"checked": False, "reason": spec_error}
    live, live_error = registered_tasks()
    if live_error:
        return {"checked": False, "reason": live_error}

    missing = sorted(set(spec) - set(live))
    extra = sorted(set(live) - set(spec))
    differs: list[str] = []
    unreadable: list[str] = []
    for name in sorted(set(spec) & set(live)):
        want, got = spec[name], live[name]
        fields = ("start_minute", "repeat_every_minutes", "repeat_for_minutes")
        if any(got[field] is None for field in fields):
            unreadable.append(
                f"{name}: schtasks gave a start of {got['start_text']!r} and a "
                "repetition this could not parse, so it is NOT being reported "
                "as agreeing")
            continue
        for field, label in (("start_minute", "start"),
                             ("repeat_every_minutes", "repeat every"),
                             ("repeat_for_minutes", "repeat for")):
            if want[field] != got[field]:
                differs.append(
                    f"{name}: {label} is {got[field]} minute(s) on the machine "
                    f"and {want[field]} in $jobs")
    return {"checked": True, "reason": None, "missing": missing,
            "extra": extra, "differs": differs, "unreadable": unreadable,
            "spec_count": len(spec), "live_count": len(live)}


def check_all(now: dt.datetime, dry_run: bool) -> int:
    day = now.date().isoformat()
    now_m = now.hour * 60 + now.minute
    # Read here and consulted by three branches. Any verdict that defers work
    # to a later pass has to know whether there is one, because the chain, the
    # nightly and a held collector each have windows that outlast at most one
    # more firing of this task.
    #
    # Those three, and NOT every consumer of a next pass in this function. The
    # midday branch takes its own reading under its own name, so that giving
    # midday a clock of its own later cannot reach these three.
    # [corrected 2026-09-01: this opened "Read once" and claimed the three
    # were all of them. Midday had already added a second call, and that call
    # was binding this same name out from under the nightly.]
    next_pass = _next_pass_minute(now_m)
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
        broken, examined = failed_steps(job, day)
        if not examined:
            # Zero step records is not zero failures. It is the state a job
            # that died before writing anything leaves, and it is also what a
            # renamed PMD_JOB or a deleted record file leaves. This source of
            # truth was added because the other two agreed on a lie; its own
            # empty case would restore exactly that.
            problems += 1
            report(job, "NO RECORDS", "no step of this job recorded anything today, "
                   "so nothing inside it can be vouched for")
            return False
        if not broken:
            return True
        problems += 1
        for line in broken:
            report(job, "STEP FAILED", f"{line} ({examined} step record(s) read)")
        return False

    def maybe_rerun(job: str, reason: str, args: tuple[str, ...] = ()) -> bool:
        """True when a .bat was actually launched.

        The answer is returned rather than dropped because one caller has to
        sequence on it: a collector started in the same pass as a discover
        rerun would read the watchlist that rerun is in the middle of
        replacing.
        """
        nonlocal actions
        if reruns_done.get(job, 0) >= max_reruns:
            report(job, "GAVE UP", f"{reason}; already rerun "
                   f"{reruns_done[job]} time(s) today, a human should look")
            return False
        report(job, "RERUNNING", reason)
        launch_bat(JOBS[job][1], dry_run, args)
        if not dry_run:
            _record_rerun(day, job)
        actions += 1
        return True

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
    #
    # The rerun used to be gated on "now_m < collector_start" INSIDE the else
    # of "now_m < discover_due", which needs 445 <= now_m < 440. No clock value
    # satisfies that: discover_due is 07:25, the collector starts 07:20, and
    # register_tasks.ps1 makes the monitor's earliest weekday firing 07:25
    # anyway. CRITERIA and tasks/README both enumerate discover among the jobs
    # this watchdog reruns, and the branch that was supposed to do it could
    # never be entered, so the safety net they describe never existed. The
    # sharpest case was the morning that missed both: the same 07:25 pass
    # restarted the dead collector onto yesterday's names while declining to
    # refresh the watchlist those names came from.
    #
    # The clock was standing in for a question about a FILE, so the file is
    # what is asked now. A watchlist from a previous session is the condition
    # that actually matters, and the subscription list is the thing a rewrite
    # could desync, so it is the subscription list rather than the hour that
    # decides whether a rewrite is still free.
    discover_due = _minutes(_CRIT.clock("monitor", "discover_due"))
    collector_start = _minutes(_CRIT.clock("collector", "start_time"))
    discover_relaunched = False
    if now_m < discover_due:
        report("discover", "NOT DUE", "")
    else:
        verdict = log_verdict("discover", JOBS["discover"][3], day)
        if verdict in ("finished", "skipped_closed"):
            if steps_ok("discover"):
                report("discover", "OK", verdict)
        else:
            task = query_task(JOBS["discover"][0])
            fired = task.get("last_run") is not None and task["last_run"].date() == now.date()
            detail = ("fired but did not finish" if fired
                      else "never fired today, the machine was probably asleep")
            exited = _exit_marker("discover", day)
            if exited:
                detail = f"{detail}, and {exited}"
            # The settled flag is not consulted for discover, and the chain and
            # the nightly below explain why it is for them: every monitor pass
            # from discover_due onwards evaluates discover, monitor-night's
            # 22:45 firing included, so a provisional RUNNING here is always
            # read again while the log path is still today's.
            alive, _settled = _job_alive("discover", now, task)
            if alive:
                # Not counted as a problem and not rerun: a pass still going is
                # the ordinary state a minute after a late wake, and the rerun
                # that used to follow from here would have rewritten the
                # watchlist underneath the run that is writing it.
                report("discover", "RUNNING", f"{alive}; no finish marker yet, "
                       "which is what a pass in progress looks like")
            else:
                problems += 1
                stale, vintage = _watchlist_vintage(day)
                rewrite_free, why_free = _rewriting_the_watchlist_is_free(day, now_m)
                if rewrite_free:
                    discover_relaunched = maybe_rerun(
                        "discover", f"{detail}; {vintage}. {why_free}")
                elif stale:
                    report("discover", "FAILED", detail + f". {vintage}, and the "
                           "collector has already written its subscription list, "
                           "so a rewrite now would desync the watchlist from what "
                           "is actually being listened to and the morning would "
                           "screen names no tape was collected for. The stale "
                           "watchlist is the worse fact of the two and this pass "
                           "cannot fix it: a second collector is never started.")
                else:
                    report("discover", "FAILED", detail + f". {vintage}, so the "
                           "names the collector subscribed to are the right ones "
                           "and what is missing is the baseline warm. Not rerun: "
                           "rewriting a good watchlist to refill a cache scan "
                           "already reports as null with a reason costs more than "
                           "it buys.")

    # ---- collector
    collector_stop = _minutes(_CRIT.clock("collector", "stop_time"))
    # A hold is a promise that a later pass starts the collector, so it may
    # only be made when there is one INSIDE the window. Without this test the
    # hold added on 2026-08-20 stranded the collector for a whole morning: with
    # the machine waking at 08:25, the 08:55 pass held, the 09:25 pass reported
    # the window over because the branch that starts a collector tests
    # now_m < collector_stop and collector_stop is 09:25, and the collector
    # never started at all, with its rerun budget unspent.
    hold_is_answerable = next_pass is not None and next_pass < collector_stop
    # Whether the WATCHLIST can still be repaired before the window closes,
    # which is a different question from whether another pass exists. discover
    # gets max_reruns_per_job_per_day attempts and no more, so once that budget
    # is spent a later pass cannot rebuild the file however many of them are
    # left. Both have to hold, or the collector is being asked to wait for a
    # rescue that is not coming.
    #
    # This is what the stale-watchlist-ok override turns on. Gating it on
    # discover_relaunched instead, as it was first written on 2026-08-24, left
    # the ordinary restart path below unable to pass it: with discover's single
    # rerun already spent, maybe_rerun("discover") returns False,
    # discover_relaunched is False, the plain else restarts the collector with
    # no flag, the collector refuses the stale file and burns its own single
    # rerun, and the last-resort branch is never reached at all. That turns
    # "wrong names for the rest of the window" into "no tape", which is the one
    # outcome CRITERIA [Monitor] added the branch to prevent.
    from collect import collect_premarket as _collect
    from ops import quantifier_flags

    watchlist_stale, watchlist_vintage_said = _watchlist_vintage(day)
    #
    # Three conditions, not two. Budget and a later pass are not enough: the
    # discover block above REFUSES to rerun at all, budget untouched, once a
    # subscription list exists and the watchlist is stale, because a rewrite
    # then desyncs the file from what the socket was actually asked for. In
    # that state the first two conditions both read true, the override is
    # withheld, the collector refuses on restart and burns its own single
    # rerun, and the next pass reports GAVE UP. That is the no tape outcome
    # this flag exists to prevent, reached by the gate that is supposed to
    # prevent it.
    discover_repairable = (hold_is_answerable
                           and reruns_done.get("discover", 0) < max_reruns
                           and _rewriting_the_watchlist_is_free(day, now_m)[0])
    last_chance_args = ((_collect.STALE_WATCHLIST_ARG,)
                        if watchlist_stale and not discover_repairable else ())
    if now_m < collector_start:
        report("collector", "NOT DUE", "")
    elif now_m < collector_stop:
        if _collector_alive(now):
            report("collector", "RUNNING", "bar file moving or task running")
        elif discover_relaunched and hold_is_answerable:
            # Held rather than started, and only in the pass that just
            # relaunched discover. The collector reads the watchlist once, at
            # subscribe time, and nothing re-reads it afterwards, so a
            # collector started in these few seconds subscribes to whichever
            # version of the file won the race and is stuck with it for the
            # whole window. That is how the both-missed morning used to end up
            # listening to the previous session's names. The next pass is
            # thirty minutes away against a window that runs 07:20 to 09:25,
            # so waiting costs a quarter of the window where the wrong names
            # would cost all of it.
            problems += 1
            report("collector", "HELD", "no live collector, and discover was "
                   "relaunched in this pass, so the watchlist on disk is the "
                   "one it is replacing. Starting now would subscribe to "
                   "whichever version won the race and hold it all window. "
                   f"The {_clock_text(next_pass)} pass starts it on the file "
                   "discover wrote.")
        elif discover_relaunched:
            # Past the last pass that could act, so the choice is no longer
            # between right names now and right names in half an hour. It is
            # between possibly wrong names for the rest of the window and no
            # tape at all, and the tape is worth more: the packet records
            # watchlist_generated_at from whichever file the collector read, so
            # a session collected on the previous session's names is visible in
            # the morning rather than silent.
            problems += 1
            # stale-watchlist-ok is passed HERE and nowhere else. Since
            # 2026-08-24 the collector refuses a watchlist that is not today's,
            # which is right everywhere except this branch: here the race it
            # would refuse is the last chance the morning has, and a refusal
            # would strand the window exactly as the hold once did. The flag
            # says "this pass knows", and both the collector and scan still say
            # loudly which session's names were used.
            maybe_rerun("collector", "no live collector, and discover was "
                        "relaunched in this pass, but no later pass falls "
                        f"inside the window that ends {_clock_text(collector_stop)}, "
                        "so a hold would strand the collector for the rest of "
                        "the morning. Started on whichever watchlist version "
                        "wins the race, overruling the collector's own refusal "
                        "because there is no later pass to rerun discover; scan "
                        "records which one it was",
                        args=last_chance_args)
        else:
            problems += 1
            # The override reaches HERE too, and has to. This is the ordinary
            # restart, and it is also where a morning lands once discover's
            # rerun budget is spent: nothing above can fire again, so if the
            # watchlist is still another session's this pass is the last chance
            # the window gets, exactly as the branch above is on its own clock.
            extra = ""
            if last_chance_args:
                extra = (f". {watchlist_vintage_said}, and discover cannot be "
                         "rebuilt before the window closes, so the collector is "
                         "started on the file that is there rather than left to "
                         "refuse it; scan says which session's names were used")
            maybe_rerun("collector", "inside the window with no live collector; "
                        "restart is safe, it resumes the bar file" + extra,
                        args=last_chance_args)
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
            task = query_task(JOBS["chain"][0])
            fired = task.get("last_run") is not None and task["last_run"].date() == now.date()
            detail = "fired but did not finish" if fired else "never fired today"
            exited = _exit_marker("chain", day)
            if exited:
                # "fired but did not finish" is the same sentence for a chain
                # that died on a step, one still working and one the machine
                # lost power under. Where the log names the step, say so.
                detail = f"{detail}, and {exited}"
            alive, settled = _job_alive("chain", now, task)
            # chain_due is 09:00 and register_tasks.ps1 fires this task 07:25,
            # 07:55, 08:25, 08:55 and 09:25, so 08:55 reads NOT DUE and 09:25
            # is the ONLY pass inside [chain_due, rerun_chain_until]. A verdict
            # deferred at 09:25 is deferred to nobody.
            revisited = (next_pass is not None
                         and chain_due <= next_pass <= chain_until)
            if alive and (settled or revisited):
                # Neither a problem nor an action. The chain has no finish
                # marker for most of the time it is legitimately running, and
                # the analyst step alone can be silent for max_attempts times
                # timeout_s.
                report("chain", "RUNNING", f"{alive}; no finish marker yet, "
                       "which is what a chain in progress looks like. A second "
                       "one would race this one on packet.json and spend "
                       "another claude CLI completion."
                       + ("" if settled else
                          f" The {_clock_text(next_pass)} pass reads it again."))
            elif alive:
                # The last pass that could act, holding evidence that cannot
                # tell a working chain from one that died minutes ago. It used
                # to print RUNNING and exit 0, which is a clean bill of health
                # for a morning with no report in it. Not rerun, because the
                # cost of being wrong that way is two scans racing on
                # packet.json and a second claude CLI completion; counted and
                # named instead, so this pass exits non-zero and the 22:45 pass
                # and the morning report both carry it.
                problems += 1
                report("chain", "UNRESOLVED", f"{alive}, which is the same "
                       "reading for a chain still working as for one that died "
                       "just before this pass. No later pass falls inside "
                       f"{_clock_text(chain_due)} to {_clock_text(chain_until)} "
                       "ET, so nothing revisits this. Not rerun: a second chain "
                       "would race a live one. Read "
                       f"logs\\morning-chain-{day}.log and rerun by hand if it "
                       "died.")
            elif now_m <= chain_until:
                problems += 1
                maybe_rerun("chain", detail + "; the chain is idempotent")
            else:
                problems += 1
                report("chain", "FAILED", detail + f". Past "
                       f"{_CRIT.clock_text('monitor', 'rerun_chain_until')} ET, a premarket "
                       "report is history; run tasks\\job_morning_chain.bat by hand if "
                       "still wanted.")

    # ---- midday
    #
    # REPORT ONLY, and deliberately. Every other job here is rerun when it is
    # safe to rerun, and this one is not, for two reasons that point the same
    # way. The 12:00 sweep spends a measured 2,902 credits on a key shared with
    # another project, and job_midday.bat sets PMD_JOB, so a relaunch resolves
    # through artifacts as the owner of today and REPLACES the 12:00 packet
    # with a later measurement. That is worst in the case most likely to bring
    # the watchdog here: a scan that wrote its packet and a render that failed,
    # where a rerun spends the whole sweep again to redo a step that makes no
    # vendor call, and overwrites the good half on the way.
    #
    # The midday report is also not time critical the way the morning is.
    # CRITERIA [Midday] asks closed questions about a session already open, so a
    # named failure a human can act on beats an automatic second attempt.
    midday_due = _minutes(_CRIT.clock("monitor", "midday_due"))
    midday_last = _minutes(_CRIT.clock("monitor", "midday_last_pass"))
    if now_m < midday_due:
        report("midday", "NOT DUE", "")
    else:
        verdict = log_verdict("midday", JOBS["midday"][3], day)
        task = query_task(JOBS["midday"][0])
        alive, settled = _job_alive("midday", now, task)
        # Its OWN name. The shared next_pass read at the top of check_all is
        # still live here and the nightly branch below reads it, so binding
        # this to `next_pass` handed the nightly whatever midday computed.
        # Nothing differed today: now_m has not moved between the two calls
        # and _next_pass_minute is pure, so both return the same minute. That
        # is the whole reason to close it now, while it is still a trap for
        # the edit that gives midday a clock of its own rather than a bug.
        midday_next_pass = _next_pass_minute(now_m)
        revisited = (midday_next_pass is not None
                     and midday_next_pass <= midday_last)
        if verdict in ("finished", "skipped_closed"):
            if steps_ok("midday"):
                report("midday", "OK", verdict)
        elif alive and (settled or revisited):
            report("midday", "RUNNING", f"{alive}; no clean finish recorded yet, "
                   "which is what a midday in progress looks like rather than "
                   "one that failed")
        elif alive:
            problems += 1
            report("midday", "UNRESOLVED", f"{alive}, which is the same reading "
                   "for a midday still working as for one that died just before "
                   "this pass, and no later pass falls inside the midday window "
                   f"to read it again. Read logs\\midday-{day}.log.")
        else:
            problems += 1
            exited = _exit_marker("midday", day)
            reason = verdict if not exited else f"{verdict}, and {exited}"
            report("midday", "FAILED", reason + ". REPORT ONLY, not rerun: the "
                   "12:00 sweep spends about 2,902 credits on the shared key and "
                   "a relaunch would replace the packet it may already have "
                   "written. Run tasks\\job_midday.bat by hand if it is still "
                   "wanted")

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
        #
        # It is not free, though, and this test is why the nightly was the
        # easier of the two jobs to duplicate: a task that is STILL RUNNING
        # reports TASK_STILL_RUNNING rather than "0", so a nightly working its
        # way through the backfill at 22:45 failed this test with a finish
        # marker already on disk from the 07:00 catch-up run, and got a second
        # copy launched on top of it. The liveness gate below is what separates
        # "has not finished yet" from "did not finish".
        fired_ok = fired and task.get("last_result") == "0"
        alive, settled = _job_alive("nightly", now, task)
        # monitor-night is a SINGLE firing at nightly_due, so unlike the
        # morning there is no next pass to defer to. The morning's own passes
        # cannot serve as one either: 07:25 is before nightly_due and prints
        # NOT DUE, and by the next 22:45 the dated log path has rolled.
        revisited = next_pass is not None and next_pass >= nightly_due
        if verdict == "skipped_closed" or (verdict == "finished" and fired_ok):
            if steps_ok("nightly"):
                report("nightly", "OK", verdict)
        elif alive and (settled or revisited):
            report("nightly", "RUNNING", f"{alive}; no clean finish recorded "
                   "yet, which is what a nightly in progress looks like rather "
                   "than one that failed")
        elif alive:
            # The same correction the chain carries above, and sharper here: a
            # RUNNING printed at 22:45 was the last word on the nightly for the
            # session, because nothing runs after it and the log rolls. It is
            # rare for a SCHEDULED nightly, which Task Scheduler settles with
            # Running or 267009; the warm log is the only evidence for a hand
            # run or for a rerun this module launched with Popen, neither of
            # which Scheduler can see.
            problems += 1
            report("nightly", "UNRESOLVED", f"{alive}, which is the same "
                   "reading for a nightly still working as for one that died "
                   "just before this pass, and monitor-night fires once so "
                   "nothing revisits it. Not rerun: a second nightly on top of "
                   "a live one duplicates the backfill. The 07:00 catch-up run "
                   "fills the backfill and the outcomes again either way, so "
                   "what is at risk here is pool recall and the archive: read "
                   f"logs\\nightly-{day}.log.")
        else:
            problems += 1
            reason = ("fired but did not finish" if fired
                      else "the scheduled task never fired today")
            exited = _exit_marker("nightly", day)
            if exited:
                reason = f"{reason}, and {exited}"
            maybe_rerun("nightly", reason + "; fully idempotent")

    # ---- unjudged quantifier guard flags
    #
    # Named on every pass, whether or not there are any. A count that only
    # appears when it is bad is a count nobody learns to read, and this one is
    # here to be seen on the mornings somebody is already reading the watchdog
    # rather than on the morning they finally go looking for it.
    backlog = flag_backlog(now)
    backlog_after = _CRIT.integer("monitor", "flag_backlog_after_days")
    if backlog.get("error"):
        problems += 1
        report("flags", "UNREADABLE",
               f"the quantifier flag log could not be read ({backlog['error']}), "
               "so the guard's false positive rate is not being measured")
    elif not backlog["pending"]:
        report("flags", "OK",
               f"{backlog['raised']} quantifier flag(s) raised, 0 unjudged")
    elif backlog["oldest_days"] is None:
        problems += 1
        report("flags", "UNDATED",
               f"{backlog['pending']} unjudged quantifier flag(s) carry no "
               "readable timestamp, so their age cannot be checked: "
               f"{quantifier_flags.RUN_PREFIX} --pending")
    elif backlog["oldest_days"] >= backlog_after:
        problems += 1
        report("flags", "BACKLOG",
               f"{backlog['pending']} unjudged of {backlog['raised']} raised, "
               f"the oldest from {backlog['oldest_session']} and "
               f"{backlog['oldest_days']:.0f} days old. The false positive rate "
               "stays an impression until these are judged: "
               f"{quantifier_flags.RUN_PREFIX} --pending")
    else:
        report("flags", "PENDING",
               f"{backlog['pending']} unjudged of {backlog['raised']} raised, "
               f"the oldest {backlog['oldest_days']:.0f} day(s) old, inside the "
               f"{backlog_after} day judging window: "
               f"{quantifier_flags.RUN_PREFIX} --pending")

    # The script against the machine. See the note above reconcile_schedule
    # for why this is here and not in the suite.
    schedule = reconcile_schedule()
    if not schedule["checked"]:
        report("schedule", "NOT CHECKED", schedule["reason"] +
               ". No agreement is being claimed either way")
        problems += 1
    else:
        trouble = (schedule["missing"] + schedule["extra"]
                   + schedule["differs"] + schedule["unreadable"])
        if not trouble:
            report("schedule", "OK",
                   f"{schedule['live_count']} registered task(s) match the "
                   f"{schedule['spec_count']} in register_tasks.ps1 $jobs on "
                   "name, start and repetition")
        else:
            for name in schedule["missing"]:
                report("schedule", "MISSING",
                       f"{name} is in $jobs and NOT registered, so it never "
                       "fires. monitor-midday sat like this from 2026-08-31 "
                       "to 2026-09-01")
                problems += 1
            for name in schedule["extra"]:
                report("schedule", "UNKNOWN",
                       f"{name} is registered and NOT in $jobs, so a full "
                       "re-registration will not maintain it. A one off "
                       "probe armed on purpose looks like this and is still "
                       "worth naming")
                problems += 1
            for line in schedule["differs"]:
                report("schedule", "DIFFERS", line)
                problems += 1
            for line in schedule["unreadable"]:
                report("schedule", "NOT CHECKED", line)
                problems += 1

    print(f"monitor: {problems} problem(s), {actions} action(s) taken, "
          f"{len(JOBS)} job(s) checked")
    # Two different questions, and they had one answer between them. The exit
    # code is for the scheduler and for a human reading Task Scheduler's last
    # result column: non-zero means come and look. The status record is for the
    # job trail, and there it must mean "the watchdog ran", never "the watchdog
    # found nothing", because several of the conditions that set problems are
    # designed to persist for weeks. An unjudged quantifier flag past
    # flag_backlog_after_days is the clearest: CRITERIA says to tune the word
    # list on a month of them. With OK_CODES = (0,) one such flag made every
    # later pass record STATUS_FAILED, and two sessions after that the morning
    # report's job health line told the reader the watchdog had never recorded
    # a success and had stopped running. It was running perfectly and reporting
    # one unjudged flag, and with max_steps_named_in_report at four that noise
    # line crowds out the real overdue steps it exists to surface.
    job_status.produced("problems found", problems)
    return 0 if problems == 0 else 1


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
#
# 1 is here because this job's exit code answers a different question from its
# status record. check_all returns 1 when it FINDS something, which job_monitor
# .bat documents as "something needs a human eye", and that is a successful
# watchdog pass. A pass that genuinely fails raises, and job_status.run records
# the exception whatever this tuple says, so nothing is lost by admitting 1.
OK_CODES = (0, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the scheduled jobs, rerun what is safe.")
    parser.add_argument("--at", metavar="HH:MM", default=None,
                        help="Evaluate as if the clock read this ET time today, for testing.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Decide and report, launch nothing. It still writes its "
                             "own job status record, marked manual like any "
                             "hand run, because job_status.run wraps main and "
                             "cannot see this flag.")
    args = parser.parse_args(argv)

    now = ettime.now_et()
    if args.at:
        hour, minute = (int(part) for part in args.at.split(":"))
        now = now.replace(hour=hour, minute=minute)
        print(f"monitor: pretending the clock reads {args.at} ET")

    config.ensure_dirs()
    return check_all(now, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(job_status.run("monitor", main, ok_codes=OK_CODES))
