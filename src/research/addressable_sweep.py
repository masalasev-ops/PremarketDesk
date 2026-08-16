"""What the addressable target actually is, measured across the cached sessions.

Recall has been argued against every universe name that gapped. That
denominator conflates two different failures: a name discovery never saw, and
a name the day screen was built to reject. Only the first is a discovery
failure, and tuning toward the combined number chases a ceiling the screen
cannot reach by design.

This measures the other denominator. For every cached session it counts the
gappers, the gappers that also satisfy every non-premarket day_setup condition
(the addressable target), and what each floor costs to get from one to the
other. It reuses pool_recall's definitions rather than restating them, because
two definitions of the same target is the defect, not either one.

It reads data/backtest/eod and spends no API calls.

One limitation, stated rather than buried: market caps come from the current
universe.json, so a session from May is screened against an August market cap.
For names near the floor that is a real source of error. It is acceptable for a
distribution and would not be acceptable for a per-name claim.

Run:

    PYTHONPATH=src .venv/Scripts/python.exe -m research.addressable_sweep
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from typing import Any

from core import config, criteria
from night import pool_recall

_CRIT = criteria.load()

EOD_DIR = config.DATA_DIR / "backtest" / "eod"


def _load_sessions() -> list[tuple[str, dict[str, Any]]]:
    """Every cached end of day file, oldest first."""
    out = []
    for path in sorted(EOD_DIR.glob("*.json")):
        try:
            out.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            print(f"sweep: skipping {path.name}, {type(exc).__name__}")
    return out


def _as_rows(cache: dict[str, Any]) -> list[dict[str, Any]]:
    """Cached bars in the shape pool_recall.actual_gappers already understands."""
    return [
        {"code": symbol, "open": bar.get("o"), "volume": bar.get("v")}
        for symbol, bar in cache.items()
    ]


def _distribution(values: list[int | float], label: str) -> dict[str, Any]:
    if not values:
        return {"label": label, "sessions": 0, "note": "nothing measured"}
    ordered = sorted(values)

    def pct(p: float) -> float:
        index = min(int(p * (len(ordered) - 1)), len(ordered) - 1)
        return ordered[index]

    return {
        "label": label,
        "sessions": len(ordered),
        "min": ordered[0],
        "p25": pct(0.25),
        "median": round(statistics.median(ordered), 2),
        "mean": round(statistics.fmean(ordered), 2),
        "p75": pct(0.75),
        "max": ordered[-1],
    }


def _print_distribution(dist: dict[str, Any]) -> None:
    if not dist.get("sessions"):
        print(f"    {dist['label']:<44} nothing measured")
        return
    print(f"    {dist['label']:<44} min {dist['min']:>6}  p25 {dist['p25']:>6}  "
          f"median {dist['median']:>7}  mean {dist['mean']:>7}  "
          f"p75 {dist['p75']:>6}  max {dist['max']:>6}")


def run(write: bool = True) -> dict[str, Any]:
    sessions = _load_sessions()
    if len(sessions) < 2:
        raise SystemExit(f"need at least two cached sessions in {EOD_DIR}")

    universe_payload = json.loads(
        (config.DATA_DIR / "universe.json").read_text(encoding="utf-8")
    )
    universe_rows = {
        str(row.get("symbol", "")).upper(): row
        for row in (universe_payload.get("symbols") or [])
    }
    universe_symbols = set(universe_rows)
    gap_rule = _CRIT.rule("discovery", "gap_pct")

    per_session: list[dict[str, Any]] = []
    sensitivity_totals: dict[str, list[int]] = {}
    biggest_addressable = 0
    biggest_total = 0
    excluded_gaps: list[float] = []
    addressable_gaps: list[float] = []

    for index in range(1, len(sessions)):
        prior_date, prior_cache = sessions[index - 1]
        today_date, today_cache = sessions[index]

        prior_closes = {
            symbol: bar["c"]
            for symbol, bar in prior_cache.items()
            if bar.get("c")
        }
        gappers = pool_recall.actual_gappers(
            _as_rows(today_cache), prior_closes, universe_symbols, gap_rule
        )
        target = pool_recall.addressable_target(gappers, universe_rows)
        funnel = target["funnel"]

        # Does the floor remove the biggest mover of the day. That is the claim
        # the market cap argument rests on, so it gets counted rather than
        # asserted.
        if gappers:
            biggest = max(gappers.values(), key=lambda row: abs(row["gap_at_open_pct"]))
            biggest_total += 1
            if biggest["symbol"] in target["addressable"]:
                biggest_addressable += 1

        for symbol, row in gappers.items():
            if symbol in target["addressable"]:
                addressable_gaps.append(abs(row["gap_at_open_pct"]))
            else:
                excluded_gaps.append(abs(row["gap_at_open_pct"]))

        for label, count in target["market_cap_sensitivity"].items():
            sensitivity_totals.setdefault(label, []).append(count)

        per_session.append({
            "session_date": today_date,
            "prior_session": prior_date,
            "gapped": funnel["gapped"],
            "after_price_floor": funnel["after_price_floor"],
            "addressable": funnel["addressable"],
            "market_cap_floor_cost": funnel["market_cap_floor_cost"],
            "no_market_cap_on_file": funnel["no_market_cap_on_file"],
        })

    gapped_dist = _distribution([r["gapped"] for r in per_session], "raw gappers per session")
    addressable_dist = _distribution(
        [r["addressable"] for r in per_session], "ADDRESSABLE TARGET per session"
    )
    cost_dist = _distribution(
        [r["market_cap_floor_cost"] for r in per_session],
        "gappers removed by the 1B floor",
    )
    share_dist = _distribution(
        [
            round(100.0 * r["market_cap_floor_cost"] / r["gapped"], 2)
            for r in per_session if r["gapped"]
        ],
        "percent of gappers the 1B floor removes",
    )

    print(f"sweep: {len(per_session)} sessions measured from {per_session[0]['session_date']} "
          f"to {per_session[-1]['session_date']}, zero API calls")
    print(f"sweep: gap floor {gap_rule.describe()} percent, market cap floor "
          f"{_CRIT.rule('day_setup', 'market_cap').describe()}, price floor "
          f"{_CRIT.rule('day_setup', 'price').describe()}")
    print()
    print("  distributions")
    for dist in (gapped_dist, addressable_dist, cost_dist, share_dist):
        _print_distribution(dist)
    print()

    print("  market cap floor sensitivity, addressable names per session")
    sensitivity_summary = {}
    for label, counts in sensitivity_totals.items():
        dist = _distribution(counts, label)
        sensitivity_summary[label] = dist
        _print_distribution(dist)
    print()

    print("  does the floor remove the biggest mover of the day")
    print(f"    biggest gapper was addressable in {biggest_addressable} of "
          f"{biggest_total} sessions "
          f"({100.0 * biggest_addressable / biggest_total:.1f}%)"
          if biggest_total else "    no sessions had a gapper")
    print()
    print("  gap magnitude, addressable versus removed by the floor")
    if addressable_gaps:
        print(f"    addressable        n {len(addressable_gaps):>6}  "
              f"median |gap| {statistics.median(addressable_gaps):>6.2f}%  "
              f"mean {statistics.fmean(addressable_gaps):>6.2f}%")
    if excluded_gaps:
        print(f"    removed by floors  n {len(excluded_gaps):>6}  "
              f"median |gap| {statistics.median(excluded_gaps):>6.2f}%  "
              f"mean {statistics.fmean(excluded_gaps):>6.2f}%")
    print()

    payload = {
        "generated_at": None,
        "sessions_measured": len(per_session),
        "first_session": per_session[0]["session_date"],
        "last_session": per_session[-1]["session_date"],
        "api_calls": 0,
        "gap_floor": gap_rule.describe(),
        "market_cap_floor": _CRIT.rule("day_setup", "market_cap").describe(),
        "price_floor": _CRIT.rule("day_setup", "price").describe(),
        "conditions_applied": ["gap_pct", "price", "market_cap"],
        "conditions_excluded": ["premarket_rvol", "require_above_prior_high"],
        "limitation": (
            "market caps come from the current universe.json, so an older session "
            "is screened against a newer market cap"
        ),
        "raw_gappers": gapped_dist,
        "addressable_target": addressable_dist,
        "market_cap_floor_cost": cost_dist,
        "market_cap_floor_cost_percent": share_dist,
        "market_cap_sensitivity": sensitivity_summary,
        "biggest_gapper_addressable_sessions": biggest_addressable,
        "biggest_gapper_sessions": biggest_total,
        "gap_magnitude": {
            "addressable_median": round(statistics.median(addressable_gaps), 4)
            if addressable_gaps else None,
            "addressable_n": len(addressable_gaps),
            "removed_median": round(statistics.median(excluded_gaps), 4)
            if excluded_gaps else None,
            "removed_n": len(excluded_gaps),
        },
        "per_session": per_session,
    }

    if write:
        from core import ettime

        payload["generated_at"] = ettime.stamp(ettime.now_et())
        path = config.DATA_DIR / "addressable_sweep.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"sweep: wrote {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the addressable target across cached sessions."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write addressable_sweep.json.")
    args = parser.parse_args(argv)
    run(write=not args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
