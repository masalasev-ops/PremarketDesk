"""Per name gap propensity, from history this plan already pays for.

The pool has to be ordered inside a tier and the shipped key is 20 day average
dollar volume. Measured against 2026-08-13 that key put MU, NVDA, AAPL, MSFT
and AMD into the last five subscription slots and none of them gapped, which is
not surprising: dollar volume measures how much a name trades, and the thing
being predicted is whether it will jump overnight. Those two run against each
other, because the largest companies in the market are the steadiest.

So this measures the thing itself. For every universe name, over a trailing
window of sessions:

  gap_propensity      the fraction of sessions whose open sat further than the
                      discovery gap floor from the prior close
  median_abs_gap_pct  the median absolute gap on the sessions where it did
  atr_pct_20d         20 day average true range as a percent of price, a
                      general volatility reading rather than a gap specific one

One end of day call per symbol covers the whole window, measured at about one
counted call and 0.15 seconds each, so the universe costs roughly 2,745 calls
and seven minutes. That is a weekly cost, paid on the universe rebuild
schedule, and nothing is computed at 07:15.

Rows are keyed by (ticker, as_of). A name with too little history stores a NULL
propensity and its real sessions_used, never a computed zero: a name that has
not gapped in 250 sessions and a name nobody has measured are different facts,
and every consumer has to be able to tell them apart.
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status
from core import store
from selection import universe

_CRIT = criteria.load()

LOOKBACK_SESSIONS = _CRIT.integer("gap_stats", "lookback_sessions")
MIN_SESSIONS = _CRIT.integer("gap_stats", "min_sessions")
ATR_SESSIONS = _CRIT.integer("gap_stats", "atr_sessions")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gap_stats (
    ticker             TEXT NOT NULL,
    as_of              TEXT NOT NULL,
    gap_propensity     REAL,
    median_abs_gap_pct REAL,
    atr_pct_20d        REAL,
    sessions_used      INTEGER NOT NULL DEFAULT 0,
    computed_at        TEXT NOT NULL,
    PRIMARY KEY (ticker, as_of)
);
"""


def init(connection) -> None:
    connection.executescript(_SCHEMA)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def compute(bars: list[dict[str, Any]], as_of: dt.date) -> dict[str, Any]:
    """Propensity, median gap and ATR from one symbol's end of day history.

    Only sessions at or before as_of are used, so a window ending before a
    backtest's earliest session is strictly out of sample for it.
    """
    gap_rule = _CRIT.rule("discovery", "gap_pct")

    rows = []
    for bar in bars or []:
        try:
            day = ettime.parse_date(str(bar.get("date")))
        except (TypeError, ValueError):
            continue
        if day > as_of:
            continue
        close = _as_float(bar.get("close"))
        open_price = _as_float(bar.get("open"))
        high = _as_float(bar.get("high"))
        low = _as_float(bar.get("low"))
        if close is None or open_price is None:
            continue
        rows.append((day, open_price, high, low, close))
    rows.sort()
    rows = rows[-(LOOKBACK_SESSIONS + 1):]

    gaps: list[float] = []
    true_ranges: list[float] = []
    for index in range(1, len(rows)):
        _day, open_price, high, low, close = rows[index]
        prior_close = rows[index - 1][4]
        if prior_close:
            gaps.append((open_price - prior_close) / prior_close * 100.0)
            if high is not None and low is not None:
                true_ranges.append(max(
                    high - low, abs(high - prior_close), abs(low - prior_close)
                ))

    sessions_used = len(gaps)
    last_close = rows[-1][4] if rows else None
    atr_pct = None
    if len(true_ranges) >= ATR_SESSIONS and last_close:
        atr = sum(true_ranges[-ATR_SESSIONS:]) / ATR_SESSIONS
        atr_pct = round(atr / last_close * 100.0, 6)

    if sessions_used < MIN_SESSIONS:
        # Null, not zero. Too little history is a fact about the record, not a
        # finding about the stock.
        return {
            "gap_propensity": None,
            "median_abs_gap_pct": None,
            "atr_pct_20d": atr_pct,
            "sessions_used": sessions_used,
        }

    beyond = [abs(gap) for gap in gaps if gap_rule.test(abs(gap))]
    return {
        "gap_propensity": round(len(beyond) / sessions_used, 6),
        "median_abs_gap_pct": round(statistics.median(beyond), 6) if beyond else 0.0,
        "atr_pct_20d": atr_pct,
        "sessions_used": sessions_used,
    }


def build(as_of_dates: list[dt.date], write: bool = True) -> dict[str, Any]:
    """Compute stats for every universe name at each as_of, from one fetch each."""
    api = eodhd.client()
    universe_payload = universe.load_universe(require_fresh=False)
    symbols = universe.universe_symbols(universe_payload)

    newest = max(as_of_dates)
    oldest = min(as_of_dates)
    # Calendar days generous enough to cover the lookback before the OLDEST
    # as_of, so one call serves every as_of date.
    start = oldest - dt.timedelta(days=int(LOOKBACK_SESSIONS * 1.6) + 40)

    # Fetch first, write once. Holding a write transaction open across two
    # thousand HTTP calls would lock the database for the length of the run,
    # which blocks every other writer and makes anything else touching the
    # database fail with "database is locked" for reasons that have nothing to
    # do with it. Five thousand rows fit in memory without discussion.
    pending: list[dict[str, Any]] = []
    failed: list[str] = []
    for index, symbol in enumerate(symbols, start=1):
        bars, error = api.eod(symbol, start=start, end=newest)
        if error or not bars:
            failed.append(symbol)
            continue
        for as_of in as_of_dates:
            pending.append({
                "ticker": symbol,
                "as_of": as_of.isoformat(),
                "computed_at": ettime.stamp(),
                **compute(bars, as_of),
            })
        if index % 250 == 0:
            print(f"gap_stats: {index}/{len(symbols)} symbols fetched, "
                  f"{len(failed)} failed")

    written = 0
    if write:
        with store.session() as connection:
            store.init(connection)
            init(connection)
            for row in pending:
                store.upsert(connection, "gap_stats", ["ticker", "as_of"], row)
            connection.commit()
    written = len({row["ticker"] for row in pending})

    print(f"gap_stats: wrote {written} symbols across {len(as_of_dates)} as_of dates, "
          f"{len(failed)} failed")
    return {"written": written, "failed": failed, "as_of": [d.isoformat() for d in as_of_dates]}


def load_all(as_of: str | None = None) -> dict[str, dict[str, Any]]:
    """Stats keyed by ticker for one as_of, defaulting to the newest present."""
    with store.session() as connection:
        store.init(connection)
        init(connection)
        if as_of is None:
            row = connection.execute("SELECT MAX(as_of) FROM gap_stats").fetchone()
            as_of = row[0] if row else None
        if as_of is None:
            return {}
        rows = connection.execute(
            "SELECT * FROM gap_stats WHERE as_of=?", (as_of,)
        ).fetchall()
    return {row["ticker"]: dict(row) for row in rows}


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per name gap propensity and ATR.")
    parser.add_argument("--as-of", action="append", default=[],
                        help="Window end date, repeatable. Defaults to the last "
                             "completed session.")
    parser.add_argument("--show", metavar="N", type=int,
                        help="Print the N highest and lowest propensities and exit.")
    args = parser.parse_args(argv)

    if args.show:
        stats = load_all()
        measured = [(v["gap_propensity"], k, v) for k, v in stats.items()
                    if v.get("gap_propensity") is not None]
        measured.sort(reverse=True)
        nulls = [k for k, v in stats.items() if v.get("gap_propensity") is None]
        print(f"gap_stats: {len(stats)} rows, {len(measured)} measured, "
              f"{len(nulls)} null for too little history")
        print(f"  {'ticker':<12} {'propensity':>11} {'median gap':>11} {'atr %':>8} {'sessions':>9}")
        for propensity, ticker, row in measured[:args.show]:
            print(f"  {ticker:<12} {propensity:>11.4f} "
                  f"{row['median_abs_gap_pct'] or 0:>11.2f} "
                  f"{row['atr_pct_20d'] or 0:>8.2f} {row['sessions_used']:>9}")
        print("  ...")
        for propensity, ticker, row in measured[-args.show:]:
            print(f"  {ticker:<12} {propensity:>11.4f} "
                  f"{row['median_abs_gap_pct'] or 0:>11.2f} "
                  f"{row['atr_pct_20d'] or 0:>8.2f} {row['sessions_used']:>9}")
        return 0

    if args.as_of:
        dates = [ettime.parse_date(value) for value in args.as_of]
    else:
        dates = [ettime.today_et() - dt.timedelta(days=1)]

    quota = eodhd.preflight("gap_stats")
    if quota["refused"]:
        print(f"gap_stats: refusing, {eodhd.describe_preflight(quota)}")
        return 1
    result = build(dates)
    job_status.produced("symbols measured", result["written"])
    # build() has always returned the names it could not fetch and main has
    # always thrown that list away, so a run where every symbol failed exited
    # zero and looked identical to a clean one. Zero written is the
    # unambiguous case and needs no threshold to judge: the propensity
    # ranking discover depends on would be running on nothing new.
    if not result["written"]:
        job_status.failed(
            f"nothing was written: all {len(result['failed'])} symbol(s) failed"
            + (f", first was {result['failed'][0]}" if result["failed"] else "")
        )
    eodhd.print_call_report()
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("gap_stats", main, ok_codes=OK_CODES))
