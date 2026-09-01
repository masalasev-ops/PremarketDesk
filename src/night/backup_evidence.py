"""Copy the artifacts that cannot be rebuilt, to somewhere outside the tree.

NOT A FEATURE. A COPY. It computes nothing, decides nothing, and no module in
the pipeline reads what it writes. If this file were deleted the morning would
run exactly as it does now, which is the whole design: a backup that anything
depends on is a second input, and a second input is a second thing to be wrong.

WHY THESE SIX, AND THE LEDGER BESIDE THEM. Everything in this system
regenerates, and THE TEST EACH HELD ARTIFACT HAS TO PASS IS THAT NOTHING CAN
PRODUCE IT AGAIN. Not that it would be slow to rebuild, not that it would cost
quota: that there is no route back at any price. Everything below passes that
test and nothing else in the tree does.

[corrected 2026-09-01, second: this said FOUR and the tuple now holds six, with
a running ledger held beside it. The count moved because the test above was
applied to two things it had never been asked about. The reports were assumed
rebuildable from the packet and are not: the analyst is a MODEL, so the same
packet does not yield the same report twice, and two of this project's test
modules read archived reports as their evidence. Six sessions of them were
deleted on 2026-09-01 and are gone for good, which is the loss this correction
follows. And the flag log holds HUMAN JUDGEMENTS, which cannot be re-derived
from anything at all, making it more irreplaceable than a packet rather than
less. Seven of them existed only on this machine until now.]

[corrected 2026-09-01: this said TWO and named two, while _ARTIFACTS has
copied four since the collector's two sidecars joined it. The comment above
that tuple is why it matters: a list that grows without that argument being
remade is a backup of everything, which is a different and much weaker
promise. The list grew and the argument was not remade, so the two that
joined are argued for below beside the other two. The count travelled: both
architecture pages and a docstring in morning/scan.py said two on this
file's authority.]

  data/premarket/<date>.jsonl   the collector's own socket capture. A recording
                                of a tape that no longer exists. CRITERIA's
                                closes retention note already says it is not
                                reproducible at any price.
  runs/<date>/packet.json       the frozen evidence a morning was judged on.
                                The report renders from it, every _true column
                                is measured against the window it records, and
                                a re-read of a past session reads it rather
                                than picks.
  data/premarket/<date>-stats.jsonl
                                one line per collector run: connections,
                                reconnects, the drops it survived. A record of
                                how the capture went, and there is no second
                                copy of a connection that has closed.
  data/premarket/<date>-subscriptions.json
                                what the collector asked the socket for, at
                                subscribe time. CRITERIA's stale watchlist note
                                calls this the ONLY evidence of what was
                                listened to, because the watchlist beside it
                                can be rewritten after the socket has read it.
                                2026-08-24 is the case: by 12:00 the watchlist
                                on disk was today's and the socket had spent
                                the morning on eight context tickers.

The universe rebuilds. The closes re-fetch. Reports render from packets. The
database has store.guard_live_database. Those all have a route back; these
four have none, and every one of them lives under a gitignored directory.

WHAT PROMPTED IT. On 2026-08-21 at 15:46 a sweep that invoked every claim
directly wrote fixture data over 29 files, including that morning's capture
(258 AAPL bars at $105.00 over roughly 3,200 real ones) and its packet. Both
are gone permanently. No mistake of that shape should be able to end a session
again, and the isolation that now prevents it is one layer; this is the other.

WRITE ONCE, AND A TRIPWIRE. A dated backup is never overwritten. If the working
copy no longer matches a backup already taken, that is reported as a
DISAGREEMENT rather than resolved in either direction, because the backup being
stale and the working copy being corrupted look identical from here and only a
person can tell them apart. Had this existed on 2026-08-21, the 22:15 run would
have said so the same night.

    PYTHONPATH=src .venv/Scripts/python.exe -m night.backup_evidence
    PYTHONPATH=src .venv/Scripts/python.exe -m night.backup_evidence --list
    PYTHONPATH=src .venv/Scripts/python.exe -m night.backup_evidence --restore 2026-08-20

WHERE THE HELD SET ALREADY HAS HOLES, recorded once here rather than reported
every night for the rest of the project's life.

On 2026-09-01 the run directories for 2026-08-13, 08-14, 08-17, 08-18, 08-19
and 08-20 were deleted by hand, on the argument that an archive of reports now
known to be wrong is its own kind of dishonesty. The packets and captures for
those sessions were already held and survived. The RENDERED REPORTS were not
held, because report.md and report-html only joined _ARTIFACTS later the same
day, and no backup carries them. Those six sessions' reports are gone for good,
as are the 08-15 and 08-16 weekend sweeps recorded in the entry of 2026-08-21.

That is why HELD_SINCE exists below. A session older than the date an artifact
joined the held set was never a candidate for backup, so a source missing from
it is HISTORY. Reporting it as a finding on every run forever is the cry-wolf
shape _LEDGERS is written to avoid and the completion gate already avoids by
saying "already held, nothing at risk" rather than withholding loudly. A
session NEWER than that date with no held copy is a real finding and still
prints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import ettime
from ops import job_status

_CRIT = criteria.load()

# One entry per artifact. (where it lives, how to name it for a date).
# Adding a seventh is a deliberate edit: the argument above is that these six
# things have no route back, and a list that grows without that argument being
# remade is a backup of everything, which is a different and much weaker
# promise. The argument was remade on 2026-09-01 when the reports joined, which
# is what the last correction says the sidecars should have prompted and did
# not.
#
# WHAT EACH ONE HAS NO ROUTE BACK FROM, in one line each, because a list whose
# members cannot each answer that question is a list that has stopped meaning
# anything:
#   premarket        a recording of a tape that no longer exists
#   premarket-stats  a record of connections that have closed
#   subscriptions    what the socket was asked for, at a moment now past
#   packet           the frozen evidence a morning was judged on
#   report           a MODEL wrote it, so the same packet yields a different
#                    report every time, and test_containment and the quantifier
#                    claims read archived reports as their evidence
#   report-html      rendered from a report.md that cannot be reproduced, so it
#                    inherits the same one way door
#
# [corrected 2026-09-01: this said a THIRD and exactly TWO. The docstring's
# own correction marker was written the same night and this comment, which is
# the sentence that correction cites as the reason the count matters, was left
# saying the old number. A correction that does not reach the line it quotes
# is half a correction.]
_ARTIFACTS = (
    ("premarket", lambda day: config.PREMARKET_DIR / f"{day}.jsonl"),
    ("premarket-stats", lambda day: config.PREMARKET_DIR / f"{day}-stats.jsonl"),
    ("subscriptions", lambda day: config.PREMARKET_DIR / f"{day}-subscriptions.json"),
    ("packet", lambda day: config.run_path(day) / "packet.json"),
    ("report", lambda day: config.run_path(day) / "report.md"),
    ("report-html", lambda day: config.run_path(day) / "report.html"),
)


# WHEN EACH ARTIFACT JOINED THE HELD SET, so a hole can be told from a loss.
# A source missing from a session OLDER than its label's date was never going
# to be held and is history; the module docstring records the deletion that
# made the two report holes. A source missing from a session NEWER than it,
# with nothing held, is a finding and prints.
#
# Dates read off the git history rather than remembered: the original four
# went in together on 2026-08-21, and the two reports on 2026-09-01.
HELD_SINCE = {
    "premarket": "2026-08-21",
    "premarket-stats": "2026-08-21",
    "subscriptions": "2026-08-21",
    "packet": "2026-08-21",
    "report": "2026-09-01",
    "report-html": "2026-09-01",
}


# A RUNNING PROJECT FILE rather than a session artifact, held on the SAME
# promise as the six above and handled differently for one mechanical reason.
#
# data/quantifier-flags.jsonl carries dispositions, and a disposition is a
# person reading a packet and deciding. Nothing can produce one again: not a
# re-run, not the vendor, not the model. That makes it MORE irreplaceable than
# a packet, not less, and it sat in a gitignored directory in exactly one copy
# until 2026-09-01.
#
# It is snapshotted UNDER THE DATE THE NIGHT RAN and is deliberately NOT digest
# compared the way _ARTIFACTS is. Those six are frozen the moment they are
# written, so a disagreement there means corruption and deserves the tripwire.
# This one legitimately GROWS every time a flag is raised or judged, so
# comparing today's log against a snapshot taken nine sessions ago would report
# a disagreement every single night and teach the reader to ignore the one
# alarm in this module that matters.
#
# Write once per date still holds, so each night keeps its own state and a
# judgement recorded after the night ran is caught by the next night. The
# exposure is at most one day of judgements, against no copy at all before.
_LEDGERS = (
    ("quantifier-flags", lambda: config.DATA_DIR / "quantifier-flags.jsonl"),
)


def back_up_ledgers(day: str, dry_run: bool = False) -> dict[str, Any]:
    """Snapshot the running ledgers under one date. Write once, never compared.

    See the comment above _LEDGERS for why these are not digest compared. The
    day is the night's own date rather than a session being caught up: the file
    holds one current state, and that state belongs to the moment it was taken.
    """
    out: dict[str, Any] = {"copied": [], "held": [], "missing": [], "failed": []}
    for label, locate in _LEDGERS:
        source = locate()
        if not source.is_file():
            out["missing"].append(f"{label}: {source.name} is not on disk")
            continue
        target = backup_root() / day / f"{label}{source.suffix}"
        if target.is_file():
            out["held"].append(label)
            continue
        if dry_run:
            out["copied"].append(label)
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        except OSError as exc:
            out["failed"].append(f"{label}: {type(exc).__name__}: {exc}")
            continue
        out["copied"].append(label)
    return out


def study_root() -> Path:
    """Where study payloads are kept. A SIBLING of the dated sessions, not one.

    They are not sessions and they are not evidence in the sense _ARTIFACTS
    means. Filing them under a date would put them in the same shape as the
    four things that have no route back and quietly widen that promise.
    """
    return backup_root() / "studies"


def back_up_studies(dry_run: bool = False) -> dict[str, Any]:
    """Copy data/research payloads to the backup root, once each.

    A DIFFERENT AND WEAKER PROMISE THAN _ARTIFACTS, and the difference is the
    point. Those four cannot be produced again at any price. These can: an
    instrument exists for every one of them. They are kept because running it
    again costs quota, or reads a universe and a set of packets that have since
    moved, so a payload is cheaper to hold than to re-earn. That is prudence,
    not irreplaceability, and calling it the same thing would make the sentence
    above _ARTIFACTS mean nothing.

    Write once, on the same argument as the dated copies: a payload that
    disagrees with its backup is reported, never resolved, because a stale
    backup and an overwritten working copy look identical from here.
    """
    source_dir = config.STUDY_DIR
    copied: list[str] = []
    held: list[str] = []
    disagree: list[str] = []
    if not source_dir.is_dir():
        return {"copied": copied, "held": held, "disagree": disagree,
                "dry_run": dry_run, "root": study_root()}
    for source in sorted(source_dir.glob("*.json")):
        target = study_root() / source.name
        if target.is_file():
            if _digest(target) == _digest(source):
                held.append(source.name)
            else:
                disagree.append(source.name)
            continue
        copied.append(source.name)
        if dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return {"copied": copied, "held": held, "disagree": disagree,
            "dry_run": dry_run, "root": study_root()}


def backup_root() -> Path:
    """Outside the working tree, and outside the repository's parent.

    Read from CRITERIA so an operator can move it without editing code, and
    expanded through the environment so the default lands in the user's own
    application data rather than beside the tree it is protecting. A backup
    inside the directory that gets deleted is not a backup.
    """
    return Path(os.path.expandvars(_CRIT.text("backup", "root"))).expanduser()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target(day: str, label: str, source: Path) -> Path:
    return backup_root() / day / f"{label}{source.suffix}"


# The job that owns a session's collector run. A hand run or an instrument
# records step "collector" too, under job "manual", and today's socket cost
# probe is exactly that: it wrote 932 minutes at 10:00 against the morning's
# 3,289 at 07:20. An instrument finishing is not a session finishing.
SESSION_COLLECTOR_JOB = "collector"


def collector_finished(day: str, rows: list[dict[str, Any]] | None = None
                       ) -> tuple[bool, str]:
    """Did the scheduled collector record a COMPLETED run for this date.

    ASKED OF job_status AND NOT OF THE FILE, which is the whole point. A
    capture file exists from the socket's first written minute, so its presence
    says a run started and nothing at all about whether it ended. On 2026-08-24
    the 07:55 catch up read a file holding five bars and backed it up, and
    write once made that stub the permanent copy of a 2,089 bar session.

    A missing answer is NOT a yes. No row, a row that failed, and a row still
    open all return False with the reason, because a backup taken on a guess is
    the failure this whole module exists to prevent.

    A row still open is read IN ORDER against the completed runs beside it, and
    is not on its own an answer about the session. A watchdog restart leaves
    the killed run open forever and finishes the session in a second row; only
    an open run that started AFTER the last completed one can still be
    appending to the capture, and only that one refuses.
    """
    if rows is None:
        rows = job_status.records()
    seen_any = False
    completed: dict[str, Any] | None = None
    opened: list[str] = []
    for row in rows:
        if row.get("step") != "collector":
            continue
        started = str(row.get("started_at") or "")
        if not started.startswith(day):
            continue
        if row.get("job") != SESSION_COLLECTOR_JOB:
            seen_any = True
            continue
        seen_any = True
        # NOT a return, which is what it used to be. A morning the watchdog
        # restarted leaves the dead run's row open forever WITH a completed
        # run recorded after it, and answering on the first row seen refused
        # that session on every nightly until it fell out of the ten session
        # catch up window, after which the one artifact class this module
        # calls irreplaceable had never been copied at all. 2026-08-18 and
        # 2026-08-19 are both restarted mornings and survive only because
        # their failed first runs recorded an end. A process killed by the
        # power cut this module keeps citing records none.
        if not row.get("ended_at"):
            opened.append(started)
            continue
        if row.get("status") == "ok" and row.get("exit_code") == 0:
            if completed is None or started > str(completed.get("started_at") or ""):
                completed = row
    if completed is not None:
        # ORDER DECIDES IT, and this is the one thing an open row can still
        # mean. A run that started AFTER the completed one may be appending to
        # the capture at this moment, and write once would freeze it at
        # whatever length it has reached, which is the 2026-08-24 defect. A
        # run that started before it is a corpse and says nothing about a
        # session that went on to finish.
        latest = str(completed.get("started_at") or "")
        newer = sorted(s for s in opened if s > latest)
        if newer:
            return False, (f"the {day} collector completed a run, and another "
                           f"started after it at {newer[-1][11:19]} and never "
                           "ended, so the capture may still be growing")
        produced = completed.get("produced_count")
        return True, (f"the {day} collector finished at "
                      f"{str(completed['ended_at'])[11:19]}"
                      + (f" with {produced:,} minutes written"
                         if isinstance(produced, int) else ""))
    if opened:
        return False, (f"the {day} collector has a row that never ended, so "
                       "the session is still running or the process died "
                       "without recording an end")
    if seen_any:
        return False, (f"the {day} collector left rows but none is a completed "
                       f"{SESSION_COLLECTOR_JOB} run, so what is on disk is a "
                       "partial or an instrument's")
    return False, (f"no {SESSION_COLLECTOR_JOB} run is recorded for {day} at "
                   "all. Either the session has not run yet, or it ran before "
                   "job_status tracked it")


def survey(days: list[str]) -> dict[str, Any]:
    """What would be copied, what is already held, and what disagrees."""
    copied: list[dict[str, Any]] = []
    held: list[str] = []
    missing: list[str] = []
    gone_but_held: list[str] = []
    gone_before_held: list[str] = []
    disagree: list[dict[str, Any]] = []
    for day in days:
        for label, locate in _ARTIFACTS:
            source = locate(day)
            target = _target(day, label, source)
            if not source.is_file():
                # THREE ANSWERS, not one. The working copy is gone; what that
                # MEANS depends on whether anything holds it and on whether
                # this session was ever a candidate for holding it.
                if target.is_file():
                    gone_but_held.append(f"{day}/{label}")
                elif day < HELD_SINCE.get(label, "0000-00-00"):
                    gone_before_held.append(f"{day}/{label}")
                else:
                    missing.append(f"{day}/{label}")
                continue
            row = {"day": day, "label": label, "source": source,
                   "target": target, "bytes": source.stat().st_size}
            if not target.is_file():
                copied.append(row)
                continue
            if _digest(target) == _digest(source):
                held.append(f"{day}/{label}")
                continue
            # NOT resolved here, in either direction. A stale backup and a
            # corrupted working copy are the same observation from this side.
            disagree.append({**row, "backup_bytes": target.stat().st_size})
    return {"copy": copied, "held": held, "missing": missing,
            "gone_but_held": gone_but_held,
            "gone_before_held": gone_before_held,
            "disagree": disagree}


def run(days: list[str], dry_run: bool = False) -> dict[str, Any]:
    found = survey(days)
    written = 0
    bytes_written = 0
    failed: list[str] = []
    for row in found["copy"]:
        if dry_run:
            written += 1
            bytes_written += row["bytes"]
            continue
        try:
            row["target"].parent.mkdir(parents=True, exist_ok=True)
            # copy2 preserves mtime, so a restored file still says when the
            # collector wrote it rather than when the copy happened.
            shutil.copy2(row["source"], row["target"])
        except OSError as exc:
            failed.append(f"{row['day']}/{row['label']}: {type(exc).__name__}")
            continue
        written += 1
        bytes_written += row["bytes"]
    return {**found, "written": written, "bytes": bytes_written,
            "failed": failed, "dry_run": dry_run, "root": backup_root()}


def restore(day: str, force: bool = False) -> dict[str, Any]:
    """Put a backed up session back into the working tree.

    Refuses to overwrite a working copy that already matches the backup, and
    refuses one that DIFFERS unless forced, because overwriting the newer of
    two disagreeing files is exactly the mistake this module exists to undo.
    """
    done: list[str] = []
    skipped: list[str] = []
    for label, locate in _ARTIFACTS:
        source = locate(day)
        target = _target(day, label, source)
        if not target.is_file():
            skipped.append(f"{label}: no backup held")
            continue
        if source.is_file() and not force:
            if _digest(source) == _digest(target):
                skipped.append(f"{label}: working copy already matches")
            else:
                skipped.append(
                    f"{label}: working copy DIFFERS from the backup and would "
                    "be overwritten. Pass --force only once you know which of "
                    "the two is the real one")
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, source)
        done.append(label)
    return {"day": day, "restored": done, "skipped": skipped}


def held_sessions() -> list[str]:
    root = backup_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def report(result: dict[str, Any]) -> None:
    verb = "would copy" if result["dry_run"] else "copied"
    print(f"backup: {verb} {result['written']} file(s), "
          f"{result['bytes'] / 1048576:.2f} MB, to {result['root']}")
    for row in result["copy"]:
        print(f"  {row['day']}/{row['label']:<16} {row['bytes']:>10,} bytes")
    if result["held"]:
        print(f"backup: {len(result['held'])} file(s) already held and "
              "unchanged, left alone. A dated backup is never overwritten")
    if result["missing"]:
        # ONLY THE FINDING. A source gone from a session that already holds it,
        # and a source gone from a session older than the artifact itself, are
        # both carried in the result for anything that wants to read them and
        # neither is printed. See HELD_SINCE and the docstring's note on where
        # the held set already has holes: a line that fires every night about
        # two sessions that will never come back is a line nobody reads by the
        # end of the week, and the DISAGREES line underneath it is the one
        # thing in this module that must never be skimmed past.
        print(f"backup: {len(result['missing'])} artifact(s) not on disk to "
              f"copy: {', '.join(result['missing'][:8])}"
              + (" ..." if len(result["missing"]) > 8 else ""))
    for row in result["disagree"]:
        print(f"  DISAGREES  {row['day']}/{row['label']}: working copy "
              f"{row['bytes']:,} bytes, backup {row['backup_bytes']:,} bytes. "
              "The backup is NOT being updated. Either the working copy was "
              "overwritten or the backup is stale, and only a person can say "
              "which. Compare them before doing anything else.")
    for row in result["failed"]:
        print(f"  COULD NOT COPY {row}")


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value.
# One line per arbitration, appended and never rewritten, and it lives in the
# BACKUP ROOT rather than under data/ so it travels with the evidence it
# describes. A verdict kept beside the working tree would be lost by the same
# event that makes a working tree doubtful.
ARBITRATION_LOG = "arbitrations.jsonl"

# The minimum number of sources an arbitration must cite. Two, because one
# source is an assertion with a citation attached: the whole method here is
# that records written by DIFFERENT code at DIFFERENT times have to agree
# before either of the two files in question is touched.
MIN_SOURCES = 2


def arbitration_log_path() -> Path:
    return backup_root() / ARBITRATION_LOG


def record_arbitration(entry: dict[str, Any]) -> Path:
    """Append the verdict. Written BEFORE anything is replaced.

    Order matters. If the replacement fails halfway, a recorded verdict with no
    replacement is a readable state and someone can finish it. A replacement
    with no record is the thing this whole module exists to prevent.
    """
    path = arbitration_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return path


def arbitrate(day: str, label: str, verdict: str, sources: list[str],
              why: str, dry_run: bool = False) -> dict[str, Any]:
    """Close ONE disagreement with evidence from outside both files.

    REFUSES unless everything below holds, and each refusal is a different
    mistake:

      the artifact is named by _ARTIFACTS          or there is nothing to judge
      both copies exist                            or this is a copy, not a
                                                   disagreement, and the
                                                   ordinary path handles it
      they actually differ                         or there is no dispute and
                                                   replacing would be a write
                                                   for its own sake
      the verdict is working or backup             the only two readings
      at least MIN_SOURCES sources                 the method, not a formality
      a reason is given                            the entry has to say what
                                                   happened, not which file won

    Exactly one artifact moves, in the direction the verdict names, and the
    entry records both digests so a later reader can tell what was replaced
    without trusting this function's own account of it.
    """
    located = dict(_ARTIFACTS).get(label)
    if located is None:
        return {"ok": False, "why": f"{label!r} is not an artifact this module "
                f"backs up. Known: {', '.join(name for name, _ in _ARTIFACTS)}"}
    source = located(day)
    target = _target(day, label, source)
    if not source.is_file():
        return {"ok": False, "why": f"no working copy at {source}, so there is "
                "no disagreement here, only an absence"}
    if not target.is_file():
        return {"ok": False, "why": f"no backup at {target}, so this is a copy "
                "the ordinary path already makes and not a dispute"}
    working_digest, backup_digest = _digest(source), _digest(target)
    if working_digest == backup_digest:
        return {"ok": False, "why": "the two copies agree, so there is nothing "
                "to arbitrate and replacing one would be a write for its own sake"}
    if verdict not in ("working", "backup"):
        return {"ok": False, "why": f"verdict {verdict!r} is neither 'working' "
                "nor 'backup', and those are the only two readings"}
    if len(sources) < MIN_SOURCES:
        return {"ok": False, "why": f"{len(sources)} source(s) cited and "
                f"{MIN_SOURCES} are required. Neither of the two files counts: "
                "cite records written by different code at different times, "
                "such as the collector stats sidecar, the job status rows, or "
                "the packet's own collector_snapshot"}
    if not (why or "").strip():
        return {"ok": False, "why": "no reason given. The entry has to say what "
                "happened, not which file was picked"}

    entry = {
        "at": ettime.stamp(ettime.now_et()),
        "day": day,
        "label": label,
        "verdict": verdict,
        "sources": sources,
        "why": why.strip(),
        "working_sha256": working_digest,
        "backup_sha256": backup_digest,
        "working_bytes": source.stat().st_size,
        "backup_bytes": target.stat().st_size,
        "dry_run": bool(dry_run),
    }
    if dry_run:
        return {"ok": True, "entry": entry, "replaced": None, "dry_run": True,
                "log": arbitration_log_path()}

    log = record_arbitration(entry)
    if verdict == "working":
        shutil.copy2(source, target)
        replaced = f"backup {target}"
    else:
        shutil.copy2(target, source)
        replaced = f"working copy {source}"
    return {"ok": True, "entry": entry, "replaced": replaced, "dry_run": False,
            "log": log}


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy the premarket capture and packet somewhere safe.")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true",
                        help="Print the sessions the backup root holds.")
    parser.add_argument("--restore", default=None, metavar="YYYY-MM-DD",
                        help="Copy a session back into the working tree.")
    parser.add_argument("--force", action="store_true",
                        help="With --restore, overwrite a differing working copy.")
    parser.add_argument("--arbitrate", default=None, metavar="DAY/LABEL",
                        help="Close one DISAGREES by evidence, e.g. "
                             "2026-08-24/premarket. Needs --verdict, at "
                             "least two --source and a --why.")
    parser.add_argument("--verdict", default=None,
                        choices=("working", "backup"),
                        help="Which copy the outside evidence supports.")
    parser.add_argument("--source", action="append", default=[],
                        metavar="TEXT",
                        help="A record that is NEITHER of the two files. "
                             "Repeatable and at least two are required.")
    parser.add_argument("--why", default=None,
                        help="What happened. Not which file was picked.")
    args = parser.parse_args(argv)

    if args.list:
        sessions = held_sessions()
        print(f"backup: {backup_root()} holds {len(sessions)} session(s)")
        for day in sessions:
            print(f"  {day}")
        return 0

    if args.arbitrate:
        if "/" not in args.arbitrate:
            print("backup: --arbitrate takes DAY/LABEL, e.g. 2026-08-24/premarket")
            return 2
        day, _, label = args.arbitrate.partition("/")
        outcome = arbitrate(day, label, args.verdict or "", list(args.source),
                            args.why or "", dry_run=args.dry_run)
        if not outcome["ok"]:
            print(f"backup: REFUSED to arbitrate {args.arbitrate}: {outcome['why']}")
            print("  Write once is not relaxed. Nothing was changed.")
            return 2
        entry = outcome["entry"]
        verb = "would record" if outcome["dry_run"] else "recorded"
        print(f"backup: {verb} an arbitration for {day}/{label}, verdict "
              f"{entry['verdict']}, on {len(entry['sources'])} source(s)")
        for line in entry["sources"]:
            print(f"    source: {line}")
        print(f"    why: {entry['why']}")
        print(f"    working {entry['working_bytes']:,} bytes "
              f"sha {entry['working_sha256'][:12]}")
        print(f"    backup  {entry['backup_bytes']:,} bytes "
              f"sha {entry['backup_sha256'][:12]}")
        if outcome["dry_run"]:
            print("  --dry-run: nothing recorded and nothing replaced.")
            return 0
        print(f"  replaced {outcome['replaced']}")
        print(f"  verdict appended to {outcome['log']}")
        return 0

    if args.restore:
        outcome = restore(args.restore, force=args.force)
        print(f"backup: restored {len(outcome['restored'])} artifact(s) for "
              f"{outcome['day']}: {', '.join(outcome['restored']) or 'none'}")
        for line in outcome["skipped"]:
            print(f"  skipped {line}")
        return 0

    # Today, plus any recent session the root does not hold yet, so a night
    # the machine was off is caught up rather than lost.
    catchup = _CRIT.integer("backup", "catchup_sessions")
    days = [args.date] if args.date else sorted(
        {p.stem for p in config.PREMARKET_DIR.glob("*.jsonl")
         if len(p.stem) == 10},
        reverse=True)[:catchup]

    # A SESSION THAT IS STILL BEING WRITTEN IS NOT BACKED UP. See
    # collector_finished. --date is the explicit override and says so,
    # because after an arbitration somebody has to be able to re-take a
    # copy on purpose, and that is a different act from the nightly
    # sweeping up whatever it finds.
    if args.date:
        print(f"backup: --date {args.date} given, so the completed session "
              "check is SKIPPED for it. This is the override.")
        ready = days
    else:
        rows = job_status.records()
        ready = []
        for day in days:
            finished, why = collector_finished(day, rows)
            if finished:
                ready.append(day)
                continue
            held = all(_target(day, label, locate(day)).is_file()
                       for label, locate in _ARTIFACTS)
            print(f"backup: SKIPPED {day}, {why}."
                  + (" Every artifact for it is already held, so nothing "
                     "is at risk." if held else
                     " Nothing was copied: a partial copy held is worse "
                     "than none, because write once makes it permanent. "
                     f"Force it with --date {day} once the session is "
                     "over."))
    result = run(sorted(ready), dry_run=args.dry_run)
    report(result)

    # The running ledgers, under tonight's date. Same promise as the six, and
    # reported apart only because they are not session artifacts.
    ledgers = back_up_ledgers(ettime.today_str(), dry_run=args.dry_run)
    verb = "would copy" if args.dry_run else "copied"
    print(f"backup: ledgers {verb} {len(ledgers['copied'])}, already held "
          f"{len(ledgers['held'])}")
    for line in ledgers["missing"] + ledgers["failed"]:
        print(f"  LEDGER NOT HELD  {line}")

    # After the six, and reported apart from them, because they are held
    # on a different promise. See back_up_studies.
    studies = back_up_studies(dry_run=args.dry_run)
    verb = "would copy" if studies["dry_run"] else "copied"
    print(f"backup: studies {verb} {len(studies['copied'])}, "
          f"already held {len(studies['held'])}, at {studies['root']}")
    for name in studies["disagree"]:
        print(f"  DISAGREES  studies/{name}: the working copy differs from "
              "the backup and NEITHER was changed. A study payload is "
              "rewritten by re-running its instrument, so this is either a "
              "re-run nobody recorded or a corrupted file")
    job_status.produced("evidence files copied", result["written"])
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("backup", main, ok_codes=OK_CODES))
