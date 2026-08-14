"""Regression test for the vintage assertion.

Run directly: `python src\\test_vintage.py`, exit 0 on pass. Makes no network
calls: the exchange calendar is stubbed to a plain weekday rule so the test is
hermetic and gives the same answer on any machine. The real gate marker is
never touched; enforce() is pointed at a temporary file.

Two claims:
  1. The packet from the 2026-08-14 run, the one that completed clean and
     published the previous session, is refused. Checks (a), (b) and (d) all
     fire, and the six rows whose prior_high sits below their own prior_close
     are each named in the marker file that enforce() writes.
  2. A synthetic packet whose timestamps really are from today passes all four
     checks and writes no marker.
"""

from __future__ import annotations

import datetime as dt
import json
import sys

import config
import ettime
import market_today
import verify_morning
import vintage

PACKET_PATH = config.RUNS_DIR / "2026-08-14" / "packet.json"

# The six candidates whose prior_high was below their own prior_close, which
# cannot happen inside one OHLC bar and is the cheapest possible proof that the
# two fields came from different sessions.
IMPOSSIBLE = ["CLBT.US", "SECZ.US", "LFTO.US", "REZI.US", "TPR.US", "BSP.US"]


def _clean_packet() -> dict:
    """A packet whose every timestamp is honestly from the session it claims."""
    return {
        "session_date": "2026-08-14",
        "candidates": [
            {
                "symbol": "WDAY.US",
                "price": 206.06,
                "price_time": "2026-08-14T08:43:00-04:00",
                "prior_close": 206.45,
                "prior_high": 227.49,
                "prior_session_date": "2026-08-13",
            },
            {
                # Dropped for no coverage: unpriced, so (a) has nothing to say
                # about it and (b) and (c) still hold it to its history.
                "symbol": "MH.US",
                "price": None,
                "price_time": None,
                "prior_close": 13.55,
                "prior_high": 13.57,
                "prior_session_date": "2026-08-13",
            },
        ],
        "market_snapshot": [
            {"label": "spy", "symbol": "SPY.US", "last": 778.73,
             "as_of": "2026-08-14T08:44:00-04:00", "source": "collector",
             "prior_session_only": False},
            {"label": "10y", "symbol": "US10Y.GBOND", "last": 4.664,
             "as_of": "2026-08-13", "source": "eod", "prior_session_only": True},
        ],
    }


def main() -> int:
    failures: list[str] = []

    # Hermetic calendar: weekdays are open, weekends are not. 2026-08-13 and
    # 2026-08-14 are a Thursday and a Friday, so the prior session of the 14th
    # is the 13th under this rule exactly as it is under the real one.
    market_today.is_trading_day = lambda day: (day.weekday() < 5, "stubbed")

    prior = vintage.previous_trading_session(dt.date(2026, 8, 17))
    if prior != dt.date(2026, 8, 14):
        failures.append(f"the session before Monday 2026-08-17 came back as {prior}, "
                        "expected Friday 2026-08-14")

    # Claim 1: the real failing packet is refused.
    if not PACKET_PATH.is_file():
        print(f"SKIP  the 2026-08-14 packet is not on this machine ({PACKET_PATH})")
        return 0
    payload = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    violations = vintage.check_packet(payload)
    fired = {v["check"] for v in violations}
    for check_id in ("a", "b", "d"):
        if check_id not in fired:
            failures.append(f"check ({check_id}) did not fire on the 2026-08-14 packet")
    if "c" in fired:
        failures.append("check (c) fired, but that packet's prior_session_date was "
                        "correctly 2026-08-13, so it should not have")

    impossible_rows = sorted(v["row"] for v in violations if v["check"] == "b")
    if impossible_rows != sorted(IMPOSSIBLE):
        failures.append(f"check (b) named {impossible_rows}, expected {sorted(IMPOSSIBLE)}")

    # enforce() must refuse, and the marker it writes must name those rows.
    original_marker = verify_morning.UNVERIFIED_MARKER
    temporary = config.RUNS_DIR / "2026-08-14" / "test_vintage_UNVERIFIED"
    verify_morning.UNVERIFIED_MARKER = temporary
    try:
        temporary.unlink(missing_ok=True)
        try:
            vintage.enforce(payload)
            failures.append("enforce() accepted the 2026-08-14 packet")
        except vintage.StaleDataError:
            pass
        if not temporary.exists():
            failures.append("enforce() wrote no marker file")
        else:
            marker = temporary.read_text(encoding="utf-8")
            for symbol in IMPOSSIBLE:
                if symbol not in marker:
                    failures.append(f"the marker file does not name {symbol}")

        # Claim 2: a packet that really is from today passes, and writes nothing.
        temporary.unlink(missing_ok=True)
        clean = vintage.check_packet(_clean_packet())
        if clean:
            failures.append(f"the clean packet produced violations: {clean}")
        try:
            vintage.enforce(_clean_packet())
        except vintage.StaleDataError:
            failures.append("enforce() refused the clean packet")
        if temporary.exists():
            failures.append("enforce() wrote a marker for a clean packet")
    finally:
        temporary.unlink(missing_ok=True)
        verify_morning.UNVERIFIED_MARKER = original_marker

    if original_marker.exists():
        print(f"  the real gate marker is untouched at {original_marker}")

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print(f"PASS  the 2026-08-14 packet is refused on checks {sorted(fired)} with all "
          f"{len(IMPOSSIBLE)} impossible rows named in the marker, and a packet whose "
          "timestamps are from today passes all four")
    return 0


if __name__ == "__main__":
    sys.exit(main())
