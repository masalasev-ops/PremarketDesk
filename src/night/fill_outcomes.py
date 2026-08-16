"""Nightly outcome fill: what actually happened after each pick.

CRITERIA.md opens by saying its thresholds are unvalidated seed values, and
this module is the other half of that sentence. Every pick eventually gets
next session and fifth session outcomes written next to the morning's
references, and once a few hundred rows exist the thresholds can be moved
because the data said so.

Trading sessions are counted on the session calendar symbol's end of day
history, never weekday arithmetic. A Monday holiday makes Friday plus one
land on Tuesday, and weekday math would quietly compare against a day the
market never traded.

Idempotent by construction: a row is only written when it still has an
outcome column null that the calendar says should be fillable, and a second
run straight after the first finds nothing left to do and changes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from core import criteria
from core import eodhd
from core import ettime
from ops import job_status
from core import store

_CRIT = criteria.load()

_OUTCOME_COLUMNS = (
    ("next_day_open", "REAL"),
    ("next_day_high", "REAL"),
    ("next_day_low", "REAL"),
    ("next_day_close", "REAL"),
    ("day5_close", "REAL"),
    ("pm_high_broke_next_day", "INTEGER"),
    ("mfe_pct", "REAL"),
    ("mae_pct", "REAL"),
    ("outcomes_filled_at", "TEXT"),
)


def _session_calendar(api: eodhd.EodhdClient, back_days: int = 40) -> list[str]:
    """Real trading sessions, oldest first, from the calendar symbol's EOD bars."""
    symbol = _CRIT.text("universe", "session_calendar_symbol")
    today = ettime.today_et()
    bars, error = api.eod(symbol, start=today - dt.timedelta(days=back_days), end=today)
    if error or not bars:
        raise RuntimeError(f"session calendar unavailable from {symbol}: {error or 'no rows'}")
    return [str(b["date"]) for b in bars if b.get("date")]


def _sessions_after(calendar: list[str], date: str, count: int) -> list[str]:
    """The next `count` sessions strictly after `date`, or fewer if not elapsed."""
    later = [d for d in calendar if d > date]
    return later[:count]


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def fill(day_limit: str | None = None) -> int:
    short_n = _CRIT.integer("outcomes", "horizon_sessions_short")
    long_n = _CRIT.integer("outcomes", "horizon_sessions_long")
    api = eodhd.client()

    # Read, then fetch, then write. Three phases on purpose: a transaction must
    # never span a network call, because one held open across an end of day
    # request per pick locks the database for the length of the job and every
    # other writer fails with "database is locked" for reasons that have
    # nothing to do with it. See conftest.py for the incidents that taught this.
    with store.session() as connection:
        store.init(connection)
        added = store.ensure_columns(connection, "picks", _OUTCOME_COLUMNS)
        # source = 'live' only: outcomes are the record the thresholds will
        # one day be calibrated against, and test rows have no business in it.
        candidates = [dict(row) for row in connection.execute(
            "SELECT * FROM picks WHERE (next_day_close IS NULL OR day5_close IS NULL) "
            "AND source='live' ORDER BY date, ticker"
        ).fetchall()]

    if added:
        print(f"outcomes: widened picks with {', '.join(added)}")
    if not candidates:
        print("outcomes: every live pick already has its outcomes "
              "(test rows are never filled), nothing to do")
        job_status.produced("picks filled", 0)
        return 0

    calendar = _session_calendar(api, back_days=40)
    filled = skipped = unavailable = 0
    now_stamp = ettime.stamp(ettime.now_et())
    writes: list[tuple[dict[str, Any], str, str]] = []

    if True:
        for pick in candidates:
            date, ticker = pick["date"], pick["ticker"]
            if day_limit and date > day_limit:
                skipped += 1
                continue
            next_sessions = _sessions_after(calendar, date, long_n)
            wants_short = pick["next_day_close"] is None and len(next_sessions) >= short_n
            wants_long = pick["day5_close"] is None and len(next_sessions) >= long_n
            if not wants_short and not wants_long:
                skipped += 1
                continue

            window_end = ettime.parse_date(next_sessions[-1])
            bars, error = api.eod(ticker, start=ettime.parse_date(date), end=window_end)
            if error or not bars:
                print(f"outcomes: {ticker} {date} left alone: {error or 'no end of day rows'}")
                unavailable += 1
                continue
            by_date = {str(b.get("date")): b for b in bars}

            updates: dict[str, Any] = {}
            if wants_short:
                next_bar = by_date.get(next_sessions[short_n - 1])
                if next_bar is None:
                    print(f"outcomes: {ticker} {date} has no bar on {next_sessions[short_n - 1]}, "
                          "possibly halted or delisted, left null")
                    unavailable += 1
                else:
                    next_open = _as_float(next_bar.get("open"))
                    next_high = _as_float(next_bar.get("high"))
                    next_low = _as_float(next_bar.get("low"))
                    updates["next_day_open"] = next_open
                    updates["next_day_high"] = next_high
                    updates["next_day_low"] = next_low
                    updates["next_day_close"] = _as_float(next_bar.get("close"))

                    pm_high = pick["pm_high"]
                    if pm_high is not None and next_high is not None:
                        updates["pm_high_broke_next_day"] = int(next_high > pm_high)

                    entry_ref, stop_ref = pick["entry_ref"], pick["stop_ref"]
                    if entry_ref and next_high is not None:
                        updates["mfe_pct"] = round((next_high - entry_ref) / entry_ref * 100.0, 4)
                    if stop_ref and next_low is not None:
                        updates["mae_pct"] = round((next_low - stop_ref) / stop_ref * 100.0, 4)

            if wants_long:
                day5_bar = by_date.get(next_sessions[long_n - 1])
                if day5_bar is not None:
                    updates["day5_close"] = _as_float(day5_bar.get("close"))

            if not updates:
                skipped += 1
                continue
            updates["outcomes_filled_at"] = now_stamp
            writes.append((updates, date, ticker))
            filled += 1

    with store.session() as connection:
        for updates, date, ticker in writes:
            assignments = ", ".join(f"{column}=?" for column in updates)
            connection.execute(
                f"UPDATE picks SET {assignments} WHERE date=? AND ticker=?",
                [*updates.values(), date, ticker],
            )
        connection.commit()

        # Rows are not observations. Candidates from one morning share the
        # same tape, so the sample unit for any threshold analysis is the
        # session, and both counts are reported so nobody mistakes twelve
        # correlated rows for twelve data points.
        total_rows, total_sessions = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT date) FROM picks "
            "WHERE next_day_close IS NOT NULL AND source='live'"
        ).fetchone()
        job_status.produced("picks filled", filled)
        print(f"outcomes: {filled} picks filled, {skipped} not yet due, "
              f"{unavailable} had no data")
        print(f"outcomes: the table now holds {total_rows} live outcome rows across "
              f"{total_sessions} sessions; the sample unit is the session")
    return 0


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill pick outcomes from end of day history.")
    parser.add_argument("--before", metavar="YYYY-MM-DD", default=None,
                        help="Only consider picks dated on or before this date.")
    args = parser.parse_args(argv)
    return fill(args.before)


if __name__ == "__main__":
    sys.exit(job_status.run("outcomes", main, ok_codes=OK_CODES))
