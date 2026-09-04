"""Write site/PremarketDesk.html: one document, eight screens, every session
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
    items = [("morning", "#/", "Morning"), ("midday", "#/", "Midday"),
             ("sessions", "#/sessions", "Sessions"),
             ("record", "#/record", "Record"), ("health", "#/health", "Health")]
    # Morning and Midday resolve against whichever session is selected, so
    # their href is rewritten by the picker rather than fixed here.
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


OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the desk.")
    parser.add_argument("--limit", type=int,
                        help="Inline at most this many sessions. Default is "
                             "CRITERIA [Screens] inline_sessions.")
    parser.add_argument("--no-compact", action="store_true",
                        help="Do not recompact first. Use the frozen payloads "
                             "as they are.")
    args = parser.parse_args(argv)

    if not args.no_compact:
        compact.main([])
    result = render(limit=args.limit, compact_first=False)
    print(f"desk: {result['sessions']} session(s) inlined, "
          f"{result['raw'] / 1048576:.2f} MB of payload became "
          f"{result['encoded'] / 1048576:.2f} MB encoded")
    print(f"desk: wrote {result['path']}, {result['bytes'] / 1048576:.2f} MB")
    job_status.produced("sessions on the desk", result["sessions"])
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("desk", main, ok_codes=OK_CODES))
