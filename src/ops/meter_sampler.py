"""Read the shared quota meter on a clock, independent of the job schedule.

The job trail added on 2026-08-16 answers "which step spent what". It cannot
answer "when", because it only has readings where a job happens to run, and
this schedule is sparse: nine jobs clustered into two short windows, with
nothing at all between the 22:45 monitor and the 07:00 catch-up. A sibling
project draining the key overnight is invisible to it, and overnight is exactly
when 2026-08-16's drain would have had to happen to be as complete as it was by
the afternoon.

So this samples every thirty minutes, all day, appending to the same
logs/meter-<quota day>.log with source='sampler'. Forty eight calls a day
against a shared hundred thousand, which is 0.048 percent of the budget to turn
hour-wide guesses into a consumption curve.

It also marks the boundary rather than leaving it to be inferred. The vendor's
counter does not roll at 00:00 UTC: on 2026-08-16 it rolled 30 to 32 minutes
late, which is what produced a nonsense delta in the trail's first hour of
life. When a sample sees the counter fall, meaning remaining has RISEN, this
writes an explicit source='reset' row carrying both sides of the boundary, so
a reader sees a labelled reset instead of a gap they have to interpret.

Standalone. Nothing imports it, it is not one of the sixteen scheduled
entrypoints, and it writes no job status record: it is an instrument, not a
step, and CRITERIA.md [job status steps] must not grow an entry for it.

    python -m ops.meter_sampler            sample once and exit
    python -m ops.meter_sampler --loop     sample every interval until stopped
    python -m ops.meter_sampler --report   read the day's curve back
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from core import config
from ops import job_status

INTERVAL_MINUTES = 30

SOURCE_SAMPLER = "sampler"
SOURCE_RESET = "reset"


def _previous_reading() -> dict[str, Any] | None:
    """The last row in the trail carrying a usable counter, whatever wrote it.

    Deliberately not the last SAMPLER row. A job reading taken two minutes ago
    is a better previous value than a sampler reading taken twenty eight
    minutes ago, and mixing them is the point: the trail is one timeline of the
    shared counter, with a column saying who looked.
    """
    for row in reversed(job_status.read_trail()):
        if row.get("api_requests") is not None:
            return row
    return None


def sample() -> dict[str, Any] | None:
    """One reading, plus a reset row first if the counter has rolled.

    The reset row is written BEFORE the sample so the file reads in the order
    things happened: the boundary, then the first reading after it.
    """
    previous = _previous_reading()

    # Peek at the meter before writing anything, so a roll can be marked ahead
    # of the sample that discovered it.
    from core import eodhd

    data, error = eodhd.read_meter()
    used = None
    meter_day = None
    if not error and isinstance(data, dict):
        try:
            used = int(data.get("apiRequests"))
        except (TypeError, ValueError):
            used = None
        meter_day = str(data.get("apiRequestsDate") or "").strip() or None

    rolled = False
    if previous is not None and used is not None:
        was = previous.get("api_requests")
        # Two independent signals, either sufficient. The counter falling is
        # the unambiguous one. The meter re-dating itself catches a roll that
        # happens to land on a day when almost nothing had been spent, where
        # the fall could be small enough to look like noise.
        if was is not None and used < was:
            rolled = True
        elif (meter_day and previous.get("meter_day")
                and meter_day != previous.get("meter_day")):
            rolled = True

    if rolled:
        # Both rows are written from the SAME reading taken above, so this is
        # still one call for the whole sample, and the reset row cannot
        # disagree with the sample that detected it. The row carries both
        # sides of the boundary explicitly, which is the difference between a
        # marked reset and one a reader has to reconstruct.
        job_status.record_meter(
            "counter", "rolled", source=SOURCE_RESET,
            reading=(data, error),
            extra={
                "rolled_from_api_requests": previous.get("api_requests"),
                "rolled_from_meter_day": previous.get("meter_day"),
                "rolled_from_at": previous.get("at"),
                "rolled_to_api_requests": used,
                "rolled_to_meter_day": meter_day,
            })
        print(f"sampler: RESET. The counter rolled from "
              f"{previous.get('api_requests'):,} used dated "
              f"{previous.get('meter_day')} to {used:,} dated {meter_day}. "
              f"The previous reading was at {previous.get('at')}.")

    return job_status.record_meter("sampler", "tick", source=SOURCE_SAMPLER,
                                   reading=(data, error))


def report(day: str | None = None) -> int:
    """The day's curve, sampler rows and job rows on one timeline."""
    rows = job_status.read_trail(day)
    if not rows:
        print(f"sampler: no trail for {day or 'today'}")
        return 0

    print(f"sampler: {len(rows)} readings on {rows[0].get('quota_day')}")
    print()
    print(f"{'at':>9} {'source':<8} {'step':<12} {'when':<7} {'used':>9} "
          f"{'remaining':>10} {'delta':>9}")
    for row in rows:
        delta = row.get("delta_since_previous")
        used = row.get("api_requests")
        print(f"{str(row.get('at'))[11:19]:>9} {str(row.get('source')):<8} "
              f"{str(row.get('step')):<12} {str(row.get('when')):<7} "
              f"{('' if used is None else format(used, ',')):>9} "
              f"{('' if row.get('remaining') is None else format(row['remaining'], ',')):>10} "
              f"{('' if delta is None else format(delta, '+,')):>9}")

    sampler_rows = [r for r in rows if r.get("source") == SOURCE_SAMPLER]
    resets = [r for r in rows if r.get("source") == SOURCE_RESET]
    hours: dict[str, int] = {}
    for row in rows:
        delta = row.get("delta_since_previous")
        if delta and delta > 0:
            hours[str(row.get("at"))[11:13]] = hours.get(str(row.get("at"))[11:13], 0) + delta
    print()
    print(f"{len(sampler_rows)} sampler rows, {len(resets)} labelled reset row(s)")
    if hours:
        print("consumption by hour of the day, from every source:")
        for hour in sorted(hours):
            bar = "#" * min(60, max(1, hours[hour] * 60 // max(hours.values())))
            print(f"  {hour}:00  {hours[hour]:>7,}  {bar}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample the shared quota meter on a clock.")
    parser.add_argument("--loop", action="store_true",
                        help="Keep sampling every interval until stopped. The "
                             "scheduled task uses a single shot per firing instead, "
                             "so a crash cannot silence the sampler for a whole day.")
    parser.add_argument("--interval-minutes", type=int, default=INTERVAL_MINUTES)
    parser.add_argument("--report", action="store_true", help="Read the day's curve back.")
    parser.add_argument("--date", default=None, help="Which quota day to report on.")
    args = parser.parse_args(argv)

    if args.report:
        return report(args.date)

    config.ensure_dirs()
    if not args.loop:
        sample()
        return 0

    print(f"sampler: sampling every {args.interval_minutes} minutes, Ctrl-C to stop")
    while True:
        sample()
        time.sleep(args.interval_minutes * 60)


# Not wrapped in job_status.run and deliberately so: this is an instrument
# rather than a scheduled step, and a step that appeared in the status record
# would make the watchdog expect it and report it overdue.
if __name__ == "__main__":
    sys.exit(main())
