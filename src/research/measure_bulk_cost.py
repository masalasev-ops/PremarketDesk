"""Measure what one bulk live snapshot costs on the vendor's own counter.

discover.py and scan.py each make one bulk live call every weekday morning,
and the design has treated that as two cheap calls. Whether the vendor
agrees is not a client side question: the only honest answer is their
counter, read before and after exactly one bulk request while nothing else
touches the account.

The counter is ACCOUNT WIDE and the key is shared, so this script first
watches the meter over a settle window. A moving meter means another
consumer is spending right now, and any delta would be theirs as much as
ours, so the run aborts rather than record a contaminated number.

A note on the meter's own behavior, established by the socket measurement
and confirmed by this script's quiet watch: a /api/user read does NOT
register on the counter. The quiet check therefore expects zero drift, and
the raw delta around the bulk call belongs to the bulk call alone. A drift
of one is tolerated with a warning, so a future change in the vendor's
metering of /user shows itself instead of silently skewing the figure.

The decision this number feeds: if one bulk call costs at or above the
bulk_redesign_line in CRITERIA.md [quota], the two bulk calls a day are the
dominant cost on the shared account and the design has to change. This
script only reports the figure against that line. The redesign, if the
figure demands one, happens in its own commit where the alternatives can be
weighed against a real number rather than a range.

The counter resets at midnight UTC. A run that straddles the reset would
report a nonsense negative delta as a fact, so the script refuses to record
anything when the quota day changed mid run or the delta came back negative.
"""

from __future__ import annotations

import argparse
import sys
import time

import criteria
import eodhd
import ettime
from measure_socket_cost import read_counter

_CRIT = criteria.load()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vendor-counter cost of one bulk live OHLCV request.")
    parser.add_argument("--settle-seconds", type=float, default=45.0,
                        help="How long the meter must sit still before the call.")
    parser.add_argument("--force", action="store_true",
                        help="Measure even if the meter is moving. The number "
                             "will be contaminated and says so.")
    args = parser.parse_args(argv)

    session = eodhd.build_session()

    day_at_start = eodhd.quota_day()
    first, limit = read_counter(session)
    print(f"measure: meter reads {first:,} of {limit:,} "
          f"({ettime.stamp(ettime.now_et())}), quota day {day_at_start}")
    print(f"measure: watching for {args.settle_seconds:.0f}s of quiet. The counter "
          "is account wide; a moving meter is another consumer spending.")
    time.sleep(args.settle_seconds)
    before, _ = read_counter(session)

    drift = before - first
    if drift < 0:
        print(f"measure: the meter went BACKWARDS by {-drift:,} during the quiet "
              "watch, which means the daily reset happened mid watch. Nothing "
              "recorded; rerun clear of the midnight UTC boundary.")
        return 1
    quiet = drift <= 1  # zero expected; one tolerated in case /user metering changes
    if drift == 1:
        print("measure: the meter moved by exactly 1 during the quiet watch. "
              "Past measurements found /user reads free; if the vendor now "
              "meters them, subtract 1 from the figure below.")
    if not quiet:
        print(f"measure: the meter moved by {drift:,} in {args.settle_seconds:.0f}s "
              "beyond this script's own read. Another consumer is active.")
        if not args.force:
            print("measure: refusing to record a contaminated number. Rerun when "
                  "the account is quiet, or pass --force to measure anyway.")
            return 1
        print("measure: --force given, measuring anyway. Treat the result as an "
              "upper bound, not a fact.")

    rows, error = eodhd.client().bulk_live_us()
    if error:
        print(f"measure: the bulk call itself failed ({error}). No cost fact "
              "can be recorded from a failed call.")
        return 1
    symbols = len(rows)
    attempts = eodhd.LEDGER.by_endpoint.get("bulk-live-us", 0)

    after, _ = read_counter(session)
    delta = after - before  # /user reads measured free, so this is the bulk call
    if delta < 0 or eodhd.quota_day() != day_at_start:
        print(f"measure: the run straddled the midnight UTC reset (quota day "
              f"{day_at_start} at the start, {eodhd.quota_day()} now, delta "
              f"{delta:,}). A negative or split day delta is not a measurement. "
              "Nothing recorded; rerun clear of the boundary.")
        return 1

    print("")
    print(f"measure: meter before   {before:,}")
    print(f"measure: meter after    {after:,}")
    print(f"measure: delta          {delta:,} "
          "(user endpoint reads measured free, so the delta is the bulk call's)")
    print(f"measure: the bulk call returned {symbols:,} symbol rows in "
          f"{attempts} HTTP attempt(s)")
    if symbols and delta > 0:
        print(f"measure: implied per symbol rate {delta / symbols:.6f} "
              "counted calls per returned symbol")
    contaminated = "" if quiet else " CONTAMINATED, another consumer was active."
    redesign_line = _CRIT.integer("quota", "bulk_redesign_line")
    over = delta >= redesign_line
    print(f"measure: VERDICT one bulk live request moved the vendor counter by "
          f"{delta:,}.{contaminated}")
    print("measure: " + (
        f"at or above the {redesign_line:,} redesign line in CRITERIA.md [quota]: "
        "the two daily bulk calls dominate the shared account and the design has "
        "to change, in its own commit, not this one."
        if over else
        f"below the {redesign_line:,} redesign line in CRITERIA.md [quota]: the "
        "two daily bulk calls are not the dominant cost."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
