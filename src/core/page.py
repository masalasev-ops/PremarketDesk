"""The one HTML shell every page this project writes is wrapped in.

Four renderers wrote four unrelated documents until 2026-09-02: the morning
report in Georgia at 720 pixels with hard colours and no dark mode, the midday
report in Georgia at 940 pixels, the archive in Segoe UI with its own tokens
and dark mode, and the weekly page with no doctype, no charset and no viewport
at all, so it opened from disk in quirks mode. build_archive's docstring said
an archived day and a freshly rendered day looked identical, and its `.day`
rules were a hand re-typing of render_report's that had drifted.

This module holds the tokens (light, dark by system preference, dark or light
by an explicit data-theme stamp), the document skeleton, and REPORT_CSS, the
rules for a rendered report body scoped under `.report`, which the morning
page, the midday page and every archived day all wrap themselves in. Parity
is by construction: one CSS string, three users.

No dependency. The renderers import this and nothing here imports them.
"""

from __future__ import annotations

import html
import re
from typing import Any

# Found by the suite, so a page that skipped the shell is caught.
SHELL_MARK = "/* premarketdesk page shell */"

TOKENS_CSS = """
:root {
  --bg: #F3F4F6; --surface: #FFFFFF; --ink: #1B222C; --muted: #58636F;
  --line: #D8DDE3; --accent: #B45E14;
  --good: #2E7D32; --warn: #B98900; --bad: #C62828;
  --active: rgba(180, 94, 20, 0.10);
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #12161C; --surface: #1A2028; --ink: #E7EAEE; --muted: #97A1AC;
    --line: #303845; --accent: #E8A254;
    --good: #6FBF73; --warn: #E0B341; --bad: #E57373;
    --active: rgba(232, 162, 84, 0.14);
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #12161C; --surface: #1A2028; --ink: #E7EAEE; --muted: #97A1AC;
  --line: #303845; --accent: #E8A254;
  --good: #6FBF73; --warn: #E0B341; --bad: #E57373;
  --active: rgba(232, 162, 84, 0.14);
  color-scheme: dark;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  line-height: 1.5;
}
a { color: var(--accent); }
a:focus-visible, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
"""

# A rendered report body. The morning page wraps its markdown in
# <article class="report">, the midday page does the same, and the archive
# gives every day section the class. Georgia is deliberate: the morning page
# is read in a mail client at seven in the morning and a serif at 16 pixels is
# what survives every renderer that has ever been tried.
REPORT_CSS = """
.report {
  font-family: Georgia, "Times New Roman", serif; font-size: 16px; line-height: 1.55;
  max-width: 760px; margin: 0 auto; padding: 24px 16px 48px;
}
.report h1 { font-size: 1.6em; letter-spacing: -0.01em; border-bottom: 2px solid var(--ink);
  padding-bottom: 6px; margin: 0 0 0.6em; }
.report h2 { font-size: 1.2em; margin-top: 1.6em; border-bottom: 1px solid var(--line);
  padding-bottom: 4px; }
.report h3 { font-size: 1.05em; margin-top: 1.4em; }
.report p { margin: 0.7em 0; }
.report .tablewrap { overflow-x: auto; margin: 0.9em 0; }
.report table { border-collapse: collapse; width: 100%; font-size: 0.92em;
  font-family: Arial, Helvetica, sans-serif; }
.report th, .report td { border: 1px solid var(--line); padding: 6px 8px; text-align: left;
  vertical-align: top; }
.report th { background: var(--active); font-weight: 600; }
.report td.num, .report th.num { text-align: right; font-variant-numeric: tabular-nums;
  white-space: nowrap; }
.report td.conv-green { color: var(--good); font-weight: 600; }
.report td.conv-yellow { color: var(--warn); font-weight: 600; }
.report td.conv-red { color: var(--bad); font-weight: 600; }
.report td.conv-unscored { color: var(--muted); font-style: italic; }
.report code { font-family: Consolas, monospace; background: var(--active); padding: 1px 4px; }
.report blockquote { border-left: 3px solid var(--line); margin-left: 0; padding-left: 12px;
  color: var(--muted); }
.report p.glance { background: var(--active); border-left: 4px solid var(--ink);
  padding: 10px 14px; font-family: Arial, Helvetica, sans-serif; font-size: 0.95em; }
.report p.disclaimer { font-size: 0.85em; color: var(--muted); }
.report .local-only { margin-top: 2.5em; padding-top: 10px; border-top: 1px solid var(--line);
  font-family: Arial, Helvetica, sans-serif; font-size: 0.85em; color: var(--muted); }
.report .local-only a { color: var(--ink); }
@media print {
  .report { max-width: none; padding: 0; }
  .report .local-only { display: none; }
  .report a { color: inherit; text-decoration: none; }
}
"""

_DOCUMENT = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{mark}
{tokens}
{report_css}
{extra_css}
</style>
</head>
<body{body_class}>
{body}
{script}
</body>
</html>
"""


def shell(title: str, body: str, extra_css: str = "", script: str = "",
          lang: str = "en", body_class: str = "", include_report_css: bool = True) -> str:
    """A complete document around a body fragment.

    `title` is inserted as given and must already be escaped by the caller,
    because the callers build it differently (a model's mood phrase, a fixed
    string) and one of them is pinned by the suite to escape it itself.
    `extra_css` is the page's own rules and comes after REPORT_CSS so it wins.
    `script` is a complete <script>...</script> element or empty.
    """
    return _DOCUMENT.format(
        lang=lang, title=title, mark=SHELL_MARK, tokens=TOKENS_CSS,
        report_css=REPORT_CSS if include_report_css else "",
        extra_css=extra_css, body=body, script=script,
        body_class=f' class="{body_class}"' if body_class else "")


def escape(value: Any) -> str:
    """Text into HTML, quotes included."""
    return html.escape(str(value if value is not None else ""))


def num(value: Any, digits: int = 2, null: str = "null") -> str:
    """A number for a cell, or the null word. Never a Python repr."""
    if value is None:
        return null
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return escape(value)


def pct(value: Any, digits: int = 2, null: str = "n/a") -> str:
    if value is None:
        return null
    try:
        return f"{float(value):+.{digits}f}%"
    except (TypeError, ValueError):
        return escape(value)


# What a table cell has to look like to be right aligned: a signed number with
# optional thousands separators, decimals, and a percent, x, B or M suffix, or
# one of the words the reports use for a missing figure.
_NUMERIC_CELL_RE = re.compile(r"^[+-]?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|x|B|M)?$")
_NULL_WORDS = frozenset({"null", "n/a", "-", "unscored"})


def looks_numeric(text: str) -> bool:
    text = text.strip()
    return bool(_NUMERIC_CELL_RE.match(text)) or text in _NULL_WORDS
