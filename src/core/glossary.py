"""Plain English for every financial term the reports print.

THE ONE DEFINITION. Both reports draw their column legends and their glossary
from this module, so a term cannot be explained one way at 08:45 and another
way at 12:00. The same argument as analyst.banned_words: a definition with two
copies has two chances to drift and no way to notice.

WHO THIS IS FOR. The owner reads a gap and an RVOL without thinking. The people
the report gets forwarded to do not, and for them a table of Gap, RVOL, VWAP
and Sigma is a wall. The instruction was that the report be accessible to
somebody with no finance background, and that it may grow to get there.

TWO RULES THIS FOLLOWS, both learned from what went wrong elsewhere in the
project.

  NOTHING IS REMOVED. Every number and every technical header stays exactly
  where it was. A plain English line is added BESIDE it. Replacing "Premarket
  RVOL" with "how busy" would cost the owner the precision the column exists
  for, and would make the report worse for the person who reads it every
  morning in order to make it better for the person who reads it once.

  NO QUANTIFIER GOES NEAR A SET WORD. This text is rendered into the same
  report the quantifier guard scans, so a definition reading "every candidate"
  or "no name" would fail the morning it was written. The suite checks this
  module against analyst.quantifier_violations rather than trusting the author
  to remember.
"""

from __future__ import annotations

# term -> one or two sentences a reader with no finance background can follow.
# Ordered by how early a reader meets the term, not alphabetically, because
# the glossary is read top to bottom the first time and searched after that.
TERMS: tuple[tuple[str, str], ...] = (
    ("Premarket",
     "Trading that happens before the stock market officially opens at 9:30 in "
     "the morning, New York time. Far fewer people are trading then, so a price "
     "can move a long way on a small amount of money, and a premarket price is "
     "a weaker signal than the same price would be at midday."),
    ("Gap",
     "The difference between where a share price sits before the market opens "
     "and the price it finished at the day before. A gap up is higher than "
     "yesterday's finish and a gap down is lower. This system looks for shares "
     "that gapped because a large overnight move is often the start of a large "
     "day, in either direction."),
    ("Prior close",
     "The price a share finished at the last time the market closed. It is the "
     "number every move on this page is measured against."),
    ("Price",
     "The most recent price seen before the market opened. The time it was "
     "taken is printed beside it wherever it matters, because a premarket price "
     "can be minutes old."),
    ("Market cap",
     "What the whole company is worth at its current share price, roughly the "
     "price of one share multiplied by the number of shares that exist. Sizes "
     "on this page are written in billions. It is a rough guide to size: a 2 "
     "billion company and a 200 billion company behave very differently on "
     "the same piece of news."),
    ("Volume",
     "The number of shares that changed hands. On its own it says little, "
     "because a large company trades more shares than a small one on a quiet "
     "day."),
    ("Relative volume, RVOL",
     "How busy trading is compared with how busy this same share usually is at "
     "this same time of day. 1 is a normal amount of trading and 2 is twice the "
     "usual. This is the number that separates a share that is genuinely busy "
     "from one that is merely large."),
    ("VWAP",
     "The average price paid per share so far, counting larger trades more "
     "heavily than smaller ones. Traders treat a price above it as buyers "
     "having the upper hand and below it as sellers having it. It is a rule of "
     "thumb, not a rule."),
    ("Premarket high, premarket low",
     "The highest and the lowest price seen before the market opened."),
    ("Prior high",
     "The highest price reached during the last full trading day. A price above "
     "it means the share is already trading higher than at any point yesterday."),
    ("200 day average",
     "The average closing price over the last 200 trading days. A price above "
     "it is usually read as a longer term uptrend and below it as a downtrend. "
     "It moves slowly, so it says nothing about today on its own."),
    ("Catalyst",
     "A piece of news that might explain why a share is moving, such as a "
     "company reporting its profits or being taken over. The system reads this "
     "from tags the news provider attaches to a story, so a story about the "
     "wider market can sometimes be attached to a single company."),
    ("Score",
     "This system's own rating, from 0 to 10, of how many favourable conditions "
     "line up on one share at the same moment. **It is not a prediction and it "
     "has not been shown to work.** The thresholds behind it are starting guesses "
     "that are still being tested, and the project's own records currently show "
     "the highest scoring group performing worse than the lowest."),
    ("Conviction, green, yellow and red",
     "A word for the score band. Green is the top band, yellow the middle and "
     "red the bottom. Unscored means something the score needs was missing, "
     "which is different from scoring badly."),
    ("Day watchlist, swing watchlist",
     "Day means a share the rules would consider buying and selling within the "
     "same day. Swing means one they would consider holding for several days. "
     "The two have different tests, so a share can reach one list and not the "
     "other."),
    ("Sigma",
     "How unusual today's move is for this particular share, measured against "
     "how much it normally moves in a day. A 3 sigma move is far outside its "
     "usual range. It lets a 4 percent move in a calm share rank ahead of a 4 "
     "percent move in a wild one."),
    ("Entry, stop",
     "The entry is the price at which the rules would have started a position. "
     "The stop is the price at which they would have accepted the position was "
     "wrong and closed it, which is how a loss is kept to a known size."),
    ("Fill",
     "The price a position actually started at. It can differ from the entry, "
     "because a share that jumps straight past the intended price starts at "
     "wherever it was actually trading."),
    ("Trap",
     "A share that is rising while the news written about it is mostly "
     "negative. It is flagged because the rise and the reporting disagree."),
    ("Notable movers",
     "Large movers found by sweeping the whole market, listed whether or not "
     "they reached a watchlist. This section exists so a big move the screen "
     "passed over is still visible rather than silently absent."),
    ("Float rotation",
     "How much of a company's freely tradable stock changed hands. A high "
     "figure means an unusually large share of the available stock moved in a "
     "short time."),
)

# Table header -> the plain English line printed under that table. Keyed on the
# exact header text the reports already write, so a renamed column loses its
# legend loudly at the test rather than quietly in front of a reader.
COLUMNS: dict[str, str] = {
    "Ticker": "the short code that identifies the company",
    "Name": "the company's name",
    "Leg": "which sweep found it, premarket or the previous session",
    "As of": "the trading session the figures describe",
    "Gap %": "how far it moved overnight against yesterday's closing price",
    "Move %": "how far it moved, against the closing price named beside it",
    "Move": "how far it has moved today against yesterday's closing price",
    "Price": "the most recent price seen before the market opened",
    "Last": "the most recent price seen",
    "Prior close": "the price it finished at when the market last closed",
    "Prior high": "the highest price it reached during the last full day",
    "Mkt cap": "roughly what the whole company is worth, shown in billions",
    "Market cap": "roughly what the whole company is worth, shown in billions",
    "Catalyst": "the kind of news that may explain the move",
    "Top headline": "the most recent story the news provider tagged to it",
    "Premarket RVOL": "how busy trading is against this share's own normal, "
                      "where 1 is normal and 2 is twice normal",
    "Day RVOL": "how busy today's trading is against this share's own normal",
    "Premarket high": "the highest price seen before the market opened",
    "Premarket low": "the lowest price seen before the market opened",
    "Premarket VWAP": "the average price paid per share before the open, "
                      "weighted by trade size",
    "200d avg": "the average closing price over the last 200 trading days",
    "Score": "this system's own 0 to 10 rating, which is not a prediction",
    "Conviction": "the score's band: green is highest, red is lowest",
    "Sigma": "how unusual the move is for this particular share",
    "On watchlist": "whether the morning screen also selected it",
    "Price time": "the clock time the price was taken",
    "Price age s": "how many seconds old that price was when this was written",
    "Report date": "the date the company is due to report its profits",
    "Session": "whether that report lands before or after the market is open",
    "Morning entry": "the price the morning published as the intended entry",
    "Stop": "the price at which the rules would close the position for a loss",
    "What happened": "whether the intended entry price was ever reached",
    "Now vs fill": "where the price is now against the price it started at",
    "Best vs fill": "the best the position was worth against where it started",
    "Did the morning reach it": "whether the morning had this share on its list "
                               "and could price it",
    "Label": "the index, currency or commodity being tracked",
    "Change %": "how far it moved against its previous close",
    "Source": "where this figure came from",
}

HEADING = "What the words on this page mean"

# How a legend line opens. Named once so annotate_tables can recognise a
# legend it already wrote without matching on the whole sentence.
LEGEND_PREFIX = "Reading the columns: "

INTRO = (
    "This section explains the words used above, in ordinary language and with "
    "no finance background assumed. Nothing here is advice, and the thresholds "
    "this system screens on are starting guesses that have not been shown to "
    "work."
)


def legend(headers: list[str]) -> str | None:
    """One plain English line for a table, or None when nothing is known.

    Returned as a single sentence rather than a second table, because a legend
    laid out as a table is one more grid for the reader who is already lost in
    the first one.
    """
    parts = [f"{head} is {COLUMNS[head]}" for head in headers if head in COLUMNS]
    if not parts:
        return None
    return LEGEND_PREFIX + "; ".join(parts) + "."


def unexplained(headers: list[str]) -> list[str]:
    """Headers this module has no plain English for. The suite reads this."""
    return [head for head in headers if head not in COLUMNS]


def annotate_tables(report_text: str) -> str:
    """A plain English line under every table in a finished report.

    THE ONE IMPLEMENTATION, here rather than in either renderer, because the
    morning report and the midday report print several of the same columns and
    a walker with two copies has two chances to drift.

    Inserted AFTER the blank line that closes each table, never against the
    last row. Prose written straight after a row is parsed as one more row and
    collapses into a single first column cell, which is the 2026-09-01 glossary
    defect analyst.annotate_score_bands already carries the warning for.

    Idempotent: a table already followed by a legend is left alone, because the
    morning writes its report twice on the path where containment examined
    nothing and a legend appended twice reads as a stutter.
    """
    lines = report_text.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            out.append(lines[index])
            index += 1
            continue
        headers = [cell.strip()
                   for cell in lines[index].strip().strip("|").split("|")]
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            out.append(lines[index])
            index += 1
        while index < len(lines) and not lines[index].strip():
            out.append(lines[index])
            index += 1
        text = legend(headers)
        already = (index < len(lines)
                   and lines[index].startswith(LEGEND_PREFIX))
        if text and not already:
            out.append(text)
            out.append("")
    return "\n".join(out) + ("\n" if report_text.endswith("\n") else "")


def append_section(report_text: str, level: str = "##") -> str:
    """Append the glossary once, at the foot of a finished report."""
    if HEADING in report_text:
        return report_text
    body = "\n".join(section(level)).rstrip("\n")
    joiner = "" if report_text.endswith("\n") else "\n"
    return f"{report_text}{joiner}\n{body}\n"


def section(level: str = "##") -> list[str]:
    """The glossary, as markdown lines, ready to append to a report."""
    out = [f"{level} {HEADING}", "", INTRO, ""]
    for term, meaning in TERMS:
        out.append(f"**{term}.** {meaning}")
        out.append("")
    return out
