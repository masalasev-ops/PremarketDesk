"""Rebuild the single file report archive from runs/.

One self contained HTML file at site/PremarketDesk.html that opens by double
clicking, no web server, no network requests of any kind. Chrome blocks fetch
on file://, so every byte the page needs is inlined at build time: the CSS,
every embedded day's report HTML, and the tiny script that switches days.

The build is a full rebuild from what is on disk, never an append, so running
it twice is the same as running it once, and deleting site/ entirely costs
nothing but the next run.

Each run directory contributes its report.md and, where the 12:00 pass wrote
one, its report_midday.md, both rendered through render_report.to_html and
styled by core/page.py's REPORT_CSS, the same stylesheet report.html and
report_midday.html carry, so an archived day and a freshly rendered day look
identical by construction. The newest embed_sessions days (CRITERIA.md
[archive]) are inlined in full; older days stay in the rail but link out to
their own runs/<date>/report.html, which is rendered on the spot if the
morning that wrote report.md never got to the render step.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


from core import config
from core import criteria
from core import ettime
from core import page
from ops import job_status
from morning import render_report

_CRIT = criteria.load()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The archive's own layout: the rail, the pane, the day switching. The
# tokens and the report body rules come from core/page.py, so an archived
# day and a freshly rendered report.html share one stylesheet by
# construction rather than by a copy that drifts.
_ARCHIVE_CSS = """
  .shell { display: flex; height: 100vh; }
  .rail {
    width: 250px; flex: none; overflow-y: auto;
    background: var(--surface); border-right: 1px solid var(--line);
    padding: 14px 0 24px;
  }
  .rail-head {
    padding: 4px 16px 12px; border-bottom: 1px solid var(--line);
    margin-bottom: 8px;
  }
  .rail-head strong { font-size: 1.02rem; letter-spacing: -0.01em; }
  .rail-head span { display: block; font-size: 0.75rem; color: var(--muted); }
  .rail-day {
    display: flex; justify-content: space-between; align-items: baseline;
    width: 100%; padding: 7px 16px; border: 0; background: none;
    color: var(--ink); font: inherit; text-align: left; cursor: pointer;
    text-decoration: none; gap: 8px;
  }
  .rail-day:hover { background: var(--active); }
  .rail-day:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .rail-day.active { background: var(--active); box-shadow: inset 3px 0 0 var(--accent); }
  .rail-day .d {
    font-family: "Cascadia Code", Consolas, monospace; font-size: 0.82rem;
  }
  .rail-day .counts {
    font-family: "Cascadia Code", Consolas, monospace; font-size: 0.74rem;
    color: var(--muted); white-space: nowrap;
  }
  .counts em { font-style: normal; }
  .counts .g { color: var(--good); }
  .counts .y { color: var(--warn); }
  .counts .r { color: var(--bad); }
  .fixture-note {
    max-width: 760px; margin: 0 auto 20px; padding: 12px 16px;
    border: 1px solid var(--bad); border-left-width: 4px; border-radius: 4px;
    font-size: 0.85rem; line-height: 1.5; color: var(--bad);
  }
  .fixture-note strong { color: var(--bad); }
  .rail-note {
    padding: 10px 16px 4px; font-size: 0.7rem; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--muted);
    border-top: 1px solid var(--line); margin-top: 8px;
  }
  .rail-day.out .d::after { content: " \\2197"; color: var(--muted); }
  .pane { flex: 1; overflow-y: auto; padding: 28px 36px 80px; }
  .day { max-width: 760px; margin: 0 auto; }
  .day[hidden] { display: none; }
  .hint {
    max-width: 760px; margin: 0 auto 18px; font-size: 0.75rem;
    color: var(--muted); font-family: "Cascadia Code", Consolas, monospace;
  }
  .day .midday { margin-top: 3em; padding-top: 1.5em; border-top: 3px double var(--line); }
  .day .midday h1 { font-size: 1.3rem; }
  .day .midday-absent { color: var(--muted); font-size: 0.9em; }
  .empty { max-width: 760px; margin: 40px auto; color: var(--muted); }
  .day.report { padding: 0 0 48px; }
  @media (max-width: 720px) {
    .shell { flex-direction: column; height: auto; }
    .rail { width: auto; max-height: 38vh; border-right: 0; border-bottom: 1px solid var(--line); }
    .pane { padding: 16px 12px 48px; overflow: visible; }
    .hint { display: none; }
  }
  @media print {
    .shell { display: block; height: auto; }
    .rail, .hint { display: none; }
    .pane { overflow: visible; padding: 0; }
    .day[hidden] { display: none; }
  }
"""

_BODY = """<div class="shell">
  <nav class="rail" aria-label="Sessions">
    <div class="rail-head">
      <strong>PremarketDesk</strong>
      <span>__SUBTITLE__</span>
    </div>
__RAIL__
  </nav>
  <main class="pane">
    <p class="hint">j / k or the arrow keys step between days; the address hash picks a day directly.</p>
__DAYS__
  </main>
</div>
"""

_SCRIPT = """<script>
(function () {
  "use strict";
  var buttons = Array.prototype.slice.call(document.querySelectorAll(".rail-day[data-date]"));
  var dates = buttons.map(function (b) { return b.getAttribute("data-date"); });
  if (dates.length === 0) { return; }
  var pane = document.querySelector(".pane");
  var current = -1;
  function select(index) {
    if (index < 0 || index >= dates.length) { index = 0; }
    current = index;
    for (var i = 0; i < dates.length; i += 1) {
      var section = document.getElementById("day-" + dates[i]);
      if (section) { section.hidden = i !== index; }
      if (i === index) { buttons[i].classList.add("active"); }
      else { buttons[i].classList.remove("active"); }
    }
    pane.scrollTop = 0;
    if (buttons[index].scrollIntoView) {
      buttons[index].scrollIntoView({ block: "nearest" });
    }
  }
  function fromHash() {
    var raw = window.location.hash.replace(/^#/, "");
    var idx = dates.indexOf(raw);
    select(idx === -1 ? 0 : idx);
  }
  window.addEventListener("hashchange", fromHash);
  buttons.forEach(function (button, index) {
    button.addEventListener("click", function () {
      if (window.location.hash === "#" + dates[index]) { select(index); }
      else { window.location.hash = dates[index]; }
    });
  });
  document.addEventListener("keydown", function (event) {
    var step = 0;
    if (event.key === "j" || event.key === "ArrowDown") { step = 1; }
    else if (event.key === "k" || event.key === "ArrowUp") { step = -1; }
    else { return; }
    event.preventDefault();
    var next = current + step;
    if (next < 0) { next = 0; }
    if (next > dates.length - 1) { next = dates.length - 1; }
    if (next !== current) { window.location.hash = dates[next]; }
  });
  fromHash();
})();
</script>
"""


# What config.build_identifier() can legitimately put in a packet's commit
# field: a resolved HEAD, which is forty hex characters. It writes null with a
# commit_reason when it cannot resolve one, and it has no third answer. So a
# commit that is neither of those did not come from this code, and the only
# thing in the tree that writes one is the test fixture in
# tests/test_entrypoints.py, whose "stub" landed on a real run directory on
# 2026-08-21 and has been published as a morning ever since.
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _fixture_reason(packet: dict[str, Any]) -> str | None:
    """Why this packet was not written by a scheduled run, or None.

    Matched on the SHAPE of the commit rather than on the string "stub",
    because the next fixture to reach a run directory will not be spelled the
    same and a guard that names one value only ever catches that one.

    THE TWO SILENCES ARE NOT THE SAME AS A WRONG ANSWER, and the first draft of
    this got that wrong and accused two real mornings. A packet with no build
    key at all predates 2026-08-14, when the field was added, and 2026-08-13
    and 2026-08-14 are both on disk that way; a build dict whose commit is null
    is a run on a machine that could not resolve HEAD, which
    config.build_identifier writes deliberately with a commit_reason beside it.
    Neither says anything about whether a market was involved, so neither is
    reported. Only a commit that is PRESENT and is not a resolved HEAD is a
    statement no version of this code makes.
    """
    build = packet.get("build")
    if not isinstance(build, dict):
        return None  # predates the field; the packet cannot be asked
    commit = build.get("commit")
    if commit is None:
        return None  # a legitimate run on a machine that could not resolve HEAD
    if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
        return f"its packet was built by {commit!r}, which is not a commit"
    return None


def _counts_from_packet(run_dir: Path) -> dict[str, Any] | None:
    packet_path = run_dir / "packet.json"
    if not packet_path.is_file():
        return None
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"archive: {run_dir.name} packet.json unreadable ({exc}), counts omitted")
        # The archive still rebuilds and still carries the session, so the
        # exit code stays zero. A session that silently loses its counts is
        # how the archive quietly stops being the record it exists to be.
        job_status.failed(f"{type(exc).__name__}: {run_dir.name}/packet.json is "
                          "unreadable, so that session is archived without counts")
        return None
    candidates = packet.get("candidates", [])
    tally = {"green": 0, "yellow": 0, "red": 0}
    for candidate in candidates:
        conviction = str(candidate.get("conviction") or "")
        if conviction in tally:
            tally[conviction] += 1
    return {"candidates": len(candidates), "fixture": _fixture_reason(packet), **tally}


def _counts_html(counts: dict[str, Any] | None) -> str:
    if counts is None:
        return '<span class="counts">no packet</span>'
    if counts.get("fixture"):
        return '<span class="counts">not a morning</span>'
    return (
        f'<span class="counts">{counts["candidates"]} &#183; '
        f'<em class="g">{counts["green"]}</em> '
        f'<em class="y">{counts["yellow"]}</em> '
        f'<em class="r">{counts["red"]}</em></span>'
    )


def _fixture_banner(date: str, counts: dict[str, Any] | None) -> str:
    """The line an embedded fixture session opens with, or nothing.

    Above the report rather than below it, because the numbers underneath are
    the thing being disclaimed and a reader who stops after the tables must
    have already passed this.

    Kept rather than dropped from the archive. Removing the session would make
    the loss invisible, and a gap in the rail reads as a day the market was
    shut. This file is the record; a record that quietly omits what went wrong
    is the failure it exists to prevent.
    """
    if not counts or not counts.get("fixture"):
        return ""
    return (
        f'<p class="fixture-note"><strong>{date} is not a morning.</strong> '
        f'{counts["fixture"]}. The numbers below are test fixture values that '
        "were written over this session's real evidence, and the real evidence "
        "is gone. Nothing here was measured from a market.</p>"
    )


def collect_runs() -> list[dict[str, Any]]:
    """Every run directory holding a report.md, newest first. Skips are logged."""
    entries: list[dict[str, Any]] = []
    if not config.RUNS_DIR.is_dir():
        return entries
    for run_dir in sorted(config.RUNS_DIR.iterdir(), key=lambda p: p.name, reverse=True):
        if not run_dir.is_dir() or not _DATE_RE.match(run_dir.name):
            continue
        report = run_dir / "report.md"
        if not report.is_file():
            print(f"archive: skipped {run_dir.name}, no report.md")
            continue
        try:
            text = report.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"archive: skipped {run_dir.name}, report.md unreadable: {exc}")
            continue
        # The midday report too, where the 12:00 pass wrote one. Until
        # 2026-09-02 report_midday.md was reachable only by browsing runs/:
        # nothing delivered it, nothing linked to it and this page did not
        # carry it. Absent is None, not an empty string, so the day section
        # can say the pass has not run rather than render nothing.
        midday_path = run_dir / "report_midday.md"
        midday_text = None
        if midday_path.is_file():
            try:
                midday_text = midday_path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"archive: {run_dir.name} report_midday.md unreadable, "
                      f"carried without it: {exc}")
        entries.append({
            "date": run_dir.name,
            "dir": run_dir,
            "markdown": text,
            "midday_markdown": midday_text,
            "counts": _counts_from_packet(run_dir),
        })
    return entries


def build(embed_sessions: int) -> Path:
    entries = collect_runs()
    embedded = entries[:embed_sessions]
    linked = entries[embed_sessions:]

    rail_parts: list[str] = []
    day_parts: list[str] = []

    for entry in embedded:
        date = entry["date"]
        rail_parts.append(
            f'    <button class="rail-day" data-date="{date}">'
            f'<span class="d">{date}</span>{_counts_html(entry["counts"])}</button>'
        )
        # render_report.to_html, not markdown.markdown with a borrowed
        # extension list. This page concatenates twelve mornings, so a raw tag
        # in one headline reaches the other eleven; see the note on
        # _TAG_OPENER_RE.
        body = render_report.to_html(entry["markdown"])
        banner = _fixture_banner(date, entry["counts"])
        # The midday report under the morning's, through the same renderer,
        # behind a rule so the two documents read as two. A day without one
        # says so in a sentence rather than ending where the morning ends.
        if entry.get("midday_markdown"):
            midday = ('<div class="midday">'
                      + render_report.to_html(entry["midday_markdown"])
                      + "</div>")
        else:
            midday = ('<div class="midday"><p class="midday-absent">The 12:00 '
                      "midday pass has not written a report for this day.</p></div>")
        day_parts.append(f'<section class="day report" id="day-{date}" hidden>\n'
                         f'{banner}{body}\n{midday}\n</section>')

    if linked:
        rail_parts.append('    <div class="rail-note">Older, opens its own page</div>')
    for entry in linked:
        date = entry["date"]
        # The link target must exist even for a morning that died before the
        # render step, so render it now from the report.md we just read.
        target = entry["dir"] / "report.html"
        if not target.is_file():
            render_report.render(entry["dir"] / "report.md")
            print(f"archive: rendered missing {target}")
        rail_parts.append(
            f'    <a class="rail-day out" href="../runs/{date}/report.html">'
            f'<span class="d">{date}</span>{_counts_html(entry["counts"])}</a>'
        )

    if not entries:
        day_parts.append('<p class="empty">No runs with a report.md were found. '
                         'The archive fills in as mornings run.</p>')

    fixtures = [e["date"] for e in entries
                if e["counts"] and e["counts"].get("fixture")]
    subtitle = (
        f"{len(entries)} session{'s' if len(entries) != 1 else ''}, "
        f"{len(embedded)} embedded, rebuilt {ettime.stamp(ettime.now_et())}"
        + (f", {len(fixtures)} not a morning" if fixtures else "")
    )
    for date in fixtures:
        print(f"archive: {date} is carried but is NOT a morning, and the page "
              "says so on the session and in the rail")
    body = (
        _BODY
        .replace("__SUBTITLE__", subtitle)
        .replace("__RAIL__", "\n".join(rail_parts))
        .replace("__DAYS__", "\n".join(day_parts))
    )
    document = page.shell("PremarketDesk Archive", body, extra_css=_ARCHIVE_CSS,
                          script=_SCRIPT, body_class="archive")

    site_dir = config.SITE_DIR
    site_dir.mkdir(parents=True, exist_ok=True)
    out_path = site_dir / "PremarketDesk.html"
    out_path.write_text(document, encoding="utf-8")
    print(f"archive: wrote {out_path} ({out_path.stat().st_size:,} bytes, "
          f"{len(embedded)} embedded, {len(linked)} linked out)")
    return out_path


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild the single file report archive.")
    parser.add_argument("--embed", type=int, default=None, metavar="N",
                        help="Override the CRITERIA.md embed_sessions knob, for testing.")
    args = parser.parse_args(argv)
    embed_sessions = args.embed if args.embed is not None else _CRIT.integer(
        "archive", "embed_sessions")
    out_path = build(embed_sessions)
    job_status.produced("archive bytes", out_path.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("archive", main, ok_codes=OK_CODES))
