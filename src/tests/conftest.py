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
import hashlib
import json
import re
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
# Captured before redirection like the others, and used by the sampler
# exemption below, which has to know where the REAL logs directory is while
# config.LOGS_DIR is pointing at a sandbox copy.
REAL_LOGS = config.LOGS_DIR

# The working tree, which is what the check guards.
TREE_ROOT = config.PROJECT_ROOT

# The only paths a test run may touch. Directory names, matched against any
# component of a path, so src/__pycache__/scan.cpython-313.pyc is allowed and
# so is anything pytest would drop if it were ever added. Everything else in
# the tree is forbidden, including paths nobody has thought of yet, which is
# the point of writing it this way round.
ALLOWED_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})


# --------------------------------------------- the one behaviour exemption
#
# logs/ is inside the tree this check photographs, and the scheduled meter
# sampler appends to it from outside the suite every half hour on the hour and
# the half hour. A suite run straddling one of those instants therefore failed
# on a path the suite never touched, which is an intermittent isolation failure
# that cannot be chased and gets rationalised away.
#
# The fix is NOT to exempt logs/. Tests writing there would pollute the meter
# trail and the quantifier flag log, and the flag log is the telemetry the
# guard's word list is about to be tuned on, so blinding the check to logs/
# would blind it to the one contamination that would corrupt the measurement.
#
# What is exempt is the sampler's BEHAVIOUR, and only when all three of these
# hold together:
#
#   1. the path is one of the two files the sampler writes, by name;
#   2. the change is a pure append, with every byte that was there before
#      still there and unchanged; and
#   3. the appended bytes parse as what that file holds.
#
# A truncation fails. A same length rewrite fails. A new file that is not a
# dated sampler log fails. Any other path under logs/ fails. An append of
# anything the sampler would not have written fails.
_SAMPLER_TRAIL_RE = re.compile(r"^meter-[0-9]{4}-[0-9]{2}-[0-9]{2}[.]log$")
_SAMPLER_STDOUT_NAME = "meter-sampler.log"
# The sampler's stdout, as its own code emits it: its own "sampler: " lines,
# the EODHD call report header, and that report's indented rows. Anything
# starting at column zero that is neither of the first two is not the sampler
# talking.
_SAMPLER_STDOUT_LINE_RE = re.compile(r"^(?:[ \t]|sampler: |EODHD call report$)")
# The keys every row of the meter trail carries. See ops/job_status.record_meter.
_SAMPLER_TRAIL_KEYS = frozenset({"at", "quota_day", "source", "step"})


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sampler_kind(path: Path, logs_root: Path) -> str | None:
    """trail, stdout, or None for everything else including the rest of logs/."""
    if path.parent != logs_root:
        return None
    if _SAMPLER_TRAIL_RE.match(path.name):
        return "trail"
    if path.name == _SAMPLER_STDOUT_NAME:
        return "stdout"
    return None


def _parses_as_sampler_rows(kind: str, chunk: bytes) -> bool:
    """Is this appended chunk what the sampler writes into that file.

    A single trailing INCOMPLETE line is tolerated, because the snapshot can
    catch a flush in progress and failing on that would trade one intermittent
    failure for another. Everything before it has to be whole and valid, and
    at least one whole valid line is required, so a chunk that is nothing but
    an unterminated fragment is refused.
    """
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text:
        return False  # an mtime touch with no bytes added is not an append
    # splitlines, not split on newline, because these files are written on
    # Windows through a shell redirect and every line ends CRLF. Splitting on
    # the newline alone leaves a carriage return on the end of each line, and
    # an anchored pattern then fails to match a line that is perfectly valid.
    lines = text.splitlines()
    if lines and not text.endswith(("\n", "\r")):
        lines = lines[:-1]  # the tolerated partial line
    complete = 0
    for line in lines:
        if not line.strip():
            continue
        if kind == "trail":
            try:
                row = json.loads(line)
            except ValueError:
                return False
            if not isinstance(row, dict) or not _SAMPLER_TRAIL_KEYS <= set(row):
                return False
        elif not _SAMPLER_STDOUT_LINE_RE.match(line):
            return False
        complete += 1
    return complete > 0


def sampler_append_allowed(path: Path, before: tuple[Any, ...] | None,
                           after: tuple[Any, ...] | None,
                           logs_root: Path | None = None) -> bool:
    """All three conditions, together. Anything else is a real change.

    before is None for a file that did not exist, which is the UTC midnight
    case: at 00:00 UTC the sampler starts a new meter-<quota day>.log rather
    than appending to yesterday's, so that night's run sees a CREATED path.
    It is handled here rather than left to fail once a month, and it is
    handled by the same three conditions with a zero length previous file,
    not by a separate rule that could disagree with this one.
    """
    root = logs_root if logs_root is not None else REAL_LOGS
    kind = _sampler_kind(path, root)
    if kind is None:
        return False
    if after is None or after[:1] != ("file",):
        return False  # deleted, or replaced by a directory
    if before is not None and before[:1] != ("file",):
        return False
    was_size = before[2] if before is not None else 0
    was_digest = (before[3] if before is not None and len(before) > 3
                  else _digest(b""))
    try:
        now = path.read_bytes()
    except OSError:
        return False
    if len(now) < was_size:
        return False  # truncated
    if _digest(now[:was_size]) != was_digest:
        return False  # rewritten under the same name, size unchanged or not
    return _parses_as_sampler_rows(kind, now[was_size:])


def _allowed(path: Path) -> bool:
    try:
        relative = path.relative_to(TREE_ROOT)
    except ValueError:
        return False
    return any(part in ALLOWED_DIR_NAMES for part in relative.parts)


def snapshot_tree(root: Path | None = None,
                  logs_root: Path | None = None) -> dict[str, tuple[Any, ...]]:
    """Every file and directory under the working tree, excluding the allowlist.

    Files carry mtime and size. Directories carry only a marker, not their
    mtime, because a directory's mtime moves whenever anything inside it is
    created, and an allowed __pycache__ write would otherwise fail the run
    through its parent. Directories are still tracked for existence, so a test
    that creates runs/2026-08-15/ is caught even before it writes a file into
    it.
    """
    base = root or TREE_ROOT
    logs = logs_root if logs_root is not None else REAL_LOGS
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
            if _sampler_kind(path, logs) is None:
                out[str(path)] = ("file", stat.st_mtime, stat.st_size)
                continue
            # The two sampler files carry a fourth element, a digest of their
            # whole contents. It is what makes "every byte that was there
            # before is still there" checkable rather than assumed, and it is
            # taken only for these two paths because hashing the tree would
            # cost more than the check is worth.
            #
            # The SIZE recorded here is the length of the bytes that were
            # hashed, not stat's. The sampler is appending to these files
            # while this loop runs, and a size from stat with a digest from a
            # later read describes a file that never existed: the digest would
            # then cover more bytes than the size claims, the append check
            # would compare the wrong prefix, and a perfectly ordinary tick
            # would be reported as a rewrite. That is the intermittent this
            # whole exemption exists to remove, reintroduced one layer down.
            try:
                payload = path.read_bytes()
                out[str(path)] = ("file", stat.st_mtime, len(payload),
                                  _digest(payload))
            except OSError:
                out[str(path)] = ("file", stat.st_mtime, stat.st_size)
    return out


# Kept under the old name so the call reads the same at both ends of the suite.
snapshot = snapshot_tree


def differences(before: dict[str, Any], after: dict[str, Any],
                logs_root: Path | None = None) -> list[str]:
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
        if sampler_append_allowed(Path(path), None, after[path], logs_root):
            continue  # 00:00 UTC, the sampler started the next day's trail
        out.append(f"created  {path}")
    for path in sorted(set(before) - set(after)):
        out.append(f"deleted  {path}")
    for path in sorted(set(before) & set(after)):
        was, now = before[path], after[path]
        if was == now:
            continue
        if sampler_append_allowed(Path(path), was, now, logs_root):
            continue  # the scheduled sampler ticked mid run, appending only
        if was[:1] == ("file",) and now[:1] == ("file",) and was[2] == now[2]:
            out.append(f"modified {path}  mtime only, size unchanged at {now[2]} "
                       "bytes (an external toucher looks like this; so does a "
                       "same size overwrite)")
        else:
            out.append(f"modified {path}  {was} -> {now}")
    return out


# True while activate() is holding the redirects. Read by standalone() below,
# so a nested activate is recognised rather than assumed, and by anything that
# needs to ask "am I sandboxed" without guessing from a path.
SANDBOX_ACTIVE = False


def standalone(entry) -> int:
    """Run one suite module's main() by hand, sandboxed the way run_tests is.

    run_tests.py wraps the whole suite in activate(). NOTHING ELSE DID, so
    `python -m tests.test_containment` ran every claim against the real data/,
    runs/, logs/ and site/. That is not hypothetical: on 2026-08-20 a direct
    run of test_containment appended sixteen of its own fixtures to the real
    data/quantifier-flags.jsonl, two of them carrying a verdict, and the next
    SANDBOXED run then failed too, because activate() copies data/ in and the
    fixtures came with it. The suite broke the suite.

    The tree photograph cannot catch this. It compares the set of paths before
    and after, and this path already existed; only its contents changed.

    Refusing the direct run was the other option and is worse. Running one
    module is exactly what a person does while chasing a failure, and a refusal
    would push them to run_tests for a twelve suite pass or to comment the
    guard out. So the direct run works and is sandboxed, which makes the
    footgun unreachable rather than merely discouraged.

    Nesting is safe and is why this checks rather than assumes: activate()
    saves whatever config currently holds and restores it on exit, so a module
    whose claims open their own sandbox still leaves the outer one intact.
    """
    if SANDBOX_ACTIVE:
        return entry()
    print("conftest: no sandbox was active, so this hand run is being wrapped "
          "in one. Real data/, runs/, logs/ and site/ are not writable from "
          "here; see standalone() in tests/conftest.py.")
    with activate():
        return entry()


@contextlib.contextmanager
def activate(copy_data: bool = True) -> Iterator[Path]:
    """Point every writable root at a temporary copy for the duration.

    data/ is copied rather than left empty because the suite reads real inputs
    from it: universe.json, the collector bar file, the backtest cache. Reads
    stay honest, writes land in the copy.
    """
    global SANDBOX_ACTIVE

    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-suite-"))
    saved_config = {name: getattr(config, name) for name in _CONFIG_PATHS}
    saved_modules: list[tuple[Any, str, Any]] = []
    # Captured before anything is redirected, and restored rather than cleared,
    # so a nested activate hands the flag back to the outer one instead of
    # telling it the sandbox is gone.
    was_active = SANDBOX_ACTIVE

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

        SANDBOX_ACTIVE = True
        with block_network():
            yield sandbox
    finally:
        SANDBOX_ACTIVE = was_active
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
