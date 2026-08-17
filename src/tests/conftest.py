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

from core import config

# Every config attribute that names something writable, and the modules that
# copied one at import time. A new module holding a path constant has to be
# added here; the mtime check below is what catches it if nobody remembers.
_CONFIG_PATHS = (
    "DATA_DIR", "PREMARKET_DIR", "RUNS_DIR", "LOGS_DIR", "SITE_DIR",
    "DB_PATH", "UNIVERSE_PATH", "WATCHLIST_PATH", "CA_BUNDLE_PATH",
)

_DERIVED = (
    ("research.backtest_pool", "CACHE_DIR", lambda c: c.DATA_DIR / "backtest"),
    ("research.backtest_pool", "EOD_DIR", lambda c: c.DATA_DIR / "backtest" / "eod"),
    ("research.backtest_pool", "SESSION_DIR", lambda c: c.DATA_DIR / "backtest" / "sessions"),
    ("ops.job_status", "RECORD_PATH", lambda c: c.DATA_DIR / "job-status.jsonl"),
    ("ops.market_today", "CACHE_PATH", lambda c: c.DATA_DIR / "exchange-details.json"),
    ("ops.monitor_jobs", "STATE_PATH", lambda c: c.DATA_DIR / "monitor-reruns.json"),
    ("morning.verify_morning", "UNVERIFIED_MARKER", lambda c: c.DATA_DIR / "UNVERIFIED"),
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

        with block_network():
            yield sandbox
    finally:
        for name, value in saved_config.items():
            setattr(config, name, value)
        for module, attribute, value in saved_modules:
            if value is not None:
                setattr(module, attribute, value)
        shutil.rmtree(sandbox, ignore_errors=True)


# ------------------------------------------------------- the network boundary

class NetworkBlocked(RuntimeError):
    """Raised when a test reaches for the network without stubbing it."""


# Set by run_tests --live. Nothing else may write it. Live claims check
# live_allowed() and skip themselves when it is false, so the default suite is
# hermetic and a live claim has to be asked for.
ALLOW_LIVE = False


def live_allowed() -> bool:
    return ALLOW_LIVE


# What the stub meter reports: a healthy shared key, well above both the
# degrade threshold and the refuse floor in CRITERIA.md [quota]. Fixed, so a
# claim's outcome never moves with someone else's spending.
HEALTHY_METER = {
    "apiRequests": 1_000,
    "dailyRateLimit": 100_000,
    "name": "stub",
    "email": "stub@example.invalid",
}


class _BlockedSession:
    """Every HTTP verb raises, naming what tried and how to stub it.

    Installed as the session every EodhdClient builds, so a test that never
    stubs the network fails loudly and immediately instead of reaching the
    vendor. A test that DOES stub, by assigning client._session, replaces this
    and is unaffected: three suites already do exactly that.
    """

    def _refuse(self, verb: str, url: str, **_kwargs: Any) -> Any:
        raise NetworkBlocked(
            f"a test tried to {verb} {url}. The suite runs with the network "
            "blocked, because a claim whose outcome depends on a shared "
            "external counter is not a test. Stub it by assigning "
            "client._session, or rebind eodhd.read_meter for a meter reading. "
            "If the claim genuinely needs the network, name it claim_live_... "
            "or ..._live and gate it on conftest.live_allowed()."
        )

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._refuse("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._refuse("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        return self._refuse(method.upper(), url, **kwargs)


def meter(**overrides: Any) -> Any:
    """A meter reading for a claim that needs a specific one.

        with conftest.meter_reading(apiRequests=99_900):
            ...

    Returns an ApiResult the way eodhd.read_meter does, so preflight's own
    verdict logic runs on it rather than being stubbed away.
    """
    from core import eodhd

    payload = dict(HEALTHY_METER)
    payload.update(overrides)
    return eodhd.ApiResult(payload, None)


@contextlib.contextmanager
def meter_reading(**overrides: Any) -> Iterator[None]:
    """Feed preflight a specific meter for the duration, then restore."""
    from core import eodhd

    saved = eodhd.read_meter
    eodhd.read_meter = lambda: meter(**overrides)
    try:
        yield
    finally:
        eodhd.read_meter = saved


@contextlib.contextmanager
def block_network() -> Iterator[None]:
    """No HTTP leaves the suite, and the quota meter reads healthy and fixed.

    This is the fix for the 2026-08-16 failure, placed at the boundary rather
    than in the claim that happened to trip over it. test_pool claim 11 called
    discover.build(), which preflights the live shared key; a sibling project
    pushed that key below the refuse floor and the claim started failing with
    nothing in this repository changed. Any claim reaching the network has the
    same defect whether or not it has shown it yet, so the network is removed
    for all of them at once.

    Skipped entirely under --live, where the point is to reach the vendor.
    """
    if ALLOW_LIVE:
        yield
        return

    from core import eodhd

    saved_build = eodhd.build_session
    saved_meter = eodhd.read_meter
    saved_client = eodhd._default_client

    eodhd.build_session = lambda: _BlockedSession()
    eodhd.read_meter = lambda: meter()
    # Any client built before the block holds a real session, so the cached
    # one is dropped and rebuilt behind the block on next use.
    eodhd._default_client = None

    saved_probe = None
    try:
        import probe_alpaca

        saved_probe = probe_alpaca.build_session
        probe_alpaca.build_session = lambda: _BlockedSession()
    except ImportError:
        pass

    try:
        yield
    finally:
        eodhd.build_session = saved_build
        eodhd.read_meter = saved_meter
        eodhd._default_client = saved_client
        if saved_probe is not None:
            import probe_alpaca

            probe_alpaca.build_session = saved_probe


# ------------------------------------------------- the watchlist table skeleton

def watchlist_headers() -> dict[str, str]:
    """The two watchlist header rows, read from REPORT_TEMPLATE.md at test time.

    Three fixtures drifted on 2026-08-17 because they carried hand written
    header literals while the containment guard matches on what the template
    pins. They passed a guard that counted ticker columns and failed the moment
    it started requiring those two tables BY NAME, which is the right failure
    arriving late: the fixtures had been decoupled from what production emits
    for as long as they had existed, and nothing said so.

    Reading the template at test time is what closes that. A header change in
    the template now breaks every fixture built on it, loudly, in the same run
    that changed it.
    """
    from core import config

    text = config.REPORT_TEMPLATE_PATH.read_text(encoding="utf-8")
    wanted = {"## Day watchlist": "day watchlist",
              "## Swing watchlist": "swing watchlist"}
    found: dict[str, str] = {}
    section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = wanted.get(stripped)
            continue
        # The first Ticker row after the heading is the header the template
        # pins. It repeats later inside the empty table example, which is the
        # same string, so first wins and the two cannot disagree.
        if section and section not in found and stripped.startswith("| Ticker"):
            found[section] = stripped
    missing = sorted(set(wanted.values()) - set(found))
    if missing:
        raise AssertionError(
            f"REPORT_TEMPLATE.md carries no header row for {missing}. Either the "
            "section was renamed or its table lost its Ticker column, and every "
            "fixture that builds a watchlist table depends on finding it."
        )
    return found


def watchlist_table(kind: str, rows: list[str] | None = None) -> str:
    """A whole watchlist section, header and separator and body, from the template.

    kind is "day watchlist" or "swing watchlist". rows are body lines already
    formatted as markdown; the default is the template's own empty table row,
    because REPORT_TEMPLATE.md requires the table to be written even when the
    screen produced nothing.
    """
    header = watchlist_headers()[kind]
    columns = len([cell for cell in header.strip().strip("|").split("|")])
    separator = "| " + " | ".join(["---"] * columns) + " |"
    body = rows if rows else ["| none |" + " |" * (columns - 1)]
    heading = "## " + kind[:1].upper() + kind[1:]
    return "\n".join([f"{heading}", "", header, separator, *body, ""])
