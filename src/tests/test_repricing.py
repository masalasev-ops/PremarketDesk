"""Regression tests for the 2026-08-14 stale vintage defect and its guards.

Run directly: `python src\\test_repricing.py`, exit 0 on pass. Makes no network
calls. The evidence is the artifacts the failing morning left behind:
runs/2026-08-14/packet.json and the collector snapshot beside it.

Four claims, one per clause of the fix:
  1. Repricing from the collector reproduces this morning's real gaps in place
     of yesterday's session moves.
  3. A candidate the collector never subscribed to is dropped, not priced.
  4. A baseline median below the CRITERIA floor produces a null pm_rvol, an
     unavailable RVOL component and a null total, through the existing
     score_partial machinery rather than a second path.
  6. The packet can name the build that wrote it.
"""

from __future__ import annotations

import json
from datetime import date as dt_date
import sys
from pathlib import Path

from collect import baseline
from collect import collect_premarket
from core import config
from core import criteria
from core import ettime
from morning import scan
from core import store

_CRIT = criteria.load()
RUN_DIR = config.RUNS_DIR / "2026-08-14"
PACKET_PATH = RUN_DIR / "packet.json"
SNAPSHOT_PATH = RUN_DIR / "premarket_snapshot.jsonl"

# What the collector had recorded by 08:45, measured off the frozen snapshot
# the scan itself took. Each gap is against the 2026-08-13 close, which is the
# prior session close the fixed pipeline uses.
#
# These differ slightly from the five figures quoted when the defect was first
# reported (ARX +0.38, CLBT +0.27, WDAY +0.14, TPR -0.12, ANGX -0.92). Those
# were measured against the live collector file as it stood near 09:00, which
# by then held another fifteen minutes of bars. The snapshot is the honest
# reference for a replay: it is exactly what the 08:45 run saw, and nothing
# else can reproduce that run.
#
# All twelve are pinned rather than a sample, because the claim being tested is
# about the whole list. Note that four of them exceed one percent: SECZ, LFTO,
# ANGX and BSP genuinely moved in premarket. The property that holds for all
# twelve is not "below one percent", it is "very much smaller than the stale
# selection gap it replaced", which is asserted separately below.
EXPECTED_GAPS = {
    "ARX.US": 0.38, "CLBT.US": 0.05, "SECZ.US": 4.52, "OMER.US": -1.39,
    "AVAH.US": 0.17, "LFTO.US": 2.49, "REZI.US": 0.46, "WDAY.US": -0.19,
    "ANGX.US": -1.71, "MH.US": -0.15, "TPR.US": -0.25, "BSP.US": 1.19,
}


def _load() -> tuple[dict, dict]:
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    bars, _stats = collect_premarket.read_bars_file(SNAPSHOT_PATH)
    return packet, bars


def _rebuild(packet: dict, bars: dict) -> list[dict]:
    """The failing morning's candidates, re-run through the fixed pricing path.

    prior_close is taken from the delayed quote's previousClosePrice rather
    than from a live end of day call, because this test makes no network
    calls. That field is independent evidence of the same number: it was
    checked against EODHD's own end of day history for all twelve symbols and
    equals the 2026-08-13 close in every case.
    """
    candidates = []
    for old in packet["candidates"]:
        candidates.append({
            "symbol": old["symbol"],
            "prior_close": (old.get("quote") or {}).get("previousClosePrice"),
            "prior_high": old.get("prior_high"),
            "selection_price": old.get("price"),
            "selection_gap_pct": old.get("gap_pct"),
        })
    watchlist = {"symbols": [{"symbol": c["symbol"]} for c in candidates]}
    scan.attach_premarket_path(candidates, watchlist, scan.Packet(), bars)
    scan.price_from_collector(candidates, scan.Packet(), bars)
    scan.attach_gap(candidates)
    return candidates


def claim_one(failures: list[str]) -> None:
    packet, bars = _load()
    candidates = _rebuild(packet, bars)
    by_symbol = {c["symbol"]: c for c in candidates}

    wday = by_symbol["WDAY.US"]
    if wday["price"] == 206.45:
        failures.append("WDAY still prices at 206.45, the 2026-08-13 close")
    if wday["price_source"] != "collector":
        failures.append(f"WDAY priced from {wday['price_source']!r}, not the collector")
    if wday["prior_close"] != 206.45:
        failures.append(f"WDAY prior_close is {wday['prior_close']}, not the "
                        "2026-08-13 close of 206.45")

    for symbol, expected in EXPECTED_GAPS.items():
        actual = by_symbol[symbol]["gap_pct"]
        if actual is None or abs(actual - expected) > 0.02:
            failures.append(f"{symbol} reprices to {actual}, expected about {expected}")

    # Every published gap must be a different number from the selection gap it
    # replaced. That is the whole point: the selection gap was yesterday's.
    for candidate in candidates:
        stale = candidate["selection_gap_pct"]
        fresh = candidate["gap_pct"]
        if fresh is None:
            failures.append(f"{candidate['symbol']} has no repriced gap")
            continue
        if abs(fresh) >= abs(stale):
            failures.append(
                f"{candidate['symbol']} repriced to {fresh}, not smaller than the "
                f"stale selection gap {stale}"
            )
    print("  claim 1 gaps, repriced against the 2026-08-13 close:")
    for candidate in candidates:
        print(f"      {candidate['symbol']:<9} was {candidate['selection_gap_pct']:+7.2f}%  "
              f"now {candidate['gap_pct']:+6.2f}%  price {candidate['price']} "
              f"at {candidate['price_time']}")


def claim_three(failures: list[str]) -> None:
    packet, bars = _load()
    candidates = _rebuild(packet, bars)
    # Eight of the twelve keep their bars; four are blinded to stand for names
    # the collector never subscribed to.
    covered = [c["symbol"] for c in candidates][:8]
    thin_bars = {s: b for s, b in bars.items() if s in covered}
    candidates = _rebuild(packet, thin_bars)

    kept, dropped = scan.drop_uncovered(candidates, scan.Packet())
    if len(kept) != 8:
        failures.append(f"{len(kept)} candidates kept, expected 8")
    if len(dropped) != 4:
        failures.append(f"{len(dropped)} candidates dropped, expected 4")
    if any(row.get("reason") in (None, "") for row in dropped):
        failures.append("a dropped candidate carries no reason")
    for candidate in kept:
        if candidate.get("price_source") != "collector":
            failures.append(f"{candidate['symbol']} kept with price_source "
                            f"{candidate.get('price_source')!r}")

    payload = {
        "session_date": "2026-08-14",
        "run_time_et": "08:45",
        "candidates": kept,
        "dropped_no_coverage": dropped,
    }
    original_db = config.DB_PATH
    config.DB_PATH = RUN_DIR / "test_repricing.db"
    config.DB_PATH.unlink(missing_ok=True)
    try:
        written = scan.write_picks(payload, force_test=True)
        with store.session() as connection:
            rows = connection.execute(
                "SELECT ticker, gap_pct FROM picks WHERE date='2026-08-14'"
            ).fetchall()
    finally:
        config.DB_PATH.unlink(missing_ok=True)
        config.DB_PATH = original_db

    if written != 8 or len(rows) != 8:
        failures.append(f"{written} picks written and {len(rows)} rows in the table, "
                        "expected 8 of each")
    if any(row["gap_pct"] is None for row in rows):
        failures.append("a picks row was written with no gap")
    print(f"  claim 3 kept {len(kept)}, dropped {len(dropped)}, "
          f"picks rows {len(rows)}, every kept price from the collector")


def claim_four(failures: list[str]) -> None:
    floor = baseline.MIN_BASELINE_VOLUME
    packet, bars = _load()
    candidates = _rebuild(packet, bars)
    by_symbol = {c["symbol"]: c for c in candidates}

    for symbol in ("ARX.US", "MH.US"):
        candidate = by_symbol[symbol]
        row = {
            "median_volume": (packet_row := next(
                c for c in packet["candidates"] if c["symbol"] == symbol
            ))["baseline"]["median_volume"],
            "sessions_used": packet_row["baseline"]["sessions_used"],
        }
        usable, why_not = baseline.usable_for_rvol(row)
        if usable:
            failures.append(f"{symbol} baseline median {row['median_volume']} "
                            f"passed the {floor} floor")
            continue

        candidate.update({
            "pm_rvol": None, "pm_rvol_reason": why_not,
            "catalyst_class": "earnings", "catalyst_why": "test fixture",
            "quote": {"marketCap": 3e9, "twoHundredDayAveragePrice": 1.0},
        })
        scan.score_candidate(candidate)
        if candidate["score"] is not None:
            failures.append(f"{symbol} still scores {candidate['score']} with a null RVOL")
        if candidate["score_partial"] is None:
            failures.append(f"{symbol} has no score_partial beside its null score")
        # premarket_volume, not premarket_rvol. Since 2026-08-16 the slot is
        # filled by whichever volume measure was available and is NAMED for
        # it, so the unavailable name is the neutral one that means the slot
        # was never filled at all. These two fixtures carry no sharesFloat, so
        # neither measure is available and the slot is genuinely empty.
        if "premarket_volume" not in (candidate["score_unavailable"] or []):
            failures.append(f"{symbol} does not list premarket_volume as unavailable, "
                            f"it lists {candidate['score_unavailable']}")
        if candidate.get("volume_measure_used") is not None:
            failures.append(f"{symbol} claims to have scored on "
                            f"{candidate['volume_measure_used']} with no measure available")
        if candidate["conviction"] is not None:
            failures.append(f"{symbol} has conviction {candidate['conviction']}, "
                            "expected null")
        volume_component = next(
            (c for c in candidate["score_components"]
             if c["component"] == "premarket_volume"), None
        )
        if volume_component is None:
            failures.append(f"{symbol} has no premarket_volume component at all")
        elif volume_component["points"] is not None:
            failures.append(f"{symbol} scored {volume_component['points']} on the volume "
                            "component instead of nothing")
        print(f"  claim 4 {symbol:<8} median "
              f"{row['median_volume']:>8,.1f} < {floor:,.0f} floor, pm_rvol null, "
              f"score null, partial {candidate['score_partial']}, "
              f"unavailable {candidate['score_unavailable']}")


def claim_six(failures: list[str]) -> None:
    build = config.build_identifier()
    if "commit" not in build or not build.get("commit"):
        failures.append(f"build identifier has no commit: {build}")
    if "dirty" not in build:
        failures.append(f"build identifier has no dirty flag: {build}")
    if not isinstance(build.get("dirty"), bool):
        failures.append(f"dirty is {build.get('dirty')!r}, expected a boolean")
    print(f"  claim 6 build {build.get('commit')} dirty={build.get('dirty')}")


def claim_seven(failures: list[str]) -> None:
    """A subscribed silent symbol and a never subscribed one are not the same row.

    Monday is the first morning at fifty subscriptions and the socket has only
    ever been load tested at thirty eight, so the packet has to be able to say
    which of the fifty produced nothing. It can only say that if it knows what
    was asked for, which is why the collector writes its subscription list at
    subscribe time rather than leaving it to be inferred from the bars.
    """
    _packet, bars = _load()
    served = [symbol for symbol, rows in bars.items() if rows][:3]
    if len(served) < 3:
        failures.append("the frozen snapshot has fewer than three symbols with bars")
        return

    silent = "SILENT.US"
    never = served[-1]
    requested = served[:-1] + [silent]

    day = "2026-08-14"
    path = collect_premarket.subscriptions_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "subscribed_at": "2026-08-14T07:20:00-04:00",
        "requested_count": len(requested),
        "socket_cap": 50,
        "symbols": sorted(requested),
        "dropped_to_fit_cap": [],
    }), encoding="utf-8")

    coverage = scan.collector_coverage(bars, day)

    if coverage["requested"] != len(requested):
        failures.append(f"coverage reported {coverage['requested']} requested, "
                        f"expected {len(requested)}")
    if silent not in coverage["silent_symbols"]:
        failures.append(f"{silent} was subscribed and produced no bars but is not "
                        f"named as silent: {coverage['silent_symbols']}")
    if never in coverage["silent_symbols"]:
        failures.append(f"{never} was never subscribed but is reported as silent, "
                        "which is the distinction this claim exists to hold")
    if never not in coverage["unsubscribed_with_bars"]:
        failures.append(f"{never} produced bars without being subscribed and is not "
                        "reported as such")
    if not coverage["peak_trades_per_minute"]:
        failures.append("no peak trade rate was measured from bars that carry "
                        "a trade count per minute")
    if coverage["late_trades"] is not None or not coverage["late_trades_reason"]:
        failures.append("the late trade count must be null with its reason recorded "
                        "at scan time, not filled with a stale number")

    # And with no subscription list at all, coverage must say so rather than
    # silently reporting every absent symbol as never subscribed.
    path.unlink()
    blind = scan.collector_coverage(bars, day)
    if blind["silent"] is not None or not blind.get("reason"):
        failures.append("with no subscription list, coverage claimed to know which "
                        f"symbols were silent: {blind}")

    print(f"  claim 7 coverage names {silent} silent, keeps {never} out of that list, "
          f"peak {coverage['peak_trades_per_minute']} trades/min")


def claim_eight(failures: list[str]) -> None:
    """A price inside the premarket window can still be too old to publish.

    The vintage gate asks whether a price is from today's premarket session,
    which a 07:22 print satisfies perfectly while being 83 minutes stale at
    08:45. That is exactly what a collector killed at 08:10 leaves behind.
    """
    import datetime as dtm

    limit = criteria.load().number("price_age", "max_price_age_seconds")
    scan_clock = ettime.at(dt_date(2026, 8, 14), 8, 45)

    fresh_at = ettime.stamp(scan_clock - dtm.timedelta(seconds=60))
    stale_at = ettime.stamp(ettime.at(dt_date(2026, 8, 14), 7, 22))

    candidates = [
        {"symbol": "FRESH.US", "price": 10.0, "price_time": fresh_at,
         "pool_tier": 1, "pool_source": ["earnings_before_open"]},
        {"symbol": "STALE.US", "price": 20.0, "price_time": stale_at,
         "pool_tier": 2, "pool_source": ["overnight_news"]},
    ]
    for candidate in candidates:
        candidate["price_age_seconds"] = scan._price_age_seconds(
            candidate["price_time"], scan_clock)

    if candidates[0]["price_age_seconds"] is None or candidates[1]["price_age_seconds"] is None:
        failures.append("price_age_seconds was not recorded for both candidates")
        return
    if candidates[1]["price_age_seconds"] <= limit:
        failures.append(f"the 07:22 print measured {candidates[1]['price_age_seconds']}s, "
                        f"which does not exceed the {limit}s limit; the fixture is wrong")

    kept, dropped = scan.drop_stale_prices(candidates, scan.Packet())
    if [c["symbol"] for c in kept] != ["FRESH.US"]:
        failures.append(f"kept {[c['symbol'] for c in kept]}, expected the 08:44 print only")
    if [d["symbol"] for d in dropped] != ["STALE.US"]:
        failures.append(f"dropped {[d['symbol'] for d in dropped]}, expected the 07:22 print")
    elif "vintage" not in dropped[0]["reason"]:
        failures.append("the stale reason does not explain why vintage passes it")

    # And the observed window, from the real frozen snapshot.
    _packet, bars = _load()
    window = scan.observed_collector_window(bars, scan_clock)
    for key in ("first_bar_et", "last_bar_et", "minutes_since_last_bar",
                "scheduled_start_et", "scheduled_stop_et"):
        if window.get(key) is None:
            failures.append(f"the observed window has no {key}")
    print(f"  claim 8 kept the 08:44 print, dropped the 07:22 one at "
          f"{candidates[1]['price_age_seconds']:,.0f}s; observed window "
          f"{str(window['first_bar_et'])[11:16]} to {str(window['last_bar_et'])[11:16]}, "
          f"{window['minutes_since_last_bar']:.0f}m of silence at the scan clock")


def claim_nine(failures: list[str]) -> None:
    """A name with no baseline is scored by float rotation, and says so.

    This is the clause the float rotation work was for. Before 2026-08-16 a
    first appearance name had a null pm_rvol, which made one score component
    unavailable, which made the whole score null. The name arrived unscored on
    the morning it was most interesting. Float rotation needs no history, so it
    fills the same slot and the name gets a number.

    Two properties are checked, and the second matters as much as the first. It
    is not enough that the name is scored: the breakdown has to name float
    rotation as the thing that scored it, or a reader cannot tell a rescued
    name from an ordinary one and the two populations can never be calibrated
    apart.

    The guards are tested here too, against the real reason each exists. A
    float above shares outstanding is impossible and a float far below it is a
    vendor artifact; both must refuse to divide rather than produce a number.
    """
    def newcomer(**overrides) -> dict:
        base = {
            "symbol": "NEWCO.US", "collector_covered": True, "pm_volume": 250_000.0,
            "quote": {"sharesFloat": 20_000_000.0, "sharesOutstanding": 25_000_000.0,
                      "marketCap": 3e9},
            "pm_rvol": None,
            "pm_rvol_reason": "no cached baseline for this ticker and cutoff",
            "gap_pct": 9.4, "price": 12.0, "prior_high": 11.0, "pm_vwap": 11.5,
            "catalyst_class": "earnings", "catalyst_why": "test fixture",
        }
        base.update(overrides)
        return base

    packet = scan.Packet()
    candidate = newcomer()
    scan.attach_float_rotation([candidate], packet)
    scan.score_candidate(candidate)

    expected = 250_000.0 / 20_000_000.0
    if candidate["pm_float_rotation"] != round(expected, 8):
        failures.append(f"float rotation is {candidate['pm_float_rotation']}, "
                        f"expected {round(expected, 8)}")
    if candidate["score"] is None:
        failures.append("a first appearance name with no baseline is still unscored: "
                        f"partial {candidate['score_partial']}, "
                        f"unavailable {candidate['score_unavailable']}")
    if candidate.get("conviction") is None:
        failures.append("the rescued name has a null conviction bucket")
    if candidate.get("volume_measure_used") != "premarket_float_rotation":
        failures.append(f"volume_measure_used is {candidate.get('volume_measure_used')!r}, "
                        "expected premarket_float_rotation")
    component = next(
        (c for c in candidate["score_components"]
         if c["component"] == "premarket_float_rotation"), None)
    if component is None:
        failures.append("the breakdown does not name premarket_float_rotation as a "
                        "component: "
                        f"{[c['component'] for c in candidate['score_components']]}")
    elif "pm_rvol is null" not in component["why"]:
        failures.append("the float rotation component does not say it stood in for a "
                        f"null pm_rvol: {component['why']}")
    if not (candidate["pm_float_rotation_basis"] or {}).get("is_lower_bound"):
        failures.append("float rotation is not flagged as a lower bound, but the "
                        "collector starts after the premarket does")

    # RVOL wins the slot when both are available, so the better measure is not
    # displaced by the fallback merely because the fallback is newer.
    both = newcomer(pm_rvol=4.0, pm_rvol_reason=None)
    scan.attach_float_rotation([both], scan.Packet())
    scan.score_candidate(both)
    if both.get("volume_measure_used") != "premarket_rvol":
        failures.append(f"with both measures available the slot used "
                        f"{both.get('volume_measure_used')}, expected premarket_rvol")

    # The two guards, each against the class of bad datum it was written for.
    impossible = newcomer(quote={"sharesFloat": 30_000_000.0,
                                 "sharesOutstanding": 25_000_000.0, "marketCap": 3e9})
    artifact = newcomer(quote={"sharesFloat": 51_810.0,
                               "sharesOutstanding": 392_075_056.0, "marketCap": 3e9})
    for label, subject in (("float above outstanding", impossible),
                           ("float implausibly small", artifact)):
        scan.attach_float_rotation([subject], scan.Packet())
        if subject["pm_float_rotation"] is not None:
            failures.append(f"{label}: divided anyway and got "
                            f"{subject['pm_float_rotation']}")
        if not subject["pm_float_rotation_reason"]:
            failures.append(f"{label}: refused to divide but recorded no reason")

    # And with neither measure, the score is still null. Float rotation must
    # not have quietly become a way for an unmeasured name to score zero.
    neither = newcomer(quote={"marketCap": 3e9})
    scan.attach_float_rotation([neither], scan.Packet())
    scan.score_candidate(neither)
    if neither["score"] is not None:
        failures.append(f"a name with neither volume measure scored "
                        f"{neither['score']}, expected null")

    print(f"  claim 9 no baseline: rotation {candidate['pm_float_rotation']:.6f}, "
          f"score {candidate['score']}, conviction {candidate['conviction']}, "
          f"scored by {candidate['volume_measure_used']}; both available uses "
          f"{both['volume_measure_used']}; both guards refused; neither stays null")


def main() -> int:
    if not PACKET_PATH.is_file() or not SNAPSHOT_PATH.is_file():
        print(f"SKIP  the 2026-08-14 artifacts are not on this machine "
              f"({PACKET_PATH} / {SNAPSHOT_PATH})")
        return 0

    failures: list[str] = []
    claim_one(failures)
    claim_three(failures)
    claim_four(failures)
    claim_six(failures)
    claim_seven(failures)
    claim_eight(failures)
    claim_nine(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print("PASS  repricing from the collector, dropping the uncovered, flooring the "
          "RVOL denominator, naming the build, telling a silent subscription "
          "from an absent one and scoring a name with no baseline all hold on the "
          "2026-08-14 packet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
