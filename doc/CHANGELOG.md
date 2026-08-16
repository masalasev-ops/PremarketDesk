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

## 2026-08-16, fourth: the rotation bands are re-derived on the right population, and the schedule leaves the quota boundary

### The float rotation bands were fitted to names that never receive them

The bands added earlier today were matched to RVOL's payout on the OVERLAP, the
names carrying both measures. Those names are scored by RVOL and never reach
the rotation bands. The only names that do are the rescued ones, and they sit
materially lower: median ratio 0.6115 on the scored population and 0.4587
across all addressable.

So `> 0.0006 / >= 0.0003` paid full marks to 45.87 percent of the rescued names
against a 53.87 percent target, an 8 point shortfall in the direction that
penalises a name for having no history. That is the exact bias the alternatives
design existed to remove.

Re-derived on the rescued population: **`> 0.0004` and `>= 0.0002`**, paying
55.45 and 12.21 percent against a target of 53.87 and 12.43. Both distributions
and the edges' percentile position in each are in DECISIONS.md 2026-08-16
second.

Recorded with it: the edges are conditional on [Scan] candidate_count, because
the scored population is the top N by gap and rotation rises with gap size. The
two slices genuinely disagree about the direction of the fix, and the note in
CRITERIA says which one governs and how to re-derive.

### The overlap count reconciles

The earlier entry quoted 362 where the coverage table implied 5,282. Both are
right and they are different quantities: 5,282 is every addressable gapper with
both measures, 362 is that intersection restricted to the top candidate_count
by gap. The earlier entry gave the restricted number without naming the
restriction. `paired_n_all_addressable` is now measured directly and comes to
5,282, matching the coverage table exactly.

### The Monday probe records the lag, not just the outcome

`probe_alpaca_live` now writes a per sweep table of wall clock, newest bar
timestamp anywhere in the universe, the observed lag between them, that lag
against the documented 15 minutes, and the count of names with any premarket
bar plus its growth since the previous sweep. Whether the feed works decides
whether the design is possible; the lag decides what freeze time is achievable
and therefore what the report can contain, and a feed that works an hour behind
is the 2026-08-14 defect wearing a different vendor's name.

The table is rewritten to `data/probe-alpaca-live-table-<date>.md` after EVERY
sweep rather than once at the end. The run spans nearly two hours of a morning
that cannot be repeated and a crash at 09:00 must not take the first ninety
minutes with it.

Added `--dry-run YYYY-MM-DD`, which sweeps a completed session at five pinned
clock times. This probe gets exactly one Monday, so the plumbing was exercised
against 2026-08-14 first: the active count climbed 1,461 to 1,845 across the
morning and every column filled. The lag reads 0.0 there by construction, since
the bars were complete before the pinned clock reached them, and the written
table carries a loud banner saying so, because a zero minute lag is exactly the
number that gets quoted later by someone who did not read what produced it.

### The packet's build block is now asserted, not just written

scan.py has built a `build` block carrying the commit and a dirty flag into its
payload since 2026-08-14, and `write_packet` writes the whole payload, so live
packets do carry it. Nothing tested that it survives to the file. The existing
claim tested `config.build_identifier()` in isolation, which keeps passing if
the key is dropped from the payload or the writer stops writing it.

Neither runs/2026-08-13/packet.json nor runs/2026-08-14/packet.json has the
key, because both predate the line, and 2026-08-14 is the morning whose report
could not be tied back to the code that produced it. New claim in
test_entrypoints reads the packet off disk and fails if the block is absent. A
NULL commit is allowed, since an export with no .git is a legitimate way to run
this; what must not happen is the key being missing, because then the packet
cannot even say that it does not know.

### No scheduled job fires at the quota reset any more

The EODHD counter resets at 00:00 UTC, which is 20:00 ET in daylight time and
19:00 in standard. The Sunday universe rebuild was registered at 20:00, the
exact reset instant for half the year, so which quota day it billed to was a
race. It is the largest single job in the schedule, buying lookback_sessions
bulk calls in one run, and losing that race means spending them against a
counter that has been accumulating since the previous evening.

Moved to 20:30 in both `register_tasks.ps1` and the live task, which clears the
boundary in both halves of the year. Every other job is a morning or late
evening step and none sits near either reset time.

## 2026-08-16, third: a name with no baseline can be scored, and two probes are set for Monday

Three pieces of work, one of which changes what the morning publishes.

### Float rotation fills the volume score slot when RVOL cannot

**The defect.** `pm_rvol` divides by a cached baseline, so it is null for any
name nobody has baselined. A null component made the whole score null, which
meant a name appearing for the first time arrived UNSCORED, and a first
appearance is often exactly the morning it is worth looking at. Measured over
61 cached sessions: 2,615 of 8,302 addressable gappers, 31.5 percent,
unscorable for want of history rather than for want of evidence.

**The fix.** `premarket_float_rotation`, premarket volume over shares float,
computed in scan.py beside pm_rvol from the same collector numerator and
carrying the same lower bound flag. It needs no history. The two are scored as
ALTERNATIVES filling one slot: RVOL when available because it is the better
measure, rotation otherwise, and only a candidate with neither is unscored.
The unscorable population falls from 2,615 to 145, down 94.5 percent.

The component is NAMED for whichever measure filled it, so the breakdown says
what made a name scorable, and `volume_measure_used` carries the same fact
under a stable key. Both land in picks, because a null pm_rvol beside a real
score reads as a bug unless the row says rotation stood in.

**The denominator costs nothing.** `sharesFloat` was already in the
us-quote-delayed response scan reads marketCap from. `sharesOutstanding` was
added to the kept fields purely so the float can be sanity checked against it.

**The bands are matched, not chosen.** Setting them from the rotation
distribution alone would have followed the instruction and still been a defect:
the two measures share one slot, so unmatched bands make the slot pay
differently depending on which measure filled it, and a name would score
differently for the mere fact of having no baseline. The edges are read off the
rotation distribution at the quantiles reproducing what the RVOL bands pay, on
the 362 names where both measures exist. RVOL pays two points to 53.87 percent
and one to 12.43; `> 0.0006` and `>= 0.0003` pay 54.42 and 12.71. Full
distribution in DECISIONS.md 2026-08-16.

**Two limits, recorded rather than buried.** [Day setup] `premarket_rvol` is
unchanged, so a rescued name is SCORED but still not day_eligible; scoring was
the clause and eligibility is left OPEN. And the matching inherits RVOL's own
calibration, which looks loose on this population at two points for 53.87
percent of the names it scores. That is recorded as an open question rather
than fixed quietly, because changing it moves every score in the table.

**Supporting work.** `research/float_cache.py` caches sharesFloat for the 1,870
distinct addressable gappers, once, at about one credit each, refusing to start
if the quota meter cannot cover it. `research/float_rotation_study.py`
reconstructs RVOL from Alpaca over the same window the live path uses and
produces the distribution above. Neither is a live dependency and neither is
imported by anything that runs in a morning.

### Silence and absence are not the same thing, and only one vendor can tell them apart

Prompted by the question of why an untraded stock is worth watching at all. The
reasoning is right about the stock and wrong about 8 percent of gappers:
measured over 20 sessions, 177 of 2,244 addressable UP gaps, 7.89 percent,
printed NOTHING between 04:00 and 08:30 and still gapped at the open. Nine of
those were 10 percent or more. The largest were re-checked against the raw tape
rather than the cache, so they are not artifacts.

That 7.89 percent is a ceiling on the product, not a vendor problem: no feed
shows a trade that did not happen.

The vendor problem is the other half. A name cannot be known not to have traded
unless something watched it, and with 50 slots against 2,745 names the other
2,695 are indistinguishable from names that did not trade. EODHD REST cannot
separate the two in premarket, since it returns the previous close for
everybody. Alpaca can, since bars come back only for symbols that printed.
Reasoning and numbers in DECISIONS.md 2026-08-16. NOT ADOPTED pending the probe
below.

### Two probes are registered for Monday 2026-08-17

`probe-live-v1` at 07:55 was already set. `probe-alpaca-live` is new, at 07:25,
sweeping the whole universe every five minutes from 07:30 to 09:20. It settles
what doc/ALPACA_PROBE.md could not: that probe ran on a Saturday against a
completed session, so it proved historical access and said nothing about a live
morning, and the whole argument above rests on the live case. It spends no
EODHD quota, taking prior closes from Alpaca daily bars, so it cannot compete
with discover or the scan for the shared counter.

### Test changes

`test_repricing` claim 4 asserted the unavailable component was named
`premarket_rvol`. It is now `premarket_volume`, the neutral name meaning the
slot was never filled, so the claim was updated rather than the code bent to
keep it. New claim 9 covers the clause directly: a first appearance name with
no baseline gets a numeric score, the breakdown names float rotation as what
made it scorable, RVOL still wins the slot when both exist, both float guards
refuse to divide, and a name with neither measure still scores null.

## 2026-08-16, second: every hand invokable writer under runs/ is guarded, not just the collector

The first pass guarded `snapshot_bars`, which was the tool that proved the
hazard. Two others had exactly the same shape and were left open:
`pool_recall --date` overwrites `runs/<date>/pool_recall.json` and
`backfill_premarket --date` overwrites `runs/<date>/verify_intraday.json`.
Both now route through `core/artifacts.py`.

**The owner rule, and why it is PMD_JOB rather than the date.** The obvious rule
is "a past date is spared". It is wrong here. backfill's 07:00 catch-up pass
legitimately fills YESTERDAY as part of the schedule, so a past date rule would
break the nightly rather than protect it.

The real distinction is whether the scheduler or a human is running the module,
and the project already had a name for that: the .bat files set `PMD_JOB` and a
hand run records `manual` in the status record. `artifacts.scheduled_run()`
reads that same variable, so there is one definition of "was this the
scheduler" instead of two that can drift. A scheduled run owns what it writes
and rewrites it freely. A hand run is spared unless it passes `--overwrite`.

Measured both ways on the same command against a past session:

    pool_recall: REFUSED to overwrite runs/2026-08-14/pool_recall.json
                 (13,229 bytes, written 2026-08-14 22:15:31)
    pool_recall: wrote runs/2026-08-14/pool_recall.handrun.json instead.

    PMD_JOB=nightly
    pool_recall: REPLACING runs/2026-08-14/pool_recall.json (13,229 bytes)

**The test names the modules.** Rather than assert behaviour for the three that
exist today, the claim reads each module's source and fails if a writer under
runs/ never calls `artifacts.resolve`. A fourth tool that forgets is the whole
failure mode returning, and it should fail the suite rather than wait for
someone to notice a missing artifact months later.

`tasks/README.md` records the ownership rule next to the existing PMD_JOB note.

## 2026-08-16: the suite is swept against six frozen calendars, and what that found

**Why.** test_entrypoints was green Monday to Friday and red on a Saturday, and
was written on a Thursday. That is a class rather than an incident: trading day
guards, staleness counters that count sessions rather than days, and the quota
day boundary are all calendar sensitive, and nobody knew how many assertions
moved with the date.

**The instrument.** `run_tests.py --freeze YYYY-MM-DD` pins the ET date and runs
the clock forward from 09:00 at real speed. It patches `ettime` on the module
rather than reading an environment variable, because the shipped code must not
grow a way to lie about the date, and nothing in src/ binds those functions
directly so replacing them reaches every caller.

The clock SHIFTS rather than stops, and that detail was learned the hard way.
The first attempt froze it outright, and the suite hung with a zero byte log:
`run_websocket` spins on `while ettime.now_et() < stop_at`, and a now() that
never advances never leaves that loop.

**The sweep.** Six calendars, identical conditions.

| Frozen date | Day | Result |
| --- | --- | --- |
| 2026-08-10 | Monday | PASS |
| 2026-08-12 | Wednesday | PASS |
| 2026-08-14 | Friday | PASS |
| 2026-08-15 | Saturday | PASS |
| 2026-08-16 | Sunday | PASS |
| 2026-09-07 | Labour Day, a market holiday | PASS |

**Finding one: no day of week dependence remains.** The only genuine one was
the calendar guard's ok_codes living in a `__main__` line no importing harness
executes, fixed earlier the same day. Saturday and Sunday now pass where the
suite was previously red on a Saturday, so the sweep is also the check on that
fix.

**Finding two, and it nearly went into this file as the wrong thing.** The
holiday run first FAILED, taking test_scrub and test_txn_guard with it:

    StaleUniverseError: universe.json was generated at 2026-08-13T11:51:26-04:00,
    which is 24.9 days ago. The limit in CRITERIA.md is max_age_days = 10.

Recording that as holiday dependence would have been wrong. A control run on
2026-09-08, an ordinary Tuesday one day further out, failed identically, and
2026-08-21, a Friday eight days from the fixture, passed. The dependence is on
DISTANCE from a fixed fixture stamp, not on the calendar.

That mattered more than a mislabelled entry. Every holiday in the cached
exchange calendar is more than ten days from the fixture, the nearest being
2026-07-03 at forty days before and 2026-09-07 at twenty five days after, so
the holiday case could not be examined at all. The honest report would have
been "holiday never tested", not "holiday fails".

**The fix.** With `--freeze` active, the sandbox copy of universe.json is
restamped to one day before the frozen clock, which removes the distance
variable and leaves the calendar as the only thing changing. The real fixture
is never touched: config.DATA_DIR is already redirected when the restamp runs.
Both the holiday and its Tuesday control now pass, so a market holiday is
genuinely exercised for the first time.

**No test needed renaming.** The clause asked that any test which must depend
on the day say so in its name. None does. What the sweep found was a fixture
age dependence in two suites, which should never have been date sensitive, so
it was injected rather than labelled.

**Standing caveat.** The sweep pins the date and fixes the hour at 09:00. It
therefore says nothing about TIME of day dependence, which is a separate class
and is not measured here. The monitor's rerun windows and the collector's stop
time are the obvious candidates.

## 2026-08-15, second: a refused subscription ends the collector instead of being printed and ignored

**The bug.** `{"status_code":422,"message":"Symbols limit reached"}` carries
neither `s` nor `p`, so it fell into the branch that handles authorisation and
status frames, printed `collector: server said {...}`, and returned. The run
then continued to its stop time subscribed to nothing, folded zero trades,
wrote an empty bar file and exited zero. Nothing downstream could tell that
apart from a quiet morning: the log ends with rc=0, the status record says ok,
and the packet simply has no premarket data.

**Why it is worse than it looks.** Measured on 2026-08-15, the 50 symbol pool
is ACCOUNT WIDE, not per connection as the vendor documents. Two sockets were
opened on the same token; the first took 25 and the second took 25, and the
second was then refused while holding only 25 of its own supposed 50, with the
account at 50. A separate run had one socket accept 50 and refuse at 75.

So a refusal does not mean "this socket asked for too much". It means another
process on this token is holding slots: a probe, a hand run collector, a second
scheduled instance. Any of those silently costs the whole morning.

**The fix.** A new `SubscriptionRefused(RuntimeError)`, raised the moment a
fatal status frame arrives. It is deliberately NOT a `ConnectionError`,
`OSError` or `WebSocketException`, because those three are exactly what the
reconnect loop catches and retries, and retrying is the wrong response: the
slots are held by someone else and every reconnect is refused again until the
window is gone. The test asserts the class is none of those three, so the bug
cannot come back wearing a reconnect.

`main` catches it rather than letting it propagate, so the log carries one
sentence instead of a traceback and the run stats are still written, then exits
1. A run that was never subscribed must not report success, and the morning
chain must not treat its bar file as a window.

Non fatal status frames are no longer only printed. `run_websocket` collects
them and the returned stats carry `status_frames` and the first ten of
`status_frames_seen`, because a morning that saw six odd frames and still
worked is a different morning from a clean one.

**Why now.** The rotation design under consideration, subscribing 50 at a time
and cycling the universe, issues roughly 440 subscribe frames in a morning
rather than one. A design that talks to the subscription endpoint 440 times
cannot sit on top of a refusal that fails silently.

## 2026-08-15: the two suite failures attributed, one real defect and one instrumentation defect

Both failures on HEAD were treated as evidence rather than as broken tests, and
they turned out to be different animals. The distinction matters for how much
the rest of the status records can be trusted, so each is labelled.

### backfill: A DEFECT THE INSTRUMENTATION SURFACED. The guard was right.

`TransactionHeldError: an EODHD request to intraday-1m was attempted with 1
open database transaction(s)` was a genuine read-fetch-write violation, the
fifth site, and the lock audit's four did not include it.

The mechanism, in `backfill()`. The loop held one `store.session()` open across
its whole body. Each iteration called `_true_path`, which spends one intraday
request, and ended with an `UPDATE`, with `commit()` only after the loop. So the
UPDATE at the end of iteration N opened a write transaction that was still open
when iteration N+1 made its network call, and a run over ten picks held the
write lock for the sum of ten HTTP requests. Any other writer meets `database
is locked`.

Why the lexical scan missed it is worth recording, because it is a different
blind spot from `baseline.ensure`, which hid behind a recursive call. Here the
network call and the write are both plainly visible in the same block. The
violation is not in their order within one iteration, where the fetch correctly
precedes the write. It is in the order ACROSS iterations, where the write wraps
around to the next fetch. A scan that reads a loop body once, in the order it is
written, sees fetch then write and passes it.

Fixed by splitting into three explicit phases: read and close, fetch with no
connection open, then reopen and write. The `picks` rows are materialised into
dicts because they now outlive their connection, and the DDL from
`ensure_columns` is committed before the read phase exits so no transaction
survives into the fetch.

Implication: the runtime guard caught something nine lines of careful reading
did not. That argues for trusting the other status records MORE, not less.

### calendar: AN INSTRUMENTATION DEFECT, in the test harness only.

`calendar recorded status 'failed', expected 'ok'` was not the calendar step
failing at anything. The step exited 3, `EXIT_CLOSED`, which is correct: 2026-08-15
is a Saturday.

The shipped entrypoint has always been right. `market_today.py` ends with
`job_status.run("calendar", main, ok_codes=(0, EXIT_CLOSED))`, so a closed
market records `ok` in every real run. No live status record was ever wrong,
and no weekend or holiday has ever been misreported.

The defect was in `test_entrypoints._drive`, whose docstring claims it runs each
entrypoint "the way the scheduler runs it" and which called
`job_status.run(step, module.main, argv)` with no `ok_codes`, taking the default
`(0,)`. The harness reaches the module and calls `main()` directly, so anything
declared inside the `if __name__ == "__main__":` line is invisible to it. A
literal in that line cannot be tested by a harness that never executes it.

This was latent and day-of-week dependent. `EXIT_CLOSED` is only returned when
the market is shut, so the suite was green Monday to Friday and red on a
Saturday. It was written on a Thursday.

Fixed by making the codes a module constant, `market_today.OK_CODES`, read both
by that `__main__` line and by `_drive` through
`getattr(module, "OK_CODES", (0,))`. Any future entrypoint with non-default
codes is now covered without touching the harness. `market_today` is currently
the only module in the project that passes `ok_codes` at all.

### test_repricing: neither. Self-inflicted, and repaired.

Recorded because it touched a committed artifact and because the hazard is
general.

While testing `price_from_collector` on 2026-08-15 I ran
`collect_premarket.snapshot_bars('2026-08-14', ...)` against the existing run
directory. That function is not read-only: it re-copies the live collector file
over the snapshot. It replaced the frozen 08:45 artifact, 1,419 bars ending at
08:43, with the full trading day, 2,155 bars ending at 09:24.
`test_repricing` reads exactly that file, so all eleven of its expected gaps
drifted and the suite went red for a reason unrelated to any code change.

Restored by filtering `data/premarket/2026-08-14.jsonl` to
`minute_epoch <= 08:43`. The reconstruction is exact rather than approximate:
it yields 1,419 lines, matching `collector_snapshot.bars_total` in that
morning's `packet.json`, and ARX returns to 37 bars closing 19.5842, the value
measured from the original before it was overwritten.

The general hazard: `snapshot_bars` mutates the run directory it is pointed at.
Running it against a past session to reproduce a bug destroys the frozen
evidence that session's tests depend on. It has no dry-run mode and nothing
warns.

## 2026-08-14, seventh: src/ is organised into packages by role

Forty files sat flat in src/: production modules, tests, one off probes and
measurement scripts, indistinguishable from each other. They are now eight
packages, and src/ itself is the import root.

| package | what belongs there |
|---|---|
| `core` | config, criteria, ettime, store, eodhd. Infrastructure everything rests on; nothing here knows what a gapper is. |
| `ops` | job_status, market_today, monitor_jobs. Whether the machine is running correctly. |
| `selection` | universe, discover, gap_stats. Which names are worth watching, decided before the open. |
| `collect` | collect_premarket, baseline. Today's tape and the baseline its RVOL is measured against. |
| `morning` | scan, vintage, analyst, render_report, verify_morning, deliver. The 08:45 chain in order. |
| `night` | backfill_premarket, fill_outcomes, pool_recall, build_archive. |
| `research` | backtest_pool, probe_live_v1, the two measure_ scripts. Instruments, not pipeline. |
| `tests` | conftest, run_tests and the nine test_ modules. |

**Module names did not change, only where they live.** `import config` became
`from core import config`, so every `config.X` usage in the codebase stayed
valid and the change was about 200 import lines rather than a rewrite of
thousands of call sites. That was the whole point of choosing this shape over
a renamed package hierarchy.

Scripts run as `python -m package.module` with `PYTHONPATH` set to src, which
is what every `.bat` now does. Running a file by path would put its own
package directory on `sys.path` instead of src, and every import would fail.

**The one genuinely dangerous edit** was `config.PROJECT_ROOT`. It was
`Path(__file__).parent.parent`, and config.py moved down a level, so it would
have silently pointed every writable path at src/ instead of the repository.
It is now spelled out in three named steps rather than chained, with a comment
saying why.

Verified before commit: every module imports in its new home; all 24 module
invocations across the seven `.bat` files resolve; `job_monitor.bat` runs end
to end through real Task Scheduler semantics and writes its dated log; nine
suites pass; both sandbox escape provers still fail correctly; `criteria.py`
resolves every key; and `config.build_identifier()` still finds `.git`.

One first run after the move reported a single changed path that could not be
captured and has not reproduced across five subsequent runs, including a
deliberate cold run with every `__pycache__` deleted. It left nothing behind
in the working tree. Recorded as unexplained rather than attributed, since the
last thing recorded as a transient in this project turned out to be a real
defect of our own making.

## 2026-08-14, sixth: everything outstanding, in the order it had to run

### The news window counts trading sessions

Production built the overnight news window from a calendar day and
`backtest_pool` from the prior trading session. They agree from Tuesday to
Friday and are two days apart on a Monday, which is when it costs most: a
calendar day back from Monday is Sunday 16:00, so the window never reached
Friday's close or anything published across the weekend. Both now call
`discover.news_window_start`, and the drift, not either choice, was the defect.

**Twelve of the sixty cached sessions were affected**, eleven Mondays and the
Tuesday after Memorial Day, each losing 48 or 72 hours. The conclusion
survives without qualification, because the cache was always built on the
corrected window: the backtest used the prior trading session from the start,
so the ordering was measured correctly and only production drifted. A re-run
reproduces the recorded figures exactly, 0.1164 for propensity against 0.0893
for dollar volume, with tier hit rates 0.56, 0.37, 0.40, 0.35.

### The universe write is atomic, and a partial one is refused

`universe.json` is written to a sibling `.partial` and renamed with
`os.replace`, which is atomic on both platforms, so a reader sees the whole
previous file or the whole new one. The Sunday job has never fired, its
roughly 4,700 calls bill to Monday's quota day on a key another project took
50,199 of 100,000 from, and a refused or interrupted run is a real
possibility.

Age was already enforced by `load_universe` through `max_age_days = 10`, so no
second threshold was added for it. What is new is `check_admissible`, which
compares the count against `previous_count` carried in the file itself, under
`min_count_fraction_of_previous`, seeded at 0.5. A stale universe is a usable
input and every later script knows how to refuse one. A half written one is
not, and nothing could tell them apart.

### An unranked pool is not cut

When `load_metrics` could not read the universe, discover still built the pool
and still cut it to 42, but every name sat in the fallback band with no key,
so the subscribed names were arbitrary and the morning looked entirely normal.
Below `min_ranked_fraction_to_subscribe`, seeded at 0.5 against an observed
0.98, discover now records the failure, writes no watchlist and exits non
zero. A missing report is recoverable; a plausible one built from a random
sample is not, because nothing downstream can tell it from a real one.

### A price inside the premarket window can still be hours old

The vintage gate asks whether a price is from today's premarket session, which
a 07:22 print satisfies perfectly while being 83 minutes stale at 08:45. That
is exactly what a collector killed at 08:10 leaves. Every candidate now
carries `price_age_seconds` against the scan clock, and beyond
`max_price_age_seconds`, seeded at 900, it drops into `dropped_stale_price`
with its own reason. Counted separately from `dropped_no_coverage` because the
fixes differ: a subscription slot versus a socket that went quiet.

`collector_window_observed` puts the first and last bar beside the scheduled
window, with `minutes_since_last_bar`, so a truncated morning is visible in
the packet that morning rather than in a status record the next day.

### Zero examined is never a pass

`probe_live_v1` printed "Every reading is from today" over a log of nulls. It
now computes its denominator before any branch that could conclude, and an
empty one reports EXAMINED NOTHING. The rule is in DECISIONS.md, and this was
the fifth instance of one shape in three weeks.

**The audit found a sixth, in the machinery written yesterday.**
`job_status.report_line(rows=[])` returned None and
`monitor_jobs.failed_steps` returned an empty list when no step had recorded
anything, so an absent record file read identically to sixteen healthy steps,
in the mechanism added because the other two sources of truth had agreed on a
lie. Both now report the empty case: the morning line says nothing has
recorded anything at all, and the watchdog reports NO RECORDS as its own
verdict rather than folding it into OK. `failed_steps` returns
`(failures, records_read)`, so no caller can mistake the two again.

180 guards were audited against the rule across all sixteen scheduled modules.
The great majority already comply, most of them deliberately: `score_partial`
and `score_unavailable`, the three-state source constants, `pm_rvol_reason`,
`collector_coverage`, `check_report`'s coverage block. The audit's list of
non-compliers is recorded for future work rather than fixed wholesale, since
several are latent shapes rather than live holes and the week before a first
Monday is the wrong time to change twenty guards.

### Containment sees single letter tickers

The token pattern needed two characters, so all 21 single letter listings were
invisible and a fabricated F or T row returned no findings while the run
printed that containment passed. Those are the symbols a model is most likely
to invent, being the most familiar in the market.

The measured cost of widening: across both archived reports, **zero new
invented-ticker findings**, and claims examined rose from 25 to 29 and from 20
to 23. Two reports is a small sample, so A and I joined the prose stopword
list. A is Agilent and also the English article; I is not a listing at all.
Both are stopped in prose only, and a Ticker column cell reading A is still
checked, which is the case the guard exists for.

### The build identifier no longer writes to the tree it measures

`git status` refreshes and rewrites `.git/index`, so the whole-tree isolation
check failed on a file the check itself had caused to change. It is
`git --no-optional-locks status` now, and three consecutive suite runs pass
with no allowlist addition. `.git` stays watched.

[corrected 2026-08-14: the session that introduced this reported the resulting
intermittent failure as a transient filesystem oddity consistent with a virus
scanner, and left a comment in conftest.py saying so. It was neither transient
nor external. The `universe.json` and git-object transients from the same
session remain genuinely unexplained and are left recorded as such.]

### The morning never fetches the calendar

`market_today.get_details` had no in-process cache, and `job_status.overdue()`
walks day by day per step while scan calls it twice, so a ten day gap across
sixteen steps was hundreds of re-reads and, once the cache went stale on
20 August, would have been hundreds of sequential HTTP attempts inside the
08:45 window. There is now a per-process memo, the nightly refreshes the
calendar with `market_today.py --refresh`, and scan sets `ALLOW_NETWORK` false
so a stale calendar is used as it stands with `calendar_cache` in the packet
recording that it was. Measured: zero network clients built across fourteen
lookups with a fresh cache, and zero with a 2,417 day old one.

### The short side, measured and left alone

Recorded in DECISIONS.md with the full tables. In one line: an upward-gap-only
propensity is worse on this cache at both caps, tier 1 is unchanged at 0.55
because direction cannot be known at 07:15, and the comparison is confounded
because the variant has 60 sessions of history against the shipped key's 250.
Nothing shipped changed, and the 2026-08-14 replay is byte identical to
4cd4a3b, digest 9918b22d.

## 2026-08-14, fifth: the premarket source question, and two fields corrected

### real-time/(symbol) is not real-time/?ex=US, and that had never been checked

`bulk_live_us()` hits `real-time/AAPL.US?ex=US` and serves the last completed
session, which is the defect that published the wrong prices on 2026-08-14.
`live_quotes()` hits the same endpoint family per ticker as
`real-time/{symbol}`, and nobody had ever checked whether the per ticker form
behaves the same way. The two answers lead to different systems: if it serves
the last completed session it is useless before the open and the candidate
pool prior is the only way to choose names at 07:15; if it serves today, a
2,745 name sweep at 07:15 sees the real overnight move for the whole universe
and replaces the prior outright at about 2,745 counted calls.

**A single call on 2026-08-14 at 13:42 ET settled half of it.** SPY came back
with a timestamp of 13:26 the same day, sixteen minutes behind the wall clock
but unambiguously the current session: close 775.65 against a previousClose of
777.88, volume 14.5M. A second sample two minutes later had advanced to 13:29.
So the per ticker form is **not** the exchange wide form's
last-completed-session behaviour. It is Live v1 with the roughly seventeen
minute delay this project already documents.

**That is not the answer to the question.** Whether the feed ticks during the
premarket window is a different fact from whether it ticks during regular
hours, and a lunchtime reading says nothing about it. A feed that only updates
from 09:30 would return the prior close all morning and be indistinguishable
from the bulk endpoint until the bell. Treating the regular hours reading as
the answer would be the same overreach that produced Thursday's report.

So `src/research/probe_live_v1.py` samples five context tickers every three minutes
from 08:00 to 09:15 and puts the collector's own bar for the same minute
beside each reading, the collector being ground truth because it is a trade
socket. Roughly 26 calls, five symbols to a request. It is standalone: nothing
imports it, nothing reads its output, it writes no status record, and
CRITERIA.md [job status steps] deliberately does not carry it. Registered as a
one time task for Monday 2026-08-17 at 07:55 and meant to be deleted after.

Its `--report` mode counts how many readings carried a feed timestamp inside
the premarket window and refuses to conclude anything about 07:15 from
readings that did not. On today's lunchtime sample it correctly reports
PARTIAL.

The lag column is what will decide the follow up even if the answer is yes: a
sweep at 07:15 reading a feed that is seventeen minutes behind is reading
06:58, which is early in the premarket session and may or may not carry the
overnight move.

### A field that could never be populated

`scan.py` read `selection_gap_pct` into every `dropped_no_coverage` record.
Nothing has written it since d224837, when discover stopped computing a
selection gap, so it was always null. That is worse than useless in this
project specifically: the rule is that missing evidence stays null with a
recorded reason, so a permanently null field reads as evidence that was
sought and not found rather than as a field with no writer.

Replaced with `pool_tier` and `pool_source`, which discover does write and
which answer the question the field was presumably there for: why this name
was in front of the collector at all. No document referenced the old key, and
the only other occurrences are in test_repricing, which builds its own in a
test-local fixture to stand for what a stale packet said. That fixture is why
the orphan stayed invisible: the regression test hands the read the value no
production path supplies.

### The same check found a second one, and it would have fired on Monday

The read-without-writer scan covered **446 reads** across every consumer of a
candidate, packet, watchlist row, picks row, market snapshot row or bar row,
in all sixteen scheduled modules plus the report template and the analyst
prompt. Two orphans, both from the same commit, both left behind by the same
rewrite.

The second is `collect_premarket.py`, printing the names it dropped to fit the
socket cap:

    print(f"    dropped {row['symbol']:<12} gap {float(row.get('gap_pct') or 0):+7.2f}%")

discover stopped writing `gap_pct` onto watchlist rows at d224837, the same
commit that stranded `selection_gap_pct`. The collector's own docstring even
records the removal, saying the re-sort by gap was dropped because the field
"no longer exists on a watchlist row". The re-sort went. This print did not.

**It has not fired yet only by an accident of timing.** d224837 landed at
10:02 on 2026-08-14 and the watchlist on disk was generated at 07:15:04 the
same morning, so the only watchlist the new code has ever met was written by
the old code and still carries the key. Monday 2026-08-17 at 07:15 is the
first watchlist written under the current code, and at 07:20 the collector
would have printed a confident `gap +0.00%` for every dropped name.

That `or 0` is the whole defect. A missing key becoming a plausible number is
the same failure as the stale price, one log line further down, in the exact
line that justifies which names were cut. The header lied too: "lowest
absolute gap first" has not been the order since d224837. The line now reports
tier, rank and pool source, which are fields that exist, and says it is
discover's ranking, which is what it is.

Both were found by an audit of reads rather than by a test, because a test
that replays an old packet supplies the very key that production stopped
writing. The general lesson is the one from the pool_recall week in a
different costume: a fixture that is more generous than reality hides exactly
the defect it is meant to catch.

### bulk_live_us has no caller in any scheduled job

The 9b5e43a report described the endpoint as retained for membership. It is
not used for that or for anything else in the pipeline. Audited: the only
caller in the repository is `measure_bulk_cost.py`, which exists to price the
endpoint on the vendor's own counter, and `test_pool.py` fails if the name
reappears in discover. None of the sixteen scheduled entrypoints reach it.

Its docstring opened with "Latest live OHLCV for every US listed ticker, in
one call", which is the claim that produced Thursday's report, and which
`scan.pool_candidates` had already been corrected to contradict while the
client itself still asserted it. It now names the actual behaviour, says it is
never a source of today's premarket, records that it is retained only for the
cost measurement, and warns explicitly that the per ticker form does not
behave the same way, so nobody reasons from one to the other in either
direction.

### Still open after this entry

The premarket half of the source question, which needs Monday's sampling run.
If `real-time/{symbol}` does tick before the bell, the follow up is a costed
comparison between a 2,745 call universe sweep at 07:15 and the pool prior,
and that is a bigger change than it sounds: the pool exists because no source
on this plan had today's move for the whole universe at 07:15. If that premise
is wrong, the tier ordering, the propensity ranking and the cap measurement
are all answers to a question that need not have been asked. None of that
should move before the probe reports.

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

`src/ops/job_status.py`. Every scheduled step appends one line to
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

`src/tests/test_entrypoints.py` drives all sixteen scheduled entrypoints through
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
nothing objected. `src/morning/vintage.py` now asks, after pricing and before scoring,
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
six impossible rows in the marker file. `src/tests/test_vintage.py`.

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
src/research/backtest_pool.py, version controlled and tested, and split into two stages
that never run together.

**fetch** reconstructs one historical session's inputs, the earnings calendar,
the overnight news sweep, the prior session end of day and universe membership,
together with its outcome, the open against the prior close for every universe
name. Both go to a cache keyed by session date under data/backtest/. This is
the only stage that touches the network.

**evaluate** reads the cache and nothing else, applies a named ordering
configuration, and reports pool recall, subscribed recall, per tier hit rates
and the missed names. src/tests/test_backtest.py arms every outbound path to raise
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

src/selection/gap_stats.py computes, for every universe name over a trailing 250
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

src/tests/conftest.py redirects every writable root, sourced from config so a test
cannot bypass it by building a path itself, and rebinds the six module level
constants that captured one at import time. src/tests/run_tests.py wraps the suite in
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

src/tests/test_txn_guard.py asserts three things: a request under a deliberately
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
