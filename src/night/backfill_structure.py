"""The daily context map, written onto every session the record already holds.

WHY. The map landed on 2026-09-08 as a panel on a card and was stored nowhere,
so it could describe a morning and never improve. Nothing could ask whether a
name that gapped out of a sixty session base behaved differently from one that
gapped inside it, because no row said which of those it was, and the ledger
cannot book a rule against a level it has never recorded. This pass writes the
map onto every picks row there is, so the question becomes answerable over the
whole record rather than from tomorrow forward.

THE TRAP, and it would have corrupted the ledger in silence. A level for a past
session must be computed from bars dated UP TO THAT SESSION ONLY. Today's bars
make every historical level better than it was: a sixty session high that has
seen the following month knows where the name actually went, a base that broke
is no longer a base, and every one of those numbers still looks entirely
plausible in the column. Nothing downstream could catch it, because there is
nothing to catch: the arithmetic is right and the inputs are from the future.

    So each symbol's series is fetched ONCE, and each row slices that series by
    its own date before anything is measured. rows_for_symbol() below is pure
    and takes the whole series, which is exactly what makes the guard testable:
    claim_a_backfilled_level_cannot_see_its_own_future feeds it a truncated
    series and the full one and fails if any column moves.

WHAT IT COSTS. One eod call per DISTINCT symbol, not per row. The record holds
10,133 rows over 1,590 names, so the whole backfill is about 1,590 credits
against a shared daily 100,000, and [Quota costs] prices eod at one credit FLAT
PER CALL: the from date changes the size of the payload and not the price of
it. The series is cached under data/backtest/structure-eod so a re-run after a
fix costs nothing, which is the split research/backtest_pool.py was built
around and for the same reason.

WHAT IT DOES NOT TOUCH. The source column, which stays whatever the row said.
live, test and reconstructed rows are computed identically, because a pass that
measured them differently would make every aggregate that mixes them a lie and
every aggregate that does not a comparison of two instruments. No aggregate may
mix them anyway; see CRITERIA [Picks].

    Short interest is NOT backfilled and the null is deliberate. The
    fundamentals endpoint answers with today's figure and carries no history,
    so a 2025 row could only be handed a 2026 number in a column that reads as
    a measurement of that session. See CRITERIA [Short interest].

Run:

    PYTHONPATH=src .venv/Scripts/python.exe -m night.backfill_structure --dry-run
    PYTHONPATH=src .venv/Scripts/python.exe -m night.backfill_structure
    PYTHONPATH=src .venv/Scripts/python.exe -m night.backfill_structure --session 2026-09-08
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from core import files
from core import store
from morning import structure

_CRIT = criteria.load()

COMPUTED_BY = "backfill"

# The one reason a backfilled row can never carry a short interest figure,
# written once so every row says the same thing.
NO_SHORT_INTEREST = (
    "short interest is not backfilled: the fundamentals endpoint answers with "
    "today's figure and carries no history, so a past session could only be "
    "given a present day number")


def cache_dir() -> Path:
    """Resolved at CALL time so the test sandbox's DATA_DIR redirect reaches it."""
    return config.DATA_DIR / "backtest" / "structure-eod"


def _rows_to_fill(connection, session: str | None, source: str | None,
                  refill: bool) -> list[dict[str, Any]]:
    """Every picks row this pass would write, newest session first.

    Not refilling by default. A row whose ds_computed_by is already set has a
    map, and re-measuring it spends the same credits to produce the same
    numbers. --refill is for the case where the measurement itself changed.
    """
    where = ["1=1"]
    params: list[Any] = []
    if session:
        where.append("date = ?")
        params.append(session)
    if source:
        where.append("source = ?")
        params.append(source)
    if not refill:
        where.append("ds_computed_by IS NULL")
    sql = ("SELECT date, ticker, source, gap_pct FROM picks WHERE "
           + " AND ".join(where) + " ORDER BY date DESC, ticker")
    return [dict(row) for row in connection.execute(sql, params)]


def series_for(api: eodhd.EodhdClient, symbol: str, start: dt.date,
               end: dt.date) -> tuple[list[dict[str, Any]] | None, str | None]:
    """One symbol's daily bars, from the cache if it is there and wide enough.

    The cache is keyed by symbol and records the window it was fetched over, so
    a later run that needs an earlier start refetches rather than measuring a
    250 session window against 30 sessions of cached history and calling the
    result null. That failure would be invisible: a short window nulls itself
    honestly and looks exactly like a name with no history.

    GZIPPED, because four trading years of daily bars is about 110 KB a name
    and 1,590 names is 175 MB of a directory nothing but this reads. Written
    plain and packed in place through the shared writer, so a run interrupted
    between the two leaves a readable file either way.
    """
    path = cache_dir() / f"{symbol.replace('/', '_')}.json"
    if files.resolve_maybe_gz(path) is not None:
        try:
            cached = files.read_json_maybe_gz(path)
        except (OSError, ValueError):
            cached = None
        if isinstance(cached, dict) and cached.get("bars") is not None:
            covered_from = str(cached.get("from") or "")
            covered_to = str(cached.get("to") or "")
            if covered_from <= start.isoformat() and covered_to >= end.isoformat():
                return cached["bars"], None

    bars, error = api.eod(symbol, start=start, end=end)
    if error:
        return None, error
    if not bars:
        return None, "the end of day call returned no rows"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_name(path.name + ".gz").unlink(missing_ok=True)
    files.write_json_atomically(path, {
        "symbol": symbol, "from": start.isoformat(), "to": end.isoformat(),
        "fetched_at": ettime.now_et().isoformat(), "bars": bars})
    files.gzip_in_place(path)
    return bars, None


def _completed_before(bars: list[dict[str, Any]], session: str) -> list[dict[str, Any]]:
    """Every bar dated strictly before the session, in the order given.

    STRICTLY BEFORE. The session's own bar carries the high and low of the day
    the row is about, and a map that included it would let the session explain
    itself: a name that ran to a new high would show a position of 100 against
    a window that contains the run. That is the difference between describing
    the ground a gap happened on and describing the gap.
    """
    return [bar for bar in bars if str(bar.get("date") or "") < session]


def _basis_bar(bars: list[dict[str, Any]], session: str) -> dict[str, Any] | None:
    """The mapped session's own bar, or the last one at or before it.

    Used for its ADJUSTMENT FACTOR and for nothing else, which is why reading
    the row's own session here is not a look into the future: it says what
    money that session's prices were quoted in, which is the same question the
    pm_high on the row already answers. A session with no bar, a halt or a
    holiday the calendar disagrees about, falls back to the last one before it.
    """
    at_or_before = [bar for bar in bars if str(bar.get("date") or "") <= session]
    return at_or_before[-1] if at_or_before else None


def _no_price_reason(row: dict[str, Any], last_close: float | None) -> str:
    """Which of the two missing inputs left this row without a price.

    Two states a reader would act on differently: a row the morning never
    measured a gap for, and a series whose last completed bar carried no close.
    One sentence covering both would hide the second, which is a vendor fault
    and worth seeing.
    """
    if row.get("gap_pct") is None:
        return ("this row carries no gap_pct, so the premarket price the "
                "morning read cannot be reconstructed from it, and every "
                "reading that needs a price is null rather than measured "
                "against a substitute")
    return ("the last completed session before this one carried no close, so "
            "there is nothing to reconstruct a price against")


def rows_for_symbol(bars: list[dict[str, Any]],
                    rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The columns for every session of one symbol, keyed by session date.

    PURE, and that is what makes the point in time guarantee testable rather
    than asserted. It takes the whole series and does the slicing itself, so a
    claim can hand it a series truncated at the row's date and the full one and
    compare the two dictionaries value by value. See
    claim_a_backfilled_level_cannot_see_its_own_future.

    THE PRICE THE MAP IS READ AGAINST is reconstructed, and it is reconstructed
    from the row rather than from the bars. picks carries gap_pct, which the
    morning measured against the end of day prior close, so the premarket price
    that morning saw is the last completed close times one plus that gap. A
    ratio is basis free, so this lands on the same basis the levels are stated
    in whatever the vendor has adjusted since. A row with no gap_pct gets a map
    with no price in it: the levels are still facts, and position_pct, the
    moving average distances and the gap type are null with the map's own
    reasons rather than measured against a substitute.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        session = str(row["date"])
        history = _completed_before(bars, session)
        if not history:
            out[session] = structure.columns(
                None, reason=("no completed daily session before "
                              f"{session} is on file for this name"))
            continue
        basis = structure.basis_factor_of(_basis_bar(bars, session))
        adjusted, _ = structure.adjusted_series(history, basis)
        last_close = adjusted[-1]["close"] if adjusted else None
        gap_pct = row.get("gap_pct")
        price = (None if last_close is None or gap_pct is None
                 else round(last_close * (1.0 + float(gap_pct) / 100.0), 6))
        block = structure.measure(history, price, basis)
        out[session] = structure.columns(block, price_reason=None if price is not None
                                         else _no_price_reason(row, last_close))
    return out


def backfill(session: str | None = None, source: str | None = None,
             limit: int | None = None, refill: bool = False,
             dry_run: bool = False) -> dict[str, Any]:
    """Measure and write. Returns a record of what it did, for the caller to print."""
    history_days = _CRIT.integer("daily_structure", "history_calendar_days")
    report: dict[str, Any] = {
        "rows_wanted": 0, "symbols": 0, "rows_written": 0, "rows_mapped": 0,
        "rows_short": 0, "symbols_failed": 0, "calls": 0, "failures": [],
    }

    with store.session() as connection:
        store.init(connection)
        rows = _rows_to_fill(connection, session, source, refill)
    report["rows_wanted"] = len(rows)
    if not rows:
        return report

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_symbol.setdefault(str(row["ticker"]), []).append(row)
    symbols = sorted(by_symbol)
    if limit:
        symbols = symbols[:limit]
    report["symbols"] = len(symbols)
    if dry_run:
        report["dry_run"] = (
            f"would spend about {len(symbols)} eod call(s) at one credit each "
            f"to write {sum(len(by_symbol[s]) for s in symbols)} row(s)")
        return report

    # Before anything is spent, on the discover and scan precedent. A backfill
    # is skippable spend by definition: it describes sessions that are already
    # over and will describe them just as well tomorrow.
    quota = eodhd.preflight("backfill_structure")
    report["quota"] = quota
    if quota.get("refused") or quota.get("degraded"):
        report["refused"] = (
            "the shared key is at or below a level where this pass would be "
            "taking budget from a morning: " + eodhd.describe_preflight(quota))
        return report

    api = eodhd.client()
    written_at = ettime.now_et().isoformat()
    for index, symbol in enumerate(symbols, start=1):
        wanted = by_symbol[symbol]
        first = min(str(r["date"]) for r in wanted)
        last = max(str(r["date"]) for r in wanted)
        start = ettime.parse_date(first) - dt.timedelta(days=history_days)
        end = ettime.parse_date(last)
        bars, error = series_for(api, symbol, start, end)
        report["calls"] = eodhd.call_count()
        if error or not bars:
            # WRITTEN AS A REFUSAL, not left blank, on the
            # next_day_refused_reason precedent. The row selection is "rows
            # with no map", so a symbol the vendor cannot serve at all, a
            # delisting or a ticker reused since, would come back on every run
            # and spend one call each time to be told the same thing. A blank
            # means this pass has not reached the row; a reason means it
            # reached it and the vendor had nothing.
            report["symbols_failed"] += 1
            report["failures"].append(f"{symbol}: {error}")
            columns = {row["date"]: structure.columns(
                None, reason=(f"the end of day history for {symbol} is not "
                              f"served: {error}")) for row in wanted}
        else:
            columns = rows_for_symbol(bars, wanted)
        with store.session() as connection:
            store.init(connection)
            for row in wanted:
                record = dict(columns[str(row["date"])])
                record.update({
                    "date": row["date"], "ticker": symbol,
                    "ds_computed_at": written_at,
                    "ds_computed_by": COMPUTED_BY,
                    "short_interest_reason": NO_SHORT_INTEREST,
                })
                store.upsert(connection, "picks", ["date", "ticker"], record)
                report["rows_written"] += 1
                if record.get("ds_short_reason"):
                    report["rows_short"] += 1
                else:
                    report["rows_mapped"] += 1
            connection.commit()
        if index % 25 == 0 or index == len(symbols):
            print(f"backfill_structure: {index} of {len(symbols)} symbol(s), "
                  f"{report['rows_written']} row(s) written, "
                  f"{report['symbols_failed']} symbol(s) with no history")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", help="one session date, rather than all of them")
    parser.add_argument("--source", help="live, test or reconstructed")
    parser.add_argument("--limit", type=int, help="stop after this many symbols")
    parser.add_argument("--refill", action="store_true",
                        help="rewrite rows that already carry a map")
    parser.add_argument("--dry-run", action="store_true",
                        help="count the work and spend nothing")
    args = parser.parse_args(argv)

    report = backfill(session=args.session, source=args.source, limit=args.limit,
                      refill=args.refill, dry_run=args.dry_run)
    if report.get("refused"):
        print(f"backfill_structure: refused. {report['refused']}")
        return 1
    if report.get("dry_run"):
        print(f"backfill_structure: {report['rows_wanted']} row(s) over "
              f"{report['symbols']} symbol(s). {report['dry_run']}")
        return 0
    print(f"backfill_structure: {report['rows_written']} of {report['rows_wanted']} "
          f"row(s) written over {report['symbols']} symbol(s); "
          f"{report['rows_mapped']} carry a map, {report['rows_short']} carry a "
          f"reason instead, {report['symbols_failed']} symbol(s) had no history "
          "and their rows carry that as the reason rather than a blank")
    for failure in report["failures"][:10]:
        print(f"  no history  {failure}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
