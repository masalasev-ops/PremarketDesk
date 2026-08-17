"""Regression test for the containment checker.

Run it directly: `python src\\test_containment.py`, exit 0 on pass.

Two claims, both required:
  1. Ordinary finance acronyms in prose (ETF, CEO, FDA, SEC, EPS, IPO, GDP,
     CPI, FOMC) never trip containment, because prose tokens are not ticker
     claims. Only tokens in table cells or prefixed with $ are candidates,
     and only candidates that name a real universe symbol are claims.
  2. A report naming a real universe ticker that is absent from packet.json
     still fails, through a table cell and through a $ prefix alike.
"""

from __future__ import annotations

import json
import sys

from morning import analyst
from tests import conftest
from core import config

ROOT_RUNS = config.PROJECT_ROOT / "runs"

ACRONYMS = ["ETF", "CEO", "FDA", "SEC", "EPS", "IPO", "GDP", "CPI", "FOMC"]


def build_packet_text() -> str:
    packet = {
        "session_date": "2026-01-02",
        "candidates": [
            {"symbol": "ARX.US", "conviction": "green", "day_eligible": True},
        ],
        "market_snapshot": [{"label": "spy", "symbol": "SPY.US"}],
    }
    return json.dumps(packet)


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
    NOTABLE = (
        "\n## Notable movers\n\n"
        "| Ticker | Leg | As of | Move % | Sigma | Market cap | Catalyst |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| OMER | prior_session | 2026-08-13 | +7.10 | 3.2 | 1.2B | not checked |\n"
    )

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
    for kind, header in template.items():
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
        for kind, header in template.items():
            if header in body:
                failures.append(
                    f"{module.name} carries the {kind} header as a literal. Build "
                    "it with conftest.watchlist_table so a template change breaks "
                    "the fixture instead of silently decoupling it.")

    print(f"  claim headers   {len(template)} watchlist header(s) agree across "
          "REPORT_TEMPLATE.md, analyst._REQUIRED_TABLES and fallback_report, the "
          "fallback passes the structure gate, and no test module carries either "
          "as a literal")

def main() -> int:
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

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print(f"PASS  acronyms in prose pass, {absent} absent from the packet fails "
          "both as a table cell and as a $ mention, an omitted table is a "
          "structure failure, and an empty but present one is not")
    return 0


if __name__ == "__main__":
    sys.exit(main())
