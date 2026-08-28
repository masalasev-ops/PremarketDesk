"""Regression test for Layer 4, the notable movers section.

Run it through the suite: `python -m tests.run_tests --only tests.test_notable`
from the project root with src on PYTHONPATH. Makes no network call and spends
no quota: every input is synthetic, the closes sidecar is written into the
sandbox, the gap statistics read is stubbed, and the exchange calendar is a
plain weekday rule so the answer is the same on any machine.

Twenty six claims, and they are grouped by what they defend rather than by the
order the code runs in. The count is in CLAIMS at the foot of the file and is
printed by main(), so this line is the one that goes stale; BUILD_PLAN.md
"Layer 4" carries it too.

The fence first, because it is the thing a later change is most likely to erode
without noticing: the section is additive to the report only, it writes no
picks row, and it shares nothing with the recall measurement.

Then the arithmetic: the square root of time scaling, the null sigma with its
reason, and the fact that a quiet name under the discovery gap floor can still
reach the section while a loud one that cleared it need not.

Then the labelling, which is the section's whole premise: no ranked list mixes
two legs, every row is dated by the leg it declares, and a row that lies about
either stops the run rather than being skipped. BUILD_PLAN 4.10 claimed that
last one was "already proven by claim_notable_legs"; it was not.
claim_notable_legs calls check() and check_packet() and never enforce(), so
nothing anywhere exercised enforce raising on a check (e) violation, writing
the marker, or re-gating delivery. It does now.

Then the degrades of 4.9: a missing sidecar, a sidecar from another session, a
collector that heard nothing, and counters the file is too old to carry. 4.9
applied to the ranked lists is the newest of them, added 2026-08-22: an empty
list has to name WHICH empty it is and how many it considered, because the two
sigma lists have come back empty on every run the section has ever made while
return_stdev_20d sits null across the database, and "short" was the only word
the report had for it.

And the disclosures a surviving row owes, which is the other half of the same
morning: the price age floor keeps a stale print off the premarket leg, and the
age of a print that CLEARS the floor is published beside its stamp rather than
left for the reader to derive from a scan clock the report does not print.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

from core import config
from core import criteria
from core import ettime
from morning import analyst
from morning import scan
from morning import verify_morning
from morning import vintage
from ops import market_today
from selection import gap_stats

_CRIT = criteria.load()

SESSION = "2026-08-20"
C1, C2, C3 = "2026-08-19", "2026-08-18", "2026-08-17"

# One quiet name and one loud one, built so the sigma ordering and the raw move
# ordering disagree. That disagreement is the point of the section carrying
# both a sigma list and a size list, and a fixture where they agreed would let
# a rank-on-the-wrong-key bug pass.
#
# QUIET moves 2 percent on each of two consecutive sessions off a 1.0 percent
# daily stdev. LOUD moves 8 percent in one session off a 10.0 percent stdev.
# Raw move: LOUD wins. Sigma: QUIET wins, 2.0 against 0.8. QUIET is also under
# the 3 percent discovery gap floor and would never be a candidate.
# DOWN and BIGMOVE exist so that each ranking key can be told from its
# inverse. Without them the fixture could not: every close in it rose, so
# list 3's abs() was never exercised and ranking on the signed move gave the
# same answer; and one subscribed name meant list 4 was a single element list,
# identical under any key and any filter. Mutation testing against the shipped
# code found all four of those ranking keys asserted by nothing.
UNIVERSE_ROWS = [
    {"symbol": "QUIET.US", "code": "QUIET", "market_cap": 900_000_000.0},
    {"symbol": "LOUD.US", "code": "LOUD", "market_cap": 400_000_000.0},
    {"symbol": "MEGA.US", "code": "MEGA", "market_cap": 3_000_000_000_000.0},
    {"symbol": "ONESHOT.US", "code": "ONESHOT", "market_cap": 800_000_000.0},
    {"symbol": "TINY.US", "code": "TINY", "market_cap": 50_000_000.0},
    {"symbol": "HEARD.US", "code": "HEARD", "market_cap": 700_000_000.0},
    # The only faller, and the largest move on either universe leg. Ranking
    # list 3 on the signed move instead of its size puts TINY first instead.
    {"symbol": "DOWN.US", "code": "DOWN", "market_cap": 2_000_000_000.0},
    # Subscribed, and the largest RAW premarket move with the smallest
    # premarket sigma. Ranking list 4 on the move instead of the sigma puts
    # this first instead of HEARD.
    {"symbol": "BIGMOVE.US", "code": "BIGMOVE", "market_cap": 600_000_000.0},
]

CLOSES = {
    # c3 -> c2 -> c1. QUIET is up 2 percent on each of the two sessions.
    "QUIET.US": {"c3": 100.0, "c2": 102.0, "c1": 104.04},
    # ONESHOT is up 2 percent on the prior session only, and flat before it.
    "ONESHOT.US": {"c3": 102.0, "c2": 102.0, "c1": 104.04},
    "LOUD.US": {"c3": 100.0, "c2": 100.0, "c1": 108.0},
    "MEGA.US": {"c3": 100.0, "c2": 100.0, "c1": 101.5},
    "TINY.US": {"c3": 100.0, "c2": 120.0, "c1": 140.0},
    "HEARD.US": {"c3": 100.0, "c2": 100.5, "c1": 101.0},
    "DOWN.US": {"c3": 100.0, "c2": 100.0, "c1": 55.0},
    "BIGMOVE.US": {"c3": 100.0, "c2": 100.0, "c1": 100.0},
    # In the sidecar and NOT in the universe, which is what a symbol delisted
    # between the Sunday rebuild and this morning looks like. 4.4 says a symbol
    # with no market cap on file is not a pass and not a fail: it was never
    # examined against the floor, it is counted separately, and it cannot
    # appear on list 2. Every other symbol here carries a cap, so without this
    # one that whole rule was asserted by nothing.
    # Its moves are small on purpose: 1.5 percent on the prior session, which
    # clears min_abs_gap_pct so it is counted against that floor, and 0.5
    # percent over two sessions so it displaces nobody on the size list.
    "NOCAP.US": {"c3": 101.0, "c2": 100.0, "c1": 101.5},
}

STATS = {
    "QUIET.US": {"return_stdev_20d": 1.0},
    "ONESHOT.US": {"return_stdev_20d": 1.0},
    "LOUD.US": {"return_stdev_20d": 10.0},
    "MEGA.US": {"return_stdev_20d": 1.0},
    "HEARD.US": {"return_stdev_20d": 1.0},
    # TINY is present with a null column: fewer than the sessions the
    # denominator needs. A different outcome from being absent entirely, which
    # is what "NOCAP" below is, and from being below the floor, which is FLAT.
    "TINY.US": {"return_stdev_20d": None},
    "FLAT.US": {"return_stdev_20d": 0.001},
    "DOWN.US": {"return_stdev_20d": 1.0},
    "BIGMOVE.US": {"return_stdev_20d": 20.0},
    "NOCAP.US": {"return_stdev_20d": 1.0},
}


# What a sidecar carrying the counters says, chosen so that no derivation over
# CLOSES could produce it. See _write_closes.
WRITTEN_COUNTS = {
    "names_with_close": {"c1": 901, "c2": 902, "c3": 903},
    "names_with_both_closes_for_leg": {"prior_session": 904, "two_session": 905},
}


def _bar(symbol: str, minute: str, close: float) -> dict[str, Any]:
    """One collector minute bar, stamped at the minute it opens.

    minute_epoch is DERIVED from the session and the minute, not left at zero.
    It was zero at first, and _collector_last turns that epoch into the row's
    price_time, so every premarket row in this fixture carried a price_time of
    1969-12-31. Twelve claims ran against that and none of them noticed, because
    none put a premarket row through vintage.check_packet. The thirteenth did,
    and check (e) caught it: "declares leg premarket as of 2026-08-20 but its
    price_time is dated 1969-12-31". A fixture whose rows could never pass the
    gate the production rows must pass is a fixture testing something else.
    """
    hour, minutes = (int(part) for part in minute.split(":"))
    when = dt.datetime(*(int(part) for part in SESSION.split("-")),
                       hour, minutes, tzinfo=ettime.ET)
    return {"symbol": symbol, "minute_et": ettime.stamp(when),
            "minute_epoch": ettime.epoch_s(when),
            "o": close, "h": close, "l": close, "c": close, "v": 1000}


def _write_closes(session: str = SESSION, stamped: str | None = None,
                  closes: dict[str, Any] | None = None,
                  counters: bool = False,
                  vendor_dates: dict[str, Any] | None = None) -> None:
    """The sidecar discover writes at 07:15, into the sandbox.

    counters=False is today's shape on disk: universe_examined and
    names_with_at_least_one_close only. The two per leg counters were added on
    2026-08-20 and the writer landed hours after that morning's run, so every
    file written before 2026-08-21 lacks them and the section has to derive
    them and say that it did.
    """
    rows = CLOSES if closes is None else closes
    payload: dict[str, Any] = {
        "generated_at": f"{session}T07:15:00-04:00",
        "session_date": stamped if stamped is not None else session,
        "sessions": {"c1": C1, "c2": C2, "c3": C3},
        "closes": rows,
        "universe_examined": len(UNIVERSE_ROWS),
        "names_with_at_least_one_close": len(rows),
        "third_session_available": True,
        # What the VENDOR said these closes are from. discover writes it from
        # 2026-08-20; the default here agrees with the calendar, which is the
        # ordinary morning. Pass vendor_dates to make them disagree, or {} to
        # write a sidecar old enough not to carry them at all.
        "vendor_dates": ({"c1": [C1], "c2": [C2], "c3": [C3]}
                         if vendor_dates is None else vendor_dates),
    }
    if not payload["vendor_dates"]:
        del payload["vendor_dates"]
    if counters:
        # DELIBERATELY not what deriving them would give. Written as the real
        # counts they were indistinguishable from the derived ones, so the
        # claim that the block reads them when they are there and derives them
        # when they are not could not tell the two apart and passed either way.
        # These are the numbers discover would have written; the section must
        # republish them rather than recount, which is what BUILD_PLAN asks for
        # and is only checkable when the two answers differ.
        payload["names_with_close"] = WRITTEN_COUNTS["names_with_close"]
        payload["names_with_both_closes_for_leg"] = \
            WRITTEN_COUNTS["names_with_both_closes_for_leg"]
    path = config.DATA_DIR / f"universe-closes-{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _candidates() -> list[dict[str, Any]]:
    """The twelve-name screen output, reduced to the two names that matter here.

    HEARD is a candidate and is on the day watchlist, so a premarket row for it
    carries the mark. LOUD is not a candidate at all, so its row is NOT CHECKED
    for a catalyst rather than being called uncatalysed.
    """
    return [
        {"symbol": "HEARD.US", "price": 103.0, "prior_close": 101.0,
         "gap_pct": 1.9802, "day_eligible": True, "swing_eligible": False,
         "catalyst_found": True, "catalyst_error": None,
         "headlines": [{"title": "HEARD raises guidance"}]},
    ]


def _run(bars: dict[str, list[dict[str, Any]]] | None = None,
         candidates: list[dict[str, Any]] | None = None,
         session: str = SESSION,
         universe: list[dict[str, Any]] | None = None,
         stats: dict[str, dict[str, Any]] | None = None,
         ) -> tuple[dict[str, Any], scan.Packet, list[dict[str, Any]]]:
    """One assembly against the fixture, with the database and the clock stubbed.

    gap_stats.load_all is replaced rather than seeded, because the real one
    calls store.init, which runs an executescript and an UPDATE and commits.
    The point here is the section's arithmetic, not SQLite's. Pass stats to
    replace the whole table, which is how the shipped morning is reproduced: a
    database whose return_stdev_20d is null on every row.

    The CLOCK is stubbed to 08:45 on the fixture's session, which is when the
    scan actually runs. Without it the fixture's 08:40 bars are hours old
    against the wall clock and the premarket leg drops every one of them for a
    stale price, so the whole leg went missing depending on what time of day
    the suite happened to run. A fixture that answers differently at 09:00 and
    at 21:00 is not a fixture.
    """
    if bars is None:
        bars = {"HEARD.US": [_bar("HEARD.US", "08:40", 103.0)],
                "BIGMOVE.US": [_bar("BIGMOVE.US", "08:40", 110.0)],
                "SPY.US": [_bar("SPY.US", "08:40", 700.0)]}
    rows = _candidates() if candidates is None else candidates
    table = STATS if stats is None else stats
    real_stats, real_clock = gap_stats.load_all, ettime.now_et
    gap_stats.load_all = lambda as_of=None: dict(table)
    ettime.now_et = lambda: dt.datetime(
        *(int(part) for part in session.split("-")), 8, 45, tzinfo=ettime.ET)
    try:
        packet = scan.Packet()
        block = scan.notable_movers(
            session, {"symbols": UNIVERSE_ROWS if universe is None else universe},
            bars, rows, packet)
    finally:
        gap_stats.load_all, ettime.now_et = real_stats, real_clock
    return block, packet, rows


def _report(failures: list[str]) -> int:
    for failure in failures:
        print(f"FAIL  {failure}")
    return 1


# --------------------------------------------------------------- the fence

def claim_nothing_in_the_section_reaches_picks(failures: list[str]) -> None:
    """No name that appears only in this section can become a picks row.

    4.1's hardest rule, and the one with the worst consequence if it is ever
    eroded: picks is the record of what the trading SCREEN claimed, and
    pool_recall measures the morning against it. A briefing name written into
    picks would be counted as something the screen selected and would corrupt
    the recall measurement permanently, because there is no column that says
    which rows were briefing names.

    Asserted structurally rather than by running write_picks, because the
    guarantee wanted is that the section's names never reach it by ANY route,
    and a single run proves only that they did not on one morning.
    """
    import ast
    import pathlib

    source = pathlib.Path(scan.__file__).read_bytes().decode("utf-8")
    tree = ast.parse(source)
    write_picks = next((n for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name == "write_picks"),
                       None)
    if write_picks is None:
        failures.append("scan.write_picks is gone, so this claim describes a "
                        "module that no longer exists")
        return
    names = {n.id for n in ast.walk(write_picks) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(write_picks) if isinstance(n, ast.Attribute)}
    consts = {n.value for n in ast.walk(write_picks)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    if "notable_movers" in names | attrs | consts:
        failures.append("write_picks now mentions notable_movers. The briefing "
                        "names must never reach picks: pool_recall measures the "
                        "morning against that table and there is no column that "
                        "says which rows were briefing names.")

    # And the section itself must not reach into the picks machinery.
    block = next((n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "notable_movers"),
                 None)
    if block is None:
        failures.append("scan.notable_movers is gone")
        return
    called = {n.func.attr for n in ast.walk(block)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    called |= {n.func.id for n in ast.walk(block)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for forbidden in ("write_picks", "score_candidate", "evaluate_eligibility",
                      "upsert"):
        if forbidden in called:
            failures.append(f"notable_movers calls {forbidden}, which is outside "
                            "the fence in BUILD_PLAN 4.1")

    print("  fence        write_picks does not know the section exists, and the "
          "section calls nothing that scores, screens or writes a row")


def claim_the_section_never_imports_pool_recall(failures: list[str]) -> None:
    """No leg reads pool_recall.json and nothing in the section imports it.

    4.1: the fence around the recall measurement needs nothing to hold it,
    because there is no connection to sever. This is what keeps that true.
    """
    import ast
    import pathlib

    source = pathlib.Path(scan.__file__).read_bytes().decode("utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported += [f"{node.module}.{a.name}" for a in node.names]
    offenders = [name for name in imported if "pool_recall" in name]
    if offenders:
        failures.append(f"scan.py imports {offenders}, which puts the briefing "
                        "section and the recall measurement in one module")
    if "pool_recall.json" in source:
        failures.append("scan.py names pool_recall.json, which no leg may read")

    print(f"  no recall    {len(imported)} imports in scan.py and not one of them "
          "is pool_recall")


# ---------------------------------------------------------- the arithmetic

def claim_a_two_session_move_is_scaled_by_the_root_of_its_span(
        failures: list[str]) -> None:
    """A name up 2 percent on each of two sessions beats one up 2 percent on one.

    4.3.1. The denominator is a ONE DAY return standard deviation, so an n
    session move is divided by that times the square root of n. Without the
    scaling the two session leg would overstate every sustained mover by the
    square root of 2; with it, a two session move is directly comparable to a
    one session one.

    QUIET is up 2 percent on each of the last two sessions, so its two session
    move is 4.04 percent against a 1.0 percent daily stdev: 4.04 / sqrt(2) =
    2.857 sigma. ONESHOT is up the same 2 percent on the prior session and flat
    before it, so its two session move is the same 2.0 percent: 2.0 / sqrt(2) =
    1.414 sigma. Both carry an identical prior_session sigma of 2.0, which is
    what makes this a test of the SPAN and not of the move.
    """
    block, _packet, _rows = _run()
    by_leg: dict[str, dict[str, Any]] = {}
    for row in block["rows"]:
        by_leg.setdefault(row["leg"], {})[row["symbol"]] = row

    two = by_leg.get("two_session") or {}
    quiet, oneshot = two.get("QUIET.US"), two.get("ONESHOT.US")
    if not quiet or not oneshot:
        failures.append("QUIET and ONESHOT are not both on the two_session leg, "
                        f"so the scaling was never exercised: {sorted(two)}")
        return
    if abs((quiet["move_sigma"] or 0) - 2.8567) > 0.01:
        failures.append(f"a 4.04 percent two session move on a 1.0 percent daily "
                        f"stdev scaled to {quiet['move_sigma']}, where "
                        "4.04 / sqrt(2) is 2.857")
    if abs((oneshot["move_sigma"] or 0) - 1.4142) > 0.01:
        failures.append(f"a 2.0 percent two session move on a 1.0 percent daily "
                        f"stdev scaled to {oneshot['move_sigma']}, where "
                        "2.0 / sqrt(2) is 1.414")
    if not (quiet["move_sigma"] > oneshot["move_sigma"]):
        failures.append("a name up 2 percent on each of two sessions does not "
                        "outrank one up 2 percent on a single session, which is "
                        "the ordering 4.3.1 exists to produce")

    # The one session leg divides by sqrt(1), so the two are identical there.
    prior = by_leg.get("prior_session") or {}
    pair = [prior.get("QUIET.US"), prior.get("ONESHOT.US")]
    if all(pair) and pair[0]["move_sigma"] != pair[1]["move_sigma"]:
        failures.append("two names with the same prior session move and the same "
                        "stdev carry different prior_session sigmas: "
                        f"{pair[0]['move_sigma']} and {pair[1]['move_sigma']}")

    print(f"  root of span two sessions at 2 percent each reads "
          f"{quiet['move_sigma']} sigma against {oneshot['move_sigma']} for the "
          "same move made once")


def claim_a_move_sigma_is_null_with_its_reason_and_never_substituted(
        failures: list[str]) -> None:
    """Six null outcomes, six reasons, and never a number standing in.

    They are six and not one because the fixes differ: a symbol absent from the
    gap statistics table was never measured, a table nobody could open is a
    database fault rather than a fact about any symbol, a symbol whose stdev is
    under min_return_stdev_pct has barely moved in twenty sessions and would
    otherwise report an enormous sigma on any move at all, a null move has
    nothing to scale, and a null COLUMN splits again into a short history and a
    row written before the column was computed.

    That last split is not hypothetical. return_stdev_20d was added to
    gap_stats.py on 2026-08-17 and the last rebuild ran on 2026-08-16, so all
    10,997 rows in the live database are null and NOT ONE of them is null for
    the reason this used to give. Telling a reader that 10,997 names each have
    fewer than twenty sessions of history is not a smaller mistake for being
    repeated.

    min_return_stdev_pct is applied HERE and nowhere else: gap_stats stores the
    raw value at any magnitude, so this is the only place in the project that
    floor has ever been read.
    """
    floor = _CRIT.number("notable", "min_return_stdev_pct")

    value, reason = scan.move_sigma(5.0, {"return_stdev_20d": 2.5}, 1)
    if value != 2.0 or reason is not None:
        failures.append(f"an ordinary 5 percent move on a 2.5 stdev gave "
                        f"{value!r} with reason {reason!r}, expected 2.0 and None")

    for label, args, needle in (
        ("a symbol absent from gap_stats", (5.0, None, 1),
         "no gap statistics row"),
        # A null column has three causes and they are three, not one. Every
        # row in the live database is null because the column was added after
        # the last rebuild, and the reason used to tell the reader that all
        # 10,997 names have too little history instead.
        ("a null column on a row that records no session count",
         (5.0, {"return_stdev_20d": None}, 1), "records no session count"),
        ("a null column on a short history",
         (5.0, {"return_stdev_20d": None, "sessions_used": 4}, 1),
         "fewer than"),
        ("a null column on a long history",
         (5.0, {"return_stdev_20d": None, "sessions_used": 250}, 1),
         "written before it was computed"),
        ("a stdev under the floor", (5.0, {"return_stdev_20d": floor / 2}, 1),
         "min_return_stdev_pct"),
        ("a null move", (None, {"return_stdev_20d": 2.5}, 1), "no move"),
        ("an unreadable table",
         (5.0, None, 1, "the gap statistics table could not be read"),
         "could not be read"),
    ):
        value, reason = scan.move_sigma(*args)
        if value is not None:
            failures.append(f"{label} produced a sigma of {value!r} rather than "
                            "a null. A substituted number here ranks a name on "
                            "evidence nobody has.")
        if not reason or needle not in reason:
            failures.append(f"{label} produced reason {reason!r}, which does not "
                            f"name {needle!r}, so a reader cannot tell which of "
                            "the four absences this is")

    # Exactly on the floor is not below it.
    value, reason = scan.move_sigma(5.0, {"return_stdev_20d": floor}, 1)
    if value is None:
        failures.append(f"a stdev of exactly {floor}, which is the floor itself, "
                        f"was refused: {reason}")

    print("  null sigma   six absences, six reasons, a null column split three "
          f"ways, and a stdev sitting exactly on {floor} still divides")


def claim_a_quiet_name_under_the_discovery_floor_can_still_appear(
        failures: list[str]) -> None:
    """The section is not the screen, and its floor is unusualness, not size.

    4.10: "A name moving under the 3 percent discovery gap floor appears in it
    when its move_sigma is high." QUIET moves 2.0 percent, which discover would
    never look at, and reads 2.0 sigma against its own 1.0 percent daily
    volatility. LOUD moves 8 percent, which clears every gap floor in the
    project, and reads 0.8 sigma against its own 10 percent volatility. The
    sigma list has to prefer QUIET, or the section is a second gap screen.
    """
    block, _packet, _rows = _run()
    ranked = block["lists"]["prior_session_by_sigma"]
    if "QUIET.US" not in ranked:
        failures.append("a 2.0 percent move at 2.0 sigma is absent from the "
                        f"sigma list: {ranked}. The discovery gap floor is 3 "
                        "percent and this section does not use it.")
        return
    if "LOUD.US" in ranked and ranked.index("LOUD.US") < ranked.index("QUIET.US"):
        failures.append("an 8 percent move at 0.8 sigma outranks a 2 percent "
                        f"move at 2.0 sigma: {ranked}. The list is ranking on "
                        "the move rather than on the sigma.")

    # And the size list orders the other way round, which is what makes the two
    # lists worth having separately. Its own ordering is asserted in
    # claim_each_list_ranks_on_the_key_it_names.
    size = block["lists"]["two_session_by_move"]
    if "TINY.US" not in size:
        failures.append(f"the 40 percent two session mover is absent from the "
                        f"size list: {size}")

    print(f"  under floor  a 2 percent move at 2.0 sigma leads the sigma list "
          f"{ranked}, and the size list carries the 40 percent mover")


# ---------------------------------------------------------- the labelling

def claim_each_list_ranks_on_the_key_it_names(failures: list[str]) -> None:
    """All four ranking keys, each told apart from its inverse.

    Mutation testing against the shipped section found three of the four
    asserted by nothing: list 2 ranked by minus the market cap published the
    five SMALLEST caps and no claim noticed; list 3 ranked on the signed move
    instead of its size lost every large decliner and no claim noticed, because
    every close in the fixture rose and abs() was never exercised; and list 4
    was a one element list, identical under any key and any filter, because the
    fixture subscribed one non context symbol.

    So the fixture now carries a faller with the largest move on either
    universe leg, and a second subscribed symbol with the largest RAW premarket
    move and the smallest premarket sigma. Each assertion below is chosen so
    that the inverse key gives a different answer.

    The expected leg of each list is written out HERE rather than read from
    scan.leg_of_list_key. Reading it from the code is what made
    claim_no_ranked_list_mixes_two_legs a tautology: it re-derived the leg from
    the same table the row was stamped from, so a list that ranked one leg and
    labelled another stayed green through three separate mutations.
    """
    _write_closes()
    block, _packet, _rows = _run()
    lists = block["lists"]
    rows = {(r["leg"], r["symbol"]): r for r in block["rows"]}

    expected_leg = {
        "prior_session_by_sigma": "prior_session",
        "prior_session_by_market_cap": "prior_session",
        "two_session_by_move": "two_session",
        "premarket_by_sigma": "premarket",
    }
    if set(expected_leg) != set(scan.NOTABLE_LISTS):
        failures.append(f"the section emits lists {sorted(scan.NOTABLE_LISTS)} "
                        f"and this claim knows {sorted(expected_leg)}")
    # Checked through selected_by, not through membership. A symbol can hold a
    # prior_session row because a DIFFERENT list put one there, so "it has a
    # prior_session row" stays true when list 1 stamps its own picks
    # two_session, which is the mutation that walked past the first version of
    # this check.
    for name, leg in expected_leg.items():
        for symbol in lists.get(name, []):
            owning = [row for row in block["rows"]
                      if row["symbol"] == symbol and name in row["selected_by"]]
            if not owning:
                failures.append(f"{symbol} is on {name} and no row records that "
                                f"{name} chose it")
                continue
            for row in owning:
                if row["leg"] != leg:
                    failures.append(
                        f"{name} ranks the {leg} leg and the row it chose "
                        f"{symbol} for is stamped {row['leg']}. A list that "
                        "ranks one window and labels another is the exact thing "
                        "the leg labels exist to prevent.")

    # 1. the SIZE of the sigma on the prior session leg, so the faller leads.
    #    Ranking on the signed sigma published the five largest RISERS and
    #    dropped every large decliner, which on 2026-08-28 cost this list HRL
    #    at -8.00 sigma, the second most unusual move in the universe.
    sigma_list = lists["prior_session_by_sigma"]
    values = [abs(rows[("prior_session", s)]["move_sigma"]) for s in sigma_list
              if ("prior_session", s) in rows]
    if values != sorted(values, reverse=True):
        failures.append(f"list 1 is not sorted by the size of the sigma: {values}")
    if sigma_list and sigma_list[0] != "DOWN.US":
        failures.append(f"list 1 leads with {sigma_list[0]} where DOWN fell 45 "
                        "percent at 45 sigma against QUIET's 2.0. Ranking on "
                        "the signed sigma puts the largest riser first and "
                        "drops every large decliner off the unusualness list.")
    # The sigma key is still told apart from the raw move. QUIET moved 2.0
    # percent at 2.0 sigma and LOUD moved 8 at 0.8, so a list ranking on the
    # move carries LOUD and drops QUIET, and this list must do the opposite.
    if "QUIET.US" not in sigma_list or "LOUD.US" in sigma_list:
        failures.append(f"list 1 holds {sigma_list}, and QUIET at 2.0 sigma "
                        "belongs on it while LOUD at 0.8 does not. Ranking on "
                        "the size of the raw MOVE rather than of the sigma "
                        "swaps exactly those two.")

    # 2. market cap descending, and the LARGEST first. Ranking on minus the cap
    #    publishes the smallest and was caught by nothing before this.
    cap_list = lists["prior_session_by_market_cap"]
    caps = [rows[("prior_session", s)]["market_cap"] for s in cap_list
            if ("prior_session", s) in rows]
    if caps != sorted(caps, reverse=True):
        failures.append(f"list 2 is not sorted by market cap descending: {caps}")
    if cap_list and cap_list[0] != "MEGA.US":
        failures.append(f"list 2 leads with {cap_list[0]} where MEGA carries the "
                        "largest cap in the fixture at 3 trillion. Ranking on "
                        "minus the cap publishes the smallest instead.")
    if "HEARD.US" in cap_list:
        failures.append("HEARD moved 0.4975 percent, under "
                        f"{_CRIT.number('notable', 'min_abs_gap_pct')}, and is "
                        "on the market cap list anyway")
    if "NOCAP.US" in cap_list:
        failures.append("NOCAP has no market cap on file and is on the list "
                        "that ranks by market cap")
    if block.get("names_without_market_cap") != 1:
        failures.append(
            "the section counted "
            f"{block.get('names_without_market_cap')!r} symbol(s) over the move "
            "floor with no market cap where the fixture carries one. 4.4 says "
            "that is not a pass and not a fail: it was never examined against "
            "the floor and is counted separately.")
    capless = [r for r in block["rows"] if r["symbol"] == "NOCAP.US"]
    if not capless:
        failures.append("the symbol with no market cap reached no list at all, "
                        "so its row reason is untested")
    for row in capless:
        if row["market_cap"] is not None:
            failures.append(f"NOCAP carries market_cap {row['market_cap']!r}")
        if "never examined" not in (row["market_cap_reason"] or ""):
            failures.append("NOCAP's row does not say its cap was never "
                            f"examined: {row['market_cap_reason']!r}")

    # 3. the SIZE of the two session move, so the faller leads.
    size_list = lists["two_session_by_move"]
    sizes = [abs(rows[("two_session", s)]["move_pct"]) for s in size_list
             if ("two_session", s) in rows]
    if sizes != sorted(sizes, reverse=True):
        failures.append(f"list 3 is not sorted by the size of the move: {sizes}")
    if size_list and size_list[0] != "DOWN.US":
        failures.append(f"list 3 leads with {size_list[0]} where DOWN moved 45 "
                        "percent against TINY's 40. Ranking on the signed move "
                        "puts the riser first and drops every large decliner "
                        "off the size list.")

    # 4. premarket SIGMA, not the raw move.
    premarket_list = lists["premarket_by_sigma"]
    if premarket_list and premarket_list[0] != "HEARD.US":
        failures.append(
            f"list 4 leads with {premarket_list[0]}. HEARD moved 1.98 percent at "
            "1.98 sigma and BIGMOVE moved 10 percent at 0.5, so ranking on the "
            "raw move puts BIGMOVE first and this list is the section's "
            "headline measure.")
    if len(premarket_list) < 2:
        failures.append(f"list 4 holds {len(premarket_list)} name(s), and a one "
                        "element list is identical under any ranking key")

    print(f"  ranking keys sigma leads with {sigma_list[0] if sigma_list else None}, "
          f"cap with {cap_list[0] if cap_list else None}, size with "
          f"{size_list[0] if size_list else None}, premarket with "
          f"{premarket_list[0] if premarket_list else None}")


def claim_the_premarket_sigma_list_ranks_on_the_size_of_the_move(
        failures: list[str]) -> None:
    """List 4 leads with the biggest premarket move whichever way it went.

    The shared fixture cannot ask this. Its only faller, DOWN, sits on the
    universe legs and is not subscribed, so both subscribed names moved UP and
    the signed ordering and the size ordering agreed on every run. That is
    precisely how the defect survived: list 3 was corrected to abs() when
    mutation testing found it, and lists 1 and 4 were left ranking on the sign
    because no claim here could see the difference.

    So this one builds a two name premarket leg where the orderings disagree.
    SLIDE falls 4 percent at 4.0 sigma and RISE gains 2 at 2.0, so the size
    ordering leads with SLIDE and the signed ordering leads with RISE and puts
    the larger move last. On 2026-08-28 the live section took the signed
    ordering and published five names at 0.26 sigma and below while MNSO sat
    on the same leg at -2.51.
    """
    universe = [
        {"symbol": "RISE.US", "code": "RISE", "market_cap": 800_000_000.0},
        {"symbol": "SLIDE.US", "code": "SLIDE", "market_cap": 900_000_000.0},
    ]
    closes = {
        "RISE.US": {"c3": 100.0, "c2": 100.0, "c1": 100.0},
        "SLIDE.US": {"c3": 100.0, "c2": 100.0, "c1": 100.0},
    }
    stats = {"RISE.US": {"return_stdev_20d": 1.0},
             "SLIDE.US": {"return_stdev_20d": 1.0}}
    bars = {"RISE.US": [_bar("RISE.US", "08:40", 102.0)],
            "SLIDE.US": [_bar("SLIDE.US", "08:40", 96.0)],
            "SPY.US": [_bar("SPY.US", "08:40", 700.0)]}

    _write_closes(closes=closes)
    block, _packet, _rows = _run(bars=bars, candidates=[], universe=universe,
                                 stats=stats)
    premarket = block["lists"]["premarket_by_sigma"]
    rows = {(r["leg"], r["symbol"]): r for r in block["rows"]}

    if premarket != ["SLIDE.US", "RISE.US"]:
        failures.append(
            f"list 4 is {premarket} where SLIDE moved -4 percent at -4.0 sigma "
            "and RISE moved 2 at 2.0. Ranking on the signed sigma leads with "
            "RISE and puts the larger move last, which is how a morning of "
            "decliners publishes its five quietest names.")

    # The SIGN is not lost by ranking on the size: the row still carries it,
    # because the reader has to see which way the name went.
    slide = rows.get(("premarket", "SLIDE.US")) or {}
    if (slide.get("move_sigma") or 0) >= 0:
        failures.append(f"SLIDE's row carries move_sigma "
                        f"{slide.get('move_sigma')!r}, and the ordering is "
                        "taken on the size only so that the row can keep the "
                        "sign the reader needs")

    print(f"  premarket    list 4 leads with {premarket[0] if premarket else None} "
          f"at {slide.get('move_sigma')} sigma, ahead of the smaller riser")


def claim_no_ranked_list_mixes_two_legs(failures: list[str]) -> None:
    """Every list ranks within one leg, and a row carries one leg and one date.

    4.4. Ranking a premarket move against a prior session one would order a
    fresher window against an older one, and would put the collector names,
    already selected for gap propensity and news, into the same ordering as the
    thousands nothing selected. They would dominate systematically and the
    section would restate the watchlist it exists not to restate.

    Deduplication is WITHIN a leg and never across them: a name selected by two
    lists on one leg is one row carrying both reasons, and a name selected on
    two legs stays two rows, because they are two measurements of different
    windows at different vintages.
    """
    block, _packet, _rows = _run()
    rows = {(r["leg"], r["symbol"]): r for r in block["rows"]}
    if len(rows) != len(block["rows"]):
        failures.append("two rows share a leg and a symbol, so deduplication "
                        "within a leg is not happening")

    for name, chosen in block["lists"].items():
        leg = scan.leg_of_list_key(name)
        for symbol in chosen:
            row = rows.get((leg, symbol))
            if row is None:
                failures.append(f"{symbol} is on list {name} and has no row on "
                                f"the {leg} leg")
                continue
            if row["leg"] != leg:
                failures.append(f"{symbol} is on list {name}, which ranks the "
                                f"{leg} leg, and its row says {row['leg']}")
            if name not in row["selected_by"]:
                failures.append(f"{symbol}'s row does not record that {name} "
                                f"chose it: {row['selected_by']}")

    # A name on two lists of one leg is one row carrying both reasons.
    doubled = [r for r in block["rows"] if len(r["selected_by"]) > 1]
    for row in doubled:
        legs = {scan.leg_of_list_key(n) for n in row["selected_by"]}
        if len(legs) != 1:
            failures.append(f"{row['symbol']}'s single row carries reasons from "
                            f"two legs: {row['selected_by']}")

    # A collector name reaches list 4. It may also reach list 1, because the
    # prior session leg is universe wide and a subscribed name is a universe
    # name like any other; what must never happen is its PREMARKET measurement
    # reaching a universe list. So HEARD is checked to carry two rows with two
    # different numbers over two different windows, which is 4.4's "a name
    # selected on two different legs stays TWO rows" made concrete.
    premarket = block["lists"]["premarket_by_sigma"]
    if "HEARD.US" not in premarket:
        failures.append(f"the one subscribed name is absent from list 4: {premarket}")
    universe_row = rows.get(("prior_session", "HEARD.US"))
    collector_row = rows.get(("premarket", "HEARD.US"))
    if universe_row and collector_row:
        if abs((universe_row["move_pct"] or 0) - 0.4975) > 0.01:
            failures.append("HEARD's prior_session row reads "
                            f"{universe_row['move_pct']} where c2 to c1 is 0.4975 "
                            "percent. A premarket number on a universe leg is "
                            "the exact confusion the leg labels exist to stop.")
        if abs((collector_row["move_pct"] or 0) - 1.9802) > 0.01:
            failures.append("HEARD's premarket row reads "
                            f"{collector_row['move_pct']} where c1 to the "
                            "collector price is 1.9802 percent")
        if universe_row["as_of_session"] == collector_row["as_of_session"]:
            failures.append("one name's two rows carry the same as_of_session, "
                            "so the two windows are indistinguishable")

    stamps = {r["leg"]: r["as_of_session"] for r in block["rows"]}
    if stamps.get("premarket") != SESSION:
        failures.append(f"a premarket row is stamped {stamps.get('premarket')} "
                        f"rather than today, {SESSION}")
    for leg in ("prior_session", "two_session"):
        if leg in stamps and stamps[leg] != C1:
            failures.append(f"a {leg} row is stamped {stamps[leg]} rather than "
                            f"c1's session, {C1}. as_of_session names the NEWEST "
                            "datum in the row, and both universe legs end at c1.")

    print(f"  one leg each {len(block['rows'])} rows over "
          f"{len({r['leg'] for r in block['rows']})} legs, no list mixing two, "
          f"and {len(doubled)} row(s) carrying more than one reason")


def claim_a_mis_stamped_notable_row_stops_the_run(failures: list[str]) -> None:
    """enforce() refuses a lying row, writes the marker, and re-gates delivery.

    BUILD_PLAN 4.10 said this was "already proven by claim_notable_legs". It was
    not: that claim calls check() and check_packet() and never enforce(), so
    until this was written nothing anywhere exercised enforce RAISING on a check
    (e) violation, rewriting data/UNVERIFIED, or describe() rendering the
    section's own line. A gate nobody has watched fail is not known to be a
    gate, which this project learned when conftest.redirect_captured_paths
    turned out to be asserted by nothing.

    The marker is pointed at a temporary file. The real delivery gate is never
    touched.
    """
    import tempfile
    import pathlib

    stubbed = market_today.decide
    original = verify_morning.UNVERIFIED_MARKER
    market_today.decide = lambda details, day: (day.weekday() < 5, "stubbed")
    with tempfile.TemporaryDirectory() as raw:
        marker = pathlib.Path(raw) / "UNVERIFIED"
        verify_morning.UNVERIFIED_MARKER = marker
        try:
            cases = (
                ("a prior_session move stamped as premarket",
                 {"symbol": "QUIET.US", "leg": "premarket", "as_of_session": C1}),
                ("a row with no leg at all",
                 {"symbol": "QUIET.US", "as_of_session": C1}),
                ("a row whose leg is not a leg",
                 {"symbol": "QUIET.US", "leg": "three_session",
                  "as_of_session": C1}),
            )
            for label, row in cases:
                marker.unlink(missing_ok=True)
                try:
                    vintage.enforce({
                        "session_date": SESSION,
                        "candidates": [],
                        "market_snapshot": [],
                        "notable_movers": {"rows": [row]},
                    })
                    failures.append(f"{label} passed enforce(), so it would have "
                                    "reached the model and the report")
                except vintage.StaleDataError:
                    if not marker.is_file():
                        failures.append(f"{label} raised but wrote no marker, so "
                                        "delivery was not re-gated")
                    elif "notable" not in marker.read_text(encoding="utf-8").lower():
                        failures.append(f"{label} wrote a marker that does not "
                                        "name the section the row came from")

            # And an honest row passes, or the gate is refusing everything.
            marker.unlink(missing_ok=True)
            try:
                vintage.enforce({
                    "session_date": SESSION,
                    "candidates": [],
                    "market_snapshot": [],
                    "notable_movers": {"rows": [
                        {"symbol": "QUIET.US", "leg": "prior_session",
                         "as_of_session": C1}]},
                })
            except vintage.StaleDataError as exc:
                failures.append(f"an honest prior_session row stamped {C1} was "
                                f"refused: {exc}")
            if marker.exists():
                failures.append("a clean section wrote the gate marker")
        finally:
            market_today.decide = stubbed
            verify_morning.UNVERIFIED_MARKER = original

    if original.exists():
        print(f"  the real gate marker is untouched at {original}")
    print("  enforce      a mis-stamped, an unlabelled and an unrecognised leg "
          "each raise, rewrite the gate marker and stop the chain")


def claim_a_stale_collector_print_is_not_a_notable_move(
        failures: list[str]) -> None:
    """The section holds the same price age floor the candidate path holds.

    scan.drop_stale_prices removes a candidate whose last collector print is
    older than [Price age] max_price_age_seconds, and its docstring says why the
    vintage gate cannot do this job: a print from 07:22 is genuinely inside
    today's premarket window and passes every check vintage makes, and it is
    still not this morning's price at 08:45. That is what a collector killed at
    08:10 leaves behind.

    The premarket leg reads bars_by_symbol directly rather than the candidate
    list, on purpose, because every subscribed name is eligible for it. So it
    reached straight past drop_stale_prices and published as notable premarket
    moves the very prices the scan had already rejected two hundred lines
    earlier, on the same morning, off the same bars. One rule, one clock, both
    readers.

    The count is published rather than the drop being silent, because a name
    missing from the leg and a name the collector never heard are different
    facts.
    """
    limit = _CRIT.number("price_age", "max_price_age_seconds")
    fresh = _bar("HEARD.US", "08:40", 103.0)
    old = _bar("QUIET.US", "07:00", 120.0)

    _write_closes()
    block, packet, _rows = _run(bars={"HEARD.US": [fresh], "QUIET.US": [old]})

    premarket = {r["symbol"] for r in block["rows"] if r["leg"] == "premarket"}
    if "QUIET.US" in premarket:
        failures.append(
            f"a print {limit:,.0f}s past the floor was published as a notable "
            "premarket move. drop_stale_prices had already refused that same "
            "bar for the candidate path on the same morning.")
    if "HEARD.US" not in premarket:
        failures.append("a five minute old print was dropped too, so the floor "
                        "is refusing everything rather than the stale ones")
    if block.get("premarket_prices_too_old") != 1:
        failures.append("the section counted "
                        f"{block.get('premarket_prices_too_old')} stale print(s) "
                        "where the fixture carries one. A silent drop reads "
                        "exactly like a symbol the collector never heard.")
    if not any("price age" in note for note in packet.gaps):
        failures.append(f"no packet gap names the price age floor: {packet.gaps}")

    # And the floor is the CRITERIA one, not a number written here. A print
    # exactly on the limit is inside it, the same way the candidate path reads
    # it: drop_stale_prices refuses `age > limit`, not `age >= limit`.
    block, _packet, _rows = _run(bars={"HEARD.US": [fresh]})
    if not [r for r in block["rows"] if r["leg"] == "premarket"]:
        failures.append("a fresh print alone produced no premarket row at all")

    print(f"  price age    a print past the {limit:,.0f}s floor is left off the "
          "premarket leg and counted, and a fresh one is published")


def claim_a_premarket_row_carries_the_age_of_its_price(
        failures: list[str]) -> None:
    """The row publishes how old its print is, not only when it was.

    The claim above holds the FLOOR: a print past [Price age]
    max_price_age_seconds is left off the leg. This holds the DISCLOSURE for
    everything that survives it. The floor is a ceiling of 900 seconds, so a
    row inside it can be fifteen minutes behind the scan clock and still be
    published, and the row used to carry the bare stamp of the minute the print
    opened. Turning that into an age needs the scan clock, and the report does
    not print the scan clock, so the one number that says how stale a published
    price is was the one number no reader could compute.

    The section already had it. The premarket leg computes the age to apply the
    floor and then dropped it on the floor, so this carries the number that was
    already in hand rather than measuring anything new.

    Null on both universe legs, which is not a gap: a close has no intraday age,
    and the leg's own as_of_session is the whole vintage of the row.
    """
    _write_closes()
    block, _packet, _rows = _run()

    premarket = [r for r in block["rows"] if r["leg"] == "premarket"]
    if not premarket:
        failures.append("the fixture produced no premarket row, so this claim "
                        "checked nothing")
        return
    for row in premarket:
        age = row.get("price_age_seconds")
        # The clock is stubbed to 08:45 and the bars are stamped 08:40.
        if age != 300.0:
            failures.append(
                f"{row['symbol']} carries price_age_seconds {age!r} against a "
                "print at 08:40 and a scan clock at 08:45, which is 300 "
                "seconds. The age is the gate's own number and must not be "
                "recomputed from a different clock.")
        if not row.get("price_time"):
            failures.append(f"{row['symbol']} carries an age and no price_time, "
                            "so the two disclosures have come apart")

    for row in block["rows"]:
        if row["leg"] == "premarket":
            continue
        if row.get("price_age_seconds") is not None:
            failures.append(
                f"a {row['leg']} row carries price_age_seconds "
                f"{row['price_age_seconds']!r}. A close has no intraday age, "
                "and a number there would read as one.")

    # And it reaches the reader. The column is in the header the template pins
    # and the fallback emits, and the value is in the row's line. A field that
    # is in the packet and not in the report is not a disclosure.
    if "Price age" not in analyst.NOTABLE_HEADER:
        failures.append("analyst.NOTABLE_HEADER carries no price age column, so "
                        "the number is in the packet and not in the report")
    text = analyst.fallback_report(
        {"session_date": SESSION, "candidates": [], "notable_movers": block},
        "the narrative pass was stubbed out by this claim")
    for row in premarket:
        ticker = row["symbol"].split(".")[0]
        line = next((r for r in text.splitlines()
                     if r.startswith(f"| {ticker} |") and "premarket" in r), None)
        if line is None:
            failures.append(f"the fallback wrote no premarket row for {ticker}")
        elif not line.rstrip().endswith("| 300 |"):
            failures.append(f"the fallback's {ticker} row does not end in the "
                            f"age the packet carries: {line!r}")

    print(f"  price age s  {len(premarket)} premarket row(s) publish a 300s age "
          "beside the stamp, both universe legs carry none, and the fallback "
          "prints the column")


def claim_the_context_tickers_stay_out_of_the_premarket_leg(
        failures: list[str]) -> None:
    """SPY is subscribed, heard, and not a notable mover.

    Decided here rather than by the owner and cheap to overrule, which is why
    it is asserted rather than assumed. The eight [Collector] context_symbols
    are in bars_by_symbol, and 4.3 says every subscribed name is eligible for
    the premarket leg. They are ETFs and the universe is common stock, so they
    are in none of the three joins the section needs: no row in universe.json,
    no close in the sidecar, no row in gap_stats. A premarket row for SPY would
    carry a price and a null in every other column, including the move it is
    supposed to be notable for. Their moves are already in market_snapshot.
    """
    block, _packet, _rows = _run()
    symbols = {r["symbol"] for r in block["rows"]}
    context = set(_CRIT.text_list("collector", "context_symbols"))
    landed = {s for s in symbols if s.split(".")[0] in context}
    if landed:
        failures.append(f"context tickers reached the section: {sorted(landed)}. "
                        "They have no close in the sidecar, so their move is "
                        "null and the row is notable for nothing.")
    if block["context_symbols_excluded"] != 1:
        failures.append("the section counted "
                        f"{block['context_symbols_excluded']} excluded context "
                        "ticker(s) where the fixture subscribes one. A silent "
                        "exclusion is the thing 4.9 forbids.")
    if (block["legs"]["premarket"]["examined"] or 0) != 2:
        failures.append("the premarket leg examined "
                        f"{block['legs']['premarket']['examined']} symbols where "
                        "the fixture heard three, one of them a context ticker")

    print(f"  context out  {block['context_symbols_excluded']} context ticker "
          "excluded and counted, and the premarket leg examined the other "
          f"{block['legs']['premarket']['examined']}")


# ------------------------------------------------------------ the degrades

def claim_the_section_widens_containment_only_by_its_own_rows(
        failures: list[str]) -> None:
    """Putting the section in the packet does not make other names claimable.

    This is the defect class that bit the project on 2026-08-20, three commits
    before this section existed. analyst._packet_uppercase_tokens builds the
    allowed set from the packet's RAW TEXT first, `set(_TOKEN_RE.findall(...))`,
    and only then walks the structure. So EVERY uppercase run of one to six
    characters anywhere in packet.json becomes a ticker the report may claim. A
    fix that put the collector's per symbol roster into the packet widened that
    set by 73 names in one line, and the suite was green: AMAT, AVGO, DE, HOOD,
    MU, NOK, RIOT, SAP, TLT and TSM went from invented to allowed on the real
    packet, which is exactly the set a model reaches for in a market context
    sentence.

    This section is universe wide, so it is the largest new body of text the
    packet has gained since. The rule it has to hold is not "widen nothing", it
    is "widen by the names it publishes and by nothing else": the report is
    meant to name those and containment should let it. Anything ELSE the block
    contributes, a reason string, a list name, a leg label, a counter source, a
    headline, is text that must carry no claimable token.

    Measured on the real 2026-08-20 packet while this was written: 139 tokens
    to 159, twenty added, and all twenty were the ten published symbols in both
    spellings.
    """
    _write_closes()
    block, _packet, _rows = _run()

    base = {
        "session_date": SESSION,
        "candidates": _candidates(),
        "market_snapshot": [{"label": "spy", "symbol": "SPY.US", "last": 700.0}],
        "gaps_to_fill": [],
    }
    before = analyst._packet_uppercase_tokens(json.dumps(base))
    base["notable_movers"] = block
    after = analyst._packet_uppercase_tokens(json.dumps(base))

    published: set[str] = set()
    for row in block["rows"]:
        symbol = str(row["symbol"])
        published.add(symbol.upper())
        published.add(symbol.upper().split(".")[0])

    added = after - before
    stray = sorted(added - published)
    if stray:
        failures.append(
            f"the section made {stray} claimable, and none of them is a symbol "
            "it publishes. Every uppercase run of one to six characters in the "
            "packet text is a ticker the report may then claim, so a reason "
            "string or a label carrying one hands the model a name it holds no "
            "evidence about.")
    if not block["rows"]:
        failures.append("the fixture produced no rows, so this measured nothing")
    elif not (added & published):
        failures.append("the section published rows and widened the allowed set "
                        "by none of their symbols, so containment would report "
                        "its own section's tickers as invented and stop the "
                        "chain before render, verify, deliver and archive")

    print(f"  containment  {len(before)} tokens to {len(after)}, "
          f"{len(added)} added and all of them symbols the section publishes")


def claim_the_section_examines_the_universe_and_not_the_survivors(
        failures: list[str]) -> None:
    """The denominator is the universe, and zero examined is not zero selected.

    4.9 and 4.10's first item. A leg that looked at every name and picked none
    is a quiet market. A leg that looked at none is a lost input. A section
    reporting one number could not tell you which it was holding, which is why
    both are published per leg.
    """
    _write_closes()
    block, _packet, _rows = _run()

    if block["universe_examined"] != len(UNIVERSE_ROWS):
        failures.append(f"the section examined {block['universe_examined']} where "
                        f"the universe holds {len(UNIVERSE_ROWS)}. It must be the "
                        "universe and not any filtered subset of it.")
    for leg in ("prior_session", "two_session"):
        report = block["legs"][leg]
        if not report["available"]:
            failures.append(f"the {leg} leg is unavailable on a complete fixture: "
                            f"{report['reason']}")
        if report["examined"] != len(CLOSES):
            failures.append(f"the {leg} leg examined {report['examined']} where "
                            f"{len(CLOSES)} names carry both of its closes")
        if report["selected"] > _CRIT.integer("notable", "list_size") * 2:
            failures.append(f"the {leg} leg selected {report['selected']}, more "
                            "than its two lists can hold")

    if len(block["rows"]) > len(UNIVERSE_ROWS) * 3:
        failures.append(f"{len(block['rows'])} rows from {len(UNIVERSE_ROWS)} "
                        "names over three legs, which is more than one row per "
                        "name per leg")

    print(f"  universe     {block['universe_examined']} examined, "
          + ", ".join(f"{leg} {block['legs'][leg]['selected']} selected"
                      for leg in sorted(block["legs"])))


def claim_a_defect_in_the_section_costs_the_section(failures: list[str]) -> None:
    """The morning survives a raise inside the briefing table.

    build_packet calls notable_section, which wraps notable_movers. If it called
    notable_movers directly, any defect that raised would take build_packet down
    with it; the morning chain stops on the first non-zero exit, so a bug in a
    briefing table would cost the packet, the report and the email. The section
    is additive: nothing downstream reads it, no score depends on it, and no
    picks row comes from it.

    Nothing is swallowed. The exception type and message reach both the packet's
    gaps and the section's own skipped reason, and every leg and list carries
    it, so the report says what raised in the same place it says what was lost.

    A KeyboardInterrupt is NOT caught, because that is somebody stopping the run
    rather than a defect here, and an interrupt turned into a thin briefing is
    worse than useless.
    """
    import ast
    import pathlib as _pathlib

    real = scan.notable_movers
    packet = scan.Packet()

    def explode(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ZeroDivisionError("a denominator nobody guarded")

    try:
        scan.notable_movers = explode
        block = scan.notable_section(SESSION, {"symbols": UNIVERSE_ROWS}, {}, [],
                                     packet)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"notable_section let {type(exc).__name__} out, so a "
                        "defect in a briefing table would end the morning: "
                        f"{exc}")
        scan.notable_movers = real
        return
    finally:
        scan.notable_movers = real

    if block.get("rows"):
        failures.append("a section that raised still published rows")
    skipped = block.get("skipped") or ""
    if "ZeroDivisionError" not in skipped or "denominator nobody guarded" not in skipped:
        failures.append(f"the section's skipped reason is {skipped!r} and does "
                        "not name what raised, so the report cannot say why the "
                        "table is missing")
    if not any("ZeroDivisionError" in note for note in packet.gaps):
        failures.append(f"no packet gap names the raise: {packet.gaps}")
    legs = block.get("legs") or {}
    if set(legs) != {"premarket", "prior_session", "two_session"}:
        failures.append(f"the empty block reports on legs {sorted(legs)} rather "
                        "than the three the section emits")
    if any(report.get("available") or not report.get("reason")
           for report in legs.values()):
        failures.append("a leg in the empty block reads available, or carries no "
                        "reason, so a raise is indistinguishable from a quiet "
                        "market")
    if set(block.get("list_reasons") or {}) != set(scan.NOTABLE_LISTS):
        failures.append("the empty block does not carry a reason for each of "
                        f"the four lists: {block.get('list_reasons')}")

    # An interrupt is not a defect and must still stop the run.
    def interrupt(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise KeyboardInterrupt

    try:
        scan.notable_movers = interrupt
        scan.notable_section(SESSION, {"symbols": UNIVERSE_ROWS}, {}, [],
                             scan.Packet())
        failures.append("notable_section swallowed a KeyboardInterrupt, so "
                        "stopping the run by hand would produce a thin briefing "
                        "instead of stopping")
    except KeyboardInterrupt:
        pass
    finally:
        scan.notable_movers = real

    # And build_packet must actually go through the wrapper.
    source = _pathlib.Path(scan.__file__).read_bytes().decode("utf-8")
    tree = ast.parse(source)
    build = next((n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "build_packet"),
                 None)
    if build is None:
        failures.append("scan.build_packet is gone")
    else:
        called = {n.func.id for n in ast.walk(build)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        if "notable_section" not in called:
            failures.append("build_packet does not call notable_section, so the "
                            "wrapper guards nothing")
        if "notable_movers" in called:
            failures.append("build_packet calls notable_movers directly, so a "
                            "raise inside it reaches build_packet after all")

    print("  survives     a raise inside the section is published as the "
          "section's own reason, and an interrupt still stops the run")


def claim_an_empty_list_says_which_empty_it_is(failures: list[str]) -> None:
    """A list that returns nothing states WHICH nothing, and its denominator.

    4.9 makes the legs tell a quiet market apart from a lost input. Until
    2026-08-22 the four ranked lists did not, one level down: an empty list got
    one sentence saying it was "short" and no state and no count, and the two
    sigma lists have been empty on every run the section has ever made, because
    return_stdev_20d is null on all 10,997 rows of the gap statistics database
    until the Sunday 21:00 rebuild fills it. A reader could not tell that from a
    morning on which nothing moved.

    Four states and they are four because the fixes differ. UNCOMPUTABLE is an
    input nobody has produced, whether the leg's whole file or the one column
    the list ranks on, and the fix is to go and compute it. NOTHING TO RANK is a
    file that arrived carrying nothing for that leg. BELOW THE FLOOR is the only
    one of the three that means the market was quiet. RANKED is a list holding
    names.

    Every state carries the count it considered beside it, the way the Summary
    writes "day eligible 3 of 12" rather than "day eligible 3". A zero with
    nothing under it cannot be read.
    """
    # 1. The shipped morning: the column exists and has never been computed.
    #    Both sigma lists must read uncomputable, and both must say so against
    #    a leg that is perfectly available.
    seen: set[str] = set()

    def note(block: dict[str, Any]) -> dict[str, Any]:
        """Tally the states one fixture reached, and hand back its reports."""
        reports = block.get("list_reports") or {}
        seen.update(str((r or {}).get("state")) for r in reports.values())
        return reports

    null_column = {symbol: {"return_stdev_20d": None, "sessions_used": 250}
                   for symbol in STATS}
    _write_closes()
    block, _packet, _rows = _run(stats=null_column)
    reports = note(block)
    for name in ("prior_session_by_sigma", "premarket_by_sigma"):
        report = reports.get(name) or {}
        if report.get("state") != scan.LIST_UNCOMPUTABLE:
            failures.append(
                f"with return_stdev_20d null across the database the {name} "
                f"list reads {report.get('state')!r}. It is the state every "
                "morning since the section shipped has actually been in, and "
                "an empty list that does not say so reads as a quiet market.")
        if not report.get("considered"):
            failures.append(f"the {name} list reports considered "
                            f"{report.get('considered')!r} on a leg that "
                            "measured names. An empty list with no denominator "
                            "cannot be read.")
        if "return_stdev_20d" not in str(report.get("reason") or ""):
            failures.append(f"the {name} list does not name the null column in "
                            f"its reason: {report.get('reason')!r}")
        leg = (block["legs"] or {}).get(report.get("leg")) or {}
        if not leg.get("available"):
            failures.append(f"the {name} list reported uncomputable off a leg "
                            "that was itself unavailable, so this fixture is "
                            "not testing the null column at all")
    # The other two rank on keys the null column does not touch, so they are
    # unaffected. Without this the claim would pass on a fixture that had simply
    # emptied the section.
    for name in ("prior_session_by_market_cap", "two_session_by_move"):
        if (reports.get(name) or {}).get("state") != scan.LIST_RANKED:
            failures.append(
                f"the {name} list reads "
                f"{(reports.get(name) or {}).get('state')!r} with only the "
                "sigma column nulled. It does not rank on that column.")

    # 2. The input was never there: no sidecar at all. Both universe legs, and
    #    the premarket leg with them, lost the file rather than the market.
    (config.DATA_DIR / f"universe-closes-{SESSION}.json").unlink(missing_ok=True)
    block, _packet, _rows = _run()
    for name, report in note(block).items():
        if report.get("state") != scan.LIST_UNCOMPUTABLE:
            failures.append(f"with no closes sidecar the {name} list reads "
                            f"{report.get('state')!r} rather than uncomputable")

    # 3. The input arrived and carried nothing this leg could measure. Same
    #    empty list, different fact, different fix, and the state says so.
    _write_closes(closes={"NOCLOSE.US": {"c1": None, "c2": None, "c3": None}})
    block, _packet, _rows = _run()
    for name in ("prior_session_by_sigma", "prior_session_by_market_cap",
                 "two_session_by_move"):
        report = note(block).get(name) or {}
        if report.get("state") != scan.LIST_NOTHING_TO_RANK:
            failures.append(
                f"a sidecar that was read and carried no usable close left the "
                f"{name} list reading {report.get('state')!r}. That is a file "
                "with nothing in it, not a file nobody could open.")

    # 4. The leg measured names, the key exists, and the floor refused them
    #    all. The one empty of the three that IS a quiet market.
    under = {symbol: {"c3": 100.0, "c2": 100.0, "c1": 100.4}
             for symbol in ("QUIET.US", "LOUD.US", "MEGA.US")}
    _write_closes(closes=under)
    block, _packet, _rows = _run()
    report = note(block).get("prior_session_by_market_cap") or {}
    if report.get("state") != scan.LIST_BELOW_THE_FLOOR:
        failures.append(
            "0.4 percent moves on every name left prior_session_by_market_cap "
            f"reading {report.get('state')!r}. The leg was measured and the "
            "floor refused it, which is the only empty here that means the "
            "market was quiet.")
    if str(scan.NOTABLE_MIN_ABS_GAP_PCT) not in str(report.get("reason") or ""):
        failures.append("the below the floor reason does not quote the floor "
                        f"it applied: {report.get('reason')!r}")

    # 5. The floor cleared and the RANKING KEY is what is missing. A name with
    #    no market cap on file was never examined against anything, so this is
    #    uncomputable rather than a quiet market, and the two share a branch
    #    everywhere except here.
    _write_closes(closes={"NOCAP.US": {"c3": 100.0, "c2": 100.0, "c1": 108.0}})
    block, _packet, _rows = _run(universe=[])
    report = note(block).get("prior_session_by_market_cap") or {}
    if report.get("state") != scan.LIST_UNCOMPUTABLE:
        failures.append(
            "an 8 percent move on a symbol with no market cap on file left "
            f"prior_session_by_market_cap reading {report.get('state')!r}. It "
            "cleared the floor; the column it ranks on is what is absent.")

    # 6. And the shape holds on every list of every fixture above: a state from
    #    the fixed four, three integer counts, and a reason wherever the list
    #    came back with nothing.
    for label, produced in (("healthy", None), ("raised", "raised")):
        if produced is None:
            _write_closes()
            block, _packet, _rows = _run()
        else:
            block = scan.empty_notable_block(
                "the notable movers section raised ValueError: a name nobody "
                "guarded")
        for name, report in note(block).items():
            if report.get("state") not in scan.NOTABLE_LIST_STATES:
                failures.append(f"the {label} {name} list reports a state "
                                f"{report.get('state')!r} that is not one of "
                                f"{scan.NOTABLE_LIST_STATES}")
            for field in ("considered", "qualified", "selected"):
                if not isinstance(report.get(field), int):
                    failures.append(f"the {label} {name} list reports {field} "
                                    f"{report.get(field)!r}, which is not a "
                                    "count a reader can divide by")
            if not report.get("selected") and not report.get("reason"):
                failures.append(f"the {label} {name} list returned nothing and "
                                "states no reason, which is the whole defect "
                                "this claim exists for")
            if report.get("text") != scan._list_report_text(name, report):
                failures.append(f"the {label} {name} list's text is not what "
                                "_list_report_text builds from its own fields, "
                                "so the sentence and the numbers have come "
                                "apart")
    # list_reasons is derived and must stay derived, because the template and
    # fallback_report have quoted it since the section shipped.
    if block.get("list_reasons") != {name: report.get("reason") for name, report
                                     in (block.get("list_reports") or {}).items()}:
        failures.append("list_reasons is not the reasons in list_reports, so "
                        "the section now carries two copies of one sentence")

    # Every one of the four, or the claim is asserting three of them and
    # leaving the fourth to whatever a later change makes of it.
    missed = sorted(set(scan.NOTABLE_LIST_STATES) - seen)
    if missed:
        failures.append(f"no fixture here reached the {missed} state(s), so "
                        "they are declared and unexercised")

    print(f"  list state   all {len(scan.NOTABLE_LIST_STATES)} states reached "
          "across 6 fixtures, and an empty list names its own denominator "
          "rather than reading as a quiet market")


def claim_a_malformed_input_costs_the_section_and_not_the_run(
        failures: list[str]) -> None:
    """Nothing the section reads can raise out of build_packet.

    The section reads two files it does not own and the collector bars, and a
    JSON file is whatever is on disk rather than whatever the writer meant. A
    sessions block that is a list, a closes row that is a string, a collector
    bar with no minute_epoch: each of those raised AttributeError, TypeError or
    KeyError straight out of notable_movers, and build_packet is the morning
    chain's first step. The chain stops on the first non-zero exit, so any one
    of them cost the packet, the report and the email over a briefing table.

    notable_section catches Exception, so none of them can reach build_packet
    now. That wrapper is the backstop, not the answer: a section that silently
    disappears whenever a file is odd tells the reader nothing about which file
    or what was odd about it. So each shape below is checked to produce a NAMED
    reason rather than a caught traceback, and the wrapper's own generic reason
    is what the last two cases are allowed to fall back to.
    """
    path = config.DATA_DIR / f"universe-closes-{SESSION}.json"
    base = {
        "generated_at": f"{SESSION}T07:15:00-04:00",
        "session_date": SESSION,
        "sessions": {"c1": C1, "c2": C2, "c3": C3},
        "closes": dict(CLOSES),
        "universe_examined": len(UNIVERSE_ROWS),
        "names_with_at_least_one_close": len(CLOSES),
        "third_session_available": True,
    }

    shapes = (
        ("closes is a list", {**base, "closes": [1, 2, 3]}, "closes map"),
        ("sessions is a list", {**base, "sessions": ["a", "b"]}, "sessions block"),
        ("sessions is absent", {k: v for k, v in base.items() if k != "sessions"},
         "sessions block"),
        ("a row is a string",
         {**base, "closes": {**CLOSES, "ODD.US": "not a row"}}, None),
        ("a row is a list",
         {**base, "closes": {**CLOSES, "ODD.US": [1, 2]}}, None),
        ("a close is zero",
         {**base, "closes": {**CLOSES, "ZERO.US": {"c1": 10.0, "c2": 0.0,
                                                   "c3": 0.0}}}, None),
        ("the whole payload is a list", [1, 2, 3], "closes map"),
    )
    for label, payload, needle in shapes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        packet = scan.Packet()
        real_stats, real_clock = gap_stats.load_all, ettime.now_et
        gap_stats.load_all = lambda as_of=None: dict(STATS)
        ettime.now_et = lambda: dt.datetime(2026, 8, 20, 8, 45, tzinfo=ettime.ET)
        try:
            block = scan.notable_section(
                SESSION, {"symbols": UNIVERSE_ROWS},
                {"HEARD.US": [_bar("HEARD.US", "08:40", 103.0)]},
                _candidates(), packet)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label} raised {type(exc).__name__} past "
                            f"notable_section: {exc}")
            continue
        finally:
            gap_stats.load_all, ettime.now_et = real_stats, real_clock
        if block.get("skipped") and "raised" in str(block["skipped"]):
            failures.append(f"{label} was caught by the wrapper rather than "
                            f"refused with a reason: {block['skipped']}")
        if needle:
            said = " ".join(str(note) for note in packet.gaps)
            if needle not in said:
                failures.append(f"{label} produced no gap naming {needle!r}: "
                                f"{packet.gaps}")
        if label.startswith("a row is") and block.get("malformed_closes_rows") != 1:
            failures.append(
                f"{label} left malformed_closes_rows at "
                f"{block.get('malformed_closes_rows')!r} where the sidecar "
                "carries one. The examined counts come from the file's own "
                "denominators and still count that row, so a silent skip means "
                "two numbers in the packet disagree and nothing says why.")

    # A third session the vendor never answered for is not a quiet market.
    _write_closes(closes={s: {"c1": r["c1"], "c2": r["c2"], "c3": None}
                          for s, r in CLOSES.items()})
    path.write_text(json.dumps({
        **json.loads(path.read_text(encoding="utf-8")),
        "third_session_available": False,
    }, indent=2), encoding="utf-8")
    block, _packet, _rows = _run()
    two = block["legs"]["two_session"]
    if two["available"]:
        failures.append("the two_session leg reads available with c3 null on "
                        "every row")
    elif "never bought" not in (two["reason"] or ""):
        failures.append(
            "a third session the vendor never answered for is reported as "
            f"{two['reason']!r}, which is what a session every symbol happened "
            "to be missing from would say. discover records which it was in "
            "third_session_available and the leg has to quote it.")

    # Two shapes that are not the sidecar at all.
    _write_closes()
    packet = scan.Packet()
    real_stats, real_clock = gap_stats.load_all, ettime.now_et
    gap_stats.load_all = lambda as_of=None: dict(STATS)
    ettime.now_et = lambda: dt.datetime(2026, 8, 20, 8, 45, tzinfo=ettime.ET)
    try:
        block = scan.notable_section(
            SESSION, {},
            {"HEARD.US": [{"symbol": "HEARD.US", "c": 103.0}]},
            [{"price": 1.0}], packet)
    except Exception as exc:  # noqa: BLE001
        failures.append("a universe with no symbols key, a collector bar with "
                        "no minute_epoch and a candidate with no symbol raised "
                        f"{type(exc).__name__}: {exc}")
        block = {}
    finally:
        gap_stats.load_all, ettime.now_et = real_stats, real_clock
    if block.get("skipped") and "raised" in str(block["skipped"]):
        failures.append("a bar with no minute_epoch fell through to the "
                        f"wrapper: {block['skipped']}")

    print(f"  malformed    {len(shapes) + 1} shapes the sidecar and the bars can "
          "actually take, each refused with a reason rather than raising")


def claim_a_missing_input_names_the_leg_it_lost(failures: list[str]) -> None:
    """A lost sidecar and a silent collector each say which leg went with them.

    4.9. Each degrade is a NAMED reason in the packet and the section says which
    leg it lost, because an empty list that cannot say why it is empty reads
    exactly like a quiet market.
    """
    # 1. No sidecar at all: both universe legs, and the premarket leg with them,
    #    because the premarket move is measured against c1 from the same file.
    path = config.DATA_DIR / f"universe-closes-{SESSION}.json"
    path.unlink(missing_ok=True)
    block, packet, _rows = _run()
    if block["rows"]:
        failures.append(f"{len(block['rows'])} rows were published with no closes "
                        "sidecar on disk")
    for leg in ("prior_session", "two_session", "premarket"):
        report = block["legs"][leg]
        if report["available"] or not report["reason"]:
            failures.append(f"with no sidecar the {leg} leg reports "
                            f"available={report['available']} reason="
                            f"{report['reason']!r}")
    if not any("universe-closes" in note for note in packet.gaps):
        failures.append("no packet gap names the missing sidecar: "
                        f"{packet.gaps}")
    if block["universe_examined"] is not None:
        failures.append("with no sidecar universe_examined is "
                        f"{block['universe_examined']} rather than null. Zero "
                        "examined and unknown examined are different facts.")

    # 2. Sidecar present, collector silent: the two universe legs survive.
    _write_closes()
    block, _packet, _rows = _run(bars={})
    if not block["legs"]["prior_session"]["available"]:
        failures.append("a silent collector took the prior_session leg with it, "
                        "and that leg reads no collector bar at all")
    report = block["legs"]["premarket"]
    if report["available"] or "collector" not in (report["reason"] or ""):
        failures.append("a silent collector produced premarket leg "
                        f"available={report['available']} reason={report['reason']!r}")
    if block["lists"]["premarket_by_sigma"]:
        failures.append("list 4 published names with no collector bars behind them")
    # And a short list says why. This is the field the section leans on hardest
    # on the first real morning: every return_stdev_20d in the database is null,
    # so both sigma lists come back empty while their legs are available, and a
    # null here would read as a quiet market.
    reasons = block.get("list_reasons") or {}
    if set(reasons) != set(scan.NOTABLE_LISTS):
        failures.append(f"list_reasons covers {sorted(reasons)} rather than the "
                        f"four lists {sorted(scan.NOTABLE_LISTS)}")
    for name, chosen in block["lists"].items():
        if len(chosen) < block["list_size"] and not reasons.get(name):
            failures.append(f"{name} came back with {len(chosen)} of "
                            f"{block['list_size']} and no reason recorded, which "
                            "reads exactly like a quiet market")

    print("  degrade      a lost sidecar names all three legs and nulls the "
          "examined count, and a silent collector loses only its own")


def claim_an_undated_sidecar_costs_two_legs_and_not_the_morning(
        failures: list[str]) -> None:
    """A closes file with no session for c1 does not take the report down.

    Both universe legs are stamped with c1's SESSION, not with its value. A
    sidecar whose sessions.c1 is null therefore produced rows carrying
    as_of_session None, vintage check (e) refused them, enforce RAISED, and the
    morning chain stopped before the analyst with data/UNVERIFIED rewritten. A
    briefing section had taken the whole report down. Reproduced before the fix:
    two rows, two violations, "declares leg prior_session with no
    as_of_session".

    The writer does not produce that shape today, because discover returns
    before writing when the calendar cannot name the prior session. But it does
    write a null into that block legitimately, for c3, so a null inside sessions
    is a shape the file genuinely has, and the cost of being wrong is the entire
    morning rather than a thin table.

    The premarket leg is unaffected on purpose: it stamps today and reads c1 as
    a NUMBER, so an undated c1 costs the two legs that need it to be a date and
    nothing else.
    """
    closes = {"QUIET.US": {"c1": 104.04, "c2": 102.0, "c3": 100.0}}
    path = config.DATA_DIR / f"universe-closes-{SESSION}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generated_at": f"{SESSION}T07:15:00-04:00",
        "session_date": SESSION,
        "sessions": {"c1": None, "c2": C2, "c3": C3},
        "closes": closes,
        "universe_examined": 1,
        "names_with_at_least_one_close": 1,
        "third_session_available": True,
    }, indent=2), encoding="utf-8")

    bars = {"QUIET.US": [_bar("QUIET.US", "08:40", 110.0)]}
    block, packet, _rows = _run(bars=bars, candidates=[])

    if block["rows"]:
        undated = [r["symbol"] for r in block["rows"] if not r["as_of_session"]]
        if undated:
            failures.append(
                f"{undated} were published with no as_of_session. vintage check "
                "(e) refuses those, enforce raises, and the morning chain stops "
                "before the analyst over a briefing table.")
    for leg in ("prior_session", "two_session"):
        report = block["legs"][leg]
        if report["available"] or "sessions.c1" not in (report["reason"] or ""):
            failures.append(f"with an undated c1 the {leg} leg reports "
                            f"available={report['available']} reason="
                            f"{report['reason']!r}, which does not name the "
                            "field that could not be read")
    if not any("sessions.c1" in note for note in packet.gaps):
        failures.append(f"no packet gap names the undated c1: {packet.gaps}")

    # The premarket leg reads c1 as a number and stamps today, so it survives.
    premarket = [r for r in block["rows"] if r["leg"] == "premarket"]
    if not premarket:
        failures.append("the premarket leg was lost with the universe legs, and "
                        "it neither needs c1 to be a date nor stamps itself with "
                        f"one: {block['legs']['premarket']}")
    elif premarket[0]["as_of_session"] != SESSION:
        failures.append(f"a premarket row is stamped "
                        f"{premarket[0]['as_of_session']!r} rather than today")

    # And the whole thing passes the gate it used to fail.
    stubbed = market_today.decide
    market_today.decide = lambda details, day: (day.weekday() < 5, "stubbed")
    try:
        violations = vintage.check_packet({
            "session_date": SESSION, "candidates": [], "market_snapshot": [],
            "notable_movers": block,
        })
    finally:
        market_today.decide = stubbed
    if violations:
        failures.append(f"the section built off an undated sidecar still fails "
                        f"the vintage gate, so enforce would still stop the "
                        f"chain: {violations}")

    print(f"  undated c1   the two legs that need a date are lost and named, "
          f"the premarket leg survives with {len(premarket)} row(s), and the "
          "gate passes")


def claim_a_close_from_another_session_is_not_stamped_with_this_one(
        failures: list[str]) -> None:
    """The sidecar records the session the vendor believed it was sending.

    discover threw the vendor's own date away and kept only the close, so
    nothing anywhere in the chain could say which session the rows came from.
    It records vendor_dates now, and the section refuses to stamp a leg the
    vendor contradicts.

    WHAT THIS IS NOT. It was written on the belief that vintage check (e) was
    comparing the calendar against itself for the two universe legs, and that
    belief is wrong. ops/market_today.ALLOW_NETWORK is true by default and only
    scan.build_packet turns it off, so both job_discover.bat at 07:15 and
    job_morning_chain.bat at 08:45 refresh the exchange calendar in their own
    processes before the Python that matters. Check (e) is a live cross process
    comparison across a ninety minute gap, not a tautology. CHANGELOG.md's
    twelfth entry carries the correction and the reasoning that was wrong.

    WHAT IT IS. A cross check on the DATA rather than on the calendar, and a
    narrow one. The repository's own record is that eod-bulk-last-day answers a
    session the calendar says was open with an EMPTY ARRAY rather than with
    another session's bars, and discover returns before writing on that branch,
    so this may never fire in production. It is kept because it costs a set
    comprehension over rows already in memory, because it also catches a
    response mixing two session dates, which nothing else would see, and
    because a datum thrown away is worth less than a guard that is claimed and
    watched to fail.
    """
    # 1. The vendor sent a different session than the one asked for.
    _write_closes(vendor_dates={"c1": ["2026-08-14"], "c2": [C2], "c3": [C3]})
    block, packet, _rows = _run()
    for leg in ("prior_session", "two_session"):
        report = block["legs"][leg]
        if report["available"]:
            failures.append(f"the {leg} leg is published off closes the vendor "
                            f"stamped 2026-08-14 under a {C1} label")
        elif "2026-08-14" not in (report["reason"] or ""):
            failures.append(f"the {leg} leg was lost without naming the date "
                            f"the vendor actually sent: {report['reason']!r}")
    if not any("2026-08-14" in note for note in packet.gaps):
        failures.append(f"no packet gap names the mismatch: {packet.gaps}")
    if not block.get("vendor_date_mismatch"):
        failures.append("the block does not record the mismatch it acted on")

    # 1b. THE FAR END, which until 2026-08-22 was a different sentence for the
    # same fault. A c2 or c3 the vendor stamped with a session nobody asked for
    # is nulled on every row, correctly, and the leg that reads it then came out
    # empty with "0 rows carried both of the closes the prior_session leg
    # needs". That says the file held nothing, and sends a reader to the vendor
    # for data that arrived and was refused. c1 has named the fault since the
    # section shipped because it costs both legs at once; these cost one each.
    for close_key, lost, kept, sent in (("c2", "prior_session", "two_session", "2026-08-11"),
                                        ("c3", "two_session", "prior_session", "2026-08-08")):
        dates = {"c1": [C1], "c2": [C2], "c3": [C3]}
        dates[close_key] = [sent]
        _write_closes(vendor_dates=dates)
        block, packet, _rows = _run()
        report = block["legs"][lost]
        if report["available"]:
            failures.append(f"the {lost} leg is published off a {close_key} the "
                            f"vendor stamped {sent}")
        reason = str(report["reason"] or "")
        if "0 rows carried both of the closes" in reason:
            failures.append(f"a refused {close_key} left the {lost} leg reporting "
                            "an empty sidecar rather than a refused close")
        if sent not in reason:
            failures.append(f"the {lost} leg does not name the session the vendor "
                            f"actually sent for {close_key}: {reason[:160]!r}")
        if report.get("input_present") is not False:
            failures.append(f"a refused {close_key} left the {lost} leg reporting "
                            "its input as present, so it reads as nothing to "
                            "rank rather than as uncomputable")
        if not any(sent in note for note in packet.gaps):
            failures.append(f"a refused {close_key} raised no gap naming {sent}: "
                            f"{packet.gaps}")
        if not block["legs"][kept]["available"]:
            failures.append(f"a refused {close_key} also lost the {kept} leg, "
                            f"which does not read {close_key} at all")

    # 2. The ordinary morning, where they agree.
    _write_closes()
    block, _packet, _rows = _run()
    if not block["legs"]["prior_session"]["available"]:
        failures.append("agreeing vendor dates still lost the prior_session "
                        f"leg: {block['legs']['prior_session']['reason']!r}")
    if block.get("vendor_date_mismatch"):
        failures.append("agreeing dates were recorded as a mismatch: "
                        f"{block['vendor_date_mismatch']}")

    # 3. A sidecar too old to carry them is unknown, not disagreement.
    _write_closes(vendor_dates={})
    block, _packet, _rows = _run()
    if not block["legs"]["prior_session"]["available"]:
        failures.append("a sidecar with no vendor_dates was treated as a "
                        "mismatch rather than as unknown, so every file written "
                        "before 2026-08-20 loses both universe legs")
    if block.get("vendor_dates") is not None:
        failures.append("a sidecar with no vendor_dates reports "
                        f"{block['vendor_dates']!r} rather than null")

    # 4. A wrong c2 costs the leg that reads it and not the other one.
    _write_closes(vendor_dates={"c1": [C1], "c2": ["2026-08-11"], "c3": [C3]})
    block, _packet, _rows = _run()
    if block["legs"]["prior_session"]["available"]:
        failures.append("the prior_session leg is published off a c2 the vendor "
                        "stamped 2026-08-11, so its move measures the wrong end")
    if not block["legs"]["two_session"]["available"]:
        failures.append("a wrong c2 also cost the two_session leg, which reads "
                        f"c3: {block['legs']['two_session']['reason']!r}")

    print("  vendor dates a leg the vendor contradicts is refused and named, an "
          "agreeing one is published, and a file too old to say reads unknown")


def claim_a_notable_only_symbol_never_reaches_the_picks_table(
        failures: list[str]) -> None:
    """The fence is checked by RUNNING write_picks, not by reading it.

    claim_nothing_in_the_section_reaches_picks walks two function bodies looking
    for a token, and a token check has an obvious hole: move the row gathering
    into a module level helper and write_picks no longer mentions
    notable_movers, so every briefing name reaches the picks table and the
    suite stays green. Mutation testing found exactly that.

    So this one writes a packet through and looks at the table. picks is the
    record of what the trading SCREEN claimed, pool_recall measures the morning
    against it, and there is no column that says which rows were briefing names,
    so a briefing name written here corrupts the recall measurement permanently
    and silently.

    force_test keeps the rows out of the live measurement: they are written with
    source 'test', which is what every other suite write to this table uses.
    conftest has redirected the database into the sandbox anyway.
    """
    from core import store

    packet = {
        "session_date": SESSION,
        "generated_at": f"{SESSION}T08:45:00-04:00",
        "candidates": [
            {"symbol": "HEARD.US", "price": 103.0, "gap_pct": 1.98,
             "day_eligible": True, "swing_eligible": False, "score": 7.0,
             "conviction": "green", "prior_close": 101.0},
        ],
        "notable_movers": {
            "rows": [
                {"symbol": "QUIET.US", "leg": "prior_session",
                 "as_of_session": C1, "move_pct": 2.0, "move_sigma": 2.0,
                 "market_cap": 900_000_000.0, "selected_by": ["x"]},
                {"symbol": "DOWN.US", "leg": "two_session",
                 "as_of_session": C1, "move_pct": -45.0, "move_sigma": -31.8,
                 "market_cap": 2_000_000_000.0, "selected_by": ["y"]},
            ],
        },
    }
    try:
        written = scan.write_picks(packet, force_test=True)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"write_picks raised on a packet carrying a notable "
                        f"section: {type(exc).__name__}: {exc}")
        return

    with store.session() as connection:
        store.init(connection)
        rows = connection.execute(
            "SELECT ticker FROM picks WHERE date=?", (SESSION,)
        ).fetchall()
    tickers = {str(row[0]).upper() for row in rows}

    for symbol in ("QUIET.US", "DOWN.US", "QUIET", "DOWN"):
        if symbol in tickers:
            failures.append(
                f"{symbol} appears only in the notable movers section and has a "
                "picks row. picks is the record of what the SCREEN claimed and "
                "pool_recall measures the morning against it, with no column "
                "that says which rows were briefing names.")
    if not tickers:
        failures.append("write_picks wrote nothing at all, so this claim did "
                        "not exercise the table and proved nothing")
    elif written < 1:
        failures.append(f"write_picks reported {written} row(s) written while "
                        f"the table holds {len(tickers)}")

    print(f"  picks fence  a packet carrying two briefing rows wrote "
          f"{len(tickers)} picks row(s), and neither briefing symbol is among "
          "them")


def claim_a_closes_file_from_another_session_is_refused(
        failures: list[str]) -> None:
    """Yesterday's closes are not published under today's leg labels.

    data/ accumulates these files and nothing else in the project compares the
    one it reads against today's session. A morning where discover did not run
    would otherwise read the most recent file it could find and stamp its
    closes with today's labels, which is exactly the failure the leg labelling
    exists to prevent. generated_at cannot be used for this: the 2026-08-19
    file is stamped 08:21:27 rather than the scheduled 07:15, so a rule derived
    from the clock would refuse a legitimate file.
    """
    _write_closes(session=SESSION, stamped=C1)
    block, packet, _rows = _run()
    if block["rows"]:
        failures.append(f"{len(block['rows'])} rows were published off a sidecar "
                        f"whose own session_date is {C1}")
    if not any("session_date" in note for note in packet.gaps):
        failures.append(f"no packet gap names the mismatch: {packet.gaps}")

    # And the honest file is accepted, so the check is not refusing everything.
    _write_closes()
    block, _packet, _rows = _run()
    if not block["rows"]:
        failures.append("a sidecar stamped with today's session was refused too, "
                        "so the check refuses everything")

    print(f"  wrong day    a sidecar stamped {C1} is refused with the reason "
          "recorded, and today's is accepted")


def claim_the_counters_say_whether_they_were_read_or_derived(
        failures: list[str]) -> None:
    """A count derived here is not published as one discover wrote.

    BUILD_PLAN says the per leg counters are already in the sidecar and must not
    be recomputed. The writer landed on 2026-08-20, about six hours AFTER that
    morning's 07:15 run, so the first file carrying them is 2026-08-21's and
    every file before it has neither. Deriving them silently would violate 4.9
    in the other direction: a count nobody can tell apart from a written one is
    a count whose provenance is false.
    """
    truth = {
        "prior_session": sum(1 for r in CLOSES.values()
                             if r.get("c1") is not None and r.get("c2") is not None),
        "two_session": sum(1 for r in CLOSES.values()
                           if r.get("c1") is not None and r.get("c3") is not None),
    }

    _write_closes(counters=False)
    block, _packet, _rows = _run()
    if block["counter_source"] != "derived":
        failures.append("a sidecar with no per leg counters reported "
                        f"counter_source {block['counter_source']!r}")
    if block["names_with_both_closes_for_leg"] != truth:
        failures.append("with nothing written to read, the derived counts came "
                        f"back {block['names_with_both_closes_for_leg']} where "
                        f"counting the closes map gives {truth}")
    if block["names_with_close"] != {
            key: sum(1 for r in CLOSES.values() if r.get(key) is not None)
            for key in ("c1", "c2", "c3")}:
        failures.append("the derived per session counts are wrong: "
                        f"{block['names_with_close']}")

    _write_closes(counters=True)
    block, _packet, _rows = _run()
    if block["counter_source"] != "read":
        failures.append("a sidecar carrying the counters reported counter_source "
                        f"{block['counter_source']!r}")
    # The written numbers are deliberately impossible to derive from CLOSES, so
    # republishing them is the only way to produce them and recounting is the
    # only way not to.
    if block["names_with_both_closes_for_leg"] != \
            WRITTEN_COUNTS["names_with_both_closes_for_leg"]:
        failures.append(
            "the section recounted instead of reading what discover wrote: got "
            f"{block['names_with_both_closes_for_leg']}, the file says "
            f"{WRITTEN_COUNTS['names_with_both_closes_for_leg']}")
    if block["names_with_close"] != WRITTEN_COUNTS["names_with_close"]:
        failures.append("the per session counts were recounted rather than read: "
                        f"{block['names_with_close']}")

    print(f"  provenance   a written {WRITTEN_COUNTS['names_with_both_closes_for_leg']} "
          f"is republished and an absent one is derived as {truth}, and the "
          "block says which of the two it did")


def _section_prose(block: dict[str, Any], packet: scan.Packet) -> list[str]:
    """Every string this section would hand the model to quote."""
    out: list[str] = [str(note) for note in packet.gaps]
    if block.get("skipped"):
        out.append(str(block["skipped"]))
    for report in (block.get("legs") or {}).values():
        if report.get("reason"):
            out.append(str(report["reason"]))
    for reason in (block.get("list_reasons") or {}).values():
        if reason:
            out.append(str(reason))
    # The list outcome sentences, which are the section's LOUDEST fixed text:
    # four of them, on every run, quoted word for word by the template. They
    # carry the reason above inside them, so the guard sees the assembled
    # sentence rather than only its parts, which is where a wording that is
    # clean alone and dirty in context would show up.
    for report in (block.get("list_reports") or {}).values():
        if (report or {}).get("text"):
            out.append(str(report["text"]))
    for row in block.get("rows") or []:
        for key in ("move_sigma_reason", "market_cap_reason", "catalyst_state"):
            if row.get(key):
                out.append(str(row[key]))
    return out


def claim_a_row_says_what_the_instrument_is_or_why_it_cannot(
        failures: list[str]) -> None:
    """A list that RANKS by market cap has to say what it is ranking.

    The section's second list ranks market cap descending, so the largest
    values in the universe are read by a human every morning, and a bare ticker
    cannot tell that reader whether a very large one is a real company or a
    vendor error. It is not hypothetical: SPCX at 1.85 trillion and SKHY at
    1.18 were both written up in DECISIONS.md as implausible caps needing a
    plausibility floor. Three offline discriminators were measured against them
    and all three failed, and a vendor call then returned "Space Exploration
    Technologies Corp. Class A Common Stock" and "SK Hynix Inc. American
    Depositary Shares". The caps were right and the finding was wrong. The name
    that settles it in one glance was in the response that BUILT the universe
    file, in the same row as the Type the build already reads, and was thrown
    away.

    Two states have to stay distinguishable, because the fix arrived on
    2026-08-20 and the file is rebuilt on Sundays. A universe file that
    predates the field carries nothing for any row, which is ONE fact about the
    file; a file that has the field but nothing for one symbol is a fact about
    that symbol. Printing the second twenty times is how one absence would read
    as twenty.
    """
    named = [dict(row, name=f"{row['code']} Holdings Inc") for row in UNIVERSE_ROWS]
    named[0] = {k: v for k, v in named[0].items() if k != "name"}

    block, _packet, _rows = _run(universe=named)
    if block.get("instrument_name_reason") is not None:
        failures.append("a universe file carrying instrument names still reports "
                        f"{block['instrument_name_reason']!r}, which says the "
                        "whole file predates the field")
    if block.get("instrument_names_on_file") != len(named) - 1:
        failures.append(f"the block counts {block.get('instrument_names_on_file')!r} "
                        f"names on file where {len(named) - 1} rows carry one")
    unnamed = [r for r in block["rows"] if r.get("name") is None]
    for row in unnamed:
        if not row.get("name_reason"):
            failures.append(f"{row['symbol']} carries no name and no reason for "
                            "it, so a reader cannot tell an absent instrument "
                            "from an absent field")
    for row in block["rows"]:
        if row.get("name") and row.get("name_reason"):
            failures.append(f"{row['symbol']} carries both a name and a reason "
                            "it has none, and only one of those can be true")

    # And the state every file on disk is in until the next Sunday rebuild.
    block, _packet, _rows = _run()
    reason = block.get("instrument_name_reason")
    if not reason:
        failures.append("a universe file with no instrument name anywhere reports "
                        f"{reason!r}, so the section is silently missing a field "
                        "rather than saying the file predates it")
    if any(r.get("name_reason") for r in block["rows"]):
        failures.append("a file that predates the field still puts a per row "
                        "reason on every row, which prints one fact about the "
                        "file once for each row of the table")

    # The fallback report is where a reader actually meets this, and it is the
    # report that runs on the morning the narrative call already failed.
    packet = {"notable_movers": block, "candidates": [], "session_date": SESSION}
    text = analyst.fallback_report(packet, "the claim asked for it")
    # The report capitalises the sentence, so the tail is what to look for.
    if reason and reason[1:] not in text:
        failures.append("the fallback report drops the reason the names are "
                        "missing, so the section looks like it never had them")

    block, _packet, _rows = _run(universe=named)
    packet = {"notable_movers": block, "candidates": [], "session_date": SESSION}
    text = analyst.fallback_report(packet, "the claim asked for it")
    for row in block["rows"]:
        if row.get("name") and f"{row['name']}." not in text:
            failures.append(f"the fallback report names {row['symbol']} in the "
                            "table and never says what it is")
            break
    for row in block["rows"]:
        bare = row["symbol"].split(".")[0]
        if text.count(f"{bare} is ") > 1:
            failures.append(f"{bare} is identified {text.count(f'{bare} is ')} "
                            "times, where the paragraph is one sentence per "
                            "distinct ticker rather than one per row")
            break

    print("  claim 24        a row says what the instrument IS, and a file that "
          "predates the field says so once rather than once per row")


def claim_the_sections_own_words_pass_the_quantifier_guard(
        failures: list[str]) -> None:
    """The section cannot be the thing that costs the morning its narrative.

    REPORT_TEMPLATE.md tells the model to quote this section's reasons WORD FOR
    WORD rather than paraphrase them, and analyst.quantifier_violations then
    scans the model's output. That guard flags a quantifier near a set word:
    every, all, none, each, most or majority within six words either side of
    candidate, name or watchlist, and "no" within six words AFTER one.

    Five of the section's reasons tripped it as first written, "no name on the
    prior_session leg carries a move_sigma" among them. The guard is in warn
    mode today, so the cost would have been a flag in the log rather than a lost
    report; CRITERIA.md says what has to be true before it flips to enforcing,
    and on that day a quoted reason would be regenerated twice and then fall
    back to the Python report. The section's own words would have cost the
    narrative, every morning, for as long as the list was short.

    They are written in counts now, which is the rule fallback_report's prose
    already follows. This walks what the section actually produces rather than
    checking literals, so a reason added later is covered by construction.
    """
    seen: list[str] = []

    # Four fixtures, chosen to reach different reason strings: the healthy one,
    # a lost sidecar, a silent collector, and a sidecar with no closes at all,
    # which is what drives the "0 rows carried both" and short list branches.
    _write_closes()
    block, packet, _rows = _run()
    seen += _section_prose(block, packet)

    (config.DATA_DIR / f"universe-closes-{SESSION}.json").unlink(missing_ok=True)
    block, packet, _rows = _run()
    seen += _section_prose(block, packet)

    _write_closes()
    block, packet, _rows = _run(bars={})
    seen += _section_prose(block, packet)

    _write_closes(closes={"NOCLOSE.US": {"c1": None, "c2": None, "c3": None}})
    block, packet, _rows = _run(bars={})
    seen += _section_prose(block, packet)

    # Two more since 2026-08-22, so that all four of the ranked list states
    # reach this walk rather than the two an ordinary morning produces. The
    # sentences a list writes when it is uncomputable or below its floor are
    # the ones a reader sees on the mornings the section has least to say, and
    # they are the ones nothing else here would have scanned.
    _write_closes()
    block, packet, _rows = _run(
        stats={symbol: {"return_stdev_20d": None, "sessions_used": 250}
               for symbol in STATS})
    seen += _section_prose(block, packet)

    _write_closes(closes={symbol: {"c3": 100.0, "c2": 100.0, "c1": 100.4}
                          for symbol in ("QUIET.US", "LOUD.US", "MEGA.US")})
    block, packet, _rows = _run()
    seen += _section_prose(block, packet)

    # And the block the wrapper publishes when the assembly raises.
    seen += _section_prose(scan.empty_notable_block(
        "the notable movers section raised ValueError: a name nobody guarded"),
        scan.Packet())

    unique = sorted(set(seen))
    if len(unique) < 8:
        failures.append(f"only {len(unique)} distinct string(s) were collected, "
                        "which is too few to be the section's prose. The walk "
                        "proved nothing.")
    for line in unique:
        hits = analyst.quantifier_violations(line)
        for hit in hits:
            failures.append(
                f"a string this section hands the model trips the quantifier "
                f"guard on {hit.get('quantifier')!r}: {line!r}. The template "
                "tells the model to quote these word for word, so on the day "
                "the guard flips to enforcing this costs the narrative rather "
                "than the section.")

    print(f"  own words    {len(unique)} distinct reasons the model is told to "
          "quote, and not one asserts a quantifier over the candidate set")


def claim_the_watchlist_mark_is_filled_after_the_screens_decide(
        failures: list[str]) -> None:
    """also_on_watchlist is not null on every row of every run.

    It was. 4.4 says a name already on the day or swing watchlist appears here
    anyway and the row says so inline, because two sections selecting one name
    on different grounds is information and hiding it is not. The mark reads
    day_eligible and swing_eligible off the candidate, and those are set by
    evaluate_eligibility INSIDE stamp_all, which runs after vintage.enforce.
    The section has to be assembled BEFORE enforce, because enforce is handed a
    dict built by hand and check (e) reads the rows out of it. So at assembly
    time neither key exists on any candidate, _watchlist_mark returned None for
    every row, and the mark was dead on every run this section has ever made.

    It is filled by a second pass after stamp_all now. The mark is
    presentational: not a leg, not a vintage, nothing check (e) reads, so
    filling it after the gate costs the gate nothing.

    Checked both ways, because the ordering is the whole defect: the marking
    pass itself, and that build_packet calls it after stamp_all rather than
    before.
    """
    import ast
    import pathlib as _pathlib

    _write_closes()
    # candidates=[] is the real shape at assembly time: build_packet assembles
    # the section before stamp_all, so no candidate carries day_eligible or
    # swing_eligible yet whatever the screens will decide later.
    block, _packet, _rows = _run(candidates=[])

    if any(row.get("also_on_watchlist") for row in block["rows"]):
        failures.append("a row was marked at assembly time, when no candidate "
                        "carries an eligibility flag yet, so this claim is "
                        "measuring the fixture rather than the ordering")

    # The screens then decide, and the pass fills the mark in.
    candidates = [
        {"symbol": "QUIET.US", "day_eligible": True, "swing_eligible": False},
        {"symbol": "LOUD.US", "day_eligible": False, "swing_eligible": True},
        {"symbol": "MEGA.US", "day_eligible": True, "swing_eligible": True},
        {"symbol": "TINY.US", "day_eligible": False, "swing_eligible": False},
    ]
    marked, screened_neither = scan.mark_notable_watchlist(block, candidates)
    got = {row["symbol"]: row.get("also_on_watchlist") for row in block["rows"]}
    # TINY is a candidate that cleared neither screen, which is a DIFFERENT
    # answer from a symbol nothing screened: both used to come out as a bare
    # null, and roughly 2,742 of the 2,754 symbols this section can reach were
    # never screened at all, so reading that blank as "the screen looked and
    # said no" is the wrong conclusion in nearly every case.
    for symbol, wanted in (("QUIET.US", "day"), ("LOUD.US", "swing"),
                           ("MEGA.US", "day and swing"),
                           ("TINY.US", "screened, neither"),
                           ("DOWN.US", None)):
        if symbol in got and got[symbol] != wanted:
            failures.append(f"{symbol} is marked {got[symbol]!r} where the "
                            f"screens make it {wanted!r}")
    # Counted over ROWS and not over symbols: one symbol selected on two legs
    # is two rows by design, and both of them carry the mark.
    #
    # And counted in TWO buckets, because only three of the five marks mean the
    # symbol is on a watchlist. "screened, neither" means the screens looked and
    # refused it for both, which is the opposite of an overlap, and counting it
    # made build_packet's gap say five rows named a symbol that was also on a
    # watchlist on a morning when two of them had been refused.
    on_rows = sum(1 for row in block["rows"]
                  if row.get("also_on_watchlist")
                  and row["also_on_watchlist"] != scan.SCREENED_NEITHER)
    neither_rows = sum(1 for row in block["rows"]
                       if row.get("also_on_watchlist") == scan.SCREENED_NEITHER)
    if marked != on_rows:
        failures.append(f"the pass reported {marked} row(s) on a watchlist and "
                        f"the rows carry {on_rows}")
    if screened_neither != neither_rows:
        failures.append(f"the pass reported {screened_neither} screened-neither "
                        f"row(s) and the rows carry {neither_rows}")
    if marked == 0:
        failures.append("no row was marked at all, so the fixture never reached "
                        "a name the screens passed and this proved nothing")
    if neither_rows and marked >= marked + neither_rows:
        failures.append("the two counts overlap, so a refused name is still "
                        "being reported as an overlap between the sections")

    # And build_packet must call it AFTER stamp_all, or it is dead again.
    source = _pathlib.Path(scan.__file__).read_bytes().decode("utf-8")
    tree = ast.parse(source)
    build = next((n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "build_packet"),
                 None)
    if build is None:
        failures.append("scan.build_packet is gone")
        return
    order: list[tuple[int, str]] = []
    for node in ast.walk(build):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("stamp_all", "mark_notable_watchlist",
                                "notable_section"):
                order.append((node.lineno, node.func.id))
    order.sort()
    names = [name for _line, name in order]
    for wanted in ("notable_section", "stamp_all", "mark_notable_watchlist"):
        if wanted not in names:
            failures.append(f"build_packet does not call {wanted}")
    if names.count("mark_notable_watchlist") and names.count("stamp_all"):
        if names.index("mark_notable_watchlist") < names.index("stamp_all"):
            failures.append(
                "build_packet marks the notable rows BEFORE stamp_all, so "
                "day_eligible and swing_eligible are not set yet and the mark "
                "is null on every row again. That is the defect this claim "
                "exists for and it reads exactly like a quiet morning.")

    print(f"  mark order   {marked} row(s) marked after the screens decide, and "
          "build_packet calls the pass after stamp_all")


def claim_a_name_off_the_watchlist_is_marked_and_not_hidden(
        failures: list[str]) -> None:
    """A watchlist name appears here anyway, and the row says so.

    4.4. Two sections selecting the same name on different grounds is
    information; hiding it is not. And a name outside the candidate set is NOT
    CHECKED for a catalyst rather than being called uncatalysed, per 4.6: no
    news is fetched for any name outside the existing candidate set, because
    doing so would multiply the call count over a set an order of magnitude
    larger.
    """
    _write_closes()
    block, _packet, _rows = _run()
    rows = {(r["leg"], r["symbol"]): r for r in block["rows"]}

    heard = rows.get(("premarket", "HEARD.US"))
    if heard is None:
        failures.append("the one candidate the collector heard is absent from "
                        "the premarket leg")
    else:
        if heard["also_on_watchlist"] != "day":
            failures.append("a day watchlist name carries mark "
                            f"{heard['also_on_watchlist']!r} rather than 'day'")
        if heard["catalyst_state"] != "fetched" or not heard["catalyst"]:
            failures.append("a candidate whose news WAS fetched reports "
                            f"{heard['catalyst_state']!r} with catalyst "
                            f"{heard['catalyst']!r}")

    outsiders = [r for r in block["rows"] if r["symbol"] != "HEARD.US"]
    wrong = [r["symbol"] for r in outsiders if r["catalyst_state"] != "not checked"]
    if wrong:
        failures.append(f"{wrong} are outside the candidate set and report a "
                        "catalyst state other than 'not checked'. No news is "
                        "fetched for them, and 'no catalyst' is a different "
                        "fact from 'nobody looked'.")
    marked = [r["symbol"] for r in outsiders if r["also_on_watchlist"]]
    if marked:
        failures.append(f"{marked} are not candidates and carry a watchlist mark")

    print(f"  marks        the watchlist name is marked and kept, and "
          f"{len(outsiders)} names nobody fetched news for read 'not checked'")


CLAIMS = (
    claim_nothing_in_the_section_reaches_picks,
    claim_the_section_never_imports_pool_recall,
    claim_a_notable_only_symbol_never_reaches_the_picks_table,
    claim_a_two_session_move_is_scaled_by_the_root_of_its_span,
    claim_a_move_sigma_is_null_with_its_reason_and_never_substituted,
    claim_a_quiet_name_under_the_discovery_floor_can_still_appear,
    claim_no_ranked_list_mixes_two_legs,
    claim_each_list_ranks_on_the_key_it_names,
    claim_the_premarket_sigma_list_ranks_on_the_size_of_the_move,
    claim_a_mis_stamped_notable_row_stops_the_run,
    claim_the_context_tickers_stay_out_of_the_premarket_leg,
    claim_a_stale_collector_print_is_not_a_notable_move,
    claim_a_premarket_row_carries_the_age_of_its_price,
    claim_the_section_widens_containment_only_by_its_own_rows,
    claim_the_section_examines_the_universe_and_not_the_survivors,
    claim_a_missing_input_names_the_leg_it_lost,
    claim_an_empty_list_says_which_empty_it_is,
    claim_a_malformed_input_costs_the_section_and_not_the_run,
    claim_a_defect_in_the_section_costs_the_section,
    claim_a_closes_file_from_another_session_is_refused,
    claim_a_close_from_another_session_is_not_stamped_with_this_one,
    claim_an_undated_sidecar_costs_two_legs_and_not_the_morning,
    claim_the_counters_say_whether_they_were_read_or_derived,
    claim_a_name_off_the_watchlist_is_marked_and_not_hidden,
    claim_the_watchlist_mark_is_filled_after_the_screens_decide,
    claim_the_sections_own_words_pass_the_quantifier_guard,
    claim_a_row_says_what_the_instrument_is_or_why_it_cannot,
)


def main() -> int:
    failures: list[str] = []
    # Written once before anything runs, and rewritten by the claims that need
    # a different shape. The order below is the order they are declared in.
    _write_closes()
    for claim in CLAIMS:
        claim(failures)
        _write_closes()
    if failures:
        return _report(failures)
    print(f"PASS  {len(CLAIMS)} claims: the notable movers section examines the "
          "universe, ranks within one leg at a time, scales a multi session move "
          "by the root of its span, names every input it lost, and cannot reach "
          "picks")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
