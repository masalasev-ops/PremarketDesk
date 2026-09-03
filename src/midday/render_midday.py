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
#
# THE WORDS DESCRIBE A PRICE, NOT A TRADE. They read as an execution record
# until 2026-09-03, when the owner read the table and said outright that he
# had taken no trades and could not tell what it was describing. Nothing on
# this page was ever traded: the morning publishes an entry and a stop for
# every name it scores, and this section reads the session's own high, low and
# last against those two numbers. "Triggered", "fill" and "stopped out" are
# the vocabulary of a position somebody holds, and they were being used for a
# level a price happened to cross.
STATE_WORDS = {
    scan_midday.GAPPED_THROUGH: "already past at the open",
    scan_midday.TRIGGERED: "reached after the open",
    scan_midday.NEVER_TRIGGERED: "never reached",
    scan_midday.UNKNOWN: "unknown",
}
STOP_WORDS = {
    scan_midday.STOP_HELD: "not reached",
    scan_midday.STOP_OUT: "reached",
    scan_midday.STOP_SEQUENCE_UNKNOWN: "reached, order unknown",
    scan_midday.STOP_NOT_APPLICABLE: "no start price",
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


# The notes a packet written BEFORE 2026-09-03 carries with a field name in
# the middle of them. Fixed at the source in scan_midday; this is what a
# re-render of a packet already on disk gets, and each pair is dead the day
# the last such packet stops being re-rendered. A named list rather than a
# blanket underscore strip, for the reason DECISIONS 2026-09-03 thirteenth
# gives: the same sentences cite CRITERIA keys on purpose.
_LEGACY_PROSE: tuple[tuple[str, str], ...] = (
    ("entry_ref and stop_ref as the morning published them, not the "
     "entry_ref_true and stop_ref_true the night corrects them to",
     "the entry and stop as the morning published them, not the corrected "
     "entry and stop the night measures from the full consolidated tape"),
    ("read triggered rather than gapped_through against",
     "read as reached after the open rather than already past at the open, "
     "against"),
    ("CRITERIA [Paper]'s SKIP condition, fill_plausible, is computed",
     "The SKIP condition in CRITERIA [Paper], whether a position could have "
     "been started at that level at all, is computed"),
    ("The SKIP condition in CRITERIA [Paper], whether the fill was plausible "
     "at all, is computed",
     "The SKIP condition in CRITERIA [Paper], whether a position could have "
     "been started at that level at all, is computed"),
    ("graded rows reached their stop level after an intraday fill, where a "
     "daily high and low carry no order, so this pass cannot say whether the "
     "stop came before or after the entry",
     "graded rows reached their stop level on a session that had already "
     "reached their entry after the open, where a daily high and low carry no "
     "order, so this pass cannot say which of the two came first"),
    # The four reasons that described a trade nobody placed.
    ("no fill, so the session low is not read against the stop: a low with no "
     "trade under it stops nothing",
     "the entry was never reached, so the session low is not read against the "
     "stop: a low with nothing started under it stops nothing"),
    ("the fill happened after the open, and a daily low carries no timestamp, "
     "so whether the session low came before or after the fill is unknowable "
     "from a quote",
     "the start price was set after the open, and a daily low carries no "
     "timestamp, so whether the session low came before or after it is "
     "unknowable from a quote"),
    ("but the fill happened after the open and a daily low carries no "
     "timestamp, so whether that low came before or after the fill cannot be "
     "told from a quote",
     "but the start price was set after the open and a daily low carries no "
     "timestamp, so whether that low came before or after it cannot be told "
     "from a quote"),
    ("and the fill was the opening print, so the low is unambiguously after it",
     "and the start price was the opening print, so the low is unambiguously "
     "after it"),
)


def _prose(text: Any) -> str:
    """Packet prose for a reader: safe in a table, not shouting, no field names."""
    said = _cell(text)
    for was, now in _LEGACY_PROSE:
        said = said.replace(was, now)
    return _EMPHASIS_RE.sub(
        lambda m: m.group(0).lower() if m.group(0) in _EMPHASIS_CAPS
        else m.group(0),
        said)


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


CARRY_HEADER = ("| Ticker | Score | Conviction | Entry | Stop | Entry reached "
                "| Start price | Now vs start | Best vs start | Stop reached |")
_CARRY_RULE = "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"


def _carry_rows(rows: list[dict[str, Any]]) -> list[str]:
    """One table's worth of graded rows, under CARRY_HEADER."""
    out = [CARRY_HEADER, _CARRY_RULE]
    for row in rows:
        out.append(
            f"| {_cell(glossary.bare_ticker(row['ticker']))} "
            f"| {_num(row.get('score'), 1)} "
            f"| {_cell(row.get('conviction') or '')} "
            f"| {_num(row.get('entry_ref'))} "
            f"| {_num(row.get('stop_ref'))} "
            f"| {STATE_WORDS.get(row['state'], row['state'])} "
            f"| {_num(row.get('fill'))} "
            f"| {_pct(row.get('now_vs_fill_pct'))} "
            f"| {_pct(row.get('best_vs_fill_pct'))} "
            f"| {STOP_WORDS.get(row['stop_state'], row['stop_state'])} |")
    out.append("")
    return out


def _screens(row: dict[str, Any]) -> str:
    """Which morning watchlist a row was on, in the words the morning uses."""
    day, swing = bool(row.get("day_eligible")), bool(row.get("swing_eligible"))
    if day and swing:
        return "day and swing"
    if day:
        return "day"
    if swing:
        return "swing"
    return ""


def carry_section(packet: dict[str, Any]) -> list[str]:
    carry = packet["carry_through"]
    rows = carry["rows"]
    out = ["## What the session did against the morning's levels", ""]
    if not rows:
        out += [carry.get("picks_reason") or
                "The picks table carries no live rows for this session.", ""]
        return out

    # WHAT THIS SECTION IS, before the first number. The owner read the table
    # of 2026-09-03 and said he had taken no trades and could not tell what it
    # was describing against the morning report, which is the whole of what
    # was wrong with it: the columns were headed with the vocabulary of a
    # position, the section was titled as though its rows were picks, and 9 of
    # its 12 rows were names the morning's screens had REJECTED.
    out += ["The morning publishes an entry and a stop for every name it "
            "scores. This section reads the session's own high, low and last "
            "price against those two numbers. A start price below is where a "
            "position would have begun had somebody acted on the level, and "
            "it is not a price anybody paid.", ""]

    picked = [row for row in rows if _screens(row)]
    rejected = [row for row in rows if not _screens(row)]

    # THE WATCHLIST NAMES FIRST AND APART. The morning report's Day watchlist
    # and Swing watchlist tables carry 3 names on an ordinary morning and this
    # table carried 12, under a heading calling all of them picks, with no
    # column saying which was which. A reader comparing the two pages was
    # comparing a list of 3 against a list of 12.
    out += ["### The names the morning put on a watchlist", ""]
    if picked:
        named = ", ".join(f"{glossary.bare_ticker(row['ticker'])} on the "
                          f"{_screens(row)} screen"
                          + ("s" if _screens(row) == "day and swing" else "")
                          for row in picked)
        out += [f"{len(picked)} of {len(rows)} graded names reached a watchlist: "
                f"{named}.", ""]
        out += _carry_rows(picked)
    else:
        out += [f"0 of {len(rows)} graded names reached a watchlist this "
                "morning, so the screens turned down every name they scored. "
                "The table below is what those names went on to do.", ""]

    out += ["### The names the screens turned down", ""]
    if rejected:
        out += [f"These {len(rejected)} were scored and screened and did NOT "
                "reach a watchlist. They are graded here on the same levels "
                "so the record shows what the screens turned down, which is "
                "the only way a floor can ever be judged. A row here was not "
                "a pick.", ""]
        out += _carry_rows(rejected)
    else:
        out += ["The screens turned nothing down this morning.", ""]

    out += ["Row by row, with the reason each verdict was reached.", ""]
    for row in rows:
        out.append(f"**{_cell(glossary.bare_ticker(row['ticker']))}**: "
                   f"{_prose(row.get('state_reason'))}.")
        if row.get("stop_state_reason"):
            out.append(f"Stop: {_prose(row['stop_state_reason'])}.")
        if row.get("decided_inside_the_open_tolerance"):
            out.append(f"Close call: {_prose(row.get('open_tolerance_reason'))}.")
        if row.get("worst_vs_fill_reason"):
            out.append(f"Worst against the start price is not reported: "
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
    if movers.get("refused_reason"):
        # Not measured, and said so where the list would be. A run before the
        # open has no elapsed session to pro rate volume against, and until
        # 2026-09-02 the pass measured against one minute of 390 instead.
        out += [f"This list was not measured: {_cell(movers['refused_reason'])}. "
                f"{tally.get('quoted', 0):,} names were quoted and the picks "
                "above were graded as usual.", ""]
        return out
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
    # The largest movers each floor turned down, by name. A floor is a
    # decision this project made, and until 2026-09-03 the two floor buckets
    # were bare counts: 2,459 below the move floor and 230 below the volume
    # floor, with no way to ask which big mover either one cost. .get for a
    # packet written before the key existed.
    floors = tally.get("floor_examples") or {}
    said = []
    for bucket, label in (("below_move", "under the move floor"),
                          ("below_rvol", "over the move floor and under the volume floor")):
        rows_cut = floors.get(bucket) or []
        if not rows_cut:
            continue
        named = ", ".join(
            f"{glossary.bare_ticker(r['symbol'])} at {r['move_pct']:+.2f}%"
            + (f" on {r['day_rvol']:.1f} times its usual volume"
               if r.get("day_rvol") is not None else "")
            for r in rows_cut)
        said.append(f"{label}: {named}")
    if said:
        out += ["The largest movers each floor turned down, so a count above "
                "can be chased. " + "; ".join(said) + ".", ""]
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
    # packet["price_source"] is deliberately not read any more; see the note
    # on the header line and the one where the provenance section used to be.
    lines = [
        f"# Midday, {packet['session_date']}",
        "",
        # The two endpoint names came out of this line on 2026-09-02 with the
        # provenance section below, for the same reason: which vendor route a
        # price arrived by is a fact about the plumbing. What the reader needs
        # is what the move is measured against, and that stays. Both names are
        # still in midday_packet.json under price_source.
        f"Run at {packet['run_time_et']} ET. Every move is measured against the "
        f"{packet['prior_session']} close. "
        f"{packet['quotes_returned']:,} of {packet['universe_size']:,} universe "
        f"names quoted.",
        "",
        # THE DISCLAIMER THE MORNING HAS AND THIS PAGE DID NOT. The morning
        # report opens with one and the midday opened with a table of prices
        # that read as an execution record. Written to open with the same six
        # words, because render_report._ClassParagraphs keys the disclaimer
        # style on them and because a reader who has both pages open should
        # meet the same sentence on each.
        "Nothing here is advice, no trade was placed, and nothing on this page "
        "is a position: it reads the session's own prices against the levels "
        "the morning published. The thresholds behind those levels are "
        "unvalidated seed values.",
        "",
    ]
    if packet.get("quote_error"):
        lines += [f"PARTIAL: {_cell(packet['quote_error'])}", ""]
    lines += carry_section(packet)
    lines += movers_section(packet)
    # The four vendor provenance sentences that stood here until 2026-09-02
    # are NOT printed any more, at the owner's word: which endpoint publishes
    # what and when is a fact about this project's plumbing, not about the
    # session, and the reader of a midday report is looking at what the
    # morning's picks did. Nothing is lost. price_source still carries
    # why_not_intraday, denominator_note, open_is_not_the_auction and
    # extended_hours_reason in midday_packet.json, the measurements behind
    # them are in DECISIONS 2026-08-31, and the header line above still names
    # both endpoints and the session the denominator came from, which is the
    # part a reader needs to judge the numbers. Do not delete those packet
    # keys because this stopped reading them.
    lines += [
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
