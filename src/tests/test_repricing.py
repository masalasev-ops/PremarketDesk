"""Regression tests for the 2026-08-14 stale vintage defect and its guards.

Run directly: `python -m tests.test_repricing` with PYTHONPATH set to src/,
exit 0 on pass. Makes no network
calls. The evidence is the artifacts the failing morning left behind:
runs/2026-08-14/packet.json and the collector snapshot beside it.

Nine claims, numbered after the clause each was written for rather than
counted off, which is why the list reaches eleven and carries no 2 and no 5:
  1. Repricing from the collector reproduces this morning's real gaps in place
     of yesterday's session moves.
  3. A candidate the collector never subscribed to is dropped, not priced.
  4. A baseline median below the CRITERIA floor produces a null pm_rvol, an
     unavailable RVOL component and a null total, through the existing
     score_partial machinery rather than a second path.
  6. The packet can name the build that wrote it.
  7. A subscribed symbol that stayed silent and one that was never subscribed
     are told apart, from the collector's own subscription list.
  8. A price inside today's premarket window can still be too old to publish,
     which the vintage gate alone does not catch.
  9. A name with no baseline is scored by float rotation and the breakdown
     says which measure scored it.
  10. A sharesOutstanding that is not a share count never passes as a cross
     check: a zero or an absent one falls to the absolute share floor, a
     negative one is refused outright, each with a reason and a gap.
  11. A trade stamped outside the run's window is written to the bar file
     tagged as a replay rather than folded into the morning's minutes, proven
     against the real 2026-08-18 file rather than a fixture, and carrying its
     own SKIP rather than riding the 2026-08-14 gate.
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


def claim_ten(failures: list[str]) -> None:
    """A sharesOutstanding that is not a share count is not a cross check.

    Claim 9 proves the two ratio guards refuse the floats they were written
    for, and both of those arrive alongside a believable sharesOutstanding.
    This claim is about the quote where the cross check is itself the broken
    field, and the three ways it can break are three findings rather than one.

    A sharesOutstanding of exactly 0.0 is falsy and is also not None. Until
    2026-08-17 the two ratio guards tested it for truthiness and the absolute
    share floor tested it against None, so the same zero slipped past all
    three. The one quote deserving the most suspicion was the only one facing
    no guard at all, and rotation is premarket volume over the float, so the
    fabricated tiny float it waved through did not shade the number, it
    multiplied it: the name arrived in the top rotation band on a denominator
    nothing had checked. A zero now meets the absolute floor, which is the
    standing fallback for a missing cross check, so a tiny float beside one is
    refused and an ordinary float beside one still computes. Both directions
    are asserted, because a guard that refuses everything is not a fix.

    A negative sharesOutstanding is a different finding and gets a different
    answer: refused outright, whatever the float beside it looks like, because
    a negative share count is not a cross check the vendor left out, it is a
    record reporting something no company can have. That refusal is old
    behaviour restored rather than new behaviour invented. The max ratio guard
    used to catch negatives by arithmetic accident, since a positive float
    always exceeds a negative product, and the 2026-08-17 rewrite of that
    condition dropped the accident along with the truthiness test it was
    rewriting: a 20,000,000 share float beside a sharesOutstanding of
    -25,000,000 then published a rotation of 0.0125, and carried the
    impossible share count into the packet beside it, where that same quote
    had always been refused. It is pinned here so it cannot be lost twice.

    Every refusal is checked for its gap as well as its reason, because a null
    nobody is told about is a name that leaves the morning without a human
    seeing why. What the basis publishes for shares_outstanding is asserted
    too: an unusable one is recorded as null with its state in the source line
    beside it, never as a bare 0.0, which a downstream reader would take for a
    company with no shares rather than for a field that was never usable.

    The floor is read from CRITERIA.md rather than written here, so this claim
    keeps testing the guard and not a number that has since moved.
    """
    floor = _CRIT.number("float_rotation", "min_shares_float")
    # A float two orders of magnitude under the floor, which is the shape of
    # the vendor artifact the floor exists for: 51,810 shares was the smallest
    # real float measured on 2026-08-16, and this sits well below that.
    fabricated = floor / 100
    ordinary_float = 20_000_000.0
    pm_volume = 250_000.0
    expected = round(pm_volume / ordinary_float, 8)

    def newcomer(**quote_fields) -> dict:
        quote = {"sharesFloat": ordinary_float, "sharesOutstanding": 25_000_000.0,
                 "marketCap": 3e9}
        quote.update(quote_fields)
        return {
            "symbol": "ZEROCO.US", "collector_covered": True, "pm_volume": pm_volume,
            "quote": quote,
            "pm_rvol": None,
            "pm_rvol_reason": "no cached baseline for this ticker and cutoff",
            "gap_pct": 9.4, "price": 12.0, "prior_high": 11.0, "pm_vwap": 11.5,
            "catalyst_class": "earnings", "catalyst_why": "test fixture",
        }

    # The defect itself, its absent neighbour, and the corrupt record that is
    # refused on sight. Each reason is checked for the phrase that tells a
    # reader which case it was, because a reason that does not distinguish them
    # sends whoever reads the packet to the wrong conversation with the vendor,
    # and each gap for the phrase that says the same thing in gaps_to_fill.
    #
    # The negative case carries the ordinary float on purpose. A tiny one would
    # pass whether the negative guard fired or the floor did, and it is exactly
    # the healthy looking float beside an impossible share count that the
    # 2026-08-17 rewrite started publishing.
    refusals = (
        ("zero", newcomer(sharesFloat=fabricated, sharesOutstanding=0.0),
         "zero", "share floor with shares outstanding reported as zero"),
        ("absent", newcomer(sharesFloat=fabricated, sharesOutstanding=None),
         "no sharesOutstanding", "share floor with no shares outstanding"),
        ("negative", newcomer(sharesOutstanding=-25_000_000.0),
         "negative", "negative shares outstanding"),
    )
    for label, subject, phrase, gap_phrase in refusals:
        packet = scan.Packet()
        scan.attach_float_rotation([subject], packet)
        if subject["pm_float_rotation"] is not None:
            failures.append(
                f"sharesOutstanding {label}: the float was divided by anyway and "
                f"produced a rotation of {subject['pm_float_rotation']:,.4f}"
            )
        reason = subject["pm_float_rotation_reason"] or ""
        if not reason:
            failures.append(f"sharesOutstanding {label}: refused to divide but "
                            "recorded no reason, so the null is unexplained")
        elif phrase not in reason:
            failures.append(f"sharesOutstanding {label}: the reason does not say "
                            f"which case it was, it reads {reason!r}")
        if not any(gap_phrase in note for note in packet.gaps):
            failures.append(f"sharesOutstanding {label}: the name was nulled without "
                            f"a gap naming the case, gaps were {packet.gaps}")
        if subject["pm_float_rotation_basis"] is not None:
            failures.append(f"sharesOutstanding {label}: a basis was published for "
                            "a rotation that was never computed")

    # The working path, unchanged: the healthy newcomer still divides, and its
    # basis still carries the real share count it was checked against.
    healthy = newcomer()
    scan.attach_float_rotation([healthy], scan.Packet())
    if healthy["pm_float_rotation"] != expected:
        failures.append(f"the healthy name now computes "
                        f"{healthy['pm_float_rotation']}, expected {expected}")
    if healthy["pm_float_rotation_reason"] is not None:
        failures.append(f"the healthy name carries a refusal reason: "
                        f"{healthy['pm_float_rotation_reason']}")
    healthy_basis = healthy["pm_float_rotation_basis"] or {}
    if healthy_basis.get("shares_outstanding") != 25_000_000.0:
        failures.append("the healthy name's basis does not publish the "
                        "sharesOutstanding it was checked against, it carries "
                        f"{healthy_basis.get('shares_outstanding')!r}")

    # And a zero outstanding beside an ordinary float still computes, because
    # the floor stands in for the missing cross check rather than adding a
    # reason to refuse. Without this the fix would quietly null every name
    # whose vendor record happens to omit a usable outstanding.
    #
    # What its basis says about that zero is asserted here rather than left to
    # inspection, because it is a deliberate choice and not a side effect: the
    # count field is null, which is what this project records for evidence it
    # does not have, and the source line names the state so a reader can still
    # tell an absent sharesOutstanding from a zero one.
    ordinary = newcomer(sharesOutstanding=0.0)
    scan.attach_float_rotation([ordinary], scan.Packet())
    if ordinary["pm_float_rotation"] != expected:
        failures.append(f"a {ordinary_float:,.0f} share float with a zero "
                        f"outstanding was refused, computing "
                        f"{ordinary['pm_float_rotation']} instead of {expected}")
    ordinary_basis = ordinary["pm_float_rotation_basis"] or {}
    if ordinary_basis.get("shares_outstanding") is not None:
        failures.append("a zero sharesOutstanding was published in the basis as "
                        f"{ordinary_basis.get('shares_outstanding')!r}, which reads "
                        "as a share count rather than as a field that was unusable")
    if "zero" not in (ordinary_basis.get("shares_outstanding_source") or ""):
        failures.append("the basis does not say why shares_outstanding is null, so "
                        "a reader cannot tell the zero from an absent field: "
                        f"{ordinary_basis.get('shares_outstanding_source')!r}")

    print(f"  claim 10 a zero and an absent sharesOutstanding meet the "
          f"{floor:,.0f} share floor with a {fabricated:,.0f} share float and a "
          f"negative one is refused outright, each naming its case and raising "
          f"its gap; a zero beside a {ordinary_float:,.0f} share float still "
          f"rotates {ordinary['pm_float_rotation']:.6f} on a null share count")


def claim_eleven(failures: list[str]) -> None:
    """A trade stamped outside the run's window is refused, not folded.

    The subscription replays a last trade per symbol when it lands, and that
    trade carries its ORIGINAL timestamp. On 2026-08-18 that put three bars
    dated 2026-08-17 into the 2026-08-18 premarket file, one of them 15:59 the
    previous afternoon, and eleven more on 2026-08-17 stamped minutes before
    the collector had connected. Every one carried exactly one trade, which is
    the signature: one replayed message per symbol.

    The volume is trivial, 0.1 and 0.3 percent of the two sessions, and that is
    not what makes it a defect. pm_window_starts_late is derived from the first
    bar present, so a replayed 07:00 print makes a window the collector reached
    at 07:20 look covered from 07:00, and the flag that exists to warn a reader
    about exactly that says nothing.

    Proven against the real 2026-08-18 file rather than a fixture, because a
    fixture would only prove the comparison, not that the vendor does this.
    """
    import tempfile
    from collect.collect_premarket import BarBuilder

    day = "2026-08-18"
    source = config.PREMARKET_DIR / f"{day}.jsonl"
    if not source.is_file():
        print(f"  claim 11 SKIPPED, {source.name} is not on this machine")
        return

    open_at = ettime.at_hm(ettime.parse_date(day),
                           _CRIT.clock("collector", "start_time")).timestamp()
    close_at = ettime.at_hm(ettime.parse_date(day),
                            _CRIT.clock("collector", "stop_time")).timestamp()
    grace = _CRIT.number("collector", "late_trade_grace_s")

    with tempfile.TemporaryDirectory(prefix="pmd-window-") as tmp:
        guarded = BarBuilder(Path(tmp) / "guarded.jsonl", "ws",
                             window=(open_at, close_at + grace))
        unguarded = BarBuilder(Path(tmp) / "unguarded.jsonl", "ws")
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for builder in (guarded, unguarded):
                builder.add_trade(row["symbol"], row["c"], row.get("v") or 0,
                                  float(row["minute_epoch"]), False, None)

    if unguarded.out_of_window_trades:
        failures.append("a builder given no window refused something, so the "
                        "guard is not opt in and an ad hoc run could lose its tape")
    if not guarded.out_of_window_trades:
        failures.append(f"the {day} file is expected to carry replayed trades "
                        "outside the collection window and the guard found none")
        return
    stale = [row for row in guarded.out_of_window_examples
             if not row["at"].startswith(day)]
    if not stale:
        failures.append("no refused trade came from a previous session, which is "
                        f"the case that matters: {guarded.out_of_window_examples[:3]}")
    share = guarded.out_of_window_volume / max(1.0, unguarded.total_volume) * 100.0
    if share > 5.0:
        failures.append(f"the window guard refused {share:.1f}% of the session's "
                        "volume, which is far more than a replay and needs looking at "
                        "before it is trusted")
    print(f"  claim 11 the window guard refuses {guarded.out_of_window_trades} "
          f"replayed trade(s) on {day} ({guarded.out_of_window_volume:,.0f} shares, "
          f"{share:.2f}% of the session), {len(stale)} of them dated to an earlier "
          "session, and refuses nothing when no window is given")


def main() -> int:
    failures: list[str] = []

    # The gate used to cover the whole module, and three of these claims read
    # neither artifact. Verified by cloning the repository, where runs/ and
    # data/ are untracked: it printed the SKIP line and then
    # "tests.test_repricing ok" having asserted nothing at all. Nothing else in
    # src/tests covers attach_float_rotation or the sharesOutstanding guards,
    # so that whole surface was unguarded on every machine but this one.
    # test_vintage states the principle: a guard that only runs on the machine
    # where the bug was first found is not a guard.
    replayed = PACKET_PATH.is_file() and SNAPSHOT_PATH.is_file()
    if not replayed:
        print(f"SKIP  the 2026-08-14 artifacts are not on this machine "
              f"({PACKET_PATH} / {SNAPSHOT_PATH}), so the five claims that "
              "replay that morning are skipped. The rest ran.")

    if replayed:
        claim_one(failures)
        claim_three(failures)
        claim_four(failures)
    claim_six(failures)
    if replayed:
        claim_seven(failures)
        claim_eight(failures)
    claim_nine(failures)
    claim_ten(failures)
    # claim_eleven carries its own SKIP against its own file, so it decides for
    # itself rather than riding a gate about two other files.
    claim_eleven(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    if replayed:
        print("PASS  repricing from the collector, dropping the uncovered, flooring the "
              "RVOL denominator, naming the build, telling a silent subscription "
              "from an absent one, dropping a price too old to publish, scoring a name "
              "with no baseline and refusing a sharesOutstanding that is not a share "
              "count all hold on the 2026-08-14 packet")
    else:
        print("PASS  naming the build, scoring a name with no baseline and refusing "
              "a sharesOutstanding that is not a share count all hold; the five "
              "claims that replay 2026-08-14 were skipped for want of its artifacts")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
