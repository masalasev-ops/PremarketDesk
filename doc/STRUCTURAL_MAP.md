# The structural map: what it measures, where it is written, what it cannot say

Written 2026-09-09, when the daily context map stopped being a panel on a card
and became typed columns on `picks`. The map itself landed the evening before
(CHANGELOG ninety fifth, DECISIONS twentieth) and this note covers what was
added on top of it: the columns, the backfill over the whole record, the gap
context readings, the two base items that were missing, and the float and short
interest context.

BUILD_PLAN.md carries one line pointing here. Every threshold named below is in
CRITERIA.md `[Daily structure]` or `[Short interest]` and nowhere else.

## Why columns, and why the backfill is the point

The map as shipped was display only. It was computed at 08:45, drawn on a card,
and written to nothing. That made it a decoration rather than an instrument:

- The ledger could never book a rule against a structural level, because no row
  recorded one.
- No query could ask whether a name that gapped out of a sixty session base
  behaved differently from one that gapped inside a broken one, because no row
  said which of those it was.
- The map could not get better over time, which was the whole argument for
  building it instead of publishing a level.

So every reading is a typed column on `picks`, declared in
`store._PICKS_LATER_COLUMNS`, and every session already in the record is filled
by `night/backfill_structure.py`. A JSON blob would have stored the same bytes
and answered none of those questions: the ledger filters and groups on these,
and SQLite cannot index inside a string.

**Named by role, not by session count.** `ds_high_medium`, never `ds_high_60`.
The counts are CRITERIA knobs. A column named for one starts lying the day it
moves, while every historical row keeps the old meaning and nothing says so.
Each row carries the window it was actually measured over beside the level it
produced, which is the `fill_band_pct` precedent: a row says what it was
measured by rather than inheriting whatever the file says today.

**One flattener.** `morning/structure.py columns()` builds the column
dictionary, and both writers call it: `scan.write_picks` for the live morning
and the backfill for everything else. Two flatteners would eventually disagree
about what `ds_pos_medium` means, and a column whose meaning depends on which
pass wrote it cannot be grouped on. `claim_the_map_columns_are_one_list`
asserts the two, and that the table declares exactly what the flattener emits.

## Where it is drawn

The desk card, and only the desk card. The emailed report has never carried the
map and still does not; it is a panel on `site/PremarketDesk.html` under
`#/session/<date>/`.

A session whose packet predates the map, which is every session on file before
2026-09-08, has the map on its `picks` rows anyway, and `desk/compact.py` reads
it from there. That is the ONE value on the desk not copied out of the packet,
named as one in that file's opening argument. The packet wins wherever it has a
map, so the fallback only ever fills a blank, and the card labels what it filled
with the date it was measured. `structure.block_from_columns()` is the inverse
of `columns()` and lives beside it, so the round trip through 67 columns has one
opinion about what a field means rather than two;
`claim_a_stored_map_draws_the_same_card` requires the payload out of the record
to be identical to the payload out of a packet.

## The trap, and how it is held shut

A level for a past session must be computed from bars dated up to THAT session
only. This is the one way the backfill could have corrupted the record in
silence:

- A sixty session high that has seen the following month knows where the name
  actually went.
- A base that broke is no longer a base.
- A range position measured through the move is a position inside the answer.

Every one of those numbers still looks entirely plausible in the column,
because the arithmetic is right and only the inputs are from the future.
Nothing downstream could catch it, because there is nothing to catch.

Three things hold it shut:

1. `rows_for_symbol()` takes the whole fetched series and slices it by each
   row's own date itself, so the slicing cannot be forgotten at a call site.
2. The mapped session's OWN bar is excluded, not merely the ones after it. It
   carries the high and low of the day the row is about, and a map including it
   would let the session explain itself.
3. `claim_a_backfilled_level_cannot_see_its_own_future` hands the function the
   whole series and one truncated at the row's date and fails if a single
   column moves. It also measures the same window WITHOUT the slice and
   requires that to differ, so a run in which the guard is doing nothing fails
   rather than reassures.

**Which money the levels are in.** The vendor computes `adjusted_close` against
its own latest data, so a series fetched today states every old bar in today's
money. That is right for the morning, whose price is also today's. It is wrong
for a row dated last November, whose `pm_high` and `prior_close` are in last
November's money: a split since then would leave one row carrying two scales
with nothing saying so. The backfill passes the adjustment factor of the mapped
session's own bar as `basis_factor`, which restates the slice in that session's
money. Reading that one bar is not a look into the future: it answers what the
session's prices were quoted in, which is the same question the `pm_high` on
the row already answers. `ds_basis_factor` records what was used.

**What the backfill does not touch.** The `source` column. live, test and
reconstructed rows are computed identically, because a pass that measured them
differently would make every aggregate that mixes them a lie and every
aggregate that does not a comparison of two instruments. No aggregate may mix
them anyway; see CRITERIA `[Picks]`.

**Too little history gives a null and a reason.** A row from the first weeks of
the reconstructed record has a few sessions behind it, draws the short window
and nothing else, and says so in `ds_short_reason`. Never a zero.

## What it costs

One `eod` call per DISTINCT symbol, not per row. The record holds 10,133 rows
over 1,590 names, so the whole backfill is about 1,590 credits against a shared
daily 100,000. CRITERIA `[Quota costs]` prices `eod` at one credit FLAT PER
CALL: the from date changes the size of the payload and not the price of it.

The series is cached gzipped under `data/backtest/structure-eod`, keyed by
symbol and recording the window it was fetched over, so a re-run after a fix
costs nothing. That is the split `research/backtest_pool.py` was built around,
for the same reason: a harness that refetched while it measured would make
every comparison a measurement of two different things.

`[Daily structure] history_calendar_days` widened from 400 to 1,100 on the same
argument. It costs nothing and it is what makes `ds_since_above_*` answerable
at all; see below.

## The readings that were added

### Sessions since the last close above each window high

`ds_since_above_short`, `_medium`, `_long`, each with its date.

A level on its own says only where a line is. "60 session high 54.20, last
closed above it 118 sessions ago" says the name has been under it for half a
year. "No close above it in the 760 sessions on file" says something stronger
again. The card could print neither.

**The arithmetic has a floor and a reader should know it.** The level is the
highest HIGH over the last N sessions, and a close never exceeds its own bar's
high, so no session inside that window can close above it. The answer is
therefore never smaller than N. A name that has just made a new high comes back
with NO answer rather than with a zero, which is the strongest of the three
readings and the one a zero would destroy.

This is also why the fetch window widened. Over 400 calendar days the 250
session answer had thirty sessions to search in and was null on almost every
name.

### Average daily volume, with its denominator

`ds_avg_volume`, `ds_avg_volume_sessions`, `ds_avg_volume_of`.

The count travels with the mean for the reason `avg_volume_20d` carries one: a
field named for twenty sessions that averaged three asserts a denominator it
does not have, and nothing downstream can tell.

Volume is NOT back adjusted. A share count is not a price, and the correction
that makes a pre split high comparable to today makes a pre split volume wrong
by the same factor in the other direction. A split inside the window is
disclosed by `ds_adjustment_steps` like every other one.

### The consolidation ratio

`ds_consolidation_ratio`: the twenty session range divided by ATR(14).

A coiled name and an extended name are different objects, and nothing on the
card distinguished them: both show a position inside a range and neither says
whether that range is three days wide or thirty. Two names can sit at the same
`position_pct` inside ranges four apart.

Crabel's 1990 work on narrow range days, which found a compressed range
precedes a large trending session about two thirds of the time, is why a coiled
name is worth separating at all. It is not why the consolidation line sits at
3: that is a SEED, and the reading it is taken against is on every row so it
can be moved over the record rather than re-argued.

### The gap context

`ds_gap_type` plus its inputs: `ds_regime`, `ds_regime_sessions`,
`ds_regime_direction`, `ds_regime_range_pct`, `ds_regime_range_atr`,
`ds_regime_net_move_pct`, `ds_regime_net_move_atr`, `ds_gap_vs_regime`,
`ds_gap_direction`, `ds_gap_threshold_pct`, `ds_gap_type_why`.

A gap out of a four week base and a gap on the fifth straight up session are
opposite objects, and the report described them identically: same gap percent,
same RVOL band, same catalyst class, same card.

The readings are measured. The call is derived from them against two SEED lines
and is written WITH the numbers that produced it, so a reader who would put a
line elsewhere can move it over the record instead of taking the word. That is
the rule `catalyst_class` is published under, applied to a second field. A
classification never travels without its inputs, and
`claim_a_gap_type_never_travels_without_its_inputs` is what enforces it.

The regime is called from the last twenty sessions:

- **consolidation** when the window's range is at or below
  `gap_regime_range_atr_max` average ranges wide.
- **trend** when the window's NET travel is at or beyond
  `gap_regime_net_move_atr_min` average ranges, with its direction.
- **neither** in between, which is most windows and is reported as itself
  rather than forced into one of the two.

The two cannot both fire: net travel cannot exceed the range that contains it,
so a window three ranges wide cannot have travelled four.

The type then follows:

- **unknown** when the regime cannot be called or the gap has no direction.
  Below the map's own `min_sessions` there is no map and no type at all.
- **exhaustion** when the window is a trend, the gap runs with it, and the run
  of consecutive gapping sessions reaches `gap_run_exhaustion_sessions`.
- **runaway** when the window is a trend and the gap runs with it.
- **breakaway** when the window is a consolidation and the price is outside its
  range.
- **common** otherwise, which includes every gap AGAINST a trend. That is
  neither a continuation nor an exhaustion of a move it opposes, and a fifth
  word for it would name something this record has never measured.

**Recent gapping, count and run both.** `ds_recent_gap_sessions` counts how
many of the last five sessions gapped at the `[Day setup] gap_pct` line;
`ds_recent_gap_run` is the run ending at the last of them. Three gaps scattered
through a week is a busy name, three in a row is the sequence every source
calls exhaustion, and a count alone cannot tell them apart.

**Its own past gaps.** `ds_prior_gap_count` over `ds_prior_gap_of` sessions,
with `ds_prior_gap_median_otc_pct` and its `ds_prior_gap_n`. This is the only
reading in the block that is evidence about THIS name rather than about gapping
names, which is what `desk/precedent.py` answers.

**Three absences, three sentences.** A short history, a missing price and a gap
of exactly nothing are states a reader would act on differently, and until each
said its own name a row with a perfectly good year of bars and no price
reported itself as one with no history.

### The reconstructed price

A backfilled row's map needs a price to be read against, and the picks row does
not carry one. It carries `gap_pct`, which the morning measured against the end
of day prior close, so the premarket price that morning saw is the last
completed close times one plus that gap. A ratio is basis free, so this lands
on the same basis the levels are stated in.

582 of the 10,080 reconstructed rows carry no `gap_pct`. Those get a map with
every level in it and nulls for everything that needs a price, with
`ds_price_reason` saying which of the two inputs was missing. `ds_price_reason`
is a separate absence from `ds_short_reason`: a row with a year of bars and no
price still carries every level it measured, and folding the two together would
throw those away to report the wrong one.

## Float and short interest, context and not signal

`shares_float`, `pm_volume_pct_float`, `short_interest_shares`,
`short_interest_pct_float`, `short_interest_days_to_cover`,
`short_interest_as_of`, `short_interest_fetched_days_ago`,
`short_interest_source`,
`short_interest_reason`.

Read by NOTHING: not `[Day setup]`, not `[Swing setup]`, not any score
component, not the pool ordering.
`claim_no_context_column_reaches_eligibility_or_the_score` reads the screens
and the scorers for the names, in the file rather than in a design note,
because prose has never once stopped an addition.

The academic record is the reason. The raw short interest ratio's relation to
future returns largely disappears once the information short sellers are acting
on is controlled for, so the number is evidence about who is positioned rather
than about what happens next.

Four smaller decisions inside it:

- **One denominator, ours, and the vendor's own three fields are why.**
  `short_interest_pct_float` divides the vendor's shares short by the same
  `sharesFloat` `[Float rotation]` divides by, never by the vendor's own
  percent field. Measured on QCOM on 2026-09-09: 33,274,306 shares short, a
  `SharesFloat` of 1,048,101,946, and a `ShortPercentFloat` of 0.0348 that
  implies a float near 956 million. The vendor's own numerator and denominator
  do not divide into its own quotient. Computed here it is 3.175 percent and a
  reader can check it against the two beside it. Days to cover is computed the
  same way from the twenty session average volume rather than read out of
  `ShortRatio`, which is taken over some other window and would look like the
  same statistic.
- **The age on the row is a lower bound, and it is named as one.** Exchanges
  publish twice a month on a settlement lag, so a morning's figure describes a
  position taken up to three weeks earlier, and the payload carries no
  settlement date to measure that with. Measured on 2026-09-09 over QCOM, BE
  and NOK: `SharesStats.SharesShort` is null on all three and the figure comes
  from `Technicals`, which dates nothing. So `short_interest_as_of` is null and
  `short_interest_fetched_days_ago` says how long ago this project fetched it,
  which is named for what it measures rather than for what a reader would want
  it to measure. `SharesShortPriorMonth` sits in the same payload at no extra
  call and is deliberately not read: the direction of a short position is a
  second reading nobody asked for, and this section is already the lowest value
  thing in this note.
- **A hyphenated class is refused outright.** `eodhd.fundamentals` records that
  `SharesFloat` on a class row is the PARENT company's, LEN-B reporting a float
  six times its own shares outstanding. A shares short figure filed under the
  same line cannot be trusted to be this class either. Null with that reason
  beats a number from another security.
- **NOT BACKFILLED**, and refusing to is the honest half of this. The
  fundamentals endpoint answers with today's figure and carries no history, so
  a 2025 row could only be handed a 2026 number in a column that reads as a
  measurement of that session. Backfilled rows carry null with that reason.

Ten credits a call is the dearest line in `[Quota costs]`, so it is cached with
an age in `data/short-interest.json` and skipped whole on the thin quota path.

## What this still cannot say

- **Nothing here is validated.** Every threshold added is a SEED. The gap types
  are a vocabulary the literature uses, not a partition this record has tested,
  and the two lines that draw them were chosen rather than fitted.
- **The map prescribes nothing** and the boundary is enforced, not merely
  stated: `claim_the_daily_map_prescribes_nothing` refuses a key naming an
  entry, a stop, a target or a horizon and refuses any product of the average
  range in the module's code.
- **The backfilled rows are not a sample of anything.** They are the names this
  desk's pool selected, on the sessions it ran, and the reconstructed ones were
  replayed rather than lived. Any base rate taken over them inherits every
  selection the pool made.
- **The obvious next question is now askable and has not been asked.** Whether
  `ds_gap_type`, `ds_consolidation_ratio` or `ds_since_above_medium` separates
  the outcome columns at all is a query over `picks` fenced on one `source`,
  and it should be pre-registered before it is run, on the
  `PRECEDENT_PREREGISTRATION.md` precedent. Until then these are columns, not
  findings.
