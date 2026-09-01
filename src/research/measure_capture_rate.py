"""What the live record says [Collector] premarket_capture_rate is, guarded.

An instrument, not a pipeline step. Nothing downstream reads its output, and
this one PROPOSES NOTHING: it pairs, it guards, it archives, it reports.

    PYTHONPATH=src .venv\\Scripts\\python.exe -m research.measure_capture_rate

ZERO VENDOR CALLS. Every number below already exists on this machine. picks
carries capture_observed, written by night/true_volume.py against the Alpaca
SIP tape over the collector's OWN window, and runs/<date>/packet.json carries
the morning that produced the row. Pairing the two is arithmetic on a database
and a directory, which is the whole reason this can be re-asked as often as
anyone likes.

**What capture_observed is.** pm_volume over true_volume_socket_window: the
shares the socket recorded, divided by what the consolidated tape carried over
[Collector] start_time to the packet's own cutoff. NOT over 04:00 to the
cutoff. The socket cannot hear 04:00 to 07:20 at all, so dividing by the whole
premarket would fold the late start into a number that is meant to measure the
FEED, and the two shortfalls have two different fixes. CRITERIA's "two ratios
this writes" note records that this file used to say the wrong one.

**THE RAW MEDIAN IS CONTAMINATED AND THAT IS WHAT THE GUARDS ARE FOR.** Two
sessions in the record cannot be measurements of the feed:

  the packet the session ran on may be unusable, and research/cutoff_0830.py
  already decides that question and already names 2026-08-21's hand written
  stub with the right reason, so its sessions() is reused rather than
  reimplemented. A second copy of that judgement would drift from the first.

  the packet may record collector_window_observed.started_late_minutes above
  zero, which is 2026-08-24 at 9.0. capture_observed for such a session divides
  the socket count by an Alpaca window that begins at [Collector] start_time,
  which the socket was not listening to for nine of its minutes. Those rows
  measure a START TIME failure and the correction they would move is the FEED.

Three more guards apply per row rather than per session, and each is either an
existing CRITERIA key or a zero test:

  true_volume_socket_window below [Collector] min_capture_vendor_volume, the
  same floor scan.attach_capture_estimate puts under a per symbol share.

  capture_observed at or above 1.0, impossible for a venue subset. Not a
  threshold and not in CRITERIA for the same reason scan.py spells it inline:
  1.0 is the definition of the whole tape, not a chosen edge.

  picks.true_window disagreeing with the packet's rvol_cutoff_hhmm, which
  would mean the numerator and the denominator describe different clocks.

**WHAT CANNOT BE GUARDED, and it stays null with a reason.** [Collector]
min_capture_minutes is the third refusal scan applies to a measured share, and
the record cannot answer it. picks carries true_bars, the count of Alpaca
minutes inside the window, and nothing anywhere counts the minutes the socket
and the tape BOTH covered. A checked and empty result and a never checked one
are different states, so every row carries a null common_minutes beside the
sentence saying why, and the summary reports the guard as NOT APPLIED rather
than as passed.

**BOTH DENOMINATORS, EVERYWHERE.** Rows and sessions. Twelve names from one
morning share a tape and are one observation. Every group states both, and a
group below CRITERIA [Score watch] min_group_rows or min_group_sessions is
WITHHELD with its shortfall named, per metric, because the rows carrying a
collector_window_share are not the rows carrying a capture_observed.

**THE PAYLOAD CARRIES RAW ROWS.** Every paired row, kept or refused, with the
volumes the ratio was built from, the screen inputs the morning used, and the
liquidity key. BUILD_PLAN records what archiving percentiles cost the float
rotation study: the fit could not be recomputed and the re-run spent real
vendor requests. research/sweep_capture_rate.py is arithmetic on this file and
takes nothing else, which is only possible because the rows are here.
"""

from __future__ import annotations

import argparse
import json
import statistics
from typing import Any

from core import config
from core import criteria
from core import ettime
from core import store
from research import cutoff_0830

_CRIT = criteria.load()

SHIPPED_RATE = _CRIT.number("collector", "premarket_capture_rate")
MIN_VENDOR_VOLUME = _CRIT.number("collector", "min_capture_vendor_volume")
MIN_MINUTES = _CRIT.integer("collector", "min_capture_minutes")
MIN_GROUP_ROWS = _CRIT.integer("score_watch", "min_group_rows")
MIN_GROUP_SESSIONS = _CRIT.integer("score_watch", "min_group_sessions")

# Not a threshold and deliberately not a CRITERIA key. A socket carrying a
# subset of the venues cannot report more than all of them, so 1.0 is the
# definition of the whole tape rather than a chosen edge, which is exactly how
# scan.attach_capture_estimate spells the same refusal.
IMPOSSIBLE_SHARE = 1.0

PATH_STEM = "capture_rate_study"

MINUTES_UNRECORDED = (
    "the count of minutes the socket and the tape BOTH covered is not "
    "persisted anywhere: picks carries true_bars, which is alpaca minutes "
    "inside the window, and no column counts the intersection. [Collector] "
    f"min_capture_minutes of {MIN_MINUTES} is therefore NOT APPLIED on this "
    "record rather than passed")


# ------------------------------------------------------------------ guarding

def session_state(day: str, entry: dict[str, Any] | None,
                  refusal: str | None) -> dict[str, Any]:
    """One session's verdict, with the reason on every refusal.

    Two guards in order. cutoff_0830.sessions() first, because a packet it
    calls unusable has nothing worth reading a late start out of, and its
    reasons are already written and already argued with. Then the late start,
    which is a property of a packet that IS usable.
    """
    if refusal is not None:
        return {"day": day, "kept": False, "guard": "packet_unusable",
                "why": refusal, "cutoff_hhmm": None,
                "started_late_minutes": None}
    packet = (entry or {}).get("packet") or {}
    window = packet.get("collector_window_observed") or {}
    late = window.get("started_late_minutes")
    cutoff = packet.get("rvol_cutoff_hhmm")
    if late is None:
        return {"day": day, "kept": False, "guard": "late_start_unknown",
                "why": ("the packet carries no "
                        "collector_window_observed.started_late_minutes, so "
                        "whether the socket heard its own window is unknown "
                        "and an unmeasured start is not a clean one"),
                "cutoff_hhmm": cutoff, "started_late_minutes": None}
    if late > 0:
        return {"day": day, "kept": False, "guard": "started_late",
                "why": (f"the collector's first bar landed {late} minute(s) "
                        "after [Collector] start_time, so capture_observed "
                        "divides the socket count by an alpaca window the "
                        "socket was not listening to for part of. That is a "
                        "START TIME shortfall and this is a measurement of "
                        "the FEED"),
                "cutoff_hhmm": cutoff, "started_late_minutes": late}
    return {"day": day, "kept": True, "guard": None, "why": None,
            "cutoff_hhmm": cutoff, "started_late_minutes": late}


def row_refusals(row: dict[str, Any], cutoff: str | None) -> list[dict[str, str]]:
    """Every per row guard, all of them evaluated, none short circuited.

    A row refused twice is refused for two reasons and both are recorded. A
    first-wins list would make the second reason invisible for exactly the
    rows most worth looking at.
    """
    out: list[dict[str, str]] = []
    vendor = row.get("true_volume_socket_window")
    share = row.get("capture_observed")
    window = row.get("true_window")

    if vendor is None:
        out.append({"guard": "thin_vendor_volume", "why": (
            "the row carries no true_volume_socket_window, so the "
            "denominator of the share is unknown")})
    elif vendor < MIN_VENDOR_VOLUME:
        out.append({"guard": "thin_vendor_volume", "why": (
            f"it rested on {vendor:,.0f} tape share(s) over the socket's own "
            f"window, under the [Collector] min_capture_vendor_volume floor "
            f"of {MIN_VENDOR_VOLUME:,.0f}")})

    if share is None:
        out.append({"guard": "impossible_share", "why": (
            "the row carries no capture_observed")})
    elif share >= IMPOSSIBLE_SHARE:
        out.append({"guard": "impossible_share", "why": (
            f"it came out at {share:.4f}, and a socket carrying a subset of "
            "the venues cannot report all of the tape")})

    if not window:
        out.append({"guard": "window_disagreement", "why": (
            "the row carries no true_window, so what it measured over cannot "
            "be checked against the morning's own cutoff")})
    elif cutoff is None:
        out.append({"guard": "window_disagreement", "why": (
            "the packet carries no rvol_cutoff_hhmm to check the row's "
            f"true_window {window} against")})
    elif str(window).rsplit("-", 1)[-1] != cutoff:
        out.append({"guard": "window_disagreement", "why": (
            f"the row measured {window} and the morning screened to {cutoff}, "
            "so the numerator and the denominator describe different clocks")})
    return out


# ----------------------------------------------------------------- reporting

def group(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """rows, sessions and the median, or a withholding that says how short.

    Per METRIC, not per group: the rows carrying a collector_window_share are
    not the rows carrying a capture_observed, so each field counts its own.
    """
    values = [(r["date"], r[field]) for r in rows if r.get(field) is not None]
    sessions = sorted({day for day, _ in values})
    short_rows = MIN_GROUP_ROWS - len(values)
    short_sessions = MIN_GROUP_SESSIONS - len(sessions)
    block: dict[str, Any] = {
        "metric": field,
        "rows": len(values),
        "sessions": len(sessions),
        "session_dates": sessions,
        "median": None,
        "withheld": short_rows > 0 or short_sessions > 0,
        "withheld_why": None,
    }
    if block["withheld"]:
        parts = []
        if short_rows > 0:
            parts.append(f"{short_rows} row(s) short of [Score watch] "
                         f"min_group_rows {MIN_GROUP_ROWS}")
        if short_sessions > 0:
            parts.append(f"{short_sessions} session(s) short of [Score watch] "
                         f"min_group_sessions {MIN_GROUP_SESSIONS}")
        block["withheld_why"] = " and ".join(parts)
        return block
    block["median"] = round(statistics.median(v for _, v in values), 6)
    return block


def per_symbol_medians(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The shipped estimator's own unit, one median per symbol.

    CRITERIA's "Why 0.1172 rather than 0.0923" argument is that the question
    is what share to assume for ONE symbol nothing has been measured for, so
    the estimator is the median of the per symbol rates and not the volume
    weighted aggregate. 0.1172 is that estimator over 110 symbols on the
    2026-08-21 payload, and reproducing it is what makes this comparable.
    """
    by_symbol: dict[str, list[float]] = {}
    for row in rows:
        if row.get("capture_observed") is None:
            continue
        by_symbol.setdefault(row["ticker"], []).append(row["capture_observed"])
    return {
        "symbols": len(by_symbol),
        "observations_per_symbol": {
            str(n): sum(1 for v in by_symbol.values() if len(v) == n)
            for n in sorted({len(v) for v in by_symbol.values()})},
        "medians": {sym: round(statistics.median(v), 6)
                    for sym, v in sorted(by_symbol.items())},
    }


def weighted_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The other estimator, kept beside the first because CRITERIA argues them.

    The volume weighted aggregate answers "what share of the total tape did
    the socket hear", which is a different question from the one the screen
    asks. It is reported so the two can be read against each other and against
    the 0.1172 versus 0.0923 pair the shipped note argues over.
    """
    usable = [r for r in rows
              if r.get("capture_observed") is not None
              and r.get("pm_volume") is not None
              and r.get("true_volume_socket_window")]
    if not usable:
        return {"rows": 0, "sessions": 0, "value": None,
                "why": "no row carries both volumes"}
    socket = sum(r["pm_volume"] for r in usable)
    tape = sum(r["true_volume_socket_window"] for r in usable)
    return {
        "rows": len(usable),
        "sessions": len({r["date"] for r in usable}),
        "socket_shares": round(socket, 2),
        "tape_shares_over_the_socket_window": round(tape, 2),
        "value": round(socket / tape, 6) if tape else None,
        "why": None,
    }


def residual(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The shortfall NO divisor reaches, printed beside the one that a divisor does.

    capture_observed corrects the FEED: what the socket missed of the minutes
    it was listening to. collector_window_share is the OTHER shortfall, the
    tape over 07:20 to the cutoff as a share of 04:00 to the cutoff, and no
    capture rate touches it. The composite below multiplies the two: what the
    socket carried of the WHOLE premarket window. Raising the capture rate
    cannot move that number, because the minutes are not missing from the
    sample, they are missing from the recording.
    """
    full = [r for r in rows
            if r.get("pm_volume") is not None and r.get("pm_volume_true")]
    socket = sum(r["pm_volume"] for r in full)
    tape = sum(r["pm_volume_true"] for r in full)
    return {
        "collector_window_share": group(rows, "collector_window_share"),
        "composite_socket_share_of_the_full_premarket": {
            "rows": len(full),
            "sessions": len({r["date"] for r in full}),
            "socket_shares": round(socket, 2),
            "tape_shares_over_the_full_window": round(tape, 2),
            "value": round(socket / tape, 6) if tape else None,
            "basis": ("pm_volume over pm_volume_true, so the denominator is "
                      "the whole premarket the baseline accumulates over and "
                      "not the window the socket was awake for"),
        },
    }


# ---------------------------------------------------------------- collection

def picks_rows() -> list[dict[str, Any]]:
    """Every live row the truth pass has written a capture share for.

    READS ONLY. Nothing in research writes to picks; morning/scan.py owns that
    table and night/paper_ledger.py owns the other one.
    """
    with store.session() as connection:
        store.init(connection)
        return [dict(row) for row in connection.execute(
            "SELECT date, ticker, capture_observed, true_volume_socket_window, "
            "collector_window_share, pm_volume, pm_volume_true, true_bars, "
            "true_window, truth_source, truth_at, pm_rvol, pm_capture_share, "
            "pm_capture_basis, day_eligible "
            "FROM picks WHERE source='live' AND capture_observed IS NOT NULL "
            "ORDER BY date, ticker")]


def packet_fields(candidate: dict[str, Any] | None) -> dict[str, Any]:
    """The morning's own screen inputs for one name, carried into the payload.

    The sweep re-asks the day screen question and may not read a packet, so
    everything it needs to answer it travels here: the liquidity key, the RVOL
    denominator, the share the morning actually divided by, and the OTHER
    conditions' verdicts. Those verdicts are scan.py's own and are not
    recomputed: a capture rate cannot move a market cap or a prior high, and
    re-implementing four screens to leave them unchanged is how a research
    file starts disagreeing with production.
    """
    if candidate is None:
        return {
            "avg_volume_20d": None,
            "avg_volume_20d_reason": ("no candidate with this symbol survives "
                                      "in the packet for this session"),
            "baseline_median": None,
            "baseline_sessions_used": None,
            "baseline_computed_at": None,
            "baseline_age_days": None,
            "pm_volume_packet": None,
            "pm_rvol_packet": None,
            "pm_rvol_reason": None,
            "pm_capture_share_packet": None,
            "pm_capture_basis_packet": None,
            "day_eligible_packet": None,
            "day_failed_conditions": None,
            "day_failed_unmeasured": None,
            "on_watchlist": None,
        }
    baseline = candidate.get("baseline") or {}
    volume = candidate.get("avg_volume_20d")
    return {
        "avg_volume_20d": volume,
        "avg_volume_20d_reason": (None if volume is not None else
                                  "the packet candidate carries no "
                                  "avg_volume_20d"),
        "baseline_median": baseline.get("median_volume"),
        "baseline_sessions_used": baseline.get("sessions_used"),
        "baseline_computed_at": baseline.get("computed_at"),
        "baseline_age_days": baseline.get("age_days"),
        "pm_volume_packet": candidate.get("pm_volume"),
        "pm_rvol_packet": candidate.get("pm_rvol"),
        "pm_rvol_reason": candidate.get("pm_rvol_reason"),
        "pm_capture_share_packet": candidate.get("pm_capture_share"),
        "pm_capture_basis_packet": candidate.get("pm_capture_basis"),
        "day_eligible_packet": candidate.get("day_eligible"),
        "day_failed_conditions": candidate.get("day_failed_conditions"),
        "day_failed_unmeasured": candidate.get("day_failed_unmeasured"),
        "on_watchlist": candidate.get("on_watchlist"),
    }


def collect() -> dict[str, Any]:
    """Pair picks against packets, guard both, and keep every refusal."""
    usable, refused = cutoff_0830.sessions()
    by_day = {entry["day"]: entry for entry in usable}
    refusal_by_day = {entry["day"]: entry["why"] for entry in refused}

    rows = picks_rows()
    days = sorted({row["date"] for row in rows})

    sessions: list[dict[str, Any]] = []
    for day in days:
        if day in by_day:
            state = session_state(day, by_day[day], None)
        elif day in refusal_by_day:
            state = session_state(day, None, refusal_by_day[day])
        else:
            state = session_state(day, None, (
                "there is no run directory for this session at all, so the "
                "morning that produced these rows cannot be read"))
        state["rows"] = sum(1 for row in rows if row["date"] == day)
        sessions.append(state)
    state_by_day = {s["day"]: s for s in sessions}

    out: list[dict[str, Any]] = []
    for row in rows:
        state = state_by_day[row["date"]]
        entry = by_day.get(row["date"])
        packet = (entry or {}).get("packet") or {}
        candidate = None
        for item in packet.get("candidates") or []:
            if item.get("symbol") == row["ticker"]:
                candidate = item
                break
        fields = packet_fields(candidate)

        socket = row["pm_volume"]
        source = "picks.pm_volume"
        if socket is None:
            socket = fields["pm_volume_packet"]
            source = ("packet candidate pm_volume, because picks began "
                      "carrying the column after this session")
        if socket is None:
            source = ("neither picks nor the packet carries the morning's "
                      "socket volume for this row")

        refusals = row_refusals(row, state["cutoff_hhmm"])
        record = {
            "date": row["date"],
            "ticker": row["ticker"],
            "session_kept": state["kept"],
            "session_guard": state["guard"],
            "capture_observed": row["capture_observed"],
            "pm_volume": socket,
            "pm_volume_source": source,
            "true_volume_socket_window": row["true_volume_socket_window"],
            "pm_volume_true": row["pm_volume_true"],
            "collector_window_share": row["collector_window_share"],
            "true_bars": row["true_bars"],
            "true_window": row["true_window"],
            "packet_cutoff_hhmm": state["cutoff_hhmm"],
            "truth_source": row["truth_source"],
            "truth_at": row["truth_at"],
            "common_minutes": None,
            "common_minutes_reason": MINUTES_UNRECORDED,
            "pm_rvol_picks": row["pm_rvol"],
            "pm_capture_share_picks": row["pm_capture_share"],
            "pm_capture_basis_picks": row["pm_capture_basis"],
            "day_eligible_picks": row["day_eligible"],
            "row_refusals": refusals,
            "kept": state["kept"] and not refusals,
        }
        record.update(fields)
        out.append(record)

    for state in sessions:
        state["rows_kept"] = sum(
            1 for r in out if r["date"] == state["day"] and r["kept"])
        state["rows_refused"] = state["rows"] - state["rows_kept"]
    return {"sessions": sessions, "rows": out}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Every descriptive number this instrument is willing to state."""
    kept = [r for r in rows if r["kept"]]
    # Split by whether the SESSION already stood, because "twelve rows failed
    # a row guard" reads as twelve names cut from the fit set, and a row guard
    # firing inside a session that was refused whole cut nothing. Both counts
    # are kept: a guard that fires only where the session is already gone is
    # a guard nothing has yet tested on live data, and that is worth knowing.
    in_live: dict[str, int] = {}
    in_refused: dict[str, int] = {}
    for row in rows:
        target = in_live if row["session_kept"] else in_refused
        for refusal in row["row_refusals"]:
            target[refusal["guard"]] = target.get(refusal["guard"], 0) + 1
    guards = {
        "inside_sessions_that_stood": in_live,
        "inside_sessions_already_refused": in_refused,
    }
    return {
        "all_rows_contaminated": {
            "note": ("every paired row, guards NOT applied. Reported because "
                     "it is the number a reader takes off the table without "
                     "the guards, and the whole point is the distance between "
                     "this and the line below"),
            "capture_observed": group(rows, "capture_observed"),
        },
        "guarded_fit_set": {
            "note": ("sessions and rows that survive every guard. This is the "
                     "set any re-derivation would be fitted on"),
            "capture_observed": group(kept, "capture_observed"),
            "per_symbol": per_symbol_medians(kept),
            "median_of_per_symbol_medians": _median_of_medians(kept),
            "volume_weighted_aggregate": weighted_aggregate(kept),
        },
        "row_guard_counts": guards,
        "guards_not_applied": [
            {"guard": "min_capture_minutes", "why": MINUTES_UNRECORDED}],
        "residual_no_divisor_closes": residual(kept),
    }


def _median_of_medians(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The shipped estimator, with BOTH denominators and the withholding rule.

    The unit is the SYMBOL here and the session count is still reported,
    because a per symbol estimator computed off one morning is one observation
    wearing a larger number exactly as much as a per row one is.
    """
    per = per_symbol_medians(rows)
    sessions = sorted({r["date"] for r in rows
                       if r.get("capture_observed") is not None})
    short_rows = MIN_GROUP_ROWS - per["symbols"]
    short_sessions = MIN_GROUP_SESSIONS - len(sessions)
    block: dict[str, Any] = {
        "estimator": ("median over symbols of that symbol's median share, "
                      "which is CRITERIA's own recipe for 0.1172"),
        "symbols": per["symbols"],
        "sessions": len(sessions),
        "value": None,
        "withheld": short_rows > 0 or short_sessions > 0,
        "withheld_why": None,
    }
    if block["withheld"]:
        parts = []
        if short_rows > 0:
            parts.append(f"{short_rows} symbol(s) short of [Score watch] "
                         f"min_group_rows {MIN_GROUP_ROWS}")
        if short_sessions > 0:
            parts.append(f"{short_sessions} session(s) short of [Score watch] "
                         f"min_group_sessions {MIN_GROUP_SESSIONS}")
        block["withheld_why"] = " and ".join(parts)
        return block
    block["value"] = round(
        statistics.median(per["medians"].values()), 6)
    return block


# ------------------------------------------------------------------ printing

def _line(block: dict[str, Any], label: str) -> str:
    if block.get("withheld"):
        return f"  {label:<38} WITHHELD, {block['withheld_why']}"
    value = block.get("median", block.get("value"))
    rows = block.get("rows", block.get("symbols"))
    unit = "rows" if "rows" in block else "symbols"
    return (f"  {label:<38} {value:>9.6f}   {rows:>3} {unit}, "
            f"{block['sessions']} sessions")


def report(payload: dict[str, Any]) -> None:
    print("measure_capture_rate: zero vendor calls, this is arithmetic on "
          "picks and runs/")
    print(f"\nshipped [Collector] premarket_capture_rate = {SHIPPED_RATE}, "
          f"and this instrument MOVES NOTHING\n")

    print("sessions")
    for state in payload["sessions"]:
        verdict = "kept    " if state["kept"] else "REFUSED "
        print(f"  {verdict}{state['day']}  {state['rows']:>2} row(s), "
              f"{state['rows_kept']:>2} kept")
        if not state["kept"]:
            print(f"            {state['guard']}: {state['why']}")

    summary = payload["summary"]
    print("\ncapture_observed")
    print(_line(summary["all_rows_contaminated"]["capture_observed"],
                "raw median, guards NOT applied"))
    print(_line(summary["guarded_fit_set"]["capture_observed"],
                "guarded median"))
    print(_line(summary["guarded_fit_set"]["median_of_per_symbol_medians"],
                "median of per symbol medians"))
    aggregate = summary["guarded_fit_set"]["volume_weighted_aggregate"]
    if aggregate["value"] is None:
        print(f"  {'volume weighted aggregate':<38} unavailable, "
              f"{aggregate['why']}")
    else:
        print(f"  {'volume weighted aggregate':<38} "
              f"{aggregate['value']:>9.6f}   {aggregate['rows']:>3} rows, "
              f"{aggregate['sessions']} sessions")

    print("\nrow guards")
    for where, label in (("inside_sessions_that_stood",
                          "inside sessions that stood"),
                         ("inside_sessions_already_refused",
                          "inside sessions already refused")):
        counts = summary["row_guard_counts"][where]
        if not counts:
            print(f"  {label}: none fired. CHECKED AND EMPTY, which is not "
                  "the same state as never checked")
            continue
        print(f"  {label}")
        for guard, count in sorted(counts.items()):
            print(f"    {guard:<36} {count:>3} row(s)")
    for skipped in summary["guards_not_applied"]:
        print(f"  NOT APPLIED {skipped['guard']}: {skipped['why']}")

    residuals = summary["residual_no_divisor_closes"]
    print("\nthe residual no divisor closes")
    print(_line(residuals["collector_window_share"],
                "median collector_window_share"))
    composite = residuals["composite_socket_share_of_the_full_premarket"]
    if composite["value"] is not None:
        print(f"  {'composite socket share, full window':<38} "
              f"{composite['value']:>9.6f}   {composite['rows']:>3} rows, "
              f"{composite['sessions']} sessions")
    print("  the capture rate corrects the FEED. The window shortfall above "
          "is a start time")
    print("  question with a different fix, and no divisor reaches it.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-derive the capture rate from the live record, offline.")
    parser.add_argument("--out", default=None,
                        help="where to write the payload; defaults to "
                             f"doc/research/{PATH_STEM}-<today>.json")
    parser.add_argument("--no-write", action="store_true",
                        help="report and archive nothing")
    args = parser.parse_args(argv)

    collected = collect()
    payload: dict[str, Any] = {
        "generated_at": ettime.stamp(ettime.now_et()),
        "instrument": "research.measure_capture_rate",
        "vendor_calls": 0,
        "proposes": ("nothing. This file measures and archives. See the "
                     "report for the one line an owner would change and when"),
        "shipped": {
            "premarket_capture_rate": SHIPPED_RATE,
            "min_capture_vendor_volume": MIN_VENDOR_VOLUME,
            "min_capture_minutes": MIN_MINUTES,
            "collector_start_time": _CRIT.clock_text("collector", "start_time"),
            "collector_stop_time": _CRIT.clock_text("collector", "stop_time"),
            "baseline_session_start": _CRIT.clock_text("baseline",
                                                       "session_start"),
            "day_screen_rvol_floor": _CRIT.rule("day_setup",
                                                "premarket_rvol").describe(),
            "truth_baseline_sessions": _CRIT.integer("truth",
                                                     "baseline_sessions"),
            "score_watch_min_group_rows": MIN_GROUP_ROWS,
            "score_watch_min_group_sessions": MIN_GROUP_SESSIONS,
        },
        "sessions": collected["sessions"],
        "rows": collected["rows"],
    }
    payload["summary"] = summarise(collected["rows"])
    report(payload)

    if args.no_write:
        print("\nmeasure_capture_rate: --no-write, nothing archived")
        return 0
    out = (config.DOC_DIR / "research" /
           f"{PATH_STEM}-{ettime.today_et().isoformat()}.json"
           if args.out is None else config.PROJECT_ROOT / args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" explicitly. Line endings in this repository are PER FILE and
    # everything new under doc/research/ is LF; the default on Windows would
    # translate to CRLF and the file would land disagreeing with its own
    # directory the moment it was created.
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8",
                   newline="\n")
    print(f"\nmeasure_capture_rate: wrote {out}, "
          f"{len(collected['rows'])} raw row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
