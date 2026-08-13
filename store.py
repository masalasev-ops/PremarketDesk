"""SQLite storage.

One database file, opened the same way everywhere, with the schema created on
demand so no script depends on another having run first.

Two habits worth keeping. Tables carry natural primary keys, not autoincrement
ids, so re-running a day updates its rows instead of quietly accumulating a
second copy. And every write path uses an upsert, so idempotency is a property
of the schema rather than something each script has to remember.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS baseline (
    ticker        TEXT NOT NULL,
    cutoff_hhmm   TEXT NOT NULL,
    median_volume REAL,
    sessions_used INTEGER NOT NULL DEFAULT 0,
    computed_at   TEXT NOT NULL,
    PRIMARY KEY (ticker, cutoff_hhmm)
);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    connection = sqlite3.connect(config.DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init(connection: sqlite3.Connection | None = None) -> None:
    """Create anything missing. Safe to call on every run."""
    owned = connection is None
    connection = connection or connect()
    try:
        connection.executescript(_SCHEMA)
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
    """
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    added: list[str] = []
    for name, declaration in columns:
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
    """Insert or update on the natural key. This is what makes re-runs safe."""
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
    with connect() as connection:
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
