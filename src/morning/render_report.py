"""Render report.md to report.html in the same runs/YYYY-MM-DD directory.

The markdown library with tables, fenced_code and sane_lists, wrapped in a
small self contained HTML shell. The styling is deliberately plain: the report
is read in an email client at seven in the morning, and every fancy thing an
email client cannot render is a fancy thing that turns into noise there.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import xml.etree.ElementTree as etree
from pathlib import Path

import markdown

from core import artifacts
from core import config
from core import ettime
from core import glossary
from core import page
from ops import job_status

_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]

# A `<` that begins something tag SHAPED. Python-Markdown passes raw HTML
# through by design and dropped safe_mode in 3.0, so every character of the
# report reaches the page as markup unless something stops it.
#
# The report is not all first party text. Vendor news headlines are quoted into
# it verbatim, from a feed nobody here controls, and they land in the Premarket
# gappers section and in Skips and traps. A headline carrying "</section>"
# closes the archive's day early and takes the rest of the page with it,
# because build_archive wraps each morning in
# `<section class="day" id="day-DATE" hidden>` and its day switching script
# then addresses a section that no longer contains what it should. A headline
# carrying `<script>` runs when the file is opened.
#
# Neither is likely from a real newswire. Both are ordinary consequences of
# putting third party text into a document with passthrough on, which is the
# same reasoning that made the collector scrub its token out of exception text
# before printing.
#
# Only the tag SHAPED `<` is neutralised, so "guidance < consensus" is left for
# markdown to escape as it already does, and blockquotes are untouched because
# `>` is not matched at all. No archived report contains a raw tag, an autolink
# or a fenced block, and neither REPORT_TEMPLATE.md nor prompt_analyst.md asks
# for HTML, so nothing legitimate is being taken away.
#
# The one wart: inside an inline code span, `<b>` now renders as &lt;b>,
# because markdown escapes the ampersand this produces. No report uses a code
# span at all, and the alternative is passthrough.
_TAG_OPENER_RE = re.compile(r"<(?=[a-zA-Z/!?])")

# The other way third party text reaches the page as markup. _TAG_OPENER_RE
# stops a raw tag, and markdown's own syntax then puts two back: `![p](url)`
# renders an <img> and `[x](url)` an <a>, from a vendor headline as readily as
# from the template. An image in the emailed report is a fetch to a host the
# feed chose, which is a tracking pixel, and build_archive promises the archive
# makes no network request of any kind. A javascript: href in an anchor runs
# when clicked. No archived report carries a link or an image and nothing in
# REPORT_TEMPLATE.md asks for one, so nothing legitimate is removed; the one
# link the renderer keeps is an ordinary http(s) anchor, because a future
# footer may want one and a plain web link is not the hazard.
_SAFE_HREF_RE = re.compile(r"^https?://", re.IGNORECASE)


class _StripEmbeds(markdown.treeprocessors.Treeprocessor):
    """Drop every image and every anchor whose href is not plain http(s).

    A Treeprocessor runs over the parsed tree after inline patterns, which is
    the one place the image and the anchor exist as elements rather than as
    text that might or might not be syntax. The element is replaced by its own
    text (the alt text or the link text), so the sentence still reads.
    """

    def run(self, root):
        for parent in list(root.iter()):
            # Last child first, so removing one never shifts the index of a
            # sibling still to be visited. Walking forward, the second embed
            # in a sentence took the first one's slot, was handed its own
            # text as a tail, and was then removed with it.
            for index in range(len(parent) - 1, -1, -1):
                child = parent[index]
                if child.tag == "img":
                    self._unwrap(parent, index, child, child.get("alt") or "")
                elif child.tag == "a" and not _SAFE_HREF_RE.match(child.get("href") or ""):
                    self._unwrap(parent, index, child, "".join(child.itertext()))

    @staticmethod
    def _unwrap(parent, index, child, text):
        # Keep the text where the element was: onto the previous sibling's
        # tail, or the parent's text if the element came first.
        tail = child.tail or ""
        if index == 0:
            parent.text = (parent.text or "") + text + tail
        else:
            previous = parent[index - 1]
            previous.tail = (previous.tail or "") + text + tail
        parent.remove(child)


class _ClassParagraphs(markdown.treeprocessors.Treeprocessor):
    """Two paragraphs the stylesheet treats differently, found by their words.

    The disclaimer opens with "Nothing here is advice", which is the string
    analyst.py already keys on, and the at a glance strip opens with the
    marker analyst.summary_strip writes. Neither can carry a class in
    markdown, so the class is added here, on the parsed tree.
    """

    def run(self, root):
        for element in root.iter("p"):
            text = "".join(element.itertext()).strip()
            if text.startswith("Nothing here is advice"):
                element.set("class", "disclaimer")
            elif text.startswith("At a glance."):
                element.set("class", "glance")


_CONVICTION_WORDS = {"green": "conv-green", "yellow": "conv-yellow",
                     "red": "conv-red", "unscored": "conv-unscored"}


class _DressTables(markdown.treeprocessors.Treeprocessor):
    """What a table needs to read on a phone and in a mail client.

    Every table is wrapped in a scrolling div, so a ten column notable movers
    table scrolls inside its own box instead of pushing the page sideways on a
    390 pixel screen. Cells that hold a number are classed `num` and right
    aligned with tabular figures, so -7.40 and -23.07 line up. A cell in a
    column headed Conviction is classed by its word, so green, yellow, red and
    unscored are colours and not four words that look alike. Every table
    carries border="1" cellpadding="6" as well, because a mail client that
    strips the style block leaves an HTML table borderless, and ten columns of
    whitespace separated words is not a table.

    A watchlist table whose only body row reads `none` in its first cell is
    removed, sentence and all it was: the sentence beneath it already says the
    screen produced nothing, and the markdown keeps the table because the
    containment guard reads the markdown, not this page. The column legend
    and the conviction band definition that analyst and glossary write under
    it go with it, because until 2026-09-02 they stayed, a "Reading the
    columns" line under no columns and a band definition under no bands.
    """

    def run(self, root):
        for parent in list(root.iter()):
            for index in range(len(parent) - 1, -1, -1):
                table = parent[index]
                if table.tag != "table":
                    continue
                if self._is_none_only(table):
                    self._remove_keeping_tail(parent, index)
                    # The legends sit at the same index now that the table
                    # is gone. Walking DOWN the parent, those paragraphs were
                    # visited already and nothing below index shifts.
                    while index < len(parent) and self._is_table_legend(parent[index]):
                        self._remove_keeping_tail(parent, index)
                    continue
                self._dress(table)
                wrapper = etree.Element("div")
                wrapper.set("class", "tablewrap")
                # A box that scrolls sideways has to be reachable from the
                # keyboard, or a reader who does not use a mouse cannot see
                # the columns past the edge. WCAG 2.1.1, and the axe rule
                # scrollable-region-focusable names exactly this element.
                wrapper.set("tabindex", "0")
                wrapper.set("role", "region")
                wrapper.set("aria-label", "table, scrolls sideways")
                wrapper.tail = table.tail
                table.tail = None
                parent.remove(table)
                parent.insert(index, wrapper)
                wrapper.append(table)

    @staticmethod
    def _rows(table):
        for section in table:
            if section.tag in ("thead", "tbody"):
                for row in section:
                    yield section.tag, row
            elif section.tag == "tr":
                yield "tbody", section

    @staticmethod
    def _remove_keeping_tail(parent, index) -> None:
        element = parent[index]
        tail = element.tail or ""
        parent.remove(element)
        if index > 0:
            parent[index - 1].tail = (parent[index - 1].tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail

    @staticmethod
    def _is_table_legend(element) -> bool:
        if element.tag != "p":
            return False
        text = "".join(element.itertext()).strip()
        return text.startswith((glossary.LEGEND_PREFIX, glossary.BAND_LEGEND_PREFIX))

    def _is_none_only(self, table) -> bool:
        body_rows = [row for where, row in self._rows(table) if where == "tbody"]
        if len(body_rows) != 1:
            return False
        cells = list(body_rows[0])
        if not cells:
            return False
        first = "".join(cells[0].itertext()).strip().lower()
        rest = all(not "".join(c.itertext()).strip() for c in cells[1:])
        return first == "none" and rest

    def _dress(self, table) -> None:
        table.set("border", "1")
        table.set("cellpadding", "6")
        headers: list[str] = []
        for where, row in self._rows(table):
            if where == "thead":
                headers = ["".join(c.itertext()).strip().lower() for c in row]
                break
        for where, row in self._rows(table):
            for position, cell in enumerate(row):
                text = "".join(cell.itertext()).strip()
                classes: list[str] = []
                header = headers[position] if position < len(headers) else ""
                if where == "tbody" and header == "conviction":
                    klass = _CONVICTION_WORDS.get(text.lower())
                    if klass:
                        classes.append(klass)
                if where == "tbody" and position > 0 and page.looks_numeric(text):
                    classes.append("num")
                if classes:
                    cell.set("class", " ".join(classes))


class _StripEmbedsExtension(markdown.Extension):
    def extendMarkdown(self, md):
        # After the inline processor (priority 20) and before prettify (10).
        md.treeprocessors.register(_StripEmbeds(md), "premarketdesk_strip_embeds", 15)
        md.treeprocessors.register(_ClassParagraphs(md), "premarketdesk_classes", 14)
        md.treeprocessors.register(_DressTables(md), "premarketdesk_tables", 13)


def to_html(text: str) -> str:
    """Report markdown to a body fragment, with raw HTML neutralised.

    THE one place markdown is rendered. build_archive embeds twelve mornings
    into a single page and used to call markdown.markdown itself with this
    module's extension list, so the two agreed on extensions and would not have
    agreed on this. A renderer that escapes and an archive that does not is the
    archive being the unescaped one, which is also the file that concatenates
    twelve reports into one document where a single unclosed tag reaches
    eleven other mornings.
    """
    return markdown.markdown(_TAG_OPENER_RE.sub("&lt;", text),
                             extensions=[*_EXTENSIONS, _StripEmbedsExtension()])


# The footer's links are RELATIVE PATHS on this machine, from runs/<date>/ to
# the sibling sessions and to site/. They are dead in an email, so deliver.py
# strips the whole div by this class before sending, and the archive never
# sees it because the archive renders the markdown, not this shell.
LOCAL_ONLY_CLASS = "local-only"


def footer_links(report_path: Path) -> str:
    """Previous session, this day's midday page, the archive and the weekly page.

    Until 2026-09-02 report.html carried zero anchors: the midday report was
    written at 12:00 and reachable only by browsing runs/, and nothing linked
    to the archive or the weekly page from the morning a reader actually
    opens. Only links whose target exists are written, so a day with no
    midday pass yet shows none, and the sentence says so instead.
    """
    run_dir = report_path.parent
    runs_dir = run_dir.parent
    date = run_dir.name
    links: list[str] = []
    previous = None
    if runs_dir.is_dir():
        for sibling in sorted(runs_dir.iterdir(), key=lambda p: p.name, reverse=True):
            if sibling.is_dir() and sibling.name < date and (sibling / "report.html").is_file():
                previous = sibling.name
                break
    if previous:
        links.append(f'<a href="../{previous}/report.html">previous session {previous}</a>')
    midday = run_dir / "report_midday.html"
    if midday.is_file():
        links.append('<a href="report_midday.html">the midday report for this day</a>')
    else:
        links.append("the midday report is written at 12:00 and is not here yet")
    site = runs_dir.parent / "site"
    if (site / "PremarketDesk.html").is_file():
        links.append(f'<a href="../../site/PremarketDesk.html#{date}">the archive</a>')
    if (site / "Weekly.html").is_file():
        links.append('<a href="../../site/Weekly.html">the weekly page</a>')
    return (f'<div class="{LOCAL_ONLY_CLASS}"><p>Also on this machine: '
            + "; ".join(links) + ".</p></div>")


def render(report_path: Path, overwrite: bool = False) -> Path:
    """Render one report, sparing a past morning's HTML by default.

    artifacts.py named this writer as one of three still going straight to
    write_text, and the hazard is not hypothetical: on 2026-08-28 a review
    loop called render() over every archived report.md to check that the
    escaping change had not altered them, and rewrote twelve past mornings'
    report.html in the process. Bodies were identical so nothing was lost, and
    that was luck rather than design.

    The scheduled path is unaffected: a .bat sets PMD_JOB, artifacts.scheduled_run
    reads it, and the chain owns today's artifacts and rewrites them freely.
    """
    text = report_path.read_text(encoding="utf-8")
    body = to_html(text)

    title = "PremarketDesk"
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    html_path, _spared = artifacts.resolve(
        report_path.with_suffix(".html"),
        overwrite or artifacts.scheduled_run(),
        what="render")
    # The title is the model's own mood phrase and goes into an element that
    # does not parse markup, so it is escaped rather than neutralised: a bare
    # `<` there ends the title element and the rest of the line becomes body.
    # One shell for every page this project writes, see core/page.py. The
    # body is an article classed report, the same class an archived day and
    # the midday page carry, so the three cannot drift apart in style.
    article = ('<article class="report">\n' + body + "\n"
               + footer_links(report_path) + "\n</article>")
    html_path.write_text(
        page.shell(html.escape(title, quote=False), article),
        encoding="utf-8")
    return html_path


# The exit codes that mean this step did its job. Declared at module level so
# the __main__ line below and the entrypoint test harness read the same value:
# a literal inside __main__ is invisible to a harness that imports the module
# and calls main() directly. See ops/job_status.py for the contract.
OK_CODES = (0,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render report.md to report.html.")
    parser.add_argument("--report", metavar="PATH",
                        help="Report to render. Defaults to runs/<today>/report.md.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace an existing report.html instead of "
                             "writing beside it. See core/artifacts.py.")
    args = parser.parse_args(argv)

    report_path = (
        Path(args.report) if args.report
        else config.run_path(ettime.today_et().isoformat()) / "report.md"
    )
    if not report_path.is_file():
        print(f"render: there is no report at {report_path}. Run analyst.py first.")
        return 1

    html_path = render(report_path, overwrite=args.overwrite)
    job_status.produced("html bytes", html_path.stat().st_size)
    print(f"render: wrote {html_path} ({html_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("render", main, ok_codes=OK_CODES))
