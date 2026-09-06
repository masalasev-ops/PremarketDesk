"""Package 6.3: would a third discovery pass at 08:15 catch anything?

THE RULE AND THE BAR ARE HERE AND ARE FIXED BEFORE THE FIRST RUN, the same
discipline package 5.5 used. The plan's own words are the pre-registration:
"Measure what it would have caught from the news feed's timestamps before
arming it." This is that measurement.

THE RULE. For each cached session, sweep the overnight news feed twice
through production's own `discover.overnight_news`, once to 07:15 and once to
08:15, over the same window start. A symbol is LATE when it carries no tagged
story by 07:15 and does carry one by 08:15. A late symbol is REACHED when it
is also a big gapper, at or past [Discovery] recall_big_gap_pct, that the
shipped pool did not subscribe.

THE BAR, fixed before the run. An 08:15 pass is worth arming only if it
reaches at least 0.5 big gappers a session on average, which is one every
other morning. Below that it costs 306 credits and a scheduled task every
weekday to catch a name less often than the sweep in 5.5 catches three, and
the honest answer is no.

THE POPULATION CHANGED BEFORE THE RUN AND AFTER A SMOKE TEST, which is worth
stating plainly rather than leaving to be noticed. It was written as every
cached session. Two sessions were fetched to prove the instrument worked and
cost 18 calls and 56 seconds, so all 240 would be about 10,800 credits and two
hours of wall clock. It is a SYSTEMATIC ONE IN FOUR sample instead, 60
sessions taken by stride across the whole range rather than the first 60,
because the first 60 are all 2025 and the feed's volume is not flat across a
year.

The smoke test returned exactly 0.500, sitting on the bar, which is the least
informative number it could have produced and is why changing the population
here costs nothing: no direction was visible to steer toward.

WHAT WOULD MAKE IT VOID. The vendor filters its news from and to on UTC
DATES and the cutoff is applied by the client, so both sweeps here fetch the
same rows and differ only in where the instant cut falls. That is what makes
the comparison exact rather than two samples of a moving feed. If a future
plan filtered server side by instant, this would be comparing two fetches
instead of one fetch cut twice, and the difference would carry feed noise.

Two stages, as always: fetch is dated and spends quota, evaluate is
reproducible from the bytes.

    PYTHONPATH=src .venv/Scripts/python.exe -m research.late_news_test fetch
    PYTHONPATH=src .venv/Scripts/python.exe -m research.late_news_test evaluate
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from typing import Any

from core import config, criteria, eodhd, ettime, files

_CRIT = criteria.load()

OUT_DIR = config.PROJECT_ROOT / "data" / "research" / "late-news"
SESSIONS_DIR = config.PROJECT_ROOT / "data" / "backtest" / "sessions"

EARLY_HHMM = (7, 15)
LATE_HHMM = (8, 15)
REACH_BAR_PER_SESSION = 0.5


def _sessions() -> list[str]:
    return sorted(p.name for p in SESSIONS_DIR.iterdir() if p.is_dir())


def fetch(limit: int | None, force: bool, stride: int = 1) -> int:
    from selection import discover

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    api = eodhd.EodhdClient()
    days = _sessions()
    if stride > 1:
        days = days[::stride]
    if limit:
        days = days[:limit]

    written = spared = 0
    for index, day in enumerate(days, 1):
        target = OUT_DIR / f"{day}.json"
        if target.exists() and not force:
            spared += 1
            continue
        inputs = json.loads((SESSIONS_DIR / day / "inputs.json").read_text("utf-8"))
        universe = set(inputs.get("prior_closes") or {})
        session = ettime.parse_date(day)
        since = discover.news_window_start(session)

        sweeps: dict[str, Any] = {}
        for label, hhmm in (("early", EARLY_HHMM), ("late", LATE_HHMM)):
            until = ettime.at_hm(session, hhmm)
            result = discover.overnight_news(api, universe, since, until)
            sweeps[label] = {
                "status": result.get("status"),
                "truncated": result.get("truncated"),
                "pages": result.get("pages"),
                "names": sorted(result.get("names") or {}),
            }

        files.write_text_atomically(target, json.dumps({
            "session_date": day,
            "window_start_et": since.isoformat(),
            "early_cutoff_et": f"{EARLY_HHMM[0]:02d}:{EARLY_HHMM[1]:02d}",
            "late_cutoff_et": f"{LATE_HHMM[0]:02d}:{LATE_HHMM[1]:02d}",
            "universe_symbols": len(universe),
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sweeps": sweeps,
        }, indent=2, sort_keys=False) + "\n",
            attempts=files.ATTEMPTS, retry_s=files.RETRY_S)
        written += 1
        if index % 20 == 0 or index == len(days):
            print(f"  {index}/{len(days)}  {day}  early "
                  f"{len(sweeps['early']['names'])} name(s), late "
                  f"{len(sweeps['late']['names'])}, {eodhd.call_count()} call(s)")

    print(f"late news: {written} session(s) written, {spared} already on disk, "
          f"{eodhd.call_count()} EODHD call(s)")
    return 0


def evaluate(as_of: str | None) -> int:
    from research import backtest_pool

    big_floor = _CRIT.number("discovery", "recall_big_gap_pct")
    cap = _CRIT.integer("discovery", "max_subscribed_candidates")
    floor_slots = _CRIT.integer("discovery", "min_slots_per_tier")
    base_metrics = backtest_pool.load_metrics(as_of)
    ordering = backtest_pool.ORDERINGS["SHIPPED"]

    late_counts: list[int] = []
    reached: list[int] = []
    reached_names: list[str] = []
    truncated_sessions = 0
    scored = 0

    for day in _sessions():
        path = OUT_DIR / f"{day}.json"
        if not path.exists():
            continue
        blob = json.loads(path.read_text("utf-8"))
        early = set(blob["sweeps"]["early"]["names"])
        late = set(blob["sweeps"]["late"]["names"])
        if blob["sweeps"]["late"].get("truncated"):
            truncated_sessions += 1
        inputs = json.loads((SESSIONS_DIR / day / "inputs.json").read_text("utf-8"))
        outcome = json.loads((SESSIONS_DIR / day / "outcome.json").read_text("utf-8"))
        gappers, _actions = backtest_pool.refuse_corporate_actions(
            day, inputs.get("prior_session"), outcome["gappers"])
        big = {s for s, r in gappers.items()
               if abs(float(r.get("gap_at_open_pct") or 0.0)) >= big_floor}

        try:
            metrics, _where = backtest_pool.metrics_for_session(
                day, base_metrics, inputs)
            pool = backtest_pool.build_pool(inputs, metrics)
            ranked = backtest_pool.order_pool(pool, metrics, ordering)
            capped = backtest_pool.apply_cap(ranked, cap, tier_floor=floor_slots)
            shipped = {r["symbol"] for r in capped if r.get("subscribed")}
        except Exception:  # noqa: BLE001, a session that will not rebuild is data
            continue

        newly = late - early
        hit = newly & big - shipped
        late_counts.append(len(newly))
        reached.append(len(hit))
        reached_names.extend(sorted(hit))
        scored += 1

    if not scored:
        print("no session had both sweeps on disk. Run fetch first.")
        return 1

    mean_reached = statistics.mean(reached)
    print(f"\nlate news test, {scored} session(s)")
    print(f"  names gaining a first story 07:15 to 08:15   "
          f"mean {statistics.mean(late_counts):.1f}, max {max(late_counts)}")
    print(f"  of those, big gappers the pool missed        "
          f"total {sum(reached)}, mean {mean_reached:.3f} a session")
    print(f"  sessions where it would have reached any     "
          f"{sum(1 for r in reached if r)} of {scored}")
    if truncated_sessions:
        print(f"  sessions whose late sweep hit the page cap   {truncated_sessions}"
              "  (these UNDERSTATE the late set)")
    verdict = "CLEARS" if mean_reached >= REACH_BAR_PER_SESSION else "FAILS"
    print(f"\n  {verdict} the pre-registered bar of {REACH_BAR_PER_SESSION} "
          f"a session: {mean_reached:.3f}")
    if reached_names:
        print(f"  examples: {', '.join(reached_names[:12])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--sessions", type=int, default=None)
    f.add_argument("--force", action="store_true")
    f.add_argument("--stride", type=int, default=1,
                   help="take every Nth session, so a sample spans the whole "
                        "range instead of its first weeks")
    e = sub.add_parser("evaluate")
    e.add_argument("--as-of", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "fetch":
        return fetch(args.sessions, args.force, args.stride)
    return evaluate(args.as_of)


OK_CODES = (0,)

if __name__ == "__main__":
    sys.exit(main())
