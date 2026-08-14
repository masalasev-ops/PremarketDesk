# Changelog

Dated entries, newest first. Appended to, never rewritten. What belongs here is
what changed and why it had to; the reasoning behind a choice that could have
gone another way belongs in DECISIONS.md, and every threshold belongs in
CRITERIA.md.

This file starts at 2026-08-14. Everything before it is in doc/BUILD_PLAN.md
and in the git history.

## 2026-08-14

### The bulk real-time endpoint lags a session, and nothing noticed

The first fully scheduled live morning ran clean, exit zero at every step, and
published a report describing the previous session.

`/real-time/{any}.US` returns the last COMPLETED session. At 08:45 ET on a
trading day the last completed session is yesterday, so the endpoint's `close`
is yesterday's close and its `previousClose` is the close before that. The
scan read the first as this morning's premarket price and the second as the
prior session close. Confirmed against EODHD's own end of day history for all
twelve candidates: twelve of twelve `prior_close` values equalled the 08-12
close, and eleven of twelve `price` values equalled the 08-13 close to the
cent.

Four fields were corrupted by that one read:

- `price`, which was the prior session's close rather than a premarket print.
- `prior_close`, which was the close of the session before that.
- `gap_pct`, computed between those two, which was therefore the prior
  session's own move. ARX was published at "gap +43.35 percent" when its real
  premarket gap that morning was +0.38 percent, and WDAY at +17.78 percent
  when its real gap was +0.14 percent.
- `pm_rvol`, whose numerator was the delayed quote's `ethVolume`. That field
  describes the previous extended session until the vendor rolls it, measured
  on this date as after 08:45 and before 08:56. At 08:45 it gave ARX
  20,744,130 shares of yesterday's post market.

`prior_high` was the only one of the group that was right, read from end of day
history and correctly dated to the prior session. That is what made the failure
visible: `price` and `prior_high` were both from 2026-08-13, so the
`require_above_prior_high` gate compared a session's close against its own
high, which can never pass. Both watchlists were structurally guaranteed empty,
and the report explained it as a dull tape.

Fixed by sourcing every published price from the collector, which is the only
feed on this plan carrying today's premarket, and by reading `prior_close` and
`prior_high` out of the same end of day record so they cannot drift apart
again. The bulk endpoint is kept for membership only, where ranking 2,745 names
in one call is a thing nothing else can do, and every field it produces is
named `selection_*` and overwritten before scoring. See DECISIONS.md.

### A vintage assertion that ends the run

Nothing in the pipeline had ever asked whether the data was from today, so
nothing objected. `src/vintage.py` now asks, after pricing and before scoring,
and a violation ends the run: the gate marker is rewritten naming every failing
row and scan exits non-zero, which stops the morning chain before the analyst
call. There is no degrade path, because a stale price is not thin evidence to
hedge around.

Four checks. (a) every priced candidate's price timestamp falls inside today's
premarket window. (b) `prior_high` is not below `prior_close`, since a session's
high cannot be below its own close. (c) the prior close is dated to the prior
trading session per the exchange calendar, not merely to some earlier date.
(d) the market snapshot is from today, where a row explicitly labelled
`prior_session_only` is held instead to being correctly dated to the prior
session.

Check (b) alone would have caught this morning without a single vendor call:
six of the twelve candidates carried a `prior_high` below their own
`prior_close`. Replaying that packet through the check now fires (a), (b) and
(d), leaves (c) silent because that field was in fact correct, and names all
six impossible rows in the marker file. `src/test_vintage.py`.

### A floor under the RVOL denominator

`usable_for_rvol` accepted any baseline with enough sessions and a median above
zero. ARX's premarket median was 23.5 shares and MH's was 10, so the ratio
built on them was arithmetic without meaning: ARX scored an RVOL of 882,728 and
maxed the RVOL scoring band by construction. Six of the twelve candidates sat
below the new floor.

`min_baseline_premarket_volume = 1000` shares, in CRITERIA.md under Baseline
next to its sibling `min_sessions_for_rvol`, which is the threshold it works
with and the function that reads it. A seed value chosen to exclude degenerate
denominators, not a validated threshold. Below it, `pm_rvol` is null with the
reason recorded and the RVOL component is unavailable, which routes through the
existing `score_partial` and `score_unavailable` machinery from 2758972 rather
than a second path: the total goes null, the conviction bucket goes null, and
the report says unscored.

A floor on the denominator, not a cap on the ratio. A cap would have turned
882,728 into a plausible looking number and hidden the fact that the
denominator was never usable.

### Containment went dark exactly when it mattered

`claims_checked` was 0 and `columns_scanned` was 0. Both screens were empty, so
the model omitted both watchlist tables entirely, and the tables are where the
guard finds the `Ticker` header it locates claims by. Meanwhile the report
named twelve tickers in bold prose, none of them validated. The check reported
a clean pass over a report it had not read.

Two changes, folded into the existing containment path rather than a second
one. REPORT_TEMPLATE.md and prompt rule 12 now require both tables to be
written even when empty, header and separator and a single `| none | | | |`
row, and the deterministic fallback report does the same. And containment now
extracts ticker shaped tokens from prose as well as table columns: a report
with prose ticker claims and no ticker column at all is a structural failure,
returning 2, not a pass with a footnote.

Prose is ambiguous where a Ticker column is not, so time expressions and ISO
dates are stripped before tokens are taken (`06:37 ET` is a time, and ET is
also Energy Transfer) and a stopword list in CRITERIA.md removes what survives.
That list contains some real tickers and is a recorded fail-open; see the prose
stopword note there.

### Also

- Candidates the collector never subscribed to are dropped rather than priced,
  named in the packet's new `dropped_no_coverage` list with a reason, and
  counted in the run summary. See DECISIONS.md.
- `packet.json` carries `build`, the resolved commit and a dirty flag, so a
  report can be tied to the code that wrote it.
- A null `gap_pct` no longer reads as a checked zero in the eligibility test,
  which would have produced "gap_pct 0.00 fails > 3", a claim about the stock
  made out of a fact about the pipeline.
- The gate table in verify_morning.py now shows the price and the minute it
  printed, alongside the collector premarket volume that feeds RVOL. The
  failure that made the gate earn its keep was invisible without a clock beside
  the price.

### Discover stopped ranking a stale feed and started building a pool

The stale vintage fix above repaired what the 08:45 scan did with its numbers.
It did not touch where the names came from. discover.py was still calling the
bulk /real-time endpoint at 07:15, ranking the whole universe by its gap, and
keeping the top 30, so it was still ranking the previous session's movers. The
collector only ever subscribes to what discover chose, so every morning's
evidence was still being gathered for the wrong names before the scan ran.

Gap ranking is gone from discover. Nothing there reads a price from today,
because at 07:15 no source on this plan has one for the whole universe.
Selection is now a prior assembled from four things knowable before the open,
unioned, deduplicated, and intersected with universe.json:

- **earnings before open today**, from the calendar API. EODHD supplies
  before_after_market and a report_date but no clock time, so a 07:00 reporter
  and an 08:30 reporter are not distinguishable in this feed. The field is
  recorded as the vendor gives it and timing_precision says so.
- **overnight news**, from a symbol-less sweep of the news feed over the window
  from 16:00 ET the prior day to the run clock, paged and bounded, with each
  name carrying the timestamp of its newest item.
- **prior session movers**, from two bulk end of day calls so the move is close
  to close. This is the input the pool always had, now labelled as the
  continuation prior it is rather than mistaken for today's gap.
- **recent runners**, from the picks table, weighted by a per session decay so
  three days ago outranks three weeks ago.

A source that fails records not_fetched and a source that succeeds with nothing
records fetched_and_empty, the distinction catalyst_why already draws, so a
pool missing its earnings names is never mistaken for a morning without
earnings.

The pool is ranked by tier, then by 20 day average dollar volume descending,
and cut at max_subscribed_candidates, seeded to 42 so it fits the collector's
50 socket slots alongside the 8 context tickers. Everything below the cut is
written to watchlist.json marked not_subscribed, so the cut is auditable.

At 08:45 the pool tier becomes a recorded field and nothing more. scan ranks
the subscribed names by the gap it actually measured from the collector, so a
tier 5 recent runner with the morning's biggest move ranks first. pool_source
and pool_tier are carried into the packet and the picks row.

Cost: two bulk end of day calls at a measured 98 counted calls each, one
calendar call and up to five news calls, against the one bulk live call at 100
that this replaces. About 100 counted calls a morning more, far below the
bulk_redesign_line.

### pool_recall, and what it already says

The nightly pass reads today's end of day for the whole exchange, works out
which universe names actually gapped at the open against their prior close,
and writes runs/<date>/pool_recall.json: how many gapped, how many the pool
held, the recall fraction, and the names it missed. One bulk call, which that
pass was making anyway.

Backtested against 2026-08-13, whose real gappers are known:

- 99 universe names gapped beyond the 3 percent floor at the open.
- The pool held 72 of them. Recall 0.727.
- The 42 actually subscribed held 28. Recall 0.283.
- All 28 hits came from tier 1. Of 37 subscribed earnings names, 28 gapped.
- The five tier 2 slots that remained went to MU, NVDA, AAPL, MSFT and AMD by
  dollar volume. None of them gapped.

So the pool finds the gappers and the cut throws most of them away, and the
dollar volume tiebreak is what throws them: inside the news tiers it sorts
toward the largest names in the market, which are the least likely to gap.
On 2026-08-13 that cost little because 37 earnings names filled 37 of the 42
slots. On 2026-08-14, a light calendar with 2 earnings names, it would have
spent 40 of 42 slots on mega caps. The tier ordering is marked in CRITERIA.md
as a seed and an assumption about base rates; this is the first measurement
against it and it says the assumption is wrong below tier 1.

### The recall harness moved into the repository

The tool that produced the 2026-08-13 recall numbers was a scratchpad script.
It is the instrument that decides the tier ordering, so it is now
src/backtest_pool.py, version controlled and tested, and split into two stages
that never run together.

**fetch** reconstructs one historical session's inputs, the earnings calendar,
the overnight news sweep, the prior session end of day and universe membership,
together with its outcome, the open against the prior close for every universe
name. Both go to a cache keyed by session date under data/backtest/. This is
the only stage that touches the network.

**evaluate** reads the cache and nothing else, applies a named ordering
configuration, and reports pool recall, subscribed recall, per tier hit rates
and the missed names. src/test_backtest.py arms every outbound path to raise
and then runs every ordering to completion, so the zero network claim is
asserted rather than asserted-to.

The split is the point. Fetching is slow, dated and expensive enough to afford
once; evaluating is free and will be run once per ordering candidate, and every
comparison has to come from the same bytes. Bulk end of day is cached per day
rather than per session because consecutive sessions share it, so sixty
sessions cost sixty one bulk days rather than a hundred and twenty.

From cache alone the harness reproduces the published 2026-08-13 figures
exactly: 99 gapped, pool held 72 at 0.7273, subscribed held 28 at 0.2828.

### Gap propensity, measured rather than proxied

src/gap_stats.py computes, for every universe name over a trailing 250
sessions, the fraction of sessions whose open sat beyond the discovery gap
floor from the prior close, the median absolute gap on those sessions, and 20
day ATR as a percent of price. It rides the universe rebuild schedule in
tasks/job_universe.bat, so nothing is computed at 07:15.

Rows are keyed by (ticker, as_of), which is what lets a backtest rank on a
window that ended before its earliest session instead of one that includes the
sessions being scored. A name with fewer than min_sessions of history stores a
null propensity and its real sessions_used, never a computed zero: a name
nobody has measured and a name that has not gapped in a year are different
facts, and order_pool sorts nulls last within their tier rather than as zero.

Measured cost: 2,745 symbols in 2,745 counted calls and 421 seconds, zero
failures. 2,708 measured and 37 null at the 2026-08-13 window.

### Sixty sessions cached

60 consecutive trading sessions from 2026-05-19 to 2026-08-13, spanning a full
quarterly earnings cycle so the sweep sees the heavy calendar case and the
light one rather than whichever the last fortnight happened to be. 62 bulk end
of day days, 27MB, under data/backtest/, which is gitignored.

Cost: the meter moved 52,888 to 62,736, so 9,848 counted calls, but the gap
propensity run overlapped it and the shared key has a sibling consumer, so that
figure is an upper bound rather than an attribution. The harness's own ledger
records 373 HTTP calls for the fetch: 58 bulk end of day at a measured 98
counted each, plus 249 news, 58 calendar and 8 others, which puts the fetch's
own share near 6,000.

The fetch checks the preflight every ten sessions and stops cleanly if the key
drops to the degrade threshold, reporting how many sessions were cached. A
partial cache is usable; evaluate takes whatever sessions it finds.

### Also

- test_store.py wrote to the live database, so it failed with "database is
  locked" whenever a real job held a write transaction, which is a fact about
  the machine rather than about the code under test. It now runs against a
  throwaway database, the same reasoning as the runs/ sandbox added to
  test_scrub.py.
- gap_stats.py held one write transaction open across two thousand HTTP calls,
  which is what locked the database. It now fetches first and writes once.

### Packet schema

New keys: `build`, `vintage`, `dropped_no_coverage`. New candidate fields:
`price_time`, `price_source`, `pm_volume`, `prior_close`, `prior_source`,
`gap_reason`, `pm_rvol_basis`, and the `selection_*` group replacing the
candidate `price`, `prior_close` and `gap_pct` that the bulk feed used to
write directly. New market snapshot fields: `as_of` on every row,
`prior_session_only`, `prior_session_date`.

There is no SCHEMA.md in this repository to record that in. Noted here instead.
