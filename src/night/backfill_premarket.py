"""Nightly true premarket backfill, run after 22:00 ET.

The morning's pm_high, pm_low and pm_vwap describe what the collector saw
from its 07:20 start. The true premarket session runs from 04:00, and EODHD's
one minute intraday bars cover all of it, published a few hours behind live.
So every evening this job writes pm_high_true, pm_low_true and pm_vwap_true
into the day's picks, next to the morning values, never over them.

The two sets of columns are the point, and until 2026-08-28 this paragraph
claimed more for them than they hold. Their difference was called "the standing
measurement of what a 07:20 collector start misses". It is not: it conflates
THREE causes and cannot separate them.

  1. The collector's late start, 04:00 to 07:20, which is the one this
     sentence named.
  2. A feed disagreement INSIDE the shared window, where the vendor's bars and
     the trades socket disagree over minutes both of them saw.
  3. The window END. The true window ran to [backfill] market_open, 09:30,
     while the morning's pm_high stops at the scan cutoff, 08:45. Nothing
     after 08:45 can be in a report written at 08:45, so that stretch is not
     something the collector missed, it is something the report is not about.

Measured on 2026-08-20, four names, three different causes: AAP's true high of
58.00 against a live 48.34 came from 04:00 to 07:20 and is cause 1; SCSC's
64.85 against 59.82 came from 08:45 to 09:30 and is cause 3; and WMT's 116.695
against 108.00 came from 07:20 to 08:45, the minutes the collector was
listening to, and is cause 2 with the other two contributing nothing.

night/true_volume.py had already reasoned this out for volume and ends its
window at the packet's own rvol_cutoff_hhmm for exactly this reason. This
module predates that and never got it. So the true path is now computed TWICE
over the same fetched bars, once over the full premarket session and once over
the collector's own window, and the pm_*_collector_window columns are what
make the three causes separable: full against collector window is what the
window bounds cost, and collector window against the live value is the feed
disagreement on identical minutes, which is the only one of the three that is
a statement about the collector.

A true high LOWER than the live high
should not happen if both sources saw the same tape, since the true window
contains the collector window, but the trades websocket and the published
bars can legitimately differ on odd lots, condition codes, and late
corrections. So the shortfall is recorded as a magnitude, a percentage in
pm_source_disagreement, small values reading as feed noise and large ones as
a bad bar worth chasing, and the morning value is never silently corrected.

While it is here with the intraday feed open, this job also runs the
definitive collector volume check, verify_against_intraday, and writes the
result into the day's run directory for the record. That check runs FIRST and
independently of picks, because it reads the collector bar file rather than the
table, and gating an instrument on the thing it measures is how it stopped
being taken at all when picks was emptied on 2026-08-19.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

from collect import collect_premarket
from core import config
from core import criteria
from core import eodhd
from core import ettime
from ops import job_status
from core import store

_CRIT = criteria.load()

# A premarket bar file is named for its session. Matched rather than parsed so
# the stats and subscriptions sidecars in the same directory are never mistaken
# for one, and neither is anything a human drops there.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The artifact's name, taken from the module that reads it rather than spelled
# again here, because these two modules disagreeing about that file is the whole
# of the defect _has_measurement below exists to close.
VOLUME_CHECK_FILE = collect_premarket.VOLUME_CHECK_FILE

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
    # The same three values over the COLLECTOR'S OWN window, 07:20 to the scan
    # cutoff, from the same bars in the same pass at no extra call. Without
    # these the difference between live and true is one number covering three
    # causes; with them it decomposes. See the module docstring.
    ("pm_high_collector_window", "REAL"),
    ("pm_low_collector_window", "REAL"),
    ("pm_vwap_collector_window", "REAL"),
    ("pm_collector_window_bars", "INTEGER"),
    # What that window actually was on this row, never assumed by a reader.
    # The morning's cutoff snaps to [Scan] run_time only inside
    # rvol_cutoff_snap_minutes, so a rerun genuinely has a different clock.
    ("pm_collector_window", "TEXT"),
    ("backfilled_at", "TEXT"),
)


def _window(day: str) -> tuple[dt.datetime, dt.datetime]:
    date = ettime.parse_date(day)
    open_h, open_m = _CRIT.clock("baseline", "session_start")
    close_h, close_m = _CRIT.clock("backfill", "market_open")
    start = dt.datetime(date.year, date.month, date.day, open_h, open_m, tzinfo=ettime.ET)
    end = dt.datetime(date.year, date.month, date.day, close_h, close_m, tzinfo=ettime.ET)
    return start, end


def _collector_window(day: str) -> tuple[dt.datetime, dt.datetime, str]:
    """The minutes the collector was actually listening to, on this session.

    The end comes from the packet's own rvol_cutoff_hhmm rather than a fixed
    08:45, the same rule night/true_volume._window follows and for the same
    reason: the morning cutoff snaps to [Scan] run_time only inside
    rvol_cutoff_snap_minutes, so a session that ran late genuinely compared a
    different window, and a fixed clock here would mismeasure precisely the
    sessions that went wrong.

    Unlike true_volume this does NOT refuse a session whose packet is gone. It
    falls back to the scheduled [Scan] run_time and puts the window it used on
    the row, because the true columns beside it are still worth writing and a
    row that says which window it compared can be read either way. true_volume
    refuses because its whole output is that one comparison; here it is one of
    two, and the full session columns do not need the packet at all.
    """
    date = ettime.parse_date(day)
    open_h, open_m = _CRIT.clock("collector", "start_time")
    close_h, close_m = _CRIT.clock("scan", "run_time")
    packet_path = config.run_path(day) / "packet.json"
    if packet_path.is_file():
        try:
            cutoff = json.loads(packet_path.read_text(encoding="utf-8")
                                ).get("rvol_cutoff_hhmm")
            if cutoff:
                close_h, close_m = (int(part) for part in str(cutoff).split(":"))
        except (ValueError, OSError, TypeError):
            pass
    start = dt.datetime(date.year, date.month, date.day, open_h, open_m, tzinfo=ettime.ET)
    end = dt.datetime(date.year, date.month, date.day, close_h, close_m, tzinfo=ettime.ET)
    return start, end, f"{open_h:02d}:{open_m:02d}-{close_h:02d}:{close_m:02d}"


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
    # The collector's own window is a SUBSET of the one already fetched, so the
    # second accumulator costs nothing but a comparison per bar. Fetching it
    # separately would double the call count to answer a question the bars in
    # hand already answer.
    socket_start, socket_end, socket_text = _collector_window(day)
    socket_from, socket_to = ettime.epoch_s(socket_start), ettime.epoch_s(socket_end)

    class _Path:
        __slots__ = ("high", "low", "volume_sum", "price_volume", "bars")

        def __init__(self) -> None:
            self.high = self.low = None
            self.volume_sum = self.price_volume = 0.0
            self.bars = 0

        def add(self, hi: float, lo: float, typical: float, vol: float) -> None:
            self.bars += 1
            self.high = hi if self.high is None else max(self.high, hi)
            self.low = lo if self.low is None else min(self.low, lo)
            self.price_volume += typical * vol
            self.volume_sum += vol

    full, socket = _Path(), _Path()
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
        hi, lo = float(bar_high), float(bar_low)
        typical = (hi + lo + float(bar_close)) / 3.0
        full.add(hi, lo, typical, bar_volume)
        if socket_from <= int(stamp) < socket_to:
            socket.add(hi, lo, typical, bar_volume)

    if full.bars == 0:
        return None, "intraday returned no bars inside the premarket window"
    return {
        "pm_high_true": round(full.high, 4) if full.high is not None else None,
        "pm_low_true": round(full.low, 4) if full.low is not None else None,
        "pm_vwap_true": (round(full.price_volume / full.volume_sum, 4)
                         if full.volume_sum else None),
        "pm_true_bars": full.bars,
        # Null rather than zero when the collector's window carried no bar at
        # all. A window with nothing in it is not a high of nothing, and the
        # bar count beside it says which of the two a reader is holding.
        "pm_high_collector_window": (round(socket.high, 4)
                                     if socket.high is not None else None),
        "pm_low_collector_window": (round(socket.low, 4)
                                    if socket.low is not None else None),
        "pm_vwap_collector_window": (round(socket.price_volume / socket.volume_sum, 4)
                                     if socket.volume_sum else None),
        "pm_collector_window_bars": socket.bars,
        "pm_collector_window": socket_text,
    }, None


def _median(values: list[float]) -> float:
    return sorted(values)[len(values) // 2]


def _gap_report(connection, sessions: int) -> None:
    """The live to true gap on the premarket high, split by what causes it.

    One number here used to be reported as what a 07:20 collector start
    misses. It is not one thing, and the module docstring has the measurement
    that showed it: the total splits into a FEED gap, the vendor against the
    socket over minutes both were watching, and a WINDOW gap, the stretches of
    the true session the morning was never looking at.

    The split matters because the two have different fixes and opposite
    meanings. A window gap is the report working as designed: nothing after
    the scan cutoff belongs in a report written at the cutoff. A feed gap is
    the collector disagreeing with the vendor about minutes it recorded, which
    is the same direction as the known volume under capture and is the only
    half of this that is a statement about the collector.
    """
    rows = connection.execute(
        """
        SELECT date, ticker, pm_high, pm_high_true, pm_high_collector_window
        FROM picks
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
    worst = max(gaps, key=abs)
    print(
        f"backfill: over the last {sessions} sessions ({len(gaps)} live rows), the "
        f"true premarket high exceeds the live one by median {_median(gaps):+.2f} percent, "
        f"worst case {worst:+.2f} percent"
    )

    # Rows written before 2026-08-28 carry no collector window column, so the
    # split is reported over the rows that HAVE one and says how many that is.
    # Reporting it over all of them with the missing ones read as zero is the
    # absence dressed as a measurement this project keeps finding.
    split = [row for row in rows
             if row["pm_high"] and row["pm_high_collector_window"]]
    if not split:
        print(f"backfill: 0 of {len(gaps)} of those rows carry "
              "pm_high_collector_window, so the feed and window halves of that "
              "gap cannot be separated yet. Rows written before 2026-08-28 have "
              "no such column and are not refilled by this pass.")
        return
    feed = [(r["pm_high_collector_window"] - r["pm_high"]) / r["pm_high"] * 100.0
            for r in split]
    window = [(r["pm_high_true"] - r["pm_high_collector_window"])
              / r["pm_high_collector_window"] * 100.0 for r in split]
    print(
        f"backfill: on the {len(split)} of those row(s) carrying a collector "
        f"window high, that gap splits into a FEED half of median "
        f"{_median(feed):+.2f} percent, the vendor against the socket over "
        f"minutes both watched, and a WINDOW half of median "
        f"{_median(window):+.2f} percent, the true session the morning was "
        "never looking at. Only the first is a statement about the collector."
    )


# Picks filled across the primary day and every catch-up day of one run. The
# status record wants the whole invocation's count, and backfill() is called
# once per day it fills, so the running total lives out here rather than in a
# return value: backfill()'s return value is main's exit code, and an exit
# code that counted rows would report three filled picks as failure three.
_FILLED = [0]


def verify_volume(day: str, overwrite: bool = False) -> bool:
    """The definitive collector volume check, written to runs/<date>/.

    Reads the collector bar file and the intraday feed and touches no database
    at all, which is why it now runs FIRST and outside the picks path rather
    than at the tail of a successful fill.

    It used to sit at the end of backfill(), after the early return that fires
    when a day has no live picks rows. That coupling was invisible until picks
    was emptied on 2026-08-19 over the collector volume defect, at which point
    the nightly stopped writing verify_intraday.json entirely. The measurement
    that BUILD_PLAN.md's top open question depends on stopped being taken on
    the night that question got most urgent, and nothing said so. The bar file
    is what it reads, the bar file is written whether or not a pick was ever
    scored, and an instrument must not be gated on the thing it measures.

    Returns True when a summary was written.
    """
    summary = collect_premarket.verify_against_intraday(day, quiet=True)
    if summary is None:
        print(f"backfill: collector volume verification for {day} had nothing to "
              "compare, either no collector bars or intraday has not published yet")
        return False

    from core import artifacts
    from selection import universe

    verify_path, _spared = artifacts.resolve(
        config.run_dir(day) / VOLUME_CHECK_FILE,
        overwrite or artifacts.scheduled_run(),
        what="backfill",
    )
    # Atomically, because Path.write_text truncates the destination before it
    # writes a byte, and this file is the only record that a session was ever
    # measured. An interruption there leaves a result that parses as nothing and
    # satisfies is_file() forever, and until _has_measurement below that was
    # enough to make every later night skip the session for good.
    # universe.write_atomically is the temp-file-and-os.replace pair this repo
    # already owns for exactly this, serving universe.json and watchlist.json;
    # it takes a payload and a target, which is this call. It does not sort
    # keys, and nothing reads this file by key order.
    universe.write_atomically(summary, verify_path)

    # Read out of the summary rather than asserted from it. The key set belongs
    # to verify_against_intraday and is being extended, and a print is not
    # allowed to be the thing that ends the nightly.
    detail = (f"{summary.get('within_one_percent')} of {summary.get('compared')} "
              "symbols within one percent")
    median = summary.get("median_abs_pct")
    if isinstance(median, (int, float)):
        detail += f", median absolute difference {median:.2f}%"
    print(f"backfill: collector volume verification written to {verify_path} ({detail})")
    return True


def _has_measurement(path: Path) -> bool:
    """Whether a written verify_intraday.json is a measurement or a corpse.

    is_file() was the old test, and it disagreed with the only programmatic
    reader of this artifact. collect_premarket.latest_volume_check has always
    skipped a copy it cannot parse, on the rule that "a half written or hand
    mangled summary is no measurement", while this module counted the same file
    as a session already measured. A zero byte result satisfies is_file()
    forever, so unverified_sessions skipped that session on every future night,
    _catchup_dates could not reach it because it only finds days with live picks
    rows whose pm_high_true is null, and no output named the file.

    The test is the day key rather than a schema on purpose. What
    verify_against_intraday returns is being extended, and a parser validating a
    fixed key set would start calling every summary written after that change
    unmeasured, which is the same mistake pointed the other way.
    """
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(summary, dict) and bool(summary.get("day"))


def unverified_sessions(before_day: str, limit: int) -> list[str]:
    """Recent sessions with a collector bar file and no verification written.

    The companion to _catchup_dates below, and deliberately a different query.
    That one asks which picks rows still lack their true columns, so it can only
    ever find days that HAVE picks rows. This one asks which collected sessions
    were never measured, which is the question that survives an empty picks
    table. Both exist because the vendor publishes intraday later than 22:15
    often enough that one pass is not enough.

    A session counts only when the collector wrote a subscription list for it,
    which is what makes it a premarket run rather than a bar file somebody
    produced by hand. 2026-08-13 is the case that forces the distinction: its
    file holds 1,810 bars across 38 symbols from 13:32 to 20:00 ET, an
    afternoon shakedown, and BUILD_PLAN.md records that no verification is owed
    for it. Without this test the sweep would spend 38 intraday calls measuring
    it and write the answer into a preserved run directory.
    """
    days: list[str] = []
    directory = config.PREMARKET_DIR
    if not directory.is_dir():
        return days
    for path in sorted(directory.glob("*.jsonl"), key=lambda p: p.name, reverse=True):
        day = path.stem
        if not _DATE_RE.match(day) or day >= before_day:
            continue
        if not collect_premarket.subscriptions_path(day).is_file():
            continue
        # RUNS_DIR / day rather than config.run_dir(day): this is a read only
        # sweep and run_dir creates the directory it names, so asking it here
        # would leave an empty runs/<date>/ behind for every session it looked
        # at.
        written = config.RUNS_DIR / day / VOLUME_CHECK_FILE
        if _has_measurement(written):
            continue
        if written.exists():
            print(f"backfill: {written} exists and does not parse as a measurement, "
                  f"so {day} still counts as unmeasured and is being measured again")
        days.append(day)
        if len(days) >= limit:
            break
    return days


def backfill(day: str, overwrite: bool = False) -> int:
    """Read, close, fetch, then write. The three phases are not cosmetic.

    This loop spends one intraday request per pick. Run inside a single open
    transaction, as it was until 2026-08-15, the UPDATE at the end of each
    iteration opens a write transaction that is then held across the NEXT
    iteration's network call, and the whole run holds the write lock for the
    sum of every request it makes. Any other writer meets 'database is locked'.
    The connection is therefore closed before the first request and reopened
    after the last one.
    """
    api = eodhd.client()

    # Before anything else, and before any path that can return early. See
    # verify_volume's own docstring for what put it here.
    verify_volume(day, overwrite=overwrite)

    # ---- phase 1, read. No network call may happen inside this block.
    with store.session() as connection:
        store.init(connection)
        added = store.ensure_columns(connection, "picks", _TRUE_COLUMNS)
        if added:
            print(f"backfill: widened picks with {', '.join(added)}")

        # source = 'live' only: true premarket columns are outcome evidence,
        # and spending intraday calls widening test rows would pollute the
        # record this table exists to build.
        #
        # Materialised into dicts because the rows outlive this connection now.
        picks = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM picks WHERE date=? AND source='live' ORDER BY ticker",
                (day,),
            ).fetchall()
        ]
        # Commit the DDL from ensure_columns before leaving, so no transaction
        # is still open when the fetch phase starts.
        connection.commit()

    if not picks:
        print(f"backfill: no live picks for {day} (test rows are not backfilled), "
              "nothing to do")
        return 0

    # ---- phase 2, fetch. No database connection is open here.
    fetched: list[tuple[dict[str, Any], dict[str, Any], float | None]] = []
    disagreements = failed = 0
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
        fetched.append((pick, true_row, disagree))

    # ---- phase 3, write. Every network call is already done.
    filled = 0
    now_stamp = ettime.stamp(ettime.now_et())
    with store.session() as connection:
        for pick, true_row, disagree in fetched:
            connection.execute(
                """
                UPDATE picks SET pm_high_true=?, pm_low_true=?, pm_vwap_true=?,
                    pm_true_bars=?, pm_source_disagreement=?, backfilled_at=?
                WHERE date=? AND ticker=?
                """,
                (
                    true_row["pm_high_true"], true_row["pm_low_true"],
                    true_row["pm_vwap_true"], true_row["pm_true_bars"],
                    disagree, now_stamp, day, pick["ticker"],
                ),
            )
            filled += 1
        connection.commit()

        print(f"backfill: {filled} of {len(picks)} picks filled for {day}, "
              f"{disagreements} source disagreements, {failed} unavailable")
        job_status.produced("picks filled", _FILLED[0] + filled)
        _FILLED[0] += filled
        _gap_report(connection, _CRIT.integer("backfill", "gap_report_sessions"))

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


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the true premarket window into picks.")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=ettime.today_et().isoformat(),
                        help="Session to backfill. Defaults to today in ET.")
    parser.add_argument("--no-catchup", action="store_true",
                        help="Only the named day, no sweep of unfilled prior days.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace an existing verify_intraday.json under runs/. "
                             "Without it a hand run is spared and the copy is written "
                             "beside the original. The scheduled nightly always "
                             "overwrites, including for the catch-up days it owns.")
    args = parser.parse_args(argv)
    result = backfill(args.date, overwrite=args.overwrite)
    if not args.no_catchup:
        catchup_days = _CRIT.integer("backfill", "catchup_days")
        filled = _catchup_dates(args.date, catchup_days)
        for day in filled:
            print(f"backfill: catching up {day}, its true premarket columns are still null")
            backfill(day, overwrite=args.overwrite)
        # And separately, sessions that were collected and never measured. A day
        # with no picks rows is invisible to the sweep above and still has a bar
        # file worth comparing, which is the whole of what the volume question
        # has left to work with while picks is empty.
        for day in unverified_sessions(args.date, catchup_days):
            if day in filled:
                continue  # already measured by its own backfill pass just now
            print(f"backfill: {day} was collected and never verified, measuring it now")
            verify_volume(day, overwrite=args.overwrite)
    return result


if __name__ == "__main__":
    sys.exit(job_status.run("backfill", main, ok_codes=OK_CODES))
