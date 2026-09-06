# Pre-registration: the Alpaca premarket sweep as a fifth discovery prior

Written 2026-09-06, BEFORE the evaluation was run and before one number from
it existed. Package 5.5 in doc/IMPROVEMENT_PLAN.md asks for exactly this and
says to pre-register the ranking rule and the bar first. This file is that,
and it is committed before the evaluate step runs so the order is checkable in
the history rather than asserted here.

## The question, and the one it is not

Discovery picks the pool from four priors that all describe the PAST: who
reports today, what was in the news overnight, who moved yesterday, who ran
recently. None of them looks at what is happening this morning, because no
EODHD endpoint on this plan serves the whole universe's premarket before the
open, and reading one that only looked current is what ranked yesterday's
movers every morning until 2026-08-14.

Alpaca does serve it, for a session that is over. So the question is whether a
sweep of the universe's own premarket tape, taken at 07:00 and available to
the 07:15 pass, finds big gappers the four priors miss.

THE QUESTION THIS DOES NOT ANSWER is whether to ship it. That is package 5.6
item 4 and it is the owner's, because it bends hard rule 1: EODHD is the only
vendor in the published path. A win here is evidence for that decision and is
not the decision. Nothing in this study writes to picks, to the watchlist, or
to any published path.

## The population

All 240 replayed sessions in data/backtest/sessions, 2025-08-29 to 2026-08-13.
Not the live sessions: there are four of those, and package 5.5 was written
when it expected nine. A bar reading "beats on seven of nine" cannot be
evaluated on four, and 240 sessions with known outcomes is the stronger test
in any case.

Each session carries `prior_closes` for about 2,648 universe symbols as the
universe stood THAT WEEK, and `outcome.gappers` measured at that session's
open. Both are already cached and cost no vendor call. Using today's universe
against a 2025 session is the circular measurement this project has already
made once, and the per session file is what avoids it.

## The rule, fixed here before it was run

For session D, Alpaca SIP one minute bars, 04:00 to 07:00 ET, adjustment raw:

  premarket_last    the close of the last bar in the window
  premarket_volume  the sum of bar volume across the window
  premarket_dollars premarket_volume times premarket_last
  gap_pct           (premarket_last - prior_close) / prior_close * 100,
                    against that session's own cached prior_closes

A symbol is ELIGIBLE when it has at least one bar in the window and
premarket_dollars is at or above the floor. Eligible symbols are ranked by
absolute gap_pct, descending, ties broken by symbol so the order is total.

THE FLOOR IS PRE-REGISTERED AT 50,000 DOLLARS. Below that a gap is one or two
prints and the price is not a price, which is the same argument the day
setup's three dollar price floor already makes. 10,000 and 250,000 are
declared HERE as sensitivity checks and will be reported beside the primary,
so a floor chosen after seeing the answer cannot be presented as the one that
was chosen before.

## What it is measured against

The shipped configuration on the same sessions, the same gappers and the same
corporate action refusal: ordering SHIPPED, tier floor 4, cap 45, scored by
`subscribed_recall_big` per session, which is recall of gappers at or past
[Discovery] recall_big_gap_pct = 8 among the names the pool subscribed.

Three arms, and the third is the proposal:

  A   Alpaca sweep alone, top 45 by absolute gap
  B   the shipped pool, top 45            THE BASELINE
  C   the union, taking the shipped pool's top 45 less K and the Alpaca
      sweep's top K that the shipped pool does not already hold  PRIMARY

K IS PRE-REGISTERED AT 10, a little under a quarter of the cap, with 5 and 20
declared here as sensitivities. K is a cost: every slot the sweep takes is a
slot the four priors do not get, which is what makes C the honest arm and A
the informative extreme rather than a proposal.

## The bar, fixed here before it was run

C beats B when BOTH hold over the 240 sessions:

  1. mean subscribed_recall_big is higher for C, on a paired t test across
     sessions at p below 0.05
  2. C is at least as good as B on more sessions than it is worse, on a sign
     test at p below 0.05

Two tests because either alone has a hole. A mean can be carried by a handful
of sessions where the sweep caught something enormous, and a session count can
be carried by many trivial wins against a few large losses. A result that
passes one and fails the other is reported as a split and is NOT a pass.

FAILING THE BAR IS A RESULT AND WILL BE WRITTEN UP THE SAME WAY. The value of
running this is the same in both directions: it converts 5.6 item 4 from a
judgement with nothing under it into a decision with a number under it.

## What would make the result void

  - Alpaca serving materially less premarket history for older sessions than
    newer ones, which would confound the arms with the calendar. The fetch
    records per session how many symbols came back with at least one bar and
    the evaluation refuses any session where that count is under 100.
  - A gap computed against a prior close from a different adjustment basis
    than the bars. Bars are fetched raw and prior_closes are the vendor's own
    for that session, so a split between the two dates would show as an
    enormous gap on both arms; corporate actions are refused by the same
    `refuse_corporate_actions` the shipped measurement uses.
