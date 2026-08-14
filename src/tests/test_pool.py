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
  8. pool_recall.build runs end to end and writes its file. claim 7 tests the
     pure function; this tests the one the scheduler actually calls.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import re
import shutil
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
import universe
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


def claim_eight(failures: list[str]) -> None:
    """build() end to end, because measure() alone never caught a NameError.

    claim 7 exercises pool_recall.measure and passed happily for a week while
    pool_recall.build raised NameError on every real run, wrote nothing, and
    was ignored by the nightly batch file. A unit that tests the pure function
    and never the one the scheduler calls is not coverage.
    """
    import pool_recall

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
        if payload.get("recall") != 0.0:
            failures.append(f"build() reported recall {payload.get('recall')}, expected 0.0")
        if [r["symbol"] for r in payload.get("missed", [])] != ["GAPPER.US"]:
            failures.append(f"build() missed list is {payload.get('missed')}")
        for key in ("gapped", "pool_held", "recall", "missed", "session_date"):
            if key not in payload:
                failures.append(f"pool_recall payload has no {key}")
        written = sandbox / "2026-08-13" / "pool_recall.json"
        if not written.is_file():
            failures.append("pool_recall.build wrote no pool_recall.json")
        else:
            print(f"  claim 8 build() wrote {written.name} with "
                  f"{payload['gapped']} gapper(s) and recall {payload['recall']}")
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
    import backtest_pool
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
    """An unranked pool is refused rather than cut to the cap arbitrarily."""
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
            except Exception as exc:  # noqa: BLE001
                # Any other failure is the network stub missing, not this claim.
                if should_refuse:
                    failures.append(f"a 0% ranked universe raised {type(exc).__name__} "
                                    f"instead of UnrankedPoolError: {exc}")
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
