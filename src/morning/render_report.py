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
                             extensions=_EXTENSIONS)

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


def render(report_path: Path) -> Path:
    text = report_path.read_text(encoding="utf-8")
    body = to_html(text)

    title = "PremarketDesk"
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    html_path = report_path.with_suffix(".html")
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
    args = parser.parse_args(argv)

    report_path = (
        Path(args.report) if args.report
        else config.run_path(ettime.today_et().isoformat()) / "report.md"
    )
    if not report_path.is_file():
        print(f"render: there is no report at {report_path}. Run analyst.py first.")
        return 1

    html_path = render(report_path)
    job_status.produced("html bytes", html_path.stat().st_size)
    print(f"render: wrote {html_path} ({html_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(job_status.run("render", main, ok_codes=OK_CODES))
