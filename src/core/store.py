"""SQLite storage.

One database file, opened the same way everywhere, with the schema created on
demand so no script depends on another having run first.

Two habits worth keeping. Tables carry natural primary keys, not autoincrement
ids, so re-running a day updates its rows instead of quietly accumulating a
second copy. And every write path uses an upsert, so idempotency is a property
of the schema rather than something each script has to remember.
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
import sys
from pathlib import Path
import weakref
from typing import Any, Iterable, Iterator

from core import config

# Table and column names are interpolated into SQL text and therefore must be
# code literals, never data. This pattern is the enforcement.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_identifier(name: str) -> str:
    """Refuse anything that is not a plain SQL identifier, before it reaches SQL."""
    if not isinstance(name, str) or not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(
            f"not a valid SQL identifier: {name!r}. Table and column names are "
            "interpolated into SQL and must be code literals, never data."
        )
    return name

_SCHEMA = """
CREATE TABLE IF NOT EXISTS baseline (
    ticker        TEXT NOT NULL,
    cutoff_hhmm   TEXT NOT NULL,
    median_volume REAL,
    sessions_used INTEGER NOT NULL DEFAULT 0,
    computed_at   TEXT NOT NULL,
    PRIMARY KEY (ticker, cutoff_hhmm)
);

CREATE TABLE IF NOT EXISTS picks (
    date              TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    day_eligible      INTEGER,
    swing_eligible    INTEGER,
    score             REAL,
    conviction        TEXT,
    gap_pct           REAL,
    pm_rvol           REAL,
    pm_high           REAL,
    pm_low            REAL,
    pm_vwap           REAL,
    collector_covered INTEGER,
    pm_window_start   TEXT,
    prior_high        REAL,
    catalyst_class    TEXT,
    entry_ref         REAL,
    stop_ref          REAL,
    source            TEXT,
    score_partial     REAL,
    score_unavailable TEXT,
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS sessions (
    -- One row a session, written by desk.compact after the morning and again
    -- after the midday pass. It is a SUMMARY and never the evidence: every
    -- column here is derivable from that session's packet, which is kept
    -- forever under CRITERIA [Retention] and is what the screens are drawn
    -- from. This table exists so the Sessions, Record and Name screens can
    -- ask a question across every session without opening every packet.
    --
    -- Rewritten in full on every build, never appended, so running the build
    -- twice is the same as running it once. That is build_archive's property
    -- and it is the property that makes a summary safe to keep.
    date                TEXT NOT NULL,
    generated_at        TEXT,
    run_at              TEXT,
    -- The screen counts, as the morning published them.
    candidates          INTEGER,
    day_eligible        INTEGER,
    swing_eligible      INTEGER,
    green               INTEGER,
    yellow              INTEGER,
    red                 INTEGER,
    gapped_up           INTEGER,
    gapped_down         INTEGER,
    top_symbol          TEXT,
    top_gap_pct         REAL,
    -- The pipeline, from candidate_provenance, so the Sessions screen can say
    -- how twelve became three without reading the packet.
    pool_size           INTEGER,
    subscribed          INTEGER,
    ranked              INTEGER,
    cleared_floors      INTEGER,
    kept                INTEGER,
    capped_out          INTEGER,
    -- The midday half. NULL for a session whose 12:00 pass never ran, which
    -- is a different thing from a session where nothing triggered, and the
    -- screens must not read one as the other.
    midday_generated_at TEXT,
    triggered           INTEGER,
    gapped_through      INTEGER,
    never_triggered      INTEGER,
    midday_median_move  REAL,
    -- Whether the day is readable at all, and in what form.
    packet_bytes        INTEGER,
    packet_compressed   INTEGER,
    has_report          INTEGER,
    computed_at         TEXT NOT NULL,
    PRIMARY KEY (date)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    date             TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    -- Rows are keyed on the rule version, so changing the rule in CRITERIA
    -- [Paper] books BESIDE what the old one produced rather than over it. A
    -- ledger that overwrote itself on every rule change could not answer
    -- whether the change helped, which is most of what a ledger is for.
    rule_version     TEXT NOT NULL,
    -- The window the rule traded, on the PICK'S OWN session. Not the one
    -- picks.next_day_* describes, which is the session after it. Carried per
    -- row so a row says which day it is about rather than inheriting an
    -- assumption. See CRITERIA [Paper].
    session          TEXT,
    -- The screen's verdict, carried as a GROUPING column and never as a
    -- filter. Booking only what the screen admitted makes "did the screen
    -- separate outcomes" unaskable, and that is the question this feeds.
    day_eligible     INTEGER,
    swing_eligible   INTEGER,
    conviction       TEXT,
    score            REAL,
    -- 1 when a trade was taken. 0 covers both a row skipped on evidence and
    -- one whose trigger never fired; skip_reason and exit_reason say which,
    -- and a skipped pick is WRITTEN rather than dropped so it can still be
    -- counted later.
    booked           INTEGER,
    skip_reason      TEXT,
    entry_ref_used   REAL,
    stop_ref_used    REAL,
    entry_at         TEXT,
    entry_price      REAL,
    exit_at          TEXT,
    exit_price       REAL,
    exit_reason      TEXT,
    shares           INTEGER,
    notional         REAL,
    -- What this trade could actually LOSE in dollars: the stop distance times
    -- the shares. Under a fixed notional it is whatever the stop distance
    -- happens to be, and over v1's first sixteen trades it ran 253 to 2,141;
    -- under a fixed risk it is the same on every trade by construction.
    -- Recorded rather than derived so the two sizings can be read side by side.
    risk_notional_taken REAL,
    -- Which sizing mode produced the position, carried per row so a row says
    -- how it was sized rather than inheriting whatever CRITERIA says today.
    sizing_mode      TEXT,
    -- NULL, never zero, on a row that took no trade. A zero P&L is a flat
    -- trade and a null one is no trade, and a median that mixes them is the
    -- defect this project has now found under five other names.
    pnl              REAL,
    pnl_pct          REAL,
    max_drawdown_pct REAL,
    -- WHEN things happened, which is the only part of this table that is any
    -- use before the record is large enough to judge. minutes_to_trigger is
    -- counted from the open and minutes_to_peak from the ENTRY, so one answers
    -- "should I still be watching this at 10:00" and the other "is this one
    -- done", and neither answers the other. Both are BAR counts: the vendor
    -- publishes a minute bar only for a minute that traded.
    minutes_to_trigger INTEGER,
    minutes_to_peak  INTEGER,
    -- The best the position was ever worth while it was actually open. NOT
    -- picks.mfe_pct_true, which is a bound over the whole of the FOLLOWING
    -- session measured from a reference level rather than from a fill.
    mfe_pct_held     REAL,
    bars_held        INTEGER,
    booked_at        TEXT,
    PRIMARY KEY (date, ticker, rule_version)
);
"""

# Columns added after the first schema shipped. init() widens existing
# databases with these so no script depends on another having migrated first.
_PICKS_LATER_COLUMNS = (
    # THE VENDOR'S SECTOR FOR THE NAME, recorded so the morning's composition
    # can one day be compared against its own history rather than left as a
    # number with no scale. "Nine of twelve in one sector" is a concentrated
    # morning or an ordinary one and a reader has no way to tell without the
    # median across past sessions.
    #
    # It is a RECORD ONLY. Nothing screens on it, nothing scores on it, and
    # scan.list_shape reads today's from the packet rather than from here.
    # This column exists so the comparison becomes possible, and it cannot
    # answer for a session that closed before it existed: rows written before
    # this carry NULL, which reads as a session whose sectors were never
    # recorded and never as a session with no sector.
    ("sector", "TEXT"),
    # 'live', 'test' or 'reconstructed'. The writer sets it explicitly on
    # every row; NULL can only mean the row predates the column, and every
    # row in the table on migration day (2026-08-14) was test data from
    # midday runs, so init() marks NULL rows 'test'. That backfill statement
    # is permanently idempotent: no writer ever leaves source NULL.
    ("source", "TEXT"),
    # The sum over the KNOWN score components when the total score is null
    # because a component input was never observed, and the names of the
    # unavailable components. See CRITERIA.md Score buckets: null score
    # means unscored, never low.
    ("score_partial", "REAL"),
    ("score_unavailable", "TEXT"),
    # Which prior put this name in front of the collector, and at what rank.
    # Kept beside the morning's measured numbers, never instead of them: the
    # pool is itself under evaluation and cannot be evaluated if the reason a
    # name was watched is not recorded next to what it went on to do.
    ("pool_source", "TEXT"),
    ("pool_tier", "INTEGER"),
    # Premarket volume over shares float, the volume measure that needs no
    # baseline, and the name of whichever measure actually scored the row.
    # Both are needed to read a score honestly: a null pm_rvol beside a real
    # score is a bug unless volume_measure_used says float rotation stood in,
    # and calibrating the two bands against each other later is impossible if
    # the rows do not record which band they were scored under.
    ("pm_float_rotation", "REAL"),
    ("volume_measure_used", "TEXT"),
    # WHAT THE MORNING ACTUALLY SAW, and what it turned that into. pm_rvol has
    # divided an ESTIMATE since 2026-08-21, and until these columns existed the
    # table recorded the ratio without either of its inputs, so no later pass
    # could tell a symbol on its own measured capture share from one on the
    # file wide default, or recover the observation the estimate was built on.
    ("pm_volume", "REAL"),
    ("pm_volume_estimated", "REAL"),
    ("pm_capture_share", "REAL"),
    ("pm_capture_basis", "TEXT"),
    # WHAT IT ACTUALLY WAS, written by night/true_volume.py from Alpaca's full
    # SIP tape once the session is over, beside the morning's numbers and never
    # over them, on the pm_high_true precedent above.
    #
    # _true does NOT mean one source here. [Backfill]'s pm_high_true, pm_low_true
    # and pm_vwap_true come from EODHD intraday; these four come from Alpaca. A
    # column suffix is not a provenance, so truth_source carries the vendor and
    # every query that mixes them has to look at it.
    ("pm_volume_true", "REAL"),
    ("pm_rvol_true", "REAL"),
    ("pm_float_rotation_true", "REAL"),
    ("true_baseline_median", "REAL"),
    ("true_baseline_sessions", "INTEGER"),
    ("true_bars", "INTEGER"),
    # Why the SHORT leg is null, on the day5_refused_reason precedent. Without
    # it a row refused for a corporate action left next_day_close null with no
    # reason, and the candidate query selects on exactly that null, so the row
    # came back every night and spent one end of day call each time to be
    # refused again. NULL here with a NULL close means the fill has not reached
    # the row; a reason means it reached it and would not measure across the
    # action.
    ("next_day_refused_reason", "TEXT"),
    # The window this was measured over, copied from the packet's
    # rvol_cutoff_hhmm rather than assumed, so a row says what it compared.
    ("true_window", "TEXT"),
    ("truth_source", "TEXT"),
    ("truth_at", "TEXT"),
    # Why a true value is null. NULL reason with a NULL value means the pass
    # has not reached this row; a reason means it reached it and could not.
    ("truth_reason", "TEXT"),
    # pm_volume / pm_volume_true, the share the socket ACTUALLY carried, which
    # is what [Collector] premarket_capture_rate asserts as one number for
    # every name. And pm_volume_estimated / pm_volume_true, how well the
    # morning's correction did, where 1.0 is exactly right. Different
    # questions; see CRITERIA [Truth] the two ratios this writes note.
    ("capture_observed", "REAL"),
    ("estimate_error", "REAL"),
    # The true volume over the COLLECTOR'S OWN window, 07:20 to the cutoff,
    # and that window's share of the whole premarket. capture_observed divides
    # by the first of these and not by pm_volume_true, because the socket
    # cannot see 04:00 to 07:20 at all: a share computed against the full
    # window would fold the collector's late start into what is meant to be a
    # measurement of the feed, and the two have different fixes.
    ("true_volume_socket_window", "REAL"),
    ("collector_window_share", "REAL"),
    # THE REFERENCE LEVELS AS THE WHOLE TAPE HAD THEM, written by
    # night/true_volume.py off the same Alpaca bars as the columns above.
    #
    # entry_ref and stop_ref are pm_high and pm_low, which are the COLLECTOR'S
    # RAW LIVE levels: the extremes of a socket sample that carried a median
    # 0.0296 of the tape over its own window. A sample understates a maximum
    # and overstates a minimum, so entry_ref sits BELOW the true premarket high
    # and stop_ref sits ABOVE the true premarket low.
    #
    # THE TWO BIASES DO NOT POINT THE SAME WAY, and saying they do would be the
    # easy mistake here. mfe_pct measures up from entry_ref, so too low an
    # entry_ref makes the favourable excursion look BIGGER than it was.
    # mae_pct measures down from stop_ref, so too high a stop_ref makes the
    # adverse excursion look DEEPER than it was. The record therefore flatters
    # its upside and overstates its downside at the same time, and the net
    # effect on any read of it is not signed in advance. It has to be measured,
    # which is what these columns are for.
    #
    # Beside, never over, on the pm_high_true precedent. The gap between the
    # two pairs is a measurement of the feed and the project needs it, so the
    # sampled pair is not corrected and not replaced.
    ("entry_ref_true", "REAL"),
    ("stop_ref_true", "REAL"),
    # The same two levels over the COLLECTOR'S OWN window, 07:20 to the cutoff,
    # for the same reason capture_observed sits beside collector_window_share.
    # The full window pair folds the collector's LATE START into a number that
    # would otherwise read as the sampling shortfall alone, and those are two
    # different shortfalls with two different fixes. Full against collector
    # window is what the 04:00 to 07:20 stretch costs; collector window against
    # the live level is the sampling, and only the second is a statement about
    # the socket. Null when the socket's window carried no bar, which
    # true_volume_socket_window above says independently.
    ("entry_ref_collector_window", "REAL"),
    ("stop_ref_collector_window", "REAL"),
    # Why the true pair is null. Separate from truth_reason, which is first
    # wins across the volume columns: sharing it would let a refused float
    # stand as the recorded explanation for a missing reference level.
    ("refs_true_reason", "TEXT"),
    # THE MORNING'S OWN FILL WARNING, written by scan at 08:45 from the
    # collector's bars, because the definitive check cannot run until the
    # session is over and Alpaca will serve it. A WARNING, never an approval:
    # over 54 rows it missed four of the ten levels the night went on to call
    # untradeable. See CRITERIA [Fill warning], which records both error rates.
    #
    # Kept beside the night's fill_plausible and never merged with it. The
    # morning's band is centred on pm_high and the night's on entry_ref_true,
    # which differ by a median 1.19 percent and by as much as 20.9, so on the
    # names that matter most they are not even the same band.
    ("pm_band_volume", "REAL"),
    ("pm_band_minutes", "INTEGER"),
    ("pm_band_notional", "REAL"),
    ("pm_band_state", "TEXT"),
    # The two excursions measured against the pair above rather than against
    # the collector's sampled one, written by night/fill_outcomes.py.
    #
    # DECLARED HERE rather than only in that module's widening tuple, which is
    # where they started. store.init did not then create them, so a database
    # the outcome fill had never run against was missing the columns entirely
    # and night/weekly_page.py's score section raised OperationalError reading
    # them. Every other _true column on this table is declared here; these are
    # not different.
    ("mfe_pct_true", "REAL"),
    ("mae_pct_true", "REAL"),
    # WHETHER entry_ref_true IS A PRICE ANYONE COULD HAVE TRANSACTED AT, which
    # is a different question from what the level was. On a name whose whole
    # premarket is a few hundred shares the level is a print rather than a
    # market, and every excursion measured from it is arithmetic about a price
    # that was never available.
    #
    # fill_band_volume is an UPPER BOUND and is not a measurement of volume at
    # the level: a one minute bar carries no distribution, so a minute that ran
    # from below up into the band contributes all of its volume while only some
    # of it transacted inside. fill_band_minutes is exact. fill_band_notional
    # is the volume at the level, which is the comparable one: this table holds
    # prices from 5.64 to 1,585 and a share count means different things at the
    # two ends. fill_band_pct is the band the row was judged under, carried per
    # row so a row says what it was measured by rather than inheriting whatever
    # the file says today.
    ("fill_band_volume", "REAL"),
    ("fill_band_minutes", "INTEGER"),
    ("fill_band_notional", "REAL"),
    ("fill_band_pct", "REAL"),
    # THREE STATE AND NEVER A BOOLEAN: 'plausible', 'implausible', or
    # 'unknown'. A boolean has no room for the third, and the third is the one
    # that matters, because a row the feed could not reach would otherwise read
    # as one that was checked and failed. The two are opposite facts and this
    # project has now confused them under four other names.
    ("fill_plausible", "TEXT"),
    ("fill_plausible_reason", "TEXT"),
)


# Columns added to paper_trades after it first shipped. init() widens an
# existing database with these, the same way _PICKS_LATER_COLUMNS does, so a
# ledger written before rule v2 existed is not dropped to gain its columns.
_PAPER_LATER_COLUMNS = (
    ("risk_notional_taken", "REAL"),
    ("sizing_mode", "TEXT"),
    ("minutes_to_trigger", "INTEGER"),
    ("minutes_to_peak", "INTEGER"),
    ("mfe_pct_held", "REAL"),
)


class TransactionHeldError(RuntimeError):
    """Raised when a network call is attempted with a write transaction open."""


class _TrackedConnection(sqlite3.Connection):
    """A connection the guard can hold weakly.

    sqlite3.Connection itself cannot be weak referenced, so connect() builds
    this subclass instead, which can. Behaviour is otherwise identical: the
    subclass exists only so a closed connection can drop out of the registry on
    its own rather than being leaked by it.
    """


# Every connection this module has handed out, weakly held so a closed or
# garbage collected one drops out on its own. This is the whole registry: no
# other code in this project calls sqlite3.connect, so anything talking to the
# database is in here.
_LIVE: "weakref.WeakSet[_TrackedConnection]" = weakref.WeakSet()


def open_transactions() -> list[sqlite3.Connection]:
    """Connections with a write transaction currently open.

    Read from sqlite3's own in_transaction, which is true only once a statement
    has actually begun a transaction. Nothing here consults a flag the calling
    code sets, because the failures this exists to catch are precisely the ones
    where the calling code did not know it was holding anything: three of the
    four sites found by audit looked innocent, and the fourth held its
    transaction behind a recursion where no lexical scan could see it.
    """
    return [connection for connection in list(_LIVE) if _in_transaction(connection)]


def _in_transaction(connection: sqlite3.Connection) -> bool:
    try:
        return bool(connection.in_transaction)
    except (sqlite3.ProgrammingError, ReferenceError):
        return False  # already closed


def assert_no_open_transaction(context: str) -> None:
    """Refuse to let a network call happen underneath an open transaction.

    A transaction spanning a request holds SQLite's write lock for the length
    of that request, so every other writer on the machine fails with "database
    is locked" for a reason that has nothing to do with it. It happened three
    times in three weeks and each local fix was followed by another instance
    somewhere else, which is what says the rule needs enforcing rather than
    auditing.

    The fix at every call site is the same shape: read, close, fetch, reopen,
    write.
    """
    held = open_transactions()
    if not held:
        return
    raise TransactionHeldError(
        f"{context} was attempted with {len(held)} open database transaction(s). "
        "A transaction must not span a network call: it holds the write lock "
        "for the length of the request and every other writer fails with "
        "'database is locked'. Restructure as read, close, fetch, then write. "
        "See conftest.py and the changelog entry for 2026-08-14."
    )


class LiveDatabaseUnderTestError(RuntimeError):
    """Raised when test code opens the real premarketdesk.db."""


def _real_data_root() -> Path:
    """The live data directory, derived rather than captured.

    NOT config.DATA_DIR, which the sandbox rebinds, and NOT a value captured at
    import, which was the first attempt and was wrong in a way worth keeping on
    the record: under run_tests this module is imported AFTER conftest has
    already pointed config.DATA_DIR at the sandbox copy, so the captured root
    WAS the sandbox and the guard refused every legitimate connection. Six
    suites went red at once.

    config.PROJECT_ROOT is derived from this file's own location and is the one
    name conftest never rebinds, so deriving from it is correct whatever the
    import order turns out to be.
    """
    return (config.PROJECT_ROOT / "data").resolve()


def _test_module_is_loaded() -> str | None:
    """The name of a loaded tests module, or None. Cheap enough to call often.

    Import graph rather than a flag anybody has to remember to set. A claim
    called directly from a REPL has tests.test_regressions in sys.modules just
    as surely as one called by run_tests, and that is precisely the case with
    no other protection on it.
    """
    for name in sys.modules:
        if name == "tests" or name.startswith("tests."):
            return name
    return None


def guard_live_database(path: Path) -> None:
    """Refuse to open the real database while test code is loaded.

    THE GAP THIS CLOSES. conftest rebinds config.DB_PATH for every claim, so
    inside run_tests nothing can reach the live file. Call the same claim
    directly, which is the normal way to debug one, and the rebinding never
    happens. On 2026-08-21 claim 73 was written that way: it rebound DATA_DIR
    and RUNS_DIR, not DB_PATH, and while it was being checked by hand its two
    fixture rows landed in the live picks table and its fake probe overwrote a
    real session's truth columns with nulls.

    Isolation was a property of the RUNNER and not of the code. It is now a
    property of the code: the refusal is here, at the one function every
    connection goes through, so it holds however the claim was invoked.

    Refuses rather than redirects. A silent redirect would make a claim pass
    against a database it did not mean to open, which trades a loud failure for
    a quiet one.
    """
    if not _test_module_is_loaded():
        return
    try:
        target = Path(path).resolve()
    except OSError:
        return
    if target.parent != _real_data_root():
        return
    raise LiveDatabaseUnderTestError(
        f"refusing to open {target}: it is the LIVE database and "
        f"{_test_module_is_loaded()} is loaded. A test that reaches the real "
        "picks table can destroy the record it exists to protect, which is "
        "what happened on 2026-08-21. Use tests.conftest.isolated_store(), or "
        "rebind config.DB_PATH, before opening a connection."
    )


# THE NIGHT'S COLUMNS ON picks, declared here beside the morning's. Until
# 2026-09-02 fill_outcomes and backfill_premarket each declared their own
# tuple and widened the table themselves, so a fresh database held about 85
# picks columns declared across four files, and store.py:291 records the
# night the weekly page raised on a column only fill_outcomes knew about. The
# night modules alias these; the declaration lives in one place.
OUTCOME_COLUMNS = (
    ("next_day_open", "REAL"),
    ("next_day_high", "REAL"),
    ("next_day_low", "REAL"),
    ("next_day_close", "REAL"),
    ("day5_close", "REAL"),
    # Why the fifth session was refused, on the rows where it was. A null
    # day5_close is also how a fill that is simply not due yet looks, and until
    # 2026-08-20 the units guard in fill_outcomes had no way to say which of
    # the two a given null was. See the long leg in fill_outcomes.fill().
    ("day5_refused_reason", "TEXT"),
    ("pm_high_broke_next_day", "INTEGER"),
    ("mfe_pct", "REAL"),
    ("mae_pct", "REAL"),
    # mfe_pct_true and mae_pct_true are NOT in this tuple. They are declared
    # beside the other _true columns in _PICKS_LATER_COLUMNS, so init creates
    # them and a reader that has never run the outcome fill still finds them.
    # Declaring a column in two places is one drift away from two declarations.
    ("outcomes_filled_at", "TEXT"),
    # THE PICK'S OWN SESSION, open to close, for EVERY pick and not only the
    # booked ones. Added 2026-09-02 (IMPROVEMENT_PLAN 5.3): every outcome
    # above is measured against a reference level, the premarket high, and
    # SCORE_INVERSION.md's 2026-09-02 amendment records that the level sits
    # further from the next open in proportion to the gap, so a reference free
    # outcome is needed beside them. From the same end of day bar the fill
    # already fetches, at no extra call. Null for rows filled before the
    # columns existed until fill_pick_day backfills them, never overwritten.
    ("pick_day_open", "REAL"),
    ("pick_day_high", "REAL"),
    ("pick_day_low", "REAL"),
    ("pick_day_close", "REAL"),
    # Why the pick's own session is null, on the day5_refused_reason
    # precedent. fill_pick_day selects on pick_day_close IS NULL, and a row
    # whose pick date bar the vendor's history simply never serves came back
    # every night and spent one end of day call to be told so again. NULL
    # here with a NULL close means the backfill has not reached the row; a
    # reason means it reached it and the vendor had no bar for that date.
    ("pick_day_refused_reason", "TEXT"),
)

TRUE_COLUMNS = (
    ("pm_high_true", "REAL"),
    ("pm_low_true", "REAL"),
    ("pm_vwap_true", "REAL"),
    ("pm_true_bars", "INTEGER"),
    # The percentage by which the true high undercuts the live high. NULL
    # means the backfill has not checked this row (or could not, both highs
    # are needed); 0.0 means checked and clean. A magnitude, not a boolean:
    # feed noise and bad bars both trip a boolean, and then nobody can tell
    # them apart. Queries counting clean rows must test = 0.0, never IS NULL.
    ("pm_source_disagreement", "REAL"),
    # The same three values over the COLLECTOR'S OWN window, 07:20 to the scan
    # cutoff, from the same bars in the same pass at no extra call. Without
    # these the difference between live and true is one number covering three
    # causes; with them it decomposes. See backfill_premarket's docstring.
    ("pm_high_collector_window", "REAL"),
    ("pm_low_collector_window", "REAL"),
    ("pm_vwap_collector_window", "REAL"),
    ("pm_collector_window_bars", "INTEGER"),
    # What that window actually was on this row, never assumed by a reader.
    # The morning's cutoff snaps to [Scan] run_time only inside
    # rvol_cutoff_snap_minutes, so a rerun genuinely has a different clock.
    ("pm_collector_window", "TEXT"),
    ("backfilled_at", "TEXT"),
)

# The schema's own version, stamped into the database the first time init
# runs against it and read back after. One row per version applied, so a
# migration that has run once is not run again: the source='test' backfill in
# init ran a full table scan on every connection until 2026-09-02, because
# nothing recorded that it had already run.
SCHEMA_VERSION = 1
_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    guard_live_database(config.DB_PATH)
    config.ensure_dirs()
    connection = sqlite3.connect(config.DB_PATH, timeout=30, factory=_TrackedConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _LIVE.add(connection)
    return connection


@contextlib.contextmanager
def session() -> Iterator[sqlite3.Connection]:
    """A connection that commits on success, rolls back on error, and CLOSES.

    sqlite3's own context manager is a transaction manager, not a closing
    one: `with connect() as c:` commits or rolls back and leaves the
    connection open, which reads as correct and is not. A lingering WAL
    handle on Windows can block file operations for a later job. Every
    script-lifetime use goes through here instead.
    """
    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init(connection: sqlite3.Connection | None = None) -> None:
    """Create anything missing, widen anything old. Safe to call on every run."""
    owned = connection is None
    connection = connection or connect()
    try:
        connection.executescript(_SCHEMA)
        connection.executescript(_SCHEMA_VERSION_TABLE)
        ensure_columns(connection, "picks", _PICKS_LATER_COLUMNS)
        ensure_columns(connection, "picks", OUTCOME_COLUMNS)
        ensure_columns(connection, "picks", TRUE_COLUMNS)
        ensure_columns(connection, "paper_trades", _PAPER_LATER_COLUMNS)
        applied = {row[0] for row in
                   connection.execute("SELECT version FROM schema_version").fetchall()}
        if SCHEMA_VERSION not in applied:
            # Any row without a source predates the source column, and
            # everything written before it existed was test data. Writers
            # always set source, so this can never touch a post migration row.
            # Run once per database, recorded, rather than on every connection.
            connection.execute("UPDATE picks SET source='test' WHERE source IS NULL")
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, "
                "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))", (SCHEMA_VERSION,))
        connection.commit()
    finally:
        if owned:
            connection.close()


def ensure_columns(
    connection: sqlite3.Connection, table: str, columns: Iterable[tuple[str, str]]
) -> list[str]:
    """Add any missing columns to an existing table. Returns what it added.

    Later checkpoints widen the picks table. This lets them do so without
    dropping a database that already holds outcome history.

    table and column names are interpolated into the SQL and must be code
    literals, never data; anything failing the identifier check raises.
    """
    _require_identifier(table)
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    added: list[str] = []
    for name, declaration in columns:
        _require_identifier(name)
        if name in existing:
            continue
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        added.append(name)
    if added:
        connection.commit()
    return added


def upsert(
    connection: sqlite3.Connection,
    table: str,
    key_columns: list[str],
    values: dict[str, Any],
) -> None:
    """Insert or update on the natural key. This is what makes re-runs safe.

    table, key column and value column names are interpolated into the SQL
    and must be code literals, never data; anything failing the identifier
    check raises before touching the database.
    """
    _require_identifier(table)
    for name in list(values) + list(key_columns):
        _require_identifier(name)
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in key_columns)
    conflict = ", ".join(key_columns)
    statement = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT({conflict}) DO UPDATE SET {updates}"
        if updates
        else f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    )
    connection.execute(statement, [values[c] for c in columns])


def _self_check() -> int:
    init()
    with session() as connection:
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
    print(f"database  {config.DB_PATH}")
    print(f"tables    {', '.join(tables) or 'none'}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
