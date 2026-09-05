# What "a name like this one" means

## Status

**Pre-registered. No base rate exists at the time this file was written.**

Pre-registered at: 2026-09-04, when `research_outcomes` did not exist as a
table, `data/backtest/` did not exist on this machine, and `picks` held 43 rows
across 4 sessions, every one of them `source='live'`. There is nothing here to
tune against. That is the point of the date on this line.

The package this belongs to is IMPROVEMENT_PLAN 5.7, and the engine it grades
is 5.4. This file must carry a date earlier than the first `research_outcomes`
row, and a claim in the suite checks that it does.

## Why a pre-registration and not just code

The Precedent screen prints, next to a name the desk published this morning,
what happened the last time names like it appeared. Everything rests on what
"like it" means. Loosen the definition and the count is a market average
wearing a name's label. Tighten it and the count is four rows of noise. Both
failures are invisible in the output: the screen prints a confident number
either way.

The failure this file exists to prevent is narrower and worse than either. It
is choosing the bands AFTER seeing which bands make the desk look good. That
process has a name and it is not measurement. So the bands are fixed here,
before the engine has produced a single outcome, and changing one after results
exist requires an amendment on this page that says what changed, when, and what
the old rule produced.

## 1. The question

For a candidate the morning published, with a known gap, premarket RVOL, price,
market value, prior high relation and earnings flag: among past candidates
matching it on the rule below, what fraction reached the entry the report
named, and how did the ones that did end the session?

It is a count of the past. It is not a forecast, it carries no confidence
interval, and nothing on the screen may phrase it as a prediction.

## 2. The population

`research_outcomes` rows only, which are keyed to `picks` rows carrying
`source='reconstructed'`. Live rows are NEVER pooled in.

The reason is not purity. The live record is 43 rows over 4 sessions, all of
them after the 2026-09-01 history floor, and 2 of those 4 sessions ran the two
phase collector while 2 did not. Mixing 43 rows measured one way into a count
that claims to describe a year would corrupt the year and tell the reader
nothing about the 43. The Record screen is where live rows are read, and it
stays the only place.

## 3. The outcome, defined once

Every outcome comes from `night/paper_ledger.simulate` on the candidate's OWN
session, sizing mode v1 (fixed notional), against Alpaca one minute regular
session bars for that session. The function is imported, not reimplemented, so
that a base rate and the live ledger are the same instrument. If the ledger's
rule changes, both move together and the version travels on the row.

Four quantities are printed and no others:

  reached the entry   `booked = 1` from simulate. The session's tape reached
                      `entry_ref` while a resting stop order would have been
                      live. A candidate that never reached it was never bought
                      and is counted in the denominator, never in the result.
  how it ended        `pnl_pct`, entry to exit, where exit is the stop if it
                      was reached and the session close otherwise. Never a
                      target: the rule has none, on purpose.
  how many finished up  the count of booked rows with `pnl_pct > 0`.
  minutes to the peak `minutes_to_peak`, a BAR COUNT and not a clock reading,
                      as paper_ledger's own docstring says. On a thin name it
                      understates elapsed time. The screen must say "bars"
                      nowhere and must not imply a stopwatch.

The middle result is the MEDIAN of `pnl_pct` over booked rows, never the mean.
One name that doubled would carry a group that otherwise lost money.

## 4. The match rule, fixed here

Six conditions, applied as a conjunction. A past row matches only if it
satisfies every condition that has not been dropped by section 5.

  1. earnings overnight   exact boolean match.
  2. gap band             both rows fall in the same band of
                          [Precedent] gap_band_edges.
  3. premarket RVOL band  same band of rvol_band_edges.
  4. above prior high     exact boolean match.
  5. price band           same band of price_band_edges.
  6. market value band    same band of cap_band_edges.

The band edges live in CRITERIA `[Precedent]` and nowhere else.

**Catalyst class is deliberately absent, and this is the largest known
weakness of the rule.** `replay_session` leaves `score` and `catalyst_class`
NULL for a reconstructed row, because the class needs EODHD news TAGS per
article and the session cache stores only a newest title and timestamp. What
IS reconstructible is whether the name reported after the prior close, from the
session cache's earnings list, and that single boolean is condition 1. So a
takeover and a drug approval with the same gap, RVOL, price and size are one
group under this rule. Every screen that prints a count from it must be
readable as saying so, and `match_note` on the row carries the words.

The alternative, waiting for a class the cache cannot produce, is not a rule
that is more careful. It is no rule.

## 5. The widening ladder, fixed here

If a group holds fewer rows than `[Precedent] min_rows` or fewer distinct
sessions than `min_sessions`, conditions are dropped ONE AT A TIME in this
exact order, re-counting after each drop, stopping at the first count that
clears both floors:

  1. market value band
  2. price band
  3. above prior high
  4. premarket RVOL band

Earnings overnight and the gap band are never dropped. If the count still does
not clear both floors after step 4, the group is WITHHELD and the screen prints
that it is, naming the count it reached.

Order is by how weakly each condition is believed to matter, from a source that
predates this file: SCORE_INVERSION's first fifty rows and the live record's
own bucket, which is earnings versus none. It is a guess, and it is a guess
written down before the results rather than after.

Every widened group is labelled widened on the screen, every time, naming the
dropped conditions. A widened count is weaker evidence and the reader is never
left to infer that from a footnote.

## 6. The floors

`min_rows` and `min_sessions` are both required, and sessions is the one that
matters. Twelve names published on one morning share that morning's market and
are one observation, not twelve. A group of 200 rows drawn from 9 mornings is
9 observations with a large label on it.

The values are in CRITERIA. They are SEED. They were chosen before any data
existed and the sweep that would set them properly is IMPROVEMENT_PLAN 5.4's
threshold sweep, whose output is a document and not a screen.

## 7. What is printed and what is withheld

A group clearing both floors prints: rows, distinct sessions, reached count and
percentage, median `pnl_pct`, count finishing up, the 25th and 75th percentiles
and the extremes for the spread bar, and median `minutes_to_peak`.

A group under either floor prints the words that it is too few to say anything,
the row count it reached, and nothing else. No median, no bar, no percentage.
A withheld group is a result and is displayed as one.

## 8. Known confounds, written down now

**The market.** Every count here is unconditioned on what the market did that
day. A band whose rows happen to fall on trending days will read well. The
screen's "what kind of morning this is" section is a partial answer and not a
control.

**Survivorship in the universe.** `data/universe.json` is today's universe. A
name delisted during the replayed year is absent from it, so the past the
engine reconstructs is a past with the worst outcomes removed. This biases
every base rate UP and there is no cheap fix. It must be stated on the screen.

**The reconstructed screen is not the live screen.** `swing_eligible`, `score`
and `conviction` are NULL for reconstructed rows. The Precedent screen may not
group by score or conviction, because those columns do not exist in its
population. Only the Record screen may, on live rows.

**The capture rate.** Live premarket RVOL comes from a socket hearing about
11.72 percent of the consolidated tape (CRITERIA [Collector]
premarket_capture_rate). The replay's RVOL comes from Alpaca SIP, which is the
whole tape. So today's RVOL and a reconstructed RVOL are not the same
measurement, and condition 3 matches a socket number against a SIP number.
This is the same mismatch DECISIONS 2026-08-17 seventh records for the float
rotation edges. It is not fixed here and it is the second largest weakness of
the rule after the missing catalyst class.

**The history floor.** CRITERIA [Retention] history_from cuts the live record
at 2026-09-01. It does not apply to reconstructed rows, which describe
sessions long before it. A reader could take a base rate over 248 mornings as
evidence about a desk that has run four. The screen says which population each
number came from, on every section.

## 9. What would make this wrong

Stated now so it cannot be argued about later.

  - If the widening ladder fires on more than half of a morning's candidates,
    the bands are too tight and the rule needs re-cutting, not the data.
  - If fewer than a third of a morning's candidates clear the floors at all,
    the screen is not worth its tab.
  - If the median reached-entry rate across all groups differs by more than
    ten points from the live record's own rate once the live record passes 200
    booked trades, the reconstruction is not reproducing the live screen and
    every number on the screen is suspect.

## 10. What must not happen after results exist

  - No band edge moves without an amendment on this page, dated, saying what
    the old edge produced.
  - The ladder order does not change to make a group qualify.
  - `min_rows` and `min_sessions` do not fall to admit a group somebody wanted
    to see.
  - No condition is added to the conjunction. Adding one after the fact is
    choosing a subgroup by its answer.
  - The engine is never re-run with a changed question over the same bytes and
    the old result quietly dropped. Both runs stay.
