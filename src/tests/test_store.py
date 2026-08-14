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

import pathlib
import shutil
import sqlite3
import sys
import tempfile

from core import store


def _is_closed(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def main() -> int:
    failures: list[str] = []

    # Against a throwaway database, never the live one. This test writes, and
    # writing to data/premarketdesk.db means it fails with "database is locked"
    # whenever a real job holds a write transaction, which is a property of the
    # machine rather than of the code under test. It also means a test could
    # corrupt the outcome history. Same reasoning as the runs/ sandbox in
    # test_scrub.py.
    from core import config

    real_db = config.DB_PATH
    sandbox = tempfile.mkdtemp(prefix="premarketdesk-test-store-")
    config.DB_PATH = pathlib.Path(sandbox) / "test.db"
    try:
        return _run(failures)
    finally:
        config.DB_PATH = real_db
        shutil.rmtree(sandbox, ignore_errors=True)


def _run(failures: list[str]) -> int:

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
