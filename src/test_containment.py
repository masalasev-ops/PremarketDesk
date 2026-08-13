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

import analyst
import config

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


def main() -> int:
    packet_text = build_packet_text()
    absent = pick_absent_universe_symbol(packet_text)
    failures: list[str] = []

    # Claim 1: acronyms in prose pass.
    prose_report = (
        "# PremarketDesk test\n\n"
        "The CEO spoke before the FOMC while the SEC reviewed an IPO. GDP and "
        "CPI both printed, EPS beat, the FDA approved, and an ETF rebalanced.\n\n"
        "## Day watchlist\n\n"
        "| Ticker | Gap % |\n|---|---|\n| ARX | 43.02 |\n\n"
        "Prose mention of $ARX is also fine.\n"
    )
    invented, _ = analyst.check_report(prose_report, packet_text)
    if invented:
        failures.append(f"acronym prose tripped containment: {invented}")

    # Claim 2a: a universe ticker absent from the packet fails via a table cell.
    table_report = prose_report + (
        f"\n## Swing watchlist\n\n| Ticker | Gap % |\n|---|---|\n| {absent} | 9.99 |\n"
    )
    invented, _ = analyst.check_report(table_report, packet_text)
    if absent not in invented:
        failures.append(f"table cell naming {absent} was not caught: {invented}")

    # Claim 2b: the same ticker fails via a $ prefix in prose.
    dollar_report = prose_report + f"\nWatch ${absent} for sympathy.\n"
    invented, _ = analyst.check_report(dollar_report, packet_text)
    if absent not in invented:
        failures.append(f"$ prefixed {absent} was not caught: {invented}")

    if failures:
        for failure in failures:
            print(f"FAIL  {failure}")
        return 1
    print(f"PASS  acronyms in prose pass, {absent} absent from the packet fails "
          "both as a table cell and as a $ mention")
    return 0


if __name__ == "__main__":
    sys.exit(main())
