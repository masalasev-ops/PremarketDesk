"""The paper ledger: what ONE written rule would have done with each pick.

CRITERIA.md [Paper] holds the rule and this module applies it. Nothing here
decides anything: entry, stop, exit, size and every refusal are read from that
section, and a rule that lives in code is a rule nobody can argue with.

WHY A LEDGER AND NOT MORE EXCURSIONS. mfe_pct is a BOUND, not a return. It says
how far the tape ran past a reference at its best moment, which a real rule
captures only with perfect exit timing and usually does not capture at all.
Reading it as a result is the most common way to be wrong with this table, and
CRITERIA has said so since the column existed: "not a simulation of any trade".
This module is the simulation, so mfe_pct can go back to being a diagnostic and
the two are reported on the same line.

THE SESSION IT TRADES IS THE PICK'S OWN, and that is NOT the session
night/fill_outcomes.py measures. The scan runs 08:45 on the pick date and the
report is about the open ninety minutes later, so the rule trades that open.
[Outcomes] fills next_day_open through mae_pct_true from the session AFTER
that one, and the session the report was actually about appears in none of
them. AXTI on 2026-08-27 is the plainest case: entry_ref 70.94, its own session
opened 70.30 and reached 70.85, a miss by 0.13 percent, while next_day_high is
65.4155 from 2026-08-28 and mfe_pct reads -7.79. Nothing in [Outcomes] is
changed by this module; it fetches its own bars for its own session and the
two horizons are kept apart on purpose.

IT BOOKS AGAINST THE MEASURED REFERENCES AND THE ALPACA TAPE. entry_ref and
stop_ref are the collector's raw live levels, which are the extremes of a
socket sample, and a ledger built on a level that was never available books a
P&L that is wrong from its first row. entry_ref_true and stop_ref_true are the
same references off the full SIP tape, and fill_plausible says whether that
level was a price anyone could have transacted at. A row that is not
'plausible' is SKIPPED WITH ITS REASON WRITTEN DOWN, never silently dropped.

    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger
    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger --date 2026-08-27
    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger --all
    PYTHONPATH=src .venv/Scripts/python.exe -m night.paper_ledger --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys
from typing import Any

import probe_alpaca

from core import criteria
from core import ettime
from core import store
from night import true_volume
from ops import job_status

_CRIT = criteria.load()

# Every column the ledger writes. store.ensure_table builds it from this, so
# the schema and the writer cannot drift apart.
LEDGER_COLUMNS = (
    ("date", "TEXT NOT NULL"),
    ("ticker", "TEXT NOT NULL"),
    # Rows are keyed on the rule version, so changing the rule books BESIDE
    # what the old one produced rather than over it. A ledger that overwrote
    # itself on every rule change could not answer whether the change helped.
    ("rule_version", "TEXT NOT NULL"),
    ("session", "TEXT"),
    # The screen's verdict, carried as a GROUPING column and never as a filter.
    # Booking only what the screen admitted makes "did the screen separate
    # outcomes" unaskable, and that is the question the ledger exists to feed.
    ("day_eligible", "INTEGER"),
    ("swing_eligible", "INTEGER"),
    ("conviction", "TEXT"),
    ("score", "REAL"),
    # 1 when a trade was taken. 0 covers both a skipped row and one whose
    # trigger never fired, and skip_reason and exit_reason say which.
    ("booked", "INTEGER"),
    ("skip_reason", "TEXT"),
    ("entry_ref_used", "REAL"),
    ("stop_ref_used", "REAL"),
    ("entry_at", "TEXT"),
    ("entry_price", "REAL"),
    ("exit_at", "TEXT"),
    ("exit_price", "REAL"),
    ("exit_reason", "TEXT"),
    ("shares", "INTEGER"),
    ("notional", "REAL"),
    # NULL, never zero, on a row that took no trade. A zero P&L is a flat
    # trade and a null one is no trade, and a median that mixes them is the
    # defect this project has now found under five other names.
    ("pnl", "REAL"),
    ("pnl_pct", "REAL"),
    ("max_drawdown_pct", "REAL"),
    ("bars_held", "INTEGER"),
    ("booked_at", "TEXT"),
)

EXIT_STOP = "stop"
EXIT_CLOSE = "session close"
EXIT_NEVER = "trigger never fired"


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def session_window(day: str) -> tuple[dt.datetime, dt.datetime]:
    """The regular session on the pick's OWN date, 09:30 to the close.

    The open comes from [Backfill] market_open because that is the same fact
    already written down once, and the close from [Paper] session_close. The
    rule trades regular hours only: the trigger level is a premarket high and
    premarket is precisely where item 2 measured the thin liquidity, so a rule
    that let itself fill there would book the fills fill_plausible exists to
    doubt.
    """
    date = ettime.parse_date(day)
    open_h, open_m = _CRIT.clock("backfill", "market_open")
    close_h, close_m = _CRIT.clock("paper", "session_close")
    return (dt.datetime(date.year, date.month, date.day, open_h, open_m,
                        tzinfo=ettime.ET),
            dt.datetime(date.year, date.month, date.day, close_h, close_m,
                        tzinfo=ettime.ET))


def simulate(bars: list[dict[str, Any]], entry_level: float, stop_level: float,
             notional: float) -> dict[str, Any]:
    """Apply the rule to one session's minutes. Returns what it did and why.

    Reads the bars in ORDER, which is the whole reason this fetches one minute
    data instead of using the end of day bar already in picks. An OHLC bar
    cannot say whether its high came before its low, so it cannot say whether a
    stop was reached before a target, and every ledger built on one is
    answering a question the data does not contain.

    THE SAME MINUTE CASE IS BOOKED AS A LOSS. A minute whose high reaches the
    trigger and whose low reaches the stop carries no sequence inside it, so
    the order is unknowable. The losing reading is taken because the flattering
    one is a choice that would show up in every summary this table feeds.

    A trigger that never fires books NO TRADE and a NULL P&L. Zero would read
    as a flat trade, and those are different facts.
    """
    out: dict[str, Any] = {
        "booked": 0, "entry_at": None, "entry_price": None,
        "exit_at": None, "exit_price": None, "exit_reason": EXIT_NEVER,
        "shares": None, "notional": None, "pnl": None, "pnl_pct": None,
        "max_drawdown_pct": None, "bars_held": None,
    }
    entry_price = None
    entry_index = None
    for index, bar in enumerate(bars):
        high, low = _as_float(bar.get("h")), _as_float(bar.get("l"))
        opened = _as_float(bar.get("o"))
        if high is None or low is None or opened is None:
            continue
        if high >= entry_level:
            # A session that gaps straight through the resting order fills at
            # the open, not at the level. That is the honest treatment and the
            # common case for a gap candidate, and the flattering alternative
            # would book the level every time.
            entry_price = max(entry_level, opened)
            entry_index = index
            out["entry_at"] = str(bar.get("t") or "")
            break
    if entry_price is None or entry_index is None:
        return out

    shares = int(notional // entry_price)
    if shares < 1:
        # One share costs more than the whole position. Not a trade, and not a
        # zero either: the rule could not be applied at this size.
        out["exit_reason"] = (
            f"one share costs {entry_price:,.2f} and the position is "
            f"{notional:,.0f}, so the rule cannot be applied at this size")
        return out

    lowest = None
    exit_price = None
    exit_at = None
    exit_reason = EXIT_CLOSE
    held = 0
    for bar in bars[entry_index:]:
        high, low = _as_float(bar.get("h")), _as_float(bar.get("l"))
        close = _as_float(bar.get("c"))
        if low is None or high is None:
            continue
        held += 1
        lowest = low if lowest is None else min(lowest, low)
        if low <= stop_level:
            exit_price = stop_level
            exit_at = str(bar.get("t") or "")
            exit_reason = EXIT_STOP
            break
        if close is not None:
            exit_price, exit_at = close, str(bar.get("t") or "")
    if exit_price is None:
        # Entered on a bar with no readable close and nothing after it. The
        # trade is open at the end of the data, which is not a result.
        out["exit_reason"] = (
            "the session's minutes end with the position still open, so there "
            "is no exit price and the trade is not booked")
        return out

    out.update({
        "booked": 1,
        "entry_price": round(entry_price, 4),
        "exit_at": exit_at, "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "shares": shares, "notional": round(shares * entry_price, 2),
        "pnl": round((exit_price - entry_price) * shares, 2),
        "pnl_pct": round((exit_price - entry_price) / entry_price * 100.0, 4),
        "max_drawdown_pct": (
            round((lowest - entry_price) / entry_price * 100.0, 4)
            if lowest is not None else None),
        "bars_held": held,
    })
    return out


def book(day: str, probe: Any = None) -> dict[str, Any]:
    """Every live pick of one session, put through the rule. Writes nothing."""
    version = _CRIT.text("paper", "rule_version")
    notional = _CRIT.number("paper", "position_notional")
    with store.session() as connection:
        store.init(connection)
        rows = [dict(row) for row in connection.execute(
            "SELECT ticker, day_eligible, swing_eligible, conviction, score, "
            "entry_ref_true, stop_ref_true, fill_plausible, "
            "fill_plausible_reason FROM picks "
            "WHERE date=? AND source='live' ORDER BY ticker", (day,))]
    if not rows:
        return {"day": day, "rows": [], "skipped": "no live picks rows",
                "version": version}

    start, end = session_window(day)
    stamp = ettime.stamp(ettime.now_et())
    window_text = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

    # Only the rows the rule will actually trade are fetched. A skipped row
    # needs no bars, and the skip is decided from columns already in the table.
    tradeable = [r for r in rows
                 if r["fill_plausible"] == true_volume.FILL_PLAUSIBLE
                 and r["entry_ref_true"] is not None
                 and r["stop_ref_true"] is not None]
    bare = {r["ticker"]: r["ticker"].split(".", 1)[0] for r in rows}
    bars: dict[str, list[dict[str, Any]]] = {}
    error = None
    if tradeable:
        probe = probe if probe is not None else probe_alpaca.Probe()
        bars, error = true_volume.fetch_bars(
            probe, sorted({bare[r["ticker"]] for r in tradeable}), start, end)

    out: list[dict[str, Any]] = []
    for row in rows:
        record: dict[str, Any] = {
            "date": day, "ticker": row["ticker"], "rule_version": version,
            "session": window_text,
            "day_eligible": row["day_eligible"],
            "swing_eligible": row["swing_eligible"],
            "conviction": row["conviction"], "score": row["score"],
            "booked": 0, "skip_reason": None,
            "entry_ref_used": row["entry_ref_true"],
            "stop_ref_used": row["stop_ref_true"],
            "entry_at": None, "entry_price": None, "exit_at": None,
            "exit_price": None, "exit_reason": None, "shares": None,
            "notional": None, "pnl": None, "pnl_pct": None,
            "max_drawdown_pct": None, "bars_held": None,
            "booked_at": stamp,
        }
        # WRITTEN WITH ITS REASON, never dropped. A pick that vanishes from
        # the ledger is one nobody can ask about later, and the count of rows
        # the rule declined is as much a result as the ones it took.
        if row["fill_plausible"] != true_volume.FILL_PLAUSIBLE:
            record["skip_reason"] = (
                f"fill_plausible is {row['fill_plausible']!r}, not "
                f"{true_volume.FILL_PLAUSIBLE!r}: "
                f"{row['fill_plausible_reason'] or 'no reason recorded'}")
        elif row["entry_ref_true"] is None or row["stop_ref_true"] is None:
            record["skip_reason"] = (
                "no measured entry or stop reference, so the rule has no level "
                "to trigger on. The sampled entry_ref is NOT substituted: it "
                "is the number the measured one exists to be compared against")
        elif error:
            record["skip_reason"] = (
                f"the session's minutes could not be fetched ({error}), so "
                "nothing is known about what the rule would have done")
        else:
            record.update(simulate(
                bars.get(bare[row["ticker"]]) or [],
                float(row["entry_ref_true"]), float(row["stop_ref_true"]),
                notional))
            if not (bars.get(bare[row["ticker"]]) or []):
                record["skip_reason"] = (
                    f"alpaca returned no minutes for {window_text}, so the "
                    "rule was not applied rather than read as no trigger")
                record["exit_reason"] = None
        out.append(record)
    return {"day": day, "rows": out, "skipped": None, "version": version,
            "session": window_text, "fetch_error": error,
            "requests": getattr(probe, "request_count", 0)}


def write(result: dict[str, Any], dry_run: bool = False) -> int:
    """Upsert on (date, ticker, rule_version). A re-run replaces its own rows.

    Keyed on the rule version, so bumping [Paper] rule_version books a second
    set beside the first rather than over it. Re-running the SAME version is an
    update, because it is the same rule over the same tape and a second copy of
    it would be a duplicate rather than a second observation.
    """
    if dry_run or not result["rows"]:
        return 0
    with store.session() as connection:
        store.init(connection)
        # The table is in store's own schema and store.init creates it, so
        # there is one place a column is declared. LEDGER_COLUMNS below is the
        # writer's list and a claim holds the two in step.
        for record in result["rows"]:
            store.upsert(connection, "paper_trades",
                         ["date", "ticker", "rule_version"], record)
        connection.commit()
    return len(result["rows"])


def report(result: dict[str, Any]) -> None:
    if result.get("skipped"):
        print(f"paper: nothing booked for {result['day']}: {result['skipped']}")
        return
    rows = result["rows"]
    booked = [r for r in rows if r["booked"]]
    print(f"paper: {result['day']} under rule {result['version']} over "
          f"{result['session']}, {len(booked)} of {len(rows)} live picks "
          f"traded, {result.get('requests', 0)} alpaca requests, no EODHD quota")
    print(f"  {'ticker':<10} {'trigger':>10} {'stop':>10} {'entry':>10} "
          f"{'exit':>10} {'why':>14} {'pnl':>10} {'pnl %':>8} {'drawdn':>8}")
    for record in rows:
        if not record["booked"]:
            continue
        print(f"  {record['ticker']:<10} {record['entry_ref_used']:>10} "
              f"{record['stop_ref_used']:>10} {record['entry_price']:>10} "
              f"{record['exit_price']:>10} {record['exit_reason']:>14} "
              f"{record['pnl']:>10,.2f} {record['pnl_pct']:>+7.2f}% "
              f"{record['max_drawdown_pct']:>+7.2f}%")
    for record in rows:
        if record["booked"]:
            continue
        why = record["skip_reason"] or record["exit_reason"] or "no reason"
        print(f"  {record['ticker']:<10} not traded: {why}")


def ledger_report() -> None:
    """The one line the report can carry, and the diagnostics beside it.

    THE RULE VERSION IS NAMED because a P&L without the rule that produced it
    is not a number anybody can act on or argue with.

    BOTH DENOMINATORS, because twelve names from one morning share a tape and
    are one observation. Every summary here prints rows and sessions.

    mfe_pct_true SITS BESIDE THE BOOKED P&L, which is the point of the ledger.
    The bound is what was available at the tape's best moment and the booking
    is what one written rule captured, and the gap between them is what a
    target would have been trying to take. They are also measured over
    DIFFERENT SESSIONS, which is stated on the line rather than left to be
    discovered: the ledger trades the pick's own session and [Outcomes]
    measures the one after it.
    """
    with store.session() as connection:
        store.init(connection)
        rows = [dict(row) for row in connection.execute(
            "SELECT p.*, k.mfe_pct_true, k.mae_pct_true FROM paper_trades p "
            "LEFT JOIN picks k ON k.date=p.date AND k.ticker=p.ticker")]
    if not rows:
        print("paper: the ledger is empty")
        return

    by_version: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_version.setdefault(row["rule_version"], []).append(row)

    print("")
    for version, held in sorted(by_version.items()):
        booked = [r for r in held if r["booked"] and r["pnl_pct"] is not None]
        sessions = len({r["date"] for r in held})
        skipped = [r for r in held if r["skip_reason"]]
        never = [r for r in held
                 if not r["booked"] and not r["skip_reason"]]
        if not booked:
            print(f"paper: rule {version} booked NO trades across "
                  f"{len(held)} picks in {sessions} session(s). "
                  f"{len(skipped)} skipped, {len(never)} never triggered.")
            continue
        wins = [r for r in booked if r["pnl_pct"] > 0]
        drawdowns = [r["max_drawdown_pct"] for r in booked
                     if r["max_drawdown_pct"] is not None]
        # THE ONE LINE. Rule version, both denominators, median booked P&L,
        # win rate, worst drawdown. The drawdown clause is appended rather than
        # made a condition on the whole line: written the other way round the
        # `if` bound to the entire f-string, so a ledger with no readable
        # drawdown printed a BLANK LINE instead of the summary.
        worst = (f", worst drawdown {min(drawdowns):+.2f}%" if drawdowns
                 else ", worst drawdown unknown, no row carries one")
        print(f"paper: rule {version} booked {len(booked)} trades from "
              f"{len(held)} picks across {sessions} session(s): median "
              f"{statistics.median(r['pnl_pct'] for r in booked):+.2f}%, "
              f"win rate {len(wins)}/{len(booked)}{worst}")
        print(f"  not traded: {len(skipped)} skipped on evidence, "
              f"{len(never)} never reached the trigger")
        stopped = [r for r in booked if r["exit_reason"] == EXIT_STOP]
        print(f"  exits: {len(stopped)} stopped, "
              f"{len(booked) - len(stopped)} held to the close")
        print(f"  median booked P&L "
              f"{statistics.median(r['pnl'] for r in booked):+,.2f} dollars on "
              f"a {_CRIT.number('paper', 'position_notional'):,.0f} position")

        paired = [r for r in booked if r["mfe_pct_true"] is not None]
        if paired:
            print(f"  beside it, mfe_pct_true over the SAME picks: median "
                  f"{statistics.median(r['mfe_pct_true'] for r in paired):+.2f}%"
                  f" over n={len(paired)}. That is a BOUND at the tape's best "
                  "moment, on the session AFTER the one the rule traded, and "
                  "it is not a return.")


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the CRITERIA [Paper] rule to each live pick.")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                        help="The session to book. Defaults to today.")
    parser.add_argument("--all", action="store_true",
                        help="Book every session with live picks rows.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apply the rule and print, write nothing.")
    args = parser.parse_args(argv)

    if args.all:
        with store.session() as connection:
            store.init(connection)
            days = [row[0] for row in connection.execute(
                "SELECT DISTINCT date FROM picks WHERE source='live' "
                "ORDER BY date")]
    else:
        days = [args.date or ettime.today_str()]

    written = 0
    for day in days:
        result = book(day)
        written += write(result, dry_run=args.dry_run)
        report(result)
    if not args.dry_run:
        ledger_report()
    job_status.produced("paper trades booked", written)
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("paper", main, ok_codes=OK_CODES))
