"""Write site/PremarketDesk.html: one document, eight screens, every session
inlined. And local/PremarketDesk.html beside it, the same desk with the Health
screen as a ninth, for this machine only; see LOCAL_KEEP.

A FULL REBUILD FROM WHAT IS ON DISK, never an append, so running it twice is
the same as running it once and deleting the file costs nothing but the
next run. That is build_archive's property and it is the property that makes a
generated page safe to keep.

WHY THE DATA IS INLINED. build_archive found it first and its docstring is the
authority: Chrome blocks fetch on file://, so every byte the page needs is
inlined at build time. The desk inherits that. Each session's frozen payload
is gzipped and base64 encoded into the document and inflated in the page by
DecompressionStream, which is native in Chrome and Edge and is the reason no
library ships here.

That scales further than it looks. A compacted session gzips to about 15KB and
inlines as about 20KB of base64, so CRITERIA [Screens] inline_sessions at 400
is about 8MB and covers more than a year. It is a CEILING and not a window:
every session the project has ever run is in the file, and a route to any of
them resolves with no server and no second document.

    PYTHONPATH=src .venv/Scripts/python.exe -m desk.render
"""

from __future__ import annotations

import argparse
import base64
import gzip
import html
import json
import sys
from typing import Any

from core import config
from core import criteria
from core import ettime
from core import files
from core import glossary
from core import page
from core import reader
from core import store
from desk import assets
from desk import compact
from ops import job_status

_CRIT = criteria.load()

# The archive page's filename. build_archive owned site/PremarketDesk.html
# until 2026-09-04, when the owner retired it: the desk answers the same
# question better and two pages over one set of sessions is one page too many.
# The desk carries the written reports for exactly that reason, so nothing the
# old page did is lost with its name.
DESK_FILE = "PremarketDesk.html"

# TWO DESKS SINCE 2026-09-11. site/PremarketDesk.html is published by
# ops.publish and says nothing about the machine. config.LOCAL_DIR's copy,
# beside the Weekly page, is the same desk plus the Health screen, which the
# owner took off the public site and wanted kept for themselves the same day.
# These are the payload keys that screen reads and the published copy drops.
LOCAL_KEEP = ("health", "bars_source")

# The knobs the application reads. Passed in rather than restated in
# JavaScript, so CRITERIA stays the one place a display bound is written down
# and a change to it reaches the page without editing the page.
_KNOB_KEYS = (
    ("screens", "spine_scale_pct", "number", "spine_scale_pct"),
    ("screens", "path_min_bars", "integer", "path_min_bars"),
    ("screens", "ladder_label_gap_px", "integer", "ladder_label_gap_px"),
    ("screens", "sessions_page_size", "integer", "sessions_page_size"),
    ("screens", "name_decks", "integer", "name_decks"),
    ("screens", "precedent_strip_domain_pct", "number", "precedent_strip_domain_pct"),
    # The two times a midday screen counts down to before its pass has run.
    # Read from the sections that own them rather than restated under
    # [Screens], so the page counts down to the minute the scheduler actually
    # fires and moving either one reaches the screen without a second edit.
    ("ladder", "open_time", "text", "ladder_open"),
    ("ladder", "close_time", "text", "ladder_close"),
    ("ladder", "refresh_seconds", "integer", "ladder_refresh_s"),
    ("midday", "run_time", "text", "midday_run_time"),
    ("monitor", "midday_due", "text", "midday_due"),
)


def knobs() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for section, key, kind, name in _KNOB_KEYS:
        out[name] = (_CRIT.integer(section, key) if kind == "integer"
                     else _CRIT.text(section, key) if kind == "text"
                     else _CRIT.number(section, key))
    return out


def index_rows() -> list[dict[str, Any]]:
    """The summary row per session, newest first, from the sessions table.

    Read back from the database rather than recomputed here, because the
    Sessions and Record screens are meant to be answerable without opening a
    packet and this is the proof that they are.
    """
    with store.session() as connection:
        store.init(connection)
        cursor = connection.execute(
            "SELECT * FROM sessions ORDER BY date DESC")
        return [dict(row) for row in cursor.fetchall()]


# ------------------------------------------------ the published copy's source
#
# THE COMMENTS STAY ON THIS MACHINE. The desk's script and stylesheets are
# written with their reasons beside them, and those reasons are the machine
# describing itself: the packet, the collector, what was replayed and why.
# The owner asked for none of that where a reader can see it, and a page's
# source is one view-source away. So the published copy is written without
# them; the local copy and assets.py keep every word.
#
# A TOKENIZER AND NOT A PATTERN, because the script holds a regular expression
# that reads /^[><]=?\s*/, whose last two characters close a block comment
# for any stripper that does not know it is inside a regex. Strings and regex
# literals are copied whole; a slash starts a regex where an expression can
# start, which is after an operator, an opening bracket or a keyword.

_REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = {"return", "typeof", "case", "in", "of", "delete", "void",
                   "throw", "new", "else", "do"}


def strip_js_comments(source: str) -> str:
    """source with every // and /* */ comment removed and blank lines closed."""
    out: list[str] = []
    i, n = 0, len(source)
    last, word = "", ""
    while i < n:
        c = source[i]
        following = source[i + 1] if i + 1 < n else ""
        if c in "\"'":
            j = i + 1
            while j < n and source[j] != c:
                if source[j] == "\n":
                    raise ValueError(f"an unterminated string at offset {i}")
                j += 2 if source[j] == "\\" else 1
            out.append(source[i:j + 1])
            i, last, word = j + 1, c, ""
            continue
        if c == "/" and following == "/":
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if c == "/" and following == "*":
            end = source.find("*/", i + 2)
            if end < 0:
                raise ValueError(f"an unterminated comment at offset {i}")
            out.append("\n" if "\n" in source[i:end] else " ")
            i = end + 2
            continue
        if c == "/" and (not last or last in _REGEX_AFTER or word in _REGEX_KEYWORDS):
            j, in_class = i + 1, False
            while j < n:
                d = source[j]
                if d == "\\":
                    j += 2
                    continue
                if d == "\n":
                    raise ValueError(f"an unterminated regex at offset {i}")
                if d == "[":
                    in_class = True
                elif d == "]":
                    in_class = False
                elif d == "/" and not in_class:
                    break
                j += 1
            j += 1
            while j < n and source[j].isalpha():
                j += 1
            out.append(source[i:j])
            i, last, word = j, "/", ""
            continue
        out.append(c)
        if c.isalnum() or c in "_$":
            joined = i > 0 and (source[i - 1].isalnum() or source[i - 1] in "_$")
            word = word + c if joined and word else c
            last = c
        elif not c.isspace():
            last, word = c, ""
        i += 1
    lines = "".join(out).split("\n")
    return "\n".join(line.rstrip() for line in lines if line.strip()) + "\n"


def _published(document: str) -> str:
    """The page as uploaded: its script and styles without their comments.

    Only a script with no attributes is the application; the JSON blocks carry
    an id and are data, and are left exactly as they are. page.SHELL_MARK
    stays: it is the stamp the suite finds every page by, and says nothing.
    """
    import re

    document = re.sub(r"<script>(.*?)</script>",
                      lambda m: f"<script>{strip_js_comments(m.group(1))}</script>",
                      document, flags=re.S)

    def css(match: re.Match[str]) -> str:
        return match.group(0) if match.group(0) == page.SHELL_MARK else ""

    return re.sub(r"(<style[^>]*>)(.*?)(</style>)",
                  lambda m: m.group(1) + re.sub(r"/\*.*?\*/", css, m.group(2), flags=re.S)
                  + m.group(3), document, flags=re.S)


def _encode(payload: dict[str, Any]) -> tuple[str, int]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, 9)).decode("ascii"), len(raw)


def payloads(dates: list[str]) -> tuple[dict[str, str], dict[str, str], int, int]:
    """Frozen payload per session, gzipped and base64 encoded for inlining.

    A session with no frozen payload is compacted on the spot rather than
    skipped, so a desk built before the nightly has ever run still carries
    every session it can see. Returns the published map, the local map, and
    the published map's raw and encoded totals, which the caller reports
    because a page that silently grew past what a browser will open is the
    failure this counting exists to catch.

    TWO MAPS FROM ONE PASS, so each session's reports are rendered once. The
    local one keeps LOCAL_KEEP, what the Health screen reads; see render().
    """
    out: dict[str, str] = {}
    local: dict[str, str] = {}
    raw_total = encoded_total = 0
    for date in dates:
        payload = compact.load_frozen(date)
        if payload is None:
            payload = compact.compact_session(date)
        if payload is None:
            continue
        # THE PUBLISHED COPY, and this is the one place every session passes
        # through on its way into the page, frozen ones included. A payload
        # frozen before 2026-09-11 carries its report rendered in full and the
        # keys only the Health screen reads, so both are redone here rather
        # than trusted from the freeze. The frozen file keeps them.
        run_dir = config.run_path(date)
        payload = dict(payload, report=compact._rendered(run_dir, "report.md"),
                       report_midday=compact._rendered(run_dir, "report_midday.md"))
        encoded, raw = _encode(reader.desk_payload(payload))
        out[date] = encoded
        raw_total += raw
        encoded_total += len(encoded)
        local[date] = _encode(reader.desk_payload(payload, keep=LOCAL_KEEP))[0]
    return out, local, raw_total, encoded_total


def _nav(local: bool = False) -> str:
    # SHORT, because these sit in a menu bar. "Ladder" is a trading price
    # ladder and named nothing a reader could see; "Precedent" is a word
    # about the screen rather than about what it shows. Open and Similar
    # also put the first three in the order the morning happens: Morning
    # before the bell, Open for the first hour, Midday after.
    items = [("morning", "#/", "Morning"),
             # Sits beside Morning and not after Record, because it is about
             # the SAME session and is read at the same hour. It is a separate
             # screen and not a section of Morning on purpose: the score is
             # the desk's opinion and a base rate is a count of what lookalikes
             # did, and folding one into the other hides the case where they
             # disagree, which is the only case either gets corrected by.
             # Between Morning and Precedent because it is read in the
             # hour AFTER the one Morning publishes, on the same session, and
             # a reader at 09:35 should not have to pass Precedent to reach
             # the only screen that is moving.
             ("ladder", "#/", "Open"),
             ("precedent", "#/", "Similar"),
             ("midday", "#/", "Midday"),
             ("report", "#/", "Report"),
             ("sessions", "#/sessions", "Sessions"),
             ("record", "#/record", "Record")]
    # Morning, Midday and Report resolve against whichever session is
    # selected, so their href is rewritten by setNav rather than fixed here.
    #
    # HEALTH IS ON THE LOCAL DESK ONLY since 2026-09-11. It left the published
    # one on the owner's instruction once the desk was public: every line of
    # it was the machine describing itself, its packet, its vendor budget and
    # its listener, and none of it was about a share. The owner wanted it kept
    # for themselves, so the copy built into config.LOCAL_DIR still has it.
    if local:
        items.append(("health", "#/", "Health"))
    #
    # REPORT JOINED ON 2026-09-04, when the owner opened the desk and asked
    # where the morning report was. It had exactly one inbound link in the
    # whole application, a card on the Session screen, and Session is not in
    # this list either: the only route to a written report was Sessions, then
    # a day, then the card. The screen the desk OPENS on had no route to it
    # at all, which is the same as not having built it.
    return "<nav>" + "".join(
        f'<a data-nav="{key}" href="{href}">{html.escape(label)}</a>'
        for key, href, label in items) + "</nav>"


def alert_banner(today: str | None = None) -> str:
    """What failed today, drawn above every screen. Empty when nothing did.

    WHY NOT THE HEALTH SCREEN. That screen already answers this question and
    cannot answer it on the morning it counts. It reads p.health out of the
    session's PACKET, and a morning whose scan died wrote no packet at all, so
    the session does not exist, the router has nothing to route to, and the
    desk opens on the last good day looking entirely normal. That is exactly
    what happened on 2026-09-08: the chain died at 08:45:21, the desk showed
    Friday, and the owner found out at 09:10 by noticing the absence of
    something rather than the presence of anything.

    So this reads data/job-status.jsonl instead, which every step appends to in
    a finally block as it exits and which is therefore the one record that
    survives the failure it describes. It is rendered into the document at
    build time rather than drawn by the page's router, for the same reason:
    the router is a function of the sessions that exist.

    Two loudnesses, by what the failure COST rather than by what it was. A
    morning with no report on disk is the red one, because that is the state
    the owner would otherwise discover by going to look for a report. A
    failure on a morning whose report was still written is a warning: the
    screens are real, something on the way to them was not.

    THE RED ONE HAS THREE READINGS and printed one of them until 2026-09-09.
    "No report" says nothing about whether the screens under it are this
    morning, because the desk step runs on the failure path on purpose. A
    dead scan writes no packet and the screens are genuinely the last good
    day; a step that died after the scan leaves a packet, and the screens
    are this morning. A withheld draft is a third state again, and the only
    one where there is something to go and read. Each says where to look
    next, and they are not interchangeable.

    AND IT REPORTS STATE, NOT HISTORY. A step that failed and was rerun green
    is gone from here on the next render, because a banner that stays up after
    the thing it describes was fixed is up every day by lunchtime, and a
    banner that is always up is furniture. The morning report keeps the
    repaired failure, which is right for a record OF a morning and wrong for a
    light that answers "is something wrong now".
    """
    day = today or ettime.today_str()
    on = ettime.parse_date(day)
    rows = job_status.records()

    # STATE, NOT HISTORY, and that is the whole difference between this and
    # the morning report's line. failures_today deliberately keeps a step that
    # failed and was rerun, because the report is a record OF THE MORNING and
    # a reader who is told only about what is still broken cannot tell a clean
    # run from a repaired one. This banner answers a different question, asked
    # at a glance and continuously: is something wrong RIGHT NOW. A repaired
    # failure that stays on the page is a banner that is up every day by
    # lunchtime, and a banner that is always up is furniture.
    #
    # So the recovered ones are dropped here and nowhere else. group_failures
    # sets recovered when a later run of the same step succeeded, which is the
    # same fact the report prints as "and a later run succeeded".
    failures = [row for row in
                job_status.group_failures(job_status.failures_today(on, rows))
                if not row.get("recovered")]
    overdue = job_status.overdue(on, rows)
    run_dir = config.run_path(day)
    report_missing = not (run_dir / "report.html").is_file()
    # TWO FACTS, NOT ONE, and this banner conflated them until 2026-09-09.
    # Whether a report exists and whether the SCREENS BELOW are this session
    # are independent. The chain does NOT stop dead at a failure: the desk
    # step is deliberately run on the failure path, under its own marker, so
    # that a morning which lost its report still draws its screens. On
    # 2026-09-09 that worked exactly as designed and this banner then told
    # the reader they were looking at the previous session, of screens
    # stamped with that morning's own date and packet time. A reader who
    # believes it goes looking for figures already in front of them.
    #
    # The packet is the right thing to read for it, and for the same reason
    # the docstring gives for reading job-status: a session exists on the
    # desk if and only if its packet was written.
    screens_are_this_session = (run_dir / "packet.json").is_file()
    # A report written and then withheld is not the same state as no report
    # written, and the difference is entirely where the reader should look
    # next. The 2026-09-09 analyst produced 53,957 characters and refused to
    # deliver them, and the banner called that "no report was written".
    draft_on_disk = (run_dir / "report.md").is_file()
    if not failures and not overdue and not report_missing:
        return ""

    # IN THE READER'S WORDS since 2026-09-11, when the desk went public and the
    # owner asked for nothing on it about packets, steps or files. The step
    # names, exit codes and paths this used to list are the machine's working
    # and are in the job status record and the logs, where the owner reads
    # them; what a reader of the page needs is whether the screens below are
    # this morning and whether a report exists. The three readings above are
    # kept exactly, only said without the machine's names.
    if report_missing:
        # Unresolved by definition, whatever the step records say. A morning
        # with no report is the state itself and not a report of one, so this
        # stands even when every failed step was later rerun green.
        klass, headline = "deskalert", f"No morning report for {day}"
        if not screens_are_this_session:
            lead = ("This morning's update did not complete, so the screens "
                    "below are the last session that did, not this one. "
                    "Every figure on them is that earlier morning.")
        elif draft_on_disk:
            lead = ("This morning's report was written and then held back, so "
                    "there is no report for this session. The screens below "
                    "are this session.")
        else:
            lead = ("No report was written for this session. The screens "
                    "below are this session.")
    else:
        klass, headline = "deskalert warn", f"Part of {day}'s update did not finish"
        lead = ("The report was written, so the screens below are this "
                "session, but some of what they show may be missing or out of "
                "date until the update finishes.")

    return (f'<div class="{klass}" role="alert">'
            f"<h2>{html.escape(headline)}</h2>"
            f"<p>{html.escape(lead)}</p></div>")


def glossary_json() -> str:
    """Every term and column the glossary defines, keyed for lookup.

    ONE GLOSSARY, TWO SURFACES. These definitions were written for the
    emailed report and the desk never read them, so the screens carried the
    vocabulary and the plain English sat in a module beside them. A reader
    counted about one unexplained term every 24 words of visible desk text
    on 2026-09-09, which is what a second source would have cost anyway.

    COLUMNS entries are written to follow their own name ("Ticker is the
    short code..."), so the popover prints the name and then the text and
    both shapes read as one sentence.
    """
    entries = {name.lower(): text for name, text in glossary.COLUMNS.items()}
    # TERMS last: they are the fuller of the two where a word is in both.
    entries.update({name.lower(): text for name, text in glossary.TERMS})
    # Published with the page, so an entry that defines the machine itself,
    # "packet" and its kind, is left out: no screen shows those words any more
    # and the definition was the machine describing its own files.
    entries = {name: text for name, text in entries.items()
               if not reader.machine_words(f"{name} {text}")}
    return json.dumps(entries, separators=(",", ":"))


def body(index: dict[str, Any], blobs: dict[str, str], local: bool = False) -> str:
    index_json = json.dumps(index, separators=(",", ":"))
    blob_json = json.dumps(blobs, separators=(",", ":"))
    gloss_json = glossary_json()
    return f"""
<div class="bar">
  <div class="bar-in">
    <div class="mark"><b>Premarket<span>Desk</span></b></div>
    {_nav(local)}
    <div class="bar-actions noprint">
      <div class="picker-wrap" id="picker-wrap">
        <button class="btn" id="session-btn" type="button" aria-haspopup="dialog"
                aria-expanded="false" aria-label="Choose a session">
          <span class="mono" id="session-btn-label">n/a</span>
          <span aria-hidden="true" style="color:var(--muted);font-size:10px">&#9660;</span>
        </button>
        <div class="cal-pop noprint" id="session-pop" hidden></div>
      </div>
      <button class="btn" id="theme-btn" type="button">Theme</button>
      <button class="btn primary" id="print-btn" type="button">Save as PDF</button>
    </div>
  </div>
</div>
<div class="wrap">
  <div class="printhead printonly">
    <h1 class="pagetitle" id="print-title">PremarketDesk</h1>
    <p id="print-sub">Saved from the desk.</p>
  </div>
  {alert_banner()}
  <div class="eyebrow" id="stamp">
    <span><b class="mono" id="stamp-date">n/a</b> session</span>
    <span>&middot;</span>
    <span>prices as of <b class="mono" id="stamp-run">n/a</b> ET</span>
  </div>
  <div id="screen"></div>
  <p class="foot">
    These are prices from the hours before the market opens, when far fewer
    shares change hands than during the day. They are unofficial. Wherever a
    screen says how busy a share's trading has been before the open, that
    figure is an estimate. The conditions a name has to pass to reach a list
    are starting values that nobody has yet shown to work. Nothing here is
    advice.
  </p>
</div>
<script id="desk-glossary" type="application/json">{gloss_json}</script>
<script id="desk-index" type="application/json">{index_json}</script>
<script id="desk-payloads" type="application/json">{blob_json}</script>
"""


def render(limit: int | None = None, compact_first: bool = True) -> dict[str, Any]:
    limit = limit if limit is not None else _CRIT.integer("screens", "inline_sessions")
    rows = index_rows()
    if not rows and compact_first:
        # Nothing has been compacted, so compact everything first rather than
        # write an empty desk. A desk with no sessions is indistinguishable
        # from a desk whose build half worked. Not done when the caller has
        # just compacted, or asked not to: main() would otherwise compact
        # twice on an empty tree, and --no-compact would compact anyway.
        compact.main([])
        rows = index_rows()
    rows = rows[:limit]
    dates = [r["date"] for r in rows]
    blobs, local_blobs, raw_total, encoded_total = payloads(dates)
    # The index is published too, and a session's file size on this machine
    # is not a fact about any share. See core/reader.
    rows = [{key: value for key, value in r.items()
             if key not in ("packet_bytes", "packet_compressed")}
            for r in rows if r["date"] in blobs]

    index = {"built_at": ettime.stamp(), "knobs": knobs(), "sessions": rows}
    written = {}
    for local, folder, sessions, extra in (
            (False, config.SITE_DIR, blobs, ""),
            (True, config.LOCAL_DIR, local_blobs, assets.HEALTH_JS)):
        document = page.shell(
            title="PremarketDesk", body=body(index, sessions, local=local),
            extra_css=assets.DECK_CSS,
            script=f"<script>{assets.DECK_JS.replace(assets.EXTRA_MARKER, extra)}</script>",
            # REPORT_CSS comes along now that the desk carries the written
            # reports. Safe beside DECK_CSS by construction: every one of its
            # 46 selectors is scoped under .report and none of them is bare.
            include_report_css=True)
        if not local:
            document = _published(document)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / DESK_FILE
        files.write_text_atomically(destination, document, attempts=3, retry_s=0.4)
        written[local] = (destination, len(document))
    return {"path": written[False][0], "sessions": len(rows), "bytes": written[False][1],
            "local_path": written[True][0], "raw": raw_total, "encoded": encoded_total}


def compact_for_this_run(recompact_all: bool = False) -> None:
    """Today, plus any session the summary table has never seen.

    NOT EVERY SESSION, which is what this did until 2026-09-04. The morning
    chain, the midday chain and the nightly all end on a desk build, so
    every session on file was recompacted three times a day: its packet
    read, its two reports re-rendered from markdown, its payload gzipped
    and its summary row rewritten. Four sessions hid the cost. At the
    [Screens] inline_sessions ceiling of 400 it is four hundred packets and
    eight hundred markdown renders, twice before the open.

    Today is compacted because today is what changed: the scan wrote the
    packet, the analyst wrote the report, the midday pass wrote its rows. A
    session with no summary row is compacted too, because a payload the
    index cannot see is a session missing from every screen, and that is
    how a machine that was off for a day catches up. Everything else is
    already frozen and correct, and the nightly rebuilds all of it anyway,
    which is what carries a change to this file to older sessions.

    AND A PAYLOAD CAN GO STALE WITHOUT ITS SESSION CHANGING, which is why
    recompact_all exists. The Precedent block is computed from
    research_outcomes at compact time and frozen with the rest, so running the
    replay fills that table and changes nothing a reader can see through THIS
    function: every session already has a summary row, so nothing here is
    recompacted and the screens keep printing the empty state they were built
    with.

    THE NIGHTLY DOES FIX IT, and this paragraph said otherwise until it was
    checked. job_nightly.bat runs `desk.compact` with no --session, which is
    every known session, and only then `desk.render --no-compact`. So a stale
    payload survives until 22:15 and no longer. What this flag is for is the
    window in between, and any hand run of desk.render on its own, where
    waiting for the nightly is not the answer.
    """
    known = compact.known_sessions()
    if recompact_all:
        if not known:
            print("desk: no sessions to recompact")
            return
        print(f"desk: recompacting all {len(known)} session(s) by hand, "
              "because a frozen payload can go stale without its session "
              "changing")
        compact.build(known)
        return
    seen = {row["date"] for row in index_rows()}
    todo = [date for date in known if date not in seen]
    today = ettime.today_str()
    if today in known and today not in todo:
        todo.insert(0, today)
    if not todo:
        print("desk: every session already has a summary row and today has "
              "no packet, so nothing was recompacted. Pass --recompact-all if "
              "something the payloads READ has changed, such as the replay "
              "behind the Precedent screen")
        return
    compact.build(todo)


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the desk.")
    parser.add_argument("--limit", type=int,
                        help="Inline at most this many sessions. Default is "
                             "CRITERIA [Screens] inline_sessions.")
    parser.add_argument("--no-compact", action="store_true",
                        help="Do not recompact first. Use the frozen payloads "
                             "as they are. The nightly passes this because it "
                             "has already run desk.compact over every session.")
    parser.add_argument("--recompact-all", action="store_true",
                        help="Recompact every session, not just today and "
                             "the ones the index has never seen. For when "
                             "something the payloads READ has changed rather "
                             "than the sessions themselves, such as the "
                             "replay behind the Precedent screen.")
    args = parser.parse_args(argv)

    if not args.no_compact:
        compact_for_this_run(recompact_all=args.recompact_all)
    result = render(limit=args.limit, compact_first=False)
    print(f"desk: {result['sessions']} session(s) inlined, "
          f"{result['raw'] / 1048576:.2f} MB of payload became "
          f"{result['encoded'] / 1048576:.2f} MB encoded")
    print(f"desk: wrote {result['path']}, {result['bytes'] / 1048576:.2f} MB")
    print(f"desk: wrote {result['local_path']}, the copy with Health, never published")
    job_status.produced("sessions on the desk", result["sessions"])
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("desk", main, ok_codes=OK_CODES))
