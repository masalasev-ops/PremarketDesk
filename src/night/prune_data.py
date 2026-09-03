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
  runs/, logs/, site/      not under data/ and not this module's business.
                           build_archive rebuilds site/ FROM runs/, so pruning
                           runs/ would silently shorten the archive.

THE AGE COMES FROM THE FILENAME, NOT THE MTIME. universe-closes-2026-08-18.json
describes the session of the 18th whoever copied it and whenever. An mtime rule
would spare a file that was touched by a backup and delete one that was not,
which makes the retention window a property of the filesystem rather than of
the data.

    python -m night.prune_data --dry-run    say what would go, delete nothing
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
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
    args = parser.parse_args(argv)
    result = prune(dry_run=args.dry_run)
    report(result)
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
