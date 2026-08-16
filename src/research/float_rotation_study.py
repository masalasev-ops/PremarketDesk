"""What premarket float rotation looks like, and how it compares to RVOL.

Float rotation is premarket volume divided by shares float. Unlike RVOL it
needs no history, so it is computable on a name's first appearance, which is
exactly the population RVOL cannot score. That makes it worth having, and it
makes its scoring bands worth measuring rather than guessing.

Two things are measured, and the second is the one that decides the bands.

The distribution of float rotation across the cached sessions, which says what
values actually occur. And the distribution of RVOL over the SAME population,
reconstructed the way the live path computes it, which says what those values
have to be worth. The two measures share one score slot as alternatives, so if
their bands are not matched to each other the slot pays differently depending
on which measure filled it, and a name would score higher for the mere fact of
having no baseline. The bands are therefore chosen to award the same share of
the population the same points, and that share is recorded.

Three details the numbers depend on:

The window is not the whole premarket. The live numerator is the collector's
volume from CRITERIA [collector] start_time to the scan's run_time, so both
measures use exactly that window. Measuring 04:00 to 08:30 would set the bands
against a numerator far larger than the one the scan computes, and every live
name would land a band too low.

The RVOL denominator uses the OTHER window, 04:00 to the cutoff, because that
is what the cached baseline accumulates. Reproducing that asymmetry is the
point: it is what makes the live ratio a lower bound, and a calibration that
quietly fixed it would not describe the ratio being calibrated.

Volume comes from Alpaca, the only source that serves the whole universe for a
past session. The collector only ever saw the 42 names it had slots for, so its
own history cannot describe the population the bands apply to. Float comes from
data/float_cache.json. Neither is a live dependency.

Run:

    PYTHONPATH=src .venv/Scripts/python.exe -m research.float_rotation_study
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from typing import Any

from collect import baseline
from core import config, criteria, ettime
from night import pool_recall
from research import float_cache
import probe_alpaca

_CRIT = criteria.load()

EOD_DIR = config.DATA_DIR / "backtest" / "eod"
OUT_PATH = config.DATA_DIR / "float_rotation_study.json"

# Candidate band edges. These are NOT thresholds and nothing reads them to make
# a decision. They exist so the edge finally written into CRITERIA is chosen
# against a recorded share of the population rather than by taste.
_CANDIDATE_EDGES = (
    0.0002, 0.0005, 0.001, 0.002, 0.003, 0.005,
    0.0075, 0.01, 0.015, 0.02, 0.03, 0.05,
)


def _utc(day: str, section: str, key: str) -> str:
    date = ettime.parse_date(day)
    hour, minute = _CRIT.clock(section, key)
    when = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=ettime.ET)
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def volume_between(probe: Any, start: str, end: str, codes: list[str]) -> tuple[dict[str, float], bool]:
    """Shares traded per symbol between two UTC stamps. (volumes, complete)."""
    volumes: dict[str, float] = {}
    complete = True
    for index in range(0, len(codes), 2000):
        chunk = codes[index:index + 2000]
        token, pages = None, 0
        while True:
            params = {
                "symbols": ",".join(chunk), "timeframe": "1Min",
                "start": start, "end": end, "limit": 10000, "feed": "sip",
            }
            if token:
                params["page_token"] = token
            status, payload, _ = probe.get(params)
            pages += 1
            if status != 200:
                complete = False
                break
            for symbol, bars in ((payload.get("bars") or {}).items()):
                for bar in bars or []:
                    volumes[symbol] = volumes.get(symbol, 0.0) + float(bar.get("v") or 0)
            token = payload.get("next_page_token")
            if not token or pages >= 400:
                complete = complete and not token
                break
    return volumes, complete


def _percentiles(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def pct(p: float) -> float:
        return ordered[min(int(p * (len(ordered) - 1)), len(ordered) - 1)]

    return {
        "n": len(ordered), "min": ordered[0],
        "p10": pct(0.10), "p25": pct(0.25), "p50": pct(0.50), "p75": pct(0.75),
        "p90": pct(0.90), "p95": pct(0.95), "p99": pct(0.99), "max": ordered[-1],
        "mean": statistics.fmean(ordered),
    }


def _show(label: str, dist: dict[str, Any], places: int = 5) -> None:
    if not dist.get("n"):
        print(f"  {label:<38} nothing measured")
        return
    fmt = f".{places}f"
    print(f"  {label:<38} n {dist['n']:>5}  p25 {dist['p25']:{fmt}}  "
          f"median {dist['p50']:{fmt}}  p75 {dist['p75']:{fmt}}  "
          f"p90 {dist['p90']:{fmt}}  p95 {dist['p95']:{fmt}}  max {dist['max']:.4f}")


def run(sessions: int | None = None, write: bool = True) -> dict[str, Any]:
    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    universe_rows = {str(r.get("symbol", "")).upper(): r for r in payload["symbols"]}
    universe_symbols = set(universe_rows)
    gap_rule = _CRIT.rule("discovery", "gap_pct")
    candidate_count = _CRIT.integer("scan", "candidate_count")
    lookback = _CRIT.integer("baseline", "lookback_sessions")
    min_sessions = _CRIT.integer("baseline", "min_sessions_for_rvol")
    volume_floor = _CRIT.number("baseline", "min_baseline_premarket_volume")

    floats = float_cache.load_cache()["symbols"]
    days = sorted(p.stem for p in EOD_DIR.glob("*.json"))
    pairs = list(zip(days, days[1:]))
    if sessions:
        pairs = pairs[-sessions:]

    probe = probe_alpaca.Probe()
    all_codes = [row["code"] for row in payload["symbols"]]

    # Rolling history of 04:00 to cutoff volume per symbol, which is what the
    # cached baseline accumulates. Keyed by symbol, oldest first.
    history: dict[str, list[float]] = {}

    rot_all: list[float] = []
    rot_top: list[float] = []
    rvol_all: list[float] = []
    rvol_top: list[float] = []
    # Names where BOTH measures exist, which is the only fair place to match
    # one band set to the other. RVOL is available for barely half the scored
    # population, and that half is not a random half: it is the established
    # names. Matching a payout computed on them against a rotation payout
    # computed on everybody would be comparing two different populations.
    paired: list[tuple[float, float]] = []
    # Same thing without the top-by-gap restriction, so the overlap count in
    # the report reconciles against the coverage table instead of looking like
    # a different quantity that happens to share a name.
    paired_all: list[tuple[float, float]] = []
    # Rotation split by which band set the name will actually be scored under.
    overlap_rot_all: list[float] = []
    overlap_rot_top: list[float] = []
    rescued_rot_all: list[float] = []
    rescued_rot_top: list[float] = []
    scored_by_rvol = scored_by_rotation = scored_by_either = scored_by_neither = 0
    rescued = 0
    rescue_examples: list[dict[str, Any]] = []
    no_float = no_volume = 0
    per_session: list[dict[str, Any]] = []

    print(f"measuring {len(pairs)} sessions. numerator window "
          f"{_CRIT.clock_text('collector', 'start_time')} to "
          f"{_CRIT.clock_text('scan', 'run_time')} ET, baseline window "
          f"{_CRIT.clock_text('baseline', 'session_start')} to "
          f"{_CRIT.clock_text('scan', 'run_time')} ET")

    for index, (prior, today) in enumerate(pairs):
        # The baseline window, for every universe name, so the rolling history
        # is there when a name first becomes a gapper.
        base_vol, base_ok = volume_between(
            probe, _utc(today, "baseline", "session_start"),
            _utc(today, "scan", "run_time"), all_codes)
        num_vol, num_ok = volume_between(
            probe, _utc(today, "collector", "start_time"),
            _utc(today, "scan", "run_time"), all_codes)
        if not (base_ok and num_ok):
            print(f"{today}: sweep incomplete, session skipped")
            continue

        prior_cache = json.loads((EOD_DIR / f"{prior}.json").read_text(encoding="utf-8"))
        today_cache = json.loads((EOD_DIR / f"{today}.json").read_text(encoding="utf-8"))
        prior_closes = {s: b["c"] for s, b in prior_cache.items() if b.get("c")}
        rows = [{"code": s, "open": b.get("o"), "volume": b.get("v")}
                for s, b in today_cache.items()]
        gappers = pool_recall.actual_gappers(rows, prior_closes, universe_symbols, gap_rule)
        addressable = pool_recall.addressable_target(gappers, universe_rows)["addressable"]

        ranked = sorted(addressable.items(),
                        key=lambda kv: abs(kv[1].get("gap_at_open_pct") or 0), reverse=True)
        top_symbols = {s for s, _ in ranked[:candidate_count]}

        session_scored = 0
        for symbol in addressable:
            code = symbol.split(".")[0]
            volume = num_vol.get(code)
            if volume is None:
                no_volume += 1
                continue

            # --- RVOL exactly as the live path builds it
            past = history.get(code, [])[-lookback:]
            rvol = None
            if len(past) >= min_sessions:
                median = statistics.median(past)
                if median > 0 and median >= volume_floor:
                    rvol = volume / median

            # --- float rotation
            row = floats.get(symbol) or {}
            share_float = row.get("sharesFloat")
            outstanding = row.get("sharesOutstanding")
            rotation = None
            if share_float and share_float > 0 and not (
                    outstanding and share_float > outstanding * 1.01):
                rotation = volume / float(share_float)
            elif not share_float:
                no_float += 1

            if rvol is not None:
                rvol_all.append(rvol)
                if symbol in top_symbols:
                    rvol_top.append(rvol)
            if rotation is not None:
                rot_all.append(rotation)
                if symbol in top_symbols:
                    rot_top.append(rotation)
            if rvol is not None and rotation is not None and symbol in top_symbols:
                paired.append((rvol, rotation))
            # The two populations the two band sets actually serve. A name in
            # the overlap is scored by RVOL and NEVER sees the rotation bands;
            # a rescued name sees nothing else. So the rotation bands have to
            # be calibrated on rescued, and this is what makes that checkable.
            if rotation is not None:
                if rvol is not None:
                    overlap_rot_all.append(rotation)
                    if symbol in top_symbols:
                        overlap_rot_top.append(rotation)
                else:
                    rescued_rot_all.append(rotation)
                    if symbol in top_symbols:
                        rescued_rot_top.append(rotation)
            if rvol is not None and rotation is not None:
                paired_all.append((rvol, rotation))

            has_rvol, has_rot = rvol is not None, rotation is not None
            scored_by_rvol += has_rvol
            scored_by_rotation += has_rot
            scored_by_either += has_rvol or has_rot
            scored_by_neither += not (has_rvol or has_rot)
            if has_rot and not has_rvol:
                rescued += 1
                session_scored += 1
                if symbol in top_symbols and len(rescue_examples) < 12:
                    rescue_examples.append({
                        "date": today, "symbol": symbol,
                        "gap_at_open_pct": addressable[symbol].get("gap_at_open_pct"),
                        "premarket_volume": volume,
                        "shares_float": share_float,
                        "float_rotation": round(rotation, 6),
                        "baseline_sessions_available": len(past),
                    })

        per_session.append({"date": today, "addressable": len(addressable),
                            "rescued_by_rotation": session_scored})

        # Roll the history forward with today's baseline window volumes.
        for code in all_codes:
            history.setdefault(code, []).append(base_vol.get(code, 0.0))
        if (index + 1) % 20 == 0:
            print(f"  ... {index + 1}/{len(pairs)} sessions, {probe.request_count} requests")

    def share_above(values: list[float]) -> dict[str, float]:
        return {str(e): round(sum(1 for v in values if v > e) / len(values), 4)
                for e in _CANDIDATE_EDGES} if values else {}

    # What the live RVOL bands actually pay out, over the population that will
    # be scored. This is the target the rotation bands are matched to.
    def rvol_points_share(values: list[float]) -> dict[str, float]:
        if not values:
            return {}
        two = sum(1 for v in values if _CRIT.band_number("score_premarket_rvol", v) >= 2)
        one = sum(1 for v in values if _CRIT.band_number("score_premarket_rvol", v) == 1)
        return {"two_points": round(two / len(values), 4),
                "one_point": round(one / len(values), 4),
                "zero": round((len(values) - two - one) / len(values), 4)}

    def round_down(value: float) -> float:
        """To one significant figure, so a band edge is a number a human can
        hold, and downward so the rounding never makes a band stricter than
        the share it was matched to."""
        if value <= 0:
            return 0.0
        import math
        power = math.floor(math.log10(value))
        # round() after the scaling, because 6 * 1e-4 in binary floating point
        # is 0.0006000000000000001 and a band edge written into CRITERIA with
        # a tail like that is unreadable.
        return round(math.floor(value / (10 ** power)) * (10 ** power), -power + 1)

    def edge_at(values: list[float], share: float) -> float:
        """The value that this share of the population exceeds."""
        ordered = sorted(values, reverse=True)
        index = min(max(int(round(share * len(ordered))) - 1, 0), len(ordered) - 1)
        return ordered[index]

    def percentile_of(values: list[float], edge: float) -> float | None:
        """Where an edge sits in a distribution, as the share at or below it."""
        if not values:
            return None
        return round(sum(1 for v in values if v <= edge) / len(values), 4)

    def payout(values: list[float], two: float, one: float) -> dict[str, float]:
        """What a pair of rotation edges pays on a population."""
        if not values:
            return {}
        n = len(values)
        hi = sum(1 for v in values if v > two)
        mid = sum(1 for v in values if one <= v <= two)
        return {"two_points": round(hi / n, 4), "one_point": round(mid / n, 4),
                "zero": round((n - hi - mid) / n, 4)}

    def rvol_payout(values: list[float]) -> tuple[float, float]:
        two = sum(1 for v in values
                  if _CRIT.band_number("score_premarket_rvol", v) >= 2) / len(values)
        one = sum(1 for v in values
                  if _CRIT.band_number("score_premarket_rvol", v) == 1) / len(values)
        return two, one

    # ---- does the mapping transfer to the population it serves
    #
    # The first derivation matched the rotation bands to RVOL's payout on the
    # OVERLAP, the names carrying both measures. That was the wrong target and
    # the error is worth stating plainly rather than quietly repairing: an
    # overlap name is scored by RVOL and never sees the rotation bands at all.
    # The only names those bands ever touch are the rescued ones, the names
    # with no usable baseline. If the two populations have different rotation
    # distributions, edges calibrated on the overlap pay the wrong rate for
    # every name the fallback exists to serve.
    #
    # So both distributions are reported at the same quantiles, the current
    # edges are located in each, and the edges are then re-derived against the
    # rescued population, which is the one that actually gets them.
    transfer: dict[str, Any] = {}
    for slice_name, over, resc, pair in (
        ("all_addressable", overlap_rot_all, rescued_rot_all, paired_all),
        (f"top_{candidate_count}_by_gap", overlap_rot_top, rescued_rot_top, paired),
    ):
        if not (over and resc and pair):
            transfer[slice_name] = {"note": "one of the populations is empty"}
            continue
        two_share, one_share = rvol_payout([p[0] for p in pair])

        # The edges currently in CRITERIA, read from the file rather than
        # written here, so this comparison stays honest after they change.
        bands = _CRIT.bands("score_premarket_float_rotation")
        edges = [band.rule.value for band in bands if band.rule is not None]
        current_two = edges[0] if edges else None
        current_one = edges[1] if len(edges) > 1 else None

        exact_two = edge_at(resc, two_share)
        exact_one = edge_at(resc, two_share + one_share)
        rederived_two = round_down(exact_two)
        rederived_one = round_down(exact_one)

        transfer[slice_name] = {
            "overlap_n": len(over),
            "rescued_n": len(resc),
            "paired_n": len(pair),
            "overlap": _percentiles(over),
            "rescued": _percentiles(resc),
            "median_ratio_rescued_over_overlap": round(
                statistics.median(resc) / statistics.median(over), 4)
            if statistics.median(over) else None,
            "rvol_target": {"two_points": round(two_share, 4),
                            "one_point": round(one_share, 4)},
            "current_edges": {"two_points": current_two, "one_point": current_one},
            "current_edge_percentile_in_overlap": {
                "two_points": percentile_of(over, current_two),
                "one_point": percentile_of(over, current_one)},
            "current_edge_percentile_in_rescued": {
                "two_points": percentile_of(resc, current_two),
                "one_point": percentile_of(resc, current_one)},
            "current_edges_pay_on_overlap": payout(over, current_two, current_one),
            "current_edges_pay_on_rescued": payout(resc, current_two, current_one),
            "rederived_exact_on_rescued": {"two_points": round(exact_two, 8),
                                           "one_point": round(exact_one, 8)},
            "rederived_on_rescued": {"two_points": rederived_two,
                                     "one_point": rederived_one},
            "rederived_edges_pay_on_rescued": payout(resc, rederived_two, rederived_one),
        }

    matched: dict[str, Any] = {
        "paired_n_top_by_gap": len(paired),
        "paired_n_all_addressable": len(paired_all),
        "selection_rule_for_top_by_gap": (
            f"names in the top {candidate_count} by absolute gap at open per "
            "session, which is CRITERIA [scan] candidate_count, intersected "
            "with the names carrying BOTH measures. The all_addressable count "
            "is the same intersection without the top-by-gap restriction and "
            "is what reconciles against the coverage table."
        ),
    }

    result = {
        "measured_at": ettime.now_et().date().isoformat(),
        "matched_bands": matched,
        "mapping_transfer": transfer,
        "windows": {
            "numerator": f"{_CRIT.clock_text('collector', 'start_time')} to "
                         f"{_CRIT.clock_text('scan', 'run_time')} ET",
            "rvol_denominator": f"{_CRIT.clock_text('baseline', 'session_start')} to "
                                f"{_CRIT.clock_text('scan', 'run_time')} ET, "
                                f"median of {lookback} prior sessions",
        },
        "sessions": len(per_session),
        "candidate_count": candidate_count,
        "float_rotation": {"all_addressable": _percentiles(rot_all),
                           "top_by_gap": _percentiles(rot_top)},
        "rvol_reconstructed": {"all_addressable": _percentiles(rvol_all),
                               "top_by_gap": _percentiles(rvol_top)},
        "coverage": {
            "scored_by_rvol": scored_by_rvol,
            "scored_by_rotation": scored_by_rotation,
            "scored_by_either": scored_by_either,
            "scored_by_neither": scored_by_neither,
            "rescued_by_rotation_alone": rescued,
            "no_float_in_cache": no_float,
            "no_alpaca_volume": no_volume,
        },
        "rvol_band_payout": {"all_addressable": rvol_points_share(rvol_all),
                             "top_by_gap": rvol_points_share(rvol_top)},
        "rotation_share_above_edge": {"all_addressable": share_above(rot_all),
                                      "top_by_gap": share_above(rot_top)},
        "rescue_examples": rescue_examples,
        "per_session": per_session,
        "alpaca_requests": probe.request_count,
    }

    print(f"\nsessions measured {result['sessions']}")
    _show("float rotation, all addressable", result["float_rotation"]["all_addressable"])
    _show(f"float rotation, top {candidate_count} by gap", result["float_rotation"]["top_by_gap"])
    _show("RVOL reconstructed, all addressable", result["rvol_reconstructed"]["all_addressable"], 3)
    _show(f"RVOL reconstructed, top {candidate_count}", result["rvol_reconstructed"]["top_by_gap"], 3)

    print(f"\n  OVERLAP RECONCILIATION")
    print(f"    names carrying both measures, all addressable : "
          f"{matched['paired_n_all_addressable']}")
    print(f"    the same, restricted to the top {candidate_count} by gap  : "
          f"{matched['paired_n_top_by_gap']}")
    print(f"    coverage table implies rvol + rotation - either = "
          f"{scored_by_rvol + scored_by_rotation - scored_by_either}")

    for slice_name, block in transfer.items():
        if block.get("note"):
            print(f"\n  DOES THE MAPPING TRANSFER, {slice_name}: {block['note']}")
            continue
        print(f"\n  DOES THE MAPPING TRANSFER, {slice_name}")
        print(f"    overlap n {block['overlap_n']}, rescued n {block['rescued_n']}")
        _show("      overlap (scored by RVOL, never sees these bands)", block["overlap"])
        _show("      rescued (the only names these bands touch)", block["rescued"])
        print(f"      median ratio rescued/overlap: "
              f"{block['median_ratio_rescued_over_overlap']}")
        print(f"      current edges {block['current_edges']}")
        print(f"        sit at percentile {block['current_edge_percentile_in_overlap']} "
              "of the overlap")
        print(f"        sit at percentile {block['current_edge_percentile_in_rescued']} "
              "of the rescued")
        print(f"      they pay on overlap : {block['current_edges_pay_on_overlap']}")
        print(f"      they pay on rescued : {block['current_edges_pay_on_rescued']}")
        print(f"      RVOL target         : {block['rvol_target']}")
        print(f"      re-derived on rescued: {block['rederived_on_rescued']} "
              f"paying {block['rederived_edges_pay_on_rescued']}")

    print(f"\n  coverage: {json.dumps(result['coverage'], indent=None)}")
    print(f"\n  what the live RVOL bands pay, all addressable: "
          f"{result['rvol_band_payout']['all_addressable']}")
    print(f"  what the live RVOL bands pay, top {candidate_count}: "
          f"{result['rvol_band_payout']['top_by_gap']}")
    print("\n  share of the rotation population above each candidate edge:")
    print(f"    {'edge':>9}  {'all addressable':>16}  {'top by gap':>12}")
    for edge in _CANDIDATE_EDGES:
        a = result["rotation_share_above_edge"]["all_addressable"].get(str(edge), 0)
        t = result["rotation_share_above_edge"]["top_by_gap"].get(str(edge), 0)
        print(f"    {edge:>9}  {a:>16.4f}  {t:>12.4f}")

    if write:
        OUT_PATH.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {OUT_PATH}")
    return result


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure premarket float rotation against reconstructed RVOL.")
    parser.add_argument("--sessions", type=int, default=None,
                        help="Only the most recent N sessions. Default is every cached session.")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    run(sessions=args.sessions, write=not args.no_write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
