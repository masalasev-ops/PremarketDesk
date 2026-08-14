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
