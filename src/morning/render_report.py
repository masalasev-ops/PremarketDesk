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
from pathlib import Path

import markdown

from core import artifacts
from core import config
from core import ettime
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


class _StripEmbedsExtension(markdown.Extension):
    def extendMarkdown(self, md):
        # After the inline processor (priority 20) and before prettify (10).
        md.treeprocessors.register(_StripEmbeds(md), "premarketdesk_strip_embeds", 15)


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

_SHELL = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{
    font-family: Georgia, "Times New Roman", serif;
    color: #1a1a1a;
    background: #ffffff;
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
    line-height: 1.55;
  }}
  h1 {{ font-size: 1.6em; border-bottom: 2px solid #1a1a1a; padding-bottom: 6px; }}
  h2 {{ font-size: 1.2em; margin-top: 1.6em; border-bottom: 1px solid #cccccc;
       padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.92em;
          font-family: Arial, Helvetica, sans-serif; }}
  th, td {{ border: 1px solid #bbbbbb; padding: 6px 8px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  code {{ font-family: Consolas, monospace; background: #f5f5f5; padding: 1px 4px; }}
  blockquote {{ border-left: 3px solid #cccccc; margin-left: 0;
               padding-left: 12px; color: #444444; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


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
    html_path.write_text(
        _SHELL.format(title=html.escape(title, quote=False), body=body),
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
