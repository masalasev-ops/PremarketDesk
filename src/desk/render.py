"""Write site/PremarketDesk.html: one document, nine screens, every session
inlined.

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
from core import page
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


def payloads(dates: list[str]) -> tuple[dict[str, str], int, int]:
    """Frozen payload per session, gzipped and base64 encoded for inlining.

    A session with no frozen payload is compacted on the spot rather than
    skipped, so a desk built before the nightly has ever run still carries
    every session it can see. Returns the map and the raw and encoded totals,
    which the caller reports because a page that silently grew past what a
    browser will open is the failure this counting exists to catch.
    """
    out: dict[str, str] = {}
    raw_total = encoded_total = 0
    for date in dates:
        payload = compact.load_frozen(date)
        if payload is None:
            payload = compact.compact_session(date)
        if payload is None:
            continue
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        encoded = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
        out[date] = encoded
        raw_total += len(raw)
        encoded_total += len(encoded)
    return out, raw_total, encoded_total


def _nav() -> str:
    items = [("morning", "#/", "Morning"),
             # Sits beside Morning and not after Record, because it is about
             # the SAME session and is read at the same hour. It is a separate
             # screen and not a section of Morning on purpose: the score is
             # the desk's opinion and a base rate is a count of what lookalikes
             # did, and folding one into the other hides the case where they
             # disagree, which is the only case either gets corrected by.
             ("precedent", "#/", "Precedent"),
             ("midday", "#/", "Midday"),
             ("report", "#/", "Report"),
             ("sessions", "#/sessions", "Sessions"),
             ("record", "#/record", "Record"), ("health", "#/health", "Health")]
    # Morning, Midday, Report and Health resolve against whichever session is
    # selected, so their href is rewritten by setNav rather than fixed here.
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


def body(index: dict[str, Any], blobs: dict[str, str]) -> str:
    index_json = json.dumps(index, separators=(",", ":"))
    blob_json = json.dumps(blobs, separators=(",", ":"))
    return f"""
<div class="bar">
  <div class="bar-in">
    <div class="mark"><b>PremarketDesk</b><span>Desk</span></div>
    {_nav()}
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
  <div class="eyebrow" id="stamp">
    <span><b class="mono" id="stamp-date">n/a</b> session</span>
    <span>&middot;</span>
    <span>packet <b class="mono" id="stamp-run">n/a</b> ET</span>
    <span>&middot;</span>
    <span>every figure is read from that session's packet, drawn and not described</span>
  </div>
  <div id="screen"></div>
  <p class="foot">
    Prices are premarket and unofficial. Premarket volume, and so every RVOL and
    float rotation on these screens, is an estimate scaled from the collector's
    socket capture and not a consolidated tape measurement; the truth pass writes
    the measured figure beside it overnight and never over it. The screen
    thresholds are unvalidated seed values. Nothing here is advice.
  </p>
</div>
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
    blobs, raw_total, encoded_total = payloads(dates)
    rows = [r for r in rows if r["date"] in blobs]

    index = {"built_at": ettime.stamp(), "knobs": knobs(), "sessions": rows}
    document = page.shell(
        title="PremarketDesk", body=body(index, blobs),
        extra_css=assets.DECK_CSS,
        script=f"<script>{assets.DECK_JS}</script>",
        # REPORT_CSS comes along now that the desk carries the written
        # reports. Safe beside DECK_CSS by construction: every one of its 46
        # selectors is scoped under .report and none of them is bare.
        include_report_css=True)

    config.SITE_DIR.mkdir(parents=True, exist_ok=True)
    destination = config.SITE_DIR / DESK_FILE
    files.write_text_atomically(destination, document, attempts=3, retry_s=0.4)
    return {"path": destination, "sessions": len(rows), "bytes": len(document),
            "raw": raw_total, "encoded": encoded_total}


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
    job_status.produced("sessions on the desk", result["sessions"])
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("desk", main, ok_codes=OK_CODES))
