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

Four details the numbers depend on:

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

The float denominator is screened here exactly as morning/scan screens it, by
the same CRITERIA [Float rotation] floors read from the same file. Until
2026-08-17 this script carried a private copy of one of those checks, the
impossible float against shares outstanding, with the ratio written into the
Python as 1.01, the other two floors missing entirely, and no refusal at all for
the corrupt records the live path will not divide by. That is worse than it
sounds for a script whose whole output is a set of band edges: the bands were
being fitted to a population the live path does not score, so a name the scan
refuses to divide by was still voting on where the edges fall. The population
it measures now is the one the scan actually scores, which is the point.

The bands were then re-derived against that corrected screen, on 2026-08-17,
by an actual re-run of this script, and THE EDGES DID NOT MOVE: 0.0004 and
0.0002 both times. The screen fix cannot move them, and that is provable rather
than merely observed. Across the whole 1,870 name float cache the corrected
screen changes exactly one verdict, YPF, and YPF reaches the top
[Scan] candidate_count by gap on none of the 61 cached sessions, which is the
only population these edges are fitted to.

The counts and payout shares around the edges DO differ from the ones recorded
on 2026-08-16, and not because of this fix. data/universe.json was rebuilt
between the two runs, so the addressable population differs on 29 of the 61
sessions before the float screen is consulted at all. Anything re-run here will
therefore reproduce the EDGES and not the surrounding percentages. See
DECISIONS.md 2026-08-17 sixth for both sets and the attribution.

[corrected 2026-08-20: the sentence directly above is no longer a safe thing to
expect, and it was written before the reason was known. Both fits above were
read off a `rescued` population that was 36 percent this script's own cold
start, because `history` begins empty and nothing can carry an RVOL until it
has warmed up, so every addressable name landed in `rescued` for the first
[Baseline] min_sessions_for_rvol sessions. run() now walks those sessions
without tallying them, and on that corrected population the edges DO move:
0.0004 and 0.0002 become 0.00033 and 0.00014. The two paragraphs above stay as
written because their own claim is still true. The screen fix did not move the
edges. The warm up did.

Two further things changed with that fit. round_down answers two significant
figures rather than one, because at 0.00014266 a single figure costs 30 percent
and three points of payout accuracy. And the payload now carries
`rescued_rotation_values`, the rows behind the quantiles, so the next re-fit is
arithmetic on a file rather than another 463 requests: their absence is exactly
why this correction needed a vendor run to answer a question about numbers that
had already been measured twice.]

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


def _as_float(value: Any) -> float | None:
    if value is None or value == "" or value == "NA":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


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


# Lifted out of run() on 2026-08-31 so research/sweep_baseline_floor.py
# can be held to them by a claim. That module keeps its own copies
# rather than importing this one, because `import probe_alpaca` above
# is module scope and the sweep's whole argument is that re-fitting at
# a different floor costs no vendor call. A copy that can drift needs
# something watching it, and at module scope there is something that
# can: claim_the_floor_sweep_fits_edges_the_way_the_study_does.
def round_down(value: float) -> float:
    """To two significant figures, so a band edge is a number a human can
    hold, and downward so the rounding never makes a band stricter than
    the share it was matched to.

    It was ONE significant figure until 2026-08-20, and that is lossy in
    proportion to where the value sits inside its decade. At 0.00033763 a
    single figure costs 2 percent; at 0.00014266 it costs 30 percent,
    because the value sits at the start of its decade and the next figure
    down is a third of it. The rounding is not free either way: the edges
    exist to make the rotation bands pay what the RVOL bands pay, and at
    one figure the re-derived pair missed that target by 4.94 points
    against 1.77 at two. Rounding a threshold is allowed to cost a little
    readability. It is not allowed to cost more accuracy than the
    re-derivation it is rounding was performed to gain.
    """
    if value <= 0:
        return 0.0
    import math
    power = math.floor(math.log10(value)) - 1
    # round() BEFORE the floor as well as after, and both for the same
    # reason. 0.0006 scaled by 1e5 is 59.999999999999993, so a bare floor
    # answers 0.00059: a rounding rule that exists to make an edge readable
    # would have moved it by a sixtieth. The pre-round is to nine places,
    # far finer than any edge and far coarser than the noise. The post
    # round is the original one, because 6 * 1e-4 in binary floating point
    # is 0.0006000000000000001 and a band edge written into CRITERIA with
    # a tail like that is unreadable.
    scaled = math.floor(round(value / (10 ** power), 9))
    return round(scaled * (10 ** power), -power + 1)

def edge_at(values: list[float], share: float) -> float:
    """The value that this share of the population exceeds."""
    ordered = sorted(values, reverse=True)
    index = min(max(int(round(share * len(ordered))) - 1, 0), len(ordered) - 1)
    return ordered[index]


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


def warmup_over(rolled: int, min_sessions: int) -> bool:
    """Whether enough sessions are in `history` for ANY name to carry an RVOL.

    A module level function rather than a comparison written inline, so that
    the boundary this whole correction turns on is something a claim can call.
    `rolled` is sessions actually folded into the rolling history, not the loop
    index: an incomplete vendor sweep continues without rolling, and gating on
    the index would let the first short session shift the boundary by one.
    """
    return rolled >= min_sessions


def run(sessions: int | None = None, write: bool = True) -> dict[str, Any]:
    payload = json.loads((config.DATA_DIR / "universe.json").read_text(encoding="utf-8"))
    universe_rows = {str(r.get("symbol", "")).upper(): r for r in payload["symbols"]}
    universe_symbols = set(universe_rows)
    gap_rule = _CRIT.rule("discovery", "gap_pct")
    candidate_count = _CRIT.integer("scan", "candidate_count")
    lookback = _CRIT.integer("baseline", "lookback_sessions")
    min_sessions = _CRIT.integer("baseline", "min_sessions_for_rvol")
    volume_floor = _CRIT.number("baseline", "min_baseline_premarket_volume")
    # The same three floors morning/scan.attach_float_rotation divides by, read
    # from CRITERIA rather than restated here, so this script cannot drift away
    # from the rule it is calibrating.
    min_float = _CRIT.number("float_rotation", "min_shares_float")
    min_ratio = _CRIT.number("float_rotation", "min_float_to_shares_outstanding")
    max_ratio = _CRIT.number("float_rotation", "max_float_to_shares_outstanding")

    cache = float_cache.load_cache()
    floats = cache["symbols"]
    # The other half of the cache file, and the reason it is written there at
    # all: the names the sweep asked for and never got an answer about, with the
    # reason each one carries. Absence from "symbols" is not self explaining,
    # and this is what separates a sweep that was starved from a cache that
    # simply predates the name.
    never_answered = cache["unanswered"]
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
    # EVERY SCORED ROW, kept so a re-fit at a DIFFERENT denominator floor is
    # arithmetic on this file rather than another 462 vendor requests. The
    # 2026-08-20 correction already learned this once: both payloads on disk
    # carried quantiles, and a quantile of a contaminated set does not yield
    # the quantile of the clean one, so the whole study had to be re-run to
    # answer a question about numbers already measured twice.
    #
    # rescued_rotation_values fixed that for ONE question, whether the warm up
    # rows belonged. It cannot answer the floor question, because who is
    # rescued depends on the floor and the rotations alone do not say which
    # side of any floor a row sat on. Four fields do: the baseline median that
    # decides it, the volume the ratio is built from, the rotation, and whether
    # the row is in the top by gap slice the shipped edges are fitted on.
    #
    # median is null ONLY where the row could never carry an RVOL at any floor,
    # which is fewer than [Baseline] min_sessions_for_rvol sessions of history.
    # A row with a median below the current floor keeps its median here, which
    # is the whole point: at a higher floor it moves from overlap to rescued
    # and this file can say so.
    sweep_rows: list[list[Any]] = []
    scored_by_rvol = scored_by_rotation = scored_by_either = scored_by_neither = 0
    rescued = 0
    rescue_examples: list[dict[str, Any]] = []
    no_volume = 0
    # The reasons a name has no rotation, counted apart because they are
    # different facts and only one of them is about the market. They used to
    # share one no_float counter, which folded a cache that was never answered
    # for into the vendor's float coverage: a starved cache is re-fetched, thin
    # coverage is a property of the data the bands have to be set around, and a
    # float the CRITERIA floors refuse is a name the live path will not score
    # either. Reading one number for all of them, in the module that sets the
    # bands, destroyed exactly the distinction float_cache goes to trouble to
    # record. The first two split absence again by what the cache says about it.
    # A name the sweep asked about and got nothing back for is a starved sweep
    # to re-run. A name the file says nothing about at all is either newer than
    # the last sweep or older than the sweep's habit of recording its silences,
    # and either way the answer is the same: run float_cache before reading much
    # into a thin rotation population.
    cache_asked_and_got_nothing = 0
    cache_absent_no_reason = 0
    cache_row_carried_no_float = 0
    # The refusals split by which CRITERIA floor caught the float, so the float
    # floor note in CRITERIA [Float rotation] can be re-derived from this output
    # instead of from a one-off measurement nobody can repeat.
    #
    # TWO NUMBERS PER DOOR, AND THEY ANSWER DIFFERENT QUESTIONS. The counters
    # below count OCCURRENCES: this loop runs once per (session, symbol) pair,
    # so a name refused on every session it was addressable is counted once per
    # session. The sets count NAMES. The CRITERIA note counts names, "exactly
    # one name sat below one percent of its own shares outstanding (YPF at 0.013
    # percent)", and a cached float row is constant across sessions, so reading
    # the occurrence counter as a name count reports that one name as however
    # many sessions it appeared in, dozens over the 61 this study normally runs.
    # Both are reported so neither has to be inferred from the other.
    rejected_negative_outstanding = 0
    rejected_float_above_outstanding = 0
    rejected_float_tiny_vs_outstanding = 0
    rejected_float_below_absolute_floor = 0
    names_negative_outstanding: set[str] = set()
    names_float_above_outstanding: set[str] = set()
    names_float_tiny_vs_outstanding: set[str] = set()
    names_float_below_absolute_floor: set[str] = set()
    per_session: list[dict[str, Any]] = []
    # Sessions folded into `history` so far, and the ones walked for history
    # alone. See the warm up note below for why the second number exists.
    rolled = 0
    warmup_sessions = 0

    def roll_forward(volumes: dict[str, float]) -> None:
        """Fold one session's baseline window volumes into the rolling history.

        Extracted because the warm up branch has to roll a session it does not
        count, and a second copy of this loop is exactly how the two would
        drift apart.
        """
        for code in all_codes:
            history.setdefault(code, []).append(volumes.get(code, 0.0))

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
        # (gappers, census) since 2026-08-22; the cached bars carry no
        # adjusted_close, so the census reports every row unchecked.
        gappers, _census = pool_recall.actual_gappers(
            rows, prior_closes, universe_symbols, gap_rule)
        addressable = pool_recall.addressable_target(gappers, universe_rows)["addressable"]

        ranked = sorted(addressable.items(),
                        key=lambda kv: abs(kv[1].get("gap_at_open_pct") or 0), reverse=True)
        top_symbols = {s for s, _ in ranked[:candidate_count]}

        # THE WARM UP. `history` starts empty and is built by this loop, so
        # for the first min_sessions_for_rvol sessions `past` is shorter than
        # the floor for EVERY name and rvol is None for every name. A name with
        # a usable float therefore lands in `rescued`, the population the
        # CRITERIA [Float rotation] bands are fitted on, purely because this
        # script has not warmed up yet. In the live path those names carry a
        # real RVOL off the baseline cache and are never rescued at all.
        #
        # Measured on doc/research/float_rotation_study-2026-08-17-postfix.json,
        # the payload DECISIONS.md quotes: 894 of 2,464 rescued rows, 36.3
        # percent, came from the first ten sessions, and the rescue rate runs 84
        # to 93 percent across those ten and 7 to 22 percent from the eleventh
        # onward. That discontinuity is this loop, not the market.
        #
        # Gated on `rolled` rather than on the enumerate index, because an
        # incomplete sweep above `continue`s without rolling and the two counts
        # part company the first time the vendor is short a session.
        if not warmup_over(rolled, min_sessions):
            warmup_sessions += 1
            per_session.append({"date": today, "addressable": len(addressable),
                                "rescued_by_rotation": None, "counted": False,
                                "reason": "history shorter than "
                                          f"min_sessions_for_rvol ({min_sessions}), "
                                          "so no name here could carry an RVOL"})
            roll_forward(base_vol)
            rolled += 1
            continue

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
            # Kept apart from `rvol` so sweep_rows can tell a row that could
            # never carry a ratio from one this floor happens to refuse.
            usable_history = len(past) >= min_sessions
            median = statistics.median(past) if usable_history else None
            if usable_history and median > 0 and median >= volume_floor:
                rvol = volume / median

            # --- float rotation, screened by the same floors the live path uses
            #
            # `floats.get(symbol) or {}` used to stand here, and it flattened
            # the two absences this accounting exists to tell apart: a symbol
            # the float cache never got an answer for arrived as an empty row
            # and was counted as a symbol the vendor answered without a float,
            # in the one module that sets the scoring bands. The row is left as
            # None so the first branch below can ask which one it was.
            row = floats.get(symbol)
            share_float = _as_float((row or {}).get("sharesFloat"))
            outstanding = _as_float((row or {}).get("sharesOutstanding"))
            rotation = None
            # sharesOutstanding is a cross check only when it is a real share
            # count, so it is tested present AND strictly positive rather than
            # merely truthy. The `if outstanding and ...` that stood here, and
            # that morning/scan was corrected away from on 2026-08-17, skips the
            # ratio check on a reported zero because 0.0 is falsy, and a
            # fabricated float of a few thousand shares then divides premarket
            # volume into a very large rotation and votes on where the top band
            # edge falls, off a denominator nothing ever looked at. A zero falls
            # to the absolute floor here, which is where scan.py sends it and
            # where a float with no usable cross check belongs.
            #
            # A negative outstanding is refused outright instead of being sent
            # to that floor, which is what scan.py settled on the same day and
            # for a reason this script has to respect: a quote reporting a share
            # count no company can have has told us nothing trustworthy about
            # the name, the sharesFloat sitting beside it included. A name the
            # live path refuses must not be in the population the bands are
            # fitted on, or the bands are fitted partly on names that will never
            # be scored by them.
            #
            # A float that is itself zero or negative is not a share count
            # either, and falls in with the rows carrying none.
            outstanding_usable = outstanding is not None and outstanding > 0
            if row is None:
                if symbol in never_answered:
                    cache_asked_and_got_nothing += 1
                else:
                    cache_absent_no_reason += 1
            elif share_float is None or share_float <= 0:
                cache_row_carried_no_float += 1
            elif outstanding is not None and outstanding < 0:
                rejected_negative_outstanding += 1
                names_negative_outstanding.add(symbol)
            elif outstanding_usable and share_float > outstanding * max_ratio:
                rejected_float_above_outstanding += 1
                names_float_above_outstanding.add(symbol)
            elif outstanding_usable and share_float < outstanding * min_ratio:
                rejected_float_tiny_vs_outstanding += 1
                names_float_tiny_vs_outstanding.add(symbol)
            elif not outstanding_usable and share_float < min_float:
                rejected_float_below_absolute_floor += 1
                names_float_below_absolute_floor.add(symbol)
            else:
                rotation = volume / share_float

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
                sweep_rows.append([
                    round(median, 4) if usable_history else None,
                    round(volume, 4),
                    rotation,
                    1 if symbol in top_symbols else 0,
                ])
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
                            "rescued_by_rotation": session_scored, "counted": True})

        roll_forward(base_vol)
        rolled += 1
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

        # The ELIGIBILITY question, which is a different question from the
        # bands and had never been measured. CRITERIA [Day setup] requires
        # premarket_rvol > 1.5, and Rule.test(None) is false, so a name with no
        # usable baseline cannot be day_eligible however busy it is. DECISIONS
        # 2026-08-18 records AS.US as the dated instance: it cleared every
        # other line and its entire day_failed list was the null RVOL.
        #
        # Whether a rotation floor belongs in that screen is the owner's, and
        # it is a threshold, so it is measured here rather than decided. The
        # method is the one the bands already use: find the share of the paired
        # population the RVOL floor admits, and read the rotation value
        # admitting the same share of the rescued names. A floor set any other
        # way would make the screen mean something different depending on which
        # measure a name happened to carry, which is the exact failure the band
        # matching above exists to prevent.
        day_floor = _CRIT.rule("day_setup", "premarket_rvol")
        rvol_values = [p[0] for p in pair]
        day_share = (sum(1 for v in rvol_values if day_floor.test(v))
                     / len(rvol_values)) if rvol_values else 0.0
        day_exact = edge_at(resc, day_share) if (resc and day_share) else None
        day_edge = round_down(day_exact) if day_exact else None
        day_admits = (sum(1 for v in resc if v > day_edge) if day_edge else 0)

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
            # Not a recommendation. The number the owner's yes or no is about.
            "day_setup_eligibility": {
                "rvol_floor": day_floor.describe(),
                "share_of_paired_rvol_admitted": round(day_share, 4),
                "rotation_edge_admitting_the_same_share": day_edge,
                "rotation_edge_exact": round(day_exact, 8) if day_exact else None,
                "rescued_names_it_would_admit": day_admits,
                "of_rescued_names": len(resc),
            },
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
        # Sessions the distributions below were actually built from. NOT
        # len(per_session): that counts the warm up sessions this walks for
        # history and refuses to tally, and reporting them as measured is how
        # the cold start hid in plain sight for a fortnight.
        "sessions": sum(1 for row in per_session if row.get("counted")),
        "sessions_walked": len(per_session),
        "warmup_sessions_excluded": warmup_sessions,
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
            # Seven doors where there used to be one. no_float_in_cache is gone
            # rather than kept alongside them, because a reader who found both
            # would have to guess which absences the old key still counted.
            "float_cache_asked_and_got_nothing": cache_asked_and_got_nothing,
            "absent_from_float_cache_no_reason_recorded": cache_absent_no_reason,
            "cache_row_carried_no_float": cache_row_carried_no_float,
            "negative_shares_outstanding": rejected_negative_outstanding,
            "float_above_shares_outstanding": rejected_float_above_outstanding,
            "float_tiny_against_shares_outstanding": rejected_float_tiny_vs_outstanding,
            "float_below_absolute_floor": rejected_float_below_absolute_floor,
            "no_alpaca_volume": no_volume,
        },
        # The same four doors counted by NAME rather than by occurrence. This is
        # the shape the CRITERIA [Float rotation] float floor note is written in,
        # so it is the one to read when re-deriving that note.
        "distinct_names_refused": {
            "negative_shares_outstanding": len(names_negative_outstanding),
            "float_above_shares_outstanding": len(names_float_above_outstanding),
            "float_tiny_against_shares_outstanding": len(names_float_tiny_vs_outstanding),
            "float_below_absolute_floor": len(names_float_below_absolute_floor),
            "float_tiny_against_shares_outstanding_names":
                sorted(names_float_tiny_vs_outstanding),
            "float_below_absolute_floor_names": sorted(names_float_below_absolute_floor),
        },
        "rvol_band_payout": {"all_addressable": rvol_points_share(rvol_all),
                             "top_by_gap": rvol_points_share(rvol_top)},
        "rotation_share_above_edge": {"all_addressable": share_above(rot_all),
                                      "top_by_gap": share_above(rot_top)},
        # The rows behind the percentiles, for the slice the bands are
        # fitted on. Their absence had a measured cost: when the warm up
        # contamination was found on 2026-08-20, which way the edges would
        # move could not be computed from either payload on disk, because
        # both carried quantiles and a quantile of a contaminated set does
        # not yield the quantile of the clean one. The whole study had to
        # be re-run against the vendor to answer a question about numbers
        # already measured. With these and rvol_band_payout, which holds
        # the target share, a re-fit is arithmetic on a file.
        "rescued_rotation_values": {
            "all_addressable": sorted(rescued_rot_all),
            "top_by_gap": sorted(rescued_rot_top),
        },
        # [median or null, volume, rotation, in_top_by_gap]. See sweep_rows
        # where it is built for why these four and not the quantiles.
        "sweep_rows_schema": ["baseline_median_or_null_when_history_too_short",
                              "premarket_volume", "float_rotation",
                              "in_top_by_gap"],
        "sweep_rows": sweep_rows,
        "rescue_examples": rescue_examples,
        "per_session": per_session,
        "alpaca_requests": probe.request_count,
    }

    print(f"\nsessions measured {result['sessions']} of "
          f"{result['sessions_walked']} walked, "
          f"{result['warmup_sessions_excluded']} excluded as warm up")
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

    # Spelled out rather than left to the coverage line, because these are the
    # numbers that say whether a thin rotation population is the vendor's fault
    # or the cache sweep's, and those call for opposite responses: re-run
    # float_cache, or accept the coverage and set the bands around it.
    print("\n  WHY A NAME HAS NO ROTATION")
    print(f"    the cache sweep asked and got nothing back : {cache_asked_and_got_nothing}")
    print(f"    absent, and the cache records no reason    : {cache_absent_no_reason}")
    print(f"    the cached row carried no sharesFloat      : {cache_row_carried_no_float}")
    print(f"    shares outstanding reported negative       : "
          f"{rejected_negative_outstanding}")
    print(f"    float above shares outstanding             : "
          f"{rejected_float_above_outstanding}")
    print(f"    float under {min_ratio * 100:g} percent of outstanding       : "
          f"{rejected_float_tiny_vs_outstanding}")
    print(f"    float under the {min_float:,.0f} share floor, unchecked : "
          f"{rejected_float_below_absolute_floor}")
    print(f"    no Alpaca volume for the window            : {no_volume}")
    # Occurrences above, names here. The CRITERIA note counts names, so this is
    # the block to read when re-deriving it; see the comment on the counters.
    print("    the four floors again, counted by NAME not by session:")
    print(f"      shares outstanding negative              : "
          f"{len(names_negative_outstanding)}")
    print(f"      float above shares outstanding           : "
          f"{len(names_float_above_outstanding)}")
    print(f"      float under {min_ratio * 100:g} percent of outstanding     : "
          f"{len(names_float_tiny_vs_outstanding)} "
          f"{sorted(names_float_tiny_vs_outstanding)}")
    print(f"      float under the {min_float:,.0f} share floor      : "
          f"{len(names_float_below_absolute_floor)}")

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
