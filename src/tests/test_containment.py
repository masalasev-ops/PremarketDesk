"""Regression test for the containment checker.

Run it directly: `python -m tests.test_containment` with PYTHONPATH set to
src/, exit 0 on pass.

Six claims are written inline in main(), numbered 1 to 6 in its comments, and
seven more are the claim_ functions below. Two are the foundation:
  1. Ordinary finance acronyms in prose (ETF, CEO, FDA, SEC, EPS, IPO, GDP,
     CPI, FOMC) never trip containment, because prose tokens are not ticker
     claims. Only tokens in table cells or prefixed with $ are candidates,
     and only candidates that name a real universe symbol are claims.
  2. A report naming a real universe ticker that is absent from packet.json
     still fails, through a table cell and through a $ prefix alike.

The rest widen that to context ETFs and single letter listings, to whether the
check examined anything at all, to the two watchlist tables the template
requires even when empty, and then to the quantifier guard, its flag log, the
watchdog's backlog line and the single word list all three sources of report
prose are checked against.
"""

from __future__ import annotations

import contextlib
import json
import sys
from typing import Any

from morning import analyst
from tests import conftest
from core import config
from core import criteria

ROOT_RUNS = config.PROJECT_ROOT / "runs"

ACRONYMS = ["ETF", "CEO", "FDA", "SEC", "EPS", "IPO", "GDP", "CPI", "FOMC"]


def build_packet_text() -> str:
    packet = {
        "session_date": "2026-01-02",
        "candidates": [
            {"symbol": "ARX.US", "conviction": "green", "day_eligible": True},
        ],
        "market_snapshot": [{"label": "spy", "symbol": "SPY.US"}],
        # The bands every real packet carries, read from criteria rather
        # than typed out here, and by the same call scan.py makes when it
        # stamps them. A fixture that states the bands on its own authority
        # can disagree with the file the run reads, and then the claim
        # passes while the page is wrong. Same argument as _FROZEN_UNIVERSE
        # below, reached from the other direction: that one is frozen
        # BECAUSE the live file moves under it, this one is live because
        # the whole point is agreeing with what scan writes.
        "criteria_summary": {
            "score_buckets": [band.describe() for band
                              in criteria.load().bands("score_buckets")],
        },
    }
    return json.dumps(packet)


# The names this module's assertions need the universe to contain. Written as
# a fixture rather than read from whatever universe.json holds today.
#
# WHY. analyst.check_report validates every ticker claim against the union of
# universe.json and the context list, so each assertion below depends on WHICH
# NAMES that file carries. It carried 2,745 on 2026-08-15, 2,126 on 2026-08-20
# and 1,013 on 2026-08-21, and the twenty one ONE LETTER listings that the F
# and A checks exist to exercise vanished with the last of those. Three checks
# in main() went red on 2026-08-21 against code nobody had touched, because the
# file underneath them had moved.
#
# The twelve prose names are the ones the real 2026-08-14 report puts in bold
# prose, which is the whole point of the vacuum check: they must be recognised
# as listings before their absence from a ticker column can be reported.
_FROZEN_UNIVERSE = (
    # One letter listings. F is Ford and A is Agilent, and A is also the
    # English article, which is why one is a prose stopword and both must
    # still be checked inside a Ticker column.
    "F", "A", "T",
    # The twelve the 2026-08-14 report names in prose.
    "ANGX", "ARX", "AVAH", "BSP", "CLBT", "LFTO",
    "MH", "OMER", "REZI", "SECZ", "TPR", "WDAY",
    # Enough ordinary names that pick_absent_universe_symbol has something to
    # return that the test packet does not carry.
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOG",
)


@contextlib.contextmanager
def freeze_universe():
    """Write the fixture universe over the sandbox copy, then put it back.

    RESTORES ON EXIT, and the first version did not. test_containment runs
    third in run_tests.SUITE and test_backtest seventh, and backtest_pool sorts
    its 42 name subscription cap on avg_dollar_volume_20d read from this file.
    A twenty name fixture left in place changed the input of a later module in
    the same interpreter. The suite stayed green, which is worse than failing:
    it means claim_four was scored against a universe it never asked for.

    A fixture that does not restore is not isolation, it is contamination with
    a different owner.

    config.UNIVERSE_PATH is the sandbox's under run_tests and, since
    2026-08-21, under a direct import too: conftest redirects every writable
    path the moment it is imported. So this overwrites a copy and never the
    live file. The module that used to read the live universe here is the same
    module whose live universe was destroyed by a claim run outside the
    harness, which is the argument for both halves of that change.
    """
    config.UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    previous = (config.UNIVERSE_PATH.read_bytes()
                if config.UNIVERSE_PATH.is_file() else None)
    config.UNIVERSE_PATH.write_text(json.dumps({
        "generated_at": "2026-08-21T00:00:00-04:00",
        "count": len(_FROZEN_UNIVERSE),
        "frozen_fixture": "tests/test_containment.py, see _FROZEN_UNIVERSE",
        "symbols": [{"code": name, "symbol": f"{name}.US", "name": name,
                     "exchange": "NASDAQ"} for name in _FROZEN_UNIVERSE],
    }), encoding="utf-8")
    try:
        yield
    finally:
        if previous is None:
            config.UNIVERSE_PATH.unlink(missing_ok=True)
        else:
            config.UNIVERSE_PATH.write_bytes(previous)


def pick_absent_universe_symbol(packet_text: str) -> str:
    """A real universe ticker that the packet does not carry."""
    universe = json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8"))
    packet_symbols = {"ARX", "SPY"}
    for row in universe.get("symbols", []):
        bare = str(row.get("symbol", "")).split(".")[0].upper()
        if bare and bare not in packet_symbols and bare not in ACRONYMS and len(bare) >= 2:
            return bare
    raise RuntimeError("universe.json yielded no usable symbol for the test")



def claim_briefing_table_cannot_stand_in(failures: list[str]) -> None:
    """A briefing table must not satisfy the requirement that the watchlists exist.

    The vacuum detector used to be `columns_scanned == 0`. That worked while
    the only tables carrying a Ticker header were the two watchlists, and it
    stopped working the moment a third was added: any table with a Ticker
    header raised the count above zero and the guard reported a clean pass.

    This is not hypothetical and this claim is the measurement of it. The real
    2026-08-14 report omitted BOTH watchlist tables because both screens were
    empty, while naming twelve candidates in bold prose. Appending a Notable
    movers table to that exact report flipped structure_failed from True to
    False, with all 22 prose ticker claims still unvalidated. The guard now
    requires the two tables BY NAME, so a briefing table contributes its cells
    as claims to check and cannot stand in for a watchlist that was never
    written.
    """
    real_report = ROOT_RUNS / "2026-08-14" / "report.md"
    real_packet = ROOT_RUNS / "2026-08-14" / "packet.json"
    if not real_report.is_file() or not real_packet.is_file():
        print("  claim briefing  SKIPPED, the 2026-08-14 archive is not on disk")
        return
    report_text = real_report.read_text(encoding="utf-8")
    packet_text = real_packet.read_text(encoding="utf-8")
    # Built from REPORT_TEMPLATE.md rather than written out. This literal
    # carried seven columns while the shipped section carries nine, and it was
    # decoupled from the template for as long as it existed, which is the exact
    # drift conftest.watchlist_table was written to end.
    from tests import conftest

    NOTABLE = "\n" + conftest.watchlist_table("notable movers", [
        "| OMER | prior_session | 2026-08-13 | +7.10 | 3.2 | 1.2B "
        "| not checked | - | - |",
    ])

    _, _, plain = analyst.check_report(report_text, packet_text)
    if not plain["structure_failed"]:
        failures.append("the archived 2026-08-14 report no longer fails on "
                        "structure, so this claim is measuring nothing")
        return

    _, _, withtable = analyst.check_report(report_text + NOTABLE, packet_text)
    if not withtable["structure_failed"]:
        failures.append(
            "appending a Notable movers table to the 2026-08-14 report made it "
            f"PASS the structure gate: {withtable}. A briefing table cannot "
            "stand in for a watchlist that was never written.")
    if set(withtable["tables_missing"]) != {"day watchlist", "swing watchlist"}:
        failures.append(f"the guard did not name both missing watchlists: "
                        f"{withtable['tables_missing']}")
    if withtable["columns_scanned"] <= plain["columns_scanned"]:
        failures.append("the briefing table contributed no scanned column, so it "
                        "is not being read for claims at all")

    print(f"  claim briefing  the 2026-08-14 report still fails on structure with a "
          f"briefing table appended, which raised columns scanned "
          f"{plain['columns_scanned']} to {withtable['columns_scanned']} while both "
          "watchlists stay named as missing")


def claim_headers_cannot_diverge(failures: list[str]) -> None:
    """The template, the fallback report and the containment guard agree.

    That header string exists in four places and every one of them has a
    different reason to be edited: REPORT_TEMPLATE.md tells the model what to
    write, fallback_report writes it when the model never runs, _REQUIRED_TABLES
    is what the guard looks for, and the fixtures stand in for all three. On
    2026-08-17 the fixtures had already drifted from the other three and nothing
    failed, because the guard counted ticker columns rather than matching them.

    So the agreement is asserted rather than assumed. Any one of the four can be
    edited; editing one WITHOUT the others turns this red.
    """
    from tests import conftest

    template = conftest.watchlist_headers()

    # (1) the guard looks for exactly what the template pins.
    guard = dict(analyst._REQUIRED_TABLES)
    for kind, header in template.items():
        if kind not in guard:
            failures.append(f"the guard has no required table named {kind!r}")
            continue
        if guard[kind] != header:
            failures.append(
                f"the {kind} header in REPORT_TEMPLATE.md and in "
                f"analyst._REQUIRED_TABLES have diverged.\n"
                f"      template: {header}\n"
                f"      guard:    {guard[kind]}")
    for kind in sorted(set(guard) - set(template)):
        failures.append(f"the guard requires a table {kind!r} the template does "
                        "not define, so the report can never satisfy it")

    # (2) the fallback emits exactly what the guard requires. It runs when the
    # model does not, and a fallback that fails containment is a fallback that
    # cannot ship.
    fallback = analyst.fallback_report(
        json.loads(build_packet_text()),
        "the narrative pass was stubbed out by this claim")
    for kind, header in conftest.template_headers().items():
        if header not in fallback:
            failures.append(
                f"fallback_report does not emit the {kind} header the template "
                f"pins, so a fallback report would fail the structure gate.\n"
                f"      wanted: {header}")

    # (3) and the fallback therefore passes the guard end to end, which is the
    # property all of the above exists to produce.
    _, _, coverage = analyst.check_report(fallback, build_packet_text())
    if coverage["structure_failed"]:
        failures.append(f"the fallback report fails its own structure gate: "
                        f"missing {coverage['tables_missing']}")

    # (4) and no test module carries either header as a literal, which is what
    # keeps the agreement above from being re-broken the next time a fixture
    # needs a table. Deliberately minimal probe tables like "| Ticker | Gap % |"
    # are untouched: they exist to be a DIFFERENT shape, and pinning them to
    # the template would stop them probing what they probe.
    from pathlib import Path

    tests_dir = Path(__file__).resolve().parent
    for module in sorted(tests_dir.glob("*.py")):
        if module.name == "conftest.py":
            continue  # it is the extractor, so it names the prefix it looks for
        body = module.read_text(encoding="utf-8")
        for kind, header in conftest.template_headers().items():
            if header in body:
                failures.append(
                    f"{module.name} carries the {kind} header as a literal. Build "
                    "it with conftest.watchlist_table so a template change breaks "
                    "the fixture instead of silently decoupling it.")

    # (5) the notable header is pinned the same way and is deliberately NOT a
    # required table. It has the same four places to drift between as the two
    # watchlists, minus the guard, so it gets the same treatment minus that one.
    notable = conftest.template_headers().get("notable movers")
    if notable != analyst.NOTABLE_HEADER:
        failures.append(
            "the notable movers header in REPORT_TEMPLATE.md and in "
            "analyst.NOTABLE_HEADER have diverged.\n"
            f"      template: {notable}\n"
            f"      analyst:  {analyst.NOTABLE_HEADER}")
    if "notable movers" in analyst._REQUIRED_TABLES:
        failures.append(
            "the notable movers table is in analyst._REQUIRED_TABLES. The vacuum "
            "detector requires the two watchlists BY NAME precisely so that a "
            "briefing table cannot satisfy it, and a report with no watchlist "
            "and a full notable section would now pass the structure gate.")

    print(f"  claim headers   {len(conftest.template_headers())} header(s) agree "
          "across REPORT_TEMPLATE.md, analyst and fallback_report, the notable "
          "one is pinned without being able to satisfy the vacuum detector, the "
          "fallback passes the structure gate, and no test module carries any of "
          "them as a literal")

def _list_reports() -> dict[str, dict[str, Any]]:
    """The four ranked lists' own outcome lines, as scan writes them.

    Assembled through scan._list_report_text rather than as literals, on the
    header precedent: this fixture exists to prove the fallback's prose passes
    the guard the fallback lives beside, and a hand written copy of a sentence
    production builds is a copy that stops being that sentence.

    The four states are all four here on purpose. One list ranked and full, one
    uncomputable because its ranking key is null across the leg, which is every
    morning until the Sunday rebuild, one whose leg carried nothing to rank, and
    one whose leg measured rows that stayed below its floor.
    """
    from morning import scan

    shapes = {
        "prior_session_by_sigma": {
            "state": scan.LIST_RANKED, "reason": None,
            "considered": 2753, "qualified": 41, "selected": 5},
        "prior_session_by_market_cap": {
            "state": scan.LIST_BELOW_THE_FLOOR,
            "reason": ("0 of 2753 on the prior_session leg cleared this list's "
                       "floor, a move of at least 1 percent, which is "
                       "CRITERIA.md [Notable] min_abs_gap_pct, with a market cap "
                       "on file. The leg was measured and nothing in it reached "
                       "that line."),
            "considered": 2753, "qualified": 0, "selected": 0},
        "two_session_by_move": {
            "state": scan.LIST_NOTHING_TO_RANK,
            "reason": ("the two_session leg's input was read and carried 0 rows "
                       "this list could rank: 0 rows carried both of the closes "
                       "the two_session leg needs"),
            "considered": 0, "qualified": 0, "selected": 0},
        "premarket_by_sigma": {
            "state": scan.LIST_UNCOMPUTABLE,
            "reason": ("0 of 39 on the premarket leg carry a move_sigma, which "
                       "is the key this list ranks on, so it could not be "
                       "computed. 39 of 39 report: return_stdev_20d is null on a "
                       "row covering 250 sessions, which is enough for it, so "
                       "the column was written before it was computed. The "
                       "Sunday 21:00 universe rebuild fills it."),
            "considered": 39, "qualified": 0, "selected": 0},
    }
    out: dict[str, dict[str, Any]] = {}
    for name, report in shapes.items():
        report["leg"] = scan.leg_of_list_key(name)
        report["ranks_on"] = scan._LIST_RANKING_KEY[name]
        report["text"] = scan._list_report_text(name, report)
        out[name] = report
    return out


def claim_quantifiers_over_the_set_are_rejected(failures: list[str]) -> None:
    """A quantifier about the candidate set fails, and the tally sentence passes.

    The guard exists because a prompt rule was not enough twice before. On
    2026-08-18 the report asserted "every candidate" missed a condition one of
    twelve had cleared, and separately that "every candidate" traded below its
    prior day high while that same name traded above both it and its VWAP.
    Neither sentence broke a rule at the time: the template had asked for a
    summary it gave the model no way to compute.

    Both directions are proven here. A report that quotes screen_tally must
    PASS, or the fix would have traded a false claim for a failing run.
    """
    banned = ("The day screen produced nothing today. "
              "Every candidate missed the prior day high.\n")
    hits = analyst.quantifier_violations(banned)
    if not hits:
        failures.append("a report asserting 'every candidate' passed the quantifier guard")
    elif hits[0]["quantifier"] != "every" or hits[0]["set_word"] != "candidate":
        failures.append(f"the guard caught the wrong thing: {hits[0]}")

    # The sentence the template now instructs, built from screen_tally.
    quoted = ("The day screen produced nothing today. Failed conditions: "
              "require_above_prior_high 11 of 12, premarket_rvol 10 of 12.\n")
    if analyst.quantifier_violations(quoted):
        failures.append("the tally sentence the template now requires trips its "
                        f"own guard: {analyst.quantifier_violations(quoted)}")

    # The empty watchlist table's own none row sits under a heading carrying the
    # word watchlist. Scanning table rows would fail every empty morning, which
    # is the morning this guard matters most on.
    table = ("## Day watchlist\n\n"
             "| Ticker | Gap % |\n| --- | --- |\n| none | |\n\n"
             "The day screen produced nothing today. Failed conditions: "
             "premarket_rvol 10 of 12.\n")
    if analyst.quantifier_violations(table):
        failures.append("the empty watchlist table tripped the guard on its own "
                        f"none row: {analyst.quantifier_violations(table)}")
    # `no` says exactly what `none` says. Both spellings of the same claim have
    # to fail, or the ban is a spelling rule rather than a guard.
    for phrasing in ("No candidate cleared the price test.\n",
                     "None of the candidates cleared the price test.\n"):
        if not analyst.quantifier_violations(phrasing):
            failures.append(f"a report asserting {phrasing.strip()!r} passed the guard")
    # `no` is a determiner and governs what follows it. A backwards match would
    # fail this sentence, which asserts nothing about the set.
    determiner = "There is no premarket high for AS, so the candidate is dropped.\n"
    if analyst.quantifier_violations(determiner):
        failures.append("a determiner `no` before an unrelated noun tripped the guard: "
                        f"{analyst.quantifier_violations(determiner)}")
    print("  claim 7 a quantifier over the candidate set is rejected in both the "
          "none and no spellings, the screen_tally sentence passes, and neither an "
          "empty table's none row nor a determiner no is prose about the set")


def claim_flags_are_logged_for_measurement(failures: list[str]) -> None:
    """Every flag lands in the running log, pending, and the rate is counted.

    The guard's false positive rate was eyeballed at one in six on the day it
    shipped. An eyeballed rate decays into folklore, and this project has
    watched guards get rationalised away one failure at a time. So the flags
    accumulate with room for a verdict and the rate is counted from them.

    What is proven here is that a raised flag is RECORDED rather than only
    printed, that it starts with no verdict, and that the rate refuses to
    report itself until something has been judged. A rate that returned zero
    over an unjudged sample would be worse than no rate at all.
    """
    from ops import quantifier_flags

    # START FROM AN EMPTY LOG. This read the sandbox COPY of the live
    # quantifier-flags.jsonl, and the assertion below is that a fresh flag
    # arrives with nothing judged. That held while no real morning had ever
    # judged one. On 2026-08-21 the live file carried a judged flag, the
    # sandbox copy carried it too, and this claim went red against code that
    # had not changed: a claim resting on the CONTENT of live data rather than
    # on a fixture of its own. The path here is the sandbox's, so emptying it
    # costs nothing and makes the claim say the same thing on every tree.
    analyst.flag_log_path().write_text("", encoding="utf-8")
    before = len(quantifier_flags.load_flags())
    hits = analyst.quantifier_violations(
        "Every candidate missed the prior day high.\n")
    ids = analyst.record_quantifier_flags(hits, "2026-08-18", "report.md")
    if not ids:
        failures.append("a raised flag was not written to the running log")
        return
    flags = quantifier_flags.load_flags()
    if len(flags) != before + len(hits):
        failures.append(f"expected {before + len(hits)} flags on file, found {len(flags)}")
    latest = flags[-1]
    if latest.get("disposition") is not None:
        failures.append(f"a new flag arrived already judged: {latest}")
    for field in ("sentence", "quantifier", "set_word", "session", "line"):
        if not latest.get(field) and latest.get(field) != 0:
            failures.append(f"the logged flag carries no {field}: {latest}")

    measured = quantifier_flags.rate(flags)
    if measured["false_positive_rate"] is not None:
        failures.append("the rate reported a number with nothing judged: "
                        f"{measured}")
    quantifier_flags.mark(latest["id"], "false-positive", "test disposition")
    measured = quantifier_flags.rate(quantifier_flags.load_flags())
    if measured["judged"] < 1 or measured["false_positive_rate"] is None:
        failures.append(f"marking a flag did not move the measured rate: {measured}")
    print(f"  claim 8 a flag is logged pending, the rate refuses to report over "
          f"nothing judged, and a verdict moves it to "
          f"{measured['false_positive_rate']:.0%} of {measured['judged']}")


def claim_a_flag_cannot_cost_the_report(failures: list[str]) -> None:
    """Under either guard setting, a flagged morning still gets a report.

    The guard used to return exit 2 on any flag. The morning chain stops on the
    first non-zero code, so render, deliver and archive never ran and the
    morning got nothing at all, over one sentence, from a guard whose own false
    positive rate is still a sample of six. A guard that can cost the whole
    morning is a guard somebody switches off the first time it is wrong.

    Both settings are proven, against a model that will not stop saying it.
    Under warn, which is live, the narrative goes out untouched and the flag is
    recorded and named on the disclaimer. Under enforcing, the report is thrown
    away, regenerated with the sentence quoted back, and on a second failure the
    morning gets the plain table with that sentence in its disclaimer. Exit zero
    in both, because in both the morning has a report.
    """
    import io
    from contextlib import redirect_stdout
    from ops import quantifier_flags

    sentence = "Every candidate missed the prior day high."
    stubborn = (
        "# PremarketDesk test\n\n"
        "Nothing here is advice, the screen thresholds are unvalidated seed values.\n\n"
        f"{sentence}\n\n"
        + conftest.watchlist_table(
            "day watchlist",
            ["| ARX | 43.02 | 19.00 | 2.0 | 19.51 | 19.10 | 7.0 | green |"])
        + "\n"
        + conftest.watchlist_table("swing watchlist")
    )

    def run(session: str, mode: str):
        """Drive write_report against the stubborn model under one guard mode."""
        packet = {
            "session_date": session,
            "generated_at": session + "T08:45:00-05:00",
            "candidates": [{
                "symbol": "ARX.US", "conviction": "green", "day_eligible": True,
                "score": 7.0, "pm_rvol": 2.0, "gap_pct": 43.02, "price": 19.0,
                "prior_close": 13.3, "pm_high": 19.51, "pm_vwap": 19.1,
                "catalyst_found": True, "catalyst_class": "earnings",
                "collector_covered": True, "quote": {"name": "Aeries"},
            }],
            "market_snapshot": [{"label": "spy", "symbol": "SPY.US"}],
            "job_health": {"overdue": [], "line": None},
        }
        run_directory = config.run_dir(session)
        run_directory.mkdir(parents=True, exist_ok=True)
        packet_path = run_directory / "packet.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")

        corrections: list = []

        def stubborn_model(packet_text, correction=None):
            corrections.append(correction)
            return stubborn, {"output_tokens": 1, "total_cost_usd": 0.01}, None, "ok"

        before = len(quantifier_flags.load_flags())
        real_invoke, real_mode = analyst.invoke_claude, analyst.guard_mode
        analyst.invoke_claude = stubborn_model
        analyst.guard_mode = lambda: mode
        try:
            with redirect_stdout(io.StringIO()):
                code = analyst.write_report(packet_path)
        finally:
            analyst.invoke_claude, analyst.guard_mode = real_invoke, real_mode
        report_path = run_directory / "report.md"
        return {
            "code": code,
            "text": report_path.read_text(encoding="utf-8") if report_path.is_file() else None,
            "usage": json.loads((run_directory / "analyst_usage.json").read_text(encoding="utf-8")),
            "corrections": corrections,
            "flags": quantifier_flags.load_flags()[before:],
        }

    def disclaimer_of(text: str) -> str:
        return next((line for line in text.splitlines()
                     if "Nothing here is advice" in line), "")

    # ---- warn, which is what runs tomorrow morning
    warn = run("2026-01-05", analyst.GUARD_WARN)
    if warn["code"] != 0:
        failures.append(f"warn mode exited {warn['code']}, which stops the chain")
    if warn["text"] is None:
        failures.append("warn mode produced no report")
        return
    if sentence not in warn["text"]:
        failures.append("warn mode did not deliver the narrative it flagged")
    if warn["usage"].get("fallback") or warn["usage"].get("status") != "ok":
        failures.append(f"warn mode degraded the morning: {warn['usage'].get('status')}")
    if len(warn["corrections"]) != 1:
        failures.append(f"warn mode regenerated, calling the model "
                        f"{len(warn['corrections'])} times")
    if len(warn["flags"]) != 1:
        failures.append(f"warn mode logged {len(warn['flags'])} flag(s), expected 1")
    elif warn["flags"][0].get("outcome") != analyst.OUTCOME_WARNED:
        failures.append("a published flag is not marked as such: "
                        f"{warn['flags'][0].get('outcome')}")
    if "warn mode" not in disclaimer_of(warn["text"]):
        failures.append("warn mode published a flagged claim without saying so on "
                        f"the disclaimer: {disclaimer_of(warn['text'])}")

    # ---- enforcing, which is where this ends up
    strict = run("2026-01-06", analyst.GUARD_ENFORCING)
    if strict["code"] != 0:
        failures.append(f"a persistent quantifier flag exited {strict['code']}; the "
                        "chain stops on any non-zero code, so that is a lost morning")
    if strict["text"] is None:
        failures.append("a persistent quantifier flag produced no report at all")
        return
    if "narrative withheld" not in strict["text"]:
        failures.append("the degraded report does not say the narrative was "
                        f"withheld: {strict['text'].splitlines()[0]!r}")
    if "unavailable" in strict["text"].splitlines()[0]:
        failures.append("a withheld narrative is reported as an unavailable one, "
                        "which is the report lying about its own provenance")
    disclaimer = disclaimer_of(strict["text"])
    if sentence not in disclaimer:
        failures.append(f"the disclaimer does not quote the flagged sentence: {disclaimer}")
    if "flag " not in disclaimer:
        failures.append(f"the disclaimer does not name the flag id: {disclaimer}")
    for kind, header in conftest.watchlist_headers().items():
        if header not in strict["text"]:
            failures.append(f"the degraded report omits the {kind} table")

    # The regeneration has to be told what it did wrong. A blind retry against
    # a deterministic failure is a coin flip with no coin.
    if len(strict["corrections"]) != 2:
        failures.append(f"expected one regeneration, the model was called "
                        f"{len(strict['corrections'])} time(s)")
    elif strict["corrections"][0] is not None:
        failures.append("the first attempt carried a correction it could not have earned")
    elif not strict["corrections"][1] or sentence not in strict["corrections"][1]:
        failures.append("the regeneration was not told which sentence was rejected: "
                        f"{strict['corrections'][1]!r}")

    if len(strict["flags"]) != 2:
        failures.append(f"expected both raises logged, found {len(strict['flags'])}")
    else:
        outcomes = [f.get("outcome") for f in strict["flags"]]
        if outcomes != [analyst.OUTCOME_REGENERATED, analyst.OUTCOME_FELL_BACK]:
            failures.append(f"the flag outcomes do not distinguish the regeneration "
                            f"from the fallback: {outcomes}")
    if strict["usage"].get("status") != "quantifier" or not strict["usage"].get("fallback"):
        failures.append("the usage record does not say why the morning degraded: "
                        f"{strict['usage']}")
    print("  claim 9 warn publishes the flagged narrative and names the flag on the "
          "disclaimer; enforcing regenerates once and then hands the morning the "
          "plain table with that sentence in it. Exit 0 both ways")


def claim_the_watchdog_names_the_unjudged(failures: list[str]) -> None:
    """A backlog of unjudged flags is visible without opening the log.

    Dispositions are recorded by hand, and this project has already watched a
    diagnostic raise nightly and write nothing for a week while DECISIONS cited
    its evidence as accumulating. A flag log that fills while nobody judges is
    the same failure wearing a different hat: the rate never prints, and in a
    month the word list gets tuned on the intuition it was written with.

    So the watchdog counts them on every pass. A flag raised this morning has
    not been ignored and is named without being called a problem; one that has
    survived flag_backlog_after_days of mornings is a backlog and joins the
    problem count.
    """
    import datetime as dt
    import io
    from contextlib import redirect_stdout
    from core import criteria, ettime
    from ops import monitor_jobs, quantifier_flags

    now = ettime.now_et()
    real_query = monitor_jobs.query_task
    monitor_jobs.query_task = lambda task_name: {
        "exists": True, "status": "Ready", "last_run": None, "last_result": "0",
    }

    def watchdog_output() -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            monitor_jobs.check_all(now.replace(hour=0, minute=30), dry_run=True)
        return buffer.getvalue()

    try:
        pending_now = watchdog_output()
        # A flag old enough that nobody can call it fresh. Written straight to
        # the log because the thing under test is what a WEEK of silence looks
        # like, and no test can wait one.
        stale_days = criteria.load().integer("monitor", "flag_backlog_after_days") + 2
        path = analyst.flag_log_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "id": 90001,
                "recorded_at": ettime.stamp(now - dt.timedelta(days=stale_days)),
                "session": "2026-01-01", "report": "report.md", "line": 5,
                "quantifier": "every", "set_word": "candidate",
                "sentence": "Every candidate missed the prior day high.",
                "attempt": 1, "outcome": analyst.OUTCOME_FELL_BACK,
                "disposition": None, "disposition_note": None, "disposition_at": None,
            }, separators=(",", ":")) + "\n")
        backlog_now = watchdog_output()
    finally:
        monitor_jobs.query_task = real_query

    flag_lines = [line for line in pending_now.splitlines() if " flags " in line]
    if not flag_lines:
        failures.append("the watchdog says nothing about the quantifier flag log")
    elif "unjudged" not in flag_lines[0]:
        failures.append(f"the watchdog does not name the unjudged count: {flag_lines[0]}")

    backlog_lines = [line for line in backlog_now.splitlines() if " flags " in line]
    if not backlog_lines:
        failures.append("the watchdog lost its flag line once there was a backlog")
    elif "BACKLOG" not in backlog_lines[0]:
        failures.append("a flag older than the backlog window is not called a "
                        f"backlog: {backlog_lines[0]}")

    measured = monitor_jobs.flag_backlog(now)
    if measured.get("oldest_days") is None or measured["oldest_days"] < stale_days - 1:
        failures.append(f"the backlog age is not measured from the log: {measured}")
    if not measured.get("pending"):
        failures.append(f"the unjudged count is not counted: {measured}")
    else:
        print(f"  claim 10 the watchdog names {measured['pending']} unjudged flag(s) "
              f"and calls the {measured['oldest_days']:.0f} day old one a backlog")


def claim_the_instructions_cannot_ask_for_what_the_guard_forbids(
        failures: list[str]) -> None:
    """One word list, and all three sources of report prose checked against it.

    Three times in three commits the instructions asked for exactly what the
    guard refuses. The template asked for "the most common failed condition",
    a superlative it gave the model no way to compute, and got a false
    universal back. The deterministic fallback wrote the banned words in its
    own prose, so an analyst timeout on an empty screen produced a report that
    failed the guard and therefore no report at all. And rule 13 still said
    `no` was allowed one commit after `no` was banned.

    That is the same class the watchlist headers had, and it was closed there
    by a claim asserting all four sources agree rather than by being careful.
    This is the equivalent. REPORT_TEMPLATE.md, prompt_analyst.md and the
    fallback's emitted prose are the three places report wording is written,
    and all three are checked against the tuples in analyst.py rather than
    against a copy. The claim carries no word list of its own, on purpose: a
    fixture with its own copy is a fourth place to drift.

    A banned phrasing inside backticks is a specimen and passes, because a
    document that teaches "do not write this" has to be able to write it.
    """
    banned = analyst.banned_words()
    sets = analyst.set_words()
    if not banned or not sets:
        failures.append("the guard defines no word list to check against")
        return

    # 1. The prompt's enumeration IS the Python tuple, not a copy of it. This
    #    is what lets rule 13 name the words in the open without the scan
    #    having to make an exception for the line that defines the rule.
    prompt_text = config.ANALYST_PROMPT_PATH.read_text(encoding="utf-8")
    declared: dict[str, tuple[str, ...]] = {}
    for line in prompt_text.splitlines():
        stripped = line.strip()
        for label in ("Banned words:", "Set words:"):
            if stripped.startswith(label):
                declared[label] = tuple(
                    word.strip().lower()
                    for word in stripped[len(label):].split(",")
                    if word.strip()
                )
    if declared.get("Banned words:") != banned:
        failures.append(
            "prompt_analyst.md rule 13 lists banned words "
            f"{declared.get('Banned words:')} but the guard bans {banned}. The "
            "prompt is what the model reads and the tuple is what the guard "
            "enforces; they cannot differ.")
    if declared.get("Set words:") != sets:
        failures.append(
            f"prompt_analyst.md rule 13 lists set words {declared.get('Set words:')} "
            f"but the guard uses {sets}")

    # 2. Neither instruction file asks for what the guard forbids.
    for label, path in (("REPORT_TEMPLATE.md", config.REPORT_TEMPLATE_PATH),
                        ("prompt_analyst.md", config.ANALYST_PROMPT_PATH)):
        hits = analyst.instruction_violations(path.read_text(encoding="utf-8"))
        for hit in hits:
            failures.append(
                f"{label} line {hit['line']} asks for what the guard forbids: "
                f"{hit['quantifier']!r} near {hit['set_word']!r} in "
                f"{hit['text'][:160]!r}. Reword the instruction, or if it is "
                "quoting the phrasing as a specimen put it in backticks on a "
                "single line.")

    # 3. The third source of the same prose. The fallback is Python written,
    #    so nothing forces its wording to agree with the template's, and it
    #    already drifted once into wording that failed the guard it lives
    #    beside. Several packet shapes, because its prose is conditional and
    #    the empty morning is the one that broke.
    shapes = {
        "empty": {"session_date": "2026-01-02", "candidates": []},
        "one eligible": {
            "session_date": "2026-01-02",
            "candidates": [{"symbol": "ARX.US", "day_eligible": True,
                            "swing_eligible": True, "score": 7.0,
                            "conviction": "green", "catalyst_found": True,
                            "catalyst_class": "earnings",
                            "collector_covered": True, "quote": {}}],
        },
        "none eligible": {
            "session_date": "2026-01-02",
            "candidates": [{"symbol": "ARX.US", "day_eligible": False,
                            "swing_eligible": False, "score": 7.0,
                            "conviction": "green", "catalyst_found": True,
                            "catalyst_class": "earnings",
                            "collector_covered": True, "quote": {}}],
        },
        "degraded": {
            "session_date": "2026-01-02",
            "candidates": [{"symbol": "ARX.US", "day_eligible": False,
                            "swing_eligible": False, "score": None,
                            "conviction": None, "catalyst_found": None,
                            "pm_rvol": None, "pm_window_starts_late": True,
                            "collector_covered": False, "quote": {}}],
            "quota_preflight": {"degraded": True, "remaining": 900,
                                "daily_limit": 100000, "quota_day": "2026-01-02"},
            "economic": {"skipped": "the calendar call failed"},
            "earnings": {"skipped": "the calendar call failed"},
        },
    }
    # Every shape above is given a notable movers block as well, because the
    # fallback writes that section too and none of these packets carried one:
    # the block ran its empty branch, emitted one blank row and no reason lines,
    # and produced zero flags whatever the section's own words said. Five of
    # those words were "no name on the ... leg", which is a forward quantifier
    # one word from a set word, so this claim passed on an input that could not
    # have failed it while the real thing would have failed every morning both
    # sigma lists were short.
    section = {
        "rows": [
            {"symbol": "ARX.US", "leg": "prior_session",
             "as_of_session": "2026-01-01", "move_pct": 4.2, "move_sigma": None,
             "move_sigma_reason": "return_stdev_20d is null and this row covers "
                                  "250 sessions, which is enough for it, so the "
                                  "column was written before it was computed.",
             "market_cap": None,
             "market_cap_reason": "this symbol has no market cap on file, so it "
                                  "was never examined against the floor",
             "catalyst": None, "catalyst_state": "not checked",
             "also_on_watchlist": None, "price_time": None,
             "selected_by": ["prior_session_by_sigma"]},
        ],
        "lists": {"prior_session_by_sigma": ["ARX.US"],
                  "prior_session_by_market_cap": [],
                  "two_session_by_move": [], "premarket_by_sigma": []},
        "list_reports": _list_reports(),
        "list_reasons": {name: report["reason"]
                         for name, report in _list_reports().items()},
        "list_size": 5,
        "legs": {
            "premarket": {"available": False, "examined": 39, "selected": 0,
                          "reason": "0 subscribed symbols outside the context "
                                    "tickers carried both a collector price and "
                                    "a c1 close"},
            "prior_session": {"available": True, "examined": 2753,
                              "selected": 1, "reason": None},
            "two_session": {"available": False, "examined": 2753, "selected": 0,
                            "reason": "the third session was never bought"},
        },
        "universe_examined": 2754,
    }
    for packet in shapes.values():
        packet["notable_movers"] = section

    # The fixture is only worth walking if the fallback actually renders it.
    # It stopped rendering once already, on 2026-08-22, when the section moved
    # from list_reasons to list_reports and this hand written block still
    # carried only the first: the four list sentences vanished from the prose
    # and the walk below went on passing over the section's loudest strings.
    rendered = analyst.fallback_report(shapes["empty"], "the model timed out")
    for name, report in _list_reports().items():
        if report["text"] not in rendered:
            failures.append(
                f"the fallback does not render the {name} list's own sentence, "
                "so the walk below is not reading the strings this section "
                "hands the model. Fixture and renderer have decoupled.")

    for label, packet in shapes.items():
        prose = analyst.fallback_report(packet, "the model timed out")
        for hit in analyst.quantifier_violations(prose):
            failures.append(
                f"the fallback's own prose on a {label} packet trips the guard "
                f"it lives beside: {hit['quantifier']!r} near {hit['set_word']!r} "
                f"in {hit['text'][:120]!r}. An analyst timeout on that morning "
                "would produce a report the guard rejects, which is no report.")

    # 4. The one exemption, asserted rather than assumed. The withheld
    #    disclaimer QUOTES the sentence that caused the withholding, so it
    #    carries the banned pattern on purpose. That has to be true only of
    #    the disclaimer line, or the exemption is covering something else.
    quoted = "Every candidate missed the prior day high."
    withheld = analyst.fallback_report(
        shapes["one eligible"],
        analyst.quantifier_reason(analyst.quantifier_violations(quoted), [1]),
        analyst.CAUSE_WITHHELD,
    )
    lines = withheld.splitlines()
    disclaimer_line = next(
        (number for number, line in enumerate(lines, start=1)
         if "Nothing here is advice" in line), None)
    stray = [hit for hit in analyst.quantifier_violations(withheld)
             if hit["line"] != disclaimer_line]
    if stray:
        failures.append(f"the withheld fallback carries banned prose away from "
                        f"the disclaimer it quotes evidence on: {stray}")
    if not any(hit["line"] == disclaimer_line
               for hit in analyst.quantifier_violations(withheld)):
        failures.append("the withheld disclaimer no longer quotes the flagged "
                        "sentence, so a reader is told the narrative was held "
                        "back and not told what for")

    # 5. And the check itself is real: injecting a banned word into any of the
    #    three has to be caught. A green check that would stay green is worth
    #    nothing, and this is the cheapest way to know it would not.
    probes = {
        "an instruction file": lambda: analyst.instruction_violations(
            "Name every candidate whose score is null.\n"),
        "a backticked specimen uncovered": lambda: analyst.instruction_violations(
            "Do not write every candidate missed the high.\n"),
        "a wrapped instruction": lambda: analyst.instruction_violations(
            "The disclaimer must name every\ncandidate whose pm_rvol is null.\n"),
    }
    for label, probe in probes.items():
        if not probe():
            failures.append(f"the drift check does not catch a banned word in {label}")
    # And the specimen convention still works, or the files could not teach.
    if analyst.instruction_violations("Do not write `every candidate missed`.\n"):
        failures.append("a backticked specimen is refused, so the instruction "
                        "files cannot quote the phrasing they forbid")

    print(f"  claim 11 one word list of {len(banned)} banned and {len(sets)} set "
          "words, read by prompt_analyst.md, REPORT_TEMPLATE.md and the fallback "
          "prose across 4 packet shapes, with the withheld disclaimer the only "
          "exemption and a wrapped instruction still caught")


def claim_the_conviction_bands_are_defined_where_they_are_first_shown(
        failures: list[str]) -> None:
    """green, yellow and red meant nothing on the page until 2026-09-01.

    Conviction is published in three tables, the day watchlist, the swing
    watchlist and technical signals, and until this claim was written the
    report never said anywhere what the three words meant. A reader could see
    that a row was red and had no way to learn that red is a score under 4 on a
    scale to 10, or that unscored is a fourth state that is not a low one.

    Three properties, and the second and third matter more than the first.

    The arithmetic comes from criteria_summary.score_buckets, which is the
    packet's own frozen copy of the bands that scored THAT run. Reading CRITERIA
    at render time instead would let a threshold edited next week rewrite the
    meaning of a number published today.

    The legend appears under the FIRST table carrying the word, because a
    definition printed after its third use is not a definition. And it appears
    exactly once: two legends on one page can disagree.

    A packet with no bands gets NO legend rather than an invented one, which is
    the same rule every other null in this file follows.
    """
    packet = json.loads(build_packet_text())

    rendered = analyst.annotate_score_bands(
        analyst.fallback_report(packet, "the narrative pass was stubbed out"),
        packet)
    legend = analyst._bucket_legend(packet)

    if not legend:
        failures.append(
            "the fixture packet carries no criteria_summary.score_buckets, so "
            "this claim is asserting placement for a legend that was never "
            "built. Fixture and renderer have decoupled.")
        return

    if rendered.count(legend) != 1:
        failures.append(
            f"the conviction legend appears {rendered.count(legend)} times, "
            "where two definitions of the same three words can disagree with "
            "each other and one is no definition at all")

    # Every band the packet scored against has to reach the page. A legend
    # quoting two of three bands is worse than none: it reads complete.
    for band in (packet.get("criteria_summary") or {}).get("score_buckets") or []:
        if str(band) not in legend:
            failures.append(
                f"the packet scored against band {str(band)!r} and the legend "
                "does not carry it, so the page defines fewer buckets than it "
                "prints")

    lines = rendered.splitlines()
    headers = [n for n, line in enumerate(lines)
               if line.lstrip().startswith("|") and "Conviction" in line]
    placed = next((n for n, line in enumerate(lines) if legend in line), None)
    if not headers:
        failures.append("the fallback published no table carrying Conviction, "
                        "so this claim is not reading the report it thinks")
    elif placed is None:
        failures.append("the conviction legend reached no line of the report")
    else:
        if placed < headers[0]:
            failures.append(
                "the conviction legend is printed above the first table that "
                "uses the words, where a reader meets the definition before "
                "the thing it defines")
        if len(headers) > 1 and placed > headers[1]:
            failures.append(
                f"the conviction legend sits after the second table carrying "
                f"the word, at line {placed + 1} against a header at line "
                f"{headers[1] + 1}. A definition printed after its second use "
                "is not doing the job")

    # The prose ships through the same guard as the rest of the report.
    for hit in analyst.quantifier_violations(legend):
        failures.append(
            f"the conviction legend trips the guard it ships beside: "
            f"{hit['quantifier']!r} near {hit['set_word']!r}. A deterministic "
            "line that fails containment would withhold the report it is "
            "meant to explain")

    # And the null case: no bands in the packet, no legend on the page.
    bare = {"session_date": "2026-01-02", "candidates": []}
    if analyst._bucket_legend(bare) is not None:
        failures.append(
            "a packet carrying no score_buckets still produced a legend, so "
            "the report would state bands that nothing in the run was scored "
            "against")

    print(f"  bucket legend  {len(headers)} table(s) carry Conviction, the "
          f"legend is defined once under the first of them, and a packet with "
          f"no bands gets none")


def claim_the_fallback_closes_every_table_it_opens(failures: list[str]) -> None:
    """A markdown table runs until a blank line, and prose after a row joins it.

    On 2026-09-01 the notable movers glossary rendered inside the table it was
    written under: eighteen "TICKER is Company." sentences parsed as one more
    row, and with no pipes in them the whole paragraph collapsed into a single
    first column cell beside nine empty ones. The report published that way.

    It was latent for six sessions. The names have been carried since
    2026-08-24, but fallback_report only runs when the model's answer cannot be
    used, and 2026-09-01 was the first morning it was rejected. That is the
    property worth pinning: this renderer is the one that runs when something
    has already gone wrong, so it is the one least often seen and least able to
    afford being wrong.

    The rule is structural rather than about this paragraph. Any line that
    follows a table row must either be another row or be blank, anywhere in the
    document, so a section added later cannot reintroduce the same shape.
    """
    section = {
        "rows": [
            {"symbol": "AAA.US", "name": "Aaa Industries Inc", "leg": "premarket",
             "as_of_session": "2026-01-02", "move_pct": 4.0, "move_sigma": 2.0,
             "market_cap": 1_000_000_000, "catalyst": None,
             "catalyst_state": "not checked", "also_on_watchlist": None,
             "price_time": None, "price_age_seconds": None,
             "selected_by": ["premarket_by_sigma"]},
            {"symbol": "BBB.US", "name": "Bbb Holdings PLC", "leg": "premarket",
             "as_of_session": "2026-01-02", "move_pct": -3.0, "move_sigma": -1.5,
             "market_cap": 2_000_000_000, "catalyst": None,
             "catalyst_state": "not checked", "also_on_watchlist": None,
             "price_time": None, "price_age_seconds": None,
             "selected_by": ["premarket_by_sigma"]},
        ],
        "lists": {}, "list_reports": {}, "legs": {}, "universe_examined": 2754,
    }
    packet = {"session_date": "2026-01-02", "candidates": [],
              "notable_movers": section}

    rendered = analyst.fallback_report(packet, "the model timed out")
    lines = rendered.splitlines()

    # The fixture is only worth walking if the names actually reached the page.
    if "Aaa Industries Inc" not in rendered:
        failures.append(
            "the fallback did not render the instrument names at all, so this "
            "claim is walking a document that no longer contains the paragraph "
            "it exists to place. Fixture and renderer have decoupled.")
        return

    for index in range(1, len(lines)):
        previous, current = lines[index - 1].strip(), lines[index].strip()
        if not previous.startswith("|") or not current or current.startswith("|"):
            continue
        failures.append(
            f"line {index + 1} of the fallback follows a table row and is "
            f"neither blank nor a row: {current[:90]!r}. Markdown reads it as "
            "one more row, and with no pipes in it the whole line becomes a "
            "single first column cell. That is how the 2026-09-01 glossary "
            "was published in a column two inches wide")

    print(f"  closed tables  the fallback's {sum(1 for l in lines if l.startswith('|')):,} "
          "table rows are each followed by a row or a blank line")


def claim_a_form_designator_is_not_a_ticker_claim(failures: list[str]) -> None:
    """"10-Q" is a form, not a claim about the listing Q.

    The same defect _ABBREVIATION_RE was written for, one punctuation mark
    further out. Every piece of an abbreviation there has to start with a
    LETTER, so "10-Q", "S-1" and "H.4.1" matched nothing and _TOKEN_RE took the
    bare capital out of each. Q, S and H are all real listings.

    Measured 2026-08-28 against the real 2026-08-28 report and packet: "A 10-Q
    is due next week" invented Q, and "The Fed's H.4.1 release is out Thursday"
    invented H. "A Form S-1 was filed for the IPO" claimed S and escaped only
    because that packet happens to carry a bare S somewhere, which is the same
    luck that let 2026-08-18 escape the S&P case.

    The cost of being wrong is the whole morning rather than one unchecked
    claim: check_report exits 2 on an invented ticker and the chain's
    "if %RC% neq 0 exit /b %RC%" skips render, verify, deliver and archive.

    BOTH DIRECTIONS ARE ASSERTED. Blanking too much is a claim silently not
    checked, which is the failure this whole guard exists to prevent, so the
    second half holds that ordinary ticker prose still produces its claim,
    including a three letter ticker followed by a hyphen and a digit, which is
    the shape the letter cap was chosen to leave alone.
    """
    designators = [
        ("A 10-Q is due next week.", "Q"),
        ("A Form S-1 was filed for the IPO.", "S"),
        ("The Fed's H.4.1 release is out Thursday.", "H"),
        ("An 8-K was filed Monday morning.", "K"),
        ("A 13-F showed the stake.", "F"),
        ("The 10-K lands after the close.", "K"),
    ]
    for sentence, fragment in designators:
        tokens = analyst._prose_tokens(sentence)
        if fragment in tokens:
            failures.append(
                f"{sentence!r} produces the token {fragment!r}. That is a form "
                "designator, not a claim about a listing, and an invented "
                "ticker exits 2 and costs the whole morning.")

    keep = [
        ("MRVL trades at 223.70.", "MRVL"),
        ("SPY is up 0.12 percent.", "SPY"),
        ("NVDA.US leads the tape.", "NVDA"),
        ("CHA and BWLP opened their windows late.", "BWLP"),
        ("AU was dropped for a stale price.", "AU"),
        # Three letters and a hyphenated digit. The letter run in the
        # designator pattern is capped at two so this stays a claim; a cap of
        # three would swallow it and the claim would go unchecked.
        ("SPY-1 is not a real instrument.", "SPY"),
    ]
    for sentence, wanted in keep:
        tokens = analyst._prose_tokens(sentence)
        if wanted not in tokens:
            failures.append(
                f"{sentence!r} lost the claim {wanted!r}. Blanking too much is "
                "a ticker claim nobody checks, which is what this guard is for.")

    print(f"  designators  {len(designators)} form designators produce no "
          f"ticker claim and {len(keep)} ordinary sentences keep theirs")


def main() -> int:
    # Every check below reads the universe through analyst.check_report. It
    # reads THIS fixture, not whatever the live file holds today, and the
    # fixture is put back before any later module in the same interpreter
    # reads the path.
    with freeze_universe():
        return _checks()


def _checks() -> int:
    packet_text = build_packet_text()
    absent = pick_absent_universe_symbol(packet_text)
    failures: list[str] = []

    # Claim 1: acronyms in prose pass, and so do prose-in-a-grid cells like
    # headline times ("2:48 PM ET" must not read as Philip Morris) and column
    # headers ("PM high" likewise). Only ticker columns and $ prefixes claim.
    prose_report = (
        "# PremarketDesk test\n\n"
        "The CEO spoke before the FOMC while the SEC reviewed an IPO. GDP and "
        "CPI both printed, EPS beat, the FDA approved, and an ETF rebalanced.\n\n"
        "## Day watchlist\n\n"
        "| Ticker | Gap % | PM high | Top headline |\n|---|---|---|---|\n"
        "| ARX | 43.02 | 19.51 | Workday jumps on report, 2:48 PM ET |\n\n"
        "Prose mention of $ARX is also fine.\n"
    )
    invented, _, _ = analyst.check_report(prose_report, packet_text)
    if invented:
        failures.append(f"acronym prose or grid prose tripped containment: {invented}")

    # Claim 2a: a universe ticker absent from the packet fails via a table cell.
    table_report = prose_report + (
        f"\n## Swing watchlist\n\n| Ticker | Gap % |\n|---|---|\n| {absent} | 9.99 |\n"
    )
    invented, _, _ = analyst.check_report(table_report, packet_text)
    if absent not in invented:
        failures.append(f"table cell naming {absent} was not caught: {invented}")

    # Claim 2b: the same ticker fails via a $ prefix in prose.
    dollar_report = prose_report + f"\nWatch ${absent} for sympathy.\n"
    invented, _, _ = analyst.check_report(dollar_report, packet_text)
    if absent not in invented:
        failures.append(f"$ prefixed {absent} was not caught: {invented}")

    # Claim 3: context tickers are ETFs, outside the universe file, and were
    # once fail open. A context symbol claimed in a table but absent from the
    # packet must now be caught via the universe-plus-context union. QQQ is on
    # the fixed context list and the test packet carries only SPY.
    context_report = prose_report + (
        "\n## Swing watchlist\n\n| Ticker | Gap % |\n|---|---|\n| QQQ | 1.23 |\n"
    )
    invented, _, _ = analyst.check_report(context_report, packet_text)
    if "QQQ" not in invented:
        failures.append(f"context ETF QQQ absent from the packet was not caught: {invented}")

    # Claim 3b: a fabricated single letter row must fail. The token pattern
    # required two characters until 2026-08-14, so all 21 single letter
    # listings were invisible and a made up F or T row returned invented=[]
    # while the run printed that containment passed. Those are the symbols a
    # model is most likely to invent, being the most familiar in the market.
    single_report = prose_report + (
        "\n## Swing watchlist\n\n| Ticker | Gap % |\n|---|---|\n| F | 4.10 |\n"
    )
    invented, _, _ = analyst.check_report(single_report, packet_text)
    if "F" not in invented:
        failures.append(f"a fabricated single letter row for F was not caught: {invented}")

    # And the other side of the widening: A is Agilent and also the English
    # article, so it is a prose stopword. Prose must not trip on it while a
    # Ticker column cell reading A still does.
    article_report = (
        "# PremarketDesk test\n\n"
        "A quiet tape this morning. A single name cleared the floors.\n\n"
        "## Day watchlist\n\n| Ticker | Gap % |\n|---|---|\n| ARX | 43.02 |\n"
    )
    invented, _, _ = analyst.check_report(article_report, packet_text)
    if invented:
        failures.append(f"the English article A tripped containment in prose: {invented}")

    a_row_report = prose_report + (
        "\n## Swing watchlist\n\n| Ticker | Gap % |\n|---|---|\n| A | 2.00 |\n"
    )
    invented, _, _ = analyst.check_report(a_row_report, packet_text)
    if "A" not in invented:
        failures.append("a Ticker column cell reading A was not checked, so the "
                        f"stopword is too broad: {invented}")

    # Claim 4: coverage is honest. A report whose only table is headed "Sym"
    # scans zero ticker columns, and with no $ claims either, claims_checked
    # is zero: the caller must then say validation did not run, and the
    # annotation helper must put that sentence on the disclaimer line.
    sym_report = (
        "# PremarketDesk test\n\n"
        "Nothing here is advice, the screen thresholds are unvalidated seed values.\n\n"
        f"## Day watchlist\n\n| Sym | Gap % |\n|---|---|\n| {absent} | 9.99 |\n"
    )
    invented, _, coverage = analyst.check_report(sym_report, packet_text)
    if invented:
        failures.append(f"a Sym headed column should scan nothing, got: {invented}")
    if coverage["columns_scanned"] != 0 or coverage["claims_checked"] != 0:
        failures.append(f"coverage should show nothing examined, got: {coverage}")
    annotated = analyst.annotate_unvalidated(sym_report, coverage)
    disclaimer_line = next(
        line for line in annotated.splitlines() if "Nothing here is advice" in line
    )
    if "NOT validated" not in disclaimer_line:
        failures.append("the unvalidated note did not land on the disclaimer line")

    # Claim 5: the vacuum. The real 2026-08-14 report omitted both watchlist
    # tables because both screens were empty, so no ticker column existed, and
    # the check reported a clean pass over a report naming twelve tickers in
    # bold prose. That must now be a failure, with those tickers listed.
    real_report = config.RUNS_DIR / "2026-08-14" / "report.md"
    real_packet = config.RUNS_DIR / "2026-08-14" / "packet.json"
    if real_report.is_file() and real_packet.is_file():
        report_text = real_report.read_text(encoding="utf-8")
        real_packet_text = real_packet.read_text(encoding="utf-8")
        _invented, _missing, coverage = analyst.check_report(report_text, real_packet_text)
        if coverage["columns_scanned"] != 0:
            failures.append("the 2026-08-14 report was expected to carry no ticker "
                            f"column, got {coverage['columns_scanned']}")
        if not coverage["structure_failed"]:
            failures.append("the 2026-08-14 report still passes containment")
        named = set(coverage["prose_claims"])
        candidates = {
            str(c["symbol"]).split(".")[0]
            for c in json.loads(real_packet_text).get("candidates", [])
        }
        if not candidates <= named:
            failures.append(f"prose claims missed {sorted(candidates - named)}")
        annotated = analyst.annotate_unvalidated(report_text, coverage)
        disclaimer_line = next(
            line for line in annotated.splitlines() if "Nothing here is advice" in line
        )
        # The wording moved with the guard: it now NAMES the missing tables,
        # because "no ticker column was scanned" stopped being the test the
        # moment a third table could carry a Ticker header.
        if "omitted 2 required table(s)" not in disclaimer_line:
            failures.append("the disclaimer does not name the omitted tables: "
                            f"{disclaimer_line}")
        for wanted in ("day watchlist", "swing watchlist"):
            if wanted not in disclaimer_line:
                failures.append(f"the disclaimer does not name the {wanted}")
        print(f"  claim 5 the 2026-08-14 report fails on structure: "
              f"{len(named)} prose ticker claims across {coverage['columns_scanned']} "
              f"ticker columns, all {len(candidates)} candidates among them")
    else:
        print("  claim 5 SKIPPED, the 2026-08-14 artifacts are not on this machine")

    # Claim 6: an empty table that is still written keeps the guard switched
    # on. The header is present, one 'none' row sits under it, and nothing in
    # the prose names a ticker.
    # Both tables, built from REPORT_TEMPLATE.md rather than from header
    # literals. REPORT_TEMPLATE.md requires both even when empty, and the
    # guard matches them by name, so a fixture carrying its own header
    # string is a fixture that can silently stop testing production.
    empty_table_report = (
        "# PremarketDesk test\n\n"
        "Nothing here is advice, the screen thresholds are unvalidated seed values.\n\n"
        + conftest.watchlist_table("day watchlist")
        + "\nThe day screen produced nothing today, and the most common "
          "failed condition was the premarket price sitting below the "
          "prior day high.\n\n"
        + conftest.watchlist_table("swing watchlist")
        + "\nThe swing screen produced nothing today either.\n"
    )
    invented, _, coverage = analyst.check_report(empty_table_report, packet_text)
    if coverage["columns_scanned"] < 1:
        failures.append(f"the empty but present table scanned no columns: {coverage}")
    if coverage["structure_failed"]:
        failures.append(f"an empty but present table was called a structure "
                        f"failure: {coverage}")
    if invented:
        failures.append(f"the empty table report invented tickers: {invented}")
    print(f"  claim 6 an empty but present table scans "
          f"{coverage['columns_scanned']} ticker column(s) and passes")

    claim_briefing_table_cannot_stand_in(failures)

    claim_headers_cannot_diverge(failures)

    claim_quantifiers_over_the_set_are_rejected(failures)

    claim_flags_are_logged_for_measurement(failures)

    claim_a_flag_cannot_cost_the_report(failures)

    claim_the_watchdog_names_the_unjudged(failures)

    claim_the_instructions_cannot_ask_for_what_the_guard_forbids(failures)

    claim_the_conviction_bands_are_defined_where_they_are_first_shown(failures)
    claim_the_fallback_closes_every_table_it_opens(failures)
    claim_a_form_designator_is_not_a_ticker_claim(failures)

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print(f"PASS  acronyms in prose pass, {absent} absent from the packet fails "
          "both as a table cell and as a $ mention, an omitted table is a "
          "structure failure, an empty but present one is not, and a "
          "quantifier asserted over the candidate set is rejected")
    return 0


if __name__ == "__main__":
    # Sandboxed even when run by hand. See standalone() in conftest.py:
    # run_tests wraps the suite, and until 2026-08-20 a direct module
    # run wrote to the real data/ and runs/.
    from tests import conftest as _conftest

    sys.exit(_conftest.standalone(main))
