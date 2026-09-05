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
SURVIVORSHIP = ("The replayed universe is today's, so names that delisted "
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
            dropped: list[str], version: str,
            eligible: int | None = None) -> list[dict[str, Any]]:
    where = ["rule_version = ?"]
    params: list[Any] = [version]
    # THE POPULATION IS EVERY REPLAYED CANDIDATE, and the day screen's verdict
    # is deliberately NOT a filter on it. This defaulted to day_eligible = 1
    # for part of 2026-09-05 and that was a population error, caught before any
    # figure was drawn from it: the list this screen sits beside is the RANKED
    # candidates, published with an entry and a stop whether or not they
    # cleared the day screen, and on the four live sessions on file only 0, 0,
    # 3 and 2 of twelve did. Matching today's mostly refused names against a
    # history of only cleared ones asks the past a question about a different
    # kind of name, which is the exact fault the peak buckets already carry a
    # paragraph about.
    #
    # eligible=0 selects the refused names, which is the population the floors
    # section counts and the only caller that passes anything here.
    if eligible is not None:
        where.append("day_eligible = ?")
        params.append(eligible)
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
    # No day_eligible filter, for the reason _select gives: the ranked list
    # this screen sits beside carries names the day screen refused, so a split
    # over cleared names only would describe a population the reader is not
    # looking at.
    rows = [dict(r) for r in connection.execute(
        "SELECT date, pnl_pct, minutes_to_peak FROM research_outcomes "
        "WHERE rule_version = ? AND booked = 1 "
        "AND pnl_pct IS NOT NULL AND minutes_to_peak IS NOT NULL", (version,))]
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
    # The day screen's split of that same population, counted apart and printed
    # as its own line rather than used as a filter. It is what the floors
    # section reads, and it is the number that says how much of the replayed
    # history is names the desk would have refused.
    cleared = connection.execute(
        "SELECT COUNT(*) AS rows FROM research_outcomes WHERE rule_version = ? "
        "AND day_eligible = 1 AND skip_reason IS NULL", (version,)).fetchone()
    refused = connection.execute(
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT date) AS sessions "
        "FROM research_outcomes WHERE rule_version = ? "
        "AND day_eligible = 0 AND skip_reason IS NULL", (version,)).fetchone()
    return {
        "rows": row["rows"] or 0, "sessions": row["sessions"] or 0,
        "reached": row["reached"] or 0,
        "cleared_rows": cleared["rows"] or 0,
        "refused_rows": refused["rows"] or 0,
        "refused_sessions": refused["sessions"] or 0,
        # Said in words on the screen, because a count with no stated
        # population is the thing this whole feature exists not to print.
        "population": ("every name the replayed pool subscribed and the "
                       "reconstructed screen priced, whether or not it cleared "
                       "the day screen, which is the same kind of name the "
                       "ranked morning list carries"),
        "first": row["first"], "last": row["last"], "version": version,
        "command": "python -m research.replay_outcomes --fetch --all "
                   "then --evaluate --all",
        "survivorship": SURVIVORSHIP,
    }


# Day conditions the REPLAY CANNOT EVALUATE, with the reason each one is
# absent. A screen tabulating the floors uniformly would print a measured zero
# beside a floor nobody ran, which is the defect class this project logs most,
# so the absence is named here and drawn as an absence.
UNEVALUATED_FLOORS = {
    "require_fresh_price": (
        "no collector ran on a replayed session, so the print age this floor "
        "reads was never measured and it turned nobody down. On the live "
        "sessions on file it cut 2 of 12 and 3 of 12"),
}


def floors(connection: sqlite3.Connection,
           version: str | None = None) -> dict[str, Any]:
    """What each day screen condition turned down, and what those names did.

    The mirror of the Morning screen's "How the list was cut", asked backwards.
    That section says which floor cut how many THIS morning; this one says what
    the names a floor cut went on to do, across every replayed session. The two
    are different questions and only the second can say whether a floor is
    paying for itself.

    A CONDITION CAN CUT A NAME THAT ANOTHER CONDITION ALSO CUT, so these counts
    overlap by construction and are not a partition. Said here because a reader
    summing the column and finding more than the population would otherwise be
    right to distrust the whole screen.

    The unmeasured split is carried through from the engine for the reason
    scan.evaluate_eligibility records it: a floor a name failed because the
    number came in low and a floor it failed because nobody could compute the
    number are different facts, and the fix for the second is an instrument.
    """
    version = version or rule_version()
    rows = [dict(r) for r in connection.execute(
        "SELECT date, day_failed, day_failed_unmeasured, booked, pnl_pct "
        "FROM research_outcomes WHERE rule_version = ? AND skip_reason IS NULL "
        "AND day_eligible IS NOT NULL", (version,))]
    min_rows = _CRIT.integer("precedent", "min_rows")
    min_sessions = _CRIT.integer("precedent", "min_sessions")

    seen: dict[str, list[dict[str, Any]]] = {}
    unmeasured: dict[str, int] = {}
    for row in rows:
        keys = [k.strip() for k in (row["day_failed"] or "").split(",") if k.strip()]
        never = {k.strip() for k in
                 (row["day_failed_unmeasured"] or "").split(",") if k.strip()}
        for key in keys:
            seen.setdefault(key, []).append(row)
            if key in never:
                unmeasured[key] = unmeasured.get(key, 0) + 1

    out = []
    for key, cut in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        stats = summarise(cut)
        held = stats["sessions"] < min_sessions or stats["rows"] < min_rows
        out.append({
            "condition": key, "rows": stats["rows"], "sessions": stats["sessions"],
            "unmeasured": unmeasured.get(key, 0),
            "held": held,
            "reached": None if held else stats["reached"],
            "median": None if held else stats["median"],
            "best": None if held else stats["best"],
            "worst": None if held else stats["worst"],
        })
    for key, why in sorted(UNEVALUATED_FLOORS.items()):
        if key not in seen:
            out.append({"condition": key, "rows": None, "sessions": None,
                        "unmeasured": None, "held": True, "reached": None,
                        "median": None, "best": None, "worst": None, "why": why})
    return {"conditions": out, "population": len(rows),
            "cleared": sum(1 for r in rows if not (r["day_failed"] or "").strip()),
            "floors": {"rows": min_rows, "sessions": min_sessions},
            "overlap": ("A name refused by two floors is counted under both, "
                        "so these do not sum to the population")}


# The evidence splits this population can rebuild, and the roll lines it
# cannot. Named as a pair on purpose: a section showing three of nine
# sentences without saying which six are missing reads as a complete answer.
EVIDENCE_UNAVAILABLE = (
    "Six of the roll's nine lines cannot be rebuilt at all. The fill warning, "
    "the two collector coverage lines and the lower bound on relative volume "
    "each need the collector's own record, and no collector ran on a session "
    "the desk never had. The two catalyst lines need the vendor news tags per "
    "article, which the session cache does not hold")


def evidence(connection: sqlite3.Connection,
             version: str | None = None) -> dict[str, Any]:
    """Whether a name the evidence was thin on did worse than one it was not.

    The mirror of "What the evidence is worth", which prints what the packet
    resolved about its own evidence and stops there. This asks the question
    that section cannot: did it matter. Three of the roll's nine sentences are
    reconstructible and the other six are named rather than quietly dropped.

    Each split is drawn as a PAIR, thin against not thin, because a median for
    the thin group alone is a number with no scale.
    """
    version = version or rule_version()
    min_rows = _CRIT.integer("precedent", "min_rows")
    min_sessions = _CRIT.integer("precedent", "min_sessions")
    floor_sessions = _CRIT.integer("baseline", "min_sessions_for_rvol")
    rows = [dict(r) for r in connection.execute(
        "SELECT date, booked, pnl_pct, pm_rvol, baseline_sessions, pm_bars "
        "FROM research_outcomes WHERE rule_version = ? AND skip_reason IS NULL",
        (version,))]

    def pair(label: str, test: Any, thin_words: str, thick_words: str,
             note: str | None = None) -> dict[str, Any]:
        thin = [r for r in rows if test(r) is True]
        thick = [r for r in rows if test(r) is False]
        # A row the test cannot answer joins NEITHER side. It is not thin and
        # it is not thick, and putting it on either would be an answer invented
        # out of a missing input.
        unknown = len(rows) - len(thin) - len(thick)
        out = {"split": label, "thin_words": thin_words,
               "thick_words": thick_words, "unknown": unknown, "note": note,
               "sides": []}
        for words, group in ((thin_words, thin), (thick_words, thick)):
            stats = summarise(group)
            held = stats["sessions"] < min_sessions or stats["rows"] < min_rows
            out["sides"].append({
                "words": words, "rows": stats["rows"],
                "sessions": stats["sessions"], "held": held,
                "reached": None if held else stats["reached"],
                "median": None if held else stats["median"],
                "worst": None if held else stats["worst"],
                "best": None if held else stats["best"]})
        return out

    def thin_baseline(row: dict[str, Any]) -> Any:
        used = row.get("baseline_sessions")
        return None if used is None else used < floor_sessions

    def rvol_null(row: dict[str, Any]) -> Any:
        # Never None: the column's own NULL IS the answer to this question.
        return row.get("pm_rvol") is None

    def few_bars(row: dict[str, Any]) -> Any:
        bars = row.get("pm_bars")
        return None if bars is None else bars < 2

    return {
        "splits": [
            pair("thin_baseline", thin_baseline,
                 f"fewer than {floor_sessions} baseline sessions",
                 f"{floor_sessions} or more",
                 "the RVOL denominator rests on this many prior premarkets"),
            pair("rvol_null", rvol_null,
                 "premarket RVOL could not be computed at all",
                 "RVOL was measured"),
            pair("window_thin", few_bars,
                 "one premarket minute or none",
                 "more than one premarket minute"),
        ],
        "unavailable": EVIDENCE_UNAVAILABLE,
        "floors": {"rows": min_rows, "sessions": min_sessions},
    }


def morning_shape(connection: sqlite3.Connection, today: list[dict[str, Any]],
                  version: str | None = None) -> dict[str, Any]:
    """Where this morning's mix sits against every replayed morning's.

    The mirror of "What kind of morning this is", and a NARROWER thing than
    that section, which is why it says so on the screen. That one draws sector,
    catalyst class and direction. Sector is on no disk for a replayed session
    and catalyst class needs per article news tags the session cache does not
    hold, so neither can be rebuilt at any price. What survives is the shape
    the bands already carry, and it is drawn on a shared axis: today's share
    against the median replayed share, so a reader can see which way this
    morning leans rather than reading a number with no scale.
    """
    version = version or rule_version()
    rows = [dict(r) for r in connection.execute(
        "SELECT date, gap_band, rvol_band, price_band, cap_band, "
        "earnings_overnight FROM research_outcomes "
        "WHERE rule_version = ? AND skip_reason IS NULL", (version,))]
    by_session: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(row["date"], []).append(row)

    def share(group: list[dict[str, Any]], test: Any) -> float | None:
        answered = [r for r in group if test(r) is not None]
        if not answered:
            return None
        return sum(1 for r in answered if test(r)) * 100.0 / len(answered)

    measures = [
        ("gapped up", lambda r: (None if not r.get("gap_band")
                                 else str(r["gap_band"]).startswith("up"))),
        ("reported overnight", lambda r: (None if r.get("earnings_overnight") is None
                                          else bool(r["earnings_overnight"]))),
        ("volume at least 3x normal",
         lambda r: (None if not r.get("rvol_band")
                    else str(r["rvol_band"]) not in ("under 1.5x", "1.5x to 3x"))),
        ("priced over 50", lambda r: (None if not r.get("price_band")
                                      else str(r["price_band"]) == "50 and up")),
    ]

    def today_row(candidate: dict[str, Any]) -> dict[str, Any]:
        cut = lookalike.bands_for(
            candidate.get("gap"), candidate.get("rvol"), candidate.get("price"),
            (candidate.get("mcap") / 1_000_000.0
             if isinstance(candidate.get("mcap"), (int, float)) else None))
        overnight = candidate.get("earn_overnight")
        return {**cut, "earnings_overnight":
                None if overnight is None else int(bool(overnight))}

    mine = [today_row(c) for c in today]
    out = []
    for words, test in measures:
        past = sorted(v for v in (share(g, test) for g in by_session.values())
                      if v is not None)
        out.append({
            "words": words,
            "today": share(mine, test),
            "median": None if not past else round(_percentile(past, 0.5), 1),
            "p10": None if not past else round(_percentile(past, 0.10), 1),
            "p90": None if not past else round(_percentile(past, 0.90), 1),
            "sessions": len(past),
        })
    return {"measures": out, "sessions": len(by_session),
            "unavailable": ("Sector and catalyst class are drawn on the Morning "
                            "screen and cannot be rebuilt here: no replayed "
                            "session carries a sector, and the catalyst class "
                            "needs per article news tags the cache does not hold")}


def _daily_stats(rows: list[dict[str, Any]], min_rows: int,
                 min_sessions: int) -> dict[str, Any]:
    """The printed figures for a group of DAILY BAR rows.

    A different instrument from summarise() and deliberately not sharing its
    shape. There is no entry here, so there is no "reached the buy" and no
    booked count: these names were never priced. What exists is where the day
    opened and where it went, so the figures are open to close and the best a
    holder could have got, and calling either of them a result would be a
    simulated trade wearing a daily bar's clothes.
    """
    sessions = {r["date"] for r in rows}
    closes = [float(r["open_to_close_pct"]) for r in rows
              if r.get("open_to_close_pct") is not None]
    highs = [float(r["open_to_high_pct"]) for r in rows
             if r.get("open_to_high_pct") is not None]
    held = len(sessions) < min_sessions or len(rows) < min_rows
    out = {"rows": len(rows), "sessions": len(sessions), "held": held,
           "median": None, "p25": None, "p75": None, "worst": None,
           "best": None, "up": None, "median_high": None}
    if closes and not held:
        out["median"] = round(_percentile(closes, 0.5), 4)
        out["p25"] = round(_percentile(closes, 0.25), 4)
        out["p75"] = round(_percentile(closes, 0.75), 4)
        out["worst"] = round(min(closes), 4)
        out["best"] = round(max(closes), 4)
        out["up"] = sum(1 for v in closes if v > 0)
    if highs and not held:
        out["median_high"] = round(_percentile(highs, 0.5), 4)
    return out


NO_ENTRY_HERE = ("These names were never priced, so there is no entry, no "
                 "stop and no trade. The figures are the DAY: where it opened "
                 "and where it went, which is a weaker question than the one "
                 "the table above answers and must not be read beside it")


def missed(connection: sqlite3.Connection) -> dict[str, Any]:
    """What gapped that the pool never subscribed, by how far it gapped.

    The mirror of the Morning screen's "What else moved", asked of a year. That
    section names today's movers outside the pool; this one asks whether the
    pool has been missing the ones that mattered, band by band, and it is the
    only section here that can answer a question about the SELECTION rather
    than about the screen.

    Rows whose session the replay has not screened carry subscribed NULL and
    are excluded: on those, "not subscribed" is unknown rather than false.
    """
    min_rows = _CRIT.integer("precedent", "min_rows")
    min_sessions = _CRIT.integer("precedent", "min_sessions")
    rows = [dict(r) for r in connection.execute(
        "SELECT date, ticker, gap_band, subscribed, open_to_close_pct, "
        "open_to_high_pct FROM research_daily WHERE gapped = 1 "
        "AND subscribed IS NOT NULL AND skip_reason IS NULL")]
    unknown = connection.execute(
        "SELECT COUNT(*) FROM research_daily WHERE gapped = 1 "
        "AND subscribed IS NULL").fetchone()[0]

    bands: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bands.setdefault(row["gap_band"] or "not banded", []).append(row)

    out = []
    for band_name, group in sorted(bands.items(), key=lambda kv: -len(kv[1])):
        taken = [r for r in group if r["subscribed"]]
        left = [r for r in group if not r["subscribed"]]
        stats = _daily_stats(left, min_rows, min_sessions)
        out.append({
            "band": band_name, "gapped": len(group),
            "subscribed": len(taken), "missed": len(left),
            "share_subscribed": (round(len(taken) * 100.0 / len(group))
                                 if group else None),
            **stats})
    return {"bands": out, "unknown_sessions": unknown,
            "floors": {"rows": min_rows, "sessions": min_sessions},
            "caveat": NO_ENTRY_HERE, "survivorship": SURVIVORSHIP}


def events(connection: sqlite3.Connection) -> dict[str, Any]:
    """What names that reported overnight did, split by the kind of report.

    The mirror of "Coming up", which lists tomorrow's reporters and stops. This
    asks what the last few hundred of them did, which is the only thing that
    makes a calendar entry worth reading before the open.

    The beat and miss split is the vendor's own estimate against its own
    actual. It is absent on a large share of rows, and an absent estimate joins
    NEITHER side rather than being read as a miss.
    """
    min_rows = _CRIT.integer("precedent", "min_rows")
    min_sessions = _CRIT.integer("precedent", "min_sessions")
    rows = [dict(r) for r in connection.execute(
        "SELECT date, earnings_tier_key, earnings_estimate, earnings_actual, "
        "gapped, open_to_close_pct, open_to_high_pct FROM research_daily "
        "WHERE earnings_tier_key IS NOT NULL AND skip_reason IS NULL")]

    tiers: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        tiers.setdefault(row["earnings_tier_key"], []).append(row)
    by_tier = []
    for key, group in sorted(tiers.items(), key=lambda kv: -len(kv[1])):
        gapped = [r for r in group if r["gapped"]]
        by_tier.append({
            "tier": key, "rows": len(group),
            "gapped": len(gapped),
            "share_gapped": round(len(gapped) * 100.0 / len(group)) if group else None,
            **_daily_stats(group, min_rows, min_sessions)})

    def surprise(row: dict[str, Any]) -> Any:
        estimate, actual = row.get("earnings_estimate"), row.get("earnings_actual")
        if estimate is None or actual is None:
            return None
        return actual > estimate

    beat = [r for r in rows if surprise(r) is True]
    missed_it = [r for r in rows if surprise(r) is False]
    return {
        "tiers": by_tier,
        "surprise": [
            {"words": "beat the estimate",
             **_daily_stats(beat, min_rows, min_sessions)},
            {"words": "came in at or under it",
             **_daily_stats(missed_it, min_rows, min_sessions)},
        ],
        "no_estimate": len(rows) - len(beat) - len(missed_it),
        "floors": {"rows": min_rows, "sessions": min_sessions},
        "caveat": NO_ENTRY_HERE, "survivorship": SURVIVORSHIP,
    }


def noon(connection: sqlite3.Connection,
         version: str | None = None) -> dict[str, Any]:
    """What a noon verdict has been worth by the close.

    The mirror of "What noon will grade", which prints the levels the pass is
    about to read back and can say nothing about them. This is the question
    that section raises and cannot answer: when noon said a name never
    triggered, how often was that the end of it.

    The grades are midday/scan_midday.grade's own, folded from the same cached
    minutes the simulation read, so the state names here are the state names
    the live pass writes and not a second vocabulary.
    """
    version = version or rule_version()
    min_rows = _CRIT.integer("precedent", "min_rows")
    min_sessions = _CRIT.integer("precedent", "min_sessions")
    rows = [dict(r) for r in connection.execute(
        "SELECT date, noon_state, noon_now_vs_fill_pct, booked, pnl_pct "
        "FROM research_outcomes WHERE rule_version = ? "
        "AND noon_skip_reason IS NULL AND noon_state IS NOT NULL", (version,))]
    ungraded = connection.execute(
        "SELECT COUNT(*) FROM research_outcomes WHERE rule_version = ? "
        "AND noon_skip_reason IS NOT NULL", (version,)).fetchone()[0]

    states: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        states.setdefault(row["noon_state"], []).append(row)

    out = []
    for state, group in sorted(states.items(), key=lambda kv: -len(kv[1])):
        stats = summarise(group)
        # THE ONE FIGURE THIS SECTION EXISTS FOR: of the names noon called one
        # way, how many the close called the other. A noon verdict that never
        # changes is a verdict worth acting on and one that often changes is
        # not, and no other section here can say which.
        turned = sum(1 for r in group if r.get("booked"))
        out.append({
            "state": state, "rows": stats["rows"], "sessions": stats["sessions"],
            "held": stats["sessions"] < min_sessions or stats["rows"] < min_rows,
            "reached_by_close": turned,
            "share_reached": (round(turned * 100.0 / len(group)) if group
                              else None),
            "median": stats["median"], "worst": stats["worst"],
            "best": stats["best"], "p25": stats["p25"], "p75": stats["p75"]})
    for entry in out:
        if entry["held"]:
            for key in ("reached_by_close", "share_reached", "median", "worst",
                        "best", "p25", "p75"):
                entry[key] = None
    return {"states": out, "ungraded": ungraded,
            "clock": _CRIT.text("midday", "run_time"),
            "floors": {"rows": min_rows, "sessions": min_sessions},
            "note": ("The grade is the noon pass's own rule read off the same "
                     "cached minutes, and reached by the close is the paper "
                     "rule's own answer for the same name, so a row where they "
                     "disagree is one instrument disagreeing with the other "
                     "rather than two measurements of different things")}


def daily_coverage(connection: sqlite3.Connection) -> dict[str, Any]:
    """How much daily bar history exists, for the two sections that read it."""
    row = connection.execute(
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT date) AS sessions, "
        "MIN(date) AS first, MAX(date) AS last FROM research_daily "
        "WHERE skip_reason IS NULL").fetchone()
    return {"rows": row["rows"] or 0, "sessions": row["sessions"] or 0,
            "first": row["first"], "last": row["last"],
            "command": "python -m research.replay_daily --evaluate --all"}


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
        cut = floors(connection, version) if cover["rows"] else None
        worth = evidence(connection, version) if cover["rows"] else None
        shape = (morning_shape(connection, candidates, version)
                 if cover["rows"] else None)
        # The two daily bar sections stand on their OWN coverage, because
        # research_daily fills from the session caches alone and can hold a
        # year while research_outcomes is still empty. Gating them on the
        # trade table would blank two sections that have answers.
        daily = daily_coverage(connection)
        gone = missed(connection) if daily["rows"] else None
        calendar = events(connection) if daily["rows"] else None
        midday = noon(connection, version) if cover["rows"] else None
    return {"coverage": cover, "names": names, "peaks": buckets,
            "floors": cut, "evidence": worth, "shape": shape,
            "daily": daily, "missed": gone, "events": calendar, "noon": midday}
