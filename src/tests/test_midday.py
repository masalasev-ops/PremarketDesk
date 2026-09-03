"""Regression test for the midday pass, CRITERIA [Midday].

Run it through the suite: `python -m tests.run_tests --only tests.test_midday`
from the project root with src on PYTHONPATH. Makes no network call and spends
no quota: every quote is synthetic and the grading rule is pure arithmetic on a
dict, which is most of why the rule was written as a function taking a quote
rather than as something that fetches one.

The claims are grouped by what they defend.

FIRST THE SEQUENCE, because it is the one thing this pass can most easily be
made to lie about. A daily high and a daily low carry no order. When the fill
is the opening print, everything after it is after it and a stop out is
knowable; when the fill happens intraday, the session low may predate it and
the honest answer is that nobody can tell. A pass that collapsed those two into
one verdict would read exactly like a pass that knew, on the rows where it
does not, and the ledger's most valuable finding to date is about WHEN a name
made its high.

THEN THE ROW THAT NEVER FILLED, which the first prototype got wrong on
2026-08-31: it read the session low against the stop on a name whose high never
reached the entry. A low with no trade under it stops nothing.

THEN THE DENOMINATOR, which is the defect that nearly shipped. The quote's
previousClosePrice was measured to be two different sessions depending on the
row, with a correct previousCloseDate beside it either way, so the vintage
check written into the first draft of CRITERIA would have passed on every bad
row. The prior close comes from a bulk day asked for BY DATE, and a symbol the
bulk day does not carry is left unmeasured rather than measured against the
field that cannot be trusted.

THEN WHAT THE SCAN LOST, because a count with no names cannot be chased and 358
names arrived in an unpriced bucket on the first real run with nothing saying
which field they were missing.

AND THE RENDERER'S ESCAPING, because every headline in the movers section is
third party text from a feed nobody here controls. It reaches the report as a
LIST ITEM rather than as a table cell, which is worth stating because the first
version of that claim asserted against a table row the headline never touches
and passed while the escaping was removed. The hazard is a newline: a headline
that starts a line of its own can forge a heading or a table row.
"""

from __future__ import annotations

from tests.conftest import run_claim

import datetime as dt
import json
import sys
from typing import Any

from core import config
from core import criteria
from core import ettime
from core import glossary
from midday import render_midday
from midday import scan_midday

_CRIT = criteria.load()


def _quote(**kw: Any) -> dict[str, Any]:
    """A quote as read_quote returns one, with everything present."""
    base = {
        "open": None, "high": None, "low": None, "last": None,
        "prev_close": 100.0, "prev_close_source": "eod-bulk-last-day",
        "vendor_prev_close_date_reported": "2026-08-28",
        "volume": None, "average_volume": None, "market_cap": 1e9,
        "name": "Test Inc", "last_trade_at": None, "quote_age_seconds": 30,
        "refused_reason": None,
    }
    base.update(kw)
    return base


def _pick(**kw: Any) -> dict[str, Any]:
    base = {"ticker": "TEST.US", "score": 8.0, "conviction": "green",
            "day_eligible": 1, "swing_eligible": 0, "gap_pct": 5.0,
            "pm_high": 10.0, "pm_low": 9.0, "entry_ref": 10.0, "stop_ref": 9.0}
    base.update(kw)
    return base


# ------------------------------------------------------------ the sequence

def claim_a_gap_through_can_name_a_stop_out_and_an_intraday_fill_cannot(
        failures: list[str]) -> None:
    """The same low, the same stop, two different verdicts, and both are right.

    Identical session extremes. The only difference is whether the open cleared
    the entry, which is what decides whether the fill was the session's first
    print. That is the whole argument for extending [Collector] stop_time past
    the open, so it is asserted rather than described.
    """
    through = scan_midday.grade(
        _pick(), _quote(open=10.5, high=11.0, low=8.5, last=8.7))
    intraday = scan_midday.grade(
        _pick(), _quote(open=9.5, high=11.0, low=8.5, last=8.7))

    if through["stop_state"] != scan_midday.STOP_OUT:
        failures.append(
            f"a fill at the opening print with a later low through the stop "
            f"read {through['stop_state']!r}, and it is knowable: the fill is "
            "the first price of the session")
    if intraday["stop_state"] != scan_midday.STOP_SEQUENCE_UNKNOWN:
        failures.append(
            f"an intraday fill with a session low through the stop read "
            f"{intraday['stop_state']!r}, which claims an order a daily high "
            "and low cannot carry")
    if through["worst_vs_fill_pct"] is None:
        failures.append("a gap through withheld worst_vs_fill_pct, which it "
                        "can compute: the fill preceded every other print")
    if intraday["worst_vs_fill_pct"] is not None:
        failures.append(
            f"an intraday fill reported worst_vs_fill_pct "
            f"{intraday['worst_vs_fill_pct']}, measured against a low that may "
            "have happened before the fill")
    if not intraday["worst_vs_fill_reason"]:
        failures.append("an intraday fill withheld worst_vs_fill_pct and gave "
                        "no reason, which is a silence rather than a null")
    print("  sequence     a fill at the open books a stop out, an intraday "
          "fill says the order is unknown, and only the first reports a worst")


def claim_the_two_fills_are_the_paper_rule_s_fills(failures: list[str]) -> None:
    """A gap through fills at the open, a trigger fills at the level.

    CRITERIA [Paper] ENTRY PRICE is max(entry_ref, that minute's open), and
    this pass has one bar rather than minutes, so the same rule reduces to
    these two cases. If they ever diverge, the midday verdict and the night
    ledger stop being two measurements of one question.
    """
    through = scan_midday.grade(
        _pick(), _quote(open=10.5, high=11.0, low=10.2, last=10.9))
    trigger = scan_midday.grade(
        _pick(), _quote(open=9.5, high=11.0, low=9.4, last=10.9))
    if through["fill"] != 10.5:
        failures.append(f"a gap through filled at {through['fill']}, not at the "
                        "10.5 open the session actually opened at")
    if trigger["fill"] != 10.0:
        failures.append(f"an intraday trigger filled at {trigger['fill']}, not "
                        "at the 10.0 entry reference the order rested on")
    print("  two fills    a gap through fills at the open and a trigger fills "
          "at the level, as CRITERIA [Paper] books them")


def claim_a_row_that_never_filled_reads_no_stop(failures: list[str]) -> None:
    """The prototype defect of 2026-08-31, pinned.

    The session low is far below the stop and the high never reached the entry.
    Reading one against the other books a loss on a trade nobody was in.
    """
    row = scan_midday.grade(
        _pick(), _quote(open=9.5, high=9.8, low=5.0, last=9.6))
    if row["state"] != scan_midday.NEVER_TRIGGERED:
        failures.append(f"a high of 9.8 under a 10.0 entry read "
                        f"{row['state']!r}")
    if row["stop_state"] != scan_midday.STOP_NOT_APPLICABLE:
        failures.append(
            f"a row that never triggered read its stop as {row['stop_state']!r} "
            "against a low of 5.0, which books a loss on a position that was "
            "never opened")
    if row["fill"] is not None:
        failures.append(f"a row that never triggered carries a fill of "
                        f"{row['fill']}")
    print("  no fill      a name whose high never reached the entry reads no "
          "stop however far its low fell")


def claim_the_boundaries_go_the_way_criteria_writes_them(
        failures: list[str]) -> None:
    """On the line is IN, for all three comparisons, and each is stated.

    open >= entry is a gap through, high >= entry triggers, low <= stop is
    reached. Every one of the three is a place a later edit can silently move
    a verdict by one tick.
    """
    on_entry_open = scan_midday.grade(
        _pick(), _quote(open=10.0, high=10.4, low=9.5, last=10.2))
    on_entry_high = scan_midday.grade(
        _pick(), _quote(open=9.5, high=10.0, low=9.5, last=9.9))
    on_stop = scan_midday.grade(
        _pick(), _quote(open=10.5, high=11.0, low=9.0, last=9.1))

    if on_entry_open["state"] != scan_midday.GAPPED_THROUGH:
        failures.append(f"an open exactly ON the entry read "
                        f"{on_entry_open['state']!r}, not a gap through")
    if on_entry_high["state"] != scan_midday.TRIGGERED:
        failures.append(f"a high exactly ON the entry read "
                        f"{on_entry_high['state']!r}, so a resting order at "
                        "that level would not have filled")
    if on_stop["stop_state"] != scan_midday.STOP_OUT:
        failures.append(f"a low exactly ON the stop read "
                        f"{on_stop['stop_state']!r}, so a resting stop at that "
                        "level would not have been hit")
    print("  boundaries   on the line is in, for the open, the high and the low")


def claim_a_close_verdict_is_flagged(failures: list[str]) -> None:
    """The quote's open is the first consolidated print, not the auction.

    Measured 2026-08-31: it differed from the official open for 30 percent of
    2,750 names, by a median 0.34 percent. So a verdict decided by less than
    [Midday] open_tolerance_pct says so, and one decided by more does not.
    """
    tolerance = _CRIT.number("midday", "open_tolerance_pct")
    inside = 10.0 * (1 + tolerance / 200.0)
    outside = 10.0 * (1 + tolerance / 100.0 * 3)
    close = scan_midday.grade(
        _pick(), _quote(open=inside, high=11.0, low=9.5, last=10.5))
    clear = scan_midday.grade(
        _pick(), _quote(open=outside, high=11.0, low=9.5, last=10.5))

    if not close["decided_inside_the_open_tolerance"]:
        failures.append(
            f"an open {inside:g} against a 10.0 entry, inside the {tolerance:g} "
            "percent tolerance, was presented as settled")
    if not close["open_tolerance_reason"]:
        failures.append("a flagged row carried no reason, so a reader sees a "
                        "flag with nothing behind it")
    if clear["decided_inside_the_open_tolerance"]:
        failures.append(
            f"an open {outside:g} against a 10.0 entry was flagged as close, "
            "which makes the flag meaningless by firing on everything")
    print(f"  close call   a verdict decided inside {tolerance:g} percent of "
          "the entry is flagged, one decided outside it is not")


# ----------------------------------------------------------- the denominator

def claim_the_prior_close_is_never_the_quote_s_own_field(
        failures: list[str]) -> None:
    """read_quote takes the prior close as an ARGUMENT and reads no substitute.

    The quote carries previousClosePrice, and on 2026-08-31 that field was the
    prior session for about a third of names and TODAY for about another
    third, with a correct previousCloseDate on both. So the fixture hands over
    a quote whose previousClosePrice is wildly wrong and asserts that nothing
    picked it up.
    """
    now = ettime.now_et()
    raw = {"open": 10.5, "high": 11.0, "low": 9.0, "lastTradePrice": 10.9,
           "previousClosePrice": 999.0,
           "previousCloseDate": "2026-08-28 17:00:00",
           "volume": 1_000_000, "averageVolume": 200_000,
           "lastTradeTime": ettime.epoch_ms(now)}

    row = scan_midday.read_quote(raw, now, "2026-08-28", 100.0)
    if row["prev_close"] != 100.0:
        failures.append(
            f"prev_close read {row['prev_close']}, not the 100.0 handed in "
            "from the bulk day. 999.0 is the quote's own field and it must not "
            "reach a denominator")
    if row["prev_close_source"] != "eod-bulk-last-day":
        failures.append(f"prev_close_source says {row['prev_close_source']!r}, "
                        "so the packet does not name where the denominator "
                        "came from")

    # And with no bulk close, the row is refused rather than falling back.
    missing = scan_midday.read_quote(raw, now, "2026-08-28", None)
    if not missing["refused_reason"]:
        failures.append(
            "a symbol the bulk day did not carry was NOT refused, so something "
            "supplied a denominator from elsewhere, which is the 2026-08-14 "
            "defect's exact shape")
    if missing["last"] is not None or missing["prev_close"] is not None:
        failures.append("a refused row kept its prices, so a later reader can "
                        "still compute a move from numbers this pass refused")
    print("  denominator  the prior close comes from the bulk day, a missing "
          "one refuses the row, and previousClosePrice is never read")


def claim_a_stale_quote_is_refused_with_its_age(failures: list[str]) -> None:
    limit = _CRIT.number("midday", "max_quote_age_seconds")
    now = ettime.now_et()
    stale = {"open": 10.5, "high": 11.0, "low": 9.0, "lastTradePrice": 10.9,
             "volume": 1, "averageVolume": 1,
             "lastTradeTime": ettime.epoch_ms(
                 now - dt.timedelta(seconds=limit + 60))}
    row = scan_midday.read_quote(stale, now, "2026-08-28", 100.0)
    if not row["refused_reason"] or "second" not in row["refused_reason"]:
        failures.append(f"a quote {limit + 60:.0f} seconds old was not refused "
                        f"with its age: {row['refused_reason']!r}")

    undated = dict(stale)
    undated.pop("lastTradeTime")
    row = scan_midday.read_quote(undated, now, "2026-08-28", 100.0)
    if not row["refused_reason"] or "unknown" not in row["refused_reason"]:
        failures.append(
            "a quote carrying no lastTradeTime was not refused as UNKNOWN age. "
            "An unknown age is not a fresh one")

    fresh = dict(stale)
    fresh["lastTradeTime"] = ettime.epoch_ms(now - dt.timedelta(seconds=10))
    row = scan_midday.read_quote(fresh, now, "2026-08-28", 100.0)
    if row["refused_reason"]:
        failures.append(f"a ten second old quote was refused: "
                        f"{row['refused_reason']!r}")
    print(f"  quote age    older than {limit:,.0f}s is refused with its age, an "
          "absent stamp is refused as unknown, and a fresh quote passes")


def claim_a_graded_row_says_which_levels_it_used(failures: list[str]) -> None:
    """The night books the same trade against corrected levels.

    Two passes reaching different verdicts on one trade is fine and expected.
    A reader who cannot tell which levels produced which verdict is not.

    IN WORDS, NOT IN FIELD NAMES. This claim used to demand the strings
    entry_ref, stop_ref and true, which is how the packet's schema came to be
    printed in a report. The distinction it exists to protect is the morning's
    published levels against the night's corrected ones, and that is what is
    checked; the words the sentence says it in are a reader's.
    """
    row = scan_midday.grade(
        _pick(), _quote(open=10.5, high=11.0, low=10.2, last=10.9))
    text = str(row.get("levels_are") or "")
    for wanted in ("the entry and stop as the morning published them",
                   "corrected entry and stop", "night"):
        if wanted not in text:
            failures.append(f"the levels disclosure does not mention {wanted!r}: "
                            f"{text!r}")
    for leaked in ("entry_ref", "stop_ref", "_true"):
        if leaked in text:
            failures.append(f"the levels disclosure prints the field name "
                            f"{leaked!r}: {text!r}")
    print("  levels       every graded row names the morning's levels and says "
          "they are not the night's corrected ones")


# --------------------------------------------------------- what the scan lost

def claim_an_unmeasured_name_is_named_not_counted(failures: list[str]) -> None:
    """Four buckets, one per missing field, each carrying examples.

    358 names arrived in a single unpriced bucket on the first real run and the
    packet could not say what any of them was missing. It turned out to be the
    denominator, which was the defect. A count that cannot be chased is how
    that stayed invisible.
    """
    quotes = {
        "NOLAST.US": _quote(open=1.0, high=2.0, low=0.5, last=None,
                            volume=10, average_volume=1),
        "NOPREV.US": _quote(open=1.0, high=2.0, low=0.5, last=1.5,
                            prev_close=None, volume=10, average_volume=1),
        "NOAVG.US": _quote(open=1.0, high=2.0, low=0.5, last=1.5,
                           volume=10, average_volume=None),
        "NOVOL.US": _quote(open=1.0, high=2.0, low=0.5, last=1.5,
                           volume=None, average_volume=1),
    }
    _rows, tally = scan_midday.rank_movers(quotes, set(), set(), set())
    for bucket, symbol in (("no_last_price", "NOLAST.US"),
                           ("no_previous_close", "NOPREV.US"),
                           ("no_average_volume", "NOAVG.US"),
                           ("no_volume", "NOVOL.US")):
        if tally.get(bucket) != 1:
            failures.append(f"{symbol} did not land in {bucket}, which counted "
                            f"{tally.get(bucket)}")
        if symbol not in (tally.get("examples", {}).get(bucket) or []):
            failures.append(f"{bucket} counted {symbol} and did not name it, so "
                            "the count cannot be chased to a cause")
    if tally["admitted"]:
        failures.append(f"{tally['admitted']} unmeasurable names were admitted "
                        "to the movers list")
    print("  unmeasured   each missing field is its own count and names the "
          "symbols behind it")


def claim_the_breakdown_names_every_name_it_counted(failures: list[str]) -> None:
    """The rendered breakdown covers the whole quoted population.

    The tally has ten buckets and the sentence named five of them. The one it
    left out is refused, which counts the quotes read_quote declined for a
    stale price, an absent lastTradeTime or a prior session with no close, and
    it was also the only bucket with no example list. Both holes were invisible
    on 2026-08-31 because that session refused nothing, so the five printed
    numbers happened to add to the quoted count and the line reconciled by
    luck.

    On a session where the vendor serves stale prices, refused is the LARGEST
    bucket in the tally. A reader would have been handed a population that does
    not add up, with nothing in the report naming where the difference went,
    which is the shape of every defect this pass was written to avoid.

    Two directions, because a sentence that names the bucket and a tally that
    reconciles are different properties: the second can hold while the first
    fails, and it did.
    """
    quotes = {
        "STALE.US": _quote(refused_reason="its last trade is 9,000 seconds old"),
        "MOVER.US": _quote(open=100.0, high=130.0, low=99.0, last=130.0,
                           volume=1_000_000, average_volume=100_000),
    }
    _rows, tally = scan_midday.rank_movers(quotes, set(), set(), set())
    if tally["refused"] != 1:
        failures.append(f"a refused quote did not land in the refused bucket, "
                        f"which counted {tally['refused']}")
    if "STALE.US" not in (tally.get("examples", {}).get("refused") or []):
        failures.append("the refused bucket counted STALE.US and did not name "
                        "it, so a session of stale prices cannot be chased to "
                        "the symbols it lost")

    text = "\n".join(render_midday.movers_section({
        "movers": {"rows": [], "tally": tally, "list_size": 15,
                   "rank_by": "move", "news_calls": 0,
                   "selection_note": "selection is on price",
                   "floors": {"min_move_pct": ">= 5", "min_day_rvol": ">= 3",
                              "min_price": ">= 3"}}}))
    if "1 carried a quote this pass refused" not in text:
        failures.append("the rendered breakdown does not name the refused "
                        "count, so a reader cannot reconcile it against the "
                        "quoted population")
    if "DO NOT ADD UP" in text:
        failures.append("a tally that reconciles was reported as one that does "
                        "not, so the guard fires on healthy sessions")

    # And the guard itself, on a tally that really has lost a name.
    broken = dict(tally, quoted=tally["quoted"] + 7)
    if "DO NOT ADD UP" not in "\n".join(render_midday.movers_section({
            "movers": {"rows": [], "tally": broken, "list_size": 15,
                       "rank_by": "move", "news_calls": 0,
                       "selection_note": "selection is on price",
                       "floors": {"min_move_pct": ">= 5",
                                  "min_day_rvol": ">= 3",
                                  "min_price": ">= 3"}}})):
        failures.append("seven names went missing from the tally and the "
                        "breakdown printed as though it covered them")

    print("  breakdown    every bucket is named and the counts reconcile "
          "against the quoted population, refusals included")


def claim_a_vendor_zero_is_a_measurement(failures: list[str]) -> None:
    """Zero volume is what the vendor said, not a field it failed to send.

    The four unpriced buckets tested their fields with `not q.get(...)`, so a
    vendor reported ZERO landed in no_volume or no_average_volume. Those are the
    buckets the report describes as "the pass could not price them ... these
    names were never measured", which is the opposite of what the vendor said. A
    halted name, or one that printed premarket and has not traded since, is
    exactly the case: measured, and measured at nothing.

    A zero AVERAGE volume is a third state again. It is a measurement and there
    is still nothing to divide by, so it is counted apart from both the missing
    field and the floors rather than being folded into either.
    """
    quotes = {
        "ZEROVOL.US": _quote(open=1.0, high=2.0, low=0.5, last=9.0,
                             volume=0.0, average_volume=1000.0),
        "ZEROAVG.US": _quote(open=1.0, high=2.0, low=0.5, last=9.0,
                             volume=100.0, average_volume=0.0),
        "NOVOL.US": _quote(open=1.0, high=2.0, low=0.5, last=9.0,
                           volume=None, average_volume=1000.0),
    }
    _rows, tally = scan_midday.rank_movers(quotes, set(), set(), set())

    if tally["no_volume"] != 1:
        failures.append(
            f"no_volume counted {tally['no_volume']}, expected only the name "
            "the vendor sent no volume for. A reported zero belongs somewhere "
            "that does not read as 'never measured'")
    if tally["no_average_volume"]:
        failures.append(
            f"no_average_volume counted {tally['no_average_volume']} for a name "
            "whose average volume the vendor reported as zero, so a measurement "
            "is being published as a missing field")
    if tally.get("zero_average_volume") != 1:
        failures.append(
            f"zero_average_volume counted {tally.get('zero_average_volume')}, so "
            "a name with nothing to divide by is not counted apart from one the "
            "vendor never answered for")
    if "ZEROAVG.US" not in (tally.get("examples", {}).get("zero_average_volume") or []):
        failures.append("the zero average volume bucket names no symbol, so the "
                        "count cannot be chased")

    print("  vendor zero  a reported zero is judged rather than counted as a "
          "field the vendor never sent, and a zero denominator is its own state")


def claim_the_midday_rvol_says_why_it_is_null(failures: list[str]) -> None:
    """day_rvol was the one null in the packet with no reason beside it.

    Every other null this pass writes carries a recorded reason. day_rvol did
    not, so a reader of a carry through row could not tell a name the vendor
    never carried a volume for from one it measured at zero, in the record
    another pass will compare against.
    """
    pick = _pick()
    measured = scan_midday.grade(pick, _quote(open=10.5, high=11.0, low=9.5,
                                              last=10.8, volume=500.0,
                                              average_volume=100.0))
    if measured["day_rvol"] != 5.0 or measured["day_rvol_reason"]:
        failures.append(
            f"a measurable relative volume came back {measured['day_rvol']} with "
            f"reason {measured['day_rvol_reason']!r}, expected 5.0 and no reason")

    absent = scan_midday.grade(pick, _quote(open=10.5, high=11.0, low=9.5,
                                            last=10.8, volume=None,
                                            average_volume=100.0))
    if absent["day_rvol"] is not None or "carried no volume" not in (
            absent["day_rvol_reason"] or ""):
        failures.append(
            "a quote carrying no volume produced no reason naming the field, so "
            f"the null cannot be chased: {absent['day_rvol_reason']!r}")

    zero = scan_midday.grade(pick, _quote(open=10.5, high=11.0, low=9.5,
                                          last=10.8, volume=500.0,
                                          average_volume=0.0))
    if zero["day_rvol"] is not None or "zero" not in (zero["day_rvol_reason"] or ""):
        failures.append(
            "a vendor reported average volume of zero did not say that it is a "
            f"measurement with nothing to divide by: {zero['day_rvol_reason']!r}")

    print("  rvol reason  a null relative volume names the field the vendor did "
          "not carry, and a zero denominator says it was measured")


def claim_a_name_the_vendor_never_answered_for_says_so(failures: list[str]) -> None:
    """A missing row is not a row missing a field.

    A picks ticker absent from the quote payload fell through to read_quote({}),
    which took the branch for a quote carrying no lastTradeTime and published
    "the quote carried no lastTradeTime, so how old its prices are is unknown
    rather than merely large". That tells a reader the vendor sent a quote and
    left one field out of it, when the vendor sent nothing at all.

    It is reachable on any morning: quote_delayed chunks its requests and
    returns partial data when a chunk fails, leaving those symbols out of the
    result rather than losing the batch.
    """
    quote = scan_midday.read_quote({}, ettime.now_et(), "2026-08-28", 100.0)
    quote["refused_reason"] = (
        "us-quote-delayed returned no row for this symbol at all, so nothing "
        "about its session is known. This is a name the vendor did not answer "
        "for, not a quote missing a field")
    row = scan_midday.grade(_pick(), quote)
    if "did not answer" not in (row["state_reason"] or ""):
        failures.append(
            "a pick the vendor sent no row for does not say so in its verdict: "
            f"{row['state_reason']!r}")
    if row["state"] != scan_midday.UNKNOWN:
        failures.append(f"a name with no quote graded as {row['state']} rather "
                        "than unknown")

    # And the wiring: build_packet must install that reason rather than letting
    # the bare read_quote({}) reason stand.
    source = (config.PROJECT_ROOT / "src" / "midday" / "scan_midday.py").read_text(
        encoding="utf-8")
    if "returned no row for this symbol at all" not in source:
        failures.append(
            "scan_midday no longer distinguishes a symbol the payload omitted "
            "from one whose quote lacked a timestamp, so the carry through rows "
            "can report a never-checked state as a checked one")

    print("  no row       a pick the vendor sent no quote for says that, rather "
          "than reporting a quote that was missing one field")


def claim_reach_reads_what_the_collector_asked_for(failures: list[str]) -> None:
    """"Subscribed" comes from the collector's record, not discover's intent.

    morning_reach decided the subscribed state from watchlist.json's subscribed
    flag. That is what discover MEANT to subscribe at 07:15. CRITERIA [Monitor]'s
    stale watchlist note settles that the two are different facts and says which
    one is evidence: "The file is not the evidence. What the collector asked the
    socket for is."

    2026-08-24 is the morning that made the distinction: a power cut collapsed
    the gap between the jobs, the collector read the previous session's
    watchlist and subscribed to the eight context symbols alone, and by 12:00
    the file on disk was today's and marked 42 names subscribed. Every one would
    have been captioned as a name the collector heard and the screen declined.
    """
    from collect import collect_premarket

    day = "2026-05-11"
    config.PREMARKET_DIR.mkdir(parents=True, exist_ok=True)
    collect_premarket.subscriptions_path(day).write_text(
        json.dumps({"symbols": ["HEARD.US"], "requested_count": 1,
                    "socket_cap": 50, "dropped_to_fit_cap": [],
                    "subscribed_at": f"{day}T07:20:02-04:00"}),
        encoding="utf-8")
    config.WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.WATCHLIST_PATH.write_text(
        json.dumps({"generated_at": f"{day}T07:15:05-04:00", "symbols": [
            {"symbol": "HEARD.US", "subscribed": True},
            {"symbol": "MEANT.US", "subscribed": True},
            {"symbol": "POOLED.US", "subscribed": False}]}),
        encoding="utf-8")

    context = scan_midday.morning_context(day)
    if context["subscribed"] != ["HEARD.US"]:
        failures.append(
            f"subscribed reads {context['subscribed']}, expected only the name "
            "the collector's own list carries. MEANT.US was discover's intent "
            "and no tape was collected for it")
    if not context.get("subscribed_source"):
        failures.append("the packet does not say which file the subscribed set "
                        "came from, so a reader cannot tell intent from record")
    if "MEANT.US" not in (context.get("subscribed_reason") or ""):
        failures.append(
            "a name the watchlist marks subscribed and the socket was never "
            "asked for is not named, so the 2026-08-24 shape stays invisible: "
            f"{context.get('subscribed_reason')!r}")

    print("  reach        subscribed is what the collector asked the socket for, "
          "and a watchlist that disagrees is named")


def claim_a_mover_says_how_far_the_morning_reached(failures: list[str]) -> None:
    """Three states, not two. Subscribed, pooled, and never seen.

    The collector prices only what it subscribed to, 42 of an 851 name pool on
    2026-08-31. "discover had it" and "the morning could have priced it" are
    different facts and the biggest mover of that session, EIX.US at -22.69
    percent, was in the second group.
    """
    big = dict(open=100.0, high=130.0, low=99.0, last=130.0, prev_close=100.0,
               volume=1_000_000, average_volume=100_000)
    quotes = {"SUB.US": _quote(**big), "POOL.US": _quote(**big),
              "NEW.US": _quote(**big), "NAMED.US": _quote(**big)}
    rows, tally = scan_midday.rank_movers(
        quotes, {"NAMED.US"}, {"SUB.US"}, {"SUB.US", "POOL.US"})
    reach = {row["symbol"]: row["morning_reach"] for row in rows}
    for symbol, wanted in (("SUB.US", "subscribed"),
                           ("POOL.US", "pooled_not_subscribed"),
                           ("NEW.US", "not_pooled")):
        if reach.get(symbol) != wanted:
            failures.append(f"{symbol} reads {reach.get(symbol)!r}, wanted "
                            f"{wanted!r}")
    if "NAMED.US" in reach:
        failures.append("a name the morning already published reached the "
                        "movers list, which is the half of the report about "
                        "what the morning did NOT say")
    if tally["named_this_morning"] != 1:
        failures.append(f"named_this_morning counted "
                        f"{tally['named_this_morning']}, wanted 1")
    for row in rows:
        if not row.get("morning_reach_note"):
            failures.append(f"{row['symbol']} carries a reach state with no "
                            "sentence saying what it means")
    print("  reach        subscribed, pooled and never seen are three states, "
          "and a name the morning published is excluded")


def claim_a_mover_with_no_headline_stays_on_the_list(
        failures: list[str]) -> None:
    """Selection is on price. News explains, it never decides membership.

    A news led scan cannot say it is blind to a mover with no tagged headline.
    This one can, and the sentence it says it with is asserted here because
    that sentence IS the difference between the two designs.
    """
    big = dict(open=100.0, high=130.0, low=99.0, last=130.0, prev_close=100.0,
               volume=1_000_000, average_volume=100_000)
    rows, _tally = scan_midday.rank_movers(
        {"QUIET.US": _quote(**big)}, set(), set(), set())
    if len(rows) != 1:
        failures.append(f"a name clearing every floor produced {len(rows)} rows "
                        "before news was ever fetched, so price is not what "
                        "selects")
        return

    class _Silent:
        def news(self, *_a: Any, **_k: Any) -> Any:
            from core import eodhd
            return eodhd.ApiResult([], None)

    scan_midday.attach_news(_Silent(), rows, ettime.today_et())
    if rows[0]["news"] != []:
        failures.append(f"a silent feed left news as {rows[0]['news']!r} rather "
                        "than an empty list")
    reason = rows[0].get("news_reason") or ""
    if "silence" not in reason:
        failures.append(f"a mover with no tagged story does not say the feed "
                        f"was silent: {reason!r}")
    print("  silence      a mover with no headline stays on the list and says "
          "the feed was silent rather than that there was no news")


# -------------------------------------------------------------- the renderer

def claim_a_headline_cannot_break_the_table_or_the_page(
        failures: list[str]) -> None:
    """Vendor text reaches a markdown table and an HTML page.

    A pipe closes a column early, a newline ends a row, and a tag shaped run
    becomes markup. render_report.py carries the long form of this argument for
    the morning; the midday renderer builds its own markdown, so it is asserted
    here against its own escaping.
    """
    plain = render_midday.to_markdown(_packet_with_headline("an ordinary story"))
    nasty = ('Acme | Corp <script>alert(1)</script>\n'
             '## Injected section\n'
             '| INJECT.US | +99.00% | 99.00x | 1.00 | 9B | subscribed |')
    markdown_text = render_midday.to_markdown(_packet_with_headline(nasty))

    # A headline reaches the report as a LIST ITEM, not a table cell, so the
    # hazard is not a broken column: it is a newline starting a line of its own
    # and that line being read as structure. A heading and a table row are the
    # two structures this renderer builds, so the headline tries to forge both.
    if markdown_text.count("\n## ") != plain.count("\n## "):
        failures.append(
            f"a headline changed the number of sections in the report, from "
            f"{plain.count(chr(10) + '## ')} to "
            f"{markdown_text.count(chr(10) + '## ')}")
    forged = [line for line in markdown_text.splitlines()
              if line.startswith("| INJECT.US")]
    if forged:
        failures.append(f"a headline forged a movers table row: {forged[0]!r}")

    html_text = render_midday.to_html(markdown_text, "t")
    if "<script>" in html_text:
        failures.append("a headline reached the page as a live script tag")
    if "&lt;script&gt;" not in html_text:
        failures.append("the script tag was neither escaped nor present, so it "
                        "was silently dropped rather than neutralised")
    if "<h2>Injected section</h2>" in html_text:
        failures.append("a headline became a section heading on the page")
    print("  escaping     a headline cannot forge a heading, a table row or a "
          "script tag, in the markdown or on the page")


def claim_the_report_states_its_limits_on_every_edition(
        failures: list[str]) -> None:
    """The three standing disclosures are unconditional.

    A report that names a limit only when it bites reads, on the quiet days,
    exactly like a report with no limits. That is the argument DECISIONS
    2026-08-20 made for the volume check and it applies unchanged here.
    """
    packet = _packet_with_headline("nothing interesting")
    text = render_midday.to_markdown(packet)
    for wanted, what in (
            ("whether the fill was plausible",
             "that these grades never ask whether the level was transactable"),
            ("the entry and stop as the morning published them",
             "which levels the grades used"),
            ("sequence", "how often the order of the high and the low is "
                         "unknowable"),
            ("open tolerance", "how many verdicts were decided inside the "
                               "open's own disagreement")):
        if wanted not in text:
            failures.append(f"the report never says {what} (looked for "
                            f"{wanted!r})")
    print("  disclosures  every edition states the levels used, the "
          "transactability it does not check, the sequence it cannot see and "
          "the verdicts decided too close to call")


def _packet_with_headline(title: str) -> dict[str, Any]:
    """A packet shaped exactly as build_packet writes one, with one mover."""
    graded = scan_midday.grade(
        _pick(), _quote(open=10.5, high=11.0, low=8.5, last=8.7,
                        volume=1_000_000, average_volume=200_000))
    return {
        "session_date": "2026-08-31",
        "generated_at": "2026-08-31T12:00:00-04:00",
        "run_time_et": "12:00",
        "configured_run_time": "12:00",
        "prior_session": "2026-08-28",
        "prior_closes_returned": 48_000,
        "universe_size": 2_751,
        "quotes_returned": 2_751,
        "quotes_missing": 0,
        "quote_error": None,
        "api_calls": 140,
        "price_source": {
            "endpoint": "us-quote-delayed",
            "denominator_endpoint": "eod-bulk-last-day",
            "why_not_intraday": "the vendor publishes intraday overnight",
            "denominator_note": "the bulk day is asked for by date",
            "open_is_not_the_auction": "the open is the first consolidated print",
            "extended_hours_reason": "the extended fields were stale at 08:45",
        },
        "carry_through": {
            "rows": [graded],
            "picks_found": 1,
            "states": {scan_midday.GAPPED_THROUGH: 1},
            "sequence_unknown_rows": 0,
            "sequence_unknown_note": "0 of 1 rows have an unknown sequence",
            "decided_inside_the_open_tolerance_rows": 0,
            "not_checked": ("The SKIP condition in CRITERIA [Paper], whether "
                            "the fill was plausible at all, is not computed here"),
            "picks_reason": None,
        },
        "movers": {
            "rows": [{
                "symbol": "EVIL.US", "name": "Evil Inc", "last": 130.0,
                "prev_close": 100.0, "move_pct": 30.0, "open": 100.0,
                "high": 130.0, "low": 99.0, "volume": 1_000_000,
                "average_volume": 100_000, "day_rvol": 10.0,
                "market_cap": 2e9, "morning_reach": "not_pooled",
                "morning_reach_note": "discover did not have this name",
                "news": [{"title": title, "date": "2026-08-31"}],
                "news_reason": None,
            }],
            "list_size": 15, "rank_by": "move", "news_calls": 1,
            "selection_note": "selection is on price",
            "floors": {"min_move_pct": ">= 5", "min_day_rvol": ">= 3",
                       "min_price": ">= 3"},
            "tally": {"quoted": 2_751, "refused": 0, "named_this_morning": 18,
                      "no_last_price": 0, "no_previous_close": 0,
                      "no_average_volume": 0, "no_volume": 0,
                      "below_price": 1, "below_move": 2_664, "below_rvol": 60,
                      "admitted": 1,
                      "examples": {"no_last_price": [], "no_previous_close": [],
                                   "no_average_volume": [], "no_volume": []},
                      "unpriced_note": "each count names the field"},
        },
        "morning_context": {"packet_found": True, "packet_reason": None,
                            "named_this_morning": [], "pooled": [],
                            "subscribed": [], "watchlist_reason": None},
        "quota_preflight": {},
        "build": {},
    }


def claim_no_report_prints_an_exchange_qualified_ticker(
        failures: list[str]) -> None:
    """AAOI, never AAOI.US, and in every section rather than the tables only.

    THE MORNING GOT THIS FOR FREE AND THE MIDDAY DID NOT, which is the whole
    lesson. prompt_analyst.md rule 8 tells the model to write bare tickers, and
    analyst.fallback_report strips the suffix for the mornings the model never
    runs. The 12:00 pass has NO MODEL to instruct and no fallback to inherit
    from, so nothing stripped anything: it shipped AAOI.US, AXTI.US, MSTR.US
    and nine more in its carry table while the 08:45 report about those same
    twelve picks named them AAOI, AXTI and MSTR. One set of picks, two
    spellings, and a reader with no reason to know they are the same names.

    A rule the morning obeys because a prompt says so and the midday obeys
    because somebody remembered is a rule with two chances to break, so the
    strip is glossary.bare_ticker and this claim reads the RENDERED OUTPUT
    rather than the call sites. Reading the output is the point: the defect was
    never a wrong function, it was four emission sites and one sentence of
    examples that called no function at all, and a claim written against the
    call sites would have found the four and missed the fifth.

    The pattern allows a dotted decimal, so 1.19B and -0.73 percent are not
    tickers, and matches a dot followed by two or more capitals, which is what
    an exchange qualifier is: .US, .INDX, .GBOND.
    """
    import re as _re

    from midday import render_midday

    qualified = _re.compile(r"\b[A-Z][A-Z0-9.]{0,7}\.[A-Z]{2,}\b")

    packets = sorted((config.PROJECT_ROOT / "runs").glob("*/midday_packet.json"))
    checked = 0
    for path in packets:
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
            markdown = render_midday.to_markdown(packet)
        except (OSError, ValueError, KeyError, TypeError):
            # An archived packet written before a field existed is not this
            # claim's business. A packet that renders is.
            continue
        checked += 1
        for number, line in enumerate(markdown.splitlines(), start=1):
            for hit in qualified.findall(line):
                failures.append(
                    f"{path.parent.name} midday line {number} prints "
                    f"{hit!r}, an exchange qualified ticker. The 08:45 report "
                    "names that stock without the suffix, so one set of picks "
                    f"carries two spellings: {line[:120]!r}")

    # The helper itself, on the shapes the vendor actually returns, so the
    # claim still says something on a tree with no rendered session on disk.
    for symbol, want in (("AAOI.US", "AAOI"), ("ARX", "ARX"),
                         ("VIX.INDX", "VIX"), ("US10Y.GBOND", "US10Y"),
                         ("", ""), (None, "")):
        got = glossary.bare_ticker(symbol)
        if got != want:
            failures.append(f"glossary.bare_ticker({symbol!r}) is {got!r} and "
                            f"the reader facing form is {want!r}")

    print(f"  bare ticker {checked} rendered midday report(s) name stocks the "
          "way the morning names them, with no exchange suffix anywhere")


def claim_relative_volume_is_measured_against_the_session_so_far(
        failures: list[str]) -> None:
    """day_rvol divides by the average PRO RATED to the elapsed session.

    The vendor's averageVolume covers a whole day and the quote's volume
    covers the day so far, so dividing one by the other at noon compared 150
    traded minutes against 390. A name at exactly its normal pace read 0.385,
    and CRITERIA's floor of 3 was really asking for 7.8 times normal pace. On
    2026-09-02 it rejected 77 of the 78 names that had moved 5 percent or
    more, and the owner watching the same market could see the report was
    finding nothing.

    The raw ratio is kept beside the corrected one so an older packet is
    still comparable, and the elapsed fraction is kept so the arithmetic can
    be redone by hand.
    """
    import datetime as dt

    day = dt.date(2026, 9, 2)
    noon = scan_midday.session_elapsed(ettime.at(day, 12, 0))
    if not (0.38 < noon < 0.39):
        failures.append(f"12:00 reads {noon:.4f} of the session, wanted about 0.385")
    if scan_midday.session_elapsed(ettime.at(day, 16, 0)) != 1.0:
        failures.append("the close is not a whole session")
    if scan_midday.session_elapsed(ettime.at(day, 18, 0)) != 1.0:
        failures.append("after the close reads as more than a whole session")
    # Before the open there is NO elapsed session, and until 2026-09-02 this
    # clamped to one minute of 390, which would have multiplied every
    # day_rvol by 390 on a run before 09:30. It is refused with a reason now.
    grace = criteria.load().integer("midday", "min_minutes_after_open")
    for hour, minute in ((6, 0), (9, 29), (9, 30 + grace - 1)):
        try:
            early = scan_midday.session_elapsed(ettime.at(day, hour, minute))
        except scan_midday.SessionNotOpen as exc:
            if "refused" not in str(exc) or "opens at 09:30" not in str(exc):
                failures.append(f"the refusal at {hour:02d}:{minute:02d} does not say "
                                f"what it refused or when the session opens: {exc}")
        else:
            failures.append(f"{hour:02d}:{minute:02d} read {early!r} of the session "
                            "instead of being refused as before the open")
    try:
        first = scan_midday.session_elapsed(ettime.at(day, 9, 30 + grace))
    except scan_midday.SessionNotOpen as exc:
        failures.append(f"{grace} minutes after the open was refused: {exc}")
    else:
        if not 0 < first < 0.02:
            failures.append(f"{grace} minutes in reads {first!r}")
    # An early close day divides by the session that day actually has. The
    # calendar is handed in, so this reads no cache and makes no call.
    calendar = {"ExchangeEarlyCloseDays": {
        "0": {"Date": "2026-11-27", "Holiday": "Day after Thanksgiving"}}}
    half_day = dt.date(2026, 11, 27)
    close, reason = scan_midday.session_close(half_day, calendar)
    if close != criteria.load().clock("midday", "early_close") or "early close" not in reason:
        failures.append(f"the day after Thanksgiving closes at {close}, {reason!r}")
    regular, _reason = scan_midday.session_close(day, calendar)
    if regular != criteria.load().clock("paper", "session_close"):
        failures.append(f"an ordinary day closes at {regular}")
    half_noon = scan_midday.session_elapsed(ettime.at(half_day, 12, 0), close)
    if not (0.71 < half_noon < 0.72):
        failures.append(f"12:00 on a 13:00 close reads {half_noon:.4f}, wanted 150 of 210")
    if scan_midday.session_elapsed(ettime.at(half_day, 13, 0), close) != 1.0:
        failures.append("13:00 on an early close day is not a whole session")

    # Trading at exactly its average pace: 38.46 percent of a day's average
    # volume, 38.46 percent of the way through the session. Pace is 1.0, so a
    # floor of 3 must reject it. The raw ratio, 0.3846, would have rejected it
    # too, which is why this needs the second name below to show the bug.
    at_pace = _quote(open=100.0, high=112.0, low=99.0, last=112.0,
                     prev_close=100.0, volume=38_460, average_volume=100_000)
    # Four times its normal pace. The raw ratio is 1.538, under the floor of
    # 3, so before this change it was rejected while trading at four times
    # normal on a 12 percent move.
    fast = _quote(open=100.0, high=112.0, low=99.0, last=112.0,
                  prev_close=100.0, volume=153_800, average_volume=100_000)
    rows, tally = scan_midday.rank_movers(
        {"PACE.US": at_pace, "FAST.US": fast}, set(), set(), set(), noon)
    got = {row["symbol"]: row for row in rows}
    if "FAST.US" not in got:
        failures.append("a name trading at four times its normal pace on a 12 "
                        "percent move did not clear a floor that says three")
    elif not (3.9 < got["FAST.US"]["day_rvol"] < 4.1):
        failures.append(f"four times normal pace reads "
                        f"{got['FAST.US']['day_rvol']}, wanted about 4")
    elif not (1.5 < got["FAST.US"]["day_rvol_raw"] < 1.6):
        failures.append(f"the raw ratio was not kept beside it: "
                        f"{got['FAST.US'].get('day_rvol_raw')}")
    if "PACE.US" in got:
        failures.append("a name trading at exactly its normal pace cleared a "
                        "floor of three times normal pace")
    if tally["below_rvol"] != 1:
        failures.append(f"below_rvol counted {tally['below_rvol']}, wanted 1")
    if not (0.38 < (got.get("FAST.US") or {}).get("session_elapsed", 0) < 0.39):
        failures.append("the row does not carry the elapsed fraction it was divided by")
    print("  pace         relative volume divides by the average pro rated to the "
          "elapsed session, an early close day by its own session, the raw ratio "
          "is kept beside it, and a run before the open is refused")


class _BulkApi:
    """An api whose bulk day answers with the rows it was built with."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def eod_bulk_last_day(self, exchange: str, day: Any = None):
        from core import eodhd

        return eodhd.ApiResult(self.rows, None)


def claim_a_wrong_date_row_is_dropped_and_not_the_whole_payload(
        failures: list[str]) -> None:
    """One row carrying another session's date is dropped, counted and named;
    the payload is refused only past CRITERIA [Midday] max_wrong_date_row_share.

    Until 2026-09-02 ONE wrong row raised PriorClosesUnusable and the 12:00
    pass refused to run, after the quota preflight had already cleared the
    sweep. A vendor payload of eleven thousand rows with one stale row in it
    is not a payload for another session, and the name behind that row is
    refused as unpriced rather than measured against a wrong close.
    """
    limit = criteria.load().number("midday", "max_wrong_date_row_share")

    def row(code: str, date: str) -> dict[str, Any]:
        return {"code": code, "date": date, "close": 10.0}

    good = [row(f"G{i}", "2026-09-01") for i in range(400)]
    one_bad = good + [row("STALE", "2026-08-31")]
    closes, record = scan_midday.prior_closes(_BulkApi(one_bad), "2026-09-01")
    if len(closes) != 400 or "STALE.US" in closes:
        failures.append(f"{len(closes)} closes kept from 400 good rows and one wrong one")
    if record.get("wrong_date_rows") != 1 or record.get("rows") != 401:
        failures.append(f"the payload record does not count the dropped row: {record}")
    if record.get("wrong_date_examples") != ["STALE.US"]:
        failures.append(f"the dropped row is not named: {record.get('wrong_date_examples')}")
    if not (0 < record.get("wrong_date_share", 0) <= limit):
        failures.append(f"the share {record.get('wrong_date_share')} is not under {limit}")

    too_many = good + [row(f"B{i}", "2026-08-31") for i in range(int(400 * limit) + 5)]
    try:
        scan_midday.prior_closes(_BulkApi(too_many), "2026-09-01")
    except scan_midday.PriorClosesUnusable as exc:
        if "max_wrong_date_row_share" not in str(exc):
            failures.append(f"the refusal does not name the share it refused on: {exc}")
    else:
        failures.append("a payload over the wrong date share was accepted")
    print("  bulk rows    one wrong date row is dropped, counted and named, and the "
          f"payload is refused only past a {limit:.0%} share")


def claim_a_refused_movers_list_says_so_on_the_page(failures: list[str]) -> None:
    """A packet whose movers were not measured renders the reason where the
    list would be, and prints no tally that was never counted."""
    packet = _packet_with_headline("A headline")
    packet["movers"] = dict(packet["movers"], rows=[],
                            tally={"quoted": 2_751, "admitted": 0},
                            refused_reason="the run clock reads 09:12 ET and the "
                                           "session opens at 09:30, so the movers "
                                           "list is refused")
    text = render_midday.to_markdown(packet)
    if "This list was not measured: the run clock reads 09:12 ET" not in text:
        failures.append("the refused movers list does not carry its reason")
    if "Of 2,751 universe names quoted:" in text or "cleared everything" in text:
        failures.append("a tally that was never counted was printed")
    print("  refused list a movers list refused before the open says why, where the "
          "list would be")


def claim_the_graded_table_is_not_an_execution_record(
        failures: list[str]) -> None:
    """Nothing on this page was traded, and the page has to say so.

    The owner read the table of 2026-09-03 and said he had taken no trades and
    could not tell what it was describing against the morning report. Three
    things were wrong and this holds all three.

    IT SPOKE AS AN EXECUTION RECORD. Fill, triggered, stopped out and "no
    fill" are the vocabulary of a position somebody holds, used for a price
    crossing a level nobody acted on.

    IT CALLED 12 ROWS PICKS. The morning put 3 names on a watchlist that day
    and the table carried 12 under a heading calling them the morning's picks,
    with no column saying which was which. A reader holding both pages was
    comparing a list of 3 against a list of 12. The watchlist names now stand
    in their own table, and the names the screens turned down in another that
    says outright that a row in it was not a pick.

    IT CARRIED NO DISCLAIMER AT ALL, on a page of prices and levels, while the
    morning report has carried one since it shipped.
    """
    picked = scan_midday.grade(
        _pick(ticker="AAA.US", day_eligible=1, swing_eligible=1),
        _quote(open=9.5, high=11.0, low=9.4, last=10.6))
    picked.update(_pick(ticker="AAA.US", day_eligible=1, swing_eligible=1))
    turned_down = scan_midday.grade(
        _pick(ticker="BBB.US", day_eligible=0, swing_eligible=0),
        _quote(open=9.5, high=9.8, low=9.4, last=9.6))
    turned_down.update(_pick(ticker="BBB.US", day_eligible=0, swing_eligible=0))

    packet = _packet_with_headline("nothing interesting")
    packet["carry_through"]["rows"] = [picked, turned_down]
    packet["carry_through"]["picks_found"] = 2
    text = render_midday.to_markdown(packet)

    if "Nothing here is advice" not in text or "no trade was placed" not in text:
        failures.append("the midday page carries no disclaimer saying that "
                        "nothing on it was traded")
    for wanted, what in (
            ("The names the morning put on a watchlist",
             "which names the morning actually picked"),
            ("The names the screens turned down",
             "which names the screens rejected"),
            ("A row here was not a pick",
             "that a rejected row was never a recommendation"),
            ("AAA on the day and swing screens",
             "which screen a picked name was on"),
            ("| Entry reached | Start price | Now vs start | Best vs start "
             "| Stop reached |",
             "what each outcome column measures")):
        if wanted not in text:
            failures.append(f"the report never says {what} (looked for {wanted!r})")

    # The words of a position, in the table and in the prose beneath it. The
    # packet's own field names are untouched and are not searched for here:
    # what is checked is the page.
    for banned in ("triggered after the open", "gapped through at the open",
                   "stopped out", "no fill,", "Now vs fill", "Best vs fill",
                   "vs fill", "the fill happened"):
        if banned in text:
            line = next(l for l in text.splitlines() if banned in l)
            failures.append(f"the page still describes a trade nobody placed, "
                            f"{banned!r} in: {line.strip()[:110]!r}")

    # One legend for two tables of the same columns, not two.
    legends = [line for line in text.splitlines()
               if line.startswith(glossary.LEGEND_PREFIX)
               and "Entry reached" in line]
    if len(legends) != 1:
        failures.append(f"{len(legends)} copies of the graded table's column "
                        "legend, where two tables of one shape need one")
    print("  not a trade  the page says nothing was traded, the watchlist "
          "names stand apart from the names the screens turned down, and no "
          "column claims a fill")


def claim_a_floor_names_the_biggest_mover_it_turned_down(
        failures: list[str]) -> None:
    """A count with no examples cannot be chased, and a floor is a decision.

    On 2026-09-03 the owner brought a vendor list of the day's gainers and
    asked which of them the reports should have carried. The 12:00 pass could
    answer for the names it admitted, and for the ones it never priced, and
    not at all for the 2,459 the move floor cut or the 230 the volume floor
    cut: both were bare counts. The unpriced buckets had carried examples
    since they were written, for exactly this reason, and the floors are where
    it matters most, because a floor is a decision this project made and the
    unpriced buckets are the vendor's.

    THE LARGEST MOVER, NOT THE FIRST ONE ALPHABETICALLY. The names are
    collected whole and trimmed once at the end; trimming inside the walk
    would keep whichever names the quote dict yielded first, and the question
    being asked is which big mover a floor cost.
    """
    quotes = {}
    # Two big movers on thin volume, one small mover on heavy volume, one
    # admitted. The two big ones must come back named, largest first.
    for symbol, move, volume in (("AAA.US", 20.0, 1.0), ("BBB.US", 40.0, 1.0),
                                 ("CCC.US", 0.5, 90.0), ("DDD.US", 12.0, 90.0)):
        quotes[symbol] = {
            "symbol": symbol, "name": symbol, "refused_reason": None,
            "last": 100.0 * (1 + move / 100), "prev_close": 100.0,
            "open": 100.0, "high": 120.0, "low": 99.0,
            "volume": volume * 1_000_000, "average_volume": 1_000_000,
            "market_cap": 2e9,
        }
    _rows, tally = scan_midday.rank_movers(quotes, set(), set(), set(), 0.5)
    cut = (tally.get("floor_examples") or {})
    thin = [r["symbol"] for r in cut.get("below_rvol") or []]
    if thin[:2] != ["BBB.US", "AAA.US"]:
        failures.append("the volume floor does not name the movers it turned "
                        f"down, largest first: {thin}")
    small = [r["symbol"] for r in cut.get("below_move") or []]
    if small != ["CCC.US"]:
        failures.append(f"the move floor names {small}, expected the one name "
                        "it cut")
    text = render_midday.to_markdown(_packet_with_floor_cuts(tally))
    if "The largest movers each floor turned down" not in text:
        failures.append("the report prints the floor counts and names none of "
                        "the movers behind them")
    if "BBB at +40.00%" not in text:
        failures.append(f"the report does not name the largest mover the "
                        f"volume floor cut: {text[:0]!r}")
    print(f"  floor names {len(thin)} mover(s) the volume floor cut and "
          f"{len(small)} the move floor cut are named, largest first")


def _packet_with_floor_cuts(tally: dict[str, Any]) -> dict[str, Any]:
    """The standing fixture with one pass's real tally dropped into it."""
    packet = _packet_with_headline("nothing interesting")
    packet["movers"]["tally"] = {**packet["movers"]["tally"], **tally}
    return packet


CLAIMS = [
    claim_a_gap_through_can_name_a_stop_out_and_an_intraday_fill_cannot,
    claim_the_two_fills_are_the_paper_rule_s_fills,
    claim_a_row_that_never_filled_reads_no_stop,
    claim_the_boundaries_go_the_way_criteria_writes_them,
    claim_a_close_verdict_is_flagged,
    claim_the_prior_close_is_never_the_quote_s_own_field,
    claim_a_stale_quote_is_refused_with_its_age,
    claim_a_graded_row_says_which_levels_it_used,
    claim_an_unmeasured_name_is_named_not_counted,
    claim_the_breakdown_names_every_name_it_counted,
    claim_a_vendor_zero_is_a_measurement,
    claim_the_midday_rvol_says_why_it_is_null,
    claim_a_name_the_vendor_never_answered_for_says_so,
    claim_reach_reads_what_the_collector_asked_for,
    claim_a_mover_says_how_far_the_morning_reached,
    claim_a_mover_with_no_headline_stays_on_the_list,
    claim_a_headline_cannot_break_the_table_or_the_page,
    claim_the_report_states_its_limits_on_every_edition,
    claim_no_report_prints_an_exchange_qualified_ticker,
    claim_relative_volume_is_measured_against_the_session_so_far,
    claim_a_wrong_date_row_is_dropped_and_not_the_whole_payload,
    claim_a_refused_movers_list_says_so_on_the_page,
    claim_the_graded_table_is_not_an_execution_record,
    claim_a_floor_names_the_biggest_mover_it_turned_down,
]


def main() -> int:
    failures: list[str] = []
    print("the midday pass, CRITERIA [Midday]:")
    for claim in CLAIMS:
        run_claim(failures, claim, failures)
    if failures:
        print("")
        for line in failures:
            print(f"FAIL  {line}")
        return 1
    print(f"PASS  {len(CLAIMS)} claims: the midday pass books a stop out only "
          "where the order is knowable, reads no stop on a row that never "
          "filled, takes its denominator from a named session, names every "
          "field it lost, and cannot be broken by a headline")
    return 0


if __name__ == "__main__":
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
