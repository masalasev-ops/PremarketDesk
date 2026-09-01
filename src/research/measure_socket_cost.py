"""Measure what the websocket actually costs, on the vendor's own counter.

The claim "the collector spends no API calls" was, until this existed, a
client side observation: this process made zero REST requests. What the
vendor meters for a socket connection, a subscribe frame, or a streamed
trade is the vendor's business, and the only honest way to know is to read
their counter before and after a run in which nothing else touches the
account.

So: read /api/user (apiRequests, dailyRateLimit), run the collector alone
for a fixed window against the full watchlist subscription, read /api/user
again, and report the delta alongside what the run did (bars, messages,
connections, reconnects). The measurement itself makes exactly two user
endpoint calls, and the adjusted delta subtracts them.

Two caveats the output states every time. The counter is ACCOUNT WIDE, so
run this when no other project is using the key, or the delta is theirs as
much as ours. And a run outside market hours measures connection and
subscription cost on a quiet tape; the per message question needs a run
while the tape is actually printing.

Use --chaos-reconnects 3 for the flaky morning variant; compare its delta
against a clean run's before believing a reconnect costs nothing.

ANSWERED 2026-09-01, AND THIS WRITES INTO THE SESSION CAPTURE.

The question is closed: 21,306 messages on a live regular hours tape moved
the counter by zero. DECISIONS.md 2026-09-01 eighth carries the reading and
the three part decomposition it settles. The scheduled task and
tasks/job_probe_socket_cost.bat were deleted the same day.

WHAT THIS COSTS IF YOU RUN IT ANYWAY. It launches collect_premarket, which
writes to PREMARKET_DIR/<today>.jsonl with no argument saying otherwise. That
is the same file the 07:20 collector fills, and CRITERIA calls it not
reproducible at any price. The 2026-09-01 run put 932 regular hours bars into
that day's premarket capture, every symbol's latest price then read 10:07, and
the vintage guard refused a packet built from it until the file was arbitrated
back to its pre run state. The .bat reasoned that 10:00 clears the socket cap,
which is true, and said nothing about the file.

So: back up the capture first, or expect to arbitrate it back afterwards.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core import config
from core import eodhd
from core import ettime

from collect import collect_premarket

SELF_CALLS = 2  # the before and after user endpoint reads


def read_counter(session) -> tuple[int, int]:
    response = session.get(
        f"{config.EODHD_BASE_URL}/user",
        params={"api_token": config.eodhd_token(), "fmt": "json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return int(payload.get("apiRequests") or 0), int(payload.get("dailyRateLimit") or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vendor-counter cost of a collector run.")
    parser.add_argument("--minutes", type=float, default=20.0,
                        help="Collector run length. The measured fact used 20.")
    parser.add_argument("--chaos-reconnects", type=int, default=0, metavar="N",
                        help="Force N socket drops during the run.")
    parser.add_argument("--out-dir", default=None, metavar="PATH",
                        help="REQUIRED. Where the collector writes its bars. "
                             "Must be outside data/premarket.")
    args = parser.parse_args(argv)

    # THE ONE CONDITION, and it is checked before the counter is read so a
    # refusal costs nothing. This script runs a real socket for twenty
    # minutes and the collector it launches writes wherever
    # config.PREMARKET_DIR points. On 2026-09-01 that was the session
    # capture, and 932 regular hours bars went into a file CRITERIA calls
    # not reproducible at any price. Deleting the scheduled task removed the
    # schedule and not the hazard: a hand run reproduced it exactly.
    #
    # Refused rather than defaulted. A default output path would be a
    # sensible directory this script chose, and the next reader would not
    # know a choice had been made. Being made to name it is the point.
    if not args.out_dir:
        print("measure: REFUSED. --out-dir is required and must be outside "
              f"{config.PREMARKET_DIR}.")
        print("  This runs a live socket for minutes at a time and the "
              "collector writes wherever it is pointed. Pointed at the "
              "session capture it mixes an instrument's bars into a "
              "morning's evidence, which happened on 2026-09-01 and had to "
              "be arbitrated back out.")
        print("  Try: --out-dir data/socket-cost-probe")
        return 2
    out_dir = Path(args.out_dir).expanduser().resolve()
    capture = config.PREMARKET_DIR.resolve()
    if out_dir == capture or capture in out_dir.parents:
        print(f"measure: REFUSED. --out-dir {out_dir} is inside the session "
              f"capture at {capture}, which is the one place this must not "
              "write.")
        return 2

    session = eodhd.build_session()
    before, limit = read_counter(session)
    print(f"measure: counter before {before:,} of {limit:,} "
          f"({ettime.stamp(ettime.now_et())})")
    print("measure: the counter is account wide. If anything else uses this key "
          "during the run, the delta is contaminated.")

    command = [
        sys.executable, str(config.SRC_DIR / "collect" / "collect_premarket.py"),
        "--minutes", str(args.minutes),
        "--premarket-dir", str(out_dir),
    ]
    if args.chaos_reconnects:
        command += ["--chaos-reconnects", str(args.chaos_reconnects)]
    started = time.time()
    proc = subprocess.run(command, cwd=str(config.PROJECT_ROOT))
    wall = time.time() - started
    if proc.returncode != 0:
        print(f"measure: collector exited {proc.returncode}, the delta below "
              "describes a broken run")

    after, _ = read_counter(session)
    raw_delta = after - before
    adjusted = raw_delta - SELF_CALLS

    stats: dict[str, Any] | None = collect_premarket.read_run_stats()
    last_run: dict[str, Any] = {}
    stats_file = collect_premarket.stats_path()
    if stats_file.exists():
        lines = [l for l in stats_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            try:
                last_run = json.loads(lines[-1])
            except ValueError:
                last_run = {}

    print("")
    print(f"measure: counter after  {after:,}")
    print(f"measure: raw delta      {raw_delta:,}")
    print(f"measure: adjusted delta {adjusted:,} "
          f"(minus the {SELF_CALLS} user endpoint reads this script made)")
    print(f"measure: run wall clock {wall:,.0f}s, mode {last_run.get('mode')}")
    print(f"measure: connections {last_run.get('connections')}, "
          f"reconnects {last_run.get('reconnects')}, "
          f"resubscriptions {last_run.get('resubscriptions')}, "
          f"messages {last_run.get('messages')}, "
          f"minutes written {last_run.get('minutes_written')}")
    if stats:
        print(f"measure: day totals across {stats['runs']} run(s): {stats}")

    verdict = ("the socket run moved the vendor counter by "
               f"{adjusted:,} beyond this script's own reads")
    print(f"measure: VERDICT {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
