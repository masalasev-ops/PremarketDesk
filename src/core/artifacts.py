"""Refuse to destroy an artifact that a past run wrote.

A run directory under runs/ is evidence. packet.json, the collector snapshot
beside it and the report built from them are what a reader saw on a given
morning, and two of the project's test suites assert against them by reading
those exact files. They are not scratch space and nothing should quietly
replace one.

The scheduled jobs own today's artifacts and rewrite them freely, which is
correct: a watchdog rerun of the morning chain is supposed to produce a fresh
packet. The hazard is the operator path. A human reproducing a bug points a
tool at a past session, the tool writes where it always writes, and a frozen
artifact is gone with nothing said. That is exactly how the 08:45 snapshot for
2026-08-14 was destroyed on 2026-08-15, and it was only noticed because a test
happened to read it.

So the hand invokable writers that have been through this route their
destination through resolve() here: snapshot_bars, the nightly's
verify_intraday.json and pool_recall's own file, which is the set
test_entrypoints.claim_operator_tools_spare_artifacts pins. The default spares
the original and writes beside it; --overwrite is the explicit way to say
otherwise, and even then the thing being replaced is described before it goes.

Three writers are NOT through it yet, and the gap is named rather than implied.
analyst.write_report writes report.md and analyst_usage.json, and
render_report.render writes report.html, each with a plain write_text into
whatever run directory its --packet or --report argument points at, so a hand
run against a past session still replaces that morning's narrative.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

# Written between the stem and the suffix, so a spared write lands on
# premarket_snapshot.handrun.jsonl rather than premarket_snapshot.jsonl.handrun
# and still opens in whatever reads the original format.
SPARED_INFIX = "handrun"


def scheduled_run() -> bool:
    """True when a .bat set PMD_JOB, so the scheduler is running this.

    This is the line between an owner and a visitor. The nightly owns the
    artifacts it writes and must be able to rewrite them, including for PAST
    dates: the 07:00 catch-up pass legitimately fills yesterday, so a rule of
    "a past date is always spared" would break the schedule rather than protect
    it. A human running the same module by hand sets no PMD_JOB and is spared
    by default.

    Reuses the variable the status record already keys on, where a hand run
    records `manual`, so there is one definition of "was this the scheduler"
    rather than two that can drift.
    """
    from ops import job_status

    return bool(os.environ.get(job_status.JOB_ENV_VAR))


def line_count(path: Path) -> int | None:
    """Lines in a text artifact, or None when it is not one we can count.

    Used to describe what is about to be lost. A bar count is the single most
    useful fact about a collector snapshot, and "1,419 bars" tells an operator
    far more about what they are about to destroy than a byte size does.
    """
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return None


def describe(path: Path) -> str:
    """One line about an existing artifact: size, line count and when it was written."""
    try:
        stat = path.stat()
    except OSError:
        return f"{path} (cannot be read)"
    written = dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"{stat.st_size:,} bytes", f"written {written}"]
    if path.suffix in (".jsonl", ".log", ".md", ".txt"):
        count = line_count(path)
        if count is not None:
            label = "bars" if path.suffix == ".jsonl" else "lines"
            parts.insert(0, f"{count:,} {label}")
    return f"{path} ({', '.join(parts)})"


def spared_path(path: Path) -> Path:
    """A sibling that does not exist yet, so nothing is lost to write here."""
    candidate = path.with_name(f"{path.stem}.{SPARED_INFIX}{path.suffix}")
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.{SPARED_INFIX}-{index}{path.suffix}")
        index += 1
    return candidate


def resolve(
    path: Path,
    overwrite: bool,
    *,
    what: str = "artifact",
    announce: Any = print,
) -> tuple[Path, bool]:
    """Where to write, and whether the original was spared.

    Returns (destination, spared). Three cases, and each one says what it did:

      nothing there        write at path, silently, because there is nothing to
                           report and the ordinary first write of a morning
                           must not become chatty
      overwrite requested  write at path, after describing what is being
                           replaced, because an operator who asked for this
                           should still see what it cost
      otherwise            write beside path and say plainly that the original
                           was refused, naming it and its size
    """
    path = Path(path)
    if not path.exists():
        return path, False

    if overwrite:
        announce(f"{what}: REPLACING {describe(path)}")
        return path, False

    destination = spared_path(path)
    announce(f"{what}: REFUSED to overwrite {describe(path)}")
    announce(f"{what}: wrote {destination} instead. Pass --overwrite to replace "
             f"the original.")
    return destination, True
