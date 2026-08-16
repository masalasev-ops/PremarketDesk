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
extended on 2026-08-17 to measure it against the live morning. Adopting Alpaca
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
