"""Render the midday packet to markdown and HTML. No model, no vendor call.

CRITERIA [Midday] says why there is no narrative pass here: the morning runs
the analyst because "what should I make of this" is an open question, and
midday asks closed ones. A pick triggered or it did not. A name moved or it did
not. Both are arithmetic already in the packet, so this reads it and lays it
out, and there is no prose for a containment check or a quantifier guard to
police because nothing writes any.

Every headline in the movers section is third party text from a feed nobody
here controls. render_report.py carries the full argument for why that is never
trusted as markup; this reaches the same place by a shorter road, because it
builds the markdown itself and escapes on the way out rather than passing a
model's prose through a markdown library.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from core import artifacts
from core import config
from core import criteria
from core import glossary
from core import page
from ops import job_status
from morning import render_report

from midday import scan_midday

HEADLINES_SHOWN = int(criteria.load().number("midday", "headlines_per_mover"))

REPORT_MD = "report_midday.md"
REPORT_HTML = "report_midday.html"

# The page's own rules, over the shared report rules in core/page.py. The
# carry through table is eight columns and the notes under it are dense, so
# the midday page is wider than the morning's and its base type a touch larger.
_MIDDAY_CSS = """
.report.midday { max-width: 940px; font-size: 17px; }
.report.midday td:first-child { font-weight: 600; white-space: nowrap; }
.report.midday tbody tr:nth-child(even) td { background: var(--surface); }
.report.midday .note { color: var(--muted); font-size: 0.95em; }
"""

# How each carry through state is said in the report. The packet's spelling is
# for machines; this is the one a reader sees, and it is here rather than
# inline so the two halves of the report cannot drift apart.
STATE_WORDS = {
    scan_midday.GAPPED_THROUGH: "gapped through at the open",
    scan_midday.TRIGGERED: "triggered after the open",
    scan_midday.NEVER_TRIGGERED: "never triggered",
    scan_midday.UNKNOWN: "unknown",
}
STOP_WORDS = {
    scan_midday.STOP_HELD: "held",
    scan_midday.STOP_OUT: "stopped out",
    scan_midday.STOP_SEQUENCE_UNKNOWN: "stop level reached, sequence unknown",
    scan_midday.STOP_NOT_APPLICABLE: "not applicable",
}


# What each unjudged bucket is called in prose. A bucket name is a packet key
# and reads as one; these are the reader's words for it. Spelled out rather
# than derived by stripping "no_" off the key, which produced "carried no
# refused" the moment a bucket that is not a missing field joined the set.
UNJUDGED_WORDS = {
    "refused": "carried a quote this pass refused as stale, undated or "
               "without a prior close",
    "no_last_price": "carried no last price",
    "no_previous_close": "carried no previous close",
    "no_average_volume": "carried no average volume",
    "no_volume": "carried no volume",
    "zero_average_volume": "carry an average volume the vendor reports as "
                           "zero, so there is nothing to divide by",
    "zero_previous_close": "carry a previous close the vendor reports as "
                           "zero, so there is no denominator for a move",
}
UNJUDGED_LABELS = {
    "refused": "refused quote",
    "no_last_price": "last price",
    "no_previous_close": "previous close",
    "no_average_volume": "average volume",
    "no_volume": "volume",
    "zero_average_volume": "zero average volume",
    "zero_previous_close": "zero previous close",
}


def _pct(value: Any, places: int = 2) -> str:
    return f"{value:+.{places}f}%" if isinstance(value, (int, float)) else "n/a"


def _num(value: Any, places: int = 2) -> str:
    return f"{value:,.{places}f}" if isinstance(value, (int, float)) else "n/a"


def _cell(text: Any) -> str:
    """A markdown table cell that cannot break the table or the page.

    A pipe closes the column early and a newline ends the row, and headline
    text from the feed can carry either. Both are neutralised here rather than
    hoped about.
    """
    out = str(text if text is not None else "")
    return out.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


# Words the packet writes in capitals for EMPHASIS, which the report un-shouts.
# THE LINE IS BETWEEN PROSE AND AN ALARM. A close call and an unjudged bucket
# appear in a perfectly healthy report, so capitals there are shouting at a
# reader for whom nothing is wrong. THE COUNTS ABOVE DO NOT ADD UP and PARTIAL
# fire only when the report cannot be trusted as it stands, and both keep their
# capitals for that reason: they are the two lines a reader must not skim past.
# This project argues in capitals and that is right in a comment; a reader's
# report should not shout at them. It is a CLOSED LIST rather than a rule about
# capitals: a maximal run of capitals is looked up in the list, so NOTE stays
# NOTE. Built by scanning every note field the report actually renders:
# CRITERIA, EODHD, DECISIONS and SKIP are all-caps in the very same sentences
# and are NAMES, so a rule would have wrecked them. Fixed at the source in
# scan_midday too, but the packets already on disk carry the old wording and a
# re-render of an archived session has to read right as well.
_EMPHASIS_CAPS = ("NOT", "PRICE", "HERE", "READ")
_EMPHASIS_RE = re.compile("[A-Z]{2,}")


def _prose(text: Any) -> str:
    """Packet prose for a reader: safe in a table, and not shouting."""
    return _EMPHASIS_RE.sub(
        lambda m: m.group(0).lower() if m.group(0) in _EMPHASIS_CAPS
        else m.group(0),
        _cell(text))


def _sentence(text: Any) -> str:
    """A note used to OPEN a sentence, capitalised only where that is safe.

    The packet's notes are written to sit anywhere a reader needs them, so many
    begin with a small letter, and several were being dropped straight into
    sentence position: "selection is on price across every universe name"
    opened its own paragraph that way, and so did "every move divides by".

    Only a first word that is a PLAIN lowercase word is touched. An identifier
    keeps the spelling the vendor and the code give it, because "EthPrice" and
    "Us-quote-delayed" would be wrong in a louder way than a small letter is:
    one is a typographic slip, the other misnames the field a reader has to go
    and look up.
    """
    out = _prose(text)
    if not out:
        return out
    first = out.split(" ", 1)[0]
    if first.isalpha() and first.islower():
        return out[0].upper() + out[1:]
    return out


def carry_section(packet: dict[str, Any]) -> list[str]:
    carry = packet["carry_through"]
    rows = carry["rows"]
    out = ["## What the morning's picks did", ""]
    if not rows:
        out += [carry.get("picks_reason") or
                "The picks table carries no live rows for this session.", ""]
        return out

    # Two columns about the stop, two different headers. The eighth column was
    # also headed Stop until 2026-09-02, and the glossary, keyed on header text,
    # could hold one definition for the word, so the morning's Stop column was
    # explained as this one. See core/glossary.py.
    out += ["| Ticker | Score | Morning entry | Stop | What happened | Now vs fill "
            "| Best vs fill | Stop state |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        out.append(
            f"| {_cell(glossary.bare_ticker(row['ticker']))} "
            f"| {_num(row.get('score'), 1)} {_cell(row.get('conviction') or '')} "
            f"| {_num(row.get('entry_ref'))} "
            f"| {_num(row.get('stop_ref'))} "
            f"| {STATE_WORDS.get(row['state'], row['state'])} "
            f"| {_pct(row.get('now_vs_fill_pct'))} "
            f"| {_pct(row.get('best_vs_fill_pct'))} "
            f"| {STOP_WORDS.get(row['stop_state'], row['stop_state'])} |")
    out.append("")

    out += ["Row by row, with the reason each verdict was reached.", ""]
    for row in rows:
        out.append(f"**{_cell(glossary.bare_ticker(row['ticker']))}**: "
                   f"{_prose(row.get('state_reason'))}.")
        if row.get("stop_state_reason"):
            out.append(f"Stop: {_prose(row['stop_state_reason'])}.")
        if row.get("decided_inside_the_open_tolerance"):
            out.append(f"Close call: {_prose(row.get('open_tolerance_reason'))}.")
        if row.get("worst_vs_fill_reason"):
            out.append(f"Worst against fill is not reported: "
                       f"{_prose(row['worst_vs_fill_reason'])}.")
        out.append("")

    # The three standing disclosures. None of them is conditional, because a
    # report that states a limit only when it bites reads like a report with
    # no limits on the mornings it stays quiet.
    out += ["### What these grades are and are not", "",
            f"Levels are {_prose(rows[0].get('levels_are'))}", "",
            _sentence(carry["not_checked"]) + ".", "",
            _sentence(carry["sequence_unknown_note"]) + ".", ""]
    flagged = carry.get("decided_inside_the_open_tolerance_rows") or 0
    out += [f"{flagged} of {len(rows)} rows were decided by a margin inside the "
            "open tolerance, where the verdict could flip against the official "
            "opening auction price rather than the first consolidated print.", ""]
    return out


def movers_section(packet: dict[str, Any]) -> list[str]:
    movers = packet["movers"]
    rows = movers["rows"]
    tally = movers["tally"]
    out = ["## What else moved, that the morning never named", ""]
    if not rows:
        out += [f"Nothing cleared all three floors: {movers['floors']['min_move_pct']} "
                f"move, {movers['floors']['min_day_rvol']} relative volume and "
                f"{movers['floors']['min_price']} price. "
                f"{tally['quoted']:,} names were quoted.", ""]
    else:
        out += ["| Ticker | Move | Day RVOL | Last | Market cap | Did the morning "
                "reach it |",
                "| --- | --- | --- | --- | --- | --- |"]
        for row in rows:
            # `is None`, not falsiness: n/a is this column's word for a
            # field the vendor did not carry, and a reported zero is a
            # field it did carry.
            cap = row.get("market_cap")
            out.append(
                f"| {_cell(glossary.bare_ticker(row['symbol']))} "
                f"| {_pct(row.get('move_pct'))} "
                f"| {_num(row.get('day_rvol'))}x "
                f"| {_num(row.get('last'))} "
                f"| {(str(round(cap / 1e9, 2)) + 'B') if cap is not None else 'n/a'} "
                f"| {_cell(row['morning_reach'].replace('_', ' '))} |")
        out.append("")
        out += ["### Why each of them moved", ""]
        for row in rows:
            out.append(f"**{_cell(glossary.bare_ticker(row['symbol']))}**, "
                       f"{_pct(row.get('move_pct'))}. "
                       f"{_sentence(row['morning_reach_note'])}.")
            for item in (row.get("news") or [])[:HEADLINES_SHOWN]:
                out.append(f"- {_cell(item['title'])}")
            if row.get("news_reason"):
                out.append(f"- {_sentence(row['news_reason'])}.")
            out.append("")

    # EVERY BUCKET, so the line adds up to the quoted count. It used to name
    # five of the ten and the refused one was not among them, which was
    # invisible only because it read zero on the session this shipped against.
    # A reader cannot tell a name that failed a floor from one nothing measured
    # unless the counts reconcile, so the arithmetic is stated rather than left
    # to be attempted.
    counted = sum(tally.get(k, 0) for k in
                  ("refused", "named_this_morning", "no_last_price",
                   "no_previous_close", "no_average_volume", "no_volume",
                   "zero_average_volume", "zero_previous_close",
                   "below_price", "below_move", "below_rvol", "admitted"))
    out += ["### How this list was chosen", "",
            _sentence(movers["selection_note"]) + ".", "",
            f"Of {tally['quoted']:,} universe names quoted: "
            f"{tally.get('refused', 0):,} carried a quote this pass refused, "
            f"{tally['named_this_morning']:,} were already named this morning, "
            f"{tally['below_move']:,} moved less than the floor, "
            f"{tally['below_rvol']:,} cleared the move and not the volume, "
            f"{tally['below_price']:,} were under the price floor, "
            f"and {tally['admitted']:,} cleared everything. The rest were not "
            "judged and are named below.", ""]
    if counted != tally["quoted"]:
        out += [f"THE COUNTS ABOVE DO NOT ADD UP: they cover {counted:,} of "
                f"{tally['quoted']:,} quoted names, so "
                f"{tally['quoted'] - counted:,} went somewhere this report "
                "cannot name. Read the tally in the packet rather than this "
                "line.", ""]

    # zero_average_volume belongs here too. Leaving it out made it the one
    # unjudged bucket printed as a bare count with no symbols, in the section
    # built to make a count chaseable, and it let the all clear sentence below
    # fire while it was non zero: "nothing in this population went unmeasured"
    # two lines under a count of names that were dropped before the floors.
    unpriced = {k: tally[k] for k in
                ("refused", "no_last_price", "no_previous_close",
                 "no_average_volume", "no_volume", "zero_average_volume",
                 "zero_previous_close")
                if tally.get(k)}
    if unpriced:
        parts = ", ".join(f"{count:,} {UNJUDGED_WORDS[name]}"
                          for name, count in unpriced.items())
        # .get on examples, because a packet written before the refused bucket
        # gained a sample list carries every other key and not that one, and a
        # re-render of an archived session must not raise on it.
        # Bare tickers here too. These are sample SYMBOLS off the packet and
        # the vendor keys them with the exchange, so without this the one
        # sentence in the report that names names would print AAOI.US beside a
        # table printing AAOI. See glossary.bare_ticker.
        examples = "; ".join(
            f"{UNJUDGED_LABELS[name]}: "
            + (", ".join(glossary.bare_ticker(s)
                         for s in (tally['examples'].get(name) or []))
               or "none recorded")
            for name in unpriced)
        out += [f"Not judged, because the pass could not price them: {parts}. "
                f"These names did not fail a floor, they were never measured. "
                f"Examples, {examples}.", ""]
    else:
        out += ["Every quoted name was priced and carried the fields it needed, "
                "so nothing in this population went unmeasured.", ""]
    return out


def to_markdown(packet: dict[str, Any]) -> str:
    source = packet["price_source"]
    lines = [
        f"# Midday, {packet['session_date']}",
        "",
        f"Run at {packet['run_time_et']} ET. Prices from "
        f"{source['endpoint']}, and every move measured against the "
        f"{packet['prior_session']} close from {source['denominator_endpoint']}. "
        f"{packet['quotes_returned']:,} of {packet['universe_size']:,} universe "
        f"names quoted.",
        "",
    ]
    if packet.get("quote_error"):
        lines += [f"PARTIAL: {_cell(packet['quote_error'])}", ""]
    lines += carry_section(packet)
    lines += movers_section(packet)
    lines += [
        "## Where these numbers come from", "",
        _sentence(source["why_not_intraday"]) + ".", "",
        _sentence(source["denominator_note"]) + ".", "",
        _sentence(source["open_is_not_the_auction"]) + ".", "",
        _sentence(source["extended_hours_reason"]) + ", so they are not read.", "",
        f"Generated {packet['generated_at']}. "
        f"{packet.get('api_calls', 0)} vendor calls.", "",
    ]
    # PLAIN ENGLISH LAST, over the finished markdown, so the legends land under
    # the tables as they finally stand. The same two calls the morning report
    # makes, against the same definitions, so a column printed by both pages is
    # explained the same way on each.
    text = "\n".join(lines) + "\n"
    text = glossary.annotate_tables(text)
    return glossary.append_section(text)


def to_html(markdown_text: str, title: str) -> str:
    """Markdown to a complete page, through the ONE renderer.

    Until 2026-09-02 this module carried its own markdown parser, closed over
    the grammar it wrote, and it broke two promises its own writer made: _cell
    escaped a pipe as \\| and the parser split on the bare pipe anyway, and a
    headline carrying ** opened bold for the rest of the line. render_report
    handles both, neutralises tag shaped text, strips embeds, wraps and dresses
    tables, and is what the archive already used for the midday report, so the
    midday page now looks the same standing alone as it does in the archive.
    """
    body = render_report.to_html(markdown_text)
    return page.shell(html.escape(title, quote=False),
                      '<article class="report midday">\n' + body + "\n</article>",
                      extra_css=_MIDDAY_CSS)


def render(packet_path: Path, overwrite: bool = False) -> tuple[Path, Path]:
    packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    markdown_text = to_markdown(packet)
    title = f"PremarketDesk midday, {packet['session_date']}"
    run = config.run_dir(packet["session_date"])
    resolved = overwrite or artifacts.scheduled_run()

    md_path, _ = artifacts.resolve(run / REPORT_MD, resolved, what="midday render")
    md_path.write_text(markdown_text, encoding="utf-8")
    html_path, _ = artifacts.resolve(run / REPORT_HTML, resolved, what="midday render")
    html_path.write_text(to_html(markdown_text, title), encoding="utf-8")
    return md_path, html_path


# Declared at module level, NOT as a literal in the __main__ line below,
# so the entrypoint harness that imports this module and calls main()
# directly reads the same value the scheduler does. See
# ops/job_status.py and test_entrypoints.claim_ok_codes_declared.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the midday packet. No model, no vendor call.")
    parser.add_argument("--date", default=None, help="Session. Defaults to today ET.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    from core import ettime
    day = args.date or ettime.today_str()
    packet_path = config.RUNS_DIR / day / scan_midday.PACKET_FILE
    if not packet_path.is_file():
        print(f"midday render: no packet at {packet_path}, so there is nothing "
              "to render. Run midday.scan_midday first.")
        job_status.failed(f"no midday packet for {day}")
        return 1

    md_path, html_path = render(packet_path, args.overwrite)
    print(f"midday render: wrote {md_path}")
    print(f"midday render: wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(job_status.run("midday_render", main, ok_codes=OK_CODES))
