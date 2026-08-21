"""Regression test for Layer 4, the notable movers section.

Run it through the suite: `python -m tests.run_tests --only tests.test_notable`
from the project root with src on PYTHONPATH. Makes no network call and spends
no quota: every input is synthetic, the closes sidecar is written into the
sandbox, the gap statistics read is stubbed, and the exchange calendar is a
plain weekday rule so the answer is the same on any machine.

Twelve claims, and they are grouped by what they defend rather than by the
order the code runs in.

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
collector that heard nothing, and counters the file is too old to carry.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

from core import config
from core import criteria
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
UNIVERSE_ROWS = [
    {"symbol": "QUIET.US", "code": "QUIET", "market_cap": 900_000_000.0},
    {"symbol": "LOUD.US", "code": "LOUD", "market_cap": 400_000_000.0},
    {"symbol": "MEGA.US", "code": "MEGA", "market_cap": 3_000_000_000_000.0},
    {"symbol": "ONESHOT.US", "code": "ONESHOT", "market_cap": 800_000_000.0},
    {"symbol": "TINY.US", "code": "TINY", "market_cap": 50_000_000.0},
    {"symbol": "HEARD.US", "code": "HEARD", "market_cap": 700_000_000.0},
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
}


def _bar(symbol: str, minute: str, close: float) -> dict[str, Any]:
    return {"symbol": symbol, "minute_et": f"{SESSION}T{minute}:00-04:00",
            "minute_epoch": 0, "o": close, "h": close, "l": close, "c": close,
            "v": 1000}


def _write_closes(session: str = SESSION, stamped: str | None = None,
                  closes: dict[str, Any] | None = None,
                  counters: bool = False) -> None:
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
    }
    if counters:
        payload["names_with_close"] = {
            key: sum(1 for r in rows.values() if r.get(key) is not None)
            for key in ("c1", "c2", "c3")}
        payload["names_with_both_closes_for_leg"] = {
            "prior_session": sum(1 for r in rows.values()
                                 if r.get("c1") is not None and r.get("c2") is not None),
            "two_session": sum(1 for r in rows.values()
                               if r.get("c1") is not None and r.get("c3") is not None),
        }
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
         session: str = SESSION) -> tuple[dict[str, Any], scan.Packet, list[dict[str, Any]]]:
    """One assembly against the fixture, with the database read stubbed out.

    gap_stats.load_all is replaced rather than seeded, because the real one
    calls store.init, which runs an executescript and an UPDATE and commits.
    The point here is the section's arithmetic, not SQLite's.
    """
    if bars is None:
        bars = {"HEARD.US": [_bar("HEARD.US", "08:40", 103.0)],
                "SPY.US": [_bar("SPY.US", "08:40", 700.0)]}
    rows = _candidates() if candidates is None else candidates
    real = gap_stats.load_all
    gap_stats.load_all = lambda as_of=None: dict(STATS)
    try:
        packet = scan.Packet()
        block = scan.notable_movers(
            session, {"symbols": UNIVERSE_ROWS}, bars, rows, packet)
    finally:
        gap_stats.load_all = real
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
    """Four null outcomes, four reasons, and never a number standing in.

    They are four and not one because the fixes differ: a name absent from the
    gap statistics table was never measured, a name present with a null column
    has fewer than min_sessions_for_move_sigma returns behind it, a name whose
    stdev is under min_return_stdev_pct has barely moved in twenty sessions and
    would otherwise report an enormous sigma on any move at all, and a null
    move has nothing to scale.

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
        ("a name absent from gap_stats", (5.0, None, 1), "no gap statistics row"),
        ("a null column", (5.0, {"return_stdev_20d": None}, 1),
         "fewer than"),
        ("a stdev under the floor", (5.0, {"return_stdev_20d": floor / 2}, 1),
         "min_return_stdev_pct"),
        ("a null move", (None, {"return_stdev_20d": 2.5}, 1), "no move"),
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

    print("  null sigma   four absences, four reasons, and a stdev sitting "
          f"exactly on {floor} still divides")


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
    # lists worth having separately.
    size = block["lists"]["two_session_by_move"]
    if size and size[0] != "TINY.US":
        failures.append(f"the two session size list leads with {size[0]} rather "
                        "than the 40 percent mover, so it is not ranking on the "
                        "raw move")

    print(f"  under floor  a 2 percent move at 2.0 sigma leads the sigma list "
          f"{ranked}, and the size list leads with {size[0] if size else None}")


# ---------------------------------------------------------- the labelling

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
    if (block["legs"]["premarket"]["examined"] or 0) != 1:
        failures.append("the premarket leg examined "
                        f"{block['legs']['premarket']['examined']} names where "
                        "the fixture heard two, one of them a context ticker")

    print(f"  context out  {block['context_symbols_excluded']} context ticker "
          "excluded and counted, and the premarket leg examined the rest")


# ------------------------------------------------------------ the degrades

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

    print("  degrade      a lost sidecar names all three legs and nulls the "
          "examined count, and a silent collector loses only its own")


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
    _write_closes(counters=False)
    block, _packet, _rows = _run()
    if block["counter_source"] != "derived":
        failures.append("a sidecar with no per leg counters reported "
                        f"counter_source {block['counter_source']!r}")
    derived = block["names_with_both_closes_for_leg"]

    _write_closes(counters=True)
    block, _packet, _rows = _run()
    if block["counter_source"] != "read":
        failures.append("a sidecar carrying the counters reported counter_source "
                        f"{block['counter_source']!r}")
    if block["names_with_both_closes_for_leg"] != derived:
        failures.append("the derived counts disagree with the written ones: "
                        f"{derived} against "
                        f"{block['names_with_both_closes_for_leg']}. They are "
                        "the same question and must give the same answer.")

    print(f"  provenance   the same counts read and derived agree at {derived}, "
          "and the block says which of the two it did")


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
    claim_a_two_session_move_is_scaled_by_the_root_of_its_span,
    claim_a_move_sigma_is_null_with_its_reason_and_never_substituted,
    claim_a_quiet_name_under_the_discovery_floor_can_still_appear,
    claim_no_ranked_list_mixes_two_legs,
    claim_a_mis_stamped_notable_row_stops_the_run,
    claim_the_context_tickers_stay_out_of_the_premarket_leg,
    claim_the_section_examines_the_universe_and_not_the_survivors,
    claim_a_missing_input_names_the_leg_it_lost,
    claim_a_closes_file_from_another_session_is_refused,
    claim_the_counters_say_whether_they_were_read_or_derived,
    claim_a_name_off_the_watchlist_is_marked_and_not_hidden,
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
