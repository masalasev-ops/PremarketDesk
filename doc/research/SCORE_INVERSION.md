# Does the conviction score order anything

## Status

**Pre-registered. No verdict exists at the time this section was written.**

Pre-registered at: 2026-08-29, when the record held 66 live picks across 7
sessions and the ledger held 16 booked trades across 6. Every judging point
below is far beyond that, on purpose: this is written now precisely because the
count is too small to judge, and a rule written after the numbers are in is not
a rule.

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
