"""What each candidate replacement for the capture rate would do, scored offline.

An instrument, not a pipeline step. Nothing downstream reads its output, and
this one PROPOSES NOTHING: it scores four candidates and prints what each costs.

    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.sweep_capture_rate
    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.sweep_capture_rate --json

IT READS ONE FILE AND NOTHING ELSE. No database, no vendor, no packet.
research/measure_capture_rate.py archives the raw rows, so every question
below is arithmetic on that payload and can be re-asked forever without
another run. BUILD_PLAN records the alternative: the float rotation study
archived percentiles rather than rows, the fit could then not be recomputed,
and a re-run cost real vendor requests. A quantile of one population does not
yield the quantile of another.

THE FOUR CANDIDATES, and one of them is a refusal.

  A  a single re-derived number, by the shipped estimator's own recipe. Not
     the volume weighted aggregate: CRITERIA's "Why 0.1172 rather than 0.0923"
     argues that the aggregate answers "what share of the total tape did the
     socket hear" while the screen asks "what share should be assumed for ONE
     symbol nothing has been measured for", and the estimator for the second
     is the median of the per symbol rates. Both are printed, because the
     second half of that argument was that the per symbol figure is also the
     SAFER of the two, and whether that still holds is a fact rather than a
     convention.

  B  per symbol, which this file REFUSES to fit and says why. The refusal is
     the finding: CRITERIA [Score watch] min_group_rows and min_group_sessions
     are the withholding rule, the sample unit is the SESSION, and a symbol
     seen on one morning is one observation whatever its row count says.

  C  banded by liquidity, keyed on the packet's avg_volume_20d, which is the
     only liquidity key the morning holds at 08:45. A per symbol share needs a
     history the record does not have; a per band share needs only the band.

  D  the distribution, reporting the quantile 0.1172 sits at and what a
     deliberately conservative HIGHER value costs in admitted names. Higher
     assumed capture means a lower corrected ratio means fewer names admitted,
     and the safe direction on a long only screen is to withhold.

TWO ARMS, ALWAYS, because a capture rate is a FALLBACK and not a divisor.
scan.attach_capture_estimate prefers the symbol's own measured share and
reaches CRITERIA only where that check carries none. So the arm that answers
"what does changing the one line do" is as_fallback, and the arm that answers
"what is this number worth as a rule" is to_every_row. Reporting only the
first understates the number's reach and only the second overstates it.

THE DAY SCREEN IS REPORTED AS TWO SETS, NEVER ONE. Cleared the volume floor,
and reached the day watchlist. Clearing one condition of five is not
membership, and scan.capture_correction_report already draws that distinction
in its own gap message after a report once named a symbol as put on the day
list by a correction that had only carried it over one floor.

THE OTHER FOUR CONDITIONS ARE NOT RECOMPUTED. A capture rate cannot move a
market cap, a price, a gap or a prior high, so this file reads the packet's own
day_failed_conditions and asks only whether premarket_rvol was the last thing
in the way. Re-implementing four screens in order to leave them unchanged is
how a research file starts quietly disagreeing with production.

BOTH DENOMINATORS ON EVERY COUNT, rows and sessions. Twelve names off one
morning share a tape and are one observation, which is why the withholding
rule below counts both and why every screen line prints both. [corrected
2026-09-01: candidate D's conservative ladder reported its two screen costs as
bare row counts and report() printed that table with a rows only column pair,
which was the one place in these two files that stated a screen cost without
its session denominator.]

AND THE RESIDUAL NO DIVISOR CLOSES is printed at the end of every run. The
capture rate corrects the FEED. The 07:20 start is a different shortfall with
a different fix, and no value of this key reaches it.
"""

from __future__ import annotations

import argparse
import json
import statistics
from typing import Any

from core import config
from core import criteria

_CRIT = criteria.load()

SHIPPED_RATE = _CRIT.number("collector", "premarket_capture_rate")
MIN_GROUP_ROWS = _CRIT.integer("score_watch", "min_group_rows")
MIN_GROUP_SESSIONS = _CRIT.integer("score_watch", "min_group_sessions")
RVOL_FLOOR = _CRIT.rule("day_setup", "premarket_rvol")

PATH_STEM = "capture_rate_study"

# Display boundaries, not thresholds. Nothing reads them and moving one changes
# only how the answer is shown, exactly as sweep_baseline_floor's DEFAULT_FLOORS
# and measure_baseline_floor's BUCKETS are boundaries.
DEFAULT_BANDS = 3
DEFAULT_QUANTILES = (0.5, 0.6, 0.75, 0.9)
REPORTED_QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)

# The assumption candidate C exists to test, quoted rather than paraphrased so
# that what is being contradicted is legible. night/true_volume.py's docstring,
# and the same claim in CRITERIA's capture rate note about the thin end.
ASSUMPTION = ("night/true_volume.py: \"THE ERROR IS NOT RANDOM, which is the "
              "part worth being angry about. Thin names capture least, so "
              "thin names are understated most, and thin names are exactly "
              "the population premarket float rotation exists to rescue.\"")


# ------------------------------------------------------------------ payload

def newest_payload() -> Any:
    """The most recent archived study, by filename rather than by mtime.

    The filename carries the session the study was taken on, whoever copied
    the file and whenever, which is the same argument CRITERIA's closes
    retention note makes for reading an age off a name and not off a stat.
    """
    directory = config.DOC_DIR / "research"
    found = sorted(directory.glob(f"{PATH_STEM}-*.json"))
    if not found:
        raise SystemExit(
            f"no {PATH_STEM}-*.json under {directory}. Run "
            "research.measure_capture_rate first: this script is arithmetic "
            "on the rows that run archives, and it reads nothing else.")
    return found[-1]


def load(path: Any) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "rows" not in payload:
        raise SystemExit(
            f"{path} carries no rows, so it predates the field this script "
            "reads. Re-run research.measure_capture_rate.")
    return payload


# ---------------------------------------------------------------- withholding

def withholding(rows: int, sessions: int, unit: str = "row") -> str | None:
    """None when a group may be read, otherwise how far short it is.

    Both denominators, every time. A group can carry plenty of rows and still
    be one morning, and one morning is one observation.
    """
    parts = []
    if rows < MIN_GROUP_ROWS:
        parts.append(f"{MIN_GROUP_ROWS - rows} {unit}(s) short of "
                     f"[Score watch] min_group_rows {MIN_GROUP_ROWS}")
    if sessions < MIN_GROUP_SESSIONS:
        parts.append(f"{MIN_GROUP_SESSIONS - sessions} session(s) short of "
                     f"[Score watch] min_group_sessions {MIN_GROUP_SESSIONS}")
    return " and ".join(parts) if parts else None


def describe(values: list[tuple[str, float]], unit: str = "row") -> dict[str, Any]:
    """(sessions, value) pairs to a group block that withholds when it must."""
    sessions = sorted({day for day, _ in values})
    short = withholding(len(values), len(sessions), unit)
    return {
        "n": len(values),
        "sessions": len(sessions),
        "median": None if short else round(
            statistics.median(v for _, v in values), 6),
        "withheld": short is not None,
        "withheld_why": short,
    }


def quantile(values: list[float], share: float) -> float:
    """The value a `share` of the population sits at or below, nearest rank."""
    ordered = sorted(values)
    index = min(max(int(round(share * len(ordered))) - 1, 0), len(ordered) - 1)
    return ordered[index]


def quantile_of(values: list[float], target: float) -> float:
    """Where one value sits in a population, as a share strictly below it."""
    return round(sum(1 for v in values if v < target) / len(values), 4)


# ------------------------------------------------------------ the day screen

def rvol_under(row: dict[str, Any], share: float | None) -> tuple[float | None, str | None]:
    """pm_rvol under one capture share, or null with the row's own reason.

    Nothing is substituted. A denominator the morning refused is refused here
    with the sentence the morning wrote, and a row whose packet held no
    candidate at all is refused with the sentence the pairing wrote, because a
    capture rate cannot rescue a baseline: the correction is entirely in the
    numerator.

    [corrected 2026-09-01: this said "null with the morning's own reason" and
    the baseline branch below returned "the packet carries no usable baseline
    median for this name" whatever the row was. On a row whose packet holds no
    candidate, no baseline was ever looked for, and that sentence dressed a
    never checked state as a checked and empty one.
    measure_capture_rate.packet_fields now records a reason on that branch and
    this reads it.]
    """
    reason = row.get("pm_rvol_reason")
    if reason:
        return None, reason
    median = row.get("baseline_median")
    if not median:
        # The row's own recorded reason first, always. Nothing here can see a
        # packet, so nothing here may narrate why a field is empty.
        return None, (row.get("baseline_median_reason") or
                      ("this row carries no baseline median and no reason for "
                       "its absence, so it was archived before "
                       "measure_capture_rate recorded one and whether a "
                       "baseline was ever looked for cannot be read off it"))
    volume = row.get("pm_volume")
    if volume is None:
        return None, row.get("pm_volume_source")
    if not share:
        return None, ("this candidate offers no share for this row, so the "
                      "ratio stays null. Nothing is substituted and the "
                      "shipped key is not quietly borrowed to fill the hole")
    return round((volume / share) / median, 4), None


def share_for(row: dict[str, Any], rate: float, every_row: bool) -> tuple[float, str]:
    """The share this row would be divided by, under one arm.

    as_fallback is what editing the CRITERIA line actually does: a symbol the
    newest volume check measured keeps its own share and never sees the key.
    to_every_row is the counterfactual where the measured share is discarded.
    """
    own = row.get("pm_capture_share_packet")
    basis = str(row.get("pm_capture_basis_packet") or "")
    if not every_row and own and basis.startswith("this symbol"):
        return own, "this symbol's own measured share, which the key never reaches"
    return rate, "the candidate rate"


def day_screen(rows: list[dict[str, Any]], rate_for: Any,
               every_row: bool) -> dict[str, Any]:
    """Two sets, never one, with both denominators on each.

    cleared_volume_floor is one condition of five. reached_day_watchlist is
    membership, and it is membership only where the packet says the other four
    conditions were already clear.
    """
    cleared: list[dict[str, Any]] = []
    reached: list[dict[str, Any]] = []
    unmeasured: list[dict[str, Any]] = []
    undecidable: list[dict[str, Any]] = []
    values: list[tuple[str, float]] = []
    for row in rows:
        rate = rate_for(row)
        share, share_why = share_for(row, rate, every_row) if rate else (None, None)
        rvol, why = rvol_under(row, share)
        if rvol is None:
            unmeasured.append({"date": row["date"], "ticker": row["ticker"],
                               "why": why})
            continue
        values.append((row["date"], rvol))
        if not RVOL_FLOOR.test(rvol):
            continue
        entry = {"date": row["date"], "ticker": row["ticker"],
                 "pm_rvol": rvol, "capture_share": round(share, 6),
                 "share_source": share_why,
                 # A row whose morning predates the capture correction is a
                 # COUNTERFACTUAL here: that screen ran on the raw socket
                 # numerator and admitted nobody on this line. Counted apart,
                 # because six of nine in the current record come from one
                 # such session and a bare nine would read as nine mornings.
                 "morning_ran_the_correction": bool(
                     row.get("pm_capture_share_packet"))}
        cleared.append(entry)
        failed = row.get("day_failed_conditions")
        if failed is None:
            undecidable.append({
                "date": row["date"], "ticker": row["ticker"],
                "why": ("the packet carries no day_failed_conditions for this "
                        "name, so whether the other four conditions were "
                        "clear is unknown and unknown does not join a set")})
            continue
        if [key for key in failed if key != "premarket_rvol"]:
            continue
        reached.append(entry)

    return {
        "pm_rvol": describe(values),
        "cleared_the_volume_floor": {
            "floor": RVOL_FLOOR.describe(),
            "rows": len(cleared),
            "sessions": len({e["date"] for e in cleared}),
            "counterfactual_rows": sum(
                1 for e in cleared if not e["morning_ran_the_correction"]),
            "names": [f"{e['date']} {e['ticker']}" for e in cleared],
        },
        "reached_the_day_watchlist": {
            "rule": ("cleared the floor AND the packet records no other "
                     "failed condition. Clearing one condition is not "
                     "membership"),
            "rows": len(reached),
            "sessions": len({e["date"] for e in reached}),
            "counterfactual_rows": sum(
                1 for e in reached if not e["morning_ran_the_correction"]),
            "names": [f"{e['date']} {e['ticker']}" for e in reached],
        },
        "membership_undecidable": undecidable,
        "rvol_unmeasurable": {
            "rows": len(unmeasured),
            "reasons": unmeasured,
            "note": ("a null RVOL and a measured low one are different states "
                     "and are counted apart, which is the 2026-08-20 finding "
                     "screen_tally exists to honour"),
        },
    }


def reproduces(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """THE INSTRUMENT PROVES ITSELF FIRST, on cutoff_0830.py's precedent.

    Two claims, on every row whose morning actually ran the capture
    correction. Fed the share the morning itself used, the arithmetic here has
    to return the morning's own pm_rvol; and the membership rule here, cleared
    the floor AND no other failed condition, has to return the morning's own
    day_eligible. A recomputation that cannot reproduce production on
    production's own inputs is not measuring a candidate rate, it is measuring
    the distance between this file and scan.py. Failures are REPORTED, never
    swallowed, and a reader who sees any should disbelieve the tables below.
    """
    checked = 0
    rvol_failures: list[dict[str, Any]] = []
    screen_failures: list[dict[str, Any]] = []
    for row in rows:
        share = row.get("pm_capture_share_packet")
        if not share:
            continue
        checked += 1
        mine, _why = rvol_under(row, share)
        theirs = row.get("pm_rvol_packet")
        if mine is None or theirs is None:
            if mine is not None or theirs is not None:
                rvol_failures.append({
                    "date": row["date"], "ticker": row["ticker"],
                    "recomputed": mine, "packet": theirs,
                    "why": "one of the two is null and the other is not"})
            continue
        # Both sides are already rounded to four places by their own writers,
        # so the tolerance covers the packet rounding its numerator to cents
        # before dividing and nothing else.
        if abs(mine - theirs) > max(abs(theirs) * 1e-4, 1e-4):
            rvol_failures.append({
                "date": row["date"], "ticker": row["ticker"],
                "recomputed": mine, "packet": theirs,
                "why": "recomputed pm_rvol does not reproduce the packet's"})
        failed = row.get("day_failed_conditions") or []
        mine_member = (RVOL_FLOOR.test(theirs)
                       and not [k for k in failed if k != "premarket_rvol"])
        if bool(row.get("day_eligible_packet")) != mine_member:
            screen_failures.append({
                "date": row["date"], "ticker": row["ticker"],
                "recomputed": mine_member,
                "packet": row.get("day_eligible_packet"),
                "failed_conditions": failed})
    return {
        "rows_checked": checked,
        "rows_not_checked": len(rows) - checked,
        "not_checked_why": ("their morning predates the capture correction, so "
                            "the packet carries no pm_capture_share to feed "
                            "back in. Their day screen recomputation is a "
                            "counterfactual and is labelled as one"),
        "pm_rvol_failures": rvol_failures,
        "membership_failures": screen_failures,
        "verdict": ("reproduces" if not rvol_failures and not screen_failures
                    else "DOES NOT REPRODUCE, disbelieve everything below"),
    }


def both_arms(rows: list[dict[str, Any]], rate_for: Any) -> dict[str, Any]:
    return {
        "as_fallback": day_screen(rows, rate_for, every_row=False),
        "to_every_row": day_screen(rows, rate_for, every_row=True),
    }


def screen_pair(screen: dict[str, Any], key: str) -> dict[str, Any]:
    """One screen set, both arms, and BOTH denominators on each arm.

    The compact shape candidate D's ladder carries per rung. Rows and sessions
    travel together and neither is published without the other: a rung that
    reported six names off one morning as six would be reporting one
    observation as six, which is the whole reason [Score watch] counts
    sessions at all.
    """
    return {arm: {"rows": screen[arm][key]["rows"],
                  "sessions": screen[arm][key]["sessions"]}
            for arm in ("as_fallback", "to_every_row")}


# ------------------------------------------------------------- the candidates

def candidate_a(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One re-derived number, by the shipped estimator's own recipe."""
    by_symbol: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        by_symbol.setdefault(row["ticker"], []).append(
            (row["date"], row["capture_observed"]))
    medians = {sym: statistics.median(v for _, v in pairs)
               for sym, pairs in by_symbol.items()}
    sessions = sorted({row["date"] for row in rows})
    short = withholding(len(medians), len(sessions), "symbol")

    socket = sum(row["pm_volume"] for row in rows
                 if row.get("pm_volume") is not None
                 and row.get("true_volume_socket_window"))
    tape = sum(row["true_volume_socket_window"] for row in rows
               if row.get("pm_volume") is not None
               and row.get("true_volume_socket_window"))
    aggregate = round(socket / tape, 6) if tape else None
    value = None if short else round(statistics.median(medians.values()), 6)

    block: dict[str, Any] = {
        "candidate": "A, a single re-derived number",
        "estimator": ("median over symbols of that symbol's median share. "
                      "CRITERIA's own recipe for 0.1172, which is that "
                      "estimator over 110 symbols on the 2026-08-21 payload"),
        "symbols": len(medians),
        "sessions": len(sessions),
        "value": value,
        "withheld": short is not None,
        "withheld_why": short,
        "volume_weighted_aggregate": aggregate,
        "the_0923_argument": None,
        "shipped": SHIPPED_RATE,
        "per_symbol_medians": {k: round(v, 6) for k, v in sorted(medians.items())},
    }
    if value is not None and aggregate is not None:
        safer = "still" if value > aggregate else "NO LONGER"
        direction = ("BELOW" if value < SHIPPED_RATE else
                     "above" if value > SHIPPED_RATE else "equal to")
        block["the_0923_argument"] = (
            f"the per symbol estimator is {value} and the volume weighted "
            f"aggregate is {aggregate}, so the per symbol figure is {safer} "
            "the higher and therefore the safer of the two, which is the "
            "second half of CRITERIA's argument. Against the shipped key it "
            f"is {direction} {SHIPPED_RATE}, and a LOWER capture rate raises "
            "every corrected ratio and ADMITS names, which is the unsafe "
            "direction on a long only screen")
    if value is not None:
        block["day_screen"] = both_arms(rows, lambda _row: value)
    return block


def candidate_b(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per symbol, refused. The refusal is the finding.

    This is not "there is not much data". It is the withholding rule the
    project already wrote down, applied to the groups this candidate would
    need: one group per symbol, each judged on rows AND sessions.
    """
    by_symbol: dict[str, list[str]] = {}
    for row in rows:
        by_symbol.setdefault(row["ticker"], []).append(row["date"])
    per_symbol = []
    for symbol, days in sorted(by_symbol.items()):
        short = withholding(len(days), len(set(days)))
        per_symbol.append({
            "symbol": symbol, "rows": len(days), "sessions": len(set(days)),
            "withheld": short is not None, "withheld_why": short})
    admissible = [s for s in per_symbol if not s["withheld"]]
    counts = {str(n): sum(1 for s in per_symbol if s["rows"] == n)
              for n in sorted({s["rows"] for s in per_symbol})}
    most = max((s["rows"] for s in per_symbol), default=0)
    return {
        "candidate": "B, a share per symbol",
        "verdict": "REFUSED",
        "why": (f"{len(per_symbol)} distinct symbol(s) carry a guarded "
                f"observation and the busiest of them carries {most}. Every "
                f"one of the {len(per_symbol)} is withheld by CRITERIA "
                f"[Score watch]: {MIN_GROUP_ROWS} rows and "
                f"{MIN_GROUP_SESSIONS} sessions are the minimum a group may "
                "be read at, and no symbol here reaches either. Fitting a "
                "share per symbol would publish one number per symbol from "
                "one morning per symbol, which is the exact shape the "
                "withholding rule exists to refuse. It would also be "
                "unnecessary: scan.attach_capture_estimate ALREADY prefers a "
                "symbol's own measured share where the newest volume check "
                "carries one, so the key this study is about is only ever the "
                "fallback for a symbol nothing has measured"),
        "symbols": len(per_symbol),
        "symbols_admissible": len(admissible),
        "observations_per_symbol": counts,
        "per_symbol": per_symbol,
        "day_screen": None,
    }


def candidate_c(rows: list[dict[str, Any]], bands: int) -> dict[str, Any]:
    """Banded by liquidity, on avg_volume_20d, the only key the morning holds.

    The band EDGES are ranks over the observed rows, not chosen numbers, so
    nothing here is a threshold and nothing is added to CRITERIA. They are
    display boundaries in exactly the sense measure_baseline_floor's buckets
    are, and a band whose group is too small to read is withheld rather than
    published thin.
    """
    keyed = sorted(
        (row["avg_volume_20d"], row["capture_observed"], row["date"],
         row["ticker"])
        for row in rows if row.get("avg_volume_20d") is not None)
    missing = [{"date": r["date"], "ticker": r["ticker"],
                "why": r.get("avg_volume_20d_reason")}
               for r in rows if r.get("avg_volume_20d") is None]

    out: list[dict[str, Any]] = []
    total = len(keyed)
    for index in range(bands):
        low = index * total // bands
        high = (index + 1) * total // bands
        chunk = keyed[low:high]
        if not chunk:
            continue
        block = describe([(day, share) for _v, share, day, _t in chunk])
        block.update({
            "band": index + 1,
            "avg_volume_20d_from": chunk[0][0],
            "avg_volume_20d_to": chunk[-1][0],
            "rows": [f"{day} {tick}" for _v, _s, day, tick in chunk],
        })
        out.append(block)

    readable = [b for b in out if not b["withheld"]]
    finding = None
    if len(readable) >= 2:
        thin, thick = readable[0], readable[-1]
        if thin["median"] > thick["median"]:
            finding = (
                "THE ASSUMPTION IS CONTRADICTED. The thinnest band captures "
                f"{thin['median']} and the thickest {thick['median']}, so the "
                "thin names capture MORE of their own tape rather than less. "
                f"The assumption under test is {ASSUMPTION} If this holds, "
                "the single number understates thin names LESS than it "
                "understates liquid ones, and the bias the float rotation "
                "fallback was said to reinstate points the other way")
        elif thin["median"] < thick["median"]:
            finding = (
                "the assumption reproduces. The thinnest band captures "
                f"{thin['median']} and the thickest {thick['median']}. "
                f"{ASSUMPTION}")
        else:
            finding = ("the two readable bands sit at the same median, so "
                       "this separates nothing")
    else:
        finding = ("fewer than two bands are readable at the [Score watch] "
                   "minimums, so no direction is claimed")

    spearman = _spearman([v for v, _s, _d, _t in keyed],
                         [s for _v, s, _d, _t in keyed])
    result: dict[str, Any] = {
        "candidate": "C, banded by liquidity on avg_volume_20d",
        "bands": out,
        "rows_without_a_liquidity_key": missing,
        "direction": finding,
        "rank_correlation": {
            "rho": spearman,
            "n": len(keyed),
            "sessions": len({d for _v, _s, d, _t in keyed}),
            "reading": ("negative means capture share FALLS as average volume "
                        "rises, which is the opposite of the assumption"),
            "withheld_why": withholding(len(keyed),
                                        len({d for _v, _s, d, _t in keyed})),
        },
        "assumption_under_test": ASSUMPTION,
    }
    if readable:
        edges = [(b["avg_volume_20d_to"], b["median"]) for b in readable]

        def rate_for(row: dict[str, Any]) -> float | None:
            volume = row.get("avg_volume_20d")
            if volume is None:
                return None
            for ceiling, median in edges:
                if volume <= ceiling:
                    return median
            return edges[-1][1]

        result["day_screen"] = both_arms(rows, rate_for)
    return result


def candidate_d(rows: list[dict[str, Any]],
                shares: tuple[float, ...]) -> dict[str, Any]:
    """The distribution, and what conservatism costs in admitted names."""
    per_row = [row["capture_observed"] for row in rows]
    by_symbol: dict[str, list[float]] = {}
    for row in rows:
        by_symbol.setdefault(row["ticker"], []).append(row["capture_observed"])
    per_symbol = [statistics.median(v) for v in by_symbol.values()]
    sessions = len({row["date"] for row in rows})

    ladder = []
    for share in shares:
        value = round(quantile(per_symbol, share), 6)
        screen = both_arms(rows, lambda _row, v=value: v)
        ladder.append({
            "quantile": share,
            "capture_rate": value,
            "versus_shipped": round(value - SHIPPED_RATE, 6),
            # [corrected 2026-09-01: these two carried the row count of each
            # arm and nothing else, so a rung stated a screen cost in the one
            # unit the rest of these files never state alone.]
            "cleared_the_volume_floor": screen_pair(
                screen, "cleared_the_volume_floor"),
            "reached_the_day_watchlist": screen_pair(
                screen, "reached_the_day_watchlist"),
            "day_screen": screen,
        })

    shipped_screen = both_arms(rows, lambda _row: SHIPPED_RATE)
    return {
        "candidate": "D, the distribution",
        "rows": len(per_row),
        "sessions": sessions,
        "symbols": len(per_symbol),
        "withheld_why": withholding(len(per_row), sessions),
        "shipped_sits_at": {
            "value": SHIPPED_RATE,
            "quantile_of_the_rows": quantile_of(per_row, SHIPPED_RATE),
            "quantile_of_the_per_symbol_medians": quantile_of(
                per_symbol, SHIPPED_RATE),
            "reading": ("the share of the guarded population that captured "
                        "LESS than the shipped key. Above 0.5 means the "
                        "shipped number is already the conservative side of "
                        "this record"),
        },
        "per_row_quantiles": {str(q): round(quantile(per_row, q), 6)
                              for q in REPORTED_QUANTILES},
        "per_symbol_quantiles": {str(q): round(quantile(per_symbol, q), 6)
                                 for q in REPORTED_QUANTILES},
        "at_the_shipped_rate": shipped_screen,
        "conservative_ladder": ladder,
        "direction_note": ("a HIGHER assumed capture divides the socket count "
                           "by more, produces a LOWER corrected ratio, and "
                           "admits FEWER names. Withholding is the safe "
                           "direction on a long only screen, so the cost of "
                           "conservatism is measured in names not admitted "
                           "and never in names wrongly refused"),
    }


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, spelled out because this project takes no scipy.

    Ranks rather than values on purpose: capture share and average volume are
    on wildly different scales and one enormous name would otherwise decide
    the answer.
    """
    if len(xs) < 2:
        return None

    def rank(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while (stop + 1 < len(order)
                   and values[order[stop + 1]] == values[order[index]]):
                stop += 1
            average = (index + stop) / 2 + 1
            for position in range(index, stop + 1):
                out[order[position]] = average
            index = stop + 1
        return out

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    numerator = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denominator = (sum((a - mx) ** 2 for a in rx)
                   * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(numerator / denominator, 4) if denominator else None


# ------------------------------------------------------------------ printing

def _screen_line(label: str, screen: dict[str, Any]) -> str:
    cleared = screen["cleared_the_volume_floor"]
    reached = screen["reached_the_day_watchlist"]
    rvol = screen["pm_rvol"]
    median = ("WITHHELD" if rvol["withheld"]
              else f"{rvol['median']:>8.4f}")
    # The unmeasurable count travels with the two sets, always. A null RVOL and
    # a measured low one are different states, and a line reporting only the
    # two sets would present a name nobody could measure as a name that failed.
    return (f"    {label:<14} median pm_rvol {median}  "
            f"cleared the floor {cleared['rows']:>2} row(s) over "
            f"{cleared['sessions']} session(s), reached the watchlist "
            f"{reached['rows']:>2} over {reached['sessions']} "
            f"({reached['counterfactual_rows']} counterfactual), "
            f"{screen['rvol_unmeasurable']['rows']} unmeasurable, "
            f"{len(screen['membership_undecidable'])} undecidable")


def _ladder_cell(pair: dict[str, Any]) -> str:
    """One ladder cell: both arms, and both denominators on each of them.

    rows(sessions), twice. _screen_line above spells the same two counts out
    in words and this spells them in a column, because a ladder is a table and
    a table needs one, but neither may print the rows without the sessions.
    """
    fallback, every = pair["as_fallback"], pair["to_every_row"]
    return (f"{fallback['rows']}({fallback['sessions']})"
            f" / {every['rows']}({every['sessions']})")


def report(result: dict[str, Any]) -> None:
    print("sweep_capture_rate: arithmetic on "
          f"{result['payload']}, zero vendor calls and no database read")
    print(f"shipped [Collector] premarket_capture_rate = {SHIPPED_RATE}. "
          "THIS FILE MOVES NOTHING\n")
    print(f"guarded fit set: {result['fit_rows']} row(s) over "
          f"{result['fit_sessions']} session(s), against CRITERIA [Truth] "
          f"baseline_sessions of {result['pre_registered_denominator']} "
          "sessions, which is the pre-registered denominator this record has "
          "not reached\n")

    check = result["reproduction_check"]
    print(f"reproduction check: {check['verdict']}. "
          f"{check['rows_checked']} row(s) fed the share their own morning "
          f"used reproduce that morning's pm_rvol and day_eligible; "
          f"{check['rows_not_checked']} row(s) not checked, "
          f"{check['not_checked_why']}")
    for failure in check["pm_rvol_failures"] + check["membership_failures"]:
        print(f"  FAILED {failure['date']} {failure['ticker']}: "
              f"recomputed {failure['recomputed']} against packet "
              f"{failure['packet']}")
    print()

    block = result["A"]
    print(f"A  {block['estimator']}")
    if block["withheld"]:
        print(f"   WITHHELD: {block['withheld_why']}")
    else:
        print(f"   value {block['value']} over {block['symbols']} symbol(s), "
              f"{block['sessions']} session(s). Shipped {SHIPPED_RATE}")
        print(f"   {block['the_0923_argument']}")
        for label, screen in (("as fallback", block["day_screen"]["as_fallback"]),
                              ("every row", block["day_screen"]["to_every_row"])):
            print(_screen_line(label, screen))

    block = result["B"]
    print(f"\nB  a share per symbol: {block['verdict']}")
    print(f"   {block['symbols']} symbol(s), "
          f"{block['symbols_admissible']} admissible at the [Score watch] "
          f"minimums. Rows per symbol: {block['observations_per_symbol']}")
    print(f"   {block['why']}")

    block = result["C"]
    print("\nC  banded by liquidity on the packet's avg_volume_20d")
    print(f"   {'band':>4} {'avg_volume_20d':>28} {'rows':>5} {'sess':>5} "
          f"{'median share':>13}")
    for band in block["bands"]:
        span = (f"{band['avg_volume_20d_from']:,.0f} to "
                f"{band['avg_volume_20d_to']:,.0f}")
        value = ("WITHHELD" if band["withheld"] else f"{band['median']:.6f}")
        print(f"   {band['band']:>4} {span:>28} {band['n']:>5} "
              f"{band['sessions']:>5} {value:>13}")
        if band["withheld"]:
            print(f"        {band['withheld_why']}")
    correlation = block["rank_correlation"]
    print(f"   rank correlation of capture share against average volume: "
          f"rho {correlation['rho']} over {correlation['n']} row(s), "
          f"{correlation['sessions']} session(s)")
    print(f"   {block['direction']}")
    if block.get("day_screen"):
        for label, screen in (("as fallback", block["day_screen"]["as_fallback"]),
                              ("every row", block["day_screen"]["to_every_row"])):
            print(_screen_line(label, screen))

    block = result["D"]
    print("\nD  the distribution")
    sits = block["shipped_sits_at"]
    print(f"   {SHIPPED_RATE} sits at quantile "
          f"{sits['quantile_of_the_rows']} of the guarded rows and "
          f"{sits['quantile_of_the_per_symbol_medians']} of the per symbol "
          "medians")
    print(f"   per symbol quantiles: {block['per_symbol_quantiles']}")
    print(f"   {'quantile':>9} {'rate':>9} {'vs shipped':>11} "
          f"{'cleared':>19} {'watchlist':>19}")
    shipped = block["at_the_shipped_rate"]
    cleared = _ladder_cell(screen_pair(shipped, "cleared_the_volume_floor"))
    reached = _ladder_cell(screen_pair(shipped, "reached_the_day_watchlist"))
    print(f"   {'shipped':>9} {SHIPPED_RATE:>9} {0.0:>11} "
          f"{cleared:>19} {reached:>19}")
    for step in block["conservative_ladder"]:
        print(f"   {step['quantile']:>9} {step['capture_rate']:>9} "
              f"{step['versus_shipped']:>+11} "
              f"{_ladder_cell(step['cleared_the_volume_floor']):>19} "
              f"{_ladder_cell(step['reached_the_day_watchlist']):>19}")
    print("   two numbers per cell, as fallback then applied to every row, "
          "and each is rows(sessions)")
    print(f"   {block['direction_note']}")

    residual = result["residual_no_divisor_closes"]
    window = residual["collector_window_share"]
    composite = residual["composite_socket_share_of_the_full_premarket"]
    print("\nTHE RESIDUAL NO DIVISOR CLOSES")
    if window["withheld"]:
        print(f"   median collector_window_share WITHHELD, "
              f"{window['withheld_why']}")
    else:
        print(f"   median collector_window_share {window['median']} over "
              f"{window['rows']} row(s), {window['sessions']} session(s): the "
              "share of the whole premarket tape")
        print("   that falls inside the window the socket was awake for.")
    if composite["value"] is not None:
        print(f"   composite socket share of the FULL premarket window "
              f"{composite['value']} over {composite['rows']} row(s), "
              f"{composite['sessions']} session(s)")
    print("   The capture rate corrects the FEED. The 07:20 start is a "
          "different shortfall with a")
    print("   different fix, and no value of this key reaches it.")


def run(payload_path: Any = None, bands: int = DEFAULT_BANDS,
        shares: tuple[float, ...] = DEFAULT_QUANTILES) -> dict[str, Any]:
    path = payload_path or newest_payload()
    payload = load(path)
    rows = [row for row in payload["rows"] if row.get("kept")]
    if not rows:
        raise SystemExit(
            f"{path} carries no row that survives its own guards, so there is "
            "nothing to sweep. The refusals are in the payload.")
    result = {
        "swept_at": payload.get("generated_at"),
        "payload": str(path),
        "shipped_rate": SHIPPED_RATE,
        "fit_rows": len(rows),
        "fit_sessions": len({row["date"] for row in rows}),
        "pre_registered_denominator": payload["shipped"][
            "truth_baseline_sessions"],
        "reproduction_check": reproduces(rows),
        "A": candidate_a(rows),
        "B": candidate_b(rows),
        "C": candidate_c(rows, bands),
        "D": candidate_d(rows, shares),
        "residual_no_divisor_closes": payload["summary"][
            "residual_no_divisor_closes"],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score four candidate capture rates against the archive.")
    parser.add_argument("--payload", default=None,
                        help="the archived study to sweep; defaults to the "
                             f"newest doc/research/{PATH_STEM}-*.json")
    parser.add_argument("--bands", type=int, default=DEFAULT_BANDS,
                        help="liquidity bands for candidate C. A display "
                             "boundary, not a threshold")
    parser.add_argument("--quantiles", default=None,
                        help="comma separated quantiles for candidate D's "
                             "ladder. Default "
                             + ",".join(str(q) for q in DEFAULT_QUANTILES))
    parser.add_argument("--json", action="store_true",
                        help="print the whole result and no table")
    args = parser.parse_args(argv)

    shares = (tuple(float(x) for x in args.quantiles.split(","))
              if args.quantiles else DEFAULT_QUANTILES)
    path = (config.PROJECT_ROOT / args.payload) if args.payload else None
    result = run(path, args.bands, shares)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
