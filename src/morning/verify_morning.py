"""The first morning verification gate.

Until a human has watched one real morning's numbers and agreed they are sane,
the system must not email anyone. The gate has two parts. This script prints
the evidence table for the first few candidates of today's packet: the
collector's premarket volume, the cached baseline median, the RVOL those two
produce, the price and the minute it was printed, and how many bars stand
behind it. And a marker file, data/UNVERIFIED, which deliver.py refuses to
send past while it exists.

The price and the minute it was printed are in that table because the failure
that made this gate earn its keep was invisible without them: on 2026-08-14
every number was internally consistent and a session old. A price with no
clock beside it cannot be checked by eye.

When the table looks sane on a live morning, the human deletes the marker and
the next morning goes out. Nothing here deletes it except --arm, which removes
it only to write it straight back, and nothing recreates it on a healthy
morning, because a marker that quietly respawned after the human removed it
would overrule a decision that belongs to them.

There is exactly one automatic writer, and it is not a respawn. vintage.enforce
rewrites this marker, naming the rows that failed, when a packet's own
timestamps say the data is not today's, and the body it writes says it was
rewritten automatically. That is the gate doing its job rather than undoing the
human's.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import config
from core import ettime
from ops import job_status

UNVERIFIED_MARKER = config.DATA_DIR / "UNVERIFIED"

_MARKER_TEXT = (
    "PremarketDesk verification gate.\n"
    "While this file exists deliver.py sends no email.\n"
    "Watch one real morning's gate table (verify_morning.py), and when the\n"
    "numbers are sane delete this file to go live. Nothing deletes it for you.\n"
)


def ensure_marker() -> None:
    if not UNVERIFIED_MARKER.exists():
        config.ensure_dirs()
        UNVERIFIED_MARKER.write_text(_MARKER_TEXT, encoding="utf-8")
        print(f"gate: created {UNVERIFIED_MARKER}")


def print_table(packet_path: Path, count: int = 3) -> int:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    candidates = packet.get("candidates", [])[:count]
    if not candidates:
        # Exit ZERO. A packet with no candidates is a supported state
        # everywhere else in this system: scan.main returns 0 on it, the
        # analyst's fallback is written to print "0 of 0", and the report goes
        # out with empty tables and the reason on the disclaimer. Returning 1
        # here recorded the verify step as failed on a morning where nothing
        # went wrong, which the watchdog then counted as a problem and the next
        # day's report put on its disclaimer line as a failed scheduled step.
        # A false alarm on a quiet morning is how a real alarm stops being read.
        # The count below is what carries the fact, and zero rows tabled is
        # visible in the trail without pretending to be a fault.
        print("gate: the packet has no candidates to verify, which is a quiet "
              "morning rather than a fault. Nothing to table.")
        print(f"gate: marker {UNVERIFIED_MARKER} "
              f"{'EXISTS, no email will be sent' if UNVERIFIED_MARKER.exists() else 'is absent, email is live'}")
        job_status.produced("rows tabled", 0)
        return 0

    print(f"gate: verification table for {packet.get('session_date')}, "
          f"packet generated {packet.get('generated_at')}")
    build = packet.get("build") or {}
    print(f"gate: build {build.get('commit') or 'unknown'}"
          f"{' (working tree dirty)' if build.get('dirty') else ''}")
    # The columns are here so a human can DO THE DIVISION. That is the whole
    # job of this table: data/UNVERIFIED names it as the thing to read before
    # going live, and a reader who cannot reproduce the ratio cannot verify it.
    #
    # It used to reconcile and stopped on 2026-08-21, silently. Until then
    # pm_rvol was pm_volume over the baseline median, exactly, and after the
    # capture correction pm_rvol divides an ESTIMATE of consolidated volume
    # instead. On the first live morning the table printed ASST as 14,960
    # against 24,528.5 with an RVOL of 2.0555, which is 0.61, and nothing on
    # the page said why. Three columns that used to divide and no longer do are
    # worse than three columns that never did: the reader has a habit.
    #
    # So the two steps are both on the page. socket over capture gives est vol,
    # est vol over baseline med gives pm_rvol, and the capture column says
    # where its share came from.
    header = (
        f"  {'ticker':<10} {'price':>9} {'priced at':>17} {'socket vol':>12} "
        f"{'capture':>8} {'est vol':>14} {'baseline med':>13} {'pm_rvol':>10} "
        f"{'bars':>5}"
    )
    print(header)
    job_status.produced("rows tabled", len(candidates))
    for candidate in candidates:
        baseline_row = candidate.get("baseline") or {}
        median = baseline_row.get("median_volume")
        pm_volume = candidate.get("pm_volume")
        estimated = candidate.get("pm_volume_consolidated")
        share = candidate.get("pm_capture_share")
        priced_at = str(candidate.get("price_time") or "null")
        print(
            f"  {candidate.get('symbol', ''):<10} "
            f"{candidate.get('price') if candidate.get('price') is not None else 'null':>9} "
            f"{priced_at[11:] if len(priced_at) > 11 else priced_at:>17} "
            f"{pm_volume if pm_volume is not None else 'null':>12} "
            f"{share if share is not None else 'null':>8} "
            f"{estimated if estimated is not None else 'null':>14} "
            f"{median if median is not None else 'null':>13} "
            f"{candidate.get('pm_rvol') if candidate.get('pm_rvol') is not None else 'null':>10} "
            f"{candidate.get('bars_collected', 0):>5}"
        )
        # Where the share came from, because a symbol on the file wide default
        # and a symbol on its own measurement are different evidence and the
        # number alone cannot say which.
        basis = candidate.get("pm_capture_basis")
        if basis:
            print(f"             capture share: {basis}")
        reason = candidate.get("pm_rvol_reason")
        if reason:
            print(f"             rvol null because: {reason}")

    coverage = packet.get("collector_coverage") or {}
    if coverage.get("requested") is not None:
        print(f"gate: collector subscribed {coverage['requested']} symbols "
              f"(cap {coverage.get('socket_cap')}), {coverage.get('produced_bars')} "
              f"produced bars, peak {coverage.get('peak_trades_per_minute')} "
              "trades per minute")
        # Split the way collector_coverage now splits it. A symbol that sent a
        # replayed print from before the window is absent from the bars for the
        # same reason as one that sent nothing, and is not the same failure:
        # the replay proves the subscription was accepted. This line said
        # NOTHING about all four on 2026-08-20 while the report, correctly, did
        # not, and an operator table that contradicts the report it gates is
        # worse than one that says less.
        nothing = coverage.get("silent_with_nothing")
        replayed = coverage.get("silent_with_replay_only")
        if nothing or replayed:
            if nothing:
                print(f"gate: {len(nothing)} subscribed symbol(s) produced NOTHING: "
                      + ", ".join(nothing))
            if replayed:
                print(f"gate: {len(replayed)} subscribed symbol(s) produced only a "
                      "replayed print from outside the collection window, so the "
                      "subscription was accepted and the window was silent: "
                      + ", ".join(replayed))
        elif coverage.get("silent_symbols"):
            # A packet written before the split. Reported the old way rather
            # than dropped, because an older run directory is still evidence.
            print(f"gate: {coverage['silent']} subscribed symbol(s) produced no bars: "
                  + ", ".join(coverage["silent_symbols"]))
    elif coverage.get("reason"):
        print(f"gate: collector coverage unknown, {coverage['reason']}")

    health = (packet.get("job_health") or {}).get("line")
    if health:
        print(f"gate: {health}")

    dropped = packet.get("dropped_no_coverage") or []
    if dropped:
        print(f"gate: {len(dropped)} candidate(s) dropped for no collector coverage: "
              + ", ".join(row["symbol"] for row in dropped))

    print()
    if UNVERIFIED_MARKER.exists():
        print(f"gate: {UNVERIFIED_MARKER} exists, deliver.py will refuse to email.")
        print("gate: when this table looks sane on a real morning, delete that file to go live.")
    else:
        print("gate: no UNVERIFIED marker, delivery is armed.")
    return 0


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the first morning verification table.")
    parser.add_argument("--packet", metavar="PATH",
                        help="Packet to verify. Defaults to runs/<today>/packet.json.")
    parser.add_argument("--arm", action="store_true",
                        help="Recreate the UNVERIFIED marker to disarm delivery again.")
    args = parser.parse_args(argv)

    if args.arm:
        UNVERIFIED_MARKER.unlink(missing_ok=True)
        ensure_marker()
        return 0

    packet_path = (
        Path(args.packet) if args.packet
        else config.run_path(ettime.today_et().isoformat()) / "packet.json"
    )
    if not packet_path.is_file():
        print(f"gate: no packet at {packet_path}, run scan.py first")
        return 1
    return print_table(packet_path)


if __name__ == "__main__":
    sys.exit(job_status.run("verify", main, ok_codes=OK_CODES))
