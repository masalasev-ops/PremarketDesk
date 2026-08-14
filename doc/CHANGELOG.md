# Changelog

Dated entries, newest first. Appended to, never rewritten. What belongs here is
what changed and why it had to; the reasoning behind a choice that could have
gone another way belongs in DECISIONS.md, and every threshold belongs in
CRITERIA.md.

Errors of fact are corrected in place and carry a `[corrected YYYY-MM-DD: was
X]` marker; superseded decisions keep their original text and are answered by
a later entry. A number that was wrong when it was written is not history, it
is a mistake, and leaving it standing means the next reader measures against
it. A number that was right when it was written and has since been overtaken
is history, and rewriting it destroys the reasoning.

This file starts at 2026-08-14. Everything before it is in doc/BUILD_PLAN.md
and in the git history.

## 2026-08-14, fourth: the isolation guard is inverted, and two numbers distributed

### The isolation check photographs the tree

The check that proves the suite wrote nothing outside its sandbox used to name
the roots it watched, and gained one per escape: runs/, then data/, then the
database, then site/ when the entrypoint tests caught build_archive rewriting
the published archive. Four fixes, each correct about the root it had just
been taught and blind to the next. That is what a check written as a list of
what to guard does.

It is inverted now. `conftest.snapshot_tree()` photographs every file and
directory under the repository before the suite and again after, and anything
that appears, disappears or changes outside a two entry allowlist,
`__pycache__` and `.pytest_cache`, fails the run and is named.

**The numbers.** The tree-wide photograph covers **1,379 paths**. The
enumerated version watched **275** of them. The other **1,104 paths were the
exposure**, and they include every one of src/, doc/, tasks/, logs/, .git/ and
the virtual environment. That is what could have been written to by a test
that hardcoded a path, at any point before this entry, without the suite
saying a word.

Directories are tracked for existence but not for mtime, because a directory's
mtime moves whenever anything inside it is created and an allowed
`__pycache__` write would otherwise fail the run through its parent. A new
directory still fails, so a test creating runs/2026-08-15/ is caught before it
writes anything into it.

`--prove-check` still writes to runs/ and still fails, naming the file.
`--prove-check-outside` is new and writes to tasks/, a root no version of the
enumerated check ever watched: it fails too, which is the point.

### The mains that were returning zero without recording

pool_recall got `job_status.failed()` in the previous entry. Auditing every
other main that returns zero on an exception path found six more, and the list
is written down here rather than quietly closed, because the size of what the
status record was missing is the useful part:

1. **collect_premarket**, on `KeyboardInterrupt`. A collector stopped at 08:10
   produced a genuine file covering half the window and exited zero. Nothing
   distinguished that from a quiet morning.
2. **discover**, when `load_metrics` could not read the universe. It catches
   every exception and continues with empty metrics, which does not stop the
   pool being built, it stops it being ranked: every name falls to the fallback
   band and the cut becomes arbitrary. This was the worst of the six.
3. **discover**, when a pool source raised. It was recorded in watchlist.json
   as `not_fetched` with its reason, which is the right place for the audit
   trail and the wrong place for a human to find out that the morning is being
   built from three priors instead of four.
4. **gap_stats**, which has always returned the list of symbols it could not
   fetch, and whose main has always thrown that list away. Every symbol could
   fail and it exited zero.
5. **build_archive**, on an unreadable packet.json. The session is archived
   without its counts, which is how the archive quietly stops being the record
   it exists to be.
6. **monitor_jobs**, on an unreadable rerun state file. It reads as "nothing
   has been rerun today", which silently stops `max_reruns_per_job_per_day`
   being enforced and lets a hard failure loop.

Every exit code is unchanged. Only the record changed. Where the failure is
per item rather than fatal, the trigger is producing nothing at all, which is
unambiguous and needs no threshold to judge.

test_entrypoints forces the calendar guard to raise and asserts both halves:
it still exits zero and still assumes the market is open, and it now records
the RuntimeError. That guard runs at the head of five of the six jobs, so it
was five of the twelve silent step invocations on its own.

### The watchdog reads step records, not only the final marker

The nightly reported OK every night for a week with pool_recall failing inside
it, because the marker it reads belongs to the archive and the archive really
did finish. `monitor_jobs.failed_steps()` now reads every status record for a
job on the day and reports the job as failed naming any step that recorded
one. A step that failed and was later rerun successfully is not reported,
because the last record is the one describing the state the machine is in now.

The marker check stays exactly as it was. The two answer different questions: a
step record catches a step that failed, and a marker catches a job that died
before writing any record at all. Both cases are asserted, including a nightly
killed before the archive, which writes no pool_recall record and would be
invisible to the step check alone.

### Screen passes, distributed

6.57 is a mean over a population whose gapper counts run 42 to 518 a session.
The socket decision was resting on it and on the 12.33 and 15.62 beside it.

| cap | min | p25 | median | mean | p75 | max |
|---|---|---|---|---|---|---|
| 42 | 0 | 2 | 5.0 | 6.6 | 11 | 25 |
| 67 | 0 | 3 | 7.5 | 9.8 | 15 | 38 |
| 92 | 0 | 4 | 8.5 | 12.3 | 18 | 54 |
| 142 | 0 | 5 | 9.5 | 15.6 | 23 | 70 |

The median differs from the mean materially and it steps differently. On means
the four caps go +3.2, +2.5, +3.3, which is the flat decay the record
described. On medians they go +2.5, +1.0, +1.0. The median to mean ratio falls
as the cap rises, 0.758, 0.765, 0.691, 0.609, which says extra slots pay off
disproportionately on sessions that were already busy: tripling the cap takes
the typical morning from 5 publishable names to 9.5 and the busiest from 25 to
70. At every cap the minimum is 0, so no amount of capacity buys a report on
the emptiest mornings.

**The socket arithmetic does change.** On means the third socket buys 58
percent of what the second buys and reads as a smaller version of the same
deal. On medians it buys 29 percent: the second socket adds 3.5 publishable
names to a normal morning, the third adds 1.0. The second remains the better
purchase either way, which is unchanged. The DECISIONS cap item carries the
distributions and three correction markers.

`backtest_pool` reports `screen_passed_distribution` alongside the mean, and
`blindspot` already reports its own after the previous entry.

## 2026-08-14, third: silent failure is made impossible, and two numbers close

pool_recall failed on every nightly run for a week and left nothing anybody
would see. The fix for that one step landed with the documentation
reconciliation below. This entry is about the question that mattered more:
how many other steps could do the same, answered by inventory rather than by
guessing, because guessing which ones were exposed is what produced the bug.

### What every scheduled step did when it failed, before this entry

Six .bat files, twenty one step invocations, sixteen distinct modules. The
"trace" column asks whether a failure would reach a human, not whether it
appeared anywhere: every step writes its exit into a dated log, and the whole
point of the pool_recall week is that a traceback in `logs/nightly-*.log` is
not a trace if nobody reads that file.

| Job (trigger) | Step | Exit code | main catches | Read downstream | Entrypoint test |
|---|---|---|---|---|---|
| universe (Sun 20:00) | universe | checked, stops job | RuntimeError | universe.json, by everything | none |
| universe | gap_stats | checked, ends job | none, propagates | gap_stats table, by discover | none |
| discover (07:15) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| discover | discover | checked, stops job | StaleUniverse, QuotaRefusal, RuntimeError | watchlist.json, by collector, baseline, scan | none |
| discover | baseline | checked, ends job | none, propagates | baseline table, by scan | none |
| collector (07:20) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| collector | collector | checked, ends job | KeyboardInterrupt | the bar file, by scan, backfill | none |
| morning-chain (08:45) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| morning-chain | scan | checked, stops chain | StaleUniverse, QuotaRefusal, StaleDataError | packet.json, by analyst, verify | none |
| morning-chain | analyst | checked, stops chain | none, propagates | report.md, by render | none |
| morning-chain | render | checked, stops chain | none, propagates | report.html, by deliver, archive | none |
| morning-chain | verify | IGNORED, by design | none, propagates | nothing, it prints a table | none |
| morning-chain | deliver | checked, stops chain | none, propagates | nothing | none |
| morning-chain | archive | checked, ends job | none, propagates | nothing | none |
| nightly (22:15, 07:00) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| nightly | backfill | checked, stops job | none, propagates | picks columns, by outcomes | none |
| nightly | outcomes | checked, stops job | none, propagates | picks columns | none |
| nightly | pool_recall | IGNORED, by design | Exception, returns 0 | NOTHING | none |
| nightly | archive | checked, ends job | none, propagates | nothing | none |
| monitor (07:25 x5, 22:45) | calendar | exit 3 only | Exception, returns 0 | the .bat's skip branch | none |
| monitor | monitor | checked, ends job | none, propagates | its own rerun state | none |

**Twelve of the twenty one could fail without leaving a trace**, across eight
modules. The calendar guard is five of the twelve on its own: it catches every
exception and returns 0 so a guard fault cannot kill a real morning, which is
right, and it then proceeds on an assumption nobody is told about. The rest are
pool_recall, verify, gap_stats, the collector, backfill, outcomes and the
watchdog. Two patterns produce all of them: a main that returns 0 on a path
that did no work, and an output nothing downstream reads.

**The last column is the finding.** Not one scheduled entrypoint had a test.
Every suite tested a function underneath one. That is not an accident of this
codebase; a pure function is easy to test, so it gets tested, and the wiring
where a rename can strand a name does not.

**And there was a fourth concealing layer, not three.** The watchdog checks
each job's final step marker, and the nightly's is the archive, which runs
after pool_recall and really did finish. So the nightly reported OK every
night while the step inside it wrote nothing. That layer is correct and stays:
a watchdog that failed the nightly because a diagnostic died would be worse.

### Every job now records whether it succeeded

`src/job_status.py`. Every scheduled step appends one line to
`data/job-status.jsonl` as it exits: job name, start and end in ET, status,
exception type, and one count of what it produced. Written in a `finally`
block, catching BaseException, so a collector killed with Ctrl-C and a nightly
killed by a reboot both record dying. The `.bat` files set `PMD_JOB` so a
record says which job the step ran under, and a hand run records `manual`.

The exit code is unchanged everywhere. `job_status.failed(reason)` is how a
step keeps its zero and corrects its record: pool_recall calls it in the
handler that swallows its exception, so the chain still cannot break on a
diagnostic and the failure still reaches the morning. The calendar guard calls
it when it assumes the market is open after an error, and the analyst calls it
when the narrative falls back to the numbers only report.

Staleness is counted in trading sessions, not hours, so a weekend cannot raise
a false alarm and a Tuesday holiday cannot hide a real one. Windows are in
CRITERIA.md [job status steps], one per step, 1 for a weekday job and 5 for
the two that ride the Sunday schedule. A step with no success at all is
reported only once the record file itself is older than that step's window,
because nothing can be overdue before there was anywhere to record it, and a
line naming every step on the day this landed would have taught the reader to
skip it.

The morning report gains one line naming any overdue step, and nothing at all
when every step is current. It is written by `analyst.annotate_job_health` in
Python, appended to the disclaimer line the template guarantees, rather than
asked of the model in the prompt: the one morning a model forgets a prompt
rule is the morning it mattered. Past four overdue steps the line stops
listing them and says the machine or the schedule has stopped, naming the
worst few, because sixteen named steps is one problem rather than sixteen.

### Tests cover entrypoints now, not only the functions beneath them

`src/test_entrypoints.py` drives all sixteen scheduled entrypoints through
their own `main`, with the arguments the `.bat` passes, against the sandbox
roots. The HTTP client is stubbed with a scripted session that records every
path, so each step asserts the endpoints it actually asked for. Two steps
reach the outside world through something other than the HTTP client and are
stubbed at the equivalent layer, both marked in the file: the collector's
socket, replayed through `_connect` with one deliberately silent symbol, and
the analyst's claude CLI, stubbed at `invoke_claude`.

Every entrypoint is also asserted through its status record, which is what
catches the pool_recall shape specifically. Its exit code is zero whether or
not `build()` worked, by design, so a test asserting the exit code would have
passed all week. The record is what tells the two apart.

The suite also checks the CRITERIA.md step list against the list of steps it
drives, in both directions. A step the scheduler runs that is missing from
that list would never be reported overdue, which is the one way the whole
mechanism can fail silently.

**It found a sandbox hole on its first run.** `build_archive` built its output
path as `config.PROJECT_ROOT / "site"` rather than reading it from config, so
the sandbox could not redirect it and the suite rewrote the real published
`site/PremarketDesk.html`. The mtime check did not catch it because it watched
`runs/` and `data/`, where the previous three escapes happened. `config.SITE_DIR`
now exists, conftest redirects it, and run_tests photographs it too.

### The collector reports its own coverage

Monday is the first morning at fifty subscriptions and the socket has only
ever been load tested at thirty eight, which was the old thirty plus eight
configuration. The collector now writes
`data/premarket/<date>-subscriptions.json` at subscribe time, before the first
trade, listing what it asked the socket for. It has to be written then: the
run stats sidecar is appended when the collector stops at 09:25, forty minutes
after the packet is built.

The packet gains `collector_coverage`: the count requested, the count that
produced at least one bar, and the names of any that produced none. A symbol
that was subscribed and stayed silent is a different failure from one that was
never subscribed, and both now appear, the second as
`unsubscribed_with_bars`. With no subscription list the block says so rather
than reporting every absent symbol as never subscribed.

`peak_trades_per_minute` comes off the bars, which already carry a trade count
per minute, so nothing was added to the receive loop. On the 2026-08-14
snapshot at thirty eight symbols that peak was 5,697 trades in a minute. The
late trade count is not there: it lives in the running builder and is only
written when the collector stops, so it stays null with that reason recorded
rather than being filled from a previous run.

### The two gapper counts reconcile, and neither was wrong

The blindspot stage implied 173.7 gappers a session while the backtest and the
live pool_recall both gave 99 for 2026-08-13. There is no definitional
difference: both stages read the same `outcome["gappers"]` object out of the
same cache file, built once by the fetch stage with the same `> 3` rule on the
absolute gap, so both directions count, measured as the session open against
the prior session close, over the same 2,745 name universe in every session.

The distribution explains it. Over the sixty cached sessions the count runs
42, p25 91, median 142, mean 173.7, p75 236, max 518. It is strongly right
skewed, so the mean sits well above the typical session, and 99 is rank 40 of
60, in the lightest third.

What made 2026-08-13 look like it should be heavy was its earnings calendar:
37 names before the open against a median of 6.5, the 9th heaviest of the
sixty. On the other two sources it is light, rank 48 of 60 on overnight news
and 53 of 60 on prior session movers. Earnings weight and gapper count
correlate at 0.465, so a heavy calendar does not imply many gappers, and
"heaviest calendar day" and "heaviest day" are not the same claim. No figure
needed correcting. `blindspot` now reports the distribution rather than the
mean alone, because a mean is a poor summary of a 42 to 518 spread.

### Corrections are marked

The four numbers corrected in place on 2026-08-14 now carry
`[corrected 2026-08-14: was X]` markers naming what they said before, and both
records state the rule at the top: errors of fact are corrected in place with
a marker, superseded decisions keep their original text. The DECISIONS item
citing pool_recall as accumulating evidence nightly is corrected to say the
evidence began accumulating on the date the fix landed.

## 2026-08-14, second: the documentation was reconciled and it found a bug

Five commits in one day changed discovery, pricing, ranking, the schedule and
the schema, and the documents were audited against the code rather than
against memory. Every document was read by a separate auditor and every claim
it raised was verified against the source before being acted on: 114
discrepancies confirmed, 11 refuted and left alone.

**The audit found a live bug, which is the part worth recording.**
pool_recall.build referred to a name, `floor`, that had been renamed to
`gap_rule` when the gap threshold moved from a number to a rule. The signature
and the one comparison were updated and three later uses were not, so every
nightly run raised NameError before writing anything. Nothing caught it: main
caught RuntimeError only, the nightly batch file ignores that step's exit code
by design so a diagnostic cannot fail the chain, and the only test exercised
pool_recall.measure, the pure function, never build, the one the scheduler
calls. So the measurement that DECISIONS.md cites as "accumulating the evidence
nightly" had accumulated nothing.

Fixed, and the hole it came through closed with it. main now catches Exception
and always prints the type, because a diagnostic that fails silently is worse
than no diagnostic. test_pool.py gained claim 8, which runs build end to end
against a stubbed client and a synthetic universe and asserts the file is
written with the right arithmetic in it: one gapper, recall 0.0, the missed
name listed.

**What else was wrong.** Both architecture pages predated all five commits.
CRITERIA still documented `max_quote_age_hours` and `run_after`, two keys with
no readers left, and described the bulk live deduplication and the live-first
market snapshot as though either still ran. REPORT_TEMPLATE and the analyst
prompt still told the model to report `collector_covered false`, a state that
can no longer reach the packet because drop_uncovered removes those candidates
before enrichment. The README described a low effort analyst measured at 65 to
78 seconds, a self check that prints a TLS line it does not print, and a
trading day guard on every job including the Sunday one that does not have it.
tasks/README listed five jobs and missed three steps. BUILD_PLAN said five
scheduled jobs and a 233 second timeout.

Four numbers in the append-only records were wrong when written and were
corrected in place, since a record that misstates its own measurement is not a
record: pool_recall makes two bulk calls not one, sixty sessions cost sixty two
bulk days not sixty one, 109 of 355 null-propensity gappers is 31 percent not
half, and the 88 percent miss is the whole miss rather than the cap's share,
which splits about 50 points to the cap and 38 to the pool's reach. The
collector load test figure of 38 symbols was the OLD configuration, 30 plus 8,
and the current cap already asks for 50, which makes the throughput
precondition on the cap decision stronger rather than weaker.

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
held, the recall fraction, and the names it missed. Two bulk end of day
calls, today's and the prior session's, because the gap is measured open
against prior close and one call carries only one of them.
[corrected 2026-08-14: was "one bulk call"]

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
sessions cost sixty two bulk days rather than a hundred and eighty, a session
needing its own day, its prior and the one before that.
[corrected 2026-08-14: was "sixty one bulk days rather than a hundred and
twenty"; sixty two is what the fetch actually spent, and three days per session
over sixty sessions is a hundred and eighty, not a hundred and twenty]

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

### The measured ordering was adopted

within_tier_key is gap_propensity and min_slots_per_tier is 4, both in
CRITERIA.md with a citation rather than a seed marking: the sweep window, the
session count, the out-of-sample date and the recall of the chosen
configuration against the one it replaces. Replayed under the shipped
configuration the 60 cached sessions give 0.1164 mean subscribed recall against
0.0842 for the dollar volume key it replaces, and 0.0893 for that key given the
same floor.

The harness gained a SHIPPED configuration that ranks through
discover.rank_value rather than a copy of it, so the row that claims to measure
production moves when CRITERIA moves.

### Null propensity falls back to ATR

gap_propensity needs 100 sessions, and newly listed names are over-represented
among hard gappers: SECZ gapped 25.6 percent on 2026-08-13 with a null
propensity. within_tier_fallback is atr_pct_20d, which needs only 20 sessions.
A name with neither sorts last and discover records the count.

It did not improve anything measurable, and it did not cost anything either:
with the fallback the sweep gives 0.1164, bit identical to plain propensity.
The reason is in the same table: only 0.2 subscribed names per session lack a
propensity, so the band the fallback reorders is almost always empty. Kept
under the clause that says keep it if it does not lose. Under the dollar volume
key that count was 1.3 per session, so the fallback would have mattered more to
the ordering it replaced than to the one it serves.

### Two new evaluate metrics

**screen_passed**, the count of subscribed names that would have cleared the
replayable part of the CRITERIA day screen, not merely gapped. Recall counts
names that moved; this counts names the morning could have published, which is
what the product is made of. The shipped configuration gives 6.57 per session
against 5.77 for dollar volume. Only gap_pct, price, market_cap and
require_above_prior_high are applied: premarket_rvol cannot be replayed for a
historical session because there is no premarket tape for names that were never
subscribed, so this is an upper bound on the real screen and SCREEN_SKIPPED in
the module says so.

**subscribed_without_primary**, the per session count of subscribed names the
ranking key cannot score, which is what says whether the fallback is doing
anything.

### Test isolation became structural

src/conftest.py redirects every writable root, sourced from config so a test
cannot bypass it by building a path itself, and rebinds the six module level
constants that captured one at import time. src/run_tests.py wraps the suite in
it and photographs the real runs/ and data/ before and after, failing on any
difference. Deliberately not a pytest conftest: pytest is not a dependency and
requirements.txt is three lines on purpose.

The full suite now runs with 203 files under the real roots before and 203
unchanged after. `run_tests.py --prove-check` appends a test that writes
straight to the real runs/ and the run fails naming the file, so the check is
demonstrated rather than assumed.

The audit that came with it found the lock problem was not one function. Three
sites held a transaction across a network call: gap_stats.build, fixed earlier;
baseline.warm, which held one across an intraday call per ticker for up to
fifty tickers at 07:15; and fill_outcomes, which held one across an end of day
call per pick. All three are now read, then fetch, then write. baseline.ensure
was a fourth, latent: nothing calls it any more, and it opened a session and
recursed so that compute() ran inside the transaction. Cleared as network free:
backfill_premarket at both sites, baseline.get, baseline `--show`,
discover.recent_runners, gap_stats.load_all, scan.attach_premarket_rvol,
scan.write_picks and store.init.

### The null-propensity question is closed

The ATR fallback tying told us about the subscribed set, where only 0.2 names a
session lack a propensity. That is not the same question as how much of the
target population propensity structurally cannot see, so the target population
was measured directly: `backtest_pool.py blindspot`, cache only, no fetch.

Across the 60 cached sessions, 10,424 universe names gapped beyond the floor.
355 of them carried a null propensity, a fraction of **0.0341**, ranked with the
2026-05-18 window the sweep used. Against the 2026-08-13 window, by which the
same names have another sixty sessions of history, it falls to 230 and
**0.0221**. Those two bracket the real figure, because the shipped system
recomputes weekly and so sits between them.

Per session the null fraction runs from 0.005 to 0.143 with a median of 0.034,
which is 5.9 unreachable gappers out of 173.7. History of the null ones, in
sessions, on the earlier window: 169 had under 10, 34 had 10 to 24, 43 had 25
to 49, and 109 had 50 to 99. Those 109 are 31 percent of the 355, and they are
the ones within a couple of months of crossing the 100 session line on their
own; the 169 with under 10 sessions are a year away from it.
[corrected 2026-08-14: was "so half of them are within a fortnight or two";
109 of 355 is 31 percent, and at 50 to 99 sessions of history they are months
short of the line rather than a fortnight]

The fraction is small, so the question is closed on the first of the two
conclusions: the fallback stays as inert insurance, and no reserved allocation
for short-history names is proposed. The arithmetic that settles it is that
capturing every one of those 5.9 names would add at most 3.4 points of recall.
Set against the same sixty sessions, the shipped configuration reaches 0.1164
of the gappers, so 88 points are missed in total: about 50 of them because the
pool held the name and the cap cut it, and about 38 because the pool never held
it at all.
[corrected 2026-08-14: was "a cap that currently misses 88 percent of gappers
for want of slots"; 88 points is the whole miss, and only about 50 of it is the
cap. Attributing all 88 to slots overstates what buying capacity would buy]
The binding constraint is the cap, which is already the open item.

### The lock rule is enforced rather than audited

store.assert_no_open_transaction is called at the HTTP chokepoint before any
request goes out, and raises TransactionHeldError if any live connection has a
write transaction open. It reads sqlite3's own in_transaction through a
registry of connections store.connect handed out, so nothing depends on a
caller declaring its state. That matters because three of the four sites found
by audit looked innocent and the fourth held its transaction behind a
recursion, where no lexical scan could reach it.

sqlite3.Connection cannot be weak referenced, so connect() returns a
_TrackedConnection subclass that can, and the registry holds those weakly so a
closed connection drops out on its own.

src/test_txn_guard.py asserts three things: a request under a deliberately
opened transaction raises and names the endpoint; a connection that has only
read is not a transaction and does not trip it, while the same connection does
the moment a write begins one; and the whole morning chain runs clean, having
made 42 guarded requests and tripped none.

The nine sites cleared by the earlier audit are now enforced rather than
inspected, and so is every path nobody has read yet, including ones not yet
written.

### Packet schema

New keys: `build`, `vintage`, `dropped_no_coverage`. New candidate fields:
`price_time`, `price_source`, `pm_volume`, `prior_close`, `prior_source`,
`gap_reason`, `pm_rvol_basis`, and the `selection_*` group replacing the
candidate `price`, `prior_close` and `gap_pct` that the bulk feed used to
write directly. New market snapshot fields: `as_of` on every row,
`prior_session_only`, `prior_session_date`.

There is no SCHEMA.md in this repository to record that in. Noted here instead.
