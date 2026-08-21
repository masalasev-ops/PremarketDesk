"""Per name gap propensity, from history this plan already pays for.

The pool has to be ordered inside a tier, and the key it shipped with was 20
day average dollar volume. What this file writes replaced it: gap_propensity is
CRITERIA.md [discovery] within_tier_key now, with atr_pct_20d as its fallback. Measured against 2026-08-13 that key put MU, NVDA, AAPL, MSFT
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
# The report's move_sigma denominator has its own floor, in CRITERIA
# [Notable], because it answers a different question from gap propensity:
# 20 sessions is enough to measure how much a name moves, and gap_stats
# min_sessions is deliberately higher because a propensity RATE needs more
# observations than a spread does.
MIN_SESSIONS_FOR_SIGMA = _CRIT.integer("notable", "min_sessions_for_move_sigma")
# The WINDOW the stdev is taken over, which is a different question from the
# floor above. min_sessions_for_move_sigma says how many returns are needed
# before the answer is publishable; this says how many go into it. Until
# 2026-08-20 there was no such key and the stdev was taken over every return in
# the 250 session list, so a column named return_stdev_20d held a trailing one
# year figure. See the stdev window note in CRITERIA.md.
RETURN_STDEV_SESSIONS = _CRIT.integer("gap_stats", "return_stdev_sessions")

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


# Columns added after the table first shipped. _SCHEMA is CREATE TABLE IF NOT
# EXISTS, so it is a no op against a database that already holds rows and would
# leave a live table unwidened until the first upsert died partway through a
# 2,700 call Sunday job. ensure_columns is the migration path picks already
# uses.
_LATER_COLUMNS = (
    ("return_stdev_20d", "REAL"),
)


def init(connection) -> None:
    connection.executescript(_SCHEMA)
    added = store.ensure_columns(connection, "gap_stats", _LATER_COLUMNS)
    if added:
        print(f"gap_stats: widened the table with {', '.join(added)}")


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
        # A bar with no open stays in the chain with open_price None. It used
        # to be dropped whole, which removed its CLOSE from the chain too, so
        # the session after a hole had its gap measured against a close two
        # sessions back: a two session move stored as a one session gap. The
        # comment below already identified that exact mechanism and fixed it
        # for the returns list only, leaving gap_propensity, median_abs_gap_pct
        # and atr_pct_20d on the unfixed one, and gap_propensity is
        # [discovery] within_tier_key, the number 42 subscription slots are
        # ordered by, with atr_pct_20d as its fallback. A hole now costs one
        # gap rather than corrupting the next.
        if close is None:
            continue
        rows.append((day, open_price, high, low, close))
    rows.sort()
    rows = rows[-(LOOKBACK_SESSIONS + 1):]

    # The volatility denominator for the report's move_sigma, built from its
    # OWN filtered list rather than from rows above.
    #
    # [corrected 2026-08-20: the reason written here was that rows "drops any
    # bar missing an open". It did until 2026-08-20, when that drop was found
    # to break the close chain and each measurement was guarded on the field it
    # needs instead; rows now keeps a bar whose open is None. The sentence is
    # replaced rather than left standing, because it is the one a next reader
    # would use to justify this second list and it is false in this same file
    # thirty lines up.]
    #
    # The surviving reason is the close filter below: rows keeps a bar carrying
    # any usable field, and this list refuses a close of zero or less. Walking
    # a list that admitted one would divide by it. Closes are all this needs,
    # so closes are all it filters on, and a chain broken by a refused bar
    # would treat two sessions either side of it as adjacent and quietly widen
    # one return into two.
    closes: list[tuple[Any, float]] = []
    for bar in bars or []:
        try:
            day = ettime.parse_date(str(bar.get("date")))
        except (TypeError, ValueError):
            continue
        if day > as_of:
            continue
        close = _as_float(bar.get("close"))
        if close is not None and close > 0:
            closes.append((day, close))
    closes.sort()
    closes = closes[-(LOOKBACK_SESSIONS + 1):]
    returns = [
        (closes[i][1] - closes[i - 1][1]) / closes[i - 1][1] * 100.0
        for i in range(1, len(closes))
    ]
    # Null, not zero, below the floor. A name with one session of history has
    # no measurable volatility, and dividing a move by a fabricated one would
    # report a sigma nobody measured.
    # Over the LAST RETURN_STDEV_SESSIONS returns, not over all of them. The
    # column is called return_stdev_20d and BUILD_PLAN specifies it as "the
    # standard deviation of daily close to close returns in percent over the
    # trailing 20 sessions"; it was being computed over the whole 250 session
    # list, because min_sessions_for_move_sigma was read as the window when it
    # is a floor. A year long denominator understates a name that has just
    # started moving and overstates one that has just stopped, and it also
    # disarmed the min_return_stdev_pct floor, which exists so that a name
    # which has barely moved in twenty sessions does not report an enormous
    # sigma: almost nothing sits below 0.1 over 250 sessions.
    window = returns[-RETURN_STDEV_SESSIONS:]
    return_stdev = (round(statistics.stdev(window), 6)
                    if len(returns) >= MIN_SESSIONS_FOR_SIGMA and len(window) >= 2
                    else None)

    gaps: list[float] = []
    true_ranges: list[float] = []
    for index in range(1, len(rows)):
        _day, open_price, high, low, close = rows[index]
        prior_close = rows[index - 1][4]
        if prior_close:
            # Each measurement is guarded on the field IT needs, so a bar
            # missing an open still contributes its true range and still
            # anchors the next session's gap.
            if open_price is not None:
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
            "return_stdev_20d": return_stdev,
            "sessions_used": sessions_used,
        }

    beyond = [abs(gap) for gap in gaps if gap_rule.test(abs(gap))]
    return {
        "gap_propensity": round(len(beyond) / sessions_used, 6),
        "median_abs_gap_pct": round(statistics.median(beyond), 6) if beyond else 0.0,
        "atr_pct_20d": atr_pct,
        "return_stdev_20d": return_stdev,
        "sessions_used": sessions_used,
    }


def build(as_of_dates: list[dt.date], write: bool = True) -> dict[str, Any]:
    """Compute stats for every universe name at each as_of, from one fetch each."""
    api = eodhd.client()
    universe_payload = universe.load_universe(require_fresh=False)
    symbols = universe.universe_symbols(universe_payload)

    # One eod call per universe name, and eod is one credit, so this step can
    # price itself exactly before it spends anything. It is the second half of
    # the Sunday job and it cost a measured 2,753 credits on 2026-08-17, so the
    # flat 500 refuse floor it used to check would have cleared at 501 and then
    # stopped this run a fifth of the way in. A run that stops partway leaves
    # gap_propensity computed for the names it reached and last week's figures
    # for the rest, mixed in one table under one as_of, which is worse than not
    # running: discover ranks on that column and cannot see the seam.
    eodhd.require_quota(
        "gap_stats",
        eodhd.credit_cost(eod=len(symbols)),
        f"one end of day history for each of {len(symbols):,} universe names")

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

    # The flat floor check that used to sit here is gone. build() now reads the
    # meter once against what this run will actually spend, which is a number
    # it can compute exactly, so a second read against a floor that is five
    # times too small would only cost a call and disagree.
    try:
        result = build(dates)
    except eodhd.QuotaRefusal as exc:
        print(f"REFUSING TO RUN: {exc}")
        job_status.failed(f"{type(exc).__name__}: {exc}")
        eodhd.print_call_report()
        return 1
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
