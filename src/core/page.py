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

# Contrast is checked against the surface the text sits on, to WCAG AA: 4.5:1
# for body text, 3:1 for a rule that carries meaning. --muted is the value
# that has to be watched, because it is the one a redesign always lightens:
# #5B6672 on #FFFFFF is 5.9:1, and the familiar #999 would be 2.8:1 and fail
# at every size. --line is deliberately BELOW 3:1. A row divider is not a
# meaningful graphical object, and a divider pushed to 3:1 is the heavy grid
# that makes a table of numbers hard to read.
TOKENS_CSS = """
:root {
  --bg: #FFFFFF; --surface: #FFFFFF; --raised: #F6F7F9;
  --ink: #16191D; --ink-2: #454B54; --muted: #5B6672;
  --line: #E4E7EB; --line-strong: #9AA0A6; --accent: #A2530F;
  --good: #10704A; --warn: #8A5300; --bad: #A61B1B;
  --active: rgba(162, 83, 15, 0.07);
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #12161C; --surface: #12161C; --raised: #1A2028;
    --ink: #E7EAEE; --ink-2: #C3CAD3; --muted: #9AA5B1;
    --line: #2A323D; --line-strong: #6B7683; --accent: #E8A254;
    --good: #6FBF73; --warn: #E0B341; --bad: #E57373;
    --active: rgba(232, 162, 84, 0.10);
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #12161C; --surface: #12161C; --raised: #1A2028;
  --ink: #E7EAEE; --ink-2: #C3CAD3; --muted: #9AA5B1;
  --line: #2A323D; --line-strong: #6B7683; --accent: #E8A254;
  --good: #6FBF73; --warn: #E0B341; --bad: #E57373;
  --active: rgba(232, 162, 84, 0.10);
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
# is read in a mail client at seven in the morning and a serif at 17 pixels is
# what survives every renderer that has ever been tried.
#
# Rewritten 2026-09-02 against the reading research, which the 2026-09-02
# report failed on every count a reader would notice.
#
#   MEASURE. Prose is capped at 68 characters and the container is not, so a
#   ten column table gets the width it needs while a paragraph stays in a
#   column the eye can track. Butterick puts the readable band at 45 to 90
#   characters and Nielsen Norman at 50 to 70; a 760 pixel serif paragraph
#   was running past 95.
#
#   HEADING SPACE IS ASYMMETRIC. Two lines above a heading, half a line
#   below. Equal margins are what makes a heading float between two blocks
#   and belong to neither, and equal margins are what this file had.
#
#   TABLES LOSE THEIR GRID. Horizontal rules only, no verticals, no zebra.
#   Butterick's tables chapter and Rutter's on designing tables to be read
#   both say to remove every mark that is not data or white space and then
#   put back only what is needed; the cell border on all four sides of every
#   cell of a ten column table is the clutter they are describing. The header
#   is quieter than the data rather than louder, which is Material's rule,
#   and the space that the borders used to do the work of now comes from
#   padding.
#
#   FIGURES LINE UP. lining-nums and tabular-nums, without which a column of
#   numbers in a proportional face does not form a column at all. Arial and
#   Segoe UI carry tabular figures by default, which is the insurance for the
#   mail clients that strip the property.
#
# The border="1" and cellpadding attributes render_report writes stay on the
# element for a client that drops this stylesheet: presentational attributes
# lose to CSS in a browser, so the two do not fight.
REPORT_CSS = """
.report {
  --measure: 68ch; --u: 1.6rem;
  font-family: Georgia, "Times New Roman", serif; font-size: 17px; line-height: 1.55;
  color: var(--ink);
  max-width: 900px; margin: 0 auto; padding: 40px 24px 64px;
}
.report > * { max-width: var(--measure); }
.report > h1, .report > .tablewrap, .report > table, .report > hr { max-width: none; }
.report h1 {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 2rem; line-height: 1.15; letter-spacing: -0.02em; font-weight: 600;
  margin: 0 0 calc(var(--u) * 0.75); padding: 0 0 calc(var(--u) * 0.5);
  border-bottom: 2px solid var(--line-strong);
}
.report h2 {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 1.3rem; line-height: 1.2; font-weight: 600; letter-spacing: -0.01em;
  margin: calc(var(--u) * 2) 0 calc(var(--u) * 0.5);
  padding-top: calc(var(--u) * 0.55); border-top: 1px solid var(--line);
}
.report h3 {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 1.05rem; line-height: 1.25; font-weight: 600;
  margin: calc(var(--u) * 1.4) 0 calc(var(--u) * 0.35);
}
.report h1 + p, .report h2 + p, .report h3 + p,
.report h2 + .tablewrap, .report h3 + .tablewrap { margin-top: 0; }
.report p { margin: 0 0 calc(var(--u) * 0.65); }
.report ul, .report ol { margin: 0 0 calc(var(--u) * 0.65); padding-left: 1.35em; }
.report li { margin: 0 0 calc(var(--u) * 0.3); }
.report li:last-child { margin-bottom: 0; }
.report li > p { margin-bottom: calc(var(--u) * 0.3); }
.report strong { font-weight: 700; }

.report .tablewrap {
  overflow-x: auto; -webkit-overflow-scrolling: touch;
  margin: calc(var(--u) * 1) 0 calc(var(--u) * 1.25);
}
.report .tablewrap:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.report table {
  border-collapse: collapse; width: 100%; border: 0;
  font-family: "Segoe UI", system-ui, -apple-system, Helvetica, Arial, sans-serif;
  font-size: 14px; line-height: 1.3;
  font-variant-numeric: lining-nums tabular-nums;
  font-feature-settings: "lnum" 1, "tnum" 1;
}
.report th, .report td {
  border: 0; border-bottom: 1px solid var(--line);
  padding: 9px 14px; text-align: left; vertical-align: top;
}
.report th:first-child, .report td:first-child { padding-left: 2px; }
.report th:last-child, .report td:last-child { padding-right: 2px; }
.report thead th {
  font-size: 12px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--muted); background: transparent; white-space: nowrap;
  vertical-align: bottom; border-bottom: 1.5px solid var(--line-strong);
}
.report tbody tr:last-child td { border-bottom: 0; }
.report td.num, .report th.num { text-align: right; white-space: nowrap; }
.report td.conv-green { color: var(--good); font-weight: 600; }
.report td.conv-yellow { color: var(--warn); font-weight: 600; }
.report td.conv-red { color: var(--bad); font-weight: 600; }
.report td.conv-unscored { color: var(--muted); font-style: italic; }

.report code {
  font-family: Consolas, "SF Mono", monospace; font-size: 0.9em;
  background: var(--raised); padding: 1px 5px; border-radius: 2px;
}
.report blockquote {
  border-left: 3px solid var(--line-strong); margin: 0 0 calc(var(--u) * 0.65);
  padding-left: 16px; color: var(--ink-2);
}
.report p.glance {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 15px; line-height: 1.5; color: var(--ink);
  background: var(--raised); border-left: 3px solid var(--accent);
  padding: 16px 20px; margin: 0 0 calc(var(--u) * 0.9);
}
.report p.disclaimer {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 13.5px; line-height: 1.5; color: var(--ink-2);
  border-top: 1px solid var(--line); padding-top: calc(var(--u) * 0.5);
  margin: calc(var(--u) * 0.9) 0 calc(var(--u) * 0.65);
}
.report .local-only {
  margin-top: calc(var(--u) * 2.5); padding-top: calc(var(--u) * 0.5);
  border-top: 1px solid var(--line);
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 13.5px; color: var(--muted); max-width: none;
}
.report .local-only a { color: var(--ink); }
@media (max-width: 640px) {
  .report { padding: 24px 16px 48px; font-size: 16px; }
  .report h1 { font-size: 1.6rem; }
  .report h2 { font-size: 1.2rem; }
  .report th, .report td { padding: 8px 10px; }
}
/* Printing keeps the page's own measure rather than running to the paper's
   edge, because a printed line is read the same way a screen line is.

   NOTHING IS HELD TOGETHER EXCEPT A ROW. `break-inside: avoid` on a table
   was tried on 2026-09-02 and reverted the same day: a table that will not
   fit in what is left of a page moves whole to the next one, and the reader
   gets a hand's width of blank paper above every table that happened to sit
   low. Repeating the header on each page is what makes a split table
   readable, and a split table beats a gapped one. A row is the one thing
   small enough that holding it together costs nothing. */
@media print {
  .report { max-width: none; padding: 0; font-size: 11pt; }
  .report > * { max-width: 68ch; }
  .report > h1, .report > .tablewrap, .report > table { max-width: none; }
  .report .local-only { display: none; }
  .report a { color: inherit; text-decoration: none; }
  .report h1, .report h2, .report h3 { break-after: avoid; }
  .report p { orphans: 3; widows: 3; }
  .report .tablewrap { overflow: visible; }
  .report thead { display: table-header-group; }
  .report tr { break-inside: avoid; }
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


_VAR_DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;{}]+)\s*;")
_VAR_USE_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*?)\s*)?\)")
_DARK_BLOCK_RE = re.compile(
    r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{.*?\n\}"
    r"|:root\[data-theme=\"dark\"\]\s*\{[^}]*\}", re.S)
_CALC_RE = re.compile(r"calc\(\s*(-?[\d.]+)([a-z%]*)\s*\*\s*(-?[\d.]+)\s*\)")


def flatten_variables(document: str) -> str:
    """Resolve every var() to its light theme literal, for a mail client.

    CSS custom properties reach under half of the mail clients caniemail
    tracks, and classic Outlook has none at all: there, every colour, every
    rule, every tint and every margin in this stylesheet resolves to nothing
    and the report arrives as unstyled text on white. The browser copy keeps
    the properties, because they are what makes one token set serve three
    renderers and two themes. The emailed copy gets them resolved.

    THE LIGHT VALUES WIN. The dark blocks are removed from consideration
    before anything is read, because a client that cannot read a custom
    property cannot read the dark media query either, and a dark token
    resolved into a light document is the one outcome worse than no token at
    all. Declarations themselves are left in place, so a client that does
    support them computes the same values.

    Multiplications by a constant are folded too, `calc(1.6rem * 2)` into
    `3.2rem`, because caniemail rates calc() no better than the properties
    this is here to remove and the spacing is most of the redesign.

    Deliberately small, and it never guesses: a var() whose name it cannot
    find is left exactly as it was, so anything this misses degrades to
    today's behaviour rather than to a wrong colour.
    """
    light = _DARK_BLOCK_RE.sub("", document)
    values: dict[str, str] = {}
    for name, value in _VAR_DECL_RE.findall(light):
        values.setdefault(name, value.strip())

    def resolve(match: re.Match[str]) -> str:
        name, fallback = match.group(1), match.group(2)
        if name in values:
            return values[name]
        return fallback if fallback else match.group(0)

    # Twice, so a token defined as another token resolves too. Not a loop:
    # one level of indirection is what this token set has, and an unbounded
    # loop over untrusted text is a hazard for no gain.
    out = _VAR_USE_RE.sub(resolve, _VAR_USE_RE.sub(resolve, document))

    def fold(match: re.Match[str]) -> str:
        size = float(match.group(1)) * float(match.group(3))
        return f"{size:.4g}{match.group(2)}"

    return _CALC_RE.sub(fold, out)


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
