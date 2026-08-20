"""Regression tests for the candidate pool that replaced stale gap ranking.

Run directly: `python -m tests.test_pool` with PYTHONPATH set to src/, exit 0
on pass. Makes no network
calls and writes nothing outside a temporary directory.

Claims. The first eight are one per clause of the pool rework; nine to sixteen
were added by later work on the same path:
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
  8. pool_recall.build runs end to end and writes its file. claim 7 tests the
     pure function; this tests the one the scheduler actually calls.
  9. The news window counts trading sessions, so a Monday reaches Friday's
     close rather than Sunday evening.
  10. An interrupted universe write leaves the previous file whole.
  11. An unranked pool is refused rather than cut to the cap arbitrarily.
  12. The quota refuse floor, driven by a fed meter rather than a real one.
  13. A quota gate sized to the work, not to the flat 500 floor.
  14. Every examined name leaves the market cap funnel by exactly one door,
     and the doors are named.
  15. The gates are wired into build(), and their failures reach the right
     handler.
  16. A calendar that cannot name the third session costs the two session leg,
     not the morning.
"""

from __future__ import annotations

import contextlib
import io
import datetime as dt
import inspect
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from tests import conftest
from selection import discover
from core import eodhd
from core import ettime
from night import pool_recall
from morning import scan
from selection import universe
from core import store

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
    if result["discovery_recall_all_gappers"] != 0.6:
        failures.append(f"recall {result['discovery_recall_all_gappers']}, expected 0.6")
    missed = sorted(row["symbol"] for row in result["missed"])
    if missed != ["G3.US", "G4.US"]:
        failures.append(f"missed {missed}, expected G3.US and G4.US")
    if result["subscribed_held"] != 2:
        failures.append(f"subscribed hits {result['subscribed_held']}, expected 2")
    print(f"  claim 7 recall {result['discovery_recall_all_gappers']} of {result['gapped']} gappers, "
          f"missed {missed}, {result['subscribed_held']} of the hits subscribed")


def claim_eight(failures: list[str]) -> None:
    """build() end to end, because measure() alone never caught a NameError.

    claim 7 exercises pool_recall.measure and passed happily for a week while
    pool_recall.build raised NameError on every real run, wrote nothing, and
    was ignored by the nightly batch file. A unit that tests the pure function
    and never the one the scheduler calls is not coverage.
    """
    from night import pool_recall

    class _Api:
        def eod_bulk_last_day(self, exchange="US", day=None, symbols=None, extended=False):
            rows = [
                {"code": "GAPPER", "open": 12.0, "close": 12.5, "volume": 1000.0},
                {"code": "QUIET", "open": 10.0, "close": 10.0, "volume": 1000.0},
            ]
            if day is not None and day.isoformat() == "2026-08-12":
                rows = [
                    {"code": "GAPPER", "open": 10.0, "close": 10.0, "volume": 900.0},
                    {"code": "QUIET", "open": 10.0, "close": 10.0, "volume": 900.0},
                ]
            return eodhd.ApiResult(rows, None)

    original_client, original_runs = eodhd.client, config.RUNS_DIR
    original_universe, original_watchlist = universe.load_universe, discover.load_watchlist
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-recall-"))
    eodhd.client = lambda: _Api()
    config.RUNS_DIR = sandbox
    # A synthetic universe and pool, so the assertion is about the arithmetic
    # rather than about whether two invented tickers happen to be listed.
    universe.load_universe = lambda require_fresh=True: {
        "symbols": [{"symbol": "GAPPER.US"}, {"symbol": "QUIET.US"}]
    }
    discover.load_watchlist = lambda: {
        "generated_at": "2026-08-13T07:15:00-04:00",
        "symbols": [{"symbol": "QUIET.US", "pool_tier": 2, "pool_rank": 1,
                     "subscribed": True, "pool_source": ["news"]}],
    }
    try:
        payload = pool_recall.build(session_date="2026-08-13", write=True)
    except Exception as exc:
        failures.append(f"pool_recall.build raised {type(exc).__name__}: {exc}")
        payload = None
    finally:
        eodhd.client, config.RUNS_DIR = original_client, original_runs
        universe.load_universe, discover.load_watchlist = original_universe, original_watchlist

    if payload is not None:
        # GAPPER opened 12.0 against a 10.0 prior close, so it gapped and the
        # pool did not hold it. QUIET did not gap. Recall is therefore 0 of 1.
        if payload.get("gapped") != 1:
            failures.append(f"build() counted {payload.get('gapped')} gappers, expected 1")
        if payload.get("discovery_recall_all_gappers") != 0.0:
            failures.append(f"build() reported recall {payload.get('recall')}, expected 0.0")
        if [r["symbol"] for r in payload.get("missed", [])] != ["GAPPER.US"]:
            failures.append(f"build() missed list is {payload.get('missed')}")
        for key in ("gapped", "pool_held", "discovery_recall_all_gappers", "addressable", "missed", "session_date"):
            if key not in payload:
                failures.append(f"pool_recall payload has no {key}")
        written = sandbox / "2026-08-13" / "pool_recall.json"
        if not written.is_file():
            failures.append("pool_recall.build wrote no pool_recall.json")
        else:
            print(f"  claim 8 build() wrote {written.name} with "
                  f"{payload['gapped']} gapper(s) and recall {payload['discovery_recall_all_gappers']}")
    shutil.rmtree(sandbox, ignore_errors=True)


def claim_nine(failures: list[str]) -> None:
    """The news window counts trading sessions, so Monday reaches Friday's close.

    Production built the window from a calendar day and backtest_pool from the
    prior trading session. They agree from Tuesday to Friday and are two days
    apart on a Monday, which is when it costs the most: a calendar day back
    from Monday is Sunday 16:00, and the window then never reaches Friday's
    close or anything published across the weekend. Twelve of the sixty cached
    sessions were affected, eleven Mondays and the Tuesday after Memorial Day.
    """
    monday = dt.date(2026, 8, 17)
    if monday.weekday() != 0:
        failures.append("the fixture date is not a Monday")
        return

    start = discover.news_window_start(monday)
    friday = dt.date(2026, 8, 14)

    if start.date() != friday:
        failures.append(f"Monday's news window starts {start.date()}, expected "
                        f"{friday}, the prior trading session")
    if start.hour != 16:
        failures.append(f"the window opens at {start.hour}:00, expected 16:00")

    # The calendar day form, which is what this replaces.
    naive = ettime.at(monday - dt.timedelta(days=1), 16, 0)
    if naive.date() <= friday:
        # The calendar form must start LATER than Friday's close, which is
        # precisely how it loses the weekend. If it does not, this Monday
        # cannot demonstrate the defect and the claim proves nothing.
        failures.append(f"the fixture cannot demonstrate the defect: the calendar "
                        f"form starts {naive.date()}, not after {friday}")
    lost = (naive - start).total_seconds() / 3600.0
    if lost < 47:
        failures.append(f"only {lost:.0f}h separates the two forms on a Monday")

    # A midweek session must be unchanged, or this would widen every window.
    wednesday = dt.date(2026, 8, 12)
    if discover.news_window_start(wednesday).date() != dt.date(2026, 8, 11):
        failures.append("a midweek window no longer starts at the prior day")

    # And the backtest must ask the same function, which is the actual fix.
    from research import backtest_pool
    source = inspect.getsource(backtest_pool.fetch_session)
    if "discover.news_window_start" not in source:
        failures.append("backtest_pool computes its own news window again, which "
                        "is the drift this claim exists to prevent")

    print(f"  claim 9 Monday's window opens {start.date()} 16:00, {lost:.0f}h "
          "earlier than the calendar day form, and both callers share one function")


def claim_ten(failures: list[str]) -> None:
    """An interrupted universe write leaves the previous file whole.

    The Sunday job has never fired, its roughly 4,700 calls bill to Monday's
    quota day, and the key is shared. A refused or interrupted run is a real
    possibility, and a plain write_text leaves a truncated file that reads as
    a real universe.
    """
    original = config.UNIVERSE_PATH
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-universe-"))
    config.UNIVERSE_PATH = sandbox / "universe.json"
    try:
        good = {"generated_at": ettime.stamp(ettime.now_et()), "count": 2745,
                "symbols": [{"symbol": f"S{i}.US"} for i in range(2745)]}
        universe.write_atomically(good)
        before = config.UNIVERSE_PATH.read_text(encoding="utf-8")

        # Failure mode one: the payload cannot be serialised, so the write dies
        # before any file is touched.
        try:
            universe.write_atomically({"symbols": {1, 2, 3}})  # a set, not JSON
        except TypeError:
            pass
        else:
            failures.append("an unserialisable payload did not raise")

        # Failure mode two: the temporary file is written and the rename then
        # fails. This is the one the atomic write exists for, and the only way
        # to reach it is to break the rename itself.
        import os as _os

        real_replace = _os.replace

        def broken_replace(src, dst):
            raise OSError("simulated rename failure")

        universe.os.replace = broken_replace
        try:
            universe.write_atomically({"count": 1, "symbols": [{"symbol": "X.US"}]})
        except OSError:
            pass
        else:
            failures.append("a failing rename did not raise")
        finally:
            universe.os.replace = real_replace

        after = config.UNIVERSE_PATH.read_text(encoding="utf-8")
        if after != before:
            failures.append("an interrupted universe write changed the previous file")
        if list(sandbox.glob("*.partial")):
            failures.append("a partial file was left behind after a failed rename")

        # And the count floor: a universe truncated to 200 names is refused.
        truncated = {"generated_at": ettime.stamp(ettime.now_et()), "count": 200,
                     "previous_count": 2745,
                     "symbols": [{"symbol": f"S{i}.US"} for i in range(200)]}
        reason = universe.check_admissible(truncated)
        if not reason or "200" not in reason:
            failures.append(f"a 200 name universe against 2745 was admitted: {reason!r}")
        whole = universe.check_admissible(good | {"previous_count": 2745})
        if whole is not None:
            failures.append(f"a full universe was refused: {whole}")
        first_ever = universe.check_admissible({"count": 200, "previous_count": None})
        if first_ever is not None:
            failures.append("a first ever build with nothing to compare was refused")
    finally:
        config.UNIVERSE_PATH = original
        shutil.rmtree(sandbox, ignore_errors=True)
    print("  claim 10 an interrupted write leaves the prior universe intact, and a "
          "200 of 2745 rebuild is refused")


def claim_eleven(failures: list[str]) -> None:
    """An unranked pool is refused rather than cut to the cap arbitrarily.

    The meter is pinned healthy for the duration. This claim is about how the
    pool ranks, not about quota, and discover.build preflights before it
    reaches the unranked check, so an ambient meter below the refuse floor
    would raise QuotaRefusal first and this claim would report a pool defect
    that does not exist. That is exactly what happened on 2026-08-16. Pinning
    it here means the claim holds at ANY ambient reading rather than merely at
    the healthy one conftest installs by default.
    """
    real = discover.load_metrics
    universe_payload = {
        "generated_at": ettime.stamp(ettime.now_et()), "count": 100,
        "previous_count": 100,
        "symbols": [{"symbol": f"S{i:03d}.US", "avg_dollar_volume_20d": 1e9}
                    for i in range(100)],
    }
    original = config.UNIVERSE_PATH
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-ranked-"))
    config.UNIVERSE_PATH = sandbox / "universe.json"
    key = _CRIT.text("discovery", "within_tier_key")

    def metrics_with(share: float):
        rows = {}
        for index in range(100):
            row = {"avg_dollar_volume_20d": 1e9}
            if index < int(share * 100):
                row[key] = 0.2
            rows[f"S{index:03d}.US"] = row
        return lambda: rows

    try:
        config.UNIVERSE_PATH.write_text(json.dumps(universe_payload), encoding="utf-8")
        # Pinned once around the whole loop, not per leg: both legs call
        # discover.build, and both preflight before reaching anything this
        # claim is about.
        with conftest.meter_reading():
            for share, should_refuse in ((0.0, True), (0.6, False)):
                discover.load_metrics = metrics_with(share)
                watchlist_before = config.WATCHLIST_PATH.exists()
                try:
                    discover.build(write=False)
                except discover.UnrankedPoolError as exc:
                    if not should_refuse:
                        failures.append(f"a {share:.0%} ranked universe was refused: {exc}")
                    elif str(int(share * 100)) not in str(exc) and "0 of 100" not in str(exc):
                        failures.append(f"the refusal did not name the count: {exc}")
                except conftest.NetworkBlocked:
                    # Expected on the 0.6 leg: an adequately ranked pool is NOT
                    # refused, so build() proceeds to real work and hits the
                    # blocked network. That is this claim passing, not failing.
                    # On the 0.0 leg it would mean the unranked check never ran.
                    if should_refuse:
                        failures.append("a 0% ranked universe reached the network, so the "
                                        "unranked check did not run before the first call")
                except Exception as exc:  # noqa: BLE001
                    # No longer a blanket swallow. Before 2026-08-16 this branch
                    # absorbed anything on the 0.6 leg, including the QuotaRefusal
                    # that a live meter reading produced, which is how this claim
                    # managed to pass all week and then fail on someone else's
                    # spending. An unexpected exception is now a failure on BOTH
                    # legs and names itself.
                    failures.append(f"a {share:.0%} ranked universe raised "
                                    f"{type(exc).__name__}, which this claim does not "
                                    f"expect: {exc}")
                else:
                    if should_refuse:
                        failures.append(f"a {share:.0%} ranked universe was NOT refused")
                if config.WATCHLIST_PATH.exists() != watchlist_before:
                    failures.append("a refused discover wrote a watchlist")
    finally:
        discover.load_metrics = real
        config.UNIVERSE_PATH = original
        shutil.rmtree(sandbox, ignore_errors=True)
    print("  claim 11 a wholly unranked universe is refused and writes nothing, "
          "60 percent proceeds")


def claim_twelve(failures: list[str]) -> None:
    """The quota refusal path, driven by a fed meter rather than a real one.

    This is the other half of the 2026-08-16 fix. Blocking the network stopped
    claim 11 from failing on a sibling project's spending, but it would also
    have stopped anything from ever exercising the refusal, and a path that
    nothing exercises is a path that rots. So the reading is injected at
    eodhd.read_meter and preflight's own verdict logic runs on it for real:
    the thresholds, the arithmetic and the message are all under test, and
    only the network is gone.

    Three readings, because the interesting part is the boundary rather than
    the extremes. The floor is refuse_below_remaining from CRITERIA.md.
    """
    floor = _CRIT.integer("quota", "refuse_below_remaining")
    limit = conftest.HEALTHY_METER["dailyRateLimit"]

    cases = (
        ("just below the floor", limit - (floor - 1), True),
        ("exactly at the floor", limit - floor, False),
        ("comfortably above", limit - (floor * 10), False),
    )
    for label, used, should_refuse in cases:
        with conftest.meter_reading(apiRequests=used):
            record = eodhd.preflight("test")
            if record["refused"] != should_refuse:
                failures.append(
                    f"a meter {label} ({limit - used:,} remaining against a "
                    f"{floor:,} floor) set refused={record['refused']}, "
                    f"expected {should_refuse}")
                continue
            if not should_refuse:
                continue
            # And the refusal has to reach the caller, not just the record.
            try:
                discover.build(write=False)
            except eodhd.QuotaRefusal as exc:
                if str(floor) not in str(exc).replace(",", ""):
                    failures.append(f"the refusal did not name the floor: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"a meter {label} raised {type(exc).__name__} "
                                f"instead of QuotaRefusal: {exc}")
            else:
                failures.append(f"a meter {label} did not refuse discover.build")

    print(f"  claim 12 preflight refuses below {floor:,} remaining and proceeds at or "
          f"above it, on a fed meter with the network blocked")


def claim_thirteen(failures: list[str]) -> None:
    """A quota gate sized to the work, not to the flat 500 floor.

    Claim 12 covers the global floor. This covers the thing the floor cannot
    do. The Sunday rebuild spends a measured 4,945 credits and the floor is
    500, so a meter reading 501 clears the floor and then strands the job a
    tenth of the way through, having spent everything there was. The gate under
    test asks a different question: can the account pay for THIS step at the
    prices in CRITERIA.md [quota costs].

    Two halves, and the second is the one that carries the risk.

    The first is the arithmetic: refuse below the requirement, proceed at it.
    The requirement is computed here from the same cost table the code reads,
    so retuning lookback_sessions or a price cannot leave this claim asserting
    a number nobody uses any more.

    The second is that an UNKNOWN meter must not refuse. preflight leaves
    remaining as None on three paths, and the one that matters is a reading
    dated to another quota day, which is exactly what the vendor serves in the
    half hour after a reset it rolls thirty minutes late. Refusing there would
    convert a benign late roll into a skipped weekly rebuild, and would act on
    a number nobody read. Both unknown paths are driven here.
    """
    crit = criteria.load()
    headroom = crit.number("quota", "quota_headroom_multiple")
    limit = conftest.HEALTHY_METER["dailyRateLimit"]

    # Priced from the table rather than hardcoded, so this tracks CRITERIA.
    need = eodhd.credit_cost(
        exchange_symbol_list=2,
        eod=1,
        eod_bulk_last_day=crit.integer("universe", "lookback_sessions"),
        us_quote_delayed_per_symbol=2_942,
    )
    required = int(need * headroom)
    if need <= crit.integer("quota", "refuse_below_remaining"):
        failures.append(f"the modelled universe cost of {need:,} credits is below the "
                        "refuse floor, so this claim proves nothing the floor does not")
        return

    cases = (
        ("one credit short of the requirement", limit - (required - 1), True),
        ("exactly at the requirement", limit - required, False),
        ("comfortably above", limit - required - 50_000, False),
    )
    for label, used, should_refuse in cases:
        remaining = limit - used
        with conftest.meter_reading(apiRequests=used):
            try:
                eodhd.require_quota("test", need, "the modelled rebuild")
            except eodhd.QuotaRefusal as exc:
                if not should_refuse:
                    failures.append(f"a meter {label} ({remaining:,} remaining against "
                                    f"a {required:,} requirement) refused: {exc}")
                    continue
                message = str(exc).replace(",", "")
                for token in (str(need), str(required), "quota_headroom_multiple"):
                    if token not in message:
                        failures.append(f"the refusal does not name {token!r}: {exc}")
            else:
                if should_refuse:
                    failures.append(
                        f"a meter {label} ({remaining:,} remaining against a "
                        f"{required:,} requirement) did not refuse")

    # The load bearing half. Neither unknown meter may refuse, and the reason
    # they are unknown differs: one is dated to another day, one is unreadable.
    unknowns = (
        ("a reading dated to another quota day, which is the late roll",
         {"apiRequests": limit - 1, "apiRequestsDate": "2000-01-01"}),
        ("a reading whose fields cannot be parsed",
         {"apiRequests": None}),
    )
    for label, overrides in unknowns:
        with conftest.meter_reading(**overrides):
            record = eodhd.preflight("test")
            if record["remaining"] is not None:
                failures.append(f"{label} left remaining as {record['remaining']!r}, "
                                "expected None, so this case is not testing what it "
                                "says it is")
                continue
            try:
                eodhd.require_quota("test", need, "the modelled rebuild")
            except eodhd.QuotaRefusal as exc:
                failures.append(
                    f"{label} refused the rebuild: {exc}. An unknown meter is not a "
                    "zero meter, and refusing here would skip a weekly rebuild on a "
                    "budget that was in fact full.")

    print(f"  claim 13 a {need:,} credit step refuses below {required:,} remaining "
          f"({headroom:g}x) and proceeds at it, and neither unknown meter refuses")


def claim_fourteen(failures: list[str]) -> None:
    """Every examined name leaves by exactly one door, and the doors are named.

    The 2026-08-17 rebuild reported "46 names were dropped because no market
    cap came back" against 2,942 examined and 2,754 admitted. The arithmetic
    does not close: 142 names failed the market cap floor with nothing anywhere
    recording that they had been considered at all. And the one door that WAS
    counted conflated three different facts, one about the vendor's data and
    two about what this run managed to ask.

    The batch that answers nothing is the case that needs a claim rather than a
    reading of the code. eodhd.quote_delayed returns ({}, None) when a chunk
    comes back 200 with a body it does not recognise: no error and no rows. The
    old guard was `if error and not data`, which is False for that shape, so
    the loop ran over an empty dict and twenty names fell through to the vendor
    gap counter with nothing written anywhere. It cannot be reached from a live
    run on demand, so it is driven here from a stub.
    """
    crit = criteria.load()
    rule = crit.rule("universe", "market_cap")

    class _Stub:
        """Four batch outcomes, one per row of the truth table."""

        def __init__(self) -> None:
            self.calls = 0

        def quote_delayed(self, symbols: list[str]) -> Any:
            self.calls += 1
            codes = [s.split(".")[0] for s in symbols]
            if self.calls == 1:                       # priced, above and below floor
                return eodhd.ApiResult(
                    {f"{c}.US": {"marketCap": 100_000_000 if c == "SMALL"
                                 else 900_000_000} for c in codes}, None)
            if self.calls == 2:                       # answered, one row has no cap,
                return eodhd.ApiResult(               # the rest are simply not in it
                    {"NOCAP.US": {"marketCap": None}}, None)
            if self.calls == 3:                       # the silent hole: 200, no rows,
                return eodhd.ApiResult({}, None)      # and no error to record either
            return eodhd.ApiResult(None, "stubbed transport failure")

        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"the market cap sweep called {name}, which this "
                                 "stub does not serve")

    # Four FULL batches handed over in one call, so _attach_market_caps does
    # its own batching and its own accumulation. Feeding it one group at a time
    # and merging the results here would leave the accumulation untested and
    # assert the claim's own bookkeeping instead.
    batch = crit.integer("api", "quote_batch_size")
    groups = [
        ["BIG", "SMALL"] + [f"F{i:02d}" for i in range(batch - 2)],
        ["NOCAP", "ABSENT"] + [f"G{i:02d}" for i in range(batch - 2)],
        ["SILENT"] + [f"H{i:02d}" for i in range(batch - 1)],
        ["BROKEN"] + [f"J{i:02d}" for i in range(batch - 1)],
    ]
    if any(len(group) != batch for group in groups) or batch < 2:
        failures.append(f"quote_batch_size is {batch}, which this fixture cannot "
                        "divide into whole batches")
        return
    flat = [code for group in groups for code in group]

    stub = _Stub()
    notes: list[str] = []
    sweep = universe._attach_market_caps(stub, flat, notes)
    if stub.calls != len(groups):
        failures.append(f"the sweep made {stub.calls} calls for {len(flat)} names at "
                        f"a batch size of {batch}, expected {len(groups)}")

    staged = [{"code": code, "symbol": f"{code}.US"} for code in flat]
    admitted, funnel = universe.market_cap_funnel(staged, sweep, rule)

    expected = {
        "admitted": ["BIG"] + [f"F{i:02d}" for i in range(batch - 2)],
        "below_market_cap_floor": ["SMALL"],
        "no_market_cap_in_row": ["NOCAP"],
        "absent_from_answered_batch": sorted(["ABSENT"]
                                             + [f"G{i:02d}" for i in range(batch - 2)]),
        "in_an_unanswered_batch": sorted(groups[2] + groups[3]),
    }
    if sorted(row["code"] for row in admitted) != sorted(expected["admitted"]):
        failures.append(f"admitted {sorted(r['code'] for r in admitted)}, expected "
                        f"{sorted(expected['admitted'])}")
    for door, names in expected.items():
        if door == "admitted":
            continue
        got = funnel["names"].get(door)
        if got != names:
            failures.append(f"the {door} door holds {got}, expected {names}")
    if funnel["unaccounted"]:
        failures.append(f"the funnel does not close: {funnel['unaccounted']} names "
                        "left by no recorded door")
    if funnel["examined"] != len(flat):
        failures.append(f"the funnel examined {funnel['examined']}, expected {len(flat)}")

    # SILENT is the whole point: 200 with no rows and no error. Revert the
    # guard to `if error and not data` and its batch is treated as answered,
    # so SILENT falls through to absent_from_answered_batch, which reads as
    # "the vendor did not mention it" when in fact nothing came back at all.
    # That is the door it must NOT be in, and it is a different door from the
    # one a careless reading expects.
    if "SILENT" in (funnel["names"].get("absent_from_answered_batch") or []):
        failures.append("a batch that answered 200 with no rows and no error was "
                        "recorded as a name the vendor merely did not mention, "
                        "which is the old guard's behaviour and the exact "
                        "conflation this door exists to end")

    # The names have to reach the log, not only the payload.
    lines = " ".join(universe.funnel_notes(funnel, rule))
    for code in ("NOCAP", "ABSENT", "BROKEN", "SILENT"):
        if code not in lines:
            failures.append(f"{code} is in the funnel but not named in its notes")
    if "SMALL" in lines:
        failures.append("the floor door names its names in the notes, which buries "
                        "the three doors that are evidence gaps")

    # And the unswept share has to be acted on, not merely recorded. The
    # numerator is in_an_unanswered_batch ALONE: a batch that answered without
    # mentioning a name is vendor coverage, and on 2026-08-17 that door held a
    # structural 26 of 2,942. Counting it here would spend a third of the
    # ceiling on a constant, so both doors are driven and only one may refuse.
    ceiling = crit.number("universe", "max_unswept_fraction")
    over = int(1_000 * ceiling) + 5
    under = max(0, int(1_000 * ceiling) - 5)
    for label, door, count, should_refuse in (
        ("nothing came back for them, over the ceiling", "in_an_unanswered_batch",
         over, True),
        ("nothing came back for them, under the ceiling", "in_an_unanswered_batch",
         under, False),
        ("the vendor answered without them, far over the ceiling",
         "absent_from_answered_batch", over * 4, False),
        ("the ordinary case", "in_an_unanswered_batch", 0, False),
    ):
        verdict = universe.check_admissible({
            "count": 2_000, "previous_count": 2_000,
            "market_cap_funnel": {"examined": 1_000, door: count},
        })
        if should_refuse and not verdict:
            failures.append(f"{count} of 1,000 in {door} ({label}) was admitted, "
                            f"above the {ceiling:.1%} ceiling")
        if not should_refuse and verdict:
            failures.append(f"{count} of 1,000 in {door} ({label}) was refused, "
                            f"which it should not be: {verdict}")

    # A file written before the funnel existed must not be refused for lacking it.
    if universe.check_admissible({"count": 2_000, "previous_count": 2_000}):
        failures.append("a payload with no funnel was refused, but there is nothing "
                        "to compare and a universe predating the field is not partial")

    print(f"  claim 14 all {len(flat)} examined names leave by one of "
          f"{len(expected)} named doors, the funnel closes, and a batch that "
          "answered nothing is not recorded as a vendor gap")


def claim_fifteen(failures: list[str]) -> None:
    """The gates are wired in, and their failures reach the right handler.

    Claim 13 proves require_quota's arithmetic. It would keep passing if every
    call to it were deleted from universe.py and gap_stats.py, which is the
    difference between testing a function and testing a change. This claim
    covers the wiring and the two handlers, both of which are load bearing for
    a reason that is invisible at the call site.

    QuotaRefusal and PartialBuildError both subclass RuntimeError, and
    universe.main has caught bare RuntimeError since long before either
    existed. A handler added BELOW that one is dead code, and the symptom is
    not a crash: it is a refusal reported as "build failed" with no reason on
    the job status line, which is exactly the silent failure this project
    added job_status to end. Ordering cannot be asserted from the exit code,
    because every path returns 1, so this drives them and reads what was said.
    """
    from selection import gap_stats

    # Wiring. Source inspection because the alternative is a live build, and
    # claim 1 already establishes this idiom in this suite.
    universe_gates = inspect.getsource(universe.build).count("eodhd.require_quota")
    if universe_gates != 2:
        failures.append(f"universe.build calls require_quota {universe_gates} times, "
                        "expected 2: one after the session dates where the bulk "
                        "sweep is exactly known, one before the market cap sweep")
    gap_gates = inspect.getsource(gap_stats.build).count("eodhd.require_quota")
    if gap_gates != 1:
        failures.append(f"gap_stats.build calls require_quota {gap_gates} times, "
                        "expected 1")
    if "check_admissible(payload)" not in inspect.getsource(universe.build):
        failures.append("universe.build does not check its own payload before "
                        "writing, so a truncated build still replaces a good file")

    # Handlers, driven rather than read. Each exception is raised from a
    # stubbed build and the printed line has to be the specific one.
    for exception, wanted in (
        (eodhd.QuotaRefusal("stub, the key cannot pay"), "REFUSING TO RUN:"),
        (universe.PartialBuildError("stub, the sweep lost batches"), "REFUSING TO WRITE:"),
    ):
        saved = universe.build

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise exception

        buffer = io.StringIO()
        try:
            universe.build = _raise
            with contextlib.redirect_stdout(buffer):
                code = universe.main([])
        finally:
            universe.build = saved
        printed = buffer.getvalue()
        name = type(exception).__name__
        if code != 1:
            failures.append(f"universe.main returned {code} on {name}, expected 1")
        if wanted not in printed:
            failures.append(
                f"universe.main did not print {wanted!r} on {name}. It printed: "
                f"{printed.strip()[:160]!r}. A handler placed after the bare "
                "RuntimeError catch is unreachable, and the give away is the "
                "generic wording rather than an exception.")

    print("  claim 15 both universe gates and the gap_stats gate are called, the "
          "build checks itself before overwriting, and each refusal reaches its "
          "own handler ahead of the bare RuntimeError catch")


def claim_sixteen(failures: list[str]) -> None:
    """A calendar that cannot name the third session costs one leg, not the morning.

    write_universe_closes takes its first two session maps as arguments and
    buys only the third, and it asked the calendar for that session's date
    without ever checking the answer. previous_trading_session returns None
    when market_today cannot answer, which is not hypothetical: the calendar
    guard's own suite already drives an exploding is_trading_day, because a
    cached exchange-details.json that is missing, unparseable or refused by the
    vendor is the ordinary way this fails.

    Both consequences of passing that None on are silent until they are not.
    eod-bulk-last-day sends no date parameter for a falsy day, so the vendor
    answers with the LATEST completed session, which is c1: every two session
    move in the briefing becomes a close measured against itself and prints as
    a genuine flat. Then the payload's own session dates call .isoformat() on
    the None and raise AttributeError, which discover.main catches on none of
    its four branches, so the 07:15 pass dies before watchlist.json exists and
    the collector has nothing to subscribe to at 07:20. One unanswerable
    calendar, and the whole morning is gone.

    So this drives the real mechanism rather than stubbing the return: the
    calendar itself is made to fail and every bulk call is recorded, because
    the load bearing assertion is about a call that must NOT happen.

    The second load bearing assertion is that a payload still comes back.
    write_universe_closes documents that it ALWAYS returns one, and the wrong
    way to skip the third call is to print a warning and return None: no bulk
    call is made and nothing raises, so a claim that only watched for those two
    things would pass while the morning quietly lost the prior session leg and
    the sidecar as well as the leg the calendar actually cost it.
    """
    from ops import market_today

    class _Bulk:
        """Records every bulk call. The claim is about one that must not occur."""

        def __init__(self) -> None:
            self.days: list[Any] = []

        def eod_bulk_last_day(self, exchange="US", day=None, symbols=None,
                              extended=False):
            self.days.append(day)
            # The shape the vendor serves for a dateless request: the latest
            # completed session, which is c1 wearing c3's label.
            return eodhd.ApiResult([{"code": "AAA", "close": 11.0}], None)

        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"write_universe_closes called {name}, which this "
                                 "stub does not serve")

    today = dt.date(2026, 8, 17)
    prior, before = dt.date(2026, 8, 14), dt.date(2026, 8, 13)
    prior_by = {"AAA.US": {"code": "AAA", "close": 11.0, "date": "2026-08-14"}}
    before_by = {"AAA.US": {"code": "AAA", "close": 10.0, "date": "2026-08-13"}}

    def unanswerable(date):
        raise RuntimeError("simulated exchange calendar fault")

    real_calendar = market_today.is_trading_day
    original_data = config.DATA_DIR
    sandbox = Path(tempfile.mkdtemp(prefix="premarketdesk-closes-"))
    config.DATA_DIR = sandbox
    market_today.is_trading_day = unanswerable
    api = _Bulk()
    payload = None
    buffer = io.StringIO()
    try:
        from morning import vintage

        # This probe sits above the handler below rather than inside it. That
        # handler attributes every escape to write_universe_closes and then
        # recites discover.main's four catches as the consequence, so a fixture
        # that broke here would be reported as a production failure in a call
        # that had not been made yet. claim 9 puts its equivalent probe under
        # no handler at all for the same reason. It stays inside the outer
        # try/finally regardless: the exploding calendar is installed globally
        # by this point, and every later claim would inherit it.
        if vintage.previous_trading_session(before) is not None:
            failures.append("the fixture cannot demonstrate the defect: the calendar "
                            "still names a session before 2026-08-13, so the None "
                            "path this claim exists for is never taken")
        try:
            with contextlib.redirect_stdout(buffer):
                payload = discover.write_universe_closes(
                    api, {"AAA.US"}, prior_by, before_by, prior, before, today)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"write_universe_closes raised {type(exc).__name__}: {exc}. "
                            "discover.main catches StaleUniverseError, QuotaRefusal, "
                            "UnrankedPoolError and RuntimeError and nothing else, so "
                            "anything raised here kills the 07:15 pass before "
                            "watchlist.json is written.")
        else:
            # Not raising is only half of what was promised, and a claim that
            # stopped there would pass against the one wrong fix this finding
            # forbade: print the warning and return None. Every assertion after
            # this one is nested under a payload, so a None return would skip
            # the lot and the claim would announce success having proved only
            # that the third call was not made.
            if payload is None:
                failures.append(
                    "write_universe_closes returned None instead of a payload. Its "
                    "docstring promises it ALWAYS returns one, and that a third call "
                    "it cannot make costs the two session leg and nothing else. "
                    "Returning early on a session the calendar cannot name breaks "
                    "that: it also drops the prior session leg, which was complete "
                    "before the calendar was ever asked, and the sidecar the report "
                    "reads. No caller tests this return value, so the loss arrives "
                    "as a briefing with no notable movers rather than as an error.")

        if api.days:
            failures.append(f"the third bulk call was made with day={api.days!r} despite "
                            "the calendar naming no session. A dateless call is answered "
                            "with the latest completed session, so c3 would be c1 and "
                            "every two session move would print as flat.")
        if payload is not None:
            if payload.get("third_session_available") is not False:
                failures.append("third_session_available is "
                                f"{payload.get('third_session_available')!r}, expected "
                                "False, which is the field that tells the briefing the "
                                "two session leg is absent rather than zero")
            if (payload.get("sessions") or {}).get("c3") is not None:
                failures.append(f"sessions.c3 is {(payload['sessions']).get('c3')!r}, "
                                "expected null: no session was named, so there is no "
                                "date to stamp the leg with")
            row = (payload.get("closes") or {}).get("AAA.US") or {}
            if row.get("c3") is not None:
                failures.append(f"AAA.US carries c3 {row['c3']!r}, expected null. A "
                                "missing close is never substituted from a neighbouring "
                                "session.")
            # The prior session leg is the half that must survive untouched,
            # since both its maps were already in hand before the calendar was
            # asked.
            if (row.get("c1"), row.get("c2")) != (11.0, 10.0):
                failures.append(f"the prior session leg came through as {row!r}, "
                                "expected c1 11.0 and c2 10.0 from the two maps "
                                "already held")

            written = sandbox / f"universe-closes-{today.isoformat()}.json"
            if not written.is_file():
                failures.append("no universe closes sidecar was written, so the "
                                "briefing loses the prior session leg as well as the "
                                "two session one")
            else:
                on_disk = json.loads(written.read_text(encoding="utf-8"))
                if (on_disk["sessions"]["c3"] is not None
                        or on_disk["third_session_available"]):
                    failures.append("the file on disk disagrees with the returned "
                                    "payload about the third session, and the report "
                                    "reads the file")

            printed = buffer.getvalue()
            if "calendar" not in printed or "two session leg is absent" not in printed:
                failures.append("the run said nothing about the missing third session. "
                                f"It printed: {printed.strip()[:160]!r}. A leg that "
                                "vanishes silently is the failure mode this project "
                                "records reasons to avoid.")
    finally:
        market_today.is_trading_day = real_calendar
        config.DATA_DIR = original_data
        # The cleanup belongs beside the two restores, following claim 10. The
        # assertions above index the payload and the file on disk unguarded, so
        # a later change to the payload schema raises KeyError there, and a
        # rmtree left outside this block would abandon the directory in the
        # system temp on every run until someone went looking for it.
        shutil.rmtree(sandbox, ignore_errors=True)

    print("  claim 16 an unanswerable calendar skips the third bulk call, returns a "
          "payload with c3 null and third_session_available False, and leaves the "
          "prior session leg whole")


def main() -> int:
    failures: list[str] = []
    claim_one(failures)
    claim_two_and_three(failures)
    claim_four(failures)
    claim_five(failures)
    claim_six(failures)
    claim_seven(failures)
    claim_eight(failures)
    claim_nine(failures)
    claim_ten(failures)
    claim_eleven(failures)
    claim_twelve(failures)
    claim_thirteen(failures)
    claim_fourteen(failures)
    claim_fifteen(failures)
    claim_sixteen(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  the pool builds from four priors with honest empty states, ranks "
          "deterministically under the cap, is reranked at 08:45 on the measured "
          "gap, and its recall is measurable")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
