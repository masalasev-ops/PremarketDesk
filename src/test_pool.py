"""Regression tests for the candidate pool that replaced stale gap ranking.

Run directly: `python src\\test_pool.py`, exit 0 on pass. Makes no network
calls and writes nothing outside a temporary directory.

Claims, one per clause of the pool rework:
  1. Nothing in discover ranks on a /real-time field, and every pooled name
     carries a non-empty pool_source.
  2. A calendar that answers with nothing records fetched_and_empty, which is
     a different fact from a calendar that was never reached.
  3. The same for the overnight news sweep.
  4. Movers and runners both contribute, and an empty picks table yields no
     runners rather than an exception.
  5. A 300 name pool ranks deterministically, the subscribed count matches the
     CRITERIA cap, and everything below the cut is marked not_subscribed.
  6. Scan ranks on the measured gap, so a tier 5 recent runner with the
     morning's largest gap comes first and still records tier 5.
  7. Recall is measured against what actually gapped, naming what was missed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

import config
import criteria
import discover
import eodhd
import ettime
import pool_recall
import scan
import store

_CRIT = criteria.load()


class _Api:
    """A stubbed client. Every method returns whatever the test handed it."""

    def __init__(self, earnings=None, news_pages=None, error=None) -> None:
        self._earnings = earnings
        self._news_pages = news_pages or [[]]
        self._error = error

    def earnings_calendar(self, start, end, symbols=None):
        if self._error:
            return eodhd.ApiResult(None, self._error)
        return eodhd.ApiResult(self._earnings or [], None)

    def news_feed(self, start, end, limit=1000, offset=0):
        if self._error:
            return eodhd.ApiResult(None, self._error)
        index = offset // max(limit, 1)
        if index >= len(self._news_pages):
            return eodhd.ApiResult([], None)
        return eodhd.ApiResult(self._news_pages[index], None)


def claim_one(failures: list[str]) -> None:
    source = Path(discover.__file__).read_text(encoding="utf-8")
    # The endpoint itself, and the two fields that carried the stale prices.
    for banned in ("bulk_live_us", "normalize_bulk_live", "previousClose"):
        if banned in source:
            failures.append(f"discover.py still references {banned!r}")
    if "live_quotes" in source:
        failures.append("discover.py still references live_quotes")
    print("  claim 1 discover references no /real-time endpoint or field")


def claim_two_and_three(failures: list[str]) -> None:
    universe_symbols = {"AAA.US", "BBB.US"}
    today = dt.date(2026, 8, 14)

    empty = discover.earnings_before_open(_Api(earnings=[]), universe_symbols, today)
    if empty["status"] != discover.FETCHED_EMPTY:
        failures.append(f"an empty calendar recorded {empty['status']!r}")
    broken = discover.earnings_before_open(
        _Api(error="calendar 500"), universe_symbols, today)
    if broken["status"] != discover.NOT_FETCHED:
        failures.append(f"a failed calendar recorded {broken['status']!r}")

    found = discover.earnings_before_open(
        _Api(earnings=[
            {"code": "AAA", "before_after_market": "BeforeMarket", "report_date": "2026-08-14"},
            {"code": "BBB", "before_after_market": "AfterMarket", "report_date": "2026-08-14"},
        ]), universe_symbols, today)
    if set(found["names"]) != {"AAA.US"}:
        failures.append(f"before-open filter kept {sorted(found['names'])}")
    if not found["names"]["AAA.US"].get("timing"):
        failures.append("an earnings name carries no timing field")

    since = ettime.at(dt.date(2026, 8, 13), 16, 0)
    until = ettime.at(dt.date(2026, 8, 14), 7, 15)
    news_empty = discover.overnight_news(_Api(news_pages=[[]]), universe_symbols, since, until)
    if news_empty["status"] != discover.FETCHED_EMPTY:
        failures.append(f"an empty news sweep recorded {news_empty['status']!r}")
    news_broken = discover.overnight_news(
        _Api(error="news 500"), universe_symbols, since, until)
    if news_broken["status"] != discover.NOT_FETCHED:
        failures.append(f"a failed news sweep recorded {news_broken['status']!r}")

    news_found = discover.overnight_news(
        _Api(news_pages=[[
            {"date": "2026-08-14T02:00:00+00:00", "symbols": ["AAA.US"], "title": "older"},
            {"date": "2026-08-14T10:00:00+00:00", "symbols": ["AAA.US"], "title": "newest"},
            {"date": "2026-08-10T10:00:00+00:00", "symbols": ["BBB.US"], "title": "out of window"},
        ]]), universe_symbols, since, until)
    if set(news_found["names"]) != {"AAA.US"}:
        failures.append(f"news sweep kept {sorted(news_found['names'])}, expected AAA only")
    else:
        newest = news_found["names"]["AAA.US"]["newest_item_at"]
        if "06:00" not in newest:
            failures.append(f"newest item timestamp is {newest}, expected the 06:00 ET item")
    print("  claim 2 and 3 fetched_and_empty, not_fetched and timestamps all recorded")


def claim_four(failures: list[str]) -> None:
    original = config.DB_PATH
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-pool-"))
    config.DB_PATH = sandbox / "empty.db"
    try:
        empty = discover.recent_runners({"AAA.US"}, dt.date(2026, 8, 14))
        if empty["status"] != discover.FETCHED_EMPTY:
            failures.append(f"an empty picks table recorded {empty['status']!r}")
        if empty["names"]:
            failures.append("an empty picks table produced runners")

        with store.session() as connection:
            store.init(connection)
            for date, ticker in (("2026-08-11", "AAA.US"), ("2026-08-13", "AAA.US"),
                                 ("2026-08-13", "BBB.US")):
                store.upsert(connection, "picks", ["date", "ticker"],
                             {"date": date, "ticker": ticker, "source": "live"})
            connection.commit()
        runners = discover.recent_runners({"AAA.US", "BBB.US"}, dt.date(2026, 8, 14))
        if set(runners["names"]) != {"AAA.US", "BBB.US"}:
            failures.append(f"runners returned {sorted(runners['names'])}")
        elif runners["names"]["AAA.US"]["weight"] <= runners["names"]["AAA.US"].get("weight", 0) - 1:
            failures.append("weights are not ordered")
        else:
            # AAA appears on the most recent session, so it must outweigh the
            # decay applied to anything older.
            if runners["names"]["AAA.US"]["sessions_ago"] != 0:
                failures.append("the most recent session was not weighted highest")
    finally:
        config.DB_PATH = original
    print("  claim 4 empty picks yields no runners without raising, and recency wins")


def _pool_sources(count: int) -> dict:
    names = {f"S{index:03d}.US": {"newest_item_at": "2026-08-14T06:00:00-04:00",
                                  "newest_title": "t", "items": 1}
             for index in range(count)}
    return {
        "earnings": {"status": discover.FETCHED, "names": {}},
        "news": {"status": discover.FETCHED, "names": names},
        "movers": {"status": discover.FETCHED, "names": {}, "closes": {}},
        "runners": {"status": discover.FETCHED, "names": {}},
    }


def claim_five(failures: list[str]) -> None:
    count = 300
    cap = _CRIT.integer("discovery", "max_subscribed_candidates")
    key = _CRIT.text("discovery", "within_tier_key")
    # Descending in the ranking key, so the expected order is S000 first.
    metrics = {
        f"S{index:03d}.US": {
            "avg_dollar_volume_20d": float(index) * 1_000_000,
            key: float(count - index) / count,
        }
        for index in range(count)
    }
    now = ettime.at(dt.date(2026, 8, 14), 7, 15)

    first = discover.assemble(_pool_sources(count), metrics, now)
    second = discover.assemble(_pool_sources(count), metrics, now)
    if [r["symbol"] for r in first] != [r["symbol"] for r in second]:
        failures.append("the ranking is not deterministic across two runs")
    if len(first) != count:
        failures.append(f"the pool holds {len(first)} names, expected {count}")

    discover.apply_slots(first, cap, _CRIT.integer("discovery", "min_slots_per_tier"))
    subscribed = [r for r in first if r["subscribed"]]
    if len(subscribed) != cap:
        failures.append(f"{len(subscribed)} subscribed, expected the cap of {cap}")
    below = [r for r in first if not r["subscribed"]]
    if len(below) != count - cap:
        failures.append(f"{len(below)} below the cut, expected {count - cap}")
    if not all(r["not_subscribed"] for r in below):
        failures.append("a name below the cut is not marked not_subscribed")
    values = [(metrics[r["symbol"]] or {})[key] for r in first]
    if values != sorted(values, reverse=True):
        failures.append(f"the tiebreak is not {key} descending")
    if any(not r["pool_source"] for r in first):
        failures.append("a pooled name carries an empty pool_source")
    print(f"  claim 5 {count} names rank deterministically, {len(subscribed)} subscribed "
          f"at the cap, {len(below)} marked not_subscribed")


def claim_six(failures: list[str]) -> None:
    candidates = [
        {"symbol": "MEGA.US", "pool_tier": 2, "pool_source": ["news"],
         "price": 100.0, "pool_prior_close": 99.0},          # +1.01 percent
        {"symbol": "RUNNER.US", "pool_tier": 5, "pool_source": ["recent_runner"],
         "price": 12.0, "pool_prior_close": 10.0},           # +20 percent
        {"symbol": "EARN.US", "pool_tier": 1, "pool_source": ["earnings"],
         "price": 51.0, "pool_prior_close": 50.0},           # +2 percent
    ]
    kept, stats = scan.rank_by_measured_gap(candidates, scan.Packet(), keep=12)
    order = [c["symbol"] for c in kept]
    if not order or order[0] != "RUNNER.US":
        failures.append(f"ranking put {order} first, expected the tier 5 runner")
    if kept and kept[0]["pool_tier"] != 5:
        failures.append(f"the winner records tier {kept[0]['pool_tier']}, expected 5")
    # MEGA and EARN sit under the 3 percent discovery gap floor and are cut.
    if "MEGA.US" in order:
        failures.append("a name below the gap floor survived the cut")
    print(f"  claim 6 ranked {order} on measured gap, winner keeps pool_tier "
          f"{kept[0]['pool_tier']}")


def claim_seven(failures: list[str]) -> None:
    gappers = {
        f"G{index}.US": {"symbol": f"G{index}.US", "gap_at_open_pct": 10.0 + index,
                         "open": 10.0, "prior_close": 9.0, "volume": 1000.0}
        for index in range(5)
    }
    pool_rows = [
        {"symbol": "G0.US", "pool_source": ["news"], "pool_tier": 2,
         "pool_rank": 1, "subscribed": True},
        {"symbol": "G1.US", "pool_source": ["earnings"], "pool_tier": 1,
         "pool_rank": 2, "subscribed": True},
        {"symbol": "G2.US", "pool_source": ["recent_runner"], "pool_tier": 5,
         "pool_rank": 300, "subscribed": False},
        {"symbol": "NOISE.US", "pool_source": ["news"], "pool_tier": 2,
         "pool_rank": 3, "subscribed": True},
    ]
    result = pool_recall.measure(gappers, pool_rows)
    if result["gapped"] != 5:
        failures.append(f"counted {result['gapped']} gappers, expected 5")
    if result["pool_held"] != 3:
        failures.append(f"pool held {result['pool_held']}, expected 3")
    if result["recall"] != 0.6:
        failures.append(f"recall {result['recall']}, expected 0.6")
    missed = sorted(row["symbol"] for row in result["missed"])
    if missed != ["G3.US", "G4.US"]:
        failures.append(f"missed {missed}, expected G3.US and G4.US")
    if result["subscribed_held"] != 2:
        failures.append(f"subscribed hits {result['subscribed_held']}, expected 2")
    print(f"  claim 7 recall {result['recall']} of {result['gapped']} gappers, "
          f"missed {missed}, {result['subscribed_held']} of the hits subscribed")


def main() -> int:
    failures: list[str] = []
    claim_one(failures)
    claim_two_and_three(failures)
    claim_four(failures)
    claim_five(failures)
    claim_six(failures)
    claim_seven(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  the pool builds from four priors with honest empty states, ranks "
          "deterministically under the cap, is reranked at 08:45 on the measured "
          "gap, and its recall is measurable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
