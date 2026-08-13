"""Nightly true premarket backfill, run after 22:00 ET.

The morning's pm_high, pm_low and pm_vwap describe what the collector saw
from its 07:20 start. The true premarket session runs from 04:00, and EODHD's
one minute intraday bars cover all of it, published a few hours behind live.
So every evening this job writes pm_high_true, pm_low_true and pm_vwap_true
into the day's picks, next to the morning values, never over them.

The two sets of columns are the point. Their difference is the standing
measurement of what a 07:20 collector start misses, reported here as a median
and worst case over recent sessions. A true high LOWER than the live high is
geometrically impossible, the true window contains the collector window, so
any such row is flagged as a source disagreement and left for a human, the
morning value never silently corrected.

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
    ("pm_source_disagreement", "INTEGER"),
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
        WHERE pm_high IS NOT NULL AND pm_high_true IS NOT NULL
          AND date IN (SELECT DISTINCT date FROM picks ORDER BY date DESC LIMIT ?)
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
        f"backfill: over the last {sessions} sessions ({len(gaps)} rows), the true "
        f"premarket high exceeds the live one by median {median:+.2f} percent, "
        f"worst case {worst:+.2f} percent"
    )


def backfill(day: str) -> int:
    api = eodhd.client()
    with store.connect() as connection:
        store.init(connection)
        added = store.ensure_columns(connection, "picks", _TRUE_COLUMNS)
        if added:
            print(f"backfill: widened picks with {', '.join(added)}")

        picks = connection.execute(
            "SELECT * FROM picks WHERE date=? ORDER BY ticker", (day,)
        ).fetchall()
        if not picks:
            print(f"backfill: no picks for {day}, nothing to do")
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
            disagree = 0
            if live_high is not None and true_high is not None and true_high + 1e-6 < live_high:
                disagree = 1
                disagreements += 1
                print(
                    f"backfill: SOURCE DISAGREEMENT {ticker}: true high {true_high} is "
                    f"below the live collector high {live_high}. The true window is a "
                    "superset, so one of the sources is wrong. Flagged, nothing overwritten."
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the true premarket window into picks.")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=ettime.today_et().isoformat(),
                        help="Session to backfill. Defaults to today in ET.")
    args = parser.parse_args(argv)
    return backfill(args.date)


if __name__ == "__main__":
    sys.exit(main())
