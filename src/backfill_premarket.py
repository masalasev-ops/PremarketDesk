"""Nightly true premarket backfill, run after 22:00 ET.

The morning's pm_high, pm_low and pm_vwap describe what the collector saw
from its 07:20 start. The true premarket session runs from 04:00, and EODHD's
one minute intraday bars cover all of it, published a few hours behind live.
So every evening this job writes pm_high_true, pm_low_true and pm_vwap_true
into the day's picks, next to the morning values, never over them.

The two sets of columns are the point. Their difference is the standing
measurement of what a 07:20 collector start misses, reported here as a median
and worst case over recent sessions. A true high LOWER than the live high
should not happen if both sources saw the same tape, since the true window
contains the collector window, but the trades websocket and the published
bars can legitimately differ on odd lots, condition codes, and late
corrections. So the shortfall is recorded as a magnitude, a percentage in
pm_source_disagreement, small values reading as feed noise and large ones as
a bad bar worth chasing, and the morning value is never silently corrected.

While it is here with the intraday feed open, this job also runs the
definitive collector volume check, verify_against_intraday, and writes the
result into the day's run directory for the record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

import collect_premarket
import config
import criteria
import eodhd
import ettime
import store

_CRIT = criteria.load()

_TRUE_COLUMNS = (
    ("pm_high_true", "REAL"),
    ("pm_low_true", "REAL"),
    ("pm_vwap_true", "REAL"),
    ("pm_true_bars", "INTEGER"),
    # The percentage by which the true high undercuts the live high. NULL
    # means the backfill has not checked this row (or could not, both highs
    # are needed); 0.0 means checked and clean. A magnitude, not a boolean:
    # feed noise and bad bars both trip a boolean, and then nobody can tell
    # them apart. Queries counting clean rows must test = 0.0, never IS NULL.
    ("pm_source_disagreement", "REAL"),
    ("backfilled_at", "TEXT"),
)


def _window(day: str) -> tuple[dt.datetime, dt.datetime]:
    date = ettime.parse_date(day)
    open_h, open_m = _CRIT.clock("baseline", "session_start")
    close_h, close_m = _CRIT.clock("backfill", "market_open")
    start = dt.datetime(date.year, date.month, date.day, open_h, open_m, tzinfo=ettime.ET)
    end = dt.datetime(date.year, date.month, date.day, close_h, close_m, tzinfo=ettime.ET)
    return start, end


def _true_path(api: eodhd.EodhdClient, symbol: str, day: str) -> tuple[dict[str, Any] | None, str | None]:
    """(row, error). High, low and a VWAP proxy over the true premarket window.

    The VWAP proxy is sum(hlc3 * volume) / sum(volume) over the one minute
    bars, the standard bar approximation of a trade level VWAP. It is labelled
    a proxy by its column being _true alongside the collector's trade exact
    value, and the two are expected to differ a little even on a full window.
    """
    start, end = _window(day)
    rows, error = api.intraday(symbol, start, end, "1m")
    if error:
        return None, error
    start_epoch, end_epoch = ettime.epoch_s(start), ettime.epoch_s(end)

    high = low = None
    volume_sum = 0.0
    price_volume = 0.0
    bars = 0
    for row in rows or []:
        stamp = row.get("timestamp")
        if stamp is None or not (start_epoch <= int(stamp) < end_epoch):
            continue
        bar_high = row.get("high")
        bar_low = row.get("low")
        bar_close = row.get("close")
        bar_volume = float(row.get("volume") or 0)
        if bar_high is None or bar_low is None or bar_close is None:
            continue
        bars += 1
        high = float(bar_high) if high is None else max(high, float(bar_high))
        low = float(bar_low) if low is None else min(low, float(bar_low))
        typical = (float(bar_high) + float(bar_low) + float(bar_close)) / 3.0
        price_volume += typical * bar_volume
        volume_sum += bar_volume

    if bars == 0:
        return None, "intraday returned no bars inside the premarket window"
    return {
        "pm_high_true": round(high, 4) if high is not None else None,
        "pm_low_true": round(low, 4) if low is not None else None,
        "pm_vwap_true": round(price_volume / volume_sum, 4) if volume_sum else None,
        "pm_true_bars": bars,
    }, None


def _gap_report(connection, sessions: int) -> None:
    """Median and worst case gap between the true and live premarket highs."""
    rows = connection.execute(
        """
        SELECT date, ticker, pm_high, pm_high_true FROM picks
        WHERE pm_high IS NOT NULL AND pm_high_true IS NOT NULL AND source='live'
          AND date IN (SELECT DISTINCT date FROM picks WHERE source='live'
                       ORDER BY date DESC LIMIT ?)
        """,
        (sessions,),
    ).fetchall()
    gaps = [
        (row["pm_high_true"] - row["pm_high"]) / row["pm_high"] * 100.0
        for row in rows
        if row["pm_high"]
    ]
    if not gaps:
        print("backfill: no rows with both a live and a true premarket high yet, no gap report")
        return
    ordered = sorted(gaps)
    median = ordered[len(ordered) // 2]
    worst = max(gaps, key=abs)
    print(
        f"backfill: over the last {sessions} sessions ({len(gaps)} live rows), the "
        f"true premarket high exceeds the live one by median {median:+.2f} percent, "
        f"worst case {worst:+.2f} percent"
    )


def backfill(day: str) -> int:
    api = eodhd.client()
    with store.session() as connection:
        store.init(connection)
        added = store.ensure_columns(connection, "picks", _TRUE_COLUMNS)
        if added:
            print(f"backfill: widened picks with {', '.join(added)}")

        # source = 'live' only: true premarket columns are outcome evidence,
        # and spending intraday calls widening test rows would pollute the
        # record this table exists to build.
        picks = connection.execute(
            "SELECT * FROM picks WHERE date=? AND source='live' ORDER BY ticker",
            (day,),
        ).fetchall()
        if not picks:
            print(f"backfill: no live picks for {day} (test rows are not backfilled), "
                  "nothing to do")
            return 0

        filled = disagreements = failed = 0
        now_stamp = ettime.stamp(ettime.now_et())
        for pick in picks:
            ticker = pick["ticker"]
            true_row, error = _true_path(api, ticker, day)
            if error:
                print(f"backfill: {ticker} left alone: {error}")
                failed += 1
                continue

            live_high = pick["pm_high"]
            true_high = true_row["pm_high_true"]
            disagree = None
            if live_high is not None and true_high is not None and live_high > 0:
                shortfall = (live_high - true_high) / live_high * 100.0
                disagree = round(shortfall, 4) if shortfall > 0 else 0.0
                if disagree > 0:
                    disagreements += 1
                    print(
                        f"backfill: SOURCE DISAGREEMENT {ticker}: true high {true_high} is "
                        f"{disagree:.4f} percent below the live collector high {live_high}. "
                        "The true window contains the collector window, so this is a feed "
                        "difference or a bad bar. Recorded, nothing overwritten."
                    )

            connection.execute(
                """
                UPDATE picks SET pm_high_true=?, pm_low_true=?, pm_vwap_true=?,
                    pm_true_bars=?, pm_source_disagreement=?, backfilled_at=?
                WHERE date=? AND ticker=?
                """,
                (
                    true_row["pm_high_true"], true_row["pm_low_true"],
                    true_row["pm_vwap_true"], true_row["pm_true_bars"],
                    disagree, now_stamp, day, ticker,
                ),
            )
            filled += 1
        connection.commit()

        print(f"backfill: {filled} of {len(picks)} picks filled for {day}, "
              f"{disagreements} source disagreements, {failed} unavailable")
        _gap_report(connection, _CRIT.integer("backfill", "gap_report_sessions"))

    # The definitive collector volume check, for the record.
    summary = collect_premarket.verify_against_intraday(day, quiet=True)
    if summary is not None:
        verify_path = config.run_dir(day) / "verify_intraday.json"
        verify_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"backfill: collector volume verification written to {verify_path}")
    else:
        print("backfill: collector volume verification had nothing to compare")
    return 0


def _catchup_dates(before_day: str, limit: int) -> list[str]:
    """Recent prior sessions whose picks still lack a true premarket high.

    The vendor sometimes publishes intraday later than the nightly runs, and
    a day the nightly could not fill must not stay unfilled forever just
    because the calendar moved on.
    """
    with store.session() as connection:
        store.init(connection)
        rows = connection.execute(
            "SELECT DISTINCT date FROM picks WHERE date < ? AND pm_high_true IS NULL "
            "AND source='live' ORDER BY date DESC LIMIT ?",
            (before_day, limit),
        ).fetchall()
    return [row["date"] for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the true premarket window into picks.")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=ettime.today_et().isoformat(),
                        help="Session to backfill. Defaults to today in ET.")
    parser.add_argument("--no-catchup", action="store_true",
                        help="Only the named day, no sweep of unfilled prior days.")
    args = parser.parse_args(argv)
    result = backfill(args.date)
    if not args.no_catchup:
        for day in _catchup_dates(args.date, _CRIT.integer("backfill", "catchup_days")):
            print(f"backfill: catching up {day}, its true premarket columns are still null")
            backfill(day)
    return result


if __name__ == "__main__":
    sys.exit(main())
