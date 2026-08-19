# Decisions

Choices that could reasonably have gone the other way, with the reasoning that
settled them and the date it was settled. Appended to, never rewritten. When a
decision is reversed, the new entry says so and the old one stays where it is,
because the reasoning that turned out to be wrong is the part worth keeping.

Errors of fact are corrected in place and carry a `[corrected YYYY-MM-DD: was
X]` marker; superseded decisions keep their original text and are answered by
a later entry. The distinction is whether the statement was true when it was
written. A measurement that was misreported is a mistake and is fixed where it
stands, because a decision resting on a number nobody can reproduce is worse
than no record. A decision that was right and has since been overtaken keeps
its text, because that reasoning is the point of this file.

What changed and when is in CHANGELOG.md. Every threshold is in CRITERIA.md.

This file starts at 2026-08-14. Earlier reasoning is in doc/BUILD_PLAN.md and
in the commit messages.

## 2026-08-14: a short side screen is a separate product question, NOT STARTED

**The finding.** Both screens require the premarket price to sit above the
prior session high. A stock gapping DOWN is below its prior close, so it can
essentially never clear a level above that close, and neither screen can ever
pass one. Discovery and the propensity ranking meanwhile use the ABSOLUTE gap.
Over the 60 cached sessions, 10,424 gappers split 5,809 up and 4,615 down, so
**44.3 percent of what the socket spends its slots on cannot pass either
screen**. Not one candidate has been day or swing eligible across the only
live session on record, and every one of the twelve failed on this condition.

**What was measured.** An upward-gap-only propensity, computed from the cache
with no new fetch, scored beside the shipped configuration at caps 42 and 92,
40 sessions after a 20 session warmup:

| configuration | cap | recall | screen median | screen mean |
|---|---|---|---|---|
| shipped, absolute propensity | 42 | 0.1097 | 5.5 | 6.33 |
| upward-gap-only propensity | 42 | 0.0560 | 2.5 | 3.73 |
| shipped, absolute propensity | 92 | 0.1860 | 8.5 | 12.57 |
| upward-gap-only propensity | 92 | 0.1247 | 5.0 | 7.50 |

Per tier hit rate, subscribed slots that went to a name that gapped:

| configuration | cap | tier 1 | tier 2 | tier 3 | tier 4 |
|---|---|---|---|---|---|
| shipped | 42 | 0.55 | 0.37 | 0.39 | 0.34 |
| up only | 42 | 0.55 | 0.06 | 0.04 | 0.06 |
| shipped | 92 | 0.56 | 0.28 | 0.39 | 0.34 |
| up only | 92 | 0.55 | 0.14 | 0.04 | 0.06 |

**Tier 1 is unchanged, and that is the structural point.** 0.55 against 0.55.
Tier 1 is earnings before the open, where direction cannot be known at 07:15:
the calendar says a company reports, not which way it will move. A direction
filter cannot reach the tier that supplies most of the hits, so the whole
effect lands on tiers 2 to 4, where it is destructive.

**The comparison is confounded and must not be read as settling anything.**
The shipped key is a propensity over 250 sessions of end of day history. The
variant is computed from at most 60 cached sessions, so it is a far noisier
estimator of the same kind of quantity, and a name that gapped up twice in
three appearances scores 0.67 on almost no evidence. What the table shows is
that a short-window up-propensity is worse than a long-window absolute one. It
does not show that direction filtering is worthless. The clean test needs an
up-only propensity over the same 250 session window, which is a 2,745 call
fetch this measurement was explicitly not allowed to make.

**Decision: nothing changes, and no work is attached.** Whether to screen the
short side at all is a product question, not a tuning one. A short setup is a
different instrument with different entries, different risk and a different
report section, and CRITERIA.md's swing block already says the two screens
must be allowed to drift apart. The options, none of them chosen:

- leave it, and accept that the report is a long-only instrument that spends
  44 percent of its socket on context it can never publish as a setup;
- filter discovery to upward gaps, which frees those slots but needs the clean
  250 session measurement first, and cannot help tier 1 either way;
- add a short screen, which is a new product.

Recorded so that the next person meets the finding rather than rediscovering
it, and so the cap purchasing decision above is read in its light: the recall
figure it rests on counts down gappers as successes.

## 2026-08-14: every check reports its denominator, and zero examined is never a pass

**Decision.** Any check that can pass reports what it examined alongside what
it found. Zero examined is a distinct outcome from zero failures, named as
such, and never reported as a pass. Where the check can be written so that it
is structurally incapable of concluding on an empty denominator, it is written
that way rather than relying on a branch that happens to be ordered correctly.

**The reasoning.** This is the fifth instance of one shape in three weeks:

1. The containment check passed a report it had examined nothing in, because
   the model wrote prose and the check looks for table columns.
2. `pool_recall` produced nothing for a week and the record cited it as
   accumulating evidence.
3. The collector could not tell a subscribed symbol that stayed silent from
   one never subscribed.
4. The vintage gate passes a price from 07:22 at 08:45, because it asks
   whether the price is from today's window and not how old it is.
5. `probe_live_v1` printed "Every reading is from today" over a log of nulls.

Each was found separately and fixed separately. They are one defect: a check
whose output has no denominator, so an absence of findings reads identically
whether the check looked at everything or at nothing. The absence of evidence
is being reported as evidence of absence, and in every case the empty
denominator arose from the exact failure the check existed to catch.

**What it costs.** Some noise. A check that reports "examined 0" on a quiet
morning says so out loud, and a reader has to learn that this is information
rather than an error. That is the trade, and it is worth it: the alternative
is what happened four times above, where the quiet was indistinguishable from
the healthy.

**Alternatives rejected.** Making an empty denominator a failure was rejected:
it is not one. A morning with no eligible candidates genuinely has no ticker
claims to validate, and failing the run would train the reader to ignore it.
The distinction is three-valued, pass, fail and examined-nothing, and
collapsing it back to two is what created the problem.

## 2026-08-14: a scheduled step records its outcome whether or not its exit code gates anything

**Decision.** Every step the scheduler invokes appends a status record as it
exits, in a `finally` block, regardless of whether anything acts on its exit
code. Recording the outcome and gating the chain are separated: the exit code
is for the scheduler, the record is for the human. A step that must not break
the chain keeps returning zero and calls `job_status.failed(reason)` to
correct its own record.

**The reasoning.** pool_recall raised NameError on every nightly run for a
week and produced nothing, and the entry above citing it as accumulating
evidence nightly was false the whole time. Three deliberate decisions hid it,
and a fourth that was not a decision at all:

- the nightly `.bat` ignores that step's exit code so a diagnostic cannot fail
  the chain;
- its main caught RuntimeError only, so a NameError escaped;
- the watchdog reads each job's final step marker, and pool_recall is not the
  final step, so the nightly looked finished every night;
- and the only test exercised the pure function underneath it.

The first and third are correct and stay. A diagnostic that can fail the
nightly is worse than one that cannot, and a watchdog that failed the whole
job because a measurement died would train its reader to ignore it. So the
concealment was not caused by a wrong decision anywhere; it was caused by the
absence of a channel that reports outcome without gating anything, which is
what this decision adds.

The general principle: **an ignored exit code is a decision about control
flow, never a decision about visibility.** Whenever those two are conflated,
a failure that was deliberately made harmless is also made invisible, and an
absent measurement becomes indistinguishable from a measurement that says
nothing is happening. The second is far worse than the first, because
something gets built on it. Here, an OPEN decision cited a nightly measurement
that had never run.

**Why sessions rather than hours.** Staleness is counted in trading sessions.
A weekday job that last succeeded on Friday is one session stale on Monday,
not three days. Hours would need a tolerance wide enough for a long weekend,
which is wide enough to hide four days of a real failure; sessions need no
tolerance at all and use the exchange calendar the morning guard already
reads.

**Why the report line is written in Python.** The overdue line is appended to
the report by `analyst.annotate_job_health` rather than requested of the model
in the prompt. This follows the rule that Python decides and the model
narrates, and it follows the precedent of `annotate_unvalidated`. A prompt
rule can be forgotten by a model having an off morning, and the morning it is
forgotten is the morning the line mattered.

**Why silence is the normal case.** The line appears only when something is
overdue. A status line that appears every morning is a line nobody reads,
which would rebuild the exact failure this replaces.

**Alternatives rejected.** Making the diagnostic fail the chain was rejected:
it inverts a correct decision to fix a reporting problem, and it would mean a
recall measurement can cost a morning's report. Widening the watchdog to check
every step marker rather than the final one was rejected as a second, parallel
mechanism reading log text with regular expressions, when the steps can simply
say what they did. Alerting by email was rejected because delivery is gated
behind the UNVERIFIED marker and an alerting path that only works once
delivery is armed is not an alerting path.

**What would change this.** If the status file itself ever fails to be written,
nothing reports that, and the recorder prints to stdout and gives up rather
than failing the job. That is the deliberate floor: the recorder must never be
the reason a job dies. If this file ever starts mattering enough that its own
absence needs detecting, the check belongs in the watchdog, not here.

## 2026-08-14: the scan prices from the collector, and drops what it cannot price

**Decision.** For every candidate the collector holds, the published price and
premarket volume come from the collector file, and the gap is measured from
that price against the prior session close read out of end of day history. A
candidate the collector was not subscribed to is dropped from the packet and
from picks, named in `dropped_no_coverage` with its reason, rather than
published at any price.

**Why the collector.** The bulk `/real-time` endpoint serves the last completed
session, so at 08:45 it prices yesterday. The delayed quote endpoint carries
today's premarket eventually, but its extended hours fields still described the
previous session at 08:45 and had rolled by 08:56, which puts the roll inside
the window the scan runs in and makes it unusable at scan time. That leaves the
websocket collector as the only feed on this plan that is unambiguously
carrying today's premarket at 08:45. It already had that status for premarket
high, low and VWAP under the rule that a quote snapshot tells you where a name
is and not where it has been. Price and volume now follow the same rule, which
is one source instead of a split the pipeline had no way to notice.

**Why drop rather than fall back.** Once price comes from the collector, an
unsubscribed name has no price. The only other number available is the stale
one this whole change exists to remove, so a fallback would reintroduce the
exact defect through the exception path, on precisely the names with the least
evidence behind them. Dropping is visible; a fallback is not. The count is
printed in the run summary and the list is in the packet, so a morning where
the collector subscribed badly shows up as a number rather than as a quietly
worse report.

**What this costs.** The collector subscribes to what discover chose at 07:15,
capped at 50 symbols, and discover chooses using the same lagging bulk feed. So
the morning's candidate pool is still seeded from names that moved in the
previous session. That is a defensible screen and it is not the screen the
report claims to run. Fixing it needs a premarket source covering the full
2,745 name universe at 07:15, and no such source has been confirmed on this
plan. Until one is, the packet is honest about what it has and the seeding
limitation is the open item.

**Alternatives rejected.** Keeping the bulk feed for pricing and labelling the
report as prior-session was rejected: the product is a premarket report and a
correctly labelled report about the wrong session is still the wrong report.
Waiting until 08:56 for the delayed quote to roll was rejected: it moves the
whole chain inside eleven minutes of the open and depends on a vendor roll time
that was measured once and is not contractual.

## 2026-08-14: pm_rvol's numerator is collector volume, and the ratio is a lower bound

**Decision.** Premarket RVOL is the collector's cumulative premarket volume
divided by the cached baseline median, replacing the delayed quote's
`ethVolume` as the numerator. The packet records both windows and a
`is_lower_bound` flag in `pm_rvol_basis`.

**Why.** `ethVolume` at 08:45 described the previous extended session, so the
old ratio divided yesterday's post market volume by a premarket median. That
is the same class of error as the stale price and it was in the metric that
drives the RVOL scoring band. This goes one step past what was strictly asked,
which was a floor under the denominator, and it is recorded here for that
reason: the floor alone would have left every surviving RVOL computed from the
wrong session's volume.

**The asymmetry, stated rather than hidden.** The baseline accumulates from
CRITERIA Baseline `session_start`, 04:00, while the collector starts at 07:20.
The numerator therefore covers a shorter window than the denominator and the
ratio understates. That direction is the safe one: it can only withhold a
candidate from a screen, never smuggle one in.

**Why not just align them.** Moving `session_start` to 07:20 would fix the
window and break the backfill, which uses that same key to define the true
premarket window it reconstructs each night. Closing the gap properly needs a
second baseline keyed to the collector window, with its own column recording
which start each cached row was computed under, and a rewarm of the cache. That
is a real change with an API cost and it is the owner's call, so it is left
open rather than taken here.

## 2026-08-14: selection is a prior built before the open, not a read of today

**Decision.** discover.py no longer reads any price from today. It assembles a
candidate pool from four sources that are all knowable before the open,
earnings before open, overnight news, prior session movers and recent runners,
ranks the union by tier and 20 day average dollar volume, and subscribes the
collector to the top max_subscribed_candidates. The gap ranking it used to do
against the bulk /real-time feed is removed entirely.

**Why.** That endpoint serves the last completed session. Ranking the universe
by its gap at 07:15 ranked the previous session's movers, and because the
collector can only ever listen to what this pass chose, the error was upstream
of everything: the 08:45 scan could fix what it did with its numbers but could
not fix which names it had numbers for. No source on this plan is confirmed to
carry premarket prices for the full 2,745 name universe at 07:15, so there is
nothing to rank on. A prior assembled from information that genuinely exists
before the open is the honest alternative to a ranking that looks like a
measurement and is not.

**What it costs, measured rather than assumed.** Backtested against
2026-08-13: 99 universe names gapped beyond the 3 percent floor at the open,
the pool held 72 of them for a recall of 0.727, and the 42 subscribed held 28
for a recall of 0.283. Reproduce by building the four sources for the target
date, assembling and capping them, then measuring with pool_recall.measure
against pool_recall.actual_gappers for that session.

**What the measurement already says.** All 28 subscribed hits came from tier 1:
of 37 subscribed earnings names, 28 gapped. The five remaining slots went by
dollar volume to MU, NVDA, AAPL, MSFT and AMD, and none of them gapped. The
tier ordering is recorded in CRITERIA.md as a seed and an assumption about base
rates. This is the first measurement against it, and it says the assumption
holds for tier 1 and fails below it: sorting the news tiers by dollar volume
descending sorts toward the names least likely to gap. The obvious candidates
for the next change are sub-ranking the news tiers by something other than
size, or raising the cap, and neither should be made on one session. Left open
deliberately, with pool_recall accumulating the evidence nightly from
2026-08-14.
[corrected 2026-08-14: was "with pool_recall now accumulating the evidence
nightly", written on 2026-08-14 while pool_recall had in fact raised NameError
on every nightly run since it was scheduled and had written nothing. The
evidence began accumulating on 2026-08-14, when the fix landed. Nothing else
in this entry rests on it: the 2026-08-13 figures above came from the backtest
cache, not from the nightly, and they reproduce exactly]

**Alternatives rejected.** Keeping the gap ranking and labelling it as
yesterday's was rejected for the same reason the stale price was: a correctly
labelled wrong input is still the wrong input, and here it selects what the
whole morning can see. Subscribing to more names than the socket allows is not
available; the 50 slot cap is the vendor's.

**The ordering sweep, 2026-08-14. STILL OPEN, deliberately.** The tier ordering
below tier 1 has now been measured over 60 sessions, 2026-05-19 to 2026-08-13,
with the ranking metrics computed as of 2026-05-18 so every replayed session is
out of sample. Mean subscribed recall per session, with the spread, and split
by calendar weight at 8 before-open reporters:

| key | mean | median | min | max | sd | heavy | light |
|---|---|---|---|---|---|---|---|
| A 20 day dollar volume, shipped | 0.0842 | 0.0769 | 0.0000 | 0.2828 | 0.0475 | 0.1046 | 0.0674 |
| B gap propensity | 0.1147 | 0.1054 | 0.0467 | 0.2828 | 0.0473 | 0.1262 | 0.1053 |
| C median absolute gap | 0.0548 | 0.0355 | 0.0000 | 0.2828 | 0.0548 | 0.0942 | 0.0226 |
| D 20 day ATR percent | 0.1037 | 0.0916 | 0.0238 | 0.2929 | 0.0471 | 0.1231 | 0.0879 |
| E propensity, 25M filter | 0.1072 | 0.1018 | 0.0187 | 0.1964 | 0.0390 | 0.1152 | 0.1007 |

Per tier hit rate, slots given against slots that gapped, across all 60
sessions. Tier 1 is insensitive to the key because it is small; the whole
difference is tier 2:

| key | tier 1 | tier 2 |
|---|---|---|
| A | 431/784 = 0.55 | 361/1736 = 0.21 |
| B | 442/784 = 0.56 | 611/1736 = 0.35 |
| C | 446/784 = 0.57 | 77/1736 = 0.04 |
| D | 445/784 = 0.57 | 536/1736 = 0.31 |
| E | 370/648 = 0.57 | 644/1872 = 0.34 |

Tier floors against B, sweeping 0, 2 and 4 guaranteed slots per tier:

| floor | mean | sd | max | heavy | light | tier 3 | tier 4 |
|---|---|---|---|---|---|---|---|
| 0 | 0.1147 | 0.0473 | 0.2828 | 0.1262 | 0.1053 | no slots | no slots |
| 2 | 0.1163 | 0.0468 | 0.2727 | 0.1256 | 0.1087 | 47/120 = 0.39 | 42/120 = 0.35 |
| 4 | 0.1164 | 0.0438 | 0.2525 | 0.1211 | 0.1126 | 95/240 = 0.40 | 83/240 = 0.35 |

What the numbers say. B beats the shipped A by about a third in the mean and
by more than half on light-calendar sessions, which is the ordinary case: the
median session in this window had two before-open reporters and 2026-08-13's
37 was the maximum, so on most mornings tier 1 fills two slots and the
tiebreak decides the other forty. C is worse than shipped and should be
dropped from consideration. D is close to B and has one property B lacks,
being computable for a name with only 20 sessions of history, where propensity
is null until 100. E buys a tighter spread by filtering the pool, and pays for
it in pool recall, 0.5163 against 0.6193, because the filter removes gappers
from the pool outright rather than just from the front of it. Floors trade
heavy-calendar recall for light-calendar recall and tighten the spread, and
tiers 3 and 4 hit 0.35 to 0.40 when they are given slots at all, which is as
good as tier 2 and is not visible without a floor.

Two caveats that belong with the numbers. Tier 5 never receives a slot in any
configuration, because the backtest cannot honestly reconstruct recent runners
from a picks table holding one live session, so nothing here measures it. And
the one session spot check that suggested propensity would fix the 2026-08-13
failure does not hold up: MU scores 0.324 and AMD 0.216, higher than most of
the names that gapped and were cut, while SECZ, which gapped 25 percent, is
null for want of history. The sweep is the evidence, not the anecdote.

**CLOSED 2026-08-14.** Adopted: within_tier_key = gap_propensity,
min_slots_per_tier = 4, with within_tier_fallback = atr_pct_20d for the names
propensity structurally cannot score. Replayed under the shipped configuration
the 60 cached sessions give 0.1164 mean subscribed recall against the dollar
volume key's 0.0842, and 6.57 screen passes per session against 5.77. The
citation lives in CRITERIA.md's ordering note, at the values themselves.

The fallback ties rather than wins, 0.1164 either way, because only 0.2
subscribed names per session lack a propensity. It is kept because it does not
lose and because the population it protects, recent listings, is the one the
primary key cannot see at all.

Two things measured in the same round and NOT adopted. Collapsing tiers 2 to 4
into one tier is worse: 0.1154 against 0.1164 on recall, 5.88 against 6.57 on
screen passes, and a wider spread, 0.0483 against 0.0438. The tier boundaries
below earnings carry real information and were kept. And the tier hit rates
that suggested the collapse are not evidence for it: under the floor, tiers 2,
3 and 4 convert at 0.37, 0.40 and 0.35, which says each tier earns its slots,
not that they are interchangeable.

## 2026-08-14: the subscription cap is a purchasing decision, OPEN

**The question.** Recall is bounded far more by how many names can be
subscribed than by how they are ordered. Ordering, fully retuned on measured
data, moved mean subscribed recall from 0.0842 to 0.1164. The pool it is
ordering holds 0.6193. Everything between those two numbers is the cap.

Swept on the existing cache, shipped configuration, 60 sessions:

| cap | mean recall | screen passes | extra slots | recall gained | recall per slot | screen gained | screen per slot |
|---|---|---|---|---|---|---|---|
| 42 | 0.1164 | 6.57 | | | | | |
| 67 | 0.1578 | 9.75 | 25 | 0.0414 | 0.001656 | 3.18 | 0.127 |
| 92 | 0.1864 | 12.33 | 25 | 0.0286 | 0.001144 | 2.58 | 0.103 |
| 142 | 0.2236 | 15.62 | 50 | 0.0372 | 0.000744 | 3.28 | 0.066 |

**The screen pass column above is a mean, and it should not be read alone.**
[corrected 2026-08-14: the paragraph that stood here read "It does not flatten
in this range... every step still buys real recall", which is true of the mean
and false of the median. The conclusion it supported, that the third socket is
worth roughly half the second, is corrected below.] Those means sit over a
population whose gapper counts run 42 to 518 a session, and a report is thin
or full on a given morning rather than on average. The distribution, same
cache, same configuration, 60 sessions:

| cap | min | p25 | median | mean | p75 | max |
|---|---|---|---|---|---|---|
| 42 | 0 | 2 | 5.0 | 6.6 | 11 | 25 |
| 67 | 0 | 3 | 7.5 | 9.8 | 15 | 38 |
| 92 | 0 | 4 | 8.5 | 12.3 | 18 | 54 |
| 142 | 0 | 5 | 9.5 | 15.6 | 23 | 70 |

**The median differs from the mean materially, and it is the figure to plan
on.** Read off means the steps are +3.2, +2.5, +3.3, which is the flat decay
the old paragraph described. Read off medians they are +2.5, +1.0, +1.0: the
first quarter of the extra capacity buys most of what there is to buy and the
rest buys one name a morning per step.

The median to mean ratio falls as the cap rises, 0.758, 0.765, 0.691, 0.609.
That is the whole finding in one line: extra slots pay off disproportionately
on sessions that were already busy. Tripling the cap takes the typical morning
from 5 publishable names to 9.5 while taking the busiest from 25 to 70. On the
quietest quarter of mornings it moves 2 to 5, and at every cap the minimum
stays 0, so no amount of capacity buys a report on the emptiest days.

**Why this is not a code decision.** The 50 socket cap is the vendor's, not a
constant in this repository, so buying past it means buying capacity, and
whether a typical morning going from 5 publishable candidates to 9.5 is worth
the price depends on what the report is for and what the plan costs. Both are
the owner's to weigh. What the measurement supplies is the exchange rate.
[corrected 2026-08-14: this compared 15.6 against 6.6, both means. The
comparison a buyer should make is between medians, because the question is
what a normal morning looks like after the purchase, not what the average of
sixty mornings looks like.]

**What would change the answer.** The screen column here applies four of the
five day_setup conditions; premarket_rvol cannot be replayed historically, so
these counts are upper bounds. If the missing condition rejects at a steady
rate the ranking between caps is unaffected, but the absolute figures fall.

**The arithmetic, in sockets rather than slots.** Capacity is bought a socket
at a time and a socket carries fifty subscriptions, of which eight go to the
context tickers on the first one only. So the sweep's caps map onto whole
sockets, and this is the per session gain at each step:

| sockets | cap | recall | mean passes | median passes | gain over the step before |
|---|---|---|---|---|---|
| 1 | 42 | 0.1164 | 6.6 | 5.0 | |
| 2 | 92 | 0.1864 | 12.3 | 8.5 | +0.070 recall, +5.7 mean but +3.5 median |
| 3 | 142 | 0.2236 | 15.6 | 9.5 | +0.037 recall, +3.3 mean but +1.0 median |

**Yes, the socket arithmetic changes when read off medians.**
[corrected 2026-08-14: this paragraph read "the second socket is worth roughly
5.8 extra publishable candidates a morning and the third roughly 3.3, so the
second is comfortably the better purchase and the third is where this stops
being obvious". Both figures were means. On medians the gap between the two
purchases is far wider than that sentence implied.] On means the third socket
buys 58 percent of what the second buys, which reads as diminishing but
comparable. On medians it buys 29 percent: the second socket adds 3.5
publishable names to a typical morning, the third adds 1.0. The second socket
remains the better purchase on either reading, and that much is unchanged.
What changes is the third: on means it is a smaller version of the same deal,
on medians it is a different deal, buying one extra name on a normal morning
and most of its value on the busiest ones.

The 67 row is not buyable on its own; it is shown because the sweep ran it,
and on the median it is the sharpest row in the table, carrying +2.5 of the
+3.5 that the whole second socket buys. The first half of the second socket
really does carry most of that socket's value, and on medians it carries even
more of it than the means suggested.

**A precondition, not a follow up.** The collector has only ever been load
tested at 38 symbols, and that figure is from the OLD configuration: a 30 name
watchlist plus the 8 context tickers, measured on 2026-08-13. The current cap
already asks for more than that, 42 candidates plus the same 8, so the socket
is untested at today's setting before any purchase is considered. Nothing is known about its behaviour at 92 or 142 subscriptions:
message rate, the late trade grace period, the bar builder's per minute
flush, and the reconnect path have all been exercised at one scale only. A cap
change therefore carries a throughput check before it ships, not after. The
sequence is buy the socket, run the collector at the new subscription count
against a live tape, confirm the bar file stays complete and late_volume stays
proportionate, and only then raise max_subscribed_candidates. Doing it the
other way round would put an untested collector in front of the first morning
that depends on it.

## 2026-08-14: containment reads prose, with a recorded fail-open

**Decision.** Ticker claims are extracted from report prose as well as from
table columns. A report that makes prose ticker claims while carrying no ticker
column at all fails containment. Time expressions and ISO dates are stripped
first, and a stopword list in CRITERIA.md removes the finance and unit acronyms
that survive.

**Why the stopword list is a fail-open, and why that is accepted.** Some of its
entries are real tickers: ET is Energy Transfer, ALL is Allstate, ON is ON
Semiconductor. A claim about one of those names made in prose alone will not be
caught. The alternative is a guard that fires on "06:37 ET" every single
morning, and a guard that always fires is a guard nobody reads. Claims in the
watchlist tables are unaffected, and those tables are now mandatory even when
empty, so the ordinary path for a ticker claim is still checked exactly.

## 2026-08-15: recall is reported against the addressable target, and the market cap floor is KEPT

**The objection, which was right.** Recall had been measured against every
universe name that gapped. That denominator conflates a name discovery never
saw with a name the day screen was built to reject, and only the first is a
discovery failure. Tuning toward the combined figure chases a ceiling the
screen cannot reach by design.

**What changed.** `pool_recall` now reports three counts per session: gappers
above the gap floor, gappers that also satisfy every non-premarket day_setup
condition (the addressable target), and gappers actually published. Recall
against the addressable target is the headline and the raw figure stays beside
it. Every recall figure in the payload carries `numerator_is` and
`denominator_is` strings, so no fraction can be read without its denominator.

The split of day_setup is `gap_pct`, `price` and `market_cap` IN, with
`premarket_rvol` and `require_above_prior_high` OUT. The two excluded lines
need a premarket print, which is unknowable for a name that was never
subscribed, and that is exactly the population being measured. Excluding them
makes the addressable target an UPPER bound on what the day screen could
publish, which is the safe direction: it cannot flatter discovery.

**The measurement.** 61 sessions, 2026-05-18 to 2026-08-13, from the cached
end of day files at zero API calls. Produced by
`src/research/addressable_sweep.py`, written to `data/addressable_sweep.json`.

| Per session | min | p25 | median | mean | p75 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw gappers | 42 | 89 | 130 | 172.3 | 227 | 518 |
| **Addressable target** | **37** | **80** | **119** | **153.8** | **195** | **468** |
| Removed by the 1B floor | 3 | 10 | 15 | 18.2 | 25 | 48 |
| Percent removed by the floor | 4.4 | 8.4 | **10.3** | 10.8 | 12.0 | 20.5 |

**The premise that prompted this was wrong, and the correction matters.** The
argument was that the biggest gaps sit in the illiquid tail and the market cap
floor excludes that tail by design. Dollar volume rank and market cap are
different axes. ETON and HTFL ranked 1972nd and 1973rd of 2745 by dollar volume
on 2026-08-14, and both clear the floor comfortably at 1.18B and 2.58B. The
floor removes a median of 10.3 percent of gappers, not the bulk of them.

So the addressable target is not two or three names. It is a median of 119, and
recall against it is barely better than against the raw count: on 2026-08-14,
1 of 52 addressable (0.0192) against 1 of 62 raw (0.0161). The cap analysis and
the socket purchase decision were NOT being argued against the wrong number.
Discovery is missing roughly 118 addressable names on a normal session, and
that remains squarely a discovery failure rather than a screening artefact.

**The floor is kept, on the number rather than on the reasoning.** Relaxing it
buys less than it appears to:

| Floor | Median addressable per session |
| --- | ---: |
| 1B, the CRITERIA floor | 119 |
| 800M, the swing floor | 123 |
| 500M, the universe floor | 130 |
| 300M | 130 |
| No floor | 130 |

Removing the floor entirely recovers a median of 11 names per session, about 9
percent. The rows at and below 500M are identical because the universe's own
`market_cap >= 500M` already binds there, so the day_setup floor is not the
constraint below that level and lowering it alone would change nothing.

Two facts argue the other way and are recorded rather than hidden. The floor
removes the largest mover of the day in 17 of 61 sessions, so 27.9 percent of
the time the single biggest gap is unaddressable. And the removed population
does gap harder: mean 7.57 percent against 5.54 percent for the addressable
set, on 1,126 removed observations against 9,384 addressable. Big gaps do skew
small, just far less than the original argument assumed.

The decision is therefore to keep 1B until discovery recall is fixed. At a
median addressable target of 119 and a published recall near 0.02, the floor is
not the binding constraint on anything, and moving it now would shift the
denominator underneath a discovery fix that has not landed yet. It should be
revisited once recall against the addressable target is materially above zero,
because at that point the 11 names it costs are real and measurable rather than
theoretical.

**One limitation, stated.** Market caps come from the current `universe.json`,
so a May session is screened against an August market cap. For names sitting
near the floor that is a real source of error. It is acceptable for a
distribution and would not be acceptable for a per-name claim.

## 2026-08-16: a premarket feed must tell silence apart from absence, and EODHD cannot

**The question that started it.** If a stock has not traded, it cannot have
gapped, so why watch it at all. The reasoning is sound about the stock. It is
wrong about the subscription, and it is wrong about 8 percent of gappers.

**How often the rule is wrong.** Twenty sessions, every addressable gapper,
checked against whether Alpaca recorded a single print between 04:00 and 08:30.

| Population | Total | Silent in premarket | Share |
| --- | ---: | ---: | ---: |
| addressable gaps UP | 2,244 | 177 | 7.89% |
| addressable gaps DOWN | 1,621 | 125 | 7.71% |

Silent share of up-gaps, median session 7.12 percent, worst session 21.21
percent. Nine silent up-gaps of 10 percent or more across the twenty sessions,
so roughly one double digit mover per session prints nothing before the bell.

These are not cache artifacts. The largest were re-checked against the raw
tape, taking the prior close and the first regular session bar from Alpaca
rather than from the end of day cache:

| Name | Session | Gap | Premarket bars | Tape confirms |
| --- | --- | ---: | ---: | --- |
| PLPC | 2026-07-30 | +22.42% | 0 | +22.4% |
| PAY | 2026-08-04 | +17.27% | 0 | +18.6% |
| WLFC | 2026-07-21 | -65.81% | 0 | -66.0% |
| IDCC | 2026-07-30 | +17.93% | 0 | +14.9%, the gap between the two reads as a corporate action |

**The consequence that is not a vendor problem.** No feed can show a trade that
did not happen, so 7.89 percent of addressable up-gaps are unreachable by any
premarket source at any price. Best achievable premarket recall of addressable
up-gaps is about 92 percent. That is a ceiling on the product, and it should be
quoted as one rather than chased.

**The consequence that is.** The rule is about the stock; the failure is about
the subscription. A name cannot be known not to have traded unless something
was watching it. With 50 websocket slots against 2,745 names, 2,695 names send
nothing, and every one of them is indistinguishable from a name that did not
trade. Applying the silence rule to an unsubscribed name converts "never
looked" into "confirmed flat", which is the denominator rule of 2026-08-14
being violated in the most expensive direction available.

**Where the rule does pay, and what it needs.** As a filter it is valid, but
only with a source that can tell traded from untraded, and that is exactly the
discriminator between the two vendors.

EODHD REST cannot. In premarket it returns the previous close for every symbol,
so a name that ran 20 percent and a name that has not traded since Friday come
back identical. There is no signal to filter on.

Alpaca can. Bars are returned only for symbols that printed. Median 1,807 of
2,745 universe names traded in premarket, so the rule removes about 34 percent
of the universe, in 4 requests and about one second.

**What this changes, and what it does not.** 1,807 is still 36 times the 50
slot cap, so the filter does not rescue the websocket for discovery. What it
does is make the division of labour obvious: the Alpaca sweep already carries
prices for everything that traded, so gaps are computable universe wide in one
second, and the 50 slots are then only needed for the handful of names actually
published, where 12 is comfortably under 50. That reframes the cap from fatal
to irrelevant and makes the rotation design of 2026-08-15 unnecessary.

**NOT ADOPTED, and why not yet.** Every number above is from completed
sessions. Whether Alpaca's free tier serves that sweep LIVE at 08:30 on a
weekday is untested, and the whole design rests on it. probe-live-v1 is
extended on 2026-08-17 to measure it against the live morning.
[ANSWERED 2026-08-17: it does not. 23 sweeps from 07:30 to 09:15 on a live
trading morning returned zero bars. See the entry dated 2026-08-17 on the
free tier. Alpaca is closed as a candidate live source; this paragraph
stands as the reasoning that was correct when it was written.] Adopting Alpaca
would also break the standing rule that EODHD is the only data source, which is
a decision for the operator and not one this entry makes.

## 2026-08-16: float rotation fills the volume slot when RVOL cannot, and its bands are matched to RVOL's payout

**The defect.** pm_rvol divides by a cached baseline, so it is null for any
name that has never been baselined. A null component made the entire score
null. So a name appearing for the first time, which is often the most
interesting name of the morning, arrived unscored precisely because it was new.
Over 61 cached sessions that was 2,615 of 8,302 addressable gappers, 31.5
percent, unscorable for want of history rather than for want of evidence.

**The measure.** premarket float rotation, premarket volume over shares float.
It needs no history, so it is computable from a name's first minute. The
numerator is the collector's volume, the same field RVOL uses, so the lower
bound of 2026-08-14 applies unchanged and is flagged the same way. The
denominator is sharesFloat from us-quote-delayed, the same response the scan
already reads marketCap from, so it costs no extra call.

**They are alternatives in one slot, not two components.** Two components would
break the 0 to 10 scale for any name carrying both and would leave a first
appearance name unscored anyway, which is the thing being fixed. RVOL wins the
slot when available because it is the better measure: it asks whether a name is
busy against its own history, where rotation asks only whether the float is
turning over. The component is named for whichever measure filled it, and
volume_measure_used carries the same fact under a stable key.

**Coverage, over 61 sessions.**

| Measure | Names scored |
| --- | ---: |
| RVOL available | 5,687 |
| float rotation available | 7,752 |
| either | 8,157 |
| NEITHER, still unscored | 145 |
| rescued by rotation alone | 2,470 |

The unscorable population falls from 2,615 to 145, a 94.5 percent reduction.

**The distribution, measured over the collector window 07:20 to 08:45.** The
window is not the whole premarket, deliberately: the live numerator is summed
from the collector's 07:20 start, so measuring 04:00 to 08:30 would have set
the bands against a numerator far larger than the one the scan computes and
every live name would land a band too low.

| Population | n | p25 | median | p75 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| float rotation, all addressable | 7,752 | 0.00002 | 0.00010 | 0.00041 | 0.00125 | 0.00250 | 0.2382 |
| float rotation, top 12 by gap | 665 | 0.00014 | 0.00063 | 0.00243 | 0.00816 | 0.01508 | 0.2382 |
| RVOL rebuilt, all addressable | 5,687 | 0.327 | 0.676 | 1.638 | 5.128 | 13.560 | 5516.99 |
| RVOL rebuilt, top 12 by gap | 379 | 0.918 | 3.592 | 17.122 | 66.851 | 214.227 | 5516.99 |

**How the bands were set, which is the part that could have gone wrong.**
Setting them from the rotation distribution alone would have been enough to
follow the instruction and would still have been a defect. The two measures
share one slot, so if their bands are not matched the slot pays differently
depending on which measure filled it, and a name would score higher or lower
for the mere fact of having no baseline.

So the edges are read off the rotation distribution at the quantiles that
reproduce what the RVOL bands pay. The matching is done on the 362 top-by-gap
names where BOTH measures exist, because RVOL is available for barely half the
scored population and that half is not a random half, it is the established
names.

| | two points | one point |
| --- | ---: | ---: |
| what RVOL pays on the paired set | 53.87% | 12.43% |
| rotation quantile reproducing it | 0.00063175 | 0.00032431 |
| rounded to one significant figure | > 0.0006 | >= 0.0003 |
| what the rounded band then pays | 54.42% | 12.71% |

Rounding is downward so it can never make a band stricter than the share it was
matched to.

**The float guards are measured, unlike the RVOL denominator floor.** Across
the 1,785 addressable gappers carrying a float: smallest 51,810 shares, median
89,831,112. Exactly one sat below one percent of its own shares outstanding
(YPF at 0.013 percent, a vendor error rather than a small float) and the next
lowest was VG at 2.169 percent, so the one percent line falls in an empty
stretch of the distribution, which is where a threshold belongs. No name had a
float above its shares outstanding, so that guard caught nothing on the day it
was written and exists for the impossible value rather than the observed one.
The degeneracy that forced the RVOL floor cannot arise here: a baseline median
can be ten shares, a float cannot.

**Two limits, stated rather than buried.**

Eligibility is unchanged and that is deliberate. [Day setup] premarket_rvol
still requires a real RVOL, and Rule.test(None) is false, so a name rescued by
float rotation is SCORED but is still not day_eligible. Scoring was the clause;
eligibility is a separate question about what gets published and is left OPEN.

The matching inherits whatever calibration RVOL already had, and RVOL's bands
look loose on this population: they award full marks to 53.87 percent of the
names they score. That may well be too generous for both measures now. It is
recorded here as an OPEN question rather than fixed quietly, because changing
it would move every score in the table and that deserves its own decision.

## 2026-08-16, second: the float rotation bands were calibrated on a population that never sees them, and are re-derived

**Correcting the entry above, not superseding it.** The reasoning there stands:
one score slot, two measures, bands matched so the slot pays the same either
way. The execution was wrong. The bands were matched to RVOL's payout on the
OVERLAP, the names carrying both measures, and an overlap name is scored by
RVOL and never reaches the rotation bands at all. The only names those bands
ever touch are the rescued ones. Calibrating on the overlap set the rate using
a population that never gets it.

**First, the overlap count reconciles.** The earlier entry quoted 362 while the
coverage table implies 5,687 + 7,752 - 8,157 = 5,282. Both are correct and they
are different quantities. 5,282 is every addressable gapper carrying both
measures. 362 is that same intersection restricted to the top
[Scan] candidate_count by absolute gap at open, per session, which is the
population a packet actually scores. The earlier entry gave the restricted
number without naming the restriction. Measured directly, `paired_n_all_addressable`
is 5,282, matching the coverage table exactly.

**Second, the mapping does not transfer.** Both distributions, same quantiles,
over 61 cached sessions on the collector window.

Top candidate_count by gap, the population a packet scores:

| Population | n | p25 | median | p75 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overlap, scored by RVOL, never sees these bands | 362 | 0.00019 | 0.00086 | 0.00282 | 0.00802 | 0.01466 | 0.1000 |
| rescued, the only names these bands touch | 303 | 0.00010 | 0.00054 | 0.00202 | 0.00743 | 0.01340 | 0.2382 |

All addressable, the wider slice:

| Population | n | p25 | median | p75 | p90 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overlap | 5,282 | 0.000035 | 0.000123 | 0.000451 | 0.001260 | 0.002393 | 0.1000 |
| rescued | 2,470 | 0.000014 | 0.000056 | 0.000296 | 0.001229 | 0.002725 | 0.2382 |

The rescued population sits materially LOWER: median ratio 0.6115 on the scored
slice and 0.4587 across all addressable. It is not a uniform shift. The right
tail is fatter, p95 0.002725 against 0.002393 and a maximum more than twice the
overlap's, which fits what these names are: no baseline correlates with being
newly listed or thinly covered, and those skew to smaller floats, so most are
quieter but the few that move rotate harder.

**Where the old edges sat, and what they paid.**

| | edge 0.0006 (two points) | edge 0.0003 (one point) |
| --- | ---: | ---: |
| percentile in overlap | 0.4558 | 0.3287 |
| percentile in rescued | 0.5413 | 0.3960 |

| Population the edges were applied to | two points | one point |
| --- | ---: | ---: |
| overlap, which never gets them | 54.42% | 12.71% |
| **rescued, which always gets them** | **45.87%** | **14.52%** |
| RVOL target | 53.87% | 12.43% |

So the fallback paid full marks to 45.87 percent of the names it serves against
a 53.87 percent target, an 8 percentage point shortfall, in the direction that
penalises a name for having no history. That is precisely the bias the
alternatives design existed to remove, reintroduced by the calibration step.

**The re-derivation.** Reading the same quantiles off the RESCUED distribution
gives 0.00045075 and 0.00021475, rounded down to one significant figure as
before:

| | old | new | pays on rescued | RVOL target |
| --- | ---: | ---: | ---: | ---: |
| two points | > 0.0006 | **> 0.0004** | 55.45% | 53.87% |
| one point | >= 0.0003 | **>= 0.0002** | 12.21% | 12.43% |

**Which slice governs, and why it matters.** The two slices disagree about the
direction of the fix: on all addressable the re-derived two point edge moves UP
to 0.0007, on the scored slice it moves DOWN to 0.0004. That is not
inconsistency in the measurement, it is RVOL's own payout differing between the
slices, 15.35 percent against 53.87 percent, because selecting the top names by
gap selects busier names. The scored slice governs, because scoring only ever
happens to candidates in a packet.

The consequence is a dependency worth naming: **these edges are conditional on
[Scan] candidate_count = 12.** Change that and the population they were fitted
to changes with it, and they must be re-derived. That is recorded in CRITERIA
beside the bands rather than left implicit, and candidate_count is already an
open question elsewhere, so this will come up.

**What is not fixed.** The target itself is still whatever RVOL's bands pay,
and they remain loose at full marks for 53.87 percent of what they score. The
open question from the entry above stands unchanged. Re-deriving against a
loose target reproduces the looseness in the fallback, which is the correct
behaviour for a slot that must pay alike, and the wrong behaviour for a score
that should discriminate. Both bands want revisiting together, as one decision.

## 2026-08-16, third: the VWAP test on gappers is null, and the premarket discovery work STOPS

**The question.** Does trading a gapper against its session VWAP produce
anything, and if it does, is the edge in the VWAP rule or merely in the gap
screen? The second half is what the whole project rested on. Every socket,
recall and ordering question assumes that identifying gappers before the open
is worth something. Nothing had ever tested that assumption.

**Pre-registered, and the file enforces it.** The rule set and the stop rule
were written to doc/research/VWAP_GAPPERS.md at 14:10:19 and the results were
appended at 14:15:06. That ordering is not a claim: `--preregister` refuses to
overwrite an existing block and the run refuses to start unless the block is
already there, then refuses to append a second set of results. So the decision
below cannot have been made after seeing the numbers, and the artifact proves
it rather than asserting it. 61 sessions, 10,507 gapper name-sessions against
10,492 decile-matched control name-sessions.

**The rules were unconditioned, not selective.** This is the first thing to
read and it colours everything after it.

| Rule | Side | Fired on |
| --- | --- | ---: |
| `hold` | long | 99.2% of gapper name-sessions |
| `reclaim` | long | 97.1% |
| `fade` | short | 99.0% |
| `reject` | short | 97.0% |

A rule firing on 97 to 99 percent of the population is not a signal, it is a
description of the population. What follows is therefore a measurement of what
gappers do intraday, not of what a selective rule extracts from them. About
half of each pair is also literally the same trade: `hold` and `reclaim`
entered on the same bar in 5,051 of the 10,199 name-sessions where both fired,
`fade` and `reject` in 5,262 of 10,187.

**Median net returns, at 10 bps round trip.** Median across 61 sessions of the
per session median. All four lose money.

| Rule | median net return |
| --- | ---: |
| `hold` | -0.48% |
| `reclaim` | -0.39% |
| `fade` | -0.49% |
| `reject` | -0.41% |

**Against buy-the-open, paired on the name-sessions each rule actually fired
on.** Not against buy-the-open averaged over all gappers, which would have
compared two different populations.

| Rule | median difference | sessions won of 61 | sign test p |
| --- | ---: | ---: | ---: |
| `hold` | -0.258 | 28 | 0.609 |
| `reclaim` | -0.219 | 24 | 0.124 |
| `fade` | -0.255 | 26 | 0.306 |
| `reject` | -0.130 | 26 | 0.306 |

No rule beats simply buying the open and holding to 15:55.

**Against the decile-matched control, and this is a NEGATIVE result rather
than a null.** Controls are names whose absolute gap that session was under 1
percent, matched to the gappers by 20 day average dollar volume decile, same
count per decile, same days.

| Rule | median difference | sessions won of 61 | sign test p |
| --- | ---: | ---: | ---: |
| `hold` | -0.192 | 10 | 0.0 |
| `reclaim` | -0.124 | 3 | 0.0 |
| `fade` | -0.178 | 5 | 0.0 |
| `reject` | -0.135 | 6 | 0.0 |

The distinction matters and must not be softened in the retelling. The stop
rule anticipated the rules being INDISTINGUISHABLE from the control, which
would have said the gap screen adds nothing. What was measured is worse: on
every rule the gappers did significantly WORSE than dollar-volume-matched
non-gappers, winning between 3 and 10 sessions out of 61 at p = 0.0. The gap
screen does not fail to add value, it selects names on which these rules lose
more. The mechanism is visible in the dispersion, with gapper buy-the-open IQR
at 4.63 against the control's 2.39: gappers are about twice as volatile and a
rule that exits on a VWAP cross is chopped in proportion.

## The independent ground, which would stand even if the returns had been positive

Entry timing fails the practicality gate on its own.

| Rule | median entry, minutes after 09:30 | share entering within 15 minutes |
| --- | ---: | ---: |
| `hold` | 1 | 89.9% |
| `reclaim` | 7 | 69.5% |
| `fade` | 1 | 89.9% |
| `reject` | 6 | 69.5% |

Between 69.5 and 89.9 percent of all signals require action inside the first
fifteen minutes of the session, and two of the four have a median entry at
minute one. There is no charting platform here and no presence at the open.
Even had every return above been positive, these are not executable by this
operator, and that is a second and independent reason to stop rather than a
footnote to the first.

## What this tested, stated as limits and not as a list of things to try next

These are the boundaries of the claim. They are recorded so that nobody reads
the decision as broader than the evidence, and equally so that nobody treats
them as a queue of follow ups. The decision below is to stop, and a limit is
not a licence.

- Four VWAP-cross rules only, all unconditioned, on two axes of direction and
  whether the opposite condition had to occur first.
- No stops and no targets.
- One entry per name-session, no re-entries.
- Whole-day hold, exit on the rule's own cross or at 15:55.
- Entry at the close of the confirming bar. Fills, spread and slippage are not
  modelled, so the returns are indicative and optimistic.
- `universe.json` holds current listings, so names delisted since are absent
  and survivorship flatters the result by an unknown amount in an unknown
  direction. The result is negative anyway, which makes the conclusion
  stronger rather than weaker.
- Borrow availability was checked by flag only, and `shortable` and
  `easy_to_borrow` were identical across all 2,745 universe names, so the
  short-side restriction was a weaker test than it appears. Borrow COST was
  not modelled at all.
- **No catalyst conditioning. A catalyst-split version was NOT tested.** The
  gappers here are pooled regardless of why they gapped. If hard catalysts
  such as earnings, guidance, M&A and FDA behave differently from soft ones
  such as sympathy moves and analyst actions, pooling them would produce
  exactly this null by averaging a positive population against a negative one.
  That possibility is not excluded by anything measured here. It is recorded
  as a limit of the test, NOT as a reason to keep going.

## The decision, and exactly what it covers

**The premarket discovery work stops.** By the stop rule as written before the
numbers existed, and on the independent practicality ground above.

Stopping:

- The socket purchase. No second or third socket is bought.
- The cap, ordering and recall work. No further tuning of which names reach
  the collector or in what order.
- The scoring calibration, including the volume slot and its bands.
- Any migration to Alpaca for LIVE premarket discovery. The historical Alpaca
  work stands as the evidence it produced, and Alpaca remains in use for
  research bars.

Continuing:

- Monday 2026-08-17's `probe-alpaca-live` and `probe-live-v1` run as
  registered and their results are recorded. They are already scheduled, they
  cost nothing to let run, and the question of what the vendors actually serve
  live is worth having answered on the record even though nothing will now be
  built on it. Recording a result is not the same as acting on it.
- The post-open pass continues. Nothing here measured it and nothing here
  bears on it.

## Open items this closes, so they are not reopened by accident

Each of these is closed BY THIS DECISION rather than resolved on its own
terms. The measurements in them stand; what has gone is the reason to act on
them.

- **The subscription cap table, 42 through 142** (2026-08-14, "the
  subscription cap is a purchasing decision, OPEN"). The exchange rate it
  computed is still correct: a typical morning goes from 5 publishable names
  to 9.5 across three sockets. Closed because publishable names are no longer
  worth buying. Closed by this decision, not by the arithmetic changing.
- **The second-socket purchase**, and the load test that entry named as its
  precondition. The collector is still untested above 38 symbols. That now
  stays untested, because the cap is not rising.
- **The float rotation band's dependency on `candidate_count`** (2026-08-16
  second). That entry recorded that the edges were fitted to the top
  candidate_count by gap and must be re-derived if that number changes. This
  is now MOOT rather than resolved: the bands are correct as measured, and
  nothing will change candidate_count, so the re-derivation will not be
  needed. If scoring is ever restarted, that dependency is live again exactly
  as written.

  **[corrected 2026-08-18: this is DORMANT, not moot, and the sentence "if
  scoring is ever restarted" is false. Scoring was never stopped. This
  decision stopped the scoring CALIBRATION work; the morning chain runs every
  weekday and scores every candidate, as the next entry says when it calls the
  post-open pass and the morning chain the only remaining outputs.
  candidate_count is a live CRITERIA knob read by a job that runs daily, so
  the dependency is one edit away from mattering rather than retired. What
  this decision actually supports is that nobody is currently WORKING on the
  bands, which is a fact about the roadmap and not about the knob.]**

Also left where they are, unresolved and now inert: the day-setup eligibility
question for names rescued by float rotation, and the looseness of the RVOL
scoring bands. Both were open questions about scoring, and scoring has stopped.

**[corrected 2026-08-18: neither is inert and the reason given is wrong for
both. Scoring has not stopped; the scoring CALIBRATION work stopped, and the
morning chain scores every weekday. The eligibility half is answered at length
in the 2026-08-18 entry, with AS.US as the counterexample. The RVOL band half
is corrected here for the same reason: those bands set what a published score
means every morning, and 2026-08-17 seventh has since recorded that the
numerator feeding the alternative measure is miscalibrated against the source
its bands were fitted on. A question that decides what today's report says
cannot be inert.]**

## 2026-08-16, fourth: the second SOCKET is closed, the second TOKEN is not, and they were never the same purchase

**Correcting a conflation in the entry above.** The VWAP stop closed "the
socket purchase" and listed the cap table with it. That is right about one
purchase and wrong about the other, and the two have been spoken of together
often enough that the distinction needs writing down before the shorthand
outlives the reasoning.

**The second websocket socket: CLOSED.** It was only ever worth buying to lift
subscribed recall against the 50 name cap, which bought a typical morning from
5 publishable names to 9.5. Publishable names are what the VWAP test found no
value in, so the thing that purchase buys is the thing that turned out not to
be worth having. Closed, and closed on the decision rather than on the
arithmetic, which still stands.

**A second API token: OPEN, and worth MORE than it was yesterday, not less.**
It is a different purchase entirely. It buys quota isolation, not subscription
capacity, and the case for it strengthened at the moment the rest of the work
stopped.

The reasoning. The key is shared with sibling projects this repository cannot
see or throttle. On 2026-08-16 a sibling took it from 96,098 used to 99,671
across an afternoon, which put the remaining balance below discover's refuse
floor of 500. Anything scheduled into that window does not degrade, it refuses
outright. Before the stop that was one failure mode among many in a system
with several moving parts. After the stop, the post-open pass and the morning
chain are the ONLY remaining outputs, and both die the same way for a reason
that has nothing to do with either of them. Narrowing the project did not
reduce this exposure, it concentrated it: the same accident now takes out
everything rather than one component of many.

Recorded as OPEN with its reason, and deliberately NOT as a plan. No price has
been checked, no vendor terms read, and nothing here says buy it. What this
entry fixes is that the case for a second token must not be quietly retired
alongside the socket, because a reader skimming for "purchases, closed" would
take both and would be wrong about one.

**The cheap half, taken now.** Attribution does not need a second token. Every
job now reads the shared meter at entry and at exit and appends both to
`logs/meter-<quota day>.log` with the delta since the previous reading, so a
day of consumption is attributable to a time of day and to a step. A job's own
spend is its entry-to-exit delta; whatever a sibling spent shows up as the gap
between one job's exit and the next job's entry. Two calls per job, about
eighteen a day against a shared 100,000, and the readings themselves are
visible in the trail rather than hidden, so a delta of two across a step that
made no other call is the instrument seeing itself.

That does not fix the exposure. It measures it, which is the precondition for
deciding whether the token is worth its price, and it works today.

## 2026-08-17: the bill is not the call count, so the gate is sized in credits and the funnel names its doors

**The measurement that forced this.** The 2026-08-16 Sunday rebuild started
with 329 credits on the shared meter and finished successfully, and the call
report said it made 172 http calls. Reading those two numbers together says the
job cleared with room to spare. It did not. The meter moved 4,945.

The prices reconcile exactly on two independent runs and are now recorded in
CRITERIA.md [quota costs] as MEASURED: us-quote-delayed bills one credit per
SYMBOL while being issued twenty at a time, eod-bulk-last-day is a flat hundred
per call, eod and exchange-symbol-list are one each, and user is free. On the
00:06:53 rebuild, 2 + 1 + 20x100 + 2,942 staged names gives 4,945, which is the
delta between the entry and exit readings in logs/meter-2026-08-17.log. The
20:30:01 run staged 2,941 and read 4,944 at its exit. There is no slack in
either sum for the meter reads themselves, which is what pins user at zero.

So the 2026-08-16 run did not clear with room to spare. It needed 4,945 and
held 329, seven percent of the bill, and it survived only because the vendor's
counter rolled within the first seconds of it. The bulk sweep alone would have
exhausted 329 on its fourth of twenty calls.

**Decision: quota gates are sized in credits against the work about to be done,
not against a flat floor.** refuse_below_remaining is 500 and stays 500, which
is right for a scan spending a few hundred. It is useless for the Sunday
rebuild: a meter reading 501 clears that floor and then strands the job a tenth
of the way in, having spent everything that was there. eodhd.require_quota
prices the step from the table and refuses below it times the headroom in
[quota] quota_headroom_multiple.

**Two gates, at the two points where nothing has to be estimated.** After
_session_dates returns, exactly three credits are spent and len(session_dates)
is exact, so the two thousand credit bulk sweep is priced rather than guessed;
refusing there costs three credits instead of two thousand. Before the market
cap sweep, len(staged) is final, so the largest block is priced exactly and the
meter read to check it is free. The second gate is the one that had to exist.
The first is cheap insurance and its sweep estimate comes from the previous
build's cleared_price_and_liquidity, which is a real number rather than a seed.

**An unknown meter still refuses nothing, and this is load bearing.** preflight
leaves remaining as None on three paths, and the third is a reading dated to
another quota day, which is exactly what the vendor serves for the half hour
after a reset it rolls thirty minutes late. Treating that as a zero would turn
a benign late roll into a skipped weekly rebuild, and would act on a number
nobody read. require_quota therefore refuses only when remaining is not None,
never recomputing it from api_requests, which the stale branch does populate.

**gap_stats gets the same gate rather than universe carrying its budget.** It
is the second step of the same .bat and cost a measured 2,753 credits against
the same 500 floor. Coupling the two would refuse a rebuild on Sundays when
only gap_stats was unaffordable, so each prices itself. gap_stats can price
itself exactly, one eod per universe name, before its first call.

**Refusing is the cheaper failure, which is why it is the choice.** A refused
Sunday leaves last week's file, and the monitor relaunches the job at
universe_rerun_after_days, so the recovery path already exists. That argument
holds ONLY while a refusal leaves the old file in place, which is why the
write time gate below exists: it is the same reasoning applied to the failure
the quota gates cannot see. Continuing: discover only
starts refusing on the fourth morning after a miss. Proceeding on a short meter
is the outcome with no recovery. staged is sorted by dollar volume descending,
so a sweep that runs out partway does not thin the file evenly, it amputates
the illiquid tail, and the result stays inside expected_count_range and above
min_count_fraction_of_previous until roughly half the names are gone. A missing
report is recoverable. A plausible one built on a truncated universe is not.

**Decision: the market cap funnel records every door, by name.** The note this
replaces said "46 names were dropped because no market cap came back" against
2,942 examined and 2,754 admitted. That arithmetic does not close: 142 names
failed the market cap floor with nothing recording that they had been
considered. Naming the 46 alone would have made the record worse, because a
reader would take the named list as the explanation for the whole 2,942 to
2,754 drop, and it explains a quarter of it.

Five doors now, and they are not the same kind of fact.
below_market_cap_floor is a decision made on evidence. The other three are
absences that differ in what is absent: the vendor answered and carried no
market cap, the vendor answered a batch without mentioning the name, or nothing
came back for the batch at all. Only the first is a fact about the market.

**What separating them immediately revealed.** The 46 were never one thing.
They are 20 and 26, and neither group is missing data. The 20 are alternate
share classes and warrants the vendor prices under the primary class: BRK-A,
BRK-B, HEI-A, LEN-B, MOG-A, GEF-B, BH-A, UHAL-B, BF-B. The 26 are preferreds
and warrants it does not quote at all: ALB-PA, ARES-P-B, BA-P-A, HPE-P-C,
KKR-P-D, NEE-P-T, PCG-P-X, JOBY-WS, and ZVZZT, which is NASDAQ's test symbol.
So the market cap gap was silently doing the filtering that
allowed_security_type was supposed to do, and that was invisible while all 46
shared one sentence. Whether the type filter should catch them upstream is a
separate question and is left open here.

**A silent hole closed on the way.** The old guard was `if error and not data`.
eodhd.quote_delayed returns ({}, None) when a chunk comes back 200 with a body
it does not recognise: no error, no rows. The guard was False, the loop ran
over an empty dict, and twenty names fell into the vendor gap counter with
nothing written anywhere. The test is now on the data rather than the error, so
a batch that answered nothing is recorded as unanswered whether or not it said
why. It did not fire on either run observed, which is why it went unnoticed.

**check_admissible acts on the distinction, at max_unswept_fraction = 0.02, and
the build asks it BEFORE overwriting anything.** Recording the difference
without acting on it would leave the same silent corruption in place with
better documentation. But where it is enforced matters more than the number.
check_admissible has always been called downstream, by discover, on a file
already on disk. That ordering is fine for a question about age and useless for
a question about completeness: os.replace is destructive, so by the time
discover can refuse the file, the good one it would have fallen back to is
gone. Worse, the monitor relaunches the rebuild on AGE, so a truncated file
with a fresh timestamp is never retried while a missing one is, and the
recovery argument two paragraphs above would not have applied to the very
failure this gate was added to catch. build() therefore asks the question of
its own payload and raises PartialBuildError rather than writing.

The numerator is the names nothing came back for at all. Names the vendor
answered a batch without mentioning are excluded, because that is its coverage
rather than this run's failure, and it is structural: 26 of 2,942, all
preferreds and warrants. Folding them in would spend a third of the ceiling on
a constant and leave real losses 1.6 batches of room. Excluded, the baseline is
zero, 0.02 of 2,942 is 58 names, and the gate clears two lost batches of twenty
and trips on the third. Payloads written before the funnel existed carry no
field and are skipped rather than failed.

**Errors of fact corrected in place today.** CRITERIA.md recorded
eod-bulk-last-day at "98 counted calls each" in two places. At 98 the rebuild
reconciles to 4,905 and leaves 40 credits unexplained; at 100 it closes
exactly. The 98 was read off the client side call ledger, which counts calls
and is not the bill. Both sites now carry the marker. The [job status steps]
comment still said Sunday 20:00 after the schedule moved to 21:00 on
2026-08-16, and is corrected the same way.

**What this does not close.** Whether eod-bulk-last-day costs 100 for every
caller or only for this one is untested; the price is measured from universe's
usage alone. The vendor's HTTP status on exhaustion is still unobserved, so the
refusal path is argued rather than demonstrated end to end. And the 21:00 slot
has never fired, so its clearance of the late roll is inferred from the
schedule rather than seen.

## 2026-08-17: Alpaca's free tier does not serve live premarket, measured across a whole morning

**The open question this closes.** The entry above, on reconstructing premarket
from Alpaca, ends NOT ADOPTED with one reason: every number in it came from
completed sessions, and whether the free tier serves that sweep LIVE on a
weekday morning was untested while the whole design rested on it. It is tested
now.

**The measurement. 23 sweeps, 07:30 to 09:15 ET on Monday 2026-08-17, every
one empty.** Zero active names, zero bars, no newest bar timestamp, on every
sweep, across a live trading morning on which this project's own collector
folded 33,489 trades from 50 symbols into 3,102 minute bars. The probe records
its own denominator, which is what makes the emptiness informative rather than
vacuous: sweeps taken outside a premarket window prove nothing, and these were
taken across the middle of one. The table is
data/probe-alpaca-live-table-2026-08-17.md and the raw readings are beside it.

**It does not stand alone.** Two other measurements from the same morning point
the same way, and each closes a different candidate.

The per symbol real time endpoint was swept 125 times and not one reading was
dated to that day. It serves the last completed session, exactly as the bulk
form does, which had already been recorded.

The delayed quote's extended hours fields were stale at the moment they were
needed. At 08:45, KEEL.US carried ethTime dated the previous Friday at 16:29
while data/premarket/2026-08-17.jsonl already held 50 of its minute bars from
07:19 that morning. The same fields read correctly at 10:12, so they do update,
just not in time to be read at 08:45. A field that is right two hours after the
report is written is not a source for the report.

**Decision: Alpaca is closed as a candidate LIVE discovery source.** Not
deferred, not pending a better tier, closed on measurement. It remains what it
already was, a historical reconstruction source for completed sessions, and the
NOT ADOPTED entry above stands unchanged as the reasoning that was correct when
it was written.

**This corroborates the 2026-08-16 stop, it is not an input to it.** The order
matters and is worth stating so the record cannot later be read backwards. The
VWAP test stopped the premarket discovery work on 2026-08-16 on its own
evidence: four rules losing, none beating buy the open, and gappers doing
significantly worse than decile matched controls at p = 0.0, winning 3 to 10
sessions of 61. This probe ran the following morning and answers a different
question, which is whether a cheaper data path existed that would have changed
the economics. It did not. Had this probe come back positive the stop would
still stand, because the stop was about whether the names are worth having and
not about what they cost to find.

**Correction to a claim made earlier the same day.** A two credit probe at
09:57 confirmed that us-quote-delayed carries lastTradePrice and lastTradeTime,
and I described that as a live price. Precisely: it is live during REGULAR
HOURS, where it read 09:56:12 against a 09:57 fetch. Its behaviour during
premarket is UNTESTED and cannot be inferred from that reading, because the one
extended hours field this project does record was demonstrably stale at 08:45
on the same morning. Any design that assumes a universe wide premarket price
from that endpoint is assuming the untested half.

**What this does not close.** Whether lastTradePrice moves ahead of the prior
close during premarket, which a probe run between 07:30 and 09:00 would settle
for about 20 credits a day. That probe was considered and deferred: the
briefing section it would inform is built from completed sessions and needs no
premarket price, so the question is now optional rather than blocking.

## 2026-08-17, second: the briefing reads one file, scales its sigma by the span, and ranks inside one leg

Three rulings by the owner on the notable movers section, before a line of it
was built. The section is specified in BUILD_PLAN.md Layer 4; this is why each
of the three went the way it did. The design they amended was mine, written
down the same day, and each ruling replaced a worse answer.

**The universe legs read data/universe-closes-<date>.json, not
pool_recall.json.** My version had the universe wide leg reading the previous
session's true OPEN gap out of the prior day's pool_recall.json, on the
grounds that the 09:45 pass had already computed it for every name. Three
things are wrong with that and only the third was visible to me at the time.

It is not universe wide. pool_recall only records names above the discovery
gap_pct floor of 3 percent, so the leg would have covered the gappers and
called itself the universe. I had noticed this and disclosed it as a partial
view, which is the wrong repair: a section that reports a truncated
denominator and explains the truncation is worse than one that reports the
whole universe, because the explanation is what nobody reads.

It costs a vintage. The closes file exists precisely so that the section's
three closes share one vintage, bought with an extra 100 credit bulk call for
exactly that reason. Reading a fourth number out of a different module's
output on a different schedule reintroduces the mixing that call was spent to
avoid.

And close to close is the better measure for a briefing anyway. An open gap
carries only the discontinuity. Close to close carries the whole session, the
gap and the drift after it, and the question this section asks is what
happened to the name, not what the screen could have traded. The open gap
belongs to pool_recall because recall is measured against what the screen
could have caught at the open; the briefing is not that.

**Decision: no leg reads pool_recall.json.** The scope fence around the recall
measurement then holds with nothing to enforce it, because there is no
connection to sever, and the examined count is the universe rather than the
gapper count.

**move_sigma scales by the square root of the span.** I had ruled sigma
inapplicable to the multi session legs, correctly identifying that a two
session move over a one day standard deviation is dimensionally wrong, and
then stopped at the diagnosis. The standard repair is to divide an n session
move by sigma times the square root of n, which is what the section now does:
1 for premarket and prior_session, the square root of 2 for two_session.
Every leg carries a sigma, and the four labelled lists can be read as one
section.

The assumption is stated in the docstring where the scaling is computed,
because it is not free. Square root of time scaling assumes daily returns are
INDEPENDENT, and consecutive moves in one name frequently are not: momentum
and a multi day catalyst both produce runs, and dependent returns accumulate
faster than the square root allows. So the scaled sigma UNDERSTATES how
unusual a sustained run is. That is the safe direction here. It cannot inflate
a name into a briefing, it can only keep one out.

**Every ranked list stays inside one leg.** My version ranked the whole
section on each name's newest available move, premarket where the collector
heard it and the completed session otherwise. That is a ranking that cannot
mean anything. The 50 collector names were selected in advance for gap
propensity and news, and they are measured on a fresher and wider window than
the 2,704 names nothing selected. They would take the top of every list
systematically, and a section that exists so the report says something the
watchlist does not would have spent itself restating the watchlist.

**Decision: four lists, each ranked within one leg.** move_sigma and market
cap on the prior session leg universe wide, absolute move on the two session
leg universe wide, and move_sigma on the premarket leg over the collector
names alone. Like for like inside each list, and the premarket names get their
own five slots instead of taking everyone else's.

**What this cost, stated rather than buried.** Under the naming these rulings
settle, where a leg is named for the number of sessions its move SPANS, the
three session leg has no source: it needs a fourth close and the file holds
three. It is not emitted. Restoring it is one more 100 credit bulk call in
discover, 500 credits a week against a 4,945 credit universe build, and that
is the owner's call rather than the builder's. The leg name stays in
_LEG_NEWEST_SESSION_BACK, where it costs nothing and would validate correctly
if a row ever carried it.

## 2026-08-17, third: the three session leg is DROPPED, not left defined and unemitted

The notable movers section was specified with four legs and shipped with
three. The fourth, three_session, had no source: under the naming settled
earlier the same day a leg is named for the sessions its move SPANS, and a
three session move universe wide needs a fourth close where
data/universe-closes-<date>.json holds three. I left the key in
_LEG_NEWEST_SESSION_BACK anyway, with a note that it cost nothing and would
validate correctly if a row ever carried it. The owner removed it.

**The cost of restoring it, so the number is on the record and not
recomputed.** One more bulk end of day call in discover, a flat 100 credits in
CRITERIA [quota costs], every weekday morning. About 500 credits a week
against a shared 100,000 a day key that a sibling project already drains
unpredictably, and against the 4,945 credits the Sunday universe build spends.
Small, and not zero.

**What it would buy, which is less than it looks.** The two session leg
already carries most of it. A three session window and a two session window
over the same name are highly correlated, because the second contains the
first, so the marginal name that a three session leg surfaces and a two
session leg misses is rare. And the question a three session move answers is
what this name has been doing this WEEK, which is a trend question. This
report is written at 08:45 to answer what is worth watching in the next few
hours. A leg whose window outruns the report's own horizon is a different
product.

**Decision: three_session is removed from the table, not deprecated in it.**
The reasoning matters more than the deletion. This project has been bitten
repeatedly by the same shape: something is defined, looks reachable, and never
runs. The bulk feed that served the last completed session while the gate
compared it against its own high. The live v1 cumulative volume that was
available and unsound. The Alpaca free tier that answered every request and
returned no bars. In each case the thing existed, and its existing was read as
its working. An enum key that no code path emits is that shape in miniature: a
future reader finds it, assumes a producer somewhere, and either writes a row
that no list can populate or spends an afternoon looking for the writer.

A recorded decision is strictly more useful to that reader than a silent enum
entry. The entry says a leg exists. This entry says what it would cost, what
it would buy, why the answer was no, and that re-adding one key to
_LEG_NEWEST_SESSION_BACK plus one bulk call in discover is the whole job if
the answer changes.

**What this does not touch.** The extra 100 credit bulk call discover already
makes for c3 STAYS. c3 is the two session leg's baseline, so that call is
still doing the work it was bought for; dropping the leg named "three" does
not make the third close unnecessary. The per candidate gap_3session field
also stays, because it is emitted: it is measured to today's premarket price
over the twelve candidates and is a report field beside gap_pct, not a section
leg. Nothing here is defined and unemitted after this change.

## 2026-08-17, fourth: the universe escape hatch reaches ONE verdict, and the reason is which number it is measured against

The pre-write admissibility gate refuses to overwrite a good universe with a
partial one. Moving that check before the write was right and is not in
question here. What was missing is that the gate had no way out: the count
fraction verdict measures this build against previous_count, which is read from
the very file the refusal prevents replacing, so a legitimate shrink refuses
again every Sunday against the same frozen baseline, and past max_age_days
every morning job refuses too. A --force flag now exists.

**The decision that could have gone another way is its SCOPE.** The obvious
implementation is "--force writes anyway", and that is what the first fix did.
It is wrong, and the code was already saying so. check_admissible can return
three verdicts, and they are not the same kind of thing:

| verdict | measured against | clears by itself? |
|---|---|---|
| count fraction | previous_count, from the file on disk | NO, the baseline is frozen |
| unswept fraction | this build's own market cap funnel | YES, rerun when the vendor answers |
| no count | a malformed payload | not a shrink at all |

Only the first can refuse forever, because only the first is measured against
something the refusal itself prevents changing. The other two are measured
against this run, so a rerun settles them and no human has to decide anything.
An escape hatch for those buys nothing and costs the gate.

**And the refusal message had already committed to this.** Its own wording
said names in a batch that answered nothing "are the case this gate exists for
and must never be forced past", while `if verdict and not force` cheerfully
forced past exactly that. The code contradicted its own message, which is the
tell that the scope was never thought through rather than deliberately wide.
Forcing the unswept verdict writes the quota starved, illiquid tail amputated
universe the gate was built for: the sweep runs in dollar volume order, so a
run that lost batches has not thinned the universe evenly, and the result still
lands inside its expected count range while the names it is missing are the
ones a gap screen is looking for.

**Scoping it also closed a blocking defect for free, and that is the part
worth keeping.** The override matches on the verdict TEXT rather than on a
boolean, deliberately: tighten the floor afterwards and the sentence changes,
the override stops applying, and the gate speaks again, which a flag could
never do. But the first implementation applied that match at all three return
sites, each written "return answer(...)", so a matched override returned None
immediately and every check BELOW it never ran. An override recorded for the
unswept verdict admitted a file whose count was far under the floor, in
discover, every morning until the next rebuild. Narrowing the override to the
count fraction verdict, which is the LAST check in the function, means there is
no check below it left to skip. The design is now safe by construction rather
than correct by inspection, and that is why the scoping decision is recorded
here rather than treated as a tidy-up.

**Cost accepted.** An operator whose Sunday rebuild is refused on the unswept
verdict has no override and must rerun, possibly waiting on the shared quota.
That is the intended answer: the thing they would be forcing is the thing the
gate exists to stop.

## 2026-08-17, fifth: an absent, a zero and a negative sharesOutstanding are three facts, not one

Float rotation divides premarket volume by sharesFloat, and the vendor figure
needs a cross check, because a float far below shares outstanding is an
artifact and a float above it is impossible. Both checks need a usable
sharesOutstanding. The guards asked for one in two different ways, "if
outstanding" and "if outstanding is None", and between them they covered falsy
and None while covering zero NEITHER time, so a sharesOutstanding of exactly
0.0 skipped both ratio checks AND the absolute floor and a fabricated float
became the divisor unchecked.

**Decision: three states, three answers, each named in the recorded reason.**
An ABSENT sharesOutstanding and a ZERO one are both a share count the vendor
never supplied, so the float faces the absolute share floor in place of the
ratios. A NEGATIVE one is a share count that cannot exist, so the quote is
corrupt rather than incomplete and the float in it is refused outright. The
reason string says which case fired, because a human reads it and "the vendor
sent nothing" and "the vendor sent zero" call for different follow ups.

**The negative case is here because the first fix broke it, and the reasoning
is worth preserving.** The review that found the zero hole asserted negatives
were unguarded too. They were not: "if outstanding and share_float > outstanding
* max_ratio" is truthy for a negative outstanding, and every positive float
exceeds a negative product, so negatives were already refused, with a gap
raised, by accident. The fix replaced the falsy test with an explicit "present
and positive" test, which is correct in intent, and in doing so it stopped
refusing negatives and began publishing a rotation for them with an impossible
share count recorded beside it. A guard that was holding for a reason nobody
had written down was removed by a change aimed at a different hole. That is the
argument for making all three states explicit rather than leaning on which
comparisons happen to be true for which signs.

**Known and accepted, recorded so it is not mistaken for an oversight.** The
absolute share floor is weak protection at this scale. A fabricated float at or
above min_shares_float with a few hundred shares of premarket volume still
lands in the top rotation band, which starts three orders of magnitude below
where such a name computes. The floor keeps out only the most obviously bogus
denominators. Closing that properly needs either a second independent share
count to check against or a band structure that does not reward an unverifiable
denominator, and both are threshold and design questions for the owner rather
than guard placement. What changed here is that no name reaches the divisor
without facing SOME check, and that every null says why.

## 2026-08-17, sixth: the rotation bands are re-derived after the screen fix, and they do not move

**Why this was owed.** The 2026-08-17 review fixed float_rotation_study.py: it
carried a private copy of one CRITERIA floor with the ratio written into the
Python as 1.01, was missing the other two floors entirely, and refused nothing
for the corrupt records the live path will not divide by. CRITERIA
[Score premarket float rotation] names that script as the way to re-derive the
bands, and the bands scoring live names every morning were produced by the rule
that had just been corrected. Fixing the instrument and leaving its output
standing is not a fix, it is a fix and an unmeasured claim. The edges are read
off rotation quantiles at the points reproducing RVOL's payout on a specific
population, and the hole changed WHICH NAMES were in that population, so the
payout match the edges exist to preserve could no longer be assumed.

**[corrected 2026-08-17: was "the edges do not move, and they reproduce
exactly rather than approximately", with a table asserting the counts and
payout shares reproduced too. The EDGES do reproduce, and that is the claim
this entry exists to make. The surrounding percentages do NOT, because
data/universe.json was rebuilt between the two runs. The original table is
replaced rather than kept because it was wrong when written: it was built from
a proof about the screen fix and presented as though it described a re-run.]**

**The result first: the edges do not move.** Confirmed twice over, by proof and
then by an actual re-run of the script on 2026-08-17.

**Both sides of this table are committed evidence, because neither run can be
produced again.** The columns below are read from:

- 2026-08-16: doc/research/float_rotation_study-2026-08-16-prefix.json
- 2026-08-17: doc/research/float_rotation_study-2026-08-17-postfix.json

Each carries a `_provenance` header naming the commit that produced it and why
it is unrepeatable, above the script's verbatim output. The first is
unrepeatable because the script is gone: its float screen was replaced in
405c9ac. The second is unrepeatable because its INPUT is gone, since it read
data/universe.json as generated at 2026-08-17T00:50 and the Sunday rebuild
overwrites that file weekly. They live under doc/ rather than data/ because
data/ is gitignored and stays that way. This is one comparison preserved for one
entry, not a change of policy about study outputs.

| | 2026-08-16, in CRITERIA | 2026-08-17 re-run |
| --- | ---: | ---: |
| **two point edge** | **0.0004** | **0.0004** |
| **one point edge** | **0.0002** | **0.0002** |
| unrounded two point quantile | 0.00045075 | 0.00045409 |
| unrounded one point quantile | 0.00021475 | 0.00021511 |
| rescued names fitted on | 303 | 300 |
| overlap names | 362 | 363 |
| pays two points | 55.45% | 56.00% |
| pays one point | 12.21% | 11.67% |
| RVOL target | 53.87% / 12.43% | 53.72% / 12.40% |

**The edges survive because the rounding absorbs the drift.** Both quantiles
moved in the fourth significant figure and both still round to the same one
significant figure edge. That is not luck, it is what reading an edge off a
quantile at this precision is for, but it is worth stating that the margin is
real rather than infinite: the two point quantile would have to reach 0.00050
to move the edge, and it sits at 0.00045.

**None of the drift is the screen fix, and that part IS exact.** The screen
change is a pure function of data/float_cache.json and the three CRITERIA
[Float rotation] floors. Running both screens over all 1,870 cached symbols:

| | names |
| --- | ---: |
| admitted by the old screen, refused by the new | 1 |
| admitted by the new screen, refused by the old | 0 |

The single name is YPF, float 51,810 against 392,075,056 shares outstanding,
0.013 percent, refused by min_float_to_shares_outstanding. It is the same name
CRITERIA's float floor note already records as the only one under that line,
which cross checks both implementations. Replaying all 61 session pairs through
the study's own gap ranking, which reads data/backtest/eod/ and not the network,
puts YPF in the top [Scan] candidate_count by gap on ZERO of them. The edges are
fitted on the rescued subset of that population, so a name contributing no rows
to it cannot move a quantile of it. Under one fixed universe the two screens
give bit identical top-N numbers.

**What the drift IS.** data/universe.json was rebuilt at 2026-08-17T00:50, after
the 2026-08-16 study run. The addressable population is computed from the
universe and the EOD cache BEFORE the float screen is consulted, and it differs
on 29 of the 61 sessions, 9,384 rows against 9,390. That is the universe
rebuild, not the fix, and it is measurable precisely because addressable sits
upstream of everything this entry changed. Revised Alpaca history may contribute
on top of it and is not separated here; it does not need to be, because neither
cause is the screen fix and the edges hold under both.

**On the method, and a claim to retire.** An earlier draft of this entry argued
a re-run was impractical, on the grounds that it needs Alpaca volume for the
whole universe over 61 sessions. That was wrong and the project's own probe
already said so. ALPACA_PROBE.md measured the free tier serving a complete
2,745 name 1Min universe sweep in 4 requests and 1.04 seconds, and the
2026-08-17 entry closing Alpaca as a LIVE source is explicit that it "remains
what it already was, a historical reconstruction source for completed sessions".
The re-run cost 463 requests, 567 seconds and ZERO EODHD calls. It should simply
have been run, and was. The population identity proof is kept above because it
is strictly stronger for the question it answers, attributing the drift, which
a re-run alone cannot do.

The screen change is a pure function of data/float_cache.json and the three
CRITERIA [Float rotation] floors. Both screens, the pre-fix one and the
corrected one, were run over all 1,870 cached symbols:

| | names |
| --- | ---: |
| admitted by the old screen, refused by the new | 1 |
| admitted by the new screen, refused by the old | 0 |

The single name is YPF, float 51,810 against 392,075,056 shares outstanding,
0.013 percent, refused by min_float_to_shares_outstanding. That is not a new
discovery: it is the same name CRITERIA's float floor note already records as
the only one below the one percent line, which is a useful cross check that
both screens were implemented as described.

Then the only remaining question is whether YPF is in the population the edges
are fitted to. It is not, and that is decidable offline because the gap ranking
reads data/backtest/eod/ rather than Alpaca. Replaying all 61 session pairs
through the same pool_recall.actual_gappers and addressable_target the study
uses:

| YPF over the 61 cached sessions | sessions |
| --- | ---: |
| raw gapper | 2 |
| addressable | 2 |
| in the top [Scan] candidate_count by gap | 0 |

The edges are fitted on the RESCUED subset of the top candidate_count by gap,
per the 2026-08-16 entry above. YPF contributes zero rows to that population on
every one of the 61 sessions, so removing it cannot move a quantile of it, and
the 303 count, both unrounded quantiles and both payout shares are unchanged
bit for bit. The replay made zero HTTP calls, which the run's own call report
confirms.

**What DOES move, recorded so it is not discovered later and mistaken for a
contradiction.** The study's all_addressable block is a wider slice, n 7,752
rotation rows, and YPF is addressable on 2 sessions, so that block loses at most
2 rows of 7,752 and its numbers shift in the fourth decimal. Those are not the
live bands. The all_addressable re-derived edges are 0.0007 and 0.0002, which
already differ from the committed 0.0004 and 0.0002 precisely because CRITERIA
is fitted on the scored population rather than the wide one, exactly as the
2026-08-16 entry decided. Nothing in CRITERIA reads the all_addressable block.

**The earlier claim that was wrong when written, corrected in place.** The
docstring added to float_rotation_study.py earlier on 2026-08-17 said the counts
in CRITERIA [Score premarket float rotation] "were measured before that was
fixed, so a re-run will not reproduce them to the name". That was written before
anyone checked and it is false: they reproduce exactly, for the reason above.
The docstring is corrected in place rather than answered by this entry, under
the wrong-when-written rule, because a reader who found it would conclude the
committed numbers are stale and would either re-fetch for nothing or distrust
edges that are sound.

**What would make this owed again.** These edges are conditional on [Scan]
candidate_count, as CRITERIA already says: change it and the fitted population
changes and a real re-run is required. A re-run is also required if the float
cache is re-swept, since a new sweep can change more than one verdict, or if any
of the three CRITERIA [Float rotation] floors moves. The cheap proof used here
works only because the population delta was one name and that name was outside
the fitted set. It is a proof about this change, not a standing exemption.

## 2026-08-17, seventh: the rotation bands are fitted on one volume source and applied to another

**The mismatch, stated plainly.** The float rotation score bands in CRITERIA
[Score premarket float rotation] were derived by research/float_rotation_study.py,
whose numerator is ALPACA premarket volume, read from the SIP feed for completed
sessions. The live path that those bands score is
morning/scan.attach_float_rotation, whose numerator is COLLECTOR premarket
volume, folded from the EODHD websocket tape. Two different sources measuring
the same quantity, one setting the edges and the other being measured against
them. The study's own docstring is careful that the two use the same WINDOW,
07:20 to 08:45, and says nothing about them being different SOURCES, which is
how this went unnoticed while the windows were being matched.

**The direction, which is what makes it actionable.** The scoring numerator is
smaller than the fitted one, so live rotation values land below the distribution
the edges were read off, and the bands therefore admit FEWER names than intended.
The fallback under-pays the population it exists for, which is the same failure
recorded on 2026-08-16 second and corrected there by re-fitting on the rescued
population. That entry fixed which POPULATION the edges were read from. This one
is about which SOURCE the numerator comes from, and it is still open.

**How big, and why that is not answered here.** Measured on 2026-08-17 against
EODHD's own 1m bars over identical minutes, collector volume ran at a median of
-88.49 percent, about an eighth of the vendor's figure. If that were the whole
story the gap would be roughly an order of magnitude and the correction
mechanical. It is not the whole story. The same check on 2026-08-14 came back
mixed, with the collector 3.83 times the vendor in aggregate and individual ETFs
up to 50,188 percent high, and the collector's own numbers for one symbol swing
by up to 181x between the two mornings while the vendor's move by 1.1x. The
collector is not merely low, it is not reproducible session to session. The full
diagnosis is doc/research/COLLECTOR_VOLUME.md.

**Decision: record the miscalibration, do NOT re-fit yet.** A re-fit needs a
stable ratio between the two sources and there is no evidence one exists. Fitting
the bands to a numerator that moves by two orders of magnitude between sessions
would bake one morning's accident into a threshold and would be harder to detect
afterwards than the mismatch it replaced. The order is: settle what the collector
is actually doing, then decide whether the honest fix is to re-fit the bands on
collector volume, to correct the collector, or to stop scoring on a number two
sources cannot agree about.

**What this does not change.** The edges themselves stay where they are. Nothing
here says 0.0004 and 0.0002 are the wrong numbers for the distribution they were
read off, and the 2026-08-17 sixth entry establishes that the float screen fix
did not move them. The claim is narrower and worse: the distribution they were
read off is not the distribution they are applied to.

**Where this is visible to a reader who does not open this file.** The study's
docstring names Alpaca as its volume source, scan.attach_float_rotation names the
collector as its numerator source and marks the value a lower bound, and
CRITERIA [Float rotation] describes the numerator as the collector's. None of the
three says the other two disagree. That is why this entry exists.

## 2026-08-18: the report's screen summary is computed by the model, and it was wrong the first morning it mattered

**What happened.** The 2026-08-18 report explained an empty day watchlist with
"the most common failed condition was price not above the prior day high, which
every candidate missed". Every candidate did not miss it. AS.US priced at 34.71
against a prior day high of 33.4194 and cleared that condition; its day_failed
list carries exactly one line, the null premarket RVOL. Counted from the packet,
11 of 12 candidates failed the price condition and 10 of 12 failed the RVOL one.
The mode is right and the universal is false.

**Why the model was in a position to get it wrong.** REPORT_TEMPLATE.md asks for
"one sentence below it saying the day screen produced nothing today and the most
common failed condition". That is a COMPUTED STATISTIC, and the packet does not
carry it. Nothing aggregates day_failed or swing_failed. The model is handed
twelve per candidate lists and asked to report their mode, so it is doing
arithmetic by eye in prose, which is the one thing this project has consistently
refused to let it do everywhere else: membership, eligibility, scores and
conviction are all computed in Python before the model runs.

**Why nothing caught it.** The containment checker validates that every ticker
named in the report exists in the packet. vintage validates that the data is the
session it claims. Neither looks at a numeric or logical claim about the screen's
own output, and there is no third guard that does. So the sentence went out
unchecked.

**Why it matters more than a normal wording slip.** On an empty morning that
sentence IS the report. It is the entire explanation of why nothing was
published, and it pointed at the wrong cause. A reader would conclude that no
name came close, when in fact one name cleared the published gate, scored 8.0
green on an earnings catalyst, and was stopped by a baseline too thin to divide
by. Those two mornings look identical in the report and are completely different
mornings.

**Decision: recorded OPEN with the fix named, not built in this pass.** The fix
is deterministic and small: scan.py counts the failed conditions across
candidates and writes the tally into the packet, and REPORT_TEMPLATE.md tells the
model to QUOTE that tally rather than derive it. That follows the precedent
already set for the watchlist table headers, which were made literal in the
template with a prompt rule pinning them character for character precisely so a
guard would stop depending on the model's word choice. This is the same move
applied to the same class of problem, and it is left for the owner to schedule
rather than slipped into a diagnosis pass.

## 2026-08-18: the float rotation eligibility question is NOT inert, and this morning is the counterexample

**[corrected 2026-08-18: the 2026-08-16 third entry closed by listing the
day-setup eligibility question for names rescued by float rotation as
"unresolved and now inert", on the grounds that "scoring has stopped". That was
wrong when it was written and is corrected here rather than superseded. What it
stopped was the scoring CALIBRATION work, not the publication of scores: the
2026-08-16 fourth entry, written the same day, calls the post-open pass and THE
MORNING CHAIN "the ONLY remaining outputs" after the stop. [corrected
2026-08-18, later the same day: this paragraph first cited the stop's own
"Continuing" list as the thing that keeps the daily report running. That list
names the two probes and the post-open pass, not the morning chain. The morning
chain is named in the next entry, cited above. The conclusion is unchanged and
the citation was wrong.] A
question about which names reach a watchlist that is published every weekday
morning cannot be inert while that publication continues.]**

**The question, as it already stood.** The 2026-08-16 first entry recorded it
deliberately: [Day setup] premarket_rvol still requires a real RVOL, Rule.test(None)
is false, so a name rescued by float rotation is SCORED but is still not
day_eligible. Scoring was the clause being fixed; eligibility was left OPEN.

**The counterexample, 2026-08-18.** AS.US, Amer Sports, reporting earnings before
the open, gapped up 6.57 percent to 34.71 against a prior day high of 33.4194.
It cleared the prior high condition, the gap floor, the price floor and the
market cap floor. It scored 8.0, conviction green, with
volume_measure_used = premarket_float_rotation. Its entire day_failed list is:

    ["premarket_rvol None fails > 1.5"]

and pm_rvol is null because its baseline median premarket volume is 383.5 shares,
under the 1,000 share floor, so the denominator was refused as too thin. The name
traded 37,169 premarket shares, roughly 97 times that median.

**Why this instance is the one that settles the priority.** It was the ONLY one
of the twelve candidates that cleared the prior high test; the other eleven
gapped down and cannot pass a long only screen. So on 2026-08-18 the open
eligibility question was not a marginal case at the edge of the watchlist, it
WAS the watchlist. The published day list is empty rather than holding one green
earnings name, and the difference is entirely this unresolved question.

**Compounding, recorded so the two are not treated separately.** AS.US's float
rotation came out at 0.000264, which earns one point against the 0.0002 edge and
misses two against 0.0004. DECISIONS 2026-08-17 seventh records that the
numerator feeding that number is collector volume, systematically smaller than
the Alpaca volume the bands were fitted on. So the measure that rescued this name
for scoring also under-rewarded it, for a reason already on the record.

**Still not resolved here, and deliberately.** Whether a float rotation floor
belongs in [Day setup] is a threshold question, and thresholds live in CRITERIA.md
and are the owner's. Nothing in this entry changes a screen. What has changed is
that the question now has a dated, concrete instance behind it instead of being
theoretical, and it is no longer described as inert.

## 2026-08-18, third: everything parked on the stop decision, re-checked against its actual scope

**Why.** The 2026-08-16 third entry's own text was wrong about what it stopped,
saying "scoring has stopped" when the morning chain scores every weekday and
what stopped was the scoring CALIBRATION work. That entry has been cited to
close or defer several things, so each citation was checked against what the
decision actually says rather than against the sentence that summarised it.
This is the record of that check, so it is not repeated.

**The decision's actual scope, quoted.** Stopping: the socket purchase; the cap,
ordering and recall work; the scoring calibration including the volume slot and
its bands; any migration to Alpaca for LIVE premarket discovery. Continuing: the
two probes already scheduled, and the post-open pass. The 2026-08-16 fourth
entry adds the morning chain, calling it and the post-open pass "the ONLY
remaining outputs".

| Item parked on the stop | Scope supports it? | Outcome |
| --- | --- | --- |
| The subscription cap table, 42 through 142 | YES, "the cap, ordering and recall work" | stands |
| The second socket purchase and its load test precondition | YES, "the socket purchase" | stands |
| Alpaca as a live discovery source | YES, named explicitly | stands, and 2026-08-17 corroborates it independently |
| The float rotation bands' dependency on candidate_count, called MOOT | PARTLY | corrected in place: dormant, not moot |
| The day-setup eligibility question, called inert | NO | corrected 2026-08-18, with a counterexample |
| The looseness of the RVOL scoring bands, called inert | NO | corrected in place |

**The two that failed, and the single mistake behind both.** Each rested on
reading "the scoring calibration work stops" as "scoring stops". The first is a
statement about what nobody is working on. The second would be a statement about
what the system does, and it is false: the morning chain computes a score and a
conviction for every candidate every weekday and publishes them. So a question
that decides what a published score MEANS is live whatever the roadmap says, and
only a question about what to TUNE NEXT is genuinely parked.

candidate_count is the clearest case. The entry closed its dependency on the
grounds that "nothing will change candidate_count", which the stop does not
guarantee and cannot: it is a CRITERIA knob read every morning by a job that
runs on a schedule. Stopping work on the bands does not freeze the input they
were fitted to. The dependency is one edit away from mattering.

**What this does NOT change.** The three items that survive the check are
untouched, and the stop itself stands entirely. The VWAP measurement that
produced it is unaffected by any of this: four rules losing money, gappers doing
worse than decile matched controls at p = 0.0, pre-registered before the numbers
existed. Nothing here reopens that.

**The rule this suggests, recorded rather than applied.** An entry that closes
other items should say which of them it closes by SCOPE and which by
CONSEQUENCE. All six above were listed the same way, and the two that were wrong
were wrong because a consequence was asserted ("scoring has stopped") that the
scope did not deliver. That is a convention for future entries, not a change to
any existing one.


## 2026-08-18, fifth: what a rejected narrative costs, and who notices

**The decision.** A quantifier flag costs one regeneration, then the narrative,
and never the report. It used to cost the whole morning, and that was set
without ever being chosen: the guard returned exit 2 because every other
containment failure does, and the morning chain stops on the first non-zero
code, so the price was inherited from a check that guards against a different
kind of failure.

**Why the two are not alike.** An invented ticker is fabricated evidence. A
reader acting on it is acting on something that does not exist, and no partial
version of that report is safe to send, so exit 2 with nothing delivered is
right and stays. A quantifier over the candidate set is an UNCHECKABLE claim,
which is a smaller thing: the numbers around it are still true, the tables are
still correct, and the only unsafe part is one sentence. Withholding the
narrative removes that sentence and keeps everything else. Withholding the
report removes everything and keeps nothing, to protect a reader from a sentence
they were never going to see.

**Why one regeneration and not three.** The rejected sentences go back with the
request, so the second attempt is told what to avoid rather than asked to differ
by luck. An attempt that fails after being told is evidence about the report or
about the guard, and a third would be spending the morning's remaining clock on
the hope that a deterministic failure is stochastic. timeout_s is 293 seconds
and the chain starts at 08:45.

**Why the guard does not read the fallback.** Two reasons, and the first is the
one that decided it. The withheld disclaimer quotes the sentence that caused the
withholding, because a reader told the narrative was withheld and not told what
for has been handed a mystery instead of a report, and the person best placed to
say the guard was wrong is the one reading the morning it fired. That quote
necessarily carries the banned pattern. A guard reading it would reject the
fallback and leave the morning with nothing, which is the exact failure this
path exists to prevent. The second reason is that the fallback's claims are
computed in Python from the packet and are true by construction, which is
precisely what the guard exists to establish about the model's.

The fallback's own prose was rewritten into counts anyway, so the exemption
covers only the quoted evidence and never the report's ordinary sentences. That
also fixed a live defect: until today the fallback's own wording tripped the
guard, so an analyst timeout on a morning with an empty screen produced no
report at all. Both halves are kept because either alone would have left the
morning depending on the other.

**Why the watchdog counts the unjudged flags.** The flag log exists so the
guard's false positive rate is counted rather than recalled, and it fills only
if somebody records verdicts by hand. This project has already run the
experiment where a diagnostic raises on schedule and nobody reads what it wrote:
pool_recall did it nightly for a week while DECISIONS cited its evidence as
accumulating. The backlog is therefore surfaced where the jobs are, on the
mornings somebody is already reading, rather than waiting to be asked for. A
flag raised today is named and not called a problem; one that has survived
flag_backlog_after_days of mornings is a backlog and joins the problem count.

**What is deliberately not recorded as a failure.** A morning the regeneration
rescued. The report went out and the narrative is the model's, so job_status
stays ok. Marking it failed would fire the watchdog's STEP FAILED line on a good
morning, and a line that fires on good mornings stops being read, which is the
same decay this whole apparatus is built against. The event is in the flag log
with an outcome of regenerated, in analyst_usage.json, and in the unjudged
count.

**What this does not settle.** Whether the word list is right. That still waits
on judged dispositions, and the outcome split added here is the second input to
it: a word that regenerates away costs a retry, a word that reaches the fallback
costs the narrative, and the two should not be tuned as though they were the
same. `each` and `no` remain the two most likely to move.


## 2026-08-18, sixth: a guard that fires every morning is a guard nobody keeps

**The decision.** The quantifier guard runs in warn mode, logging and printing
and publishing, until the instructions stop asking for the sentences it
refuses. CRITERIA carries the switch and the three conditions for flipping it.

**Why this is not a retreat.** The fifth entry today argued that a flag should
cost the narrative rather than the morning, and made it so. It never asked how
often a flag would fire, and the answer, measured rather than guessed, is every
morning: all three archived reports flag, thirty times between them. A guard
that removes the narrative from every morning is not a guard being strict, it
is a guard that has been mispriced twice, and the second mispricing is the one
that gets it deleted. Warn mode is the price the evidence supports until the
provocation is gone.

**Why warn is the better half of the telemetry, not just the cheaper one.**
The flag log exists so the word list is tuned on data. A log filling under the
current template records which words fire, on which instructions, and how
often. A log filling after T2, T3, T15 and T16 are resolved would record only
that the remainder is quiet, which answers a question nobody asked. Running the
guard loudly while the documents still provoke it is the more informative
experiment, and it happens to be the one that keeps the narrative.

**Why the disclaimer says so.** Warn mode publishes a claim the guard calls
uncheckable. Saying that on the disclaimer line follows the rule the fallback
already follows, that a report which degraded quietly is a report lying about
its own provenance. A published flagged sentence is a quieter degradation than
the plain table, not a smaller one. It also puts the flag in front of the
person best placed to judge it on the morning it fired, which is the standing
difficulty with a log that has to be opened deliberately.

**Why the word list gets one definition rather than four.** Three times in
three commits the instructions asked for what the guard forbids, and each time
the guard was right, the instruction was wrong, and nothing said so until a
report was already written. The watchlist headers had this exact failure and it
was closed by a claim asserting every source agrees, not by anyone resolving to
be careful. So the tuples in analyst.py are the definition and rule 13's
enumeration, the template's wording and the fallback's prose are all checked
against them. The claim carries no copy of the list, because a fixture with its
own copy is a fourth place to drift, which is how three of the four watchlist
header fixtures came to be wrong for as long as they existed.

**Why backticks are the exemption and nothing else is.** These documents have
to teach a phrasing by exhibiting it. An exemption by line number would rot,
one by keyword would be argued about, and one by judgment would not be
mechanical. Backticks already mean "this is text I am showing you, not text I
am saying", they are visible to a reader and to a scanner alike, and a specimen
that will not fit on one line is a specimen that wants shortening.

**Why the instruction scan reads paragraphs where the report scan reads lines.**
Not a difference of principle. The instruction files are hand wrapped, so a
banned word and its set word land on different lines routinely and a
line-at-a-time scan reads past the pair; prompt_analyst.md had exactly that in
its own text. Model output wraps nowhere, so the report scan does not need it,
and changing a live guard's behaviour in the same commit that changes its
enforcement setting would have made tomorrow's flag count uninterpretable. That
asymmetry is recorded rather than defended: if a model ever hand wraps its
prose, the report scan needs the same treatment.

**What was not decided.** T2, T3, T15, T16, P1 and P2. The rewording removed
the banned words from those instructions without answering whether the
instructions should exist. "name the candidates whose pm_rvol is null" asks for
precisely the list "name every candidate whose pm_rvol is null" asked for, and
the empty case still invites a sentence about the whole set, which is why warn
mode is needed and why resolving them is the first condition on the switch.


## 2026-08-19: exempt what a process does, not where it writes

**The decision.** The suite's tree check exempts the meter sampler's behaviour
and not the directory it writes to. Three conditions together: the path is one
of the two files the sampler writes by name, the change is a pure append with
every previous byte unchanged, and the appended bytes parse as what that file
holds.

**Why not exempt logs/.** It is one line of code and it would have worked. It
would also have stopped the check watching the neighbourhood where the meter
trail and the quantifier flag log live, and the flag log is about to become the
evidence the guard's word list is tuned on. An isolation check that stops
watching the file a measurement depends on, in the week that measurement
starts, has been turned off in the only place it currently matters. The cost of
the narrower fix is about a hundred lines and a test module; the cost of the
wider one is a class of contamination nobody would see.

**Why a digest rather than a size.** Because a same length rewrite is the case
that matters. This check's own docstring already carries a correction about
mistaking an internally caused change for an external toucher, and size alone
cannot tell a file that grew by a tick from a file that was rewritten to the
same length. The digest is taken for two paths only, because hashing the whole
tree twice a run would cost more than the check is worth.

**Why the midnight case goes through the same three conditions.** A new dated
trail at 00:00 UTC is a creation rather than an append, and the obvious fix is
a second rule that allows a created file matching the trail pattern. Two rules
about the same thing can disagree, and the second one would be exercised once a
month by a person running the suite late, which is the worst possible test
schedule. It is the same predicate with a zero length previous file, so there
is nothing to disagree with.

**What the claims are for, given the exemption is small.** An exemption nobody
tests is a hole nobody sees. Each claim removes exactly one of the three
conditions and asserts the change is refused, so the exemption cannot quietly
become a filename convention or a directory allowance through a later edit that
looks harmless. Writing them found two intermittents in the new code, both of
which would have presented as the original symptom and been blamed on the
sampler.

**The report scan, recorded and not changed.** Whether the report scan has the
line-wrap hole the instruction scan had is now measured rather than assumed:
zero split sentences across 21 adjacent prose pairs in three reports, with the
model writing prose lines of 207 to 933 characters and wrapping at no width.
The paragraph scan finds exactly the hits the line scan finds on all three. The
hole is real in principle and has not fired. It stays unchanged until the first
week of warn-mode counts is in, because changing a guard's scan in the same
week its enforcement setting changed would make those counts uninterpretable,
and the counts are the reason the setting changed.


**The second toucher, recorded and not fixed.** `.git/FETCH_HEAD` is rewritten
by a timer outside this repository about every ten minutes, as a truncate
followed by a write of byte-identical content, and it failed one of 194
consecutive suite runs. It is the likely identity of the path that could not be
named on 2026-08-18. It is not exempted here, because the obvious exemption,
that unchanged content is not a change, does not cover the zero length window
the rewrite passes through, and covering that means letting an empty file stand
in for its own contents. That is a wider hole than the sampler's and it is the
owner's to open or refuse. Recorded so the next intermittent is compared
against it rather than investigated from scratch.


## 2026-08-19, second: fix what the data proves, measure what it only suggests

**The decision.** Two findings from the same investigation are treated
differently on purpose. The replayed out of window trade is fixed, because the
archived files prove it happens and prove what it costs. The subscription size
is NOT acted on, because the archive only correlates it, and a collector changed
on a correlation is how a measurement problem becomes two.

**What the archive proves.** The subscription replays a last trade per symbol
with its original timestamp. Forty-eight such trades on 2026-08-18, two of them
from the previous session, every one carrying exactly one trade. The damage is
not the 0.27 percent of volume, it is that pm_window_starts_late reads the first
bar present, so a replayed 07:00 print silences the flag that exists to say the
collector only reached 07:20. That is a vintage defect and this project has a
standing rule about those.

**What the archive only suggests.** Every other mechanism for the tenfold
volume gap is dead: sizes are ordinary, messages equal trades folded, no
reconnects, and the rate is flat across the window rather than collapsing. What
is left is that 38 subscriptions produced 171 SPY trades a minute and 50
produced 5.8, with the vendor's own bars moving 1.3x across the same two
mornings. Fifty is the cap. That is two sessions each side and a plausible
mechanism, which is exactly the evidence that feels like enough and is not.

**Why the probe alternates its arms.** Premarket trade rates climb through the
morning. Two consecutive blocks, small then capped, would confound the
subscription size with the clock and produce a number that looked decisive and
meant nothing. Alternating costs nothing and removes the confound.

**Why the probe refuses to run after 07:10.** The fifty symbol pool is account
wide. A probe still holding slots at 07:20 would starve the collector, and the
morning it corrupted would be the morning it was measuring. The refusal is in
the tool rather than in the operator's memory.

**Why the window guard is opt in.** A builder constructed without a window
refuses nothing. The ad hoc evening runs, measure_socket_cost.py among them,
collect outside any configured premarket window, and a guard that applied
itself by default would silently empty their output. The scheduled collector
passes its window explicitly; anything else gets the old behaviour.

**The one that nearly shipped.** The window's open edge was computed to the
microsecond while trade timestamps arrive as whole seconds, so every trade in
the run's first second read as early. The suite's replayed socket refused all
thirty and wrote no minutes. A guard against a defect that costs 0.27 percent
of volume would have discarded the first second of every morning. It floors to
the minute now, which is the granularity bars have anyway.


## 2026-08-19, third: a guard that costs more than what it guards against

**The decision.** A refused subscription is retried on a wait rather than
ending the run. The reasoning that made it fatal was not overtaken by events,
it was wrong when it was written, and it is corrected in place.

**What made it wrong.** It reasoned from the vendor's documentation of the cap
to the conclusion that a refusal must mean another process holds the slots, and
therefore that retrying is futile. Both steps were sound and the conclusion was
false, because the other process it could not imagine was the collector itself.
The cap is account wide and a closed connection keeps its symbols for a while,
so a reconnect one second after a drop competes with its own corpse. Nothing
had ever seen a refusal, so nothing had ever tested the reasoning.

**Why the retry is bounded rather than patient.** Four waits of a minute
against a window of two hours. If the slots are ours they come back inside
about that, measured at 105 seconds this morning. If they are not, the run
fails four minutes later than it used to and nothing else is different. The old
behaviour spent fifty minutes of window to save four.

**Why the collector was restarted by hand.** The window had 48 minutes left,
the watchdog's rerun budget for the day was unused, and a restart is what the
watchdog would have done on its next pass. It also tested the diagnosis: the
restart subscribing cleanly is what proves the slots were the collector's own
rather than a competitor's. A failed restart would have been equally
informative and cost nothing.

**Why the probe's guard moved from an hour to a window.** It was written to run
before the morning and 07:10 was the only free slot, so the hour and the
constraint agreed by accident. When the power took the 06:20 run, the accident
came apart: the hour refused a whole day in which the socket was free from
09:25. The constraint is that the probe must not hold slots the collector
wants, and the collector's configured window is where that is written down.

**Why the probe settles between arms.** Its two arms are two subscriptions on
one account, so arm B asking for 50 while arm A's 8 are still held is the same
collision that killed the collector this morning, and it would have produced a
refused arm measuring zero. A zero from a refusal reads exactly like a zero
from starvation, which is the answer the probe exists to find, so it has to be
impossible rather than unlikely. Refused arms are marked and excluded.

**What today did not settle.** Whether 50 subscriptions starve the feed. Today
is a third session at 50 and SPY still gets about 11 trades a minute against
171 at 38, so the correlation holds at three sessions to one. It is still a
correlation, and the probe still has to run.


## 2026-08-19, fourth: a probe that answers its question and unmakes its premise

**The decision.** The subscription cap is ruled out as the cause of the volume
gap on the strength of a measurement, and the search moves to whether the trades
websocket carries a venue subset while the intraday bars are consolidated. The
correlation with subscription count is withdrawn rather than weakened.

**Why the correlation is withdrawn rather than weakened.** It rested on two
sessions each side and on SPY being right at thirty eight subscriptions. SPY was
not right at thirty eight. It was 373.88% over the vendor's own bars, and TLT
was thirteen times over and DIA ninety five times over on the same morning. A
reading that is an order of magnitude high on one session and an order of
magnitude low on another is not a reading with a cause to find in the
subscription count. Both of those sessions failed the same check that failed the
fifty symbol ones, at 70.95% median absolute difference, and nobody had run the
check across every session at once until today.

[corrected 2026-08-19: this read "Both of those sessions failed the same check
... at 69.77% and 70.95%" and "all four sessions". The 69.77% belonged to
2026-08-13, which is not a premarket session and has since been removed from
every comparison, so the plural was wrong when written. The argument does not
depend on it: 2026-08-14 alone is the session that looked right, and it failed
the same check at 70.95%.]

**Why the probe's negative is trusted this far and no further.** It is trusted
because the mechanism it tested is a throughput mechanism and it was tested
harder than the collector tests it: fifty symbols drawn from the morning's own
list, at fourteen times the collector's message rate, on the densest tape of the
day. A starvation effect should be easier to provoke there, not harder. It is
not trusted past that because the arms are two minutes and the tape is not the
premarket tape, and the collector's own hourly counts, while they show no decay,
are not a controlled pair.

**Why the premarket re run is the next measurement rather than a longer hold.**
The hourly trade counts already argue against a hold length effect: the fifty
symbol mornings are down by about the same factor in their first hour as their
last, so a slow squeeze is not what a two minute arm would be missing. Tape type
has no such evidence against it. Re running the identical script premarket
changes one variable; lengthening the arms at the same time would change two,
and the cheaper discriminator goes first.

**What the answer no longer decides.** The choice this document was holding open
between subscribing to fewer names and splitting across connections is closed on
the first option. Fewer names buys nothing, on the measurement.

**What is still not known.** Why 2026-08-14 over reported. A venue subset
explains a collector that is short and cannot explain one that is long, so the
leading hypothesis for the fifty symbol sessions does not cover the thirty eight
symbol ones, and a single explanation for both has not been found.


## 2026-08-19, fifth: the containment guard cannot see this class, and that is why it needs claims

**The decision.** The five defects found by reading the report against its
packet are fixed at their sources rather than by widening the containment
check, and each is pinned by a claim in the suite rather than by the template
alone.

**Why containment could not have caught any of them.** It checks that every
ticker and number in the report exists in the packet, and all five reports
passed it: 42 claims checked, nothing invented, both tables present. Every
figure in the RVOL sentence was quoted correctly. What was wrong was the
DESCRIPTION around the figures, and a checker built to catch fabricated values
is structurally blind to a true value with a false account of what it measures.
That is not a gap to close in the checker. A general purpose reader of English
claims against JSON is the analyst, which is the thing being checked.

**Why three of the five are fixed in the template and two in Python.** The
split is whether the packet already carried the truth. It did for the funnel
count, the nowhere-else clause and the absent-component sentence, so the model
was narrating past evidence it had and the instructions are what changes. It
did not for is_lower_bound, job_health or the refused run's counters: those
were Python telling the packet something false or nothing at all, and no
instruction to the model could have recovered them.

**Why the drift guard is a literal string check.** It scans the template for
the two sentences the packet contradicts. That is crude, and it fired on the
template's own prohibitions, which quoted the strings they were banning. The
prohibitions were reworded rather than the check loosened, because a check with
an exception is a check that grows exceptions, and the one thing this guard has
to do is fail when somebody writes the sentence again.

**Why a recovered failure is still reported.** A step that failed at 08:16 and
succeeded at 08:37 is a working morning by every measure the packet had, which
is exactly why it was invisible. The reader is not being told the morning is
broken; they are being told what happened to it, and a rerun that fixed it is
the part they would otherwise have to infer from twelve late premarket windows.
The cost of the wrong choice here is asymmetric: a line too many is read and
dismissed in a second, and a line missing is a morning that quietly lies about
the machine.

**What is still not covered.** The report scan for banned words is still per
line rather than per paragraph, deliberately, and still deferred to its own
commit after the first week of warn mode counts. Nothing in this pass touched
it. And no check exists for the general class these five belong to, which is a
correct number with a wrong account of itself. Every one of them was found by
reading, and the next one will be too.


## 2026-08-19, sixth: read the history before spending another morning

**The decision.** The collector's run history is read before the probe runs
again, and the probe's first measurement becomes the off exchange question
rather than a repeat of the cap question.

**Why the history came first.** It costs nothing and it changes what the probe
is for. Had either morning been refused or restarted, the volume disagreement
would have had a mundane explanation already in hand and tomorrow's probe would
have been confirming rather than discovering. Both were single unbroken runs, so
the probe carries the whole question, and that is worth knowing before spending a
premarket window on it rather than after.

**Why the answer is trusted despite half the records not existing.** job_status
cannot speak for 2026-08-14: it was born that afternoon. The collector's own
sidecar can, it is a different file written by different code, and the two
defects fixed earlier today cannot have touched it here because neither morning
was refused. Where the two sources overlap, on 2026-08-17, they agree. Saying
"no record exists" is the honest answer to half the question and the sidecar is
the honest answer to the other half; neither is a guess.

**Why the vendor comparison is a separate command.** The probe runs premarket
and the vendor does not publish a session until it is over, so a fetch from
inside the probe would return zero rows every time and quietly print a shortfall
of one hundred percent. The same thing already happened by hand at 10:05 today.
A command that must be run the following session is a worse workflow and a
correct measurement.

**Why the census records values rather than judging them.** The obvious
alternative was a list of off exchange condition codes and a count of messages
matching it. That list would have been written from the vendor's documentation
rather than from the feed, which is exactly how the refusal guard was written
and exactly why it was wrong for a fortnight. Every code-like value the feed
sends is counted and printed with whether the parser reads it, and the judgement
is left to a reader who can see the codes.

**What has not been decided.** Whether dark_pool_volume is a parser bug or a
column for something the feed never sends. That is the measurement, and it is one
premarket run away.


## 2026-08-19, seventh: a hypothesis measured and refused, and a row deleted rather than footnoted

**The decision.** Replay is recorded as its own tagged row in the bar file
rather than discarded, the observed window and the intended one are carried as
separate packet fields, and 2026-08-13 is deleted from every comparison rather
than annotated in place.

**Why the two mechanism verdict is not stated.** The audit was set up to test
whether replay owns the over counting while the off exchange question owns the
under counting. It does not. Excluding every pre subscription bar moves
2026-08-14 by nothing and the other two sessions by about half a point. Stating
a two mechanism verdict anyway would have been fitting the frame to the data,
and the frame was worth testing precisely because it was checkable.

**Why the 2026-08-14 zero is reported as a limit rather than a result.** That
session predates both the job_status collector record and the subscriptions
file, so the only subscription time available is the configured one, and its
first bar falls in exactly that minute. The audit cannot see replay there. A
zero in that cell means the measurement was blind, and writing it as a finding
would be the same error as reading a missing counter as a count of none, which
this project made twice today already.

**Why replay is written to the bar file rather than to a sidecar of its own.**
The rows belong with the minutes they were mistaken for, and a separate file is
one more thing to remember to read. The protection is the tag plus a single
filter in read_bars_file, which every consumer already goes through, so a new
consumer gets the filtering by default and has to ask for replay by name. A
sidecar would invert that: safe by default only for readers who know it exists.

**Why the intended start is kept rather than replaced.** pm_window_start was
always derived from the bars. What was missing was anything beside it saying
what it was being judged against, so a reader could not see the two disagree
without knowing CRITERIA by heart, and the fields that DID quote the schedule,
the RVOL basis and the provenance membership line, asserted it as though it were
an observation. Both are needed and neither may stand in for the other.

**Why 2026-08-13 is deleted and not footnoted.** A row in a comparison table
gets counted whatever the note beside it says. It survives in the run history
and tape window tables, labelled, because those are the evidence for the
deletion and neither is a comparison.

**What is now unexplained.** The 2026-08-14 over count. It is 3.8x in aggregate
and 12.7x on TLT against the vendor's own bars, replay does not account for it,
no collector code change landed between that session and the next, and the
subscription cap was measured innocent. It has no candidate mechanism, and it
should not be quietly dropped for that reason.
