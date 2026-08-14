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
import weakref
from typing import Any, Iterable, Iterator

import config

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
"""

# Columns added after the first schema shipped. init() widens existing
# databases with these so no script depends on another having migrated first.
_PICKS_LATER_COLUMNS = (
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


def connect() -> sqlite3.Connection:
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
        ensure_columns(connection, "picks", _PICKS_LATER_COLUMNS)
        # Any row without a source predates the source column, and everything
        # written before it existed was test data. Writers always set source,
        # so this can never touch a post migration row.
        connection.execute("UPDATE picks SET source='test' WHERE source IS NULL")
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
