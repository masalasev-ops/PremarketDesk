"""Regression test for the storage helpers.

Run it directly: `python src\\test_store.py`, exit 0 on pass.

Two claims, both required:
  1. store.session() actually closes its connection on exit, success and
     failure alike. sqlite3's own context manager only manages the
     transaction and leaves the connection open, which is the trap the
     helper exists to remove.
  2. store.ensure_columns and store.upsert refuse table and column names
     that are not plain SQL identifiers, because those names are
     interpolated into SQL text and must be code literals, never data.
"""

from __future__ import annotations

import sqlite3
import sys

import store


def _is_closed(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def main() -> int:
    failures: list[str] = []

    # Claim 1a: closed after a clean exit, with the write committed.
    with store.session() as connection:
        store.init(connection)
        kept = connection
    if not _is_closed(kept):
        failures.append("session() left the connection open after a clean exit")

    # Claim 1b: closed after an exception too.
    try:
        with store.session() as connection:
            kept = connection
            raise RuntimeError("deliberate")
    except RuntimeError:
        pass
    if not _is_closed(kept):
        failures.append("session() left the connection open after an exception")

    # Claim 2: non identifiers raise before any SQL executes.
    with store.session() as connection:
        store.init(connection)
        bad_names = ["picks; DROP TABLE picks", "bad-name", "a b", "", "1st", 'x"y']
        for bad in bad_names:
            try:
                store.ensure_columns(connection, bad, [("fine", "TEXT")])
                failures.append(f"ensure_columns accepted table {bad!r}")
            except ValueError:
                pass
            try:
                store.ensure_columns(connection, "picks", [(bad, "TEXT")])
                failures.append(f"ensure_columns accepted column {bad!r}")
            except ValueError:
                pass
            try:
                store.upsert(connection, "picks", ["date", "ticker"],
                             {"date": "2099-01-01", "ticker": "T", bad: 1})
                failures.append(f"upsert accepted column {bad!r}")
            except ValueError:
                pass
        try:
            store.upsert(connection, bad_names[0], ["date"], {"date": "x"})
            failures.append("upsert accepted an injection shaped table name")
        except ValueError:
            pass

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  session() closes on exit and on error, and non identifier "
          "table or column names raise before reaching SQL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
