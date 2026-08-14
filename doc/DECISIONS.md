# Decisions

Choices that could reasonably have gone the other way, with the reasoning that
settled them and the date it was settled. Appended to, never rewritten. When a
decision is reversed, the new entry says so and the old one stays where it is,
because the reasoning that turned out to be wrong is the part worth keeping.

What changed and when is in CHANGELOG.md. Every threshold is in CRITERIA.md.

This file starts at 2026-08-14. Earlier reasoning is in doc/BUILD_PLAN.md and
in the commit messages.

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
deliberately, with pool_recall now accumulating the evidence nightly.

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

**Nothing changes yet.** The shipped ordering stays as it is, and the 8/14
replay is byte identical to d224837 to prove it. Replacing a seed value with a
measured one is its own change, so that the measurement is citable at the point
of the edit rather than recorded a commit away from it. This item stays open
until that change is made.

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
