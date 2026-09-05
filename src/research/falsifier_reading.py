"""Read the pre-registered falsifiers of PRECEDENT_PREREGISTRATION section 9.

WHY THIS IS A MODULE AND NOT A NUMBER IN A DOCUMENT. Section 12 of that page
says the widening ladder fires on more than half of a morning's candidates and
therefore that the bands are too tight. That is the finding the whole screen
turns on, and a finding nobody can recompute is an assertion. This recomputes
it from the same table the screen reads, through the same functions the screen
calls, so the paragraph and the code cannot drift apart without one of them
being wrong out loud.

IT IMPORTS THE LADDER, IT DOES NOT REIMPLEMENT IT. desk.precedent.match is
called once per replayed candidate, so the widening order, the floors and the
refusal all come from CRITERIA through the shipped path. A second copy of the
ladder here would measure a rule the screen does not run, which is the failure
this file exists to rule out.

THREE THINGS TO GET RIGHT, each of which was got wrong on 2026-09-05 before it
was got right, and each of which moves the answer across the bar:

  the rule_version fence   research_outcomes holds one row per candidate PER
                           PAPER RULE. Counting without the fence _select
                           applies double counts every candidate, halves the
                           apparent sparsity of every cell and reports the
                           falsifier as passing when it fails.

  the earnings condition   condition 1 of the match rule is the BOOLEAN
                           earnings_overnight, which takes two values. It is
                           not earnings_tier_key, which takes four and belongs
                           to the events section. Four values cut the lattice
                           twice as fine and move the answer again.

  the unread calendar      match refuses before the ladder when the calendar
                           was never read, because that is the one condition
                           the ladder may never drop. Those candidates are
                           counted on their own line below. Folding them into
                           the fired count would blame the band edges for a
                           gap in what the vendor sent.

WHAT IT CANNOT SAY. A replayed candidate is itself a row in the pool it is
matched against, so every group it lands in is one row larger than the shipped
screen would see. A live candidate is never in research_outcomes. Against
floors of 30 rows the effect is under one part in thirty and it inflates
clearance, so the true reading is if anything slightly worse than the one
printed here.

Reads only. Spends no quota, calls no vendor, and writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import statistics
import sys
from typing import Any

from core import store
from desk import precedent


def _conditions(row: dict[str, Any]) -> dict[str, Any]:
    """The six conditions, taken from the row's own stored bands.

    precedent.conditions_for reads a COMPACTED candidate and cuts the bands
    itself. A replayed row already carries the cut, written by the engine from
    the same core.lookalike.bands_for, so the bands are read back here rather
    than recut. The keys and their order are conditions_for's.
    """
    return {
        "earnings_overnight": row["earnings_overnight"],
        "gap_band": row["gap_band"],
        "rvol_band": row["rvol_band"],
        "price_band": row["price_band"],
        "cap_band": row["cap_band"],
        "above_prior_high": row["above_prior_high"],
    }


def read(connection, version: str | None = None) -> dict[str, Any]:
    version = version or precedent.rule_version()
    rows = [dict(r) for r in connection.execute(
        "SELECT date, earnings_overnight, gap_band, rvol_band, price_band, "
        "cap_band, above_prior_high FROM research_outcomes "
        "WHERE rule_version = ? AND skip_reason IS NULL", (version,))]

    per_session: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    settled: collections.Counter = collections.Counter()
    unread = 0
    withheld = 0
    # One match() per candidate. Identical condition tuples recur constantly
    # across 240 sessions, so the result is memoised on the tuple: same query,
    # same answer, and the cache is what makes this minutes rather than hours.
    cache: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        conditions = _conditions(row)
        key = tuple(conditions.values())
        result = cache.get(key)
        if result is None:
            result = precedent.match(connection, conditions, version)
            cache[key] = result
        if conditions["earnings_overnight"] is None:
            unread += 1
            continue
        per_session[row["date"]][1] += 1
        if result["held"]:
            withheld += 1
            settled["withheld"] += 1
            per_session[row["date"]][0] += 1
        elif result["widened"]:
            settled[len(result["widened"])] += 1
            per_session[row["date"]][0] += 1
        else:
            settled[0] += 1

    shares = [100.0 * fired / total
              for fired, total in per_session.values() if total]
    laddered = sum(total for _, total in per_session.values())
    fired = sum(f for f, _ in per_session.values())
    return {
        "version": version, "rows": len(rows), "sessions": len(per_session),
        "unread_calendar": unread, "laddered": laddered, "fired": fired,
        "pooled_pct": (100.0 * fired / laddered) if laddered else None,
        "median_morning_pct": statistics.median(shares) if shares else None,
        "mornings_over_half": sum(1 for s in shares if s > 50),
        "mornings": len(shares), "withheld": withheld,
        "settled": {str(k): v for k, v in sorted(
            settled.items(), key=lambda kv: str(kv[0]))},
        "distinct_shapes": len(cache),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default=None,
                        help="paper rule_version to fence on (default: the "
                             "one desk.precedent ships)")
    args = parser.parse_args(argv)

    connection = store.connect()
    out = read(connection, args.version)

    print("PRECEDENT_PREREGISTRATION section 9, first falsifier")
    print("  population        %d graded rows over %d sessions, rule_version %s"
          % (out["rows"], out["sessions"], out["version"]))
    print("                    %d distinct condition shapes among them"
          % out["distinct_shapes"])
    if out["unread_calendar"]:
        print("  calendar unread   %d candidates refused before the ladder ran, "
              "excluded below" % out["unread_calendar"])
    print("  ladder fires on   %.0f%% of candidates pooled"
          % (out["pooled_pct"] or 0))
    print("                    %.0f%% of the median morning"
          % (out["median_morning_pct"] or 0))
    print("                    %d of %d mornings strictly over half"
          % (out["mornings_over_half"], out["mornings"]))
    print("  settles at        %s" % ", ".join(
        ("withheld=%d" % v) if k == "withheld" else ("%s drop(s)=%d" % (k, v))
        for k, v in out["settled"].items()))
    over_half = out["mornings_over_half"] > out["mornings"] / 2
    tripped = ((out["pooled_pct"] or 0) > 50
               and (out["median_morning_pct"] or 0) > 50 and over_half)
    print("  VERDICT           %s" % (
        "TRIPPED on all three readings: the bands are too tight and section 9 "
        "says the rule needs re-cutting" if tripped else
        "not tripped on all three readings; read the three figures above "
        "rather than this line"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
