"""Test sandbox: no test may write to the live runs/, data/ or database.

Four incidents of one thing, in three weeks. test_scrub called build_packet
against the live repo and overwrote the frozen premarket_snapshot.jsonl of the
first real morning, destroying the only record of what that scan saw.
test_store wrote to the live database and failed with "database is locked"
whenever a real job held a transaction. gap_stats held that transaction across
two thousand HTTP calls. Each was fixed where it was found, and the next one
appeared somewhere else, which is what tells you the fix was in the wrong
place.

So the sandbox is not per test. activate() redirects every writable root that
production code reads, sourced from config so a test cannot bypass it by
constructing a path itself, and every module that captured one of those paths
at import time is rebound with it. run_tests.py wraps the whole suite in it.

That still leaves a test free to hardcode an absolute path, which no redirect
can prevent. So the second half of this is a check rather than a redirect:
snapshot() records every file under the real runs/ and data/ before the suite
and again after, and any difference fails it. A test that reaches around the
sandbox is caught by the evidence rather than by the design.

This is deliberately not a pytest conftest. pytest is not a dependency of this
project and requirements.txt is three lines on purpose. The name is kept
because the role is exactly a conftest's, and because if pytest is ever added
its import of this file will do the right thing.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator

import config

# Every config attribute that names something writable, and the modules that
# copied one at import time. A new module holding a path constant has to be
# added here; the mtime check below is what catches it if nobody remembers.
_CONFIG_PATHS = (
    "DATA_DIR", "PREMARKET_DIR", "RUNS_DIR", "LOGS_DIR", "SITE_DIR",
    "DB_PATH", "UNIVERSE_PATH", "WATCHLIST_PATH", "CA_BUNDLE_PATH",
)

_DERIVED = (
    ("backtest_pool", "CACHE_DIR", lambda c: c.DATA_DIR / "backtest"),
    ("backtest_pool", "EOD_DIR", lambda c: c.DATA_DIR / "backtest" / "eod"),
    ("backtest_pool", "SESSION_DIR", lambda c: c.DATA_DIR / "backtest" / "sessions"),
    ("job_status", "RECORD_PATH", lambda c: c.DATA_DIR / "job-status.jsonl"),
    ("market_today", "CACHE_PATH", lambda c: c.DATA_DIR / "exchange-details.json"),
    ("monitor_jobs", "STATE_PATH", lambda c: c.DATA_DIR / "monitor-reruns.json"),
    ("verify_morning", "UNVERIFIED_MARKER", lambda c: c.DATA_DIR / "UNVERIFIED"),
)

# Real roots, captured before anything is redirected. site/ joined this list
# after the entrypoint tests caught build_archive rewriting the published
# archive from inside the sandbox: the redirect stops it, and the check is
# what proves the redirect held.
REAL_RUNS = config.RUNS_DIR
REAL_DATA = config.DATA_DIR
REAL_SITE = config.SITE_DIR


def snapshot(*roots: Path) -> dict[str, tuple[float, int]]:
    """Every file under roots, with its mtime and size."""
    out: dict[str, tuple[float, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                out[str(path)] = (stat.st_mtime, stat.st_size)
    return out


def differences(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What changed between two snapshots, as readable lines."""
    out: list[str] = []
    for path in sorted(set(after) - set(before)):
        out.append(f"created  {path}")
    for path in sorted(set(before) - set(after)):
        out.append(f"deleted  {path}")
    for path in sorted(set(before) & set(after)):
        if before[path] != after[path]:
            out.append(f"modified {path}  {before[path]} -> {after[path]}")
    return out


@contextlib.contextmanager
def activate(copy_data: bool = True) -> Iterator[Path]:
    """Point every writable root at a temporary copy for the duration.

    data/ is copied rather than left empty because the suite reads real inputs
    from it: universe.json, the collector bar file, the backtest cache. Reads
    stay honest, writes land in the copy.
    """
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-suite-"))
    saved_config = {name: getattr(config, name) for name in _CONFIG_PATHS}
    saved_modules: list[tuple[Any, str, Any]] = []

    try:
        data_copy = sandbox / "data"
        if copy_data and REAL_DATA.exists():
            shutil.copytree(REAL_DATA, data_copy)
        else:
            data_copy.mkdir(parents=True, exist_ok=True)
        runs_copy = sandbox / "runs"
        if REAL_RUNS.exists():
            shutil.copytree(REAL_RUNS, runs_copy)
        else:
            runs_copy.mkdir(parents=True, exist_ok=True)
        (sandbox / "logs").mkdir(parents=True, exist_ok=True)

        config.DATA_DIR = data_copy
        config.PREMARKET_DIR = data_copy / "premarket"
        config.RUNS_DIR = runs_copy
        config.LOGS_DIR = sandbox / "logs"
        config.SITE_DIR = sandbox / "site"
        config.DB_PATH = data_copy / "premarketdesk.db"
        config.UNIVERSE_PATH = data_copy / "universe.json"
        config.WATCHLIST_PATH = data_copy / "watchlist.json"
        config.CA_BUNDLE_PATH = data_copy / "ca-bundle.pem"

        import importlib

        for module_name, attribute, build in _DERIVED:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
            saved_modules.append((module, attribute, getattr(module, attribute, None)))
            setattr(module, attribute, build(config))

        yield sandbox
    finally:
        for name, value in saved_config.items():
            setattr(config, name, value)
        for module, attribute, value in saved_modules:
            if value is not None:
                setattr(module, attribute, value)
        shutil.rmtree(sandbox, ignore_errors=True)
