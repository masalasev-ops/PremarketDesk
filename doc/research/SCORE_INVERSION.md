# Does the conviction score order anything

## Status

**Pre-registered. No verdict exists at the time this section was written.**

Pre-registered at: 2026-08-29, when the record held 66 live picks across 7
sessions and the ledger held 16 booked trades across 6. Every judging point
below is far beyond that, on purpose: this is written now precisely because the
count is too small to judge, and a rule written after the numbers are in is not
a rule.

Amended 2026-08-31, with the record at 68 live picks across 8 sessions, 53
carrying an excursion and 17 a booked trade. Every judging point below is
still far beyond that. Gap direction was added to "Known confounds, written
down now". The mechanism was true when this file was written and was simply
not written down. An amendment made before either judging point is reached is
still a pre-registration; one made after the numbers are in is a
rationalisation, and the date on this line, against the commit that carries
it, is the only thing that separates the two. Nothing else in this file
changed.

Nothing in this file is a result. `night/weekly_page.py` renders the groups
every night and concludes nothing; the judging described here is a separate act
performed against the rules written below.

## Why this exists

The score exists to order names by confidence. Over the first fifty filled
outcome rows it ordered them BACKWARDS.

Measured 2026-08-28, on the sampled reference levels and the D+1 horizon:
conviction yellow, n=25, median favourable excursion +2.93 percent; conviction
green, n=25, median -1.27 percent. Twenty-five rows each.

Re-measured 2026-08-29 against the MEASURED reference levels, after
`entry_ref_true` existed: green n=20 across 6 sessions, median favourable
-7.44 percent; yellow n=21 across 5 sessions, median +1.36 percent. Red was
withheld at n=8 across 3 sessions. The direction survived the correction.

At those counts this is noise. It is also exactly the thing that gets
rediscovered every few months by someone eyeballing a table, argued about, and
forgotten, which is what a pre-registration is for.

## What is measured

Three quantities, per conviction bucket and per score component level, with the
row count and the SESSION count printed beside every one. The sample unit is
the session: twelve names from one morning share a tape and are one
observation.

  primary     median `pnl_pct` from `paper_trades`, rule version v1. The
              CRITERIA [Paper] rule on the PICK'S OWN session.
  secondary   median `mfe_pct_true` from `picks`.
  secondary   median `mae_pct_true` from `picks`.

The two excursions are SECONDARY and stated as such because they describe the
session AFTER the one the report was about, which CRITERIA [Paper] documents.
They accumulate faster than booked trades do, so they are judged at their own
point, and a disagreement between primary and secondary is a result about the
horizon rather than about the score.

Groups below CRITERIA [Score watch] `min_group_rows` or `min_group_sessions`
are withheld rather than shown, per metric.

## Judging points

The primary is judged when `paper_trades` holds at least **200 booked rows
across at least 60 distinct sessions** under one rule version.

The secondary is judged when `picks` holds at least **200 rows carrying
`mfe_pct_true` across at least 40 distinct sessions**.

Whichever arrives first is judged on arrival and the other waits. Judging early
is not permitted and neither is judging a bucket below the CRITERIA minimums,
whatever the totals are.

## The three outcomes, decided in advance

Let `green`, `yellow` and `red` be the median primary quantity for each bucket
at the judging point, with `unscored` excluded throughout: CRITERIA [Score
buckets] says a null score is unscored and not low, and folding it into red
would be scoring names the morning declined to score.

**1. THE SCORE ORDERS OUTCOMES.** `green > yellow > red`, and
`green - red >= 1.0` percentage point. The score is kept as it stands.

**2. THE SCORE HAS NO RELATIONSHIP TO OUTCOMES.** Either the three medians span
less than 1.0 percentage point, `max - min < 1.0`, or the ordering is not
monotone in either direction. This is the null result and it is a real one: it
says the number the report prints as confidence carries no information about
what followed.

**3. THE SCORE IS INVERTED.** `red > yellow > green`, or `red - green >= 1.0`
percentage point. The direction observed on the first fifty rows is confirmed.

## The stop rule

Under outcome 2 or 3, the conviction label STOPS BEING PUBLISHED in the morning
report as a confidence signal. It may return only after the bands are
re-derived from the record and re-validated on rows written AFTER the
re-derivation, which is a fresh sample and not the one that motivated the
change.

Under outcome 3 specifically, re-deriving the bands by inverting them is
explicitly NOT permitted. An inversion at n=200 is more likely to be a defect
in a component than a discovery about markets, and the components are grouped
separately on the weekly page for exactly that reason: the first question after
outcome 3 is which component carries the inversion, not how to profit from it.

## What this is not

**No significance test and no p value.** This is an ordering check on medians
with a stated minimum group size. Adding a test would invite the reading that a
passing p value makes the score usable, when the honest position is that 200
correlated rows from 60 sessions cannot settle much either way.

**Not a study of the screen.** Only names the screen admitted appear here.
Whether the screen picks the right names is `night/pool_recall.py`'s question.

## Known confounds, written down now

The primary rests on rule v1, which has no target and holds to the close. A
different exit could reorder the buckets, and a reordering under a second rule
version is a result about the exit and not about the score.

The ledger books only rows whose `fill_plausible` is 'plausible', so the
primary is measured over a more liquid subset than the secondary. That subset
is not random with respect to the score: thin names and low scores may travel
together.

Twenty-eight of the first sixty-six picks never reached the trigger and carry a
null P&L. If a bucket triggers systematically less often, its median is taken
over a survivor set. The trigger rate per bucket is therefore reported beside
the medians when the primary is judged, and a bucket whose trigger rate differs
by more than half from another's makes the comparison unsafe to read as a
statement about the score.

**The score is unsigned and every quantity above is measured from a long.**
The gap component scores the ABSOLUTE gap, so a name down 20 percent and a
name up 20 percent earn the same points, while `pnl_pct` books the CRITERIA
[Paper] long and both excursions are taken around `entry_ref`, which is the
premarket high. A bucket holding more falling names is losing a race it was
never entered in. Measured 2026-08-31 over the live rows carrying an
excursion: green gapping up n=11 across 4 sessions, median favourable -4.24
percent; green gapping down n=11 across 6 sessions, median -8.69 percent. An
ordering that holds inside both signs is a result about the score. An
ordering that appears only in the pooled medians is a result about which
bucket held the falling names. The share of each bucket gapping down is
therefore reported beside the medians when either point is judged, split on
the sign of `gap_pct` in `picks` with zero counted as gapping up, which is
`scan.score_roll`'s own rule, and a null `gap_pct` is its own group rather
than being folded into a sign it was never measured to have. A bucket whose
gapping down share differs by more than half from another's makes the
comparison unsafe to read as a statement about the score.

The split does not need CRITERIA [Score watch] to move and must not be used
to argue that it should. Measured the same night, both halves of green clear
`min_group_rows` at 11 and 11 and `min_group_sessions` at 4 and 6, and both
halves of yellow clear them at 12 and 11 across 4 and 5. Red's halves are
withheld at 4 and 4, which is the withholding rule working rather than an
argument for weakening it: those two minimums are read by every group on the
weekly page, and lowering them so one new split publishes would change
numbers already published in order to serve it, on the single page built to
watch for a threshold turned until the output looks the way somebody wanted.
