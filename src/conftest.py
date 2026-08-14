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
snapshot_tree() photographs the working tree before the suite and again after,
and any difference outside a short allowlist fails it. A test that reaches
around the sandbox is caught by the evidence rather than by the design.

The check used to name the roots it watched, and grew one root per escape:
runs/, then data/, then the database, then site/ when build_archive was found
rewriting the published archive from inside the sandbox. Four fixes, each one
correct about the root it had just been taught and blind to the next. That is
the signature of a check written as a list of what to guard rather than as a
statement of what may change, so it is now the second: everything under the
repository is guarded, and the allowlist names the handful of paths a test run
is permitted to touch. Adding a root is no longer possible to forget, because
there are no roots to add.

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

# Real roots, captured before anything is redirected. Kept because the escape
# prover writes to one of them deliberately; the check itself no longer reads
# this list, it photographs the whole tree.
REAL_RUNS = config.RUNS_DIR
REAL_DATA = config.DATA_DIR
REAL_SITE = config.SITE_DIR

# The working tree, which is what the check guards.
TREE_ROOT = config.PROJECT_ROOT

# The only paths a test run may touch. Directory names, matched against any
# component of a path, so src/__pycache__/scan.cpython-313.pyc is allowed and
# so is anything pytest would drop if it were ever added. Everything else in
# the tree is forbidden, including paths nobody has thought of yet, which is
# the point of writing it this way round.
ALLOWED_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})


def _allowed(path: Path) -> bool:
    try:
        relative = path.relative_to(TREE_ROOT)
    except ValueError:
        return False
    return any(part in ALLOWED_DIR_NAMES for part in relative.parts)


def snapshot_tree(root: Path | None = None) -> dict[str, tuple[Any, ...]]:
    """Every file and directory under the working tree, excluding the allowlist.

    Files carry mtime and size. Directories carry only a marker, not their
    mtime, because a directory's mtime moves whenever anything inside it is
    created, and an allowed __pycache__ write would otherwise fail the run
    through its parent. Directories are still tracked for existence, so a test
    that creates runs/2026-08-15/ is caught even before it writes a file into
    it.
    """
    base = root or TREE_ROOT
    out: dict[str, tuple[Any, ...]] = {}
    if not base.exists():
        return out
    stack = [base]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.name in ALLOWED_DIR_NAMES:
                continue
            try:
                if path.is_dir():
                    out[str(path)] = ("dir",)
                    stack.append(path)
                    continue
                stat = path.stat()
            except OSError:
                continue
            out[str(path)] = ("file", stat.st_mtime, stat.st_size)
    return out


# Kept under the old name so the call reads the same at both ends of the suite.
snapshot = snapshot_tree


def differences(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What changed between two snapshots, as readable lines.

    A modification says whether the size moved as well as the mtime, because
    a test that wrote a file almost always changes its size while something
    that merely touched it does not. Both still fail the run, on purpose: a
    same size overwrite is a real escape mode and the check must not start
    guessing which is which.

    [corrected 2026-08-14: this note previously offered "a virus scanner or an
    indexer" as the likely cause of an mtime-only change, and the session that
    wrote it attributed an observed intermittent failure to exactly that. The
    real cause was config.build_identifier() running `git status`, which
    refreshes and rewrites .git/index, so the suite failed on a file the check
    itself had caused to change. It now runs `git --no-optional-locks status`
    and the failure is gone across repeated runs. Reaching for an external
    explanation before exhausting the internal ones is what let it survive a
    day.]
    """
    out: list[str] = []
    for path in sorted(set(after) - set(before)):
        out.append(f"created  {path}")
    for path in sorted(set(before) - set(after)):
        out.append(f"deleted  {path}")
    for path in sorted(set(before) & set(after)):
        was, now = before[path], after[path]
        if was == now:
            continue
        if was[:1] == ("file",) and now[:1] == ("file",) and was[2] == now[2]:
            out.append(f"modified {path}  mtime only, size unchanged at {now[2]} "
                       "bytes (an external toucher looks like this; so does a "
                       "same size overwrite)")
        else:
            out.append(f"modified {path}  {was} -> {now}")
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
