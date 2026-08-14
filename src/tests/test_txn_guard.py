"""Regression test for the no-transaction-across-a-network-call guard.

Run directly: `python src\\test_txn_guard.py`, exit 0 on pass. Makes no real
network calls: the session is stubbed to fail immediately, which is enough
because the guard runs before the request is issued.

Three claims:
  1. A request attempted with a write transaction open raises, naming the
     endpoint.
  2. The guard reads sqlite3's connection state, not a flag the caller sets:
     an open CONNECTION with no write on it is not an open transaction and
     does not trip it, and the same connection does trip it the moment a write
     begins one.
  3. The whole morning chain runs under the guard without tripping it, and the
     guard is genuinely exercised rather than merely absent, which is checked
     by counting the calls it inspected.
"""

from __future__ import annotations

import sys

import requests

from core import config
from core import eodhd
from morning import scan
from core import store


class _DeadSession:
    """Fails immediately. The guard runs before this is ever reached."""

    def get(self, url, params=None, timeout=None):
        raise requests.ConnectionError("stubbed, no network in this test")


def _client() -> eodhd.EodhdClient:
    ledger = eodhd.CallLedger()
    ledger.retries = eodhd.RETRY_BUDGET_PER_RUN  # no backoff sleeps
    client = eodhd.EodhdClient(token=config.eodhd_token(), ledger=ledger)
    client._session = _DeadSession()
    return client


def claim_one(failures: list[str]) -> None:
    client = _client()
    with store.session() as connection:
        store.init(connection)
        # A write, which is what actually begins a transaction in sqlite3.
        connection.execute(
            "INSERT OR REPLACE INTO picks (date, ticker, source) VALUES (?, ?, ?)",
            ("1970-01-01", "GUARD.TEST", "test"),
        )
        if not connection.in_transaction:
            failures.append("the fixture failed to open a transaction at all")
        try:
            client.eod("AAPL.US")
        except store.TransactionHeldError as exc:
            if "eod" not in str(exc):
                failures.append(f"the guard did not name the endpoint: {exc}")
        else:
            failures.append("a request went out with a transaction open")
        connection.rollback()
    print("  claim 1 a request under an open transaction raises, naming the endpoint")


def claim_two(failures: list[str]) -> None:
    client = _client()
    # An open connection that has only read. Not a transaction, must not trip.
    with store.session() as connection:
        store.init(connection)
        connection.execute("SELECT COUNT(*) FROM picks").fetchone()
        if store.open_transactions():
            failures.append("a read-only connection was reported as a transaction")
        try:
            client.eod("AAPL.US")
        except store.TransactionHeldError:
            failures.append("the guard tripped on a connection with no write on it")

        # Now write, and the same connection must trip it.
        connection.execute(
            "INSERT OR REPLACE INTO picks (date, ticker, source) VALUES (?, ?, ?)",
            ("1970-01-01", "GUARD.TEST", "test"),
        )
        if not store.open_transactions():
            failures.append("a written-to connection was not reported as a transaction")
        connection.rollback()
    print("  claim 2 the guard follows sqlite3's in_transaction, not a caller flag")


def claim_three(failures: list[str]) -> None:
    import pathlib
    import shutil
    import tempfile

    inspected: list[str] = []
    real_assert = store.assert_no_open_transaction

    def counting_assert(context: str) -> None:
        inspected.append(context)
        real_assert(context)

    store.assert_no_open_transaction = counting_assert
    stub = eodhd.EodhdClient(token=config.eodhd_token(), ledger=eodhd.LEDGER)
    stub._session = _DeadSession()
    eodhd.LEDGER.retries = eodhd.RETRY_BUDGET_PER_RUN
    eodhd._default_client = stub

    real_runs = config.RUNS_DIR
    sandbox = tempfile.mkdtemp(prefix="premarketdesk-guard-")
    config.RUNS_DIR = pathlib.Path(sandbox)
    try:
        scan.build_packet()
    except store.TransactionHeldError as exc:
        failures.append(f"the morning chain tripped the guard: {exc}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"the morning chain raised {type(exc).__name__}: {exc}")
    finally:
        store.assert_no_open_transaction = real_assert
        eodhd._default_client = None
        config.RUNS_DIR = real_runs
        shutil.rmtree(sandbox, ignore_errors=True)

    if not inspected:
        failures.append("the guard was never reached, so the chain proves nothing")
    print(f"  claim 3 the morning chain made {len(inspected)} guarded request(s) "
          "and tripped none")


def main() -> int:
    failures: list[str] = []
    try:
        config.eodhd_token()
    except config.ConfigError:
        print("SKIP  no token is configured, so the client cannot be built")
        return 0

    claim_one(failures)
    claim_two(failures)
    claim_three(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  no request may be issued under an open transaction, the guard "
          "reads connection state, and the morning chain runs clean under it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
