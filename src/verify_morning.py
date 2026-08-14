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
the next morning goes out. Nothing in the code ever deletes it, and nothing
recreates it on its own either: the marker is created exactly once at install
time and by the explicit --arm flag, because a marker that quietly respawned
after the human removed it would overrule a decision that belongs to them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config
import ettime
import job_status

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
        print("gate: the packet has no candidates to verify")
        return 1

    print(f"gate: verification table for {packet.get('session_date')}, "
          f"packet generated {packet.get('generated_at')}")
    build = packet.get("build") or {}
    print(f"gate: build {build.get('commit') or 'unknown'}"
          f"{' (working tree dirty)' if build.get('dirty') else ''}")
    header = (
        f"  {'ticker':<10} {'price':>9} {'priced at':>17} {'pm volume':>12} "
        f"{'baseline med':>13} {'pm_rvol':>10} {'bars':>5}"
    )
    print(header)
    job_status.produced("rows tabled", len(candidates))
    for candidate in candidates:
        baseline_row = candidate.get("baseline") or {}
        median = baseline_row.get("median_volume")
        pm_volume = candidate.get("pm_volume")
        priced_at = str(candidate.get("price_time") or "null")
        print(
            f"  {candidate.get('symbol', ''):<10} "
            f"{candidate.get('price') if candidate.get('price') is not None else 'null':>9} "
            f"{priced_at[11:] if len(priced_at) > 11 else priced_at:>17} "
            f"{pm_volume if pm_volume is not None else 'null':>12} "
            f"{median if median is not None else 'null':>13} "
            f"{candidate.get('pm_rvol') if candidate.get('pm_rvol') is not None else 'null':>10} "
            f"{candidate.get('bars_collected', 0):>5}"
        )
        reason = candidate.get("pm_rvol_reason")
        if reason:
            print(f"             rvol null because: {reason}")

    coverage = packet.get("collector_coverage") or {}
    if coverage.get("requested") is not None:
        print(f"gate: collector subscribed {coverage['requested']} symbols "
              f"(cap {coverage.get('socket_cap')}), {coverage.get('produced_bars')} "
              f"produced bars, peak {coverage.get('peak_trades_per_minute')} "
              "trades per minute")
        if coverage.get("silent_symbols"):
            print(f"gate: {coverage['silent']} subscribed symbol(s) produced NOTHING: "
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
        else config.run_dir(ettime.today_et().isoformat()) / "packet.json"
    )
    if not packet_path.is_file():
        print(f"gate: no packet at {packet_path}, run scan.py first")
        return 1
    return print_table(packet_path)


if __name__ == "__main__":
    sys.exit(job_status.run("verify", main))
