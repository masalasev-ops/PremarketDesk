# Every derivation the template asks the model to perform

Written 2026-08-18, after the 2026-08-18 report explained an empty day watchlist
with "the most common failed condition was price not above the prior day high,
which every candidate missed", which was false: one of the twelve candidates
cleared that condition and failed on something else.

That sentence is one instance of a class. This is the audit of the class:
every instruction in doc/REPORT_TEMPLATE.md and doc/prompt_analyst.md that asks
the model to COUNT, RANK, COMPARE, identify a MOST or LEAST, FILTER the
candidate set by a predicate, or CHARACTERISE the set as a whole.

The project's stated design is that "membership, eligibility, scores and
conviction are computed deterministically in Python before the model ever runs".
Every row below is a place where that principle is not currently held, or is
held only by the model's care.

## The decision rule used here

Not everything on this list should move into the packet. A derivation is worth
computing when a WRONG answer would be a false factual claim a reader cannot
check. A derivation is worth keeping as prose when it is a judgement rather than
a fact, where there is no correct value to get wrong. The column says which, per
instruction, rather than applying one policy to all of them.

Status values: APPLIED means changed in this pass. PROPOSED means listed for the
owner's decision and deliberately not changed.

## REPORT_TEMPLATE.md

| # | Where | What the model is asked to derive | Class | Verdict | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | line 11, title | a two to six word market mood phrase | characterise whole | KEEP AS PROSE. A mood phrase has no correct value, so there is nothing to get factually wrong. | unchanged |
| T2 | disclaimer, 17 to 24 | name every candidate whose pm_rvol is null, and every one whose pm_window_starts_late is true | filter across set | SUPPLY IN PACKET. Omitting a name here is a silent evidence gap, which is the exact failure the disclaimer exists to prevent. | APPLIED 2026-08-28 |
| T3 | disclaimer, 24 to 26 | name every candidate whose score is null | filter across set | SUPPLY IN PACKET. Same reason as T2. | APPLIED 2026-08-28 |
| T4 | Summary, 43 | how many candidates cleared the floors | count | SUPPLY IN PACKET. A count is checkable and the model has no reason to compute it. | PROPOSED |
| T5 | Summary, 44 | how many are day eligible and swing eligible | count | SUPPLY IN PACKET. Same. | PROPOSED |
| T6 | Summary, 45 | the strongest conviction names by bucket | rank, superlative | SUPPLY IN PACKET. "Strongest" is an ordering over a computed score, so Python already knows the answer. | APPLIED 2026-08-20 |
| T7 | Summary, 45 to 46 | anything in gaps_to_fill that materially weakens the evidence | judge | KEEP AS PROSE. "Materially" is the judgement being asked for. | unchanged |
| T8 | Summary, 43 | the market tone from the snapshot | characterise whole | KEEP AS PROSE. | unchanged |
| T9 | Day watchlist, 77 to 78 | the most common failed condition | MOST | SUPPLY IN PACKET AND QUOTE. This is the instruction that produced the false claim. | APPLIED |
| T10 | Swing watchlist, 104 | the most common failed condition | MOST | SUPPLY IN PACKET AND QUOTE. Same instruction, same fix. | APPLIED |
| T11 | Market trends, 111 to 112 | what the mix says about risk appetite | characterise whole | KEEP AS PROSE. | unchanged |
| T12 | Technical signals, 116 to 119 | premarket high, low and VWAP versus price; prior day high versus price; 200 day average versus price | compare, per candidate | SUPPLY IN PACKET. These are directional claims about two packet numbers, and a reversed one reads as a breakout that is not there. Not across candidates, but wrong in the same way. | PROPOSED |
| T13 | Economic, 125 | which events have an actual published versus still pending | classify per row | KEEP AS PROSE. A direct field read per event, with no aggregation. | unchanged |
| T14 | Economic, 125 to 126 | what the rate picture does to the gap trade | judge | KEEP AS PROSE. | unchanged |
| T15 | Skips and traps, 141 to 147 | select the candidates belonging here, by five separate predicates | filter across set | SUPPLY IN PACKET. Membership in a published section decided by the model is the thing rule 2 forbids for watchlists, applied here by prose instead. | APPLIED 2026-08-28 |
| T16 | Skips and traps, 144 to 145 | a positive gap whose headlines carry negative sentiment is a trap | derive, combine two fields across headlines | SUPPLY IN PACKET. The model must read every headline's polarity and compare it to the gap sign. | APPLIED 2026-08-20 |
| T17 | Skips and traps, 151 to 153 | evaluate four predicates over the whole set, and if all are clear write "every candidate carries a found catalyst and full evidence" | universal quantifier over set | MUST CHANGE, and it is the sharpest case on this list: the template instructs the model to ASSERT A UNIVERSAL about the candidate set. It is also the one instruction that the new quantifier guard would fail, so it cannot be left as written. | APPLIED |

Not a derivation, and worth naming as the pattern the rest should follow:

- line 50, "One block per candidate, ORDERED AS IN THE PACKET". Ordering is
  handed over rather than asked for.
- lines 26 to 30, the quota sentence, which quotes remaining and daily_limit
  straight out of quota_preflight.

## prompt_analyst.md

| # | Where | What the model is asked to derive | Class | Verdict | Status |
| --- | --- | --- | --- | --- | --- |
| P1 | rule 6a | name every candidate whose pm_rvol is null, every one whose pm_window_starts_late is true, every symbol in dropped_no_coverage | filter across set | SUPPLY IN PACKET. Duplicates T2 and T3 and should be fixed with them, in one place rather than two. | APPLIED 2026-08-28, COMPLETED 2026-09-02 |
| P1b | rule 6a | the dropped_no_coverage clause on a morning that dropped nobody | filter across set, EMPTY CASE | SUPPLY IN PACKET. The 2026-08-28 fix supplied sentences for rvol_null, window_starts_late, rvol_lower_bound and score_roll.unscored and left dropped_no_coverage as an instruction reading "if it is not empty, name the symbols". That leaves the empty morning to the model, and the phrasing it reaches for there puts a banned word inside six words of a set word. Same shape as flags id3 and id4. evidence_roll.text.dropped_no_coverage now carries it, against its own denominator of candidates plus dropped. | APPLIED 2026-09-02 |
| P2 | rule 5 | a candidate gapping up on negative sentiment headlines is a trap | derive | SUPPLY IN PACKET. Duplicates T16. | APPLIED 2026-08-20 |
| P3 | rule 2 | the day watchlist is exactly the candidates with day_eligible true | filter, but on a precomputed boolean | KEEP. The predicate is a single computed field, and this rule is the guard rather than a derivation. | unchanged |
| P4 | rule 4 | classify catalyst_found false against null | classify per candidate | KEEP. Direct field reads with the three states spelled out. | unchanged |
| P5 | rule 10 | display rounding | compute per number | KEEP. Rounding for display, with the rule stated precisely and gap_pct's unit trap called out. | unchanged |

## Second pass, 2026-08-18: the Summary counts are resolved

T4 and T5 are done, ahead of the filters and the comparisons, and the reason is
that the quantifier guard does not reach them. The guard catches every, all,
none and no. It does not catch "three candidates cleared the price test", which
is wrong in exactly the same way and which the Summary was still asking the
model to work out. A count is the shape of claim the guard is blind to, so the
counts were the ones worth removing first.

Both were already in the packet and neither needed new code:
candidate_provenance.ranking carries subscribed_considered, cleared_floors and
kept, and screen_tally carries candidates_examined and the per screen eligible
count. The template now quotes all five.

**The decision underneath it, which is about the report rather than the bug.**
The Summary sentence is written the SAME WAY on a morning when nothing is
eligible, with zeros in it, rather than switching to prose. That is a choice and
it could have gone the other way: an empty morning reads a little stiffly as "day
eligible 0 of 12". It goes this way because prose written only for the empty case
is prose that runs on the fraction of mornings nobody scrutinises, and it is
exactly where both false universals were published. "0 of 12" also says strictly
more than "none are eligible": it carries the denominator, so a reader can tell a
screen that rejected twelve names from a morning that found none to screen. Those
two are different failures and the old wording could not distinguish them.

Queued behind them, unchanged: T2, T3, T6, T12, T15, T16, P1 and P2. T6 is the
other Summary item, the strongest conviction names by bucket, and it is a rank
rather than a count; it is left because ranking on a computed score is a smaller
risk than counting, and because the same pass should not both resolve and
redesign the section.


## Fourth pass, 2026-08-28: the five filters are resolved, and the guard is armed

T2, T3, T15 and P1 are APPLIED. With T16 and P2 already applied on 2026-08-20,
every item CRITERIA names as gating `analyst.quantifier_guard` is now closed
and the knob reads `enforcing`.

What was actually wrong, stated plainly, because the third pass got close and
stopped short. It recorded that T2, T3 and P1 were "SUPPLIED IN PACKET but
still phrased as filters", which is a fair description and the wrong verdict.
The lists existed in gaps_to_fill as PROSE and in score_roll.unscored as data,
and the template still said "name the candidates whose pm_rvol is null". A
model handed a sentence and asked to reproduce the set it describes is
performing the filter, whatever the packet happens to contain. Supplying the
data and leaving the instruction alone changes nothing about who decides
membership.

So the packet gained `evidence_roll`, which carries the five lists as data AND
a sentence per list, and the instructions were rewritten to quote those
sentences word for word. The five:

  rvol_null            pm_rvol is null                        T2, T15, P1
  window_starts_late   pm_window_starts_late is true          T2, T15, P1
  rvol_lower_bound     pm_rvol_basis.is_lower_bound is true   T2
  catalyst_absent      catalyst_found is false                T15
  catalyst_unknown     catalyst_found is null                 T15

T3's list is score_roll.unscored, which already existed and is now READ rather
than re-derived; evidence_roll deliberately does not carry a second copy.

Three properties the sentences have to hold, and a claim for each in
test_evidence_gaps.py:

1. Each line is a count and never a quantifier. These strings are quoted into
   the report and then scanned by the guard that judges the report, so a line
   reading "no candidate carries a null RVOL" would be built by Python, quoted
   under instruction, and flagged against the model. Under `enforcing` that
   costs a regeneration and then the plain table, for words the packet put
   there. The notable movers section already held this rule for its own
   reasons and this is the same trap one section over.
2. The empty case is written the same way, "0 of 5", rather than disappearing.
   A count carries its denominator: a reader can tell a screen that examined
   five names and found none from a morning with nothing to examine. This is
   the second pass's argument about the Summary, applied to four more lines.
3. false and null stay apart. catalyst_found false is a window read that paid
   nothing; catalyst_found null is a window never read. The template has
   separated them since 2026-08-14 and a roll that ORs them loses which one a
   reader is holding.

All three claims were mutation tested. Conflating the two catalyst states, and
replacing the zero line with "no candidates", both fail the suite.

Still PROPOSED and untouched: T4 and T5 are done, T6, T16 and P2 are done, and
what remains on this list is T12, the per candidate directional comparisons in
Technical signals. It is the last SUPPLY IN PACKET verdict outstanding. It is
not a filter across the set, so it does not gate the guard, and it is left
here rather than folded into this pass because it is a different shape of
change: sixteen comparisons per candidate rather than five lists per morning.

## What was applied in the first pass, and what waits

APPLIED: T9, T10 and T17, plus the mechanical quantifier guard that T17 forced.
T9 and T10 were the instruction that failed; T17 had to move because the guard
would otherwise fail a report written exactly as the template demands.

PROPOSED, deliberately not changed: T2, T3, T4, T5, T6, T12, T15, T16, P1, P2.
Ten instructions. They are listed separately rather than applied in a batch
because the argument for each is different, and because moving a filter into the
packet changes what the report says on a morning when the filter is empty, which
is a judgement about the report rather than a bug fix.

The four KEEP AS PROSE judgements, T7, T8, T11 and T14, are the ones where the
model is being asked for an opinion rather than a fact. They are the reason this
audit is per instruction rather than a blanket rule.

## What the guard found when pointed at the reports already on disk

Run after it was built, against every report in runs/. This is the evidence that
the class is real rather than a single slip, and it turned up claims nobody had
read closely enough to catch.

| Report | Line | The claim | True? |
| --- | ---: | --- | --- |
| 2026-08-18 | 43 | a condition was missed by "every candidate" | FALSE. AS.US cleared it, 34.71 against 33.4194. |
| 2026-08-18 | 71 | "Every candidate this morning trades below both its premarket VWAP and its prior day high" | FALSE, and separately. AS.US traded above BOTH, 34.71 against a VWAP of 33.6747 and a prior high of 33.4194. |
| 2026-08-18 | 114 | "Every candidate this morning carries a found catalyst" | The sentence the template ORDERED, T17. |
| 2026-08-14 | 9 | "Every candidate failed the same gate, price sitting below the prior day high" | The same class, four days earlier, unnoticed at the time. |
| 2026-08-17 | 58 | "premarket RVOL, and above premarket VWAP each contributed 0.0" | FALSE POSITIVE. "each" is about score components, and "candidate" appears later in the line. |
| 2026-08-18 | 5 | "No candidate carries a null score, so none is unscored" | TRUE, but flagged. "no" is not banned; "none" is. The model should write "no candidate is unscored", or quote the count. |

Two things follow.

The 2026-08-18 report carried TWO false universals, not one. Only the first was
found by reading. The second sat in Technical signals and asserted the opposite
of the packet for the one candidate that mattered that morning, which is the
same name the whole 2026-08-18 write up is about. A guard that reads every line
found in one pass what a careful human reading missed.

The false positive rate is not zero and is not being hidden. One of six is a
genuine false positive, and one more is a true statement phrased in a banned
word. Both are cheap for the model to avoid now that prompt_analyst.md rule 13
names the words and points at screen_tally for the numbers to quote instead.
The guard is deliberately blunt: the cost of a false positive is a rerun, and
the cost of a false negative is a published claim that is not true.

## The flag rate is measured, not asserted

The one in six false positive rate quoted in the table above is an impression
from a single afternoon, and it is labelled as one. From 2026-08-18 the guard
appends every flag it raises to data/quantifier-flags.jsonl with room for a
verdict, and ops/quantifier_flags.py prints the rate counted from those verdicts.
It refuses to print a rate at all until something has been judged, and says so,
because a rate computed over an unjudged sample is worse than no rate.

Review after a month and tune the word list in analyst.py on that file. The
words most likely to move are `each`, which produced the one clear false
positive, and `no`, which was added on 2026-08-18 and is the most common English
word on the list.

## Third pass, 2026-08-20: what the trap and score work closed

Two commits on 2026-08-20 moved rows on this list and nothing here recorded it,
which matters because scan.py points a reader at this file as the audit of what
the template still asks the model to derive.

- T16 and P2 are APPLIED. scan.attach_traps decides the verdict in Python and
  the packet carries `trap`, `trap_why` and `trap_basis` per candidate. Both
  documents now forbid deriving a trap from headline polarity, a claim in the
  suite reads both of them and refuses a sentence that asks for it, and rule
  5's old wording survives only as a backticked specimen.
- T6 is APPLIED. scan.score_roll builds `summary`, ordered strongest first with
  the direction carried on every row, and the template quotes that string
  rather than asking for a ranking.
- T2, T3 and P1 are SUPPLIED IN PACKET but still phrased as filters. The lists
  the model is asked to build are already in gaps_to_fill and in
  score_roll.unscored; the instruction was never rewritten to quote them, so
  the filter is still performed by the model over data Python already holds.
- T12 and T15 are unchanged and still open.

The Where column holds line numbers as of 2026-08-18. REPORT_TEMPLATE.md has
roughly doubled in length since, so those numbers no longer locate the
instructions and the section names are what to read.
