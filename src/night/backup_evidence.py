"""Copy the artifacts that cannot be rebuilt, to somewhere outside the tree.

NOT A FEATURE. A COPY. It computes nothing, decides nothing, and no module in
the pipeline reads what it writes. If this file were deleted the morning would
run exactly as it does now, which is the whole design: a backup that anything
depends on is a second input, and a second input is a second thing to be wrong.

WHY THESE FOUR AND NOTHING ELSE. Everything in this system regenerates except:

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
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from ops import job_status

_CRIT = criteria.load()

# One entry per artifact. (where it lives, how to name it for a date).
# Adding a third is a deliberate edit: the argument above is that exactly two
# things in this system have no route back, and a list that grows without that
# argument being remade is a backup of everything, which is a different and
# much weaker promise.
_ARTIFACTS = (
    ("premarket", lambda day: config.PREMARKET_DIR / f"{day}.jsonl"),
    ("premarket-stats", lambda day: config.PREMARKET_DIR / f"{day}-stats.jsonl"),
    ("subscriptions", lambda day: config.PREMARKET_DIR / f"{day}-subscriptions.json"),
    ("packet", lambda day: config.run_path(day) / "packet.json"),
)


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


def survey(days: list[str]) -> dict[str, Any]:
    """What would be copied, what is already held, and what disagrees."""
    copied: list[dict[str, Any]] = []
    held: list[str] = []
    missing: list[str] = []
    disagree: list[dict[str, Any]] = []
    for day in days:
        for label, locate in _ARTIFACTS:
            source = locate(day)
            if not source.is_file():
                missing.append(f"{day}/{label}")
                continue
            target = _target(day, label, source)
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
    args = parser.parse_args(argv)

    if args.list:
        sessions = held_sessions()
        print(f"backup: {backup_root()} holds {len(sessions)} session(s)")
        for day in sessions:
            print(f"  {day}")
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
    result = run(sorted(days), dry_run=args.dry_run)
    report(result)
    job_status.produced("evidence files copied", result["written"])
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("backup", main, ok_codes=OK_CODES))
