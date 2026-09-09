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


def bare_ticker(symbol: object) -> str:
    """The reader facing form of a symbol: ARX, never ARX.US.

    ONE DEFINITION, for the same reason every other name in this module has
    one. The vendor keys everything by exchange qualified symbol, and every
    surface a reader sees is supposed to strip it: prompt_analyst.md rule 8
    tells the model to write ARX and not ARX.US, analyst.fallback_report strips
    it when the model does not run at all, and scan's evidence roll strips it
    in the sentences the report quotes. The 12:00 report did not, because it
    has NO MODEL to instruct and nobody had written the strip for it, so it
    published AAOI.US, AXTI.US and eleven more where the 08:45 report published
    AAOI and AXTI. Two reports about the same picks, naming them differently.

    That is exactly the drift this module exists against, and the reason the
    strip belongs HERE rather than a fourth time in the midday renderer: a rule
    the morning obeys because a prompt says so and the midday obeys because
    somebody remembered is a rule with two chances to break.

    Split on the dot rather than removing a ".US" suffix, so a symbol on any
    other exchange loses its qualifier too. A symbol with no dot is returned
    unchanged, and so is an empty one.
    """
    return str(symbol or "").split(".")[0]


# The classes CRITERIA [Score catalyst class] names, in the words a reader
# uses. Only the ones an underscore or an acronym would mangle are listed; the
# rest fall through to in_words, which is why "earnings" and "guidance" are
# absent rather than repeated here.
_CLASS_WORDS: dict[str, str] = {
    "m_and_a": "merger or acquisition",
    "fda": "FDA decision",
    "analyst_action": "analyst action",
    "index_inclusion": "index inclusion",
}


def in_words(value: object) -> str:
    """An internal name as reader words: prior_session becomes prior session.

    THE ONE PLACE an underscore is taken out of a name a reader sees. Legs,
    lists and catalyst classes are written in snake case because Python reads
    them, and until 2026-09-03 several reached the page that way: the Notable
    movers table printed prior_session in its Leg column, the section's own
    accounting printed "The two_session leg examined", and a catalyst class
    printed as analyst_action. A report is not a dump of the packet, and a
    reader who has never opened packet.json cannot be expected to translate.

    ONLY THE UNDERSCORES GO. The words themselves stay the packet's own, so a
    reader who does open the packet still finds the field the sentence came
    from. A value with no underscore is returned unchanged, and so is an empty
    one, which is why this is safe to call on anything a cell might hold.
    """
    return str(value or "").replace("_", " ")


def catalyst_class(value: object) -> str:
    """One catalyst class in reader words, m_and_a as merger or acquisition."""
    text = str(value or "").strip()
    return _CLASS_WORDS.get(text.lower(), in_words(text))


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
    # REWRITTEN 2026-09-08, and this entry is why. It said the entry was
    # "the price at which the rules would have started a position" and the
    # stop was "how a loss is kept to a known size", which describes a trading
    # plan. No plan was ever measured: these are the premarket high and low,
    # and expressed in each share's own average daily range the distance
    # between them ran from 0.14 to 2.44 of it across one morning's ten names.
    # The words survive because pages already in the archive print them.
    ("Entry, stop",
     "Two prices worked out before the market opens: the highest and the "
     "lowest this share traded at beforehand. Nothing is bought or sold at "
     "either one. They are a measuring stick, so that every morning can be "
     "scored the same way, and not prices anyone was told to act on. How far "
     "apart they are depends on how much the share happened to move before "
     "the open, which is not a fact about the share."),
    ("Reference high, reference low",
     "The same two levels under the names now printed on the screens. The "
     "record needs a fixed level to measure each morning against; these are "
     "it, and nothing more is claimed for them."),
    ("Daily structure",
     "Where a share sits in its own recent history: the highest and lowest it "
     "has traded over the last month, quarter and year, its average price over "
     "50 and 200 days, and how much it moves in a normal day. It describes the "
     "ground the share is standing on. It recommends nothing, because nothing "
     "measured here would justify a recommendation."),
    # Added 2026-09-09 with the readings themselves. Each of these is a word a
    # card now prints, and the rule this module exists for is that a term a
    # reader meets on a page is explained on the same page rather than looked
    # up somewhere they do not have.
    ("Last closed above",
     "How long ago the share last finished a day above a level. A high on its "
     "own says only where a line is. Knowing the share has not closed above it "
     "since the spring says whether that line is somewhere it keeps failing or "
     "somewhere it has simply not been."),
    ("Range in average ranges",
     "How wide the last month has been, counted in days. A share that moves "
     "about a dollar a day and has spent the month inside a three dollar band "
     "is coiled; one that has covered fifteen dollars in the same month is "
     "stretched. Both can sit in the middle of their band and look identical "
     "without this."),
    ("Gap in context",
     "What the share was doing BEFORE it gapped, and where the gap sits in "
     "that. A jump out of a month of quiet and a jump on the fifth busy day in "
     "a row are different situations that look the same in a percentage. The "
     "readings that produced the label are printed beside it, so a reader who "
     "would call it something else can see why."),
    ("Short interest",
     "How many shares people have borrowed and sold, betting the price falls, "
     "as a share of the shares actually available to trade. It is published "
     "twice a month, so it describes a position taken up to three weeks ago. "
     "It is shown as context and nothing here is ranked or chosen on it."),
    ("Days to cover",
     "How many normal days of trading it would take for everybody betting "
     "against the share to buy back what they borrowed. A large number means "
     "those bets cannot be closed quickly."),
    ("Fill",
     "The price the notebook records a position as having started at. "
     "Nobody bought anything: it is a written down number. It can differ "
     "from the price being watched, because a share that jumps straight "
     "past that price starts at wherever it happened to be trading."),
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
    "Profit per share, reported against expected": "what the company actually "
                                                  "earned for each share it has "
                                                  "issued, beside what analysts "
                                                  "had expected it to earn. The "
                                                  "difference between the two "
                                                  "often moves the price more "
                                                  "than the figure itself",
    # ---- THE CARD'S EVIDENCE PANEL, renamed 2026-09-09 out of PREMARKET
    # RVOL, MOVE IN SIGMA and FLOAT ROTATION. The panel is a grid of divs
    # rather than a table, so none of these had ever been reachable through
    # the glossary either.
    "Trading against its own normal": "how many shares changed hands this "
                                      "morning against what is normal for this "
                                      "share at this hour. 1 is normal, 2 is "
                                      "twice normal. It is an estimate",
    "Size of the move for this share": "how big this morning's move is for this "
                                       "particular share, counted in its own "
                                       "usual daily swings. A 5 here means a "
                                       "move five times the size of an ordinary "
                                       "day for it, which is a different thing "
                                       "from a big move in percent",
    "Shares traded before the open": "roughly how many shares changed hands "
                                     "this morning before the market opened. An "
                                     "estimate: this system hears only part of "
                                     "what trades and scales up from it",
    "Share of the company traded": "what fraction of all the shares a company "
                                   "has available to trade changed hands this "
                                   "morning",
    "What the whole company is worth": "the price of one share multiplied by "
                                       "the number of shares there are",
    "Money traded on a normal day": "how many dollars of this share change "
                                    "hands on an ordinary day, averaged over "
                                    "the last 20 trading days",
    "News stories found": "how many news stories this system found about this "
                          "company in the hours it searched",
    "Where it ranked overnight": "this system sorts every name it finds "
                                 "overnight into groups by why it is "
                                 "interesting, and ranks within each group. "
                                 "This is where this name came in its own group",
    "Avg so far": "the average price this share has traded at this morning, "
                  "weighted so that a minute with a lot of trading counts for "
                  "more than a quiet one",
    # ---- THE DESK'S OWN HEADERS, added 2026-09-09. Wiring the glossary to the
    # screens reached 15 of the 66 fixed headers the desk draws; the other 51
    # were plain, which for a reader is the same as not having built it. These
    # are the ones a person who does not already know the answer would stop at.
    "Packet": "the file this system writes each morning holding every "
              "figure it gathered. Every screen is drawn from it, so a "
              "number on a screen can always be traced back to one",
    "Sessions": "trading days. Weekends and market holidays are not "
                "sessions, so twenty sessions is about a calendar month",
    "Distance": "how far the last price is from the price being watched, drawn "
                "as a bar. The right hand edge is that price, so a bar running "
                "the full width is a share trading at it",
    "To ref high": "how far the last price is, as a percentage, from the "
                   "highest price this share traded at before the market opened",
    "State": "what the share's price has done today against the two prices the "
             "notebook is watching. The words are spelled out under the table",
    "Got to that price": "how many of these names ever traded at the price "
                         "being watched. It counts the price being reached and "
                         "nothing about whether that was a good thing",
    "Price reached": "how many picks whose watched price the share actually got "
                     "to that day",
    "Best it offered": "the furthest the price got in your favour before the "
                       "day ended, which is not what the notebook records: that "
                       "is the closing price",
    "Minutes to the high": "how long after the opening bell the share reached "
                           "its best price of the day",
    "Peaked after": "how long after the opening bell the best price came",
    "Middle result": "the middle outcome of the group, so half did better and "
                     "half did worse. The middle is used rather than the "
                     "average because one enormous day would drag an average "
                     "and tell you about that one day instead of the group",
    "Middle day": "the middle day of the group, so half were better and half "
                  "were worse",
    "Middle day of the missed": "the middle one of the days where the share "
                                "never reached the price being watched",
    "Median morning": "the middle morning, so half were better and half worse",
    "Usual range": "how far this share moves on an ordinary day, top to bottom",
    "Volume against its own average": "how many shares changed hands today "
                                      "against what is normal for this share. 1 "
                                      "is normal and 2 is twice normal",
    "Times seen": "how many separate mornings this name has appeared",
    "Pool had it": "whether the name was in the list the overnight search built, "
                   "before any of the morning's tests were applied",
    "Turned down by": "which test the name failed, so it never reached the "
                      "watchlist",
    "Refused": "how many were turned away, and by what",
    "Never measured": "how many could not be judged at all, because a figure "
                      "they needed was missing",
    "Noon said": "what the midday check made of it, hours after the morning "
                 "published",
    "At noon": "where the price stood at the midday check",
    "Ranked on": "which figure the list was sorted by",
    "Condition": "one of the tests a name has to pass to reach a watchlist",
    "Screens": "which of the two lists it reached, the same day one or the "
               "longer held one",
    "Swing": "the longer held of the two lists, meant to be judged over days "
             "rather than within one",
    "Kind": "what sort of thing this row is",
    "Split": "a company dividing each share into several smaller ones. The "
             "price falls to match and nobody gains or loses, but a chart that "
             "has not been corrected for it shows a crash that never happened",
    "Gapped": "whether it opened away from where it finished the day before",
    "Largest gap": "the name that moved furthest overnight, in either direction",
    "Share of the list that": "what fraction of the names on the list did this",
    "Estimate": "what analysts expected the company to earn",
    "Actual": "what the company actually reported",
    "Forecast": "what the company says it expects next, which often moves the "
                "price more than the figure it just reported",
    "Release": "when the news came out",
    "When (ET)": "the time in New York, which is the clock this whole system "
                 "runs on",
    "Name": "the company's name",
    "Leg": "which search found it: the one before the market opened, or "
           "the one over the previous full trading day",
    "As of": "the trading day the figures describe",
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
    # THE SAME TWO NUMBERS THE PAPER LEDGER BOOKS AGAINST. Both come from
    # scan.reference_levels, which reads the field names out of CRITERIA
    # [Picks], so a reader comparing the report against the record is looking
    # at one number rather than two that happen to agree today.
    "Entry": "an old name for the higher of the two prices the notebook "
             "watches, the highest this share traded at before the market "
             "opened. Reports written from 2026-09-08 head this column "
             "Ref high",
    "Stop": "an old name for the lower of the two, the lowest this share "
            "traded at before the market opened. Reports written from "
            "2026-09-08 head this column Ref low",
    "200d avg": "the average closing price over the last 200 trading days",
    "Score": "this system's own 0 to 10 rating, which is not a prediction",
    "Conviction": "the score's band: green is highest, red is lowest",
    "Sigma": "how unusual the move is for this particular share",
    "On watchlist": "whether the morning screen also selected it",
    "Price time": "the clock time the price was taken",
    "Price age s": "how many seconds old that price was when this was written",
    # The Daily structure table in the report, added 2026-09-09.
    "Month": "where the price sits between the highest and lowest of the "
             "last 20 trading days",
    "Quarter": "the same over the last 60 trading days, about three months",
    "Year": "the same over the last 250 trading days, about one year",
    "Last close above the quarter high": "how long since the share last "
                                         "finished a day above the highest "
                                         "price of the last 60 days. It says "
                                         "whether that level is one the share "
                                         "keeps failing at or one it has "
                                         "simply not been near",
    # NOT "Range in ATR". ATR is AptarGroup on the NYSE, so that header put a
    # bare listed ticker into every report and into the legend generated
    # under it. The containment check reads a report the way a reader does,
    # saw a ticker the packet never carried, and correctly refused to deliver
    # the 2026-09-09 report. No abbreviation that is also a listed symbol
    # belongs in fixed report furniture.
    "Range in normal days": "how wide the last 20 days have been, counted in "
                            "normal days. A small number means the share has "
                            "been coiled, a large one that it has been "
                            "travelling",
    "Gap in context": "what the share was doing before today, and where this "
                      "gap sits in that",
    "Before today": "the shape of the last month: how wide it was and how far "
                    "it actually travelled, both counted in normal days",
    "Price against that range": "whether the price is above, inside or below "
                                "the band the last month was held in",
    "Its own past gaps": "how often this share has gapped before, and what it "
                         "typically did between the open and the close on "
                         "those days",
    "Average daily volume": "how many shares change hands on a normal day, and "
                            "how many days that average was taken over",
    "Short interest": "shares sold by people betting the price falls, as a "
                      "share of the shares available to trade",
    "Days to cover": "how many normal trading days it would take to buy back "
                     "every one of those bets",
    "Report date": "the date the company is due to report its profits",
    "Session": "whether that report lands before or after the market is open",
    "Morning entry": "the reference level the morning froze for the record",
    # The midday outcome table, reworded 2026-09-03. Its columns described a
    # trade that was never placed: What happened, Now vs fill, Best vs fill
    # and Stop state are the vocabulary of a position somebody holds. These
    # describe a price crossing a level, which is what is actually measured.
    # The old keys stay above and below because the archive still carries
    # pages that print them.
    "Entry reached": "whether the share's price ever got up to the level "
                     "set that morning, and when",
    "Reference reached": "whether the share's price ever got up to the "
                         "level set that morning, and when",
    "Against reference": "whether the share's price ever got up to the "
                         "level set that morning, and when",
    # THE DEFINITION HAD THE SAME PROBLEM AS THE COLUMN. "the two levels the
    # record books against" explains a term nobody knows with a phrase
    # nobody knows. A reader tapping this on the desk gets one sentence and
    # it has to land on its own.
    "Ref high": "the highest price this share traded at before the market "
                "opened. Nothing is bought or sold at it: it is one of two "
                "prices a paper notebook watches, so that every morning "
                "can be scored the same way",
    "Ref low": "the lowest price this share traded at before the market "
               "opened, the other of the two the notebook watches",
    "Start price": "the price a position would have begun at had somebody "
                   "acted on the level, which is not a price anybody paid",
    "Now vs start": "where the price is now against that start price",
    "Best vs start": "the best the price got against that start price",
    "Stop reached": "whether the price ever fell to the lower of the two "
                    "levels, and whether a day's high and low alone can "
                    "say when",
    # NOT a second "Stop". The midday table carried two columns both headed
    # Stop until 2026-09-02, the stop price and whether it was reached, and
    # this dict carried the key twice, so the second definition silently
    # replaced the first and the morning's Stop column was explained as the
    # midday's. A dict literal with a repeated key is legal Python and the
    # suite now refuses one here.
    "Stop state": "whether the price reached the lower level during the "
                  "day, and whether a daily figure can even tell",
    "What happened": "whether the reference level was ever reached",
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

# How the conviction band definition opens, written by analyst._bucket_legend
# under the first table carrying a Conviction column. Named here beside the
# column legend because the renderer removes both with the table they sit
# under when that table is the `none` row and nothing else: a legend for
# columns the page no longer shows is a paragraph explaining nothing.
BAND_LEGEND_PREFIX = "Conviction is a band on the score"

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

    ONE LEGEND PER SET OF COLUMNS PER PAGE. The midday report splits its
    graded rows into two tables of the same shape since 2026-09-03, the
    watchlist names and the names the screens turned down, and the same 300
    word legend under both is 300 words nobody reads twice. The second and any
    later copy is dropped; a legend for a DIFFERENT set of columns still gets
    its own line wherever its table stands.
    """
    lines = report_text.splitlines()
    out: list[str] = []
    said: set[str] = set()
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
        if already:
            said.add(lines[index])
        if text and not already and text not in said:
            said.add(text)
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
