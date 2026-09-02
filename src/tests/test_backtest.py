"""Regression tests for the pool backtest harness.

Run directly: `python -m tests.test_backtest` with PYTHONPATH set to src/,
exit 0 on pass.

The harness is the instrument that decides the tier ordering, so the property
that matters most is that its evaluate stage is reproducible: same cache, same
answer, every time, with nothing fetched in between. A harness that reached the
network while evaluating would make each ordering comparison a measurement of
two different worlds.

Claims:
  1. The evaluate stage makes zero network calls. Asserted by making any HTTP
     attempt raise, then evaluating a synthetic cache to completion.
  2. Null metrics sort last within their tier rather than as zero.
  3. A tier floor gives each tier its minimum before the remainder fills by
     overall rank.
  4. Where the real cache is present, 2026-08-13 reproduces the published
     figures from cache alone.
"""

from __future__ import annotations

from tests.conftest import run_claim

import json
import shutil
import sys
import tempfile
from pathlib import Path

from research import backtest_pool
from selection import discover
from core import eodhd

PUBLISHED_0813 = {
    "gapped": 99, "pool_held": 72, "discovery_recall_all_gappers": 0.7273,
    "subscribed_held": 28, "subscribed_recall_all_gappers": 0.2828,
}


class _Tripwire(Exception):
    """Raised by anything that tries to reach the network during evaluate."""


def _arm_tripwire() -> list:
    """Make every outbound path raise, and return the originals for restoring."""
    import requests

    saved = [
        (eodhd.EodhdClient, "_request", eodhd.EodhdClient._request),
        (requests.Session, "request", requests.Session.request),
        (requests.Session, "get", requests.Session.get),
        (requests.Session, "post", requests.Session.post),
    ]

    def explode(*args, **kwargs):
        raise _Tripwire("the evaluate stage attempted a network call")

    for owner, name, _original in saved:
        setattr(owner, name, explode)
    return saved


def _disarm(saved: list) -> None:
    for owner, name, original in saved:
        setattr(owner, name, original)


def _synthetic_cache(directory: Path) -> None:
    """Two sessions with three names, enough to exercise tiers and the cap."""
    for date, gappers in (("2026-01-05", ["EARN.US"]), ("2026-01-06", ["NEWSY.US"])):
        session = directory / date
        session.mkdir(parents=True, exist_ok=True)
        (session / "inputs.json").write_text(json.dumps({
            "session_date": date,
            # screen_passed reads the end of day cache for these two days. No
            # such cache exists for a synthetic session, so it returns zero,
            # which is the point: the offline claim must hold even when a
            # metric has nothing to work with.
            "prior_session": "2026-01-02",
            "earlier_session": "2025-12-31",
            "run_clock": f"{date}T07:15:00-05:00",
            "earnings": {"status": discover.FETCHED,
                         "names": {"EARN.US": {"timing": "BeforeMarket"}}},
            "news": {"status": discover.FETCHED,
                     "names": {"NEWSY.US": {"newest_item_at": f"{date}T06:00:00-05:00"},
                               "QUIET.US": {"newest_item_at": f"{date}T06:00:00-05:00"}}},
            "movers": {"status": discover.FETCHED, "names": {}},
            "prior_closes": {},
        }), encoding="utf-8")
        (session / "outcome.json").write_text(json.dumps({
            "session_date": date,
            "gappers": {
                symbol: {"symbol": symbol, "gap_at_open_pct": 9.0,
                         "open": 10.0, "prior_close": 9.0, "volume": 1.0}
                for symbol in gappers
            },
        }), encoding="utf-8")


def claim_one(failures: list[str]) -> None:
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-backtest-"))
    original_dir = backtest_pool.SESSION_DIR
    backtest_pool.SESSION_DIR = sandbox
    metrics = {
        "EARN.US": {"avg_dollar_volume_20d": 1e6, "gap_propensity": 0.2,
                    "median_abs_gap_pct": 5.0, "atr_pct_20d": 3.0},
        "NEWSY.US": {"avg_dollar_volume_20d": 5e6, "gap_propensity": 0.1,
                     "median_abs_gap_pct": 4.0, "atr_pct_20d": 2.0},
        "QUIET.US": {"avg_dollar_volume_20d": 9e9, "gap_propensity": 0.0,
                     "median_abs_gap_pct": 0.0, "atr_pct_20d": 0.5},
    }
    _synthetic_cache(sandbox)
    saved = _arm_tripwire()
    try:
        sessions = backtest_pool.cached_sessions()
        if len(sessions) != 2:
            failures.append(f"synthetic cache listed {sessions}")
        for name in backtest_pool.ORDERINGS:
            for session in sessions:
                backtest_pool.evaluate_session(
                    session, metrics, backtest_pool.ORDERINGS[name], cap=2, tier_floor=0
                )
    except _Tripwire as exc:
        failures.append(f"evaluate reached the network: {exc}")
    except Exception as exc:  # noqa: BLE001  any other failure is still a failure
        failures.append(f"evaluate raised {type(exc).__name__}: {exc}")
    finally:
        _disarm(saved)
        backtest_pool.SESSION_DIR = original_dir
        shutil.rmtree(sandbox, ignore_errors=True)
    print("  claim 1 evaluate completed for every ordering with the network armed to raise")


def claim_two(failures: list[str]) -> None:
    pool = [
        {"symbol": "MEASURED.US", "pool_tier": 2},
        {"symbol": "NULLY.US", "pool_tier": 2},
        {"symbol": "HIGH.US", "pool_tier": 2},
    ]
    metrics = {
        "MEASURED.US": {"gap_propensity": 0.0},     # measured zero
        "NULLY.US": {"gap_propensity": None},       # never measured
        "HIGH.US": {"gap_propensity": 0.4},
    }
    ordered = backtest_pool.order_pool(pool, metrics, {"key": "gap_propensity"})
    order = [row["symbol"] for row in ordered]
    if order != ["HIGH.US", "MEASURED.US", "NULLY.US"]:
        failures.append(f"null sorted as zero: got {order}")
    print(f"  claim 2 nulls sort last, not as zero: {order}")


def claim_three(failures: list[str]) -> None:
    rows = [{"symbol": f"T1_{i}", "pool_tier": 1} for i in range(10)]
    rows += [{"symbol": f"T2_{i}", "pool_tier": 2} for i in range(10)]
    rows += [{"symbol": f"T4_{i}", "pool_tier": 4} for i in range(10)]

    strict = backtest_pool.apply_cap(rows, cap=12, tier_floor=0)
    strict_tiers = sorted({r["pool_tier"] for r in strict if r["subscribed"]})
    if strict_tiers != [1, 2]:
        failures.append(f"strict priority subscribed tiers {strict_tiers}, expected [1, 2]")

    floored = backtest_pool.apply_cap(rows, cap=12, tier_floor=2)
    by_tier: dict[int, int] = {}
    for row in floored:
        if row["subscribed"]:
            by_tier[row["pool_tier"]] = by_tier.get(row["pool_tier"], 0) + 1
    if sum(by_tier.values()) != 12:
        failures.append(f"floor cap subscribed {sum(by_tier.values())}, expected 12")
    for tier in (1, 2, 4):
        if by_tier.get(tier, 0) < 2:
            failures.append(f"tier {tier} got {by_tier.get(tier, 0)} slots, floor was 2")
    print(f"  claim 3 floor 2 spreads the cap across tiers {dict(sorted(by_tier.items()))}, "
          f"strict priority gives {strict_tiers}")


def claim_four(failures: list[str]) -> None:
    session = "2026-08-13"
    if session not in backtest_pool.cached_sessions():
        print(f"  claim 4 SKIPPED, {session} is not in the cache")
        return
    metrics = backtest_pool.load_metrics()
    result = backtest_pool.evaluate_session(
        session, metrics, backtest_pool.ORDERINGS["A"], cap=42, tier_floor=0
    )
    for key, expected in PUBLISHED_0813.items():
        actual = result[key]
        if isinstance(expected, float):
            if actual is None or abs(actual - expected) > 0.002:
                failures.append(f"{session} {key} is {actual}, published {expected}")
        elif actual != expected:
            failures.append(f"{session} {key} is {actual}, published {expected}")
    print(f"  claim 4 {session} from cache: {result['gapped']} gapped, pool "
          f"{result['pool_held']} at {result['discovery_recall_all_gappers']}, subscribed "
          f"{result['subscribed_held']} at {result['subscribed_recall_all_gappers']}")


def main() -> int:
    failures: list[str] = []
    run_claim(failures, claim_one, failures)
    run_claim(failures, claim_two, failures)
    run_claim(failures, claim_three, failures)
    run_claim(failures, claim_four, failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  the evaluate stage is offline and reproducible, nulls sort last, "
          "and tier floors spread the cap")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
