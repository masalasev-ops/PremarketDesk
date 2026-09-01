"""What each morning's watchlist would have been on the MEASURED premarket RVOL.

An instrument, not a pipeline step. Nothing downstream reads its output, it
writes to no table, and it makes no vendor call.

    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.counterfactual_watchlist
    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.counterfactual_watchlist --no-write

THE QUESTION. data/UNVERIFIED has been gated on collector volume since
2026-08-18, and the gate is now blocked on a DECISION rather than on a
measurement, because the measurement arrived: night/true_volume.py has written
pm_rvol_true into picks for every live row. So the question this answers is
narrow and answerable. If the day screen's volume floor had been applied to
pm_rvol_true instead of to the published estimate, which names would each
morning's watchlist have held.

WHY THE DICT COMES FROM THE PACKET AND NOT FROM THE PICKS ROW. A candidate
cannot be rebuilt from picks. picks carries none of price, quote.marketCap,
quote.twoHundredDayAveragePrice or catalyst_found, so 3 of the 5 day conditions
and 4 of the 6 swing conditions would be unavailable and the reconstruction
would answer a different screen's question. The dict replayed here is the
packet's own candidate, which is literally the dict the shipped functions were
called on at 08:45, with pm_rvol and pm_float_rotation overwritten from the
picks row and nothing else touched.

WHY THE SHIPPED FUNCTIONS ARE CALLED RATHER THAN REIMPLEMENTED.
morning.scan.evaluate_eligibility and morning.scan.score_candidate are the
screen. A reimplementation that drifts by one line produces a counterfactual
about a screen that does not exist, which is worse than no counterfactual at
all. Both mutate their argument in place and return None, so every pass gets
its own deepcopy: sharing one dict would let the baseline pass overwrite the
inputs the counterfactual pass still needs.

THE BASELINE PASS EXISTS SO A DRIFTED SCORE IS NOT READ BACKWARDS. Before any
substitution, each packet is replayed UNCHANGED and compared against its own
stored day_eligible, swing_eligible, score and conviction. CRITERIA
[Score premarket float rotation] moved its one point edge from 0.00014 to
0.0002 on 2026-08-31, and no historical row was rescored, so a row scored under
the old edge replays lower today for a reason that has nothing to do with
volume. Those rows are recorded as criteria_drifted with the differing
components named, and they are held out of the gained and lost counts. Without
that pass the drift would read as the counterfactual LOWERING a score, which is
the opposite of what it does.

THE SESSION GUARD IS night/true_volume.reread()'s OWN. A packet whose
run_time_et is not [Scan] run_time describes a different market and its
watchlists are not a morning's. That refusal catches the 2026-08-21 stub
without special casing a date, and every row of a refused session is
UNRESOLVABLE with the packet's recorded run time in the reason. Never a pass
and never a fail: a session that could not be replayed and a session that
replayed to no change are different states.

WHAT THIS DELIBERATELY DOES NOT DO. It does not lift data/UNVERIFIED, does not
propose a threshold, and does not add a section to site/Weekly.html.
night/weekly_page.py's charter is no new data, no new table and no measurement
of its own, and a counterfactual re-runs the screen, which is a measurement.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sqlite3
import statistics
from pathlib import Path
from typing import Any

from core import config
from core import criteria
from core import ettime
from core import store
from morning import scan

_CRIT = criteria.load()

# Every one of these is READ. This instrument adds no key and hardcodes none.
SCHEDULED_RUN_TIME = _CRIT.clock_text("scan", "run_time")
RVOL_FLOOR = _CRIT.rule("day_setup", "premarket_rvol")
MIN_GROUP_ROWS = _CRIT.integer("score_watch", "min_group_rows")
MIN_GROUP_SESSIONS = _CRIT.integer("score_watch", "min_group_sessions")
COLLECTOR_START = _CRIT.clock_text("collector", "start_time")
BASELINE_START = _CRIT.clock_text("baseline", "session_start")
CAPTURE_RATE = _CRIT.number("collector", "premarket_capture_rate")

# The four verdict fields the baseline pass compares. Named once so the
# comparison, the drift report and the payload cannot fall out of step.
VERDICT_FIELDS = ("day_eligible", "swing_eligible", "score", "conviction")

# The outcome columns attached per gained name. Each is reported with ITS OWN
# filled count, because they are not all filled and a missing day5_close is not
# a zero five day move.
OUTCOME_COLUMNS = (
    "next_day_open",
    "next_day_high",
    "next_day_low",
    "next_day_close",
    "pm_high_broke_next_day",
    "mfe_pct_true",
    "mae_pct_true",
    "day5_close",
)

# The four above that are DOLLAR LEVELS rather than measures of a move. Their
# median across names is arithmetic without a referent: a 40 dollar name and a
# 1,500 dollar name contribute the same weight to it and neither number says
# what happened. They are carried per row in the payload, and the report prints
# the median only because the caller asked every column for one, labelled.
LEVEL_COLUMNS = frozenset({
    "next_day_open", "next_day_high", "next_day_low", "next_day_close",
})

# A closure tolerance for the decomposition identity below, NOT a screen
# threshold: nothing about a candidate is decided on it and it gates no
# published number. The three factors should multiply back to the total ratio
# exactly, and they do not, because every column they are built from is stored
# ROUNDED. pm_rvol carries four decimals, pm_rvol_true and
# collector_window_share carry six, so the identity can only close to the
# coarsest of those. Measured over the 37 rows that carry all four inputs: the
# relative residual runs 1.96e-08 to 2.53e-06, which is the rounding and
# nothing else. 1e-5 sits an order of magnitude above the worst observed
# residual and orders of magnitude below any real disagreement. The maximum
# residual is reported beside the count so the tolerance can be argued with
# rather than trusted.
CLOSURE_TOLERANCE = 1e-5

PICKS_COLUMNS = (
    "date", "ticker", "source",
    "pm_rvol", "pm_rvol_true", "pm_float_rotation", "pm_float_rotation_true",
    "pm_volume", "pm_volume_estimated", "pm_volume_true",
    "true_volume_socket_window", "collector_window_share",
    "true_baseline_median", "true_baseline_sessions", "true_bars",
    "capture_observed", "estimate_error", "truth_source", "truth_reason",
    "fill_plausible", "fill_plausible_reason",
    "next_day_open", "next_day_high", "next_day_low", "next_day_close",
    "pm_high_broke_next_day", "mfe_pct_true", "mae_pct_true", "day5_close",
    "next_day_refused_reason", "day5_refused_reason",
)


def load_picks() -> list[dict[str, Any]]:
    """Every live picks row, READ ONLY.

    store.init() is deliberately not called: it runs an UPDATE, and nothing in
    this project may write to picks except morning/scan.py.
    """
    columns = ", ".join(PICKS_COLUMNS)
    with store.session() as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(r) for r in connection.execute(
            f"SELECT {columns} FROM picks WHERE source = 'live' ORDER BY date, ticker")]
    return rows


def load_packet(day: str) -> tuple[dict[str, Any] | None, str | None]:
    """The session's packet, or the reason it cannot answer.

    The refusal is night/true_volume.reread()'s, quoted in shape rather than
    imported, because importing that module pulls the Alpaca transport into an
    instrument whose whole claim is that it makes no vendor call.
    """
    path = config.run_path(day) / "packet.json"
    if not path.is_file():
        return None, f"no packet at runs/{day}/packet.json"
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return None, f"packet unreadable: {type(exc).__name__}"
    candidates = packet.get("candidates") or []
    if not candidates:
        return None, "the packet carries no candidates"
    run_time = str(packet.get("run_time_et") or "")
    if run_time != SCHEDULED_RUN_TIME:
        return None, (
            f"the packet was gathered at {run_time or 'an unrecorded time'}, not "
            f"the scheduled {SCHEDULED_RUN_TIME}, so it describes a different "
            "market and its watchlists are not a morning's")
    return packet, None


def replay(candidate: dict[str, Any],
           pm_rvol: Any = "keep",
           pm_float_rotation: Any = "keep") -> dict[str, Any]:
    """Run the SHIPPED screen and score over a private copy of the candidate.

    Both functions mutate in place and return None, so the deepcopy is not
    tidiness: without it the first pass would overwrite the pm_rvol the second
    pass has not read yet, and the two passes would silently become one.

    The sentinel is the string 'keep' rather than None because None is a
    MEANINGFUL substitution here. A row whose pm_rvol_true is null must be able
    to say so by writing null into the dict, and a default of None would make
    that indistinguishable from asking for no substitution at all.
    """
    working = copy.deepcopy(candidate)
    if pm_rvol != "keep":
        working["pm_rvol"] = pm_rvol
    if pm_float_rotation != "keep":
        working["pm_float_rotation"] = pm_float_rotation
    scan.evaluate_eligibility(working)
    scan.score_candidate(working)
    return working


def verdict_of(row: dict[str, Any]) -> dict[str, Any]:
    """The four fields, plus what a reader needs to argue with them."""
    return {
        "day_eligible": row.get("day_eligible"),
        "swing_eligible": row.get("swing_eligible"),
        "score": row.get("score"),
        "score_partial": row.get("score_partial"),
        "score_unavailable": list(row.get("score_unavailable") or []),
        "conviction": row.get("conviction"),
        "day_failed_conditions": list(row.get("day_failed_conditions") or []),
        "swing_failed_conditions": list(row.get("swing_failed_conditions") or []),
        "volume_measure_used": row.get("volume_measure_used"),
    }


def component_points(row: dict[str, Any]) -> dict[str, Any]:
    return {c["component"]: c["points"] for c in (row.get("score_components") or [])}


def drift_between(stored: dict[str, Any], replayed: dict[str, Any]) -> dict[str, Any] | None:
    """What the packet recorded against what the same functions produce today.

    Returns None when they agree. When they do not, the DIFFERING COMPONENTS
    are named rather than only the total, because a total that moved says the
    screen changed and a named component says which knob did it.
    """
    fields = {}
    for name in VERDICT_FIELDS:
        if replayed.get(name) != stored.get(name):
            fields[name] = {"stored": stored.get(name), "replayed": replayed.get(name)}
    if not fields:
        return None
    before, after = component_points(stored), component_points(replayed)
    components = {}
    for name in sorted(set(before) | set(after)):
        if before.get(name) != after.get(name):
            components[name] = {"stored": before.get(name), "replayed": after.get(name)}
    return {"fields": fields, "components": components}


def decompose(row: dict[str, Any]) -> dict[str, Any]:
    """Split pm_rvol_true / pm_rvol into the window, the feed and the baseline.

    THE SUBSTITUTION SWAPS A WINDOW, NOT ONLY A TAPE, and the two halves have
    different fixes, so reporting one number for both would argue for the wrong
    one. Published pm_rvol divides a numerator that starts at [Collector]
    start_time by a baseline that accumulates from [Baseline] session_start.
    pm_rvol_true divides session_start to cutoff by session_start to cutoff.

      window      1 / collector_window_share. What the numerator gains from
                  widening the window on ONE tape. Bounded below by
                  construction: it cannot be less than 1.
      feed        true_volume_socket_window / the published numerator. What the
                  socket, and then the morning's capture correction, got wrong
                  over the minutes the socket was actually listening to.
      baseline    the published baseline median over the true one. The
                  denominators come from two vendors over the same clock window.

    Each is null with a reason where its inputs are not there. The published
    baseline median is recovered as numerator / pm_rvol rather than refetched,
    which is exact: it is the division the morning performed.
    """
    out: dict[str, Any] = {
        "published_numerator": None,
        "published_numerator_column": None,
        "published_baseline_median": None,
        "window_factor": None,
        "feed_factor": None,
        "baseline_factor": None,
        "total_ratio": None,
        "collector_window_share": row["collector_window_share"],
        "closes": None,
        "residual": None,
        "reasons": {},
    }

    # FIRST, and before anything that can return early. The total ratio needs
    # only the two RVOLs, and the numerator columns it does not need are
    # exactly the ones a pre-correction row is missing. Computing it after the
    # numerator lookup silently emptied the whole pre-correction slice, which
    # is the slice the headline has to be split on, so the bug deleted the
    # evidence for the split rather than reporting it as absent.
    if row["pm_rvol"] in (None, 0):
        out["reasons"]["total_ratio"] = (
            "pm_rvol is null or zero, so there is no published ratio to compare "
            "the measured one against")
    elif row["pm_rvol_true"] is None:
        out["reasons"]["total_ratio"] = (
            "pm_rvol_true is null: " + (row["truth_reason"] or "no reason recorded"))
    else:
        out["total_ratio"] = row["pm_rvol_true"] / row["pm_rvol"]

    if row["pm_volume_estimated"] is not None:
        numerator, column = row["pm_volume_estimated"], "pm_volume_estimated"
    elif row["pm_volume"] is not None:
        numerator, column = row["pm_volume"], "pm_volume"
        out["reasons"]["published_numerator"] = (
            "pm_volume_estimated is null, so the published numerator is the RAW "
            "socket volume: this row predates the capture correction")
    else:
        out["reasons"]["published_numerator"] = (
            "neither pm_volume_estimated nor pm_volume was recorded, so the "
            "numerator the morning divided cannot be read and the gap cannot be "
            "split into its window and feed halves for this row")
        return out
    out["published_numerator"] = numerator
    out["published_numerator_column"] = column

    if row["pm_rvol"] in (None, 0):
        out["reasons"]["published_baseline_median"] = (
            "pm_rvol is null or zero, so the denominator it was divided by "
            "cannot be recovered from it")
    else:
        out["published_baseline_median"] = numerator / row["pm_rvol"]

    share = row["collector_window_share"]
    if share in (None, 0):
        out["reasons"]["window_factor"] = (
            "collector_window_share is null or zero, so how much of the "
            f"{BASELINE_START} to cutoff volume sat inside the collector's "
            f"{COLLECTOR_START} start is not measured for this row")
    else:
        out["window_factor"] = 1.0 / share

    socket_window = row["true_volume_socket_window"]
    if socket_window is None:
        out["reasons"]["feed_factor"] = (
            "true_volume_socket_window is null, so what the consolidated tape "
            "held over the minutes the socket was listening is not measured")
    elif not numerator:
        out["reasons"]["feed_factor"] = "the published numerator is zero"
    else:
        out["feed_factor"] = socket_window / numerator

    if not row["true_baseline_median"]:
        out["reasons"]["baseline_factor"] = (
            "true_baseline_median is null or zero, so the two denominators "
            "cannot be compared")
    elif out["published_baseline_median"] is None:
        out["reasons"]["baseline_factor"] = out["reasons"].get(
            "published_baseline_median", "the published denominator is unknown")
    else:
        out["baseline_factor"] = out["published_baseline_median"] / row["true_baseline_median"]

    parts = (out["window_factor"], out["feed_factor"], out["baseline_factor"])
    if out["total_ratio"] is not None and all(p is not None for p in parts):
        product = parts[0] * parts[1] * parts[2]
        out["residual"] = abs(product - out["total_ratio"]) / abs(out["total_ratio"])
        out["closes"] = out["residual"] <= CLOSURE_TOLERANCE
    else:
        out["reasons"]["closes"] = (
            "the identity was not checked on this row: one of its four terms "
            "is null for the reason recorded beside that term")
    return out


def build_rows(picks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One record per picks row, and one per session, with every state named."""
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in picks:
        by_date.setdefault(row["date"], []).append(row)

    sessions: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for day in sorted(by_date):
        packet, refusal = load_packet(day)
        rows = by_date[day]
        if packet is None:
            sessions.append({
                "date": day, "resolved": False, "refusal_reason": refusal,
                "picks_rows": len(rows), "packet_candidates": None,
            })
            for row in rows:
                records.append({
                    "date": day, "ticker": row["ticker"], "state": "unresolvable",
                    "state_reason": refusal, "raw": {k: row[k] for k in PICKS_COLUMNS},
                    "stored": None, "baseline": None, "counterfactual": None,
                    "drift": None, "decomposition": None,
                })
            continue

        candidates = {c["symbol"]: c for c in packet["candidates"]}
        sessions.append({
            "date": day, "resolved": True, "refusal_reason": None,
            "picks_rows": len(rows), "packet_candidates": len(candidates),
            "run_time_et": packet.get("run_time_et"),
            "rvol_cutoff_hhmm": packet.get("rvol_cutoff_hhmm"),
        })
        for row in rows:
            record: dict[str, Any] = {
                "date": day, "ticker": row["ticker"],
                "raw": {k: row[k] for k in PICKS_COLUMNS},
                "decomposition": decompose(row),
            }
            candidate = candidates.get(row["ticker"])
            if candidate is None:
                record.update({
                    "state": "unresolvable",
                    "state_reason": ("the packet for this session carries no candidate "
                                     "for this ticker, so there is no dict to replay"),
                    "stored": None, "baseline": None, "counterfactual": None, "drift": None,
                })
                records.append(record)
                continue

            stored = verdict_of(candidate)
            base = replay(candidate)
            drift = drift_between(candidate, base)
            record["stored"] = stored
            record["baseline"] = verdict_of(base)
            record["drift"] = drift

            if row["pm_rvol_true"] is None:
                record.update({
                    "state": "unresolvable",
                    "state_reason": ("picks carries no pm_rvol_true for this row: "
                                     + (row["truth_reason"] or "no reason recorded")),
                    "counterfactual": None,
                })
                records.append(record)
                continue

            counter = replay(candidate,
                             pm_rvol=row["pm_rvol_true"],
                             pm_float_rotation=row["pm_float_rotation_true"])
            record["counterfactual"] = verdict_of(counter)
            if drift is not None:
                record["state"] = "criteria_drifted"
                record["state_reason"] = (
                    "the packet replays to a different verdict on today's CRITERIA, so "
                    "this row cannot be attributed to the substitution: "
                    + ", ".join(f"{k} {v['stored']!r} replays {v['replayed']!r}"
                                for k, v in drift["fields"].items()))
            elif counter["day_eligible"] and not base["day_eligible"]:
                record["state"] = "gained"
                record["state_reason"] = (
                    f"day_eligible turns True: pm_rvol {row['pm_rvol']} becomes "
                    f"pm_rvol_true {row['pm_rvol_true']} against {RVOL_FLOOR.describe()}")
            elif base["day_eligible"] and not counter["day_eligible"]:
                record["state"] = "lost"
                record["state_reason"] = (
                    f"day_eligible turns False: pm_rvol {row['pm_rvol']} becomes "
                    f"pm_rvol_true {row['pm_rvol_true']} against {RVOL_FLOOR.describe()}")
            elif base["day_eligible"]:
                record["state"] = "held"
                record["state_reason"] = "day_eligible on both the published and the true number"
            else:
                record["state"] = "absent"
                record["state_reason"] = "day_eligible on neither number"
            records.append(record)
    return records, sessions


def group_state(values: list[Any], sessions: set[str]) -> dict[str, Any]:
    """The [Score watch] withholding rule, per metric.

    BOTH DENOMINATORS. Twelve names from one morning share a tape and are one
    observation, so a group states rows AND sessions and is withheld when it
    falls short of either, saying how far short it is.
    """
    short = []
    if len(values) < MIN_GROUP_ROWS:
        short.append(_plural(MIN_GROUP_ROWS - len(values), "row")
                     + f" short of {MIN_GROUP_ROWS}")
    if len(sessions) < MIN_GROUP_SESSIONS:
        short.append(_plural(MIN_GROUP_SESSIONS - len(sessions), "session")
                     + f" short of {MIN_GROUP_SESSIONS}")
    return {
        "filled_rows": len(values),
        "filled_sessions": len(sessions),
        "withheld": bool(short),
        "withheld_reason": "; ".join(short) or None,
        "median": None if short or not values else round(statistics.median(values), 4),
    }


def outcome_table(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per column filled counts and a withheld-or-published median for each.

    EACH COLUMN CARRIES ITS OWN COUNT. They are not all filled: day5_close
    needs five sessions after the pick and the newest picks have not had them,
    and a corporate action refuses a next session bar outright. A column
    summarised under the group's row count would report a median of seven rows
    as if it stood on eleven.
    """
    table: dict[str, Any] = {"rows": len(records),
                             "sessions": len(sorted({r["date"] for r in records})),
                             "session_dates": sorted({r["date"] for r in records}),
                             "columns": {}}
    for column in OUTCOME_COLUMNS:
        values, sessions, refused = [], set(), {}
        for record in records:
            value = record["raw"][column]
            if value is None:
                reason = record["raw"].get("day5_refused_reason" if column == "day5_close"
                                           else "next_day_refused_reason")
                refused[record["ticker"]] = reason or "not filled yet, and no refusal recorded"
                continue
            values.append(value)
            sessions.add(record["date"])
        entry = group_state(values, sessions)
        entry["is_price_level"] = column in LEVEL_COLUMNS
        entry["unfilled"] = refused
        # A count is not a median and the withholding rule does not reach it:
        # "9 of 11 broke the premarket high" states its own denominator in the
        # sentence, which is the thing the rule exists to make a median do.
        if column == "pm_high_broke_next_day" and values:
            entry["broke_count"] = sum(1 for v in values if v)
        # The SIGN carries the fact, per [Outcomes]: mfe_pct_true is positive
        # when the next session's high ran past entry_ref_true, and
        # mae_pct_true is NEGATIVE when the low undercut stop_ref_true, so a
        # positive adverse excursion means the stop reference was never
        # breached. A reader who assumes adverse means negative reads the
        # median backwards.
        if column == "mfe_pct_true" and values:
            entry["reached_entry_ref_true"] = sum(1 for v in values if v > 0)
        if column == "mae_pct_true" and values:
            entry["undercut_stop_ref_true"] = sum(1 for v in values if v < 0)
        table["columns"][column] = entry
    return table


def median_note(values: list[float], sessions: set[str]) -> dict[str, Any]:
    """A descriptive median of the MEASUREMENT, with both denominators beside it.

    Not withheld the way an outcome median is, and the difference is the point.
    An outcome median is a claim about what a screen decision produced, and one
    morning's twelve names are one observation of that. These are descriptives
    of the substitution itself, a per symbol ratio of two measured volumes, so
    the count that matters is symbols. Both counts are printed anyway, and a
    group short of either minimum is FLAGGED rather than suppressed, so a
    reader can discount it without the number being hidden from them.
    """
    if not values:
        return {"rows": 0, "sessions": len(sessions), "median": None,
                "below_minimum": True,
                "note": "no row carried the inputs this ratio needs"}
    short = []
    if len(values) < MIN_GROUP_ROWS:
        short.append(_plural(len(values), "row")
                     + f" against a {MIN_GROUP_ROWS} row minimum")
    if len(sessions) < MIN_GROUP_SESSIONS:
        short.append(_plural(len(sessions), "session")
                     + f" against a {MIN_GROUP_SESSIONS} session minimum")
    return {
        "rows": len(values),
        "sessions": len(sessions),
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "below_minimum": bool(short),
        "note": ("read this as a descriptive of the measurement and not as an "
                 "outcome: " + "; ".join(short)) if short else None,
    }


def substitution_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """The window half and the feed half, over the whole replayable population.

    Split on whether the row carries pm_volume_estimated. ROWS PUBLISHED UNDER
    A SUPERSEDED ARITHMETIC: the capture correction shipped on the evening of
    2026-08-21, so earlier rows divide a RAW socket numerator and carry a null
    pm_volume_estimated. A headline that pools the two describes a screen that
    no longer exists.
    """
    def slice_of(subset: list[dict[str, Any]], name: str, why: str) -> dict[str, Any]:
        sessions = {r["date"] for r in subset}
        out: dict[str, Any] = {"slice": name, "why": why, "rows": len(subset),
                               "sessions": len(sessions),
                               "session_dates": sorted(sessions), "factors": {}}
        for key in ("total_ratio", "window_factor", "feed_factor",
                    "baseline_factor", "collector_window_share"):
            values, seen = [], set()
            for record in subset:
                value = (record["decomposition"] or {}).get(key)
                if value is None:
                    continue
                values.append(value)
                seen.add(record["date"])
            out["factors"][key] = median_note(values, seen)
        closes = [r["decomposition"]["closes"] for r in subset
                  if (r["decomposition"] or {}).get("closes") is not None]
        residuals = [r["decomposition"]["residual"] for r in subset
                     if (r["decomposition"] or {}).get("residual") is not None]
        out["identity_checked"] = len(closes)
        out["identity_closes"] = sum(1 for c in closes if c)
        out["identity_residual_max"] = max(residuals) if residuals else None
        out["identity_tolerance"] = CLOSURE_TOLERANCE
        return out

    replayable = [r for r in records if r["decomposition"] is not None]
    pre = [r for r in replayable if r["raw"]["pm_volume_estimated"] is None]
    post = [r for r in replayable if r["raw"]["pm_volume_estimated"] is not None]
    return {
        "premarket_capture_rate_in_force": CAPTURE_RATE,
        "window_definition": {
            "published_numerator_starts": COLLECTOR_START,
            "published_denominator_starts": BASELINE_START,
            "true_numerator_starts": BASELINE_START,
            "true_denominator_starts": BASELINE_START,
            "note": ("the published ratio divides a "
                     f"{COLLECTOR_START} to cutoff numerator by a "
                     f"{BASELINE_START} to cutoff baseline, so it is bounded "
                     "below by construction and the window half of the gap is "
                     "arithmetic rather than a numerator the night contradicts"),
        },
        "all_replayable": slice_of(replayable, "all replayable rows",
                                   "every row whose session survived the run time guard"),
        "pre_capture_correction": slice_of(
            pre, "pm_volume_estimated is null",
            "published before the capture correction shipped on the evening of "
            "2026-08-21, so the numerator is the raw socket volume"),
        "post_capture_correction": slice_of(
            post, "pm_volume_estimated is present",
            "published under the shipped capture correction, which is the screen "
            "that runs today"),
    }


def outcomes_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Outcomes for the gained names, split every way that changes the answer.

    SPLIT ON fill_plausible, because an excursion measured from a level nobody
    could have transacted at is arithmetic about a price that was never
    available, and pooling the two answers a question about a tradeable name
    with rows that are not one.
    """
    gained = [r for r in records if r["state"] == "gained"]
    groups = {
        "all_gained": gained,
        "fill_plausible": [r for r in gained if r["raw"]["fill_plausible"] == "plausible"],
        "fill_implausible": [r for r in gained if r["raw"]["fill_plausible"] == "implausible"],
        "fill_unknown": [r for r in gained if r["raw"]["fill_plausible"] == "unknown"],
        "pre_capture_correction": [r for r in gained
                                   if r["raw"]["pm_volume_estimated"] is None],
        "post_capture_correction": [r for r in gained
                                    if r["raw"]["pm_volume_estimated"] is not None],
    }
    return {name: outcome_table(rows) for name, rows in groups.items()}


def counts(records: list[dict[str, Any]], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    states: dict[str, list[str]] = {}
    for record in records:
        states.setdefault(record["state"], []).append(f"{record['date']} {record['ticker']}")
    swing_moved = [f"{r['date']} {r['ticker']}" for r in records
                   if r["counterfactual"] is not None and r["baseline"] is not None
                   and r["counterfactual"]["swing_eligible"] != r["baseline"]["swing_eligible"]]
    score_up, score_down = [], []
    for record in records:
        if record["state"] in ("unresolvable", "criteria_drifted"):
            continue
        before = (record["baseline"] or {}).get("score")
        after = (record["counterfactual"] or {}).get("score")
        if before is None or after is None or before == after:
            continue
        entry = {"date": record["date"], "ticker": record["ticker"],
                 "from": before, "to": after,
                 "conviction_from": record["baseline"]["conviction"],
                 "conviction_to": record["counterfactual"]["conviction"]}
        (score_up if after > before else score_down).append(entry)
    return {
        "picks_rows": len(records),
        "sessions_seen": len(sessions),
        "sessions_resolved": sum(1 for s in sessions if s["resolved"]),
        "sessions_refused": [s["date"] for s in sessions if not s["resolved"]],
        "by_state": {k: {"rows": len(v),
                         "sessions": len(sorted({n.split(" ")[0] for n in v})),
                         "names": v}
                     for k, v in sorted(states.items())},
        "swing_moves": swing_moved,
        "swing_note": ("[Swing setup] carries no volume condition, so a swing "
                       "watchlist cannot move on this substitution. Reported "
                       "because unchanged is an answer."),
        "score_raised": score_up,
        "score_lowered": score_down,
    }


def build_payload(records: list[dict[str, Any]], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """The payload carries RAW ROWS, not only the derived tables.

    BUILD_PLAN records that the float rotation study archived percentiles, the
    fit could then not be recomputed, and the re-run cost real vendor requests.
    Every record below holds the picks columns the substitution read, the
    packet's stored verdict, both replayed verdicts and the decomposition, so
    every table in this file can be rebuilt from the file itself.
    """
    return {
        "instrument": "src/research/counterfactual_watchlist.py",
        "generated_at": ettime.now_et().isoformat(timespec="seconds"),
        "question": ("what each morning's day watchlist would have been if the "
                     "[Day setup] premarket_rvol floor had been applied to the "
                     "measured pm_rvol_true instead of to the published estimate"),
        "vendor_calls": 0,
        "criteria_read": {
            "scan.run_time": SCHEDULED_RUN_TIME,
            "day_setup.premarket_rvol": RVOL_FLOOR.describe(),
            "score_watch.min_group_rows": MIN_GROUP_ROWS,
            "score_watch.min_group_sessions": MIN_GROUP_SESSIONS,
            "collector.start_time": COLLECTOR_START,
            "collector.premarket_capture_rate": CAPTURE_RATE,
            "baseline.session_start": BASELINE_START,
        },
        "sessions": sessions,
        "counts": counts(records, sessions),
        "baseline_pass": {
            "note": ("the shipped functions replayed over each packet UNCHANGED "
                     "and compared against the packet's own stored verdict. A row "
                     "that disagrees is criteria_drifted and is held out of the "
                     "gained and lost counts, because a drifted score read as a "
                     "counterfactual reads backwards."),
            "rows_replayed": sum(1 for r in records if r["baseline"] is not None),
            "disagreements": [
                {"date": r["date"], "ticker": r["ticker"], "drift": r["drift"],
                 "would_have_been": (r["state"] if r["state"] != "criteria_drifted" else None)}
                for r in records if r["drift"] is not None],
        },
        "substitution": substitution_report(records),
        "outcomes": outcomes_report(records),
        "rows": records,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _score(value: Any) -> str:
    """A score is a small number on a 0 to 10 scale. Four decimals of it is noise."""
    if value is None:
        return "unscored"
    return f"{value:g}"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def report(payload: dict[str, Any]) -> None:
    print("")
    print("COUNTERFACTUAL WATCHLIST, the day volume floor on the measured RVOL")
    print(f"  generated {payload['generated_at']}, {payload['vendor_calls']} vendor calls")

    print("")
    print("SESSIONS")
    for session in payload["sessions"]:
        if session["resolved"]:
            print(f"  {session['date']}  resolved   packet {session['packet_candidates']:>2} "
                  f"candidates, picks {session['picks_rows']:>2} rows, "
                  f"run_time {session['run_time_et']}")
        else:
            print(f"  {session['date']}  REFUSED    picks {session['picks_rows']:>2} rows: "
                  f"{session['refusal_reason']}")

    base = payload["baseline_pass"]
    print("")
    print(f"BASELINE PASS, {base['rows_replayed']} rows replayed unchanged")
    if not base["disagreements"]:
        print("  no disagreement: every replayed verdict matches the packet's own")
    for item in base["disagreements"]:
        fields = ", ".join(f"{k} {v['stored']!r} replays {v['replayed']!r}"
                           for k, v in item["drift"]["fields"].items())
        comps = ", ".join(f"{k} {v['stored']} to {v['replayed']}"
                          for k, v in item["drift"]["components"].items())
        print(f"  {item['date']} {item['ticker']}: {fields}")
        print(f"      differing components: {comps or 'none, the totals moved without a component'}")
    print("  These rows are criteria_drifted and are EXCLUDED from gained and lost.")

    counted = payload["counts"]
    print("")
    print("WHAT THE SUBSTITUTION MOVES")
    for state, info in counted["by_state"].items():
        print(f"  {state:<17} {info['rows']:>3} rows over {info['sessions']} session(s)")
    print(f"  swing moves       {len(counted['swing_moves']):>3}. {counted['swing_note']}")
    for state in ("gained", "lost", "criteria_drifted", "unresolvable"):
        info = counted["by_state"].get(state)
        if not info:
            continue
        print(f"  {state}: {', '.join(info['names'])}")

    print("")
    print("SCORE MOVEMENT, drifted and unresolvable rows excluded")
    print(f"  raised {len(counted['score_raised'])}, lowered {len(counted['score_lowered'])}")
    for item in counted["score_raised"] + counted["score_lowered"]:
        print(f"    {item['date']} {item['ticker']:<9} {item['from']} to {item['to']} "
              f"({item['conviction_from']} to {item['conviction_to']})")

    sub = payload["substitution"]
    print("")
    print("THE SUBSTITUTION SWAPS A WINDOW, NOT ONLY A TAPE")
    print(f"  {sub['window_definition']['note']}")
    print(f"  {'slice':<26} {'rows':>5} {'sess':>5} {'total':>9} {'share':>8} "
          f"{'window':>8} {'feed':>8} {'baseline':>9}")
    for key in ("all_replayable", "pre_capture_correction", "post_capture_correction"):
        entry = sub[key]
        factors = entry["factors"]
        print(f"  {key:<26} {entry['rows']:>5} {entry['sessions']:>5} "
              f"{_fmt(factors['total_ratio']['median']):>9} "
              f"{_fmt(factors['collector_window_share']['median']):>8} "
              f"{_fmt(factors['window_factor']['median']):>8} "
              f"{_fmt(factors['feed_factor']['median']):>8} "
              f"{_fmt(factors['baseline_factor']['median']):>9}")
        print(f"      {entry['why']}")
        residual = entry["identity_residual_max"]
        print(f"      identity window x feed x baseline reproduces the total ratio on "
              f"{entry['identity_closes']} of {entry['identity_checked']} rows checked, "
              f"worst relative residual "
              f"{'none checked' if residual is None else format(residual, '.2e')}")
        for name, factor in factors.items():
            if factor["note"]:
                print(f"      {name}: {factor['note']}")
    print("  Medians do not multiply: each column is the median of its own ratio, "
          "so the three do not compose into the fourth.")

    print("")
    print("THE GAINED NAMES, ONE ROW EACH")
    print("  Printed whole because eleven rows is a sample a reader can hold, and "
          "every")
    print("  median below rests on some subset of exactly these rows.")
    print(f"    {'session':<11} {'name':<9} {'pm_rvol':>9} {'pm_rvol_true':>13}  "
          f"{'score':<13} {'fill':<12} {'mfe_true':>9} {'mae_true':>9} {'broke':>6}")
    for record in payload["rows"]:
        if record["state"] != "gained":
            continue
        raw = record["raw"]
        score = (f"{_score(record['baseline']['score'])} to "
                 f"{_score(record['counterfactual']['score'])}")
        broke = raw["pm_high_broke_next_day"]
        print(f"    {record['date']:<11} {record['ticker']:<9} "
              f"{_fmt(raw['pm_rvol']):>9} {_fmt(raw['pm_rvol_true']):>13}  "
              f"{score:<13} {str(raw['fill_plausible']):<12} "
              f"{_fmt(raw['mfe_pct_true']):>9} {_fmt(raw['mae_pct_true']):>9} "
              f"{'null' if broke is None else ('yes' if broke else 'no'):>6}")

    print("")
    print("OUTCOMES FOR THE GAINED NAMES")
    print("  mfe_pct_true is positive when the next session's high ran PAST "
          "entry_ref_true.")
    print("  mae_pct_true is NEGATIVE when the next session's low undercut "
          "stop_ref_true,")
    print("  so a positive adverse excursion means the stop reference was never "
          "breached.")
    for name, table in payload["outcomes"].items():
        print(f"  {name}: {table['rows']} rows over {table['sessions']} session(s) "
              f"{table['session_dates']}")
        for column, entry in table["columns"].items():
            level = "  DOLLAR LEVEL, a cross name median has no referent" \
                if entry["is_price_level"] else ""
            if entry["withheld"]:
                print(f"    {column:<24} filled {entry['filled_rows']:>2} over "
                      f"{entry['filled_sessions']} session(s)  WITHHELD: "
                      f"{entry['withheld_reason']}")
            else:
                extra = ""
                if "broke_count" in entry:
                    extra = (f", the premarket high broke on {entry['broke_count']} "
                             f"of {entry['filled_rows']}")
                if "reached_entry_ref_true" in entry:
                    extra = (f", the next high reached the true entry level on "
                             f"{entry['reached_entry_ref_true']} of {entry['filled_rows']}")
                if "undercut_stop_ref_true" in entry:
                    extra = (f", the next low undercut the true stop level on "
                             f"{entry['undercut_stop_ref_true']} of {entry['filled_rows']}")
                print(f"    {column:<24} filled {entry['filled_rows']:>2} over "
                      f"{entry['filled_sessions']} session(s)  median "
                      f"{_fmt(entry['median'])}{extra}{level}")

    print("")
    print("THE VERDICT IS A QUESTION, NOT A RECOMMENDATION")
    print("  Lifting data/UNVERIFIED is a threshold decision. This project has "
          "already settled")
    print("  that correcting a live screen belongs to the owner and not to the code.")
    print("  See doc/research/COUNTERFACTUAL_WATCHLIST.md for the three questions.")


def payload_path(stamp: str) -> Path:
    return config.DOC_DIR / "research" / f"counterfactual_watchlist-{stamp}.json"


def write_payload(payload: dict[str, Any], stamp: str) -> Path:
    """Write LF, and through a temp sibling, on config.ca_bundle's precedent.

    A plain write truncates before it writes, so a crash leaves a file that
    looks present and parses as nothing.
    """
    path = payload_path(stamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    text = json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n"
    temp.write_bytes(text.encode("utf-8").replace(b"\r\n", b"\n"))
    temp.replace(path)
    return path


def run(stamp: str | None = None, write: bool = True) -> dict[str, Any]:
    picks = load_picks()
    records, sessions = build_rows(picks)
    payload = build_payload(records, sessions)
    report(payload)
    if write:
        stamp = stamp or ettime.now_et().date().isoformat()
        path = write_payload(payload, stamp)
        print("")
        print(f"  payload written to {path.relative_to(config.PROJECT_ROOT)} "
              f"({path.stat().st_size:,} bytes, {len(records)} raw rows)")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the day screen on the measured premarket RVOL.")
    parser.add_argument("--date", default=None,
                        help="stamp for the payload filename, default today ET")
    parser.add_argument("--no-write", action="store_true",
                        help="print the report and write no payload")
    args = parser.parse_args(argv)
    if args.date:
        # Validated before anything runs, because the stamp becomes a FILENAME
        # and an unparsed one writes a payload nobody can date.
        try:
            dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"  --date {args.date!r} is not an ISO date such as 2026-09-01")
            return 2
    run(stamp=args.date, write=not args.no_write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
