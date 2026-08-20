"""Regression test for credential scrubbing at the HTTP chokepoint.

Run it directly: `python src\\test_scrub.py`, exit 0 on pass. Makes no
network calls: the session is stubbed to fail the way a real network
failure fails, with the tokenised URL quoted in the exception text.

Two claims, both required:
  1. eodhd._request never lets an error string leave the chokepoint with a
     credential in it: the returned error carries the mask, not the token.
  2. A packet built through a forced network failure names the failure in
     gaps_to_fill with the token masked, and a scan of the serialized
     packet for the raw token returns nothing.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile

import requests

from core import config
from core import eodhd
from morning import scan


class _ExplodingSession:
    """Raises the way urllib3 really does, tokenised URL in the message."""

    def __init__(self, token: str) -> None:
        self._message = (
            "HTTPSConnectionPool(host='eodhd.com', port=443): Max retries "
            f"exceeded with url: /api/eod/AAPL.US?api_token={token}&fmt=json "
            "(Caused by NameResolutionError)"
        )

    def get(self, url, params=None, timeout=None):
        raise requests.ConnectionError(self._message)


def main() -> int:
    try:
        token = config.eodhd_token()
    except config.ConfigError:
        print("PASS  no token is configured, so there is nothing to leak")
        return 0

    failures: list[str] = []
    masked = config.mask(token)

    # Claim 1: the chokepoint scrubs. The ledger's retry budget is
    # pre-spent so the stubbed failure is not retried with real backoff
    # sleeps; retry behavior has its own coverage elsewhere.
    ledger = eodhd.CallLedger()
    ledger.retries = eodhd.RETRY_BUDGET_PER_RUN
    client = eodhd.EodhdClient(token=token, ledger=ledger)
    client._session = _ExplodingSession(token)
    data, error = client.eod("AAPL.US")
    if data is not None or not error:
        failures.append("the stubbed failure should have produced an error")
    else:
        if token in error:
            failures.append("the raw token survived into the returned error")
        if masked not in error:
            failures.append(f"the mask {masked!r} is missing from the returned error")
    if any(token in note for note in ledger.errors):
        failures.append("the raw token survived into the ledger's error notes")

    # Claim 2: a whole packet built through the failure carries no token.
    #
    # build_packet snapshots the collector file into runs/<today>/, so this
    # runs against a throwaway runs directory. Without that it overwrites the
    # frozen premarket_snapshot.jsonl of whatever real run happened today,
    # which is the only record of what that morning's scan actually saw. It
    # did exactly that on 2026-08-14 before this guard was added.
    stub = eodhd.EodhdClient(token=token, ledger=eodhd.LEDGER)
    stub._session = _ExplodingSession(token)
    eodhd.LEDGER.retries = eodhd.RETRY_BUDGET_PER_RUN
    eodhd._default_client = stub
    real_runs_dir = config.RUNS_DIR
    sandbox = tempfile.mkdtemp(prefix="premarketdesk-test-scrub-")
    config.RUNS_DIR = pathlib.Path(sandbox)
    try:
        payload = scan.build_packet()
    finally:
        eodhd._default_client = None
        config.RUNS_DIR = real_runs_dir
        shutil.rmtree(sandbox, ignore_errors=True)
    serialized = json.dumps(payload)
    if token in serialized:
        failures.append("the raw token appears in the serialized packet")
    gaps = payload.get("gaps_to_fill", [])
    if not any(masked in gap for gap in gaps):
        failures.append("no gaps_to_fill entry names the failure with the mask")

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  a forced network failure leaves the chokepoint masked, and the "
          "packet built through it names the failure without the token")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
