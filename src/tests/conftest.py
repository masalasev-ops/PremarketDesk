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

import atexit
import contextlib
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

from core import config

# Every config attribute that names something writable, and the modules that
# copied one at import time. A new module holding a path constant has to be
# added here; the mtime check below is what catches it if nobody remembers.
_CONFIG_PATHS = (
    "DATA_DIR", "PREMARKET_DIR", "RUNS_DIR", "LOGS_DIR", "SITE_DIR",
    "STUDY_DIR", "SESSION_DIR",
    "DB_PATH", "UNIVERSE_PATH", "WATCHLIST_PATH", "CA_BUNDLE_PATH",
)

_DERIVED = (
    ("research.backtest_pool", "CACHE_DIR", lambda c: c.DATA_DIR / "backtest"),
    ("research.backtest_pool", "EOD_DIR", lambda c: c.DATA_DIR / "backtest" / "eod"),
    ("research.backtest_pool", "SESSION_DIR", lambda c: c.DATA_DIR / "backtest" / "sessions"),
    ("research.replay_outcomes", "OUTCOMES_DIR", lambda c: c.DATA_DIR / "backtest" / "outcomes"),
    ("ops.job_status", "RECORD_PATH", lambda c: c.DATA_DIR / "job-status.jsonl"),
    ("ops.market_today", "CACHE_PATH", lambda c: c.DATA_DIR / "exchange-details.json"),
    ("ops.monitor_jobs", "STATE_PATH", lambda c: c.DATA_DIR / "monitor-reruns.json"),
    ("morning.verify_morning", "UNVERIFIED_MARKER", lambda c: c.DATA_DIR / "UNVERIFIED"),
    # Both markers have to be here for the same reason and it is not tidiness.
    # These are files whose EXISTENCE is a state, so an un-redirected one does
    # not read as an empty sandbox, it reads as the real machine's answer. A
    # real data/DORMANT would make ops.market_today.main return EXIT_DORMANT
    # inside the suite, and every claim about the trading day guard would pass
    # by never reaching the guard.
    ("ops.market_today", "DORMANT_MARKER", lambda c: c.DATA_DIR / "DORMANT"),
    # The third state marker, for the same reason: a real data/PUBLISH_HELD
    # would stand every sandboxed scheduled publish down and pass the claims
    # about the checks by never reaching them.
    ("ops.publish", "HOLD_MARKER", lambda c: c.DATA_DIR / "PUBLISH_HELD"),
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


# ------------------------------------------------ taking the sandbox back out
#
# On 2026-09-06 there were 246 abandoned directories in TEMP holding 6.0 GB,
# built up over two days by a suite that believed it cleaned up after itself.
# Two separate causes, and the same fix does not serve both:
#
#   ten were suite sandboxes, 5,983 MB of them, each a copy of data/. Six were
#   whole trees, which is what a run that is KILLED leaves: a finally clause
#   does not run in a process that was stopped. Nothing inside that process can
#   ever clean them up, so the next run has to.
#
#   the rest were partial trees, and 236 were small scratch directories. Those
#   were not killed. Their cleanup ran and quietly failed.
#
# Both were invisible because every removal here was rmtree(ignore_errors=True).

# The two prefixes are the whole family of temporary directories this project
# makes, and the sweep will delete a directory only if its name starts with one
# of them. That makes the pattern load bearing: a new prefix has to be one of
# these two or it will accumulate forever unswept.
_TEMP_PREFIXES = ("premarketdesk-", "pmd-")
TEMP_ROOT = Path(tempfile.gettempdir())

# How old an abandoned sandbox has to be before the sweep will take it. A run
# is two to three minutes and warns at eight. Six hours is not an estimate of
# how long a run takes; it is wide enough that anything inside it is a run that
# is genuinely still going, and a leaked directory loses nothing by waiting for
# the next run to collect it. Deleting a sandbox out from under a suite running
# beside this one is the only way this function can do harm, and the age is
# what prevents it.
STALE_AFTER_SECONDS = 6 * 60 * 60


def _remove_tree(path: Path, attempts: int = 4) -> bool:
    """Delete a directory tree, and SAY whether it actually went.

    The bare rmtree(ignore_errors=True) this replaces is why the leftovers
    above went unnoticed for two days. On Windows a file that has just been
    written is briefly held open by the on access virus scanner, rmtree raises
    on it, and ignore_errors turns that into silence. The evidence fits: what
    survived in the partial trees was hundreds of megabytes of backtest JSON
    that had just been copied in, and there was no .db-wal or .db-shm anywhere,
    so sqlite had closed cleanly and a held database was not the cause.

    Retrying with a short backoff clears the scanner case. Returning a bool
    covers the rest. The caller decides whether a survivor is worth printing;
    what it may no longer do is not know.
    """
    for attempt in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        if attempt < attempts - 1:
            time.sleep(0.25 * (attempt + 1))
    return not path.exists()


def sweep_stale_sandboxes(older_than: float = STALE_AFTER_SECONDS,
                          root: Path | None = None,
                          ) -> tuple[int, int, list[str]]:
    """Collect sandboxes earlier runs abandoned. Returns (taken, bytes, stuck).

    Narrow on purpose, and every clause of the test is a safety property: a
    directory, not a symlink, sitting DIRECTLY in the root, named with one of
    this project's prefixes, and older than `older_than`. Nothing recursive,
    nothing pattern matched loosely, nothing outside the root.

    `root` is a parameter rather than a patched global so the claim can aim
    this at a scratch directory and watch what it takes. The prefix test is
    absolute and does not depend on the root, so even pointed somewhere
    unintended this can only ever delete a directory named for this project.

    run_tests calls this once at startup. It is not called at import, because
    importing this file to debug a single claim must not delete anything.
    """
    taken, freed, stuck = 0, 0, []
    cutoff = time.time() - older_than
    for entry in sorted((root or TEMP_ROOT).glob("*")):
        if entry.is_symlink() or not entry.is_dir():
            continue
        if not entry.name.startswith(_TEMP_PREFIXES):
            continue
        try:
            if entry.stat().st_mtime > cutoff:
                continue
            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        except OSError:
            # Gone, or unreadable, between the glob and the stat. Either way it
            # is not this run's business and a sweep must never be the thing
            # that fails a suite.
            continue
        if _remove_tree(entry):
            taken += 1
            freed += size
        else:
            stuck.append(entry.name)
    return taken, freed, stuck


# ---------------------------------------------------- isolation at IMPORT time

def _redirect_config(root: Path) -> None:
    """Point every writable config path inside `root`."""
    config.DATA_DIR = root / "data"
    config.PREMARKET_DIR = config.DATA_DIR / "premarket"
    config.STUDY_DIR = config.DATA_DIR / "research"
    config.RUNS_DIR = root / "runs"
    config.LOGS_DIR = root / "logs"
    config.SITE_DIR = root / "site"
    config.DB_PATH = config.DATA_DIR / "premarketdesk.db"
    config.UNIVERSE_PATH = config.DATA_DIR / "universe.json"
    config.WATCHLIST_PATH = config.DATA_DIR / "watchlist.json"
    config.CA_BUNDLE_PATH = config.DATA_DIR / "ca-bundle.pem"
    for directory in (config.DATA_DIR, config.PREMARKET_DIR, config.RUNS_DIR,
                      config.LOGS_DIR, config.SITE_DIR, config.STUDY_DIR):
        directory.mkdir(parents=True, exist_ok=True)


# IMPORTING A TEST MODULE IS ITSELF THE ISOLATION. Until 2026-08-21 the
# redirection happened when run_tests set up its sandbox, which meant a claim
# invoked any other way ran against the live tree. Two incidents inside one
# fortnight, both while the claims were being debugged by hand, which is the
# normal thing to do with a claim:
#
#   claim 73 wrote fixture rows into the live picks table and overwrote a real
#   session's truth columns. store.guard_live_database now refuses that.
#
#   a sweep that called every claim directly ran universe.main() against the
#   REAL data root with the HTTP stub installed, and wrote 1,013 stub symbols
#   over a 2,126 name universe.json and 990 bytes over a 420 KB watchlist.json.
#   No quota was spent, because the stub caught the network, and the files were
#   destroyed anyway. A guard that refuses the DATABASE does not refuse a JSON
#   file, and there are a dozen writable paths.
#
# So the redirect happens HERE, at conftest import, before any test module has
# had a chance to touch a path. run_tests still builds its own sandbox and
# repoints everything at it a moment later; this is what covers every other way
# a claim can be reached. The real roots are captured above, before this runs,
# and the tree photograph still guards the real working tree.
_IMPORT_SANDBOX = Path(tempfile.mkdtemp(prefix="pmd-import-"))
_redirect_config(_IMPORT_SANDBOX)
# And taken back out when the process ends. EVERY process that imports this
# file makes one of these, which is every suite run and every hand debugged
# claim, and until this line none of them was ever removed: 28 were sitting in
# TEMP when the sweep above was written. They are a few empty directories each,
# which is exactly why a month of them went unnoticed.
atexit.register(_remove_tree, _IMPORT_SANDBOX)

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


# ------------------------------------ the second behaviour exemption
#
# .git/FETCH_HEAD, that one path, and nothing else anywhere under .git/.
#
# VSCode's git extension runs `git fetch` on a timer. This machine carries
# "git.autofetch": true in its user settings, and the default period is 180
# seconds: measured on 2026-08-20, FETCH_HEAD was rewritten at 20:33:30 and
# again at 20:36:31, 181 seconds apart, with the size unchanged at 106 bytes
# because the fetch found nothing new. A suite run takes about thirty seconds,
# so roughly one run in six straddles a fetch and fails on a path no test
# touches. That is the same intermittent isolation failure the sampler
# exemption above exists to remove, and the same argument applies: a gate that
# fails at random teaches its reader to stop reading it.
#
# The 2026-08-14 correction on differences() is why this is written narrowly
# and why the internal explanations were exhausted first. That session
# attributed an mtime-only change to "a virus scanner or an indexer" when the
# real cause was config.build_identifier() running `git status`, and reaching
# for the external explanation before the internal ones let it survive a day.
# So: every git invocation in this repository is
# `git --no-optional-locks status --porcelain` in core/config.py and
# `git --no-optional-locks ls-files` twice in tests/test_regressions.py. None
# of the three writes FETCH_HEAD. Only a fetch or a pull does, and nothing
# here runs either.
#
# claim_no_python_here_runs_a_git_fetch is what keeps that true. The day
# something in this project starts fetching is the day this exemption begins
# hiding a real write, and the claim fails on that day rather than on the one
# somebody notices.
# ------------------------------------------------- running one claim
#
# A claim that raised used to end the rest of its module. run_tests caught
# the exception at module level, printed it, and every claim after the one
# that raised never ran, so one broken fixture could hide a module's worth of
# coverage behind a single traceback. Every module's main() now calls its
# claims through this, which records the traceback as a failure and carries
# on. test_regressions did this by hand in six places; this is the one place.
def run_claim(failures: list[str], claim: Any, *args: Any) -> None:
    """Call claim(*args); a raise becomes a recorded failure, not an abort."""
    import traceback

    try:
        claim(*args)
    except Exception as exc:  # noqa: BLE001, a claim's raise is the finding
        failures.append(
            f"{getattr(claim, '__name__', repr(claim))} raised "
            f"{type(exc).__name__}: {exc}\n"
            + "".join(traceback.format_exception(exc)).rstrip())


# ------------------------------------ the third behaviour exemption
#
# The live database's -shm and -wal sidecars, and only when the database
# itself did not move.
#
# SQLite in WAL mode rewrites the shared memory index and touches the write
# ahead log whenever a connection opens or closes, including a read only
# connection from another process: an editor extension browsing the file, a
# hand query in another terminal. On 2026-09-02 a suite run in which every
# claim passed reported FAILED because data/premarketdesk.db-shm had a new
# mtime and the same 32,768 bytes, while the .db itself was unchanged and no
# job had written a status record. That is the same intermittent the two
# exemptions above exist to remove, and it teaches the same wrong lesson.
#
# Three conditions, together: the path is a .db-shm or .db-wal sidecar by
# name; its size is unchanged, so this is a touch and not a write of new
# pages; and the .db it belongs to is unchanged between the two snapshots, so
# no row moved. A sidecar that grew fails. A sidecar whose database also
# changed fails, because that is a write, whoever made it.
_SQLITE_SIDECAR_SUFFIXES = (".db-shm", ".db-wal")


def _sqlite_sidecar_touch(path: Path, was: Any, now: Any,
                          before: dict[str, Any], after: dict[str, Any]) -> bool:
    name = path.name
    if not name.endswith(_SQLITE_SIDECAR_SUFFIXES):
        return False
    if not (was[:1] == ("file",) and now[:1] == ("file",)) or was[2] != now[2]:
        return False
    database = str(path.with_name(name.rsplit("-", 1)[0]))
    return before.get(database) is not None and before.get(database) == after.get(database)


@contextlib.contextmanager
def isolated_store() -> Iterator[Path]:
    """A private data root, runs root and database, for the duration.

    THE FIXTURE A CLAIM CARRIES WITH IT. Until 2026-08-21 isolation was
    supplied by run_tests: conftest rebound config.DATA_DIR, RUNS_DIR and
    DB_PATH around the whole suite, and a claim inherited it without asking.
    That is correct under the runner and absent everywhere else, and calling a
    claim directly is the normal way to debug one. Claim 73 was written that
    way, rebound two of the three names and not DB_PATH, and while it was being
    checked by hand it wrote fixture rows into the live picks table and
    overwrote a real session's truth columns.

    So the isolation moved into the module a claim imports. Any claim that
    touches the store opens with

        with conftest.isolated_store() as box:

    and is then safe under run_tests, under a REPL, and under whatever runs it
    next. store.guard_live_database refuses the live file outright if a claim
    forgets, so the two together are a fixture and a backstop rather than one
    of each.

    ALL THREE NAMES, because rebinding a subset is exactly the failure this
    replaces. DB_PATH is not derived from DATA_DIR at call time: config sets it
    once at import, so moving DATA_DIR alone leaves the database where it was.
    """
    box = Path(tempfile.mkdtemp(prefix="pmd-claim-"))
    saved = (config.DATA_DIR, config.RUNS_DIR, config.DB_PATH,
             config.PREMARKET_DIR, config.LOGS_DIR, config.STUDY_DIR)
    try:
        config.DATA_DIR = box / "data"
        config.RUNS_DIR = box / "runs"
        config.LOGS_DIR = box / "logs"
        config.PREMARKET_DIR = config.DATA_DIR / "premarket"
        config.STUDY_DIR = config.DATA_DIR / "research"
        config.DB_PATH = config.DATA_DIR / "premarketdesk.db"
        config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        yield box
    finally:
        (config.DATA_DIR, config.RUNS_DIR, config.DB_PATH,
         config.PREMARKET_DIR, config.LOGS_DIR, config.STUDY_DIR) = saved
        _remove_tree(box)


def _external_fetch_marker(path: Path, root: Path | None = None) -> bool:
    """True for the one path a git client rewrites and nothing here does."""
    return path == (root or TREE_ROOT) / ".git" / "FETCH_HEAD"


# ------------------------------------ the fourth behaviour exemption
#
# .git/gk/config, that one path, for the same reason as FETCH_HEAD above.
#
# The GitLens extension in this editor keeps per branch state there and
# rewrites it on its own schedule, and the rewrite CHANGES BYTES: on
# 2026-09-11 it went to gk-last-accessed and gk-last-modified =
# 2026-09-11T14:41:13.290Z at 10:41:13, same 135 bytes, different digest, and
# failed a nine minute run in which every module had passed. The digest added
# on 2026-09-06 was written for this file on the belief that the rewrite was
# the same bytes. It was never going to forgive it: the two timestamps are in
# the content. Nothing in this project writes under .git/gk/, because every
# git call here is `--no-optional-locks status` or `ls-files`, the same
# inventory the FETCH_HEAD note rests on.
def _editor_branch_state(path: Path, root: Path | None = None) -> bool:
    """True for the one file GitLens rewrites with fresh timestamps."""
    return path == (root or TREE_ROOT) / ".git" / "gk" / "config"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# Files at or under this size carry a digest in the snapshot, so an mtime that
# moved can be asked whether any byte moved with it. Above it a file keeps
# mtime and size only and an mtime-only change stays ambiguous, which is the
# behaviour every file had before 2026-09-06.
#
# 64 KB is where the cost stops being free rather than a natural boundary in
# the data. Measured on this tree: 2,479 of 3,501 files sit at or under it and
# hash in 0.16s a snapshot; raising it to 1 MB takes in 776 more files and 174
# more megabytes for them. The three files this was written for are 106 bytes,
# 106 bytes and 32,768.
HASH_MAX_BYTES = 65_536


def _same_bytes(was: Any, now: Any) -> bool:
    """True when both snapshots hashed this file and nothing in it moved.

    The mtime is deliberately not compared: this answers "did the CONTENT
    change", and a differing mtime with an identical digest is the whole case
    it exists to clear.
    """
    return (len(was) == 4 and len(now) == 4
            and was[0] == "file" and now[0] == "file"
            and was[2] == now[2] and was[3] == now[3])


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
                # EVERY SMALL FILE IS HASHED TOO, since 2026-09-06. The
                # comment below used to say the digest was taken for the two
                # sampler paths alone because hashing the tree would cost
                # more than the check is worth. That was true when it was
                # written and is not any more: measured on this tree, the
                # 2,479 files at or under HASH_MAX_BYTES hash in 0.16 seconds
                # a snapshot, 0.32 a run, against a suite that runs for nine
                # minutes. What the digest buys is in the differences() note:
                # an mtime that moved with no byte behind it stops being a
                # guess. Files past the cap keep mtime and size, so the
                # ambiguity survives exactly where reading the bytes would
                # cost something, and the message says which kind it is.
                if stat.st_size > HASH_MAX_BYTES:
                    out[str(path)] = ("file", stat.st_mtime, stat.st_size)
                    continue
                try:
                    payload = path.read_bytes()
                    out[str(path)] = ("file", stat.st_mtime, len(payload),
                                      _digest(payload))
                except OSError:
                    out[str(path)] = ("file", stat.st_mtime, stat.st_size)
                continue
            # The two sampler files carry a fourth element, a digest of their
            # whole contents. It is what makes "every byte that was there
            # before is still there" checkable rather than assumed, and they
            # are hashed WHATEVER their size, because the append check needs
            # the digest and a trail that grew past the cap must not silently
            # stop being checkable.
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


def differences(before: dict[str, Any], after: dict[str, Any],
                logs_root: Path | None = None) -> list[str]:
    """What changed between two snapshots, as readable lines.

    A modification says whether the size moved as well as the mtime, because
    a test that wrote a file almost always changes its size while something
    that merely touched it does not. Both still fail the run, on purpose: a
    same size overwrite is a real escape mode and the check must not start
    guessing which is which.

    [amended 2026-09-06: it no longer has to guess, for a file at or under
    HASH_MAX_BYTES. The snapshot carries a digest for those, so an mtime that
    moved with every byte identical is KNOWN to be a touch and is not a
    difference at all, and a same size overwrite is caught by its digest
    rather than described as indistinguishable from one. The paragraph above
    still holds above the cap and its message says so there.

    This is a widening and a tightening at once, which is why it is safe. It
    stops the run failing on an external toucher: on 2026-09-06 a git GUI
    rewrote .git/gk/config with the same 106 bytes mid run and failed a suite
    in which every one of the fourteen modules had passed.
    [corrected 2026-09-11: was "the same 106 bytes". The same SIZE was all the
    old check could see. The file carries two timestamps GitLens rewrites every
    time, so the bytes differed and the digest never forgave it; it now has its
    own exemption, _editor_branch_state. The widening below is still right for
    every other touch.] And it closes the
    hole the paragraph above admits, because a same size overwrite used to
    reach the reader as the same sentence as a harmless touch, leaving them to
    tell apart two things the check itself could not.

    The 2026-08-14 lesson below survives this unchanged and is the reason the
    cap exists rather than a blanket trust of identical bytes: an INTERNAL
    cause must still be exhausted before an external one is assumed. What the
    digest removes is the class of report that cannot be investigated at all,
    not the obligation to investigate.]

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
        if _external_fetch_marker(Path(path)):
            continue  # the editor's first autofetch of this clone
        if _editor_branch_state(Path(path)):
            continue  # GitLens wrote its branch state for the first time
        out.append(f"created  {path}")
    for path in sorted(set(before) - set(after)):
        out.append(f"deleted  {path}")
    for path in sorted(set(before) & set(after)):
        was, now = before[path], after[path]
        if was == now:
            continue
        if _same_bytes(was, now):
            continue  # the mtime moved and not one byte did
        if sampler_append_allowed(Path(path), was, now, logs_root):
            continue  # the scheduled sampler ticked mid run, appending only
        if _external_fetch_marker(Path(path)):
            continue  # the editor autofetched mid run, see the note above
        if _editor_branch_state(Path(path)):
            continue  # GitLens restamped its branch state mid run
        if _sqlite_sidecar_touch(Path(path), was, now, before, after):
            continue  # another process holds the live database open
        if was[:1] == ("file",) and now[:1] == ("file",) and was[2] == now[2]:
            if len(was) == 4 and len(now) == 4:
                out.append(f"modified {path}  SAME SIZE, DIFFERENT BYTES at "
                           f"{now[2]} bytes. Both snapshots hashed it and the "
                           "digests disagree, so this is a rewrite and not a "
                           "toucher")
            else:
                out.append(
                    f"modified {path}  mtime only, size unchanged at {now[2]} "
                    f"bytes, and past the {HASH_MAX_BYTES:,} byte hashing cap "
                    "so the bytes were not compared (an external toucher looks "
                    "like this; so does a same size overwrite)")
        else:
            out.append(f"modified {path}  {was} -> {now}")
    return out


# True while activate() is holding the redirects. Read by standalone() below,
# so a nested activate is recognised rather than assumed, and by anything that
# needs to ask "am I sandboxed" without guessing from a path.
SANDBOX_ACTIVE = False


def _rebase(path: Path) -> Path | None:
    """The sandbox path a real one maps onto, or None when it is not redirected.

    Only the four writable roots move. A doc/ or src/ path is returned as None
    and left exactly as it was, because nothing writes to those and rewriting
    one would break a module that reads CRITERIA.md through an absolute path it
    captured at import.
    """
    for real, live in ((REAL_DATA, config.DATA_DIR),
                       (REAL_RUNS, config.RUNS_DIR),
                       (REAL_LOGS, config.LOGS_DIR),
                       (REAL_SITE, config.SITE_DIR)):
        try:
            relative = path.relative_to(real)
        except ValueError:
            continue
        return live if relative == Path(".") else live / relative
    return None


# How far _rebase_value looks inside a module level container: three turns, so
# a list of run directories, a dict of lists of them, and one more. Anything
# deeper is a data structure rather than a captured constant, and a walk with
# no floor under it can be handed a self referencing one and never come back.
_CONTAINER_DEPTH = 3


def _rebase_value(value: Any, depth: int = _CONTAINER_DEPTH) -> Any:
    """The same value with every redirected Path inside it moved, or None.

    None means nothing in it moved, which is what the caller needs in order to
    leave an attribute alone rather than rebinding it to an equal copy.

    Containers are REBUILT rather than edited in place. A module holding
    RUN_DIRS = [RUNS_DIR / "2026-08-14"] shares that list object with anything
    that did `from tests.test_x import RUN_DIRS`, so mutating it would reach
    into modules this function was never asked about, and restoring it would
    then have to unpick edits made through a second name for the same object.
    Rebinding the attribute leaves the original list exactly as it was.

    Exact types, not isinstance: a namedtuple is a tuple whose constructor
    takes its fields positionally, and a defaultdict rebuilt as one loses its
    factory. Rebuilding either would be a silent corruption of a value this
    function was only asked to redirect.
    """
    if isinstance(value, Path):
        return _rebase(value)
    if depth <= 0:
        return None
    if type(value) in (list, tuple, set, frozenset):
        items = [_rebase_value(item, depth - 1) for item in value]
        if all(item is None for item in items):
            return None
        return type(value)(
            original if moved is None else moved
            for original, moved in zip(value, items)
        )
    if type(value) is dict:
        items = {key: _rebase_value(item, depth - 1) for key, item in value.items()}
        if all(item is None for item in items.values()):
            return None
        return {key: value[key] if moved is None else moved
                for key, moved in items.items()}
    return None


def _path_holders(module: Any) -> list[tuple[Any, str]]:
    """The module itself, and every class defined in it, each with a label.

    A class is included only when it was defined in this module, which is what
    __module__ records. Scanning imported classes as well would let this
    function rebind an attribute on something it was never asked about, and
    pathlib.Path itself is one import away from every suite file.
    """
    holders: list[tuple[Any, str]] = [(module, "")]
    home = getattr(module, "__name__", None)
    for name, value in list(vars(module).items()):
        if (isinstance(value, type) and home is not None
                and getattr(value, "__module__", None) == home):
            holders.append((value, f"{name}."))
    return holders


@contextlib.contextmanager
def redirect_captured_paths(module: Any) -> Iterator[list[str]]:
    """Move one module's import time Path constants onto the live sandbox.

    activate() rebinds the config attributes, and run_tests then reloads each
    suite module inside the sandbox so anything that copied one at import gets
    the sandbox copy. A hand run has neither half. The module executed before
    the sandbox opened, and for `python -m tests.test_repricing` a reload could
    not help at all: the running object is __main__, its __spec__ names
    tests.test_repricing, and sys.modules holds something else under that name,
    so importlib.reload raises rather than rebinding anything.

    So the constants are rebound in place instead. Measured on 2026-08-20: with
    the sandbox held, config.RUNS_DIR was the temporary copy while
    test_repricing.RUN_DIR was still the real runs/2026-08-14, and claim_three
    sets config.DB_PATH to RUN_DIR / "test_repricing.db" and opens it in WAL
    mode, so a hand run created a SQLite database inside the preserved evidence
    directory of the first live morning. The tree photograph cannot catch that:
    it runs only inside run_tests.main(), which a hand run never enters.

    Restored on exit, so a repeated or nested run leaves the module as it found
    it.

    What is looked at grew on 2026-08-20 as well, and the reason is worth
    keeping. This walked vars(module) for Path values and nothing else, so a
    module holding its run directories in a LIST, or on a CLASS, was quietly
    skipped and standalone() then printed an unqualified all clear over it. The
    all clear is what made that dangerous rather than merely incomplete: a
    reader who saw it had been told the hand run was safe. Module level lists,
    tuples, sets and dicts and the classes defined in the module are now looked
    inside too, and standalone() names what was examined rather than declaring
    the module clean.

    Two holes are left and are left knowingly, because saying which ones is
    worth more than implying there are none. A path held as a string is not a
    Path and is not moved. A path built inside a function from config at call
    time is not a captured constant at all, and needs no moving: it reads the
    redirected config the moment it runs.
    """
    saved: list[tuple[Any, str, Any]] = []
    moved: list[str] = []
    if module is None:
        yield moved
        return
    for owner, label in _path_holders(module):
        for name, value in list(vars(owner).items()):
            if name.startswith("__"):
                continue
            rebased = _rebase_value(value)
            if rebased is None or rebased == value:
                continue
            saved.append((owner, name, value))
            setattr(owner, name, rebased)
            moved.append(f"{label}{name}")
    try:
        yield moved
    finally:
        for owner, name, value in saved:
            setattr(owner, name, value)


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

    Wrapping the run was only half of it. Until this function also rebound the
    module's own path constants, a module that captured config.RUNS_DIR at
    import kept the real one inside the sandbox: test_repricing.RUN_DIR is
    runs/2026-08-14 and claim_three opened a database in it, inside the
    preserved evidence of the first live morning. See
    redirect_captured_paths() above.

    The line printed when nothing moved says what was examined rather than
    that the module is clean. It used to read "this module captured no real
    data/, runs/, logs/ or site/ path at import time", which is a claim about
    the module and was only ever a report on vars(module): a module holding
    its paths in a list or on a class was scanned past and then told the
    reader it had nothing. Both halves are fixed, the looking and the saying,
    because widening the search would have left the same unqualified sentence
    standing over whatever the next shape turns out to be.
    """
    if SANDBOX_ACTIVE:
        return entry()
    module = sys.modules.get(getattr(entry, "__module__", "") or "")
    print("conftest: no sandbox was active, so this hand run is being wrapped "
          "in one; see standalone() in tests/conftest.py.")
    with activate():
        with redirect_captured_paths(module) as moved:
            if moved:
                print("conftest: rebound this module's import time path "
                      f"constant(s) onto the sandbox: {', '.join(sorted(moved))}")
            else:
                print("conftest: no real data/, runs/, logs/ or site/ path was "
                      "found in this module's constants, in a list, tuple, set "
                      "or dict of them, or on a class defined here. A path held "
                      "as a string is not checked; a path built from config "
                      "inside a function needs no check, because it reads the "
                      "redirected config when it runs.")
            return entry()


# ------------------------------------------- what the sandbox does NOT copy
#
# One directory, named rather than matched by size, because a rule like "skip
# anything over 100 MB" silently changes what the suite can see the day a file
# grows.
#
# data/backtest/outcomes is 701 MB of the 816 MB backtest cache, it is written
# only by a hand run of research/replay_outcomes.py, and NOTHING IN THE SUITE
# READS IT: every reference to that module in tests/ reads its SOURCE with
# read_text, to check what it writes and where, and none of them opens a file
# under this directory.
#
# It costs about 3 seconds per copy, and activate() is called 90 times in a
# run, once by run_tests and 89 times inside test_regressions. That is four
# and a half minutes of copying a directory no claim opens, and it appeared on
# 2026-09-05 when the 240 session cache was refetched: the suite went from
# about four minutes to over eleven with no test having changed, which is the
# shape of a cost nobody chose. The sessions and eod directories beside it ARE
# copied, because test_backtest reads both through cached_sessions.
#
# If a claim ever needs these rows, copy them for that claim rather than
# widening this: the whole point is that the exclusion is one named path a
# reader can check.
#
# AND SQLITE'S WAL SIDECARS, which is a different reason and a sharper one.
# premarketdesk.db-wal and -shm exist only while a connection is open and
# vanish on a clean close, so copytree can list them and then fail to read
# them: shutil.Error, and the claim dies, whenever anything else touches the
# database while the copy runs. A hand run script, an overlapping scheduled
# job, a second suite. Observed 2026-09-06.
#
# Copying them is also wrong when it SUCCEEDS. A -wal captured a moment out of
# step with the .db beside it gives the sandbox a database whose committed
# state is not the one the working tree holds, and the suite then reads that.
# The .db alone is a consistent snapshot of everything committed; the sidecars
# are never wanted here.
def _skip_bulk_research(dirpath: Any, names: list[str]) -> set[str]:
    skip = {n for n in names if n.endswith(("-wal", "-shm"))}
    if Path(dirpath).name == "backtest":
        skip.add("outcomes")
    return skip


@contextlib.contextmanager
def activate(copy_data: bool = True) -> Iterator[Path]:
    """Point every writable root at a temporary copy for the duration.

    data/ is copied rather than left empty because the suite reads real inputs
    from it: universe.json, the collector bar file, the backtest cache. Reads
    stay honest, writes land in the copy. One directory is excluded and
    _skip_bulk_research above says which and why.
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
            shutil.copytree(REAL_DATA, data_copy, ignore=_skip_bulk_research)
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
        config.STUDY_DIR = data_copy / "research"
        config.SESSION_DIR = data_copy / "sessions"
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
        if not _remove_tree(sandbox):
            # Said out loud rather than swallowed, because this directory holds
            # a copy of data/ and is therefore close to a gigabyte. Two days of
            # silence here cost 6 GB.
            print(f"conftest: WARNING, the sandbox at {sandbox} could not be "
                  "removed. It holds a copy of data/. The next run's sweep "
                  "will collect it once it is six hours old.")


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

    # wrangler is the one exit that is a subprocess rather than an HTTP
    # session, so it is blocked at its own seam. A claim that means to reach
    # it assigns publish.run_wrangler a stub and restores it.
    from ops import publish

    saved_wrangler = publish.run_wrangler

    def _blocked_wrangler(args: list[str], *_a: Any, **_k: Any) -> Any:
        raise NetworkBlocked(
            f"a test tried to run wrangler {' '.join(args[:2])}, which uploads to "
            "Cloudflare. Stub it by assigning ops.publish.run_wrangler.")

    publish.run_wrangler = _blocked_wrangler

    try:
        yield
    finally:
        eodhd.build_session = saved_build
        eodhd.read_meter = saved_meter
        eodhd._default_client = saved_client
        publish.run_wrangler = saved_wrangler
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
    return {kind: row for kind, row in template_headers().items()
            if kind.endswith("watchlist")}


def template_headers() -> dict[str, str]:
    """Every Ticker header row the template pins, keyed by its section.

    Three of them: the two watchlists and, since 2026-08-20, the notable movers
    table. The notable one is kept in this map and OUT of watchlist_headers()
    above, because analyst._REQUIRED_TABLES must contain exactly the two
    watchlists and claim_headers_cannot_diverge compares that map against
    watchlist_headers() key for key. A briefing table that could satisfy the
    vacuum detector would let a report ship with no watchlist at all, which is
    the failure the detector exists to catch.
    """
    from core import config

    text = config.REPORT_TEMPLATE_PATH.read_text(encoding="utf-8")
    wanted = {"## Day watchlist": "day watchlist",
              "## Swing watchlist": "swing watchlist",
              "## Notable movers": "notable movers"}
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


def filled_skeleton(skeleton: str, sentence: str | None = None) -> str:
    """A slots answer good enough to pass check_slots, for a stubbed model.

    Under CRITERIA [Analyst] mode = slots the model is handed the skeleton
    and returns it with the markers replaced. A stub that returns a whole
    freeform report is refused, correctly, and a claim written around one
    tests the refusal path rather than whatever it meant to test.

    So this fills each marker with prose of the right SHAPE: a few words for
    a mood, a sentence for a tone or a headline reading, and for a setup the
    invalidation lead in that check_slots insists on. `sentence` is appended
    to the first slot, which is how a claim about the quantifier guard puts
    the sentence it wants flagged where a model would have written it.

    Nothing here asserts. A claim that wants a REJECTED answer builds one
    itself; this is the accepted one.
    """
    from morning import analyst

    filled = skeleton
    for index, marker in enumerate(analyst.markers_in(skeleton)):
        name = marker.strip("{}").split(":")[0]
        if name == analyst.SLOT_MOOD:
            text = "a stubbed mood"
        elif name == analyst.SLOT_SETUP:
            text = ("The level to work from is the premarket high. "
                    f"{analyst.INVALIDATION_MARKER} a break back under the "
                    "premarket low on rising volume.")
        else:
            text = "A stubbed sentence written by the suite."
        if index == 0 and sentence:
            text = f"{text} {sentence}"
        filled = filled.replace(marker, text, 1)
    return filled


def watchlist_table(kind: str, rows: list[str] | None = None) -> str:
    """A whole table section, header and separator and body, from the template.

    kind is "day watchlist", "swing watchlist" or "notable movers". rows are
    body lines already formatted as markdown; the default is the template's own
    empty table row, because REPORT_TEMPLATE.md requires each of these tables to
    be written even when it selected nothing.
    """
    header = template_headers()[kind]
    columns = len([cell for cell in header.strip().strip("|").split("|")])
    separator = "| " + " | ".join(["---"] * columns) + " |"
    body = rows if rows else ["| none |" + " |" * (columns - 1)]
    heading = "## " + kind[:1].upper() + kind[1:]
    return "\n".join([f"{heading}", "", header, separator, *body, ""])
