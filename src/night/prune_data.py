"""Delete the dated files under data/ that nothing can read any more.

Written 2026-08-21, because until then this project had NO retention anywhere.
A grep of the whole tree for prune, retention or unlink found one call, in
probe_alpaca_live, cleaning up after itself. data/ therefore grew by about
900 KB every trading day with nothing watching it, and the only reason that
had not become a problem is that the project is nine days old.

WHAT THIS MAY DELETE IS A WHITELIST, NOT A RULE ABOUT AGE. Exactly one file
class is listed below, and a file that does not match it is left alone no
matter how old it is or how large it grows. That is the same containment
argument scan._PACKET_VOLUME_CHECK_KEYS makes: a sweeper that deletes whatever
looks stale is one careless pattern away from deleting the only copy of
something, and this directory holds several only copies.

  data/premarket/*.jsonl   the collector's own socket capture. NOT
                           reproducible at any price: it is a recording of a
                           tape that no longer exists. It is also the only
                           record of the 2026-08-14 over count, which is still
                           unexplained. Never a candidate.
  data/backtest/eod/       the 61 session population the shipped float
                           rotation edges were fitted on. A re-fit reads it.
  data/backtest/sessions/  the replay behind the subscription cap recall
                           table, which is an open purchasing decision.
  logs/, site/             not under data/ and not this module's business.
                           desk/render rebuilds site/ FROM runs/.

runs/ IS THIS MODULE'S BUSINESS SINCE 2026-09-04, and it is a second verb.
[corrected 2026-09-04: this list said "runs/, logs/, site/ not under data/ and
not this module's business", which was true while nothing touched runs/ at
all.] sweep_runs below COMPRESSES a run directory older than CRITERIA
[Retention] hot_sessions and deletes exactly one thing, the duplicate
premarket_snapshot.jsonl, under three interlocks. It never removes report.md
or report.html at any age, only gzips them in place, so the desk still finds
every session it ever found: files.read_text_maybe_gz is what makes that true
and desk/compact reads through it. [build_archive owned site/ until it was
retired on 2026-09-04; desk/render took its filename and this obligation.]

THE AGE COMES FROM THE FILENAME, NOT THE MTIME. universe-closes-2026-08-18.json
describes the session of the 18th whoever copied it and whenever. An mtime rule
would spare a file that was touched by a backup and delete one that was not,
which makes the retention window a property of the filesystem rather than of
the data.

    python -m night.prune_data --dry-run    say what would go, delete nothing
    python -m night.prune_data --runs-only  the run directories and nothing else
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import files
from core import ettime
from ops import job_status

_CRIT = criteria.load()


# One entry per file class that may EVER be deleted. Adding a second is a
# deliberate edit that has to bring its own retention key and its own argument
# for why nothing can read the file after that window.
#
# universe-closes-<date>.json is written by discover at 07:15 and read by
# scan.load_universe_closes at 08:45 for the SAME session_date, which
# scan.main takes from the clock rather than an argument. There is no other
# reader in the tree and no way to ask for a past one: --rescore reads the
# saved packet and never reaches this file. So it is dead to the code the
# moment its own chain window closes, and every day kept past that is margin
# for a human reading it by hand.
PRUNABLE = (
    ("universe-closes-*.json", "universe", "closes_retention_days"),
)


def _session_date(name: str) -> dt.date | None:
    """The date in the filename, or None if the name does not carry one.

    A file that matches the glob but carries no readable date is KEPT and
    reported, not deleted on a guess. universe-closes-.json would match
    universe-closes-*.json.
    """
    stem = Path(name).stem
    tail = stem.rsplit("-", 3)[-3:]
    if len(tail) != 3:
        return None
    try:
        return ettime.parse_date("-".join(tail))
    except (ValueError, TypeError):
        return None


def survey(today: dt.date | None = None) -> dict[str, Any]:
    """What would go, what stays, and why, without deleting anything."""
    today = today or ettime.today_et()
    doomed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for pattern, section, key in PRUNABLE:
        window = _CRIT.integer(section, key)
        for path in sorted(config.DATA_DIR.glob(pattern)):
            day = _session_date(path.name)
            if day is None:
                kept.append({"name": path.name, "why": "no readable date in "
                                                       "the filename"})
                continue
            age = (today - day).days
            row = {"name": path.name, "day": day.isoformat(), "age_days": age,
                   "bytes": path.stat().st_size, "window": window,
                   "path": path}
            # Strictly greater, so a window of 7 keeps seven days of files and
            # the current session's file is never in reach even at a window of
            # zero: its age is 0 and 0 is not greater than 0.
            if age > window:
                doomed.append(row)
            else:
                kept.append({**row, "why": f"{age} of {window} days old"})
    return {"today": today.isoformat(), "delete": doomed, "keep": kept}


def prune(dry_run: bool = False, today: dt.date | None = None) -> dict[str, Any]:
    found = survey(today)
    freed = 0
    removed: list[str] = []
    failed: list[str] = []
    for row in found["delete"]:
        if dry_run:
            freed += row["bytes"]
            removed.append(row["name"])
            continue
        try:
            row["path"].unlink()
        except OSError as exc:
            # A file that will not delete is not a failure of the night. It is
            # reported and the step still succeeds, because nothing downstream
            # needs the space and a locked file tonight is a deleted file
            # tomorrow.
            failed.append(f"{row['name']}: {type(exc).__name__}")
            continue
        freed += row["bytes"]
        removed.append(row["name"])
    return {**found, "removed": removed, "failed": failed, "freed": freed,
            "dry_run": dry_run}


# Files under runs/<date>/ compressed once a session leaves the hot window.
# Every one is read back through files.read_text_maybe_gz, so nothing
# downstream learns that this happened. The list is explicit for the same
# reason PRUNABLE is: a sweeper that compressed whatever it found would one
# day find something that has to stay a plain file.
COMPRESSIBLE = (
    "packet.json", "report.md", "report.html",
    "midday_packet.json", "report_midday.md", "report_midday.html",
    "pool_recall.json", "analyst_usage.json", "verify_intraday.json",
)


def _run_sessions() -> list[str]:
    """Session directories under runs/, newest first."""
    if not config.RUNS_DIR.is_dir():
        return []
    return sorted((e.name for e in config.RUNS_DIR.iterdir() if e.is_dir()),
                  reverse=True)


def _run_day(session: str) -> dt.date | None:
    try:
        return ettime.parse_date(session)
    except (ValueError, TypeError):
        return None


def _snapshot_verdict(session: str) -> tuple[bool, str]:
    """Whether the duplicate snapshot may go for this session, and why not.

    THREE INTERLOCKS AND ALL THREE HAVE TO HOLD. The snapshot is a strict
    subset of the collector's file, measured over every session that carried
    both on 2026-09-04, but "measured last week over eleven sessions" is not
    the same claim as "true of this session tonight", so each is checked here
    rather than assumed.

      the collector's file for that session exists and is readable
      verify_intraday.json exists, so the volume check has run
      desk.json.gz exists, so the bars are frozen as the morning saw them

    The third is the one that matters and it is why desk.compact runs before
    this in the nightly. The collector file is the whole day and the snapshot
    is a point in time cut of it, so a session whose bars were never frozen
    cannot have its tape path redrawn exactly: measured on 2026-09-03, five of
    twelve names gained one minute, always the 08:44 bar, which was still open
    when the snapshot was written. Freezing first puts that out of reach.
    """
    run_dir = config.run_dir(session)
    if files.resolve_maybe_gz(config.PREMARKET_DIR / f"{session}.jsonl") is None:
        return False, "the collector file for that session is not on disk"
    if _CRIT.flag("retention", "snapshot_drop_needs_verify"):
        if files.resolve_maybe_gz(run_dir / "verify_intraday.json") is None:
            return False, "the volume check has not run for that session"
    if files.resolve_maybe_gz(run_dir / "desk.json") is None:
        return False, "the bars are not frozen, desk.json.gz is absent"
    return True, ""


def _proves_subset(session: str) -> tuple[bool, str]:
    """Read both files and check the snapshot really is contained.

    THE CHECK IS PERFORMED, NOT CITED. The 2026-09-04 measurement is what made
    this worth building. It is not what makes tonight's delete safe. Deleting
    on a remembered property is how the only copy of something goes.
    """
    snapshot = config.run_dir(session) / "premarket_snapshot.jsonl"
    collector = config.PREMARKET_DIR / f"{session}.jsonl"
    try:
        theirs = set(files.read_text_maybe_gz(collector).splitlines())
        mine = set(files.read_text_maybe_gz(snapshot).splitlines())
    except (OSError, ValueError) as exc:
        return False, f"could not read both files: {type(exc).__name__}"
    extra = mine - theirs
    if extra:
        return False, (f"{len(extra)} of {len(mine)} line(s) are in the run copy "
                       "and NOT in the collector file, so it is not a duplicate")
    return True, ""


def sweep_runs(dry_run: bool = False, today: dt.date | None = None) -> dict[str, Any]:
    """Compress cold run artifacts and drop proven duplicate snapshots."""
    today = today or ettime.today_et()
    hot = _CRIT.integer("retention", "hot_sessions")
    cold_days = _CRIT.integer("retention", "cold_after_days")
    may_drop = _CRIT.flag("retention", "drop_duplicate_snapshot")

    sessions = _run_sessions()
    compressed: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    saved = 0

    for index, session in enumerate(sessions):
        run_dir = config.run_dir(session)
        day = _run_day(session)
        age = (today - day).days if day else None

        snapshot = run_dir / "premarket_snapshot.jsonl"
        if may_drop and snapshot.is_file():
            allowed, why = _snapshot_verdict(session)
            if allowed:
                allowed, why = _proves_subset(session)
            if not allowed:
                refused.append({"session": session, "why": why})
            else:
                size = snapshot.stat().st_size
                if not dry_run:
                    try:
                        snapshot.unlink()
                    except OSError as exc:
                        refused.append({"session": session,
                                        "why": f"{type(exc).__name__} on delete"})
                        size = 0
                if size:
                    dropped.append({"session": session, "bytes": size})
                    saved += size

        # HOT IS A COUNT OF SESSIONS, NOT A NUMBER OF DAYS, so a fortnight of
        # holidays cannot age a session out of the working set.
        if index < hot:
            continue
        for name in COMPRESSIBLE:
            plain = run_dir / name
            if not plain.is_file():
                continue
            if dry_run:
                compressed.append({"session": session, "name": name, "saved": None})
                continue
            try:
                gained = files.gzip_in_place(plain, attempts=3, retry_s=0.4)
            except OSError as exc:
                refused.append({"session": session,
                                "why": f"{name}: {type(exc).__name__} on compress"})
                continue
            compressed.append({"session": session, "name": name, "saved": gained})
            saved += gained

        if age is not None and age > cold_days:
            tape = config.PREMARKET_DIR / f"{session}.jsonl"
            if tape.is_file():
                if dry_run:
                    compressed.append({"session": session, "name": tape.name,
                                       "saved": None})
                else:
                    try:
                        gained = files.gzip_in_place(tape, attempts=3, retry_s=0.4)
                    except OSError as exc:
                        refused.append({"session": session,
                                        "why": f"{tape.name}: {type(exc).__name__}"})
                    else:
                        compressed.append({"session": session, "name": tape.name,
                                           "saved": gained})
                        saved += gained

    return {"sessions": len(sessions), "hot": hot, "cold_after_days": cold_days,
            "compressed": compressed, "dropped": dropped, "refused": refused,
            "saved": saved, "dry_run": dry_run}


def report_runs(result: dict[str, Any]) -> None:
    mode = "would free" if result["dry_run"] else "freed"
    print(f"prune: runs/, {result['sessions']} session(s), newest "
          f"{result['hot']} held hot, {mode} {result['saved'] / 1048576:.2f} MB")
    for row in result["dropped"]:
        print(f"  dropped duplicate snapshot {row['session']} "
              f"{row['bytes'] / 1024:>8,.0f} KB")
    by_session: dict[str, int] = {}
    for row in result["compressed"]:
        by_session[row["session"]] = by_session.get(row["session"], 0) + 1
    for session, count in sorted(by_session.items(), reverse=True):
        print(f"  compressed {session}, {count} file(s)")
    # EVERY REFUSAL IS PRINTED. A snapshot this declined to drop is the one
    # case where saying nothing would read as having done the work.
    for row in result["refused"]:
        print(f"  KEPT {row['session']}: {row['why']}")
    if not result["dropped"] and not result["compressed"]:
        print("  nothing was old enough or eligible")


def report(result: dict[str, Any]) -> None:
    mode = "would delete" if result["dry_run"] else "deleted"
    print(f"prune: {mode} {len(result['removed'])} file(s), "
          f"{result['freed'] / 1048576:.2f} MB, as of {result['today']}")
    for row in result["delete"]:
        print(f"  {row['name']:<34} {row['age_days']:>3}d old, "
              f"window {row['window']}d, {row['bytes'] / 1024:>8,.0f} KB")
    # What was left alone is printed too. A prune that only reports what it
    # took reads the same on a night it did its job and a night its glob
    # stopped matching anything.
    print(f"prune: kept {len(result['keep'])} file(s) inside the window")
    for row in result["keep"]:
        print(f"  {row['name']:<34} {row['why']}")
    for row in result["failed"]:
        print(f"  COULD NOT DELETE {row}")
    print("prune: data/premarket, data/backtest, runs and logs are not in "
          "the whitelist and were not looked at")


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delete dated data files past their retention window.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Say what would go and delete nothing.")
    parser.add_argument("--runs-only", action="store_true",
                        help="Sweep runs/ and leave data/ alone.")
    args = parser.parse_args(argv)
    if args.runs_only:
        report_runs(sweep_runs(dry_run=args.dry_run))
        return 0
    result = prune(dry_run=args.dry_run)
    report(result)
    report_runs(sweep_runs(dry_run=args.dry_run))
    # ONE call. job_status.produced records the last call before exit and
    # nothing else, so the second of two calls here silently replaced the
    # first and the record carried bytes and never the file count, which is
    # the number that answers "did this step do anything". Both facts in
    # one: the count is the files and the label carries the bytes.
    job_status.produced(f"files pruned, {result['freed']} bytes freed",
                        len(result["removed"]))
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("prune", main, ok_codes=OK_CODES))
