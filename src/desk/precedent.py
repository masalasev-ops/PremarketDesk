"""What happened the last time a name looked like this one.

THE ONE THING THIS MODULE IS. For each candidate a morning published, it finds
the past reconstructed candidates that match it on six conditions and reports
what those did. It is a COUNT OF THE PAST. It is not a forecast, it carries no
interval, and no caller may phrase it as one.

The match rule, the widening ladder, the floors and the confounds are
pre-registered in doc/research/PRECEDENT_PREREGISTRATION.md. That file was
written before this module had a reader and before research_outcomes held a
row. Changing a band edge is an amendment there, not an edit to CRITERIA on
its own, and the reason is the failure this whole feature exists to avoid:
choosing the bands after seeing which bands make the desk look good.

THE POPULATION IS RECONSTRUCTED ROWS AND ONLY THOSE. research_outcomes holds
sessions the desk did not run, produced by replaying the shipped screen on a
real tape. The live record is 43 rows over four sessions and is read by the
Record screen alone. Mixing them would corrupt the year and say nothing about
the four. Every SELECT here is against research_outcomes, which holds no live
row by construction, so the fence is the table and not a WHERE clause that
somebody could forget.

WHAT THIS MODULE MAY NOT DO, and why each one is a rule rather than a habit.

  No grouping by score or conviction. Both are NULL on every reconstructed row
  because the catalyst class needs EODHD news tags the session cache does not
  hold. A calibration line saying what GREEN has been worth cannot be computed
  from this population, and the drawn design carried one until the
  pre-registration was written. It was removed rather than approximated.

  No number over fewer sessions than [Precedent] min_sessions. Twelve names
  published on one morning share that morning's market and are one
  observation. A group of 200 rows over 9 mornings is nine observations
  wearing a large label, and printing a median for it is the mistake that
  makes the whole screen worthless.

  No silent widening. A group that only qualified after conditions were
  dropped says which ones, every time it is drawn.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from core import criteria, lookalike, store
from night import paper_ledger

_CRIT = criteria.load()

# The four conditions the ladder may drop, mapped to the column each one
# filters. Earnings and the gap band are absent on purpose: they are never
# dropped, and leaving them out of this map is what makes that structural
# rather than a check somebody could remove.
_DROPPABLE = {
    "cap_band": "cap_band",
    "price_band": "price_band",
    "above_prior_high": "above_prior_high",
    "rvol_band": "rvol_band",
}

# Said on the screen wherever a count is drawn, because a reader cannot see
# the universe file that produced it. data/universe.json is TODAY'S universe,
# so a name delisted during the replayed year is not in the past this counted.
SURVIVORSHIP = ("the replayed universe is today's, so names that delisted "
                "during the year are absent and every count here reads high")


def rule_version() -> str:
    """The paper rule these counts were simulated under.

    The lowest version, which is record_so_far's own convention. A screen that
    silently drew from whichever version happened to sort last would change
    what it was showing when a new sizing mode was added.
    """
    return sorted(paper_ledger.rule_versions())[0]


def conditions_for(candidate: dict[str, Any]) -> dict[str, Any]:
    """The six match conditions for one compacted candidate.

    Reads the compacted shape (desk/compact.compact_session) rather than a
    picks row, because that is what the desk carries and re-reading the
    database at render time would make the screen depend on a table the
    published file is supposed to have replaced.

    A condition whose input was never measured is None, and a None never
    matches. An unmeasured RVOL is not an RVOL of zero and must not join a
    group of names that were measured.
    """
    cap = candidate.get("mcap")
    cap_musd = (cap / 1_000_000.0) if isinstance(cap, (int, float)) else None
    price = candidate.get("price")
    prior_high = candidate.get("prior_high")
    above = None
    if isinstance(price, (int, float)) and isinstance(prior_high, (int, float)):
        above = 1 if price > prior_high else 0
    cut = lookalike.bands_for(
        candidate.get("gap"), candidate.get("rvol"), price, cap_musd)
    # TRI-STATE, and it was a boolean over the wrong question until 2026-09-05.
    # compact carries earn_overnight, computed by core/lookalike from the same
    # rule selection/discover tiers the pool with. Reading the raw earnings
    # membership instead treated a name that reported before the PREVIOUS
    # morning's open as one that reported overnight: NIO.US on 2026-09-02,
    # report_date 2026-09-01 BeforeMarket, was stamped 1 and matched against
    # names that genuinely reported between the last close and this open.
    #
    # None means the calendar was never read. It is not a zero, and match()
    # withholds the whole group rather than guessing, because this is the one
    # condition the widening ladder may never drop.
    overnight = candidate.get("earn_overnight")
    return {
        "earnings_overnight": (None if overnight is None else int(bool(overnight))),
        "gap_band": cut["gap_band"],
        "rvol_band": cut["rvol_band"],
        "price_band": cut["price_band"],
        "cap_band": cut["cap_band"],
        "above_prior_high": above,
    }


UNREAD_EARNINGS = ("the earnings calendar was never read for this session, so "
                   "whether the name reported overnight is unknown, and that is "
                   "the one condition the match may never drop")


def in_words(conditions: dict[str, Any], dropped: list[str]) -> list[str]:
    """The match rule as a reader sees it, dropped conditions removed.

    Printed in full under every group. The rule is the one place this feature
    could quietly deceive somebody, so it is never behind a control.
    """
    out: list[str] = []
    if "earnings_overnight" not in dropped:
        overnight = conditions.get("earnings_overnight")
        out.append("earnings calendar not read" if overnight is None
                   else "reported overnight" if overnight
                   else "did not report overnight")
    if conditions.get("gap_band") and "gap_band" not in dropped:
        # The band already carries its direction as a word, so this reads
        # "gap up 6% to 8%" rather than naming the direction twice.
        out.append(f"gap {conditions['gap_band']}")
    if conditions.get("rvol_band") and "rvol_band" not in dropped:
        out.append(f"volume {conditions['rvol_band']} normal")
    if conditions.get("above_prior_high") is not None and "above_prior_high" not in dropped:
        out.append("above yesterday's high" if conditions["above_prior_high"]
                   else "below yesterday's high")
    if conditions.get("price_band") and "price_band" not in dropped:
        out.append(f"price {conditions['price_band']}")
    if conditions.get("cap_band") and "cap_band" not in dropped:
        out.append(f"market value {conditions['cap_band']}")
    return out


def _select(connection: sqlite3.Connection, conditions: dict[str, Any],
            dropped: list[str], version: str) -> list[dict[str, Any]]:
    where = ["rule_version = ?"]
    params: list[Any] = [version]
    for column, value in conditions.items():
        if column in dropped:
            continue
        if value is None:
            # An unmeasured condition cannot be matched on. It is dropped from
            # the conjunction rather than compared to NULL, which in SQL
            # matches nothing and would silently empty every group.
            continue
        where.append(f"{column} = ?")
        params.append(value)
    # skip_reason IS NULL, which is what keeps an UNGRADED row out of the
    # denominator. The engine writes booked NULL with a reason when a name had
    # no entry reference or no bars, and the screen's headline figure is "how
    # many of this shape reached the buy". A row nobody could measure is not a
    # row that failed to trigger, and counting it as one reads the base rate
    # low by exactly the number of names that were never measurable.
    where.append("skip_reason IS NULL")
    sql = ("SELECT date, booked, pnl_pct, minutes_to_peak FROM research_outcomes "
           "WHERE " + " AND ".join(where))
    return [dict(row) for row in connection.execute(sql, params)]


def _percentile(values: list[float], q: float) -> float | None:
    """Linear interpolation between order statistics. None on an empty list.

    Written out rather than taken from statistics.quantiles, which needs at
    least two points and raises on one. A group of exactly one booked row is a
    real state here and it should degrade to that row, not to an exception.
    """
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The printed figures for one matched group, or the reason there are none.

    A row that never reached its entry is KEPT in the denominator and excluded
    from every result figure. "How often did this shape become a trade at all"
    is half the answer and dropping those rows would delete it.
    """
    sessions = {r["date"] for r in rows}
    booked = [r for r in rows if r.get("booked")]
    returns = [float(r["pnl_pct"]) for r in booked if r.get("pnl_pct") is not None]
    peaks = [int(r["minutes_to_peak"]) for r in booked
             if r.get("minutes_to_peak") is not None]
    out: dict[str, Any] = {
        "rows": len(rows), "sessions": len(sessions),
        "reached": len(booked),
        "median": None, "up": None, "p25": None, "p75": None,
        "worst": None, "best": None, "peak": None,
    }
    if returns:
        out["median"] = round(_percentile(returns, 0.5), 4)
        out["p25"] = round(_percentile(returns, 0.25), 4)
        out["p75"] = round(_percentile(returns, 0.75), 4)
        out["worst"] = round(min(returns), 4)
        out["best"] = round(max(returns), 4)
        out["up"] = sum(1 for v in returns if v > 0)
    if peaks:
        out["peak"] = int(_percentile(sorted(peaks), 0.5))
    return out


def match(connection: sqlite3.Connection, conditions: dict[str, Any],
          version: str | None = None) -> dict[str, Any]:
    """One candidate's group, widened by the ladder only as far as it must be.

    The ladder is walked in the CRITERIA order, one drop at a time, re-counting
    after each and stopping at the first count that clears BOTH floors. A group
    that never clears them is withheld and says what it reached, because a
    withheld group is a result and not an absence.
    """
    version = version or rule_version()
    min_rows = _CRIT.integer("precedent", "min_rows")
    min_sessions = _CRIT.integer("precedent", "min_sessions")
    ladder = [c.strip() for c in _CRIT.text_list("precedent", "widen_order")]
    max_steps = _CRIT.integer("precedent", "max_widen_steps")

    unknown = [c for c in ladder if c not in _DROPPABLE]
    if unknown:
        raise ValueError(
            f"CRITERIA [Precedent] widen_order names {unknown}, which is not a "
            f"droppable condition. The four that may be dropped are "
            f"{sorted(_DROPPABLE)}; earnings and the gap band never are")

    if conditions.get("earnings_overnight") is None:
        return {
            "held": True, "widened": [], "version": version,
            "matched_on": in_words(conditions, []),
            "floors": {"rows": min_rows, "sessions": min_sessions},
            "rows": 0, "sessions": 0, "reached": None, "median": None,
            "up": None, "p25": None, "p75": None, "worst": None, "best": None,
            "peak": None, "why": UNREAD_EARNINGS,
        }

    dropped: list[str] = []
    attempts: list[dict[str, Any]] = []
    for step in range(min(max_steps, len(ladder)) + 1):
        rows = _select(connection, conditions, dropped, version)
        stats = summarise(rows)
        attempts.append({"dropped": list(dropped), "rows": stats["rows"],
                         "sessions": stats["sessions"]})
        if stats["rows"] >= min_rows and stats["sessions"] >= min_sessions:
            return {
                "held": False, "widened": list(dropped), "version": version,
                "matched_on": in_words(conditions, dropped),
                "floors": {"rows": min_rows, "sessions": min_sessions},
                **stats,
            }
        if step == min(max_steps, len(ladder)):
            break
        dropped.append(ladder[step])

    last = attempts[-1]
    return {
        "held": True, "widened": list(dropped), "version": version,
        # The NARROW rule, not the one the exhausted ladder ended on. A held
        # group has no count, so what the reader wants from the row is what it
        # would have been matched on, and printing the fully widened rule
        # would show a rule that produced nothing either.
        "matched_on": in_words(conditions, []),
        "floors": {"rows": min_rows, "sessions": min_sessions},
        "rows": last["rows"], "sessions": last["sessions"],
        "reached": None, "median": None, "up": None,
        "p25": None, "p75": None, "worst": None, "best": None, "peak": None,
        "why": (f"{last['rows']} matching row(s) over {last['sessions']} "
                f"session(s), against floors of {min_rows} and {min_sessions}"),
    }


def peak_buckets(connection: sqlite3.Connection,
                 version: str | None = None) -> list[dict[str, Any]]:
    """How the population ended, split by how long it took to reach its high.

    The buckets are [Precedent] peak_minutes_buckets and they are NEW TO THIS
    SCREEN. They do not line up with the Record screen: record_so_far computes
    two, minutes_to_peak <= 10 and >= 100, and these are five with a 120 line
    and no 100 line, and even the shared 10 disagrees because Record's is
    inclusive and the bucketing here is strictly less than. Said here because
    the docstring claimed the opposite until 2026-09-05, and a reader who
    believed it would have compared this screen's slowest bucket against
    Record's "peaked after 100 minutes" count as though they were one split.
    """
    version = version or rule_version()
    edges = [int(x) for x in _CRIT.text_list("precedent", "peak_minutes_buckets")]
    rows = [dict(r) for r in connection.execute(
        "SELECT date, pnl_pct, minutes_to_peak FROM research_outcomes "
        "WHERE rule_version = ? AND booked = 1 AND pnl_pct IS NOT NULL "
        "AND minutes_to_peak IS NOT NULL", (version,))]
    # "and up" rather than "over", because a value ON an edge belongs to the
    # band above it and the last bucket therefore CONTAINS its edge. A label
    # reading "over 120" on a bucket holding exactly 120 is a small lie in the
    # one place a reader checks the arithmetic.
    labels = ([f"under {edges[0]}"] +
              [f"{low} to {high}" for low, high in zip(edges, edges[1:])] +
              [f"{edges[-1]} and up"])
    buckets: list[list[dict[str, Any]]] = [[] for _ in labels]
    for row in rows:
        minutes = int(row["minutes_to_peak"])
        index = len(edges)
        for position, edge in enumerate(edges):
            if minutes < edge:
                index = position
                break
        buckets[index].append(row)
    min_sessions = _CRIT.integer("precedent", "min_sessions")
    min_rows = _CRIT.integer("precedent", "min_rows")
    out = []
    for label, group in zip(labels, buckets):
        stats = summarise([{**r, "booked": 1} for r in group])
        # BOTH floors, as the pre-registration says, and only the session one
        # was applied until 2026-09-05. A bucket of eleven trades spread over
        # twenty five mornings cleared the session floor and printed a median
        # over eleven trades.
        held = stats["sessions"] < min_sessions or stats["rows"] < min_rows
        out.append({"label": label, "held": held, "rows": stats["rows"],
                    "sessions": stats["sessions"],
                    "median": None if held else stats["median"],
                    "p25": None if held else stats["p25"],
                    "p75": None if held else stats["p75"],
                    "worst": None if held else stats["worst"],
                    "best": None if held else stats["best"]})
    return out


def coverage(connection: sqlite3.Connection,
             version: str | None = None) -> dict[str, Any]:
    """How much replayed history exists at all, for the screen's empty state.

    A screen that renders nothing when a table is empty is a screen that looks
    broken. This is what it prints instead, and it names the command that fills
    the table rather than leaving the reader to find it.
    """
    version = version or rule_version()
    row = connection.execute(
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT date) AS sessions, "
        "MIN(date) AS first, MAX(date) AS last, "
        "SUM(CASE WHEN booked = 1 THEN 1 ELSE 0 END) AS reached "
        "FROM research_outcomes WHERE rule_version = ? "
        "AND skip_reason IS NULL", (version,)).fetchone()
    return {
        "rows": row["rows"] or 0, "sessions": row["sessions"] or 0,
        "reached": row["reached"] or 0,
        "first": row["first"], "last": row["last"], "version": version,
        "command": "python -m research.replay_outcomes --fetch --all "
                   "then --evaluate --all",
        "survivorship": SURVIVORSHIP,
    }


def build(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the Precedent screen draws for one session.

    Returns a payload even when research_outcomes is empty, because the empty
    state is a state the screen renders and not an error it raises. compact
    calls this once a session and the result is frozen with the rest, so the
    published file carries its own answers and the screen reads no database.
    """
    with store.session() as connection:
        store.init(connection)
        cover = coverage(connection)
        version = cover["version"]
        names = []
        for candidate in candidates:
            conditions = conditions_for(candidate)
            group = match(connection, conditions, version)
            names.append({"sym": candidate.get("sym"),
                          "name": candidate.get("name"),
                          "conditions": conditions, **group})
        buckets = peak_buckets(connection, version) if cover["rows"] else []
    return {"coverage": cover, "names": names, "peaks": buckets}
