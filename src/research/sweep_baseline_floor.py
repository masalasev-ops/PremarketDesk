"""What raising the RVOL denominator floor would cost, at every candidate value.

An instrument, not a pipeline step. Nothing downstream reads its output.

    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.sweep_baseline_floor
    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.sweep_baseline_floor --floors 2000,5000,10000

CRITERIA [Baseline] min_baseline_premarket_volume is a seed, and the floor note
measured on 2026-08-28 what it buys: just over the floor, one ordinary session
in five reaches the top RVOL band against one in twenty for the largest names.
The note then declined to raise it, because the floor does not travel alone,
and called the change owed "a study, not an edit". This is that study.

IT TAKES NO VENDOR CALL. research/float_rotation_study.py records sweep_rows,
four fields per scored row: the baseline median that decides which side of a
floor the row sits on, the volume the ratio is built from, the rotation, and
whether the row is in the top-by-gap slice the shipped edges are fitted on.
Everything below is arithmetic on that file, which is the whole reason those
rows are recorded. Both earlier re-fits carried only quantiles, and a quantile
of one population does not yield the quantile of another, so answering a
question about numbers already measured twice cost a third vendor run.

The edges are re-fitted by the same functions float_rotation_study uses, at the
same quantiles, against the RVOL payout recomputed on the population each floor
produces. A floor that refuses more names moves rows out of the overlap and
into the rescued set, which changes BOTH the target and the distribution the
edges are read off, so neither can be carried over from the shipped fit.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

from core import config
from core import criteria

_CRIT = criteria.load()

STUDY_PATH = config.DATA_DIR / "float_rotation_study.json"

# Boundaries for the report, not thresholds. Nothing reads them.
DEFAULT_FLOORS = (1_000, 2_000, 5_000, 10_000, 25_000)


def round_down(value: float) -> float:
    """Two significant figures, downward. float_rotation_study.round_down.

    Copied rather than imported because importing that module pulls probe_alpaca
    and a research HTTP client, and this script's entire argument is that it
    needs no vendor. A claim holds the two implementations to the same answers.
    """
    if value <= 0:
        return 0.0
    power = math.floor(math.log10(value)) - 1
    scaled = math.floor(round(value / (10 ** power), 9))
    return round(scaled * (10 ** power), -power + 1)


def edge_at(values: list[float], share: float) -> float:
    """The value that this share of the population exceeds."""
    ordered = sorted(values, reverse=True)
    index = min(max(int(round(share * len(ordered))) - 1, 0), len(ordered) - 1)
    return ordered[index]


def rvol_payout(values: list[float]) -> tuple[float, float]:
    two = sum(1 for v in values
              if _CRIT.band_number("score_premarket_rvol", v) >= 2) / len(values)
    one = sum(1 for v in values
              if _CRIT.band_number("score_premarket_rvol", v) == 1) / len(values)
    return two, one


def fit(rows: list[list[Any]], floor: float, top_only: bool) -> dict[str, Any]:
    """Re-fit the rotation edges against one candidate floor.

    A row carries [median or null, volume, rotation, in_top]. median is null
    only where the history was too short for any floor to matter, so those rows
    are rescued at every floor. Everything else is decided by the floor.
    """
    use = [r for r in rows if (r[3] == 1 or not top_only)]
    overlap: list[float] = []
    rescued: list[float] = []
    paired: list[float] = []
    for median, volume, rotation, _in_top in use:
        has_rvol = median is not None and median > 0 and median >= floor
        if has_rvol:
            overlap.append(rotation)
            paired.append(volume / median)
        else:
            rescued.append(rotation)
    if not paired or not rescued:
        return {"floor": floor, "note": "one of the populations is empty",
                "overlap_n": len(overlap), "rescued_n": len(rescued)}

    two_share, one_share = rvol_payout(paired)
    exact_two = edge_at(rescued, two_share)
    exact_one = edge_at(rescued, two_share + one_share)

    # What the day screen's rvol floor admits, and the rotation edge admitting
    # the same share. The day screen has NO rotation alternative today, which
    # is why this number matters: without it, every name a raised floor refuses
    # leaves the day watchlist outright however busy it was.
    day_rule = _CRIT.rule("day_setup", "premarket_rvol")
    day_share = sum(1 for v in paired if day_rule.test(v)) / len(paired)
    day_exact = edge_at(rescued, day_share) if day_share else None

    return {
        "floor": floor,
        "overlap_n": len(overlap),
        "rescued_n": len(rescued),
        "rvol_target": {"two_points": round(two_share, 4),
                        "one_point": round(one_share, 4)},
        "refitted_edges": {"two_points": round_down(exact_two),
                           "one_point": round_down(exact_one)},
        "refitted_exact": {"two_points": round(exact_two, 8),
                           "one_point": round(exact_one, 8)},
        "day_screen": {
            "rvol_floor": day_rule.describe(),
            "share_of_paired_rvol_admitted": round(day_share, 4),
            "rotation_edge_admitting_the_same_share":
                round_down(day_exact) if day_exact else None,
        },
    }


def run(floors: tuple[int, ...] = DEFAULT_FLOORS) -> dict[str, Any]:
    if not STUDY_PATH.is_file():
        raise SystemExit(
            f"{STUDY_PATH} is absent. Run research.float_rotation_study first: "
            "this script is arithmetic on the rows that run records.")
    study = json.loads(STUDY_PATH.read_text(encoding="utf-8"))
    rows = study.get("sweep_rows")
    if not rows:
        raise SystemExit(
            f"{STUDY_PATH} carries no sweep_rows, so it predates the field this "
            "script reads. Re-run research.float_rotation_study.")

    bands = _CRIT.bands("score_premarket_float_rotation")
    edges = [band.rule.value for band in bands if band.rule is not None]
    shipped = {"two_points": edges[0] if edges else None,
               "one_point": edges[1] if len(edges) > 1 else None}
    shipped_floor = _CRIT.number("baseline", "min_baseline_premarket_volume")

    result: dict[str, Any] = {
        "measured_at": study.get("measured_at"),
        "study_sessions": study.get("sessions"),
        "sweep_rows": len(rows),
        "shipped_floor": shipped_floor,
        "shipped_edges": shipped,
        "slices": {},
    }
    for slice_name, top_only in (("all_addressable", False),
                                 ("top_by_gap", True)):
        result["slices"][slice_name] = [fit(rows, f, top_only) for f in floors]

    print(f"sweep over {len(rows):,} scored rows from "
          f"{result['study_sessions']} sessions, measured "
          f"{result['measured_at']}")
    print(f"shipped floor {shipped_floor:,.0f}, shipped edges "
          f"{shipped['two_points']} and {shipped['one_point']}\n")
    for slice_name, fits in result["slices"].items():
        print(f"  {slice_name}")
        print(f"    {'floor':>8} {'overlap':>8} {'rescued':>8} "
              f"{'2pt target':>11} {'2pt edge':>9} {'1pt edge':>9} "
              f"{'day edge':>9}")
        for row in fits:
            if "note" in row:
                print(f"    {row['floor']:>8,} {row['note']}")
                continue
            print(f"    {row['floor']:>8,} {row['overlap_n']:>8,} "
                  f"{row['rescued_n']:>8,} "
                  f"{row['rvol_target']['two_points']:>11.4f} "
                  f"{row['refitted_edges']['two_points']:>9} "
                  f"{row['refitted_edges']['one_point']:>9} "
                  f"{row['day_screen']['rotation_edge_admitting_the_same_share']:>9}")
        print()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-fit the rotation edges at candidate denominator floors.")
    parser.add_argument("--floors", default=None,
                        help="Comma separated floors. Default "
                             + ",".join(str(f) for f in DEFAULT_FLOORS))
    args = parser.parse_args(argv)
    floors = (tuple(int(x) for x in args.floors.split(","))
              if args.floors else DEFAULT_FLOORS)
    run(floors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
