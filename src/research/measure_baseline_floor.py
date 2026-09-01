"""What the RVOL denominator floor actually buys, measured per name.

An instrument, not a pipeline step. Nothing downstream reads its output.

  .venv\\Scripts\\python.exe -m research.measure_baseline_floor

CRITERIA [Baseline] min_baseline_premarket_volume exists so that a denominator
cannot max the RVOL scoring band "by construction rather than by evidence".
That is a testable claim and from 2026-08-14 to 2026-08-28 nothing had tested
it; the floor note said so in as many words. This is the test, and the floor
note now carries its result.

The method needs no external reference, which is the point. For each name
holding a cached baseline, refetch the same LOOKBACK sessions over the same
04:00 to cutoff window the baseline is built from, then divide every one of
those ORDINARY sessions by the median of the set it belongs to. Ask what share
of them would score above the top RVOL band edge against their own median.

Half of any set sits above its own median by construction, so this measures the
right tail rather than the centre. A name whose premarket volume is steady has
almost no session at 3x its own median. A name that usually trades nothing has
most of them there, and every ordinary morning it has reads as extraordinary.

The 2026-08-28 run, 241 names and 241 intraday calls: 30 percent of ordinary
sessions above 3x for medians under 1,000 shares, 20 percent from 1,000 to
5,000, 15 percent from 5,000 to 25,000, 10 percent to 100,000 and 5 percent
above it. Monotonic. The floor removes the worst band and leaves a name just
over it reaching the top band on one ordinary session in five.

Why the floor was not simply raised is in the CRITERIA note: a refused name is
rescued onto the float rotation bands, and those were fitted on the population
the CURRENT floor rescues, so the two have to move together or the change hands
a thin name its band through the other door.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from typing import Any

from core import config
from core import criteria
from core import eodhd
from core import ettime
from core import store

_CRIT = criteria.load()

LOOKBACK = _CRIT.integer("baseline", "lookback_sessions")
SESSION_START = _CRIT.clock("baseline", "session_start")
MIN_SESSIONS = _CRIT.integer("baseline", "min_sessions_for_rvol")
FLOOR = _CRIT.number("baseline", "min_baseline_premarket_volume")
THIN = _CRIT.number("baseline", "thin_baseline_premarket_volume")

# The band edge the floor note is written about. Read from CRITERIA rather than
# spelled here, so a change to the scoring bands cannot leave this measuring an
# edge the score no longer has.
TOP_BAND = max(band.rule.value for band in _CRIT.bands("score_premarket_rvol")
               if band.rule is not None and band.rule.value is not None)

# The buckets the note's table is printed over. Boundaries, not thresholds:
# nothing reads them and moving one changes only how the answer is displayed.
BUCKETS = ((0, 1_000), (1_000, 2_000), (2_000, 5_000), (5_000, 10_000),
           (10_000, 25_000), (25_000, 100_000), (100_000, None))


def cached_names(cutoff: str) -> list[str]:
    """Every ticker holding a baseline at this cutoff, which is the population.

    Deliberately not the whole universe. The floor only ever touches names that
    reached a baseline, so measuring over 2,771 names would report mostly on
    names this threshold will never see.
    """
    with store.session() as connection:
        store.init(connection)
        return [row[0] for row in connection.execute(
            "SELECT ticker FROM baseline WHERE cutoff_hhmm=? ORDER BY ticker",
            (cutoff,))]


def sessions_for(api: eodhd.EodhdClient, ticker: str, cutoff: str,
                 today: dt.date) -> tuple[list[float], str | None]:
    """The same per session premarket volumes baseline.compute sums.

    Kept deliberately parallel to baseline.compute rather than importing it,
    because that function returns only the median and the whole question here
    is about the sessions underneath it. The two must agree on the window, the
    session set and the zero rule, and the claim in the suite holds that.
    """
    start_minute = SESSION_START[0] * 60 + SESSION_START[1]
    hour, minute = cutoff.split(":")
    end_minute = int(hour) * 60 + int(minute)

    window_start = ettime.at(today - dt.timedelta(days=LOOKBACK * 2 + 5), 0, 0)
    window_end = ettime.at(today, 0, 0)
    rows, error = api.intraday(ticker, window_start, window_end, "1m")
    if error:
        return [], error
    if not rows:
        return [], f"no intraday bars returned for {ticker}"

    per_session: dict[str, float] = {}
    seen: set[str] = set()
    for row in rows:
        stamp = row.get("timestamp")
        if stamp is None:
            continue
        when = ettime.from_epoch_s(stamp)
        if when is None or when.date() >= today:
            continue
        day = when.date().isoformat()
        seen.add(day)
        mod = when.hour * 60 + when.minute
        if start_minute <= mod < end_minute:
            try:
                per_session[day] = per_session.get(day, 0.0) + float(row.get("volume") or 0)
            except (TypeError, ValueError):
                continue
    # A day with bars was a trading day. A genuine zero premarket is a real
    # observation and is kept, exactly as baseline.compute keeps it: filtering
    # it out here would raise every thin name's median and hide the effect
    # this instrument exists to measure.
    for day in seen:
        per_session.setdefault(day, 0.0)

    ordered = sorted(per_session)[-LOOKBACK:]
    return [per_session[day] for day in ordered], None


def measure(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The table the floor note prints, over whatever rows were collected."""
    usable = [r for r in rows if r["share_above_top_band"] is not None]
    out = []
    for low, high in BUCKETS:
        selected = [r for r in usable
                    if low <= r["median"] and (high is None or r["median"] < high)]
        if not selected:
            continue
        out.append({
            "median_from": low,
            "median_to": high,
            "names": len(selected),
            "share_above_top_band": statistics.median(
                r["share_above_top_band"] for r in selected),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", default="08:45",
                        help="the baseline cutoff to measure, HH:MM ET")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after this many names, for a cheap dry run")
    parser.add_argument("--out", default=None,
                        help="where to write the payload; defaults to "
                             "data/research/baseline_floor_study-<today>.json")
    args = parser.parse_args(argv)

    today = ettime.today_et()
    names = cached_names(args.cutoff)
    if args.limit:
        names = names[:args.limit]
    print(f"measure_baseline_floor: {len(names)} name(s) with a cached "
          f"{args.cutoff} baseline, top band edge > {TOP_BAND}")

    api = eodhd.EodhdClient()
    rows: list[dict[str, Any]] = []
    for index, ticker in enumerate(names, start=1):
        volumes, error = sessions_for(api, ticker, args.cutoff, today)
        if error or len(volumes) < MIN_SESSIONS:
            print(f"  {index:>4}/{len(names)} {ticker:<12} skipped: "
                  f"{error or f'only {len(volumes)} session(s)'}")
            continue
        median = statistics.median(volumes)
        # A zero median is already refused by baseline.usable_for_rvol before
        # the floor is reached, and dividing by it here would raise. Recorded
        # as unmeasurable rather than dropped, so the counts reconcile.
        share = None if median <= 0 else (
            sum(1 for v in volumes if v > TOP_BAND * median) / len(volumes))
        rows.append({
            "ticker": ticker,
            "median": median,
            "sessions": len(volumes),
            "share_above_top_band": share,
            "below_floor": median < FLOOR,
            "thin": FLOOR <= median < THIN,
            "volumes": volumes,
        })
        if index % 25 == 0:
            print(f"  {index:>4}/{len(names)} ...")

    table = measure(rows)
    payload = {
        "generated_at": ettime.stamp(ettime.now_et()),
        "cutoff_hhmm": args.cutoff,
        "lookback_sessions": LOOKBACK,
        "session_start": _CRIT.clock_text("baseline", "session_start"),
        "top_band_edge": TOP_BAND,
        "floor": FLOOR,
        "thin_line": THIN,
        "names_measured": len(rows),
        "names_with_zero_median": sum(
            1 for r in rows if r["share_above_top_band"] is None),
        "table": table,
        "rows": rows,
    }
    out = (config.STUDY_DIR /
           f"baseline_floor_study-{today.isoformat()}.json"
           if args.out is None else config.PROJECT_ROOT / args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"\n{'baseline median':>22} {'names':>6} "
          f"{'ordinary sessions above ' + str(TOP_BAND) + 'x':>32}")
    for band in table:
        high = band["median_to"]
        label = (f"{band['median_from']:,} to {high:,}" if high
                 else f"{band['median_from']:,} and up")
        print(f"{label:>22} {band['names']:>6} "
              f"{band['share_above_top_band'] * 100:>31.1f}%")
    print(f"\nmeasure_baseline_floor: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
