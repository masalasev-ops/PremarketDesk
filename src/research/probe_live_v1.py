"""Does real-time/{symbol} serve today's premarket, or the last completed session?

Standalone. Nothing in any chain imports this, nothing reads its output, and
it writes only to data/probe-live-v1-<date>.jsonl. It exists to answer one
question and then to be deleted or kept as evidence.

The question. eodhd.bulk_live_us() hits real-time/ with ex=US and serves the
last COMPLETED session, which is what published the wrong prices on
2026-08-14. eodhd.live_quotes() hits the same endpoint family per ticker,
real-time/{symbol}, and nobody had checked whether it behaves the same way.
The two answers lead to very different systems:

  same behaviour: the endpoint is useless before the open and the candidate
  pool prior stays the only way to choose names at 07:15;

  today's data: a 2,745 name sweep at 07:15 sees the actual overnight move
  for the whole universe and replaces the pool prior outright, at a cost of
  roughly 2,745 counted calls.

A one shot sample taken during the regular session on 2026-08-14 at 13:42 ET
already answered half of it: SPY returned a timestamp of 13:26 the same day,
sixteen minutes behind the wall clock but unambiguously today's session, with
a volume of 14.5M and a previousClose of 777.88 against a close of 775.65. So
the per ticker form is NOT the exchange-wide form's last-completed-session
behaviour, at least during regular hours.

What that sample cannot say is whether the feed ticks during PREMARKET, which
is the only window this project cares about, and what the lag is there. Live
v1 is documented in this project as running about seventeen minutes behind,
which at 08:45 would mean data from 08:28: still inside the premarket window,
still useful for selection, and not the same thing as live. A feed that only
updates from 09:30 would return the prior close all morning and look exactly
like the bulk endpoint until the bell.

So this samples every three minutes from 08:00 to 09:15 against five symbols
the collector is recording, and puts the collector's own bar for the same
minute beside each reading. The collector is ground truth: it is a trade
socket, so if a print happened, it has it.

Cost. Five symbols batch into one request, so one call per sample, 26 samples,
about 26 counted calls.

  python -m research.probe_live_v1            run the sampling loop
  python -m research.probe_live_v1 --report   read the log back as a table
  python -m research.probe_live_v1 --once     take a single sample now
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from collect import collect_premarket
from core import config
from core import criteria
from core import eodhd
from core import ettime

_CRIT = criteria.load()

# The context tickers, chosen because the collector subscribes to them every
# single morning regardless of what discover picked, so the comparison never
# depends on which names happened to be in the pool that day.
SYMBOLS = ["SPY.US", "QQQ.US", "IWM.US", "DIA.US", "TLT.US"]

START_HHMM = (8, 0)
STOP_HHMM = (9, 15)
INTERVAL_S = 180


def log_path(day: str | None = None) -> Path:
    return config.DATA_DIR / f"probe-live-v1-{day or ettime.today_str()}.jsonl"


def sample(api: eodhd.EodhdClient) -> dict[str, Any]:
    """One reading of all five symbols, with the wall clock beside it."""
    taken_at = ettime.now_et()
    data, error = api.live_quotes(SYMBOLS)

    rows: dict[str, Any] = {}
    for symbol in SYMBOLS:
        row = (data or {}).get(symbol) or {}
        stamp = row.get("timestamp")
        feed_at = ettime.from_epoch_s(stamp) if stamp else None
        rows[symbol] = {
            "timestamp": stamp,
            "feed_at_et": ettime.stamp(feed_at) if feed_at else None,
            "lag_minutes": (
                round((taken_at - feed_at).total_seconds() / 60.0, 1)
                if feed_at else None
            ),
            "close": row.get("close"),
            "previous_close": row.get("previousClose"),
            "volume": row.get("volume"),
            "change_p": row.get("change_p"),
        }

    return {
        "taken_at_et": ettime.stamp(taken_at),
        "error": error,
        "quotes": rows,
    }


def _collector_bar_at(bars: list[dict[str, Any]], when_epoch: int) -> dict[str, Any] | None:
    """The collector's bar covering the minute a feed reading claims to be from."""
    if not when_epoch:
        return None
    minute = collect_premarket.minute_floor(when_epoch)
    for bar in bars:
        if int(bar.get("minute_epoch") or 0) == minute:
            return bar
    return None


def report(day: str | None = None) -> int:
    """Read the log back with the collector's own bars beside it."""
    target = log_path(day)
    if not target.is_file():
        print(f"probe: nothing logged at {target}")
        return 1

    session = day or ettime.today_str()
    bars = collect_premarket.read_bars(session)

    print(f"probe: real-time/(symbol) against the collector, {session}")
    print("")
    print(f"{'taken (ET)':<10} {'symbol':<8} {'feed says':<10} {'lag':>6} "
          f"{'feed close':>11} {'collector c':>12} {'coll bars':>9} {'prev close':>11}")

    seen_today = 0
    seen_stale = 0
    total = 0
    # Samples whose FEED timestamp lands inside the premarket window. Only
    # these can answer the question that matters. A reading taken at lunchtime
    # proves the endpoint is live during regular hours, which was never in
    # doubt, and says nothing about whether it ticks before the bell.
    in_premarket = 0
    premarket_today = 0
    window_open = _CRIT.clock("baseline", "session_start")
    window_close = _CRIT.clock("backfill", "market_open")

    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        taken = str(record.get("taken_at_et") or "")[11:19]
        for symbol, quote in sorted((record.get("quotes") or {}).items()):
            total += 1
            feed_at = str(quote.get("feed_at_et") or "")
            feed_day = feed_at[:10]
            if feed_day == session:
                seen_today += 1
            elif feed_day:
                seen_stale += 1
            if len(feed_at) >= 16:
                minutes = int(feed_at[11:13]) * 60 + int(feed_at[14:16])
                if (window_open[0] * 60 + window_open[1]) <= minutes < (
                        window_close[0] * 60 + window_close[1]):
                    in_premarket += 1
                    if feed_day == session:
                        premarket_today += 1
            bar = _collector_bar_at(bars.get(symbol) or [], quote.get("timestamp") or 0)
            print(
                f"{taken:<10} {symbol:<8} {feed_at[11:19] or '-':<10} "
                f"{quote.get('lag_minutes') if quote.get('lag_minutes') is not None else '-':>6} "
                f"{quote.get('close') if quote.get('close') is not None else '-':>11} "
                f"{bar.get('c') if bar else '-':>12} "
                f"{len(bars.get(symbol) or []):>9} "
                f"{quote.get('previous_close') if quote.get('previous_close') is not None else '-':>11}"
            )

    print("")
    print(f"probe: {total} readings, {seen_today} dated to {session}, "
          f"{seen_stale} dated to an earlier session")
    print(f"probe: {in_premarket} reading(s) carried a feed timestamp inside the "
          f"{window_open[0]:02d}:{window_open[1]:02d} to "
          f"{window_close[0]:02d}:{window_close[1]:02d} premarket window, "
          f"{premarket_today} of them dated to {session}")

    # Structurally, before any branch that could conclude. The denominator is
    # not the number of readings, it is the number of readings that carried a
    # usable timestamp: a log of five nulls is five readings and zero
    # observations, and every conclusion below divides by observations.
    observations = seen_today + seen_stale
    if not observations:
        print(f"probe: EXAMINED NOTHING. {total} reading(s) were logged and none "
              "carried a feed timestamp, so there is no observation to draw on. "
              "This is not a pass and not a failure, it is an empty measurement. "
              "The usual cause is the shared quota refusing the calls; check the "
              "error field in the log.")
        return 0

    if seen_stale == total:
        print("probe: CONCLUSION real-time/(symbol) serves the LAST COMPLETED "
              "SESSION, exactly like the exchange wide form. It can never be a "
              "source of today's premarket and the candidate pool prior stays "
              "the only way to choose names at 07:15.")
        return 0

    if not in_premarket:
        # This is the state a lunchtime sample leaves you in, and calling it
        # an answer would be the same overreach that produced the 8/14 report.
        print("probe: CONCLUSION PARTIAL. Every reading is from today, so the per "
              "ticker form is NOT the exchange wide form's last-completed-session "
              "behaviour. But no reading carried a premarket timestamp, so this "
              "says nothing about whether the feed ticks before the bell, which "
              "is the only window this project needs. Run the sampling loop on a "
              "trading morning before concluding anything about 07:15.")
        return 0

    if premarket_today == in_premarket:
        print("probe: CONCLUSION real-time/(symbol) serves TODAY's PREMARKET. It "
              "is not the last-completed-session behaviour the exchange wide form "
              "has, so a universe sweep at 07:15 is a real option. What remains "
              "is the cost, roughly 2,745 counted calls, and the lag shown in the "
              "lag column above, which is what decides whether an 07:15 sweep is "
              "reading the overnight move or the last twenty minutes of it.")
    else:
        print("probe: CONCLUSION mixed, which needs explaining rather than "
              "reporting. Read the per row dates above before drawing anything "
              "from this.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Does real-time/(symbol) serve today's premarket?")
    parser.add_argument("--report", action="store_true",
                        help="Read an existing log back as a table and conclude.")
    parser.add_argument("--day", default=None, help="Session to report on.")
    parser.add_argument("--once", action="store_true",
                        help="Take one sample now and print it, whatever the clock says.")
    args = parser.parse_args(argv)

    if args.report:
        return report(args.day)

    config.ensure_dirs()
    api = eodhd.client()

    if args.once:
        record = sample(api)
        print(json.dumps(record, indent=2))
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        eodhd.print_call_report()
        return 0

    today = ettime.today_et()
    start = ettime.at_hm(today, START_HHMM)
    stop = ettime.at_hm(today, STOP_HHMM)
    now = ettime.now_et()

    if now > stop:
        print(f"probe: it is {ettime.stamp(now)}, past the {STOP_HHMM[0]:02d}:"
              f"{STOP_HHMM[1]:02d} stop. Nothing to sample today.")
        return 0

    while ettime.now_et() < start:
        time.sleep(min(30.0, (start - ettime.now_et()).total_seconds()))

    print(f"probe: sampling {len(SYMBOLS)} symbols every {INTERVAL_S}s until "
          f"{ettime.stamp(stop)}, writing {log_path().name}")

    taken = 0
    while ettime.now_et() < stop:
        record = sample(api)
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            handle.flush()
        taken += 1
        first = record["quotes"][SYMBOLS[0]]
        print(f"probe: {record['taken_at_et'][11:19]} {SYMBOLS[0]} feed says "
              f"{first['feed_at_et']} (lag {first['lag_minutes']}m) "
              f"close {first['close']}")
        remaining = (stop - ettime.now_et()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(INTERVAL_S, remaining))

    print(f"probe: {taken} samples written to {log_path()}")
    eodhd.print_call_report()
    return report()


if __name__ == "__main__":
    # Deliberately NOT wrapped in job_status.run: this is a one off probe, not
    # a scheduled step, and CRITERIA.md [job status steps] would then have to
    # carry a step that is meant to stop existing.
    sys.exit(main())
