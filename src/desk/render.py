"""Write site/Desk.html: one document, seven screens, every session inlined.

A FULL REBUILD FROM WHAT IS ON DISK, never an append, so running it twice is
the same as running it once and deleting site/Desk.html costs nothing but the
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

DESK_FILE = "Desk.html"

# The knobs the application reads. Passed in rather than restated in
# JavaScript, so CRITERIA stays the one place a display bound is written down
# and a change to it reaches the page without editing the page.
_KNOB_KEYS = (
    ("spine_scale_pct", "number"),
    ("path_min_bars", "integer"),
    ("ladder_label_gap_px", "integer"),
    ("sessions_page_size", "integer"),
)


def knobs() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, kind in _KNOB_KEYS:
        out[key] = (_CRIT.integer("screens", key) if kind == "integer"
                    else _CRIT.number("screens", key))
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
      <select class="btn" id="session-picker" aria-label="Session"></select>
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


def render(limit: int | None = None) -> dict[str, Any]:
    limit = limit if limit is not None else _CRIT.integer("screens", "inline_sessions")
    rows = index_rows()
    if not rows:
        # Nothing has been compacted, so compact everything first rather than
        # write an empty desk. A desk with no sessions is indistinguishable
        # from a desk whose build half worked.
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
        include_report_css=False)

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
    result = render(limit=args.limit)
    print(f"desk: {result['sessions']} session(s) inlined, "
          f"{result['raw'] / 1048576:.2f} MB of payload became "
          f"{result['encoded'] / 1048576:.2f} MB encoded")
    print(f"desk: wrote {result['path']}, {result['bytes'] / 1048576:.2f} MB")
    job_status.produced("sessions on the desk", result["sessions"])
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("desk", main, ok_codes=OK_CODES))
