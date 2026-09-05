# What "a name like this one" means

## Status

**Pre-registered. No base rate exists at the time this file was written.**

Pre-registered at: 2026-09-04, when `research_outcomes` did not exist as a
table, `data/backtest/` did not exist on this machine, and `picks` held 43 rows
across 4 sessions, every one of them `source='live'`. There is nothing here to
tune against. That is the point of the date on this line.

The package this belongs to is IMPROVEMENT_PLAN 5.7, and the engine it grades
is 5.4. This file must carry a date earlier than the first `research_outcomes`
row. `claim_the_precedent_screen_cannot_borrow_the_record` parses the
`Pre-registered at:` line and compares it against `MIN(computed_at)` from that
table, and fails when this file is not strictly earlier.

**Amended 2026-09-04, the same day and before a single outcome existed.** The
gap band was specified as a band of the signed gap, which put a name down 6.2
percent and a name up 3 percent in one group, both of them "under 4%". Condition
2 now bands the MAGNITUDE and carries the direction as a word, so "up 6% to 8%"
and "down 6% to 8%" can never collide. The reason is in section 4 and it is not
a refinement: this desk's entry is long only, a stop above the premarket high,
so a gap down name reaching it is a reversal and a gap up name reaching it is a
continuation, and one number over both answers neither. It was found by
comparing what the engine writes against what the screen recomputes, while the
session cache was still being fetched and `research_outcomes` was still an empty
table. An amendment made before the numbers are in is still a pre-registration;
one made after is a rationalisation, and the only thing separating them is this
paragraph and the commit that carries it.

**Amended 2026-09-05, and this one is not clean, so the ordering is written
out rather than summarised.** Six further sections were built that night, and
before the amendment was typed the engine had already graded ONE pilot session,
2026-05-19, 84 rows, to prove the plumbing ran end to end. So the sequence was:
sections designed, engine written, one session graded, its numbers seen, this
amendment written, then the year graded. What was seen in the pilot: 2 of 42
names cleared the day screen, `require_above_prior_high` was in almost every
refusal, and 4 names that the noon fold called "never triggered" reached the
buy by the close. Those are the plumbing working, and they are also numbers,
and a reader is entitled to know they were visible before section 11 below was
fixed. The pilot rows were deleted before the year was graded. What would make
this a rationalisation rather than a pre-registration is choosing a measure
because the pilot flattered it; what protects against that is that section 11
specifies every measure as a COUNT of a state the shipped rule already names,
with no threshold chosen here at all.

**Amended 2026-09-05: the population was stated too narrowly and is corrected
here.** Section 2 said `research_outcomes` rows, which is right, and the
matcher briefly read that as the rows whose `day_eligible` is 1. That is a
different population from the one the screen sits beside. The morning list is
the RANKED candidates, published with an entry and a stop whether or not they
cleared the day screen, and on the four live sessions on file only 0, 0, 3 and
2 of twelve cleared it. Matching today's mostly refused names against a history
of only cleared ones asks the past about a different kind of name. The base
rate is therefore over every replayed candidate the reconstructed screen
priced, and the day screen's verdict is a column that sections read, never a
filter on the count. Caught before any figure was drawn from it.

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
                      as paper_ledger's own docstring says. The vendor
                      publishes a minute bar only for a minute that traded, so
                      on a thin name this UNDERSTATES elapsed time and is exact
                      on any name that trades every minute. The screen prints
                      it as minutes, because that is what a reader
                      understands, and this paragraph is where the caveat
                      lives rather than in a column heading nobody can fit it
                      into.

The middle result is the MEDIAN of `pnl_pct` over booked rows, never the mean.
One name that doubled would carry a group that otherwise lost money.

## 4. The match rule, fixed here

Six conditions, applied as a conjunction. A past row matches only if it
satisfies every condition that has not been dropped by section 5.

  1. earnings overnight   exact boolean match.
  2. gap band             both rows fall in the same band of
                          [Precedent] gap_band_edges AND gapped the same way.
                          The edges are MAGNITUDES and the direction is a word
                          in front of the band, so "up 6% to 8%" and "down 6%
                          to 8%" are two groups and never one. Long only entry:
                          a gap down name reaching a stop above the premarket
                          high is a reversal, a gap up name reaching it is a
                          continuation, and one figure over both is a figure
                          about neither.
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

**The market value is today's, not the session's.** `cap_band` is cut from
`gap_stats`' market cap for the name as the universe last recorded it, which is
the vintage `replay_session` already notes per session. A name that was a 400M
company during the replayed year and is a 3B company now is banded as the
second. It biases the large bands toward names that grew, which is the same
direction as the survivorship bias below and compounds with it.

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

## 11. The six further sections, specified 2026-09-05

Each one mirrors a section the Morning screen already draws. None of them adds
a threshold: every figure is a COUNT of a state the shipped rule already names,
and every one is withheld under the same `min_rows` and `min_sessions` floors
in section 6. They are specified here so the measures cannot be chosen later
from whichever cut reads best.

**What each floor turned down.** Population: every replayed candidate whose
`day_eligible` is not null. For each condition key `scan.evaluate_eligibility`
records, the count it refused, the distinct sessions, the subset whose input
was never measured, and what those refusals went on to do under the paper rule.
The counts OVERLAP by construction, because a name can fail two conditions, and
the screen says so. `require_fresh_price` can never fire in a replay because no
collector ran, and it is reported as unevaluated, never as a floor that turned
nobody down.

**Whether thin evidence has cost anything.** Three splits, each drawn as a
PAIR so neither side is a number without a scale: a baseline resting on fewer
than `[Baseline] min_sessions_for_rvol` sessions against one that is not, a
null premarket RVOL against a measured one, and a premarket window of one
minute or none against more than one. A row whose input cannot answer the
question joins neither side. The roll's other six sentences cannot be rebuilt
from a replayed session and the screen names them rather than dropping them.

**What the desk missed.** Population: every name that cleared a replayed
session's own gap floor, from `research_daily`, which is the daily bar and NOT
a simulated trade. Per gap band: how many gapped, how many the pool subscribed,
and what the rest did open to close and open to high. Rows on sessions the
replay has not screened carry `subscribed` null and are excluded, because there
"not subscribed" is unknown rather than false.

**How these events have resolved before.** Population: every name discover
tiered as an overnight reporter, again from the daily bar. Split by tier and by
whether the vendor's actual beat its own estimate. A row with no estimate is on
neither side of that split rather than counted as a miss.

**What kind of morning this is.** A session level comparison, not a name level
one: for each of four measures the share of a morning's list that answers yes,
today's against the median and the tenth to ninetieth of every replayed
morning. It is NARROWER than the Morning section it mirrors and says so.
Sector is on no disk for a replayed session and catalyst class needs the per
article news tags the session cache does not hold, so two of that section's
three panels cannot be rebuilt at any price.

**What noon has graded before.** The same cached minutes the simulation reads,
folded to `[Midday] run_time` and handed to `midday.scan_midday.grade` itself
rather than a copy of it. Per noon state: the count, the sessions, how many
reached the buy by the close, and the spread. The figure the section exists for
is the disagreement between the two, and no threshold is set on it here.

**A confound these six add, written down now.** The two daily bar sections
measure open to close, and the trade sections measure a simulated entry to a
simulated exit. They are different instruments and a reader must not compare a
number from one against a number from the other. Every daily bar figure on the
screen carries that sentence beside it.

**A confound the whole replay adds, written down now.** The `gap_stats`
windows that rank the replayed pool were BACKFILLED on 2026-09-05, 51 of them
at a weekly cadence chosen to mirror the production Sunday rebuild, not the
windows that existed at the time. Each replayed session still reads only a
window dated strictly before it, so no session is ranked on its own outcome,
but the cadence is a reconstruction and the universe those windows were
computed over is today's. A name delisted during the year is in none of them.

## 12. The first falsifier reading, 2026-09-05

Section 9 named three things that would make this wrong. The replay finished at
240 sessions and 9,500 graded rows under one rule version, which is the fence
the screen reads through, so two of the three can now be read. Nothing in
sections 4, 5 or 6 was changed to produce these numbers, and
`research.falsifier_reading` recomputes every one of them by calling
`desk.precedent.match` once per replayed candidate, so the figures below and
the shipped ladder cannot drift apart silently.

**The widening ladder fires on 41 percent of candidates. NOT tripped.** Pooled
over the replay, 41 percent need at least one condition dropped. The median
morning is 39 percent. Counted a morning at a time, 64 of the 240 are strictly
over half. Section 9's bar is half and all three readings sit under it. Where
the ladder settles: 5,634 candidates match on the full conjunction, 1,391 after
one drop, 1,517 after two, 203 after three, 721 after four, and 34 are withheld
with the ladder exhausted.

**The reading depends on how an unmeasured condition is treated, and this is
the number to be careful with.** 1,685 of the 9,500, 18 percent, carry no
premarket RVOL band, because the name was never subscribed or the window held
no bars. `_select` drops an unmeasured condition from the conjunction rather
than comparing it to NULL, which would match nothing and empty the group. So
those candidates are matched on five conditions and land in a group wide enough
to clear the floors without the ladder. Counted the other way, treating an
unmeasured condition as a failure to match, the same population reads 54
percent pooled, 58 percent on the median morning and 135 of 240 mornings, and
the falsifier trips on all three. The first reading is the one that stands
because it is what the shipped code does; the second is recorded here so that
nobody recomputing this later finds 54 and concludes the page is lying.

**Fewer than a third clearing the floors at all: NOT tripped.** 34 candidates
in 9,500 are refused with the ladder exhausted, so better than 99 in 100 reach
a printable group.

**The reached-entry comparison: not readable.** It needs the live record at 200
booked trades and the live record holds 43. It stays unread, and of the three
it is the one that can still overturn the screen rather than its bands.

**No band edge moves.** Section 9's remedy is conditional on the trip and the
trip did not happen. The edges stay as CRITERIA describes them, which is seeds
chosen against no data, awaiting the measured sweep that note already promises.
A falsifier that did not fire is not evidence that the seeds are right.

**A gap between section 5's promise and the code, found while reading this and
closed the same day.** Section 5 says every widened group is labelled widened
on the screen, every time, naming the dropped conditions. A condition dropped
for being unmeasured was not labelled: `match` returns an empty `widened` list
for it, because the ladder never ran. The printed rule was not wrong, `in_words`
omits the condition it could not apply, so the reader saw a rule with no volume
clause rather than a false one. But a group matched on five conditions and a
group matched on six were drawn alike, and on 18 percent of candidates that is
the difference between them. `match` now returns `unmeasured` beside `widened`
and the row says which condition the group ignores. This is a disclosure and
not a rule change: no edge, no floor, no ladder order and no condition moved,
and the counts on the screen are the same counts. Section 10 governs the rule,
and adding a sentence about what the rule could not apply is not an amendment
to it.
