# PremarketDesk build plan and session handoff

Last updated: 2026-08-17, when the notable movers section was specified in full
under "What remains" as Layer 4. The build history below was written on
2026-08-14, after the first live morning and the five commits that followed
it. All sixteen checkpoints are built, verified, and committed, and the eight
Task Scheduler jobs are registered. The system is armed but
gated: it runs every weekday morning, produces a report, and refuses to email
until a human reviews one real morning and deletes data/UNVERIFIED.

The build history below is kept as written. Where a checkpoint describes
behaviour that has since changed, the change is recorded in doc/CHANGELOG.md
and the reasoning in doc/DECISIONS.md, both of which start on 2026-08-14.
Read "What remains" and "The first live morning" below for the open items.

## What this project is

A single-brain premarket report generator. Python on Windows. EODHD All-In-One
is the only market data provider. The narrative pass runs through the owner's
existing Claude subscription via the claude CLI. No second model, no rival
brain, no merge step, no yfinance, no Anthropic API key anywhere.

## Hard rules, none negotiable

1. EODHD is the only data source. No yfinance, no second vendor.
2. The narrative pass is the claude CLI (`claude -p --output-format json`) as
   a subprocess. Never the Anthropic Python SDK. Never read or set
   ANTHROPIC_API_KEY. config.py actively refuses that variable and strips it
   from .env if it ever appears, and analyst.py scrubs it from the subprocess
   environment. The model name is a CRITERIA.md knob: the original brief said
   sonnet, the owner switched it to opus on 2026-08-13 mid build.
3. Every screen threshold lives in doc/CRITERIA.md and nowhere else. No
   threshold literal in Python. criteria.py is the strict reader and raises
   on any missing key.
4. No em dashes in code, comments, strings, or docs. Use commas, colons, or
   the word "to". This applies to this file too.
5. Work checkpoints in order, commit at each checkpoint.
6. Premarket high, low, VWAP come from the collector file only, never
   inferred from a quote snapshot. Missing evidence is null with a recorded
   reason, never silently substituted.
7. The model narrates. Membership, eligibility, scores, and conviction are
   computed deterministically in Python before the model ever runs, and
   analyst.py's containment checker fails the run if the report mentions a
   ticker the packet does not carry.

## Repository layout

The owner asked mid build for code under src/ and documents under doc/.
On 2026-08-14 src/ was split into packages by role: core, ops, selection,
collect, morning, night, research and tests. Module names did not change,
only where they live, so `import config` became `from core import config`
and every `config.X` usage stayed valid. src/ is the import root, so
scripts run as `.venv\Scripts\python.exe -m <package>.<module>` with
PYTHONPATH set to src, which is what every .bat now does. config.py sits
at src/core/config.py and resolves the project root two levels up. Everything a script generates (data/, runs/, logs/) stays
at the root and is gitignored along with .env.

- src/ is split into packages by role, and src/ itself is the import root:
  - core/    config, criteria, ettime, store, eodhd. Infrastructure every
             other package rests on; nothing here knows what a gapper is.
  - ops/     job_status, market_today, monitor_jobs. Whether the machine is
             running correctly: the status record, the trading day guard and
             the watchdog.
  - selection/ universe, discover, gap_stats. Which names are worth watching,
             decided before the open.
  - collect/ collect_premarket, baseline. Today's tape, and the volume
             baseline its RVOL is measured against.
  - morning/ scan, vintage, analyst, render_report, verify_morning, deliver.
             The 08:45 chain in order.
  - night/   backfill_premarket, fill_outcomes, pool_recall, build_archive.
             What runs once the vendor has published the full day.
  - research/ backtest_pool, probe_live_v1, the two measure_ scripts.
             Instruments, not pipeline. Nothing downstream reads their output.
  - tests/   conftest, run_tests and the nine test_ modules.
- doc/: this file, CHANGELOG.md, DECISIONS.md, CRITERIA.md,
  REPORT_TEMPLATE.md, prompt_analyst.md, the two architecture pages,
  sample_report.html
- tasks/: seven job .bat files, register_tasks.ps1, README.md. They
  register as nine scheduled tasks: job_nightly runs twice, at
  22:15 and again at 07:00 as nightly-catchup, and job_monitor runs on a
  repeating weekday trigger and once more at 22:45
- data/: universe.json, watchlist.json, premarket/YYYY-MM-DD.jsonl,
  premarket/YYYY-MM-DD-subscriptions.json (what the collector asked the socket
  for, written at subscribe time), premarketdesk.db, ca-bundle.pem,
  job-status.jsonl (one line per scheduled step per run),
  UNVERIFIED (the delivery gate marker)
- runs/YYYY-MM-DD/: packet.json, premarket_snapshot.jsonl, report.md,
  report.html, analyst_usage.json, and once the nightly job has run,
  verify_intraday.json and pool_recall.json
- site/PremarketDesk.html: the single file report archive, rebuilt from
  runs/ at the end of every morning chain and every nightly run
  (build_archive.py, embed_sessions knob in CRITERIA [archive]). Opens by
  double clicking, no server, no network; the newest sessions are inlined,
  older ones link out to their runs/<date>/report.html; the URL hash picks a
  day, j and k or the arrows step between days. Full rebuild every time,
  idempotent by construction; gitignored like the other generated output

## Environment facts a new session must know

- Working directory: `e:\Stock Analysis  Tool Ideas\PremarketDesk` (two
  spaces between "Analysis" and "Tool", quote all paths).
- Python 3.14.7 at C:\Python314. Venv at `.venv`, deps: requests,
  websocket-client, markdown.
- tzdata is absent, so zoneinfo cannot resolve America/New_York. ettime.py
  provides the one ET clock: zoneinfo if available, else a fixed post 2007
  DST rule. Always use ettime, never naive datetimes.
- Norton Web/Mail Shield re-signs all HTTPS with a root whose
  basicConstraints is not marked critical. Python 3.14 enables
  VERIFY_X509_STRICT by default and rejects exactly that. Fix lives in
  config.tls_context() and config.ca_bundle(). Never verify=False.
- Norton also intermittently blocks git loose object writes with Permission
  denied. Every retry makes progress: loop `git add -A` then `git commit`
  until both exit 0. Do not conclude the repo is broken.
- Backslash paths inside Python docstrings: `data\UNVERIFIED` in a docstring
  is a unicode escape error at import time. Use forward slashes in prose.
- PowerShell 5.1: no `&&`, use `if ($?) { }` or separate statements.
- schtasks /Create /TR stored this project's spaced path UNQUOTED, and every
  task then died at fire time with 0x80070002 file not found before its .bat
  even started (discovered when the first real scheduled fire, the 22:15
  nightly on 2026-08-13, failed). register_tasks.ps1 therefore uses the
  ScheduledTasks PowerShell module, which stores the action structurally.
  If a task ever shows Last Result -2147024894, suspect quoting again.
- EODHD publishes the day's intraday later than the 22:15 nightly, probably
  as a next day batch: at 22:40 on 2026-08-13 the whole day was still empty
  (regular session included) while 2026-08-12 was complete. The backfill
  sweeps up to catchup_days prior sessions whose true premarket columns are
  still null, and the same job_nightly.bat is also scheduled at 07:00 as
  nightly-catchup, so yesterday's fill and volume verification complete
  before the new morning's collection is trusted. Never fill a day with
  another day's bars; unfilled stays null with the sweep retrying.
- The claude CLI lives at C:\Users\udaya\AppData\Roaming\npm\. The .cmd shim
  MANGLES empty string arguments (it forwards through cmd.exe), which
  silently breaks --tools "". analyst.resolve_cli therefore invokes the real
  binary directly: node_modules\@anthropic-ai\claude-code\bin\claude.exe
  next to the shim. JSON output carries result, usage, num_turns, is_error,
  subtype, total_cost_usd. The narrative run is one completion: --tools ""
  (nothing to loop on; this CLI version has no turn cap flag and needs
  none), --effort low (default effort spent ~35k thinking tokens and 340s on
  a job with no decisions to make), a one line --system-prompt, everything
  piped on stdin. The model is opus, the owner's standing choice, re-asserted
  after a review batch had said sonnet. Five measured opus runs at low effort
  on 2026-08-13: 65.3, 70.1, 67.0, 77.6, 65.8 seconds, num_turns 1 every
  time, ~31k tokens, about 17 cents equivalent. Effort moved to medium on
  2026-08-14 after the comparison recorded under the reinstated review items
  below, and five medium runs measured 97.4, 86.5, 97.7, 91.1 and 92.4
  seconds, so timeout_s is now 293, three times the slowest.
- .env holds the real EODHD token (100k daily request limit). RESEND_API_KEY
  and EMAIL_TO are empty, so delivery skips even without the gate.
- `.claude/settings.local.json` grants broad tool permissions.

## EODHD facts learned by probing, trust these over the docs

- Endpoints wrapped in eodhd.py and verified live: us-quote-delayed (fields
  ethVolume, ethTime ms epoch, marketCap, sharesFloat, averageVolume,
  twoHundredDayAveragePrice, previousClosePrice, name, sector), real-time
  with ex=US (bulk live, ~18.3k rows), eod-bulk-last-day/US, eod/{symbol},
  intraday/{symbol} interval=1m (04:00 to 19:59 ET coverage, UTC epoch
  seconds, published a few hours behind live), exchange-symbol-list (keep
  only Type == "Common Stock"), exchange-details/US (official holidays, early
  close days, trading hours, verified live on this plan, cached to
  data/exchange-details.json for the trading day guard), news (s= symbol tag
  filter, no publisher
  field, derived from url host), economic-events (no importance field, the
  CRITERIA.md high importance list owns that call), calendar/earnings, user,
  search.
- Symbol formats disagree: bulk live returns `A.US`, bulk EOD returns bare
  `VASO`, the websocket wants bare `AAPL`, everything else wants `AAPL.US`.
- Bulk live carries ghost rows: stale frozen snapshots that fabricate
  enormous gaps. That was handled by a deduplication in discover which no
  longer exists: the pool rewrite on 2026-08-14 removed the endpoint from
  discovery entirely, and test_pool.py now fails if the name reappears
  there. The fact is kept because it is the reason the feed is not trusted
  for selection. If it is ever consumed for selection again, the newest
  timestamp dedup and the age drop have to come back with it.
- The /user endpoint counter (apiRequests against dailyRateLimit) is
  ACCOUNT WIDE and this account runs other projects too. Never attribute
  that counter to this project without a controlled before and after
  measurement while nothing else is running; measure_socket_cost.py is the
  tool for that. The counter resets at 20:00 ET, midnight UTC.
- Measured 2026-08-13 evening with that tool: websocket connections,
  38 symbol subscribe frames, and reconnects are NOT metered. A 20 minute
  collector-only run (10 connections, 9 reconnects) and a second with 3
  forced drops (13 connections, 12 reconnects) both moved the vendor counter
  by exactly zero. The /user reads themselves did not register either. Still
  owed: the per message cost on a heavy live tape, measurable any weekday by
  running measure_socket_cost.py inside 04:00 to 07:15 before the jobs wake.
- Measured 2026-08-13 at 23:05 ET with measure_bulk_cost.py: ONE bulk live
  OHLCV request (real-time/AAPL.US?ex=US) moved the vendor counter by
  exactly 100 for 18,341 returned rows, in one HTTP attempt, after a 45
  second quiet watch showed zero meter drift. A flat per request rate, not
  per symbol. Verdict against the 1,000 line: NOT crossed. That measurement
  was of the bulk live call, which no scheduled job makes any more. The
  day's bulk calls are now end of day: two at 07:15 for discover's prior
  session movers, and two at 22:15 for the pool recall, at a measured 100
  counted calls each, so about 392 a day on the shared 100,000.
- Quota preflight, same night: discover.py and scan.py read /api/user on
  entry (eodhd.preflight) and act on the shared meter, never the local
  ledger, because the key is shared and remaining quota is not a function
  of this project's own usage. Below CRITERIA.md [quota]
  degrade_below_remaining (5000) scan keeps only the calls it cannot skip
  and writes the reading into gaps_to_fill, while discover records the
  reading and proceeds, its sources being the thing the morning cannot do
  without; the report disclaimer
  states the reading on both paths (REPORT_TEMPLATE.md instructs the model,
  analyst.fallback_report appends it deterministically); below
  refuse_below_remaining (500) the job exits 1 before spending anything.
  Proven by forcing the thresholds above the live reading: the refusal cost
  one call and wrote nothing, the degraded packet ran on exactly two calls,
  and the opus report's disclaimer named the reading. The same evening made
  the case for the feature unprompted: 49,999 of 100,000 were already gone
  at 23:03 on a quota day that had opened at 20:00, none of it this project.
- Review hardening on the preflight, same night, after a 28 agent
  adversarial review: a 200 meter payload with missing or null fields, or
  one whose apiRequestsDate is not the current quota day, is an unknown
  meter and never degrades or refuses (fail open, the reading recorded as
  dated; the vendor really sends apiRequestsDate, verified live).
  catalyst_found None classifies as unknown with class NULL in picks, never
  as "checked and empty"; the thin path's rvol reason says the quote was
  never fetched, not that the vendor returned nothing. A quota thinned scan
  rerun of a day holding a full width packet stands down and writes
  packet_degraded.json instead of upserting nulls over real picks. The
  baseline warm preflights itself and stands down on a degraded meter (the
  warm is skippable spend). The fallback report renders skipped calendars
  as "not checked", never as empty, and names unknown catalyst candidates.
  The call report captures the quota day at the first call so a run
  straddling the reset prints both days. bulk_redesign_line = 1000 lives in
  CRITERIA [quota]; measure_bulk_cost.py reads it and refuses to record a
  measurement that straddled the reset.
- Third hardening batch, 2026-08-14 before the first live morning:
  swing_failed distinguishes a never checked news feed from a checked and
  empty one; containment records its coverage (universe_available,
  columns_scanned, tokens_examined, claims_checked) into
  analyst_usage.json, appends "ticker claims were NOT validated" to the
  disclaimer whenever it examined nothing, and the day and swing table
  header rows are literal in REPORT_TEMPLATE.md with prompt rule 12
  pinning them character for character, so the guard no longer depends on
  the model's word choice; store.session() commits, rolls back and CLOSES
  (sqlite3's own context manager leaves connections open) and every call
  site uses it; store refuses non identifier table and column names before
  they reach SQL; and the collector scrubs the API token out of exception
  text before printing (config.scrub_secrets), because the websocket URL
  carries the token and a handshake exception can quote the URL into a
  log. Proofs: src/tests/test_store.py, the extended src/tests/test_containment.py
  (Sym headed column produces the unvalidated disclaimer), and a forced
  connection failure that logged only the masked URL, with a grep of
  logs/ for the token prefix returning nothing. Extended the same day: the
  scrub moved into eodhd._request itself, the one chokepoint every HTTP
  call passes through, so no error string can leave it with a credential
  regardless of which caller records it (exception text, non 200 bodies,
  and a belt scrub at the exit); deliver.py scrubs its Resend failure
  prints the same way; config.mask now shows only the last four characters,
  because first-and-last-four reveals enough to identify a token against a
  list; and src/tests/test_scrub.py forces a tokenised network failure through
  the chokepoint and through a whole packet build, asserting the mask
  appears and the raw token appears nowhere in the returned error, the
  ledger, gaps_to_fill, or the serialized packet.
- The quota day is the UTC calendar date (eodhd.quota_day). One ET weekday
  spans two quota days: the morning jobs bill to the day that opened at
  20:00 ET the previous evening (19:00 in standard time), and the 22:15
  nightly bills to the next one, so an evening sibling project competes
  with the following morning. Every EODHD call report now names the quota
  day the run billed to, so a starved morning is traceable to the evening
  before.
- Websocket wss://ws.eodhistoricaldata.com/ws/us: wait for the
  {"status_code":200} Authorized frame before subscribing, or the socket
  dies silently. ws.eodhd.com has a bad TLS cert, keep eodhistoricaldata.com.
  Cap is 50 concurrent symbols.
- Trades arrive out of order; bars settle late_trade_grace_s before being
  written.
- Live v1 cumulative volume is NOT a sound short window reference (measured
  up to +1113 percent disagreement). The definitive check is
  `collect_premarket.py --verify-intraday` against EODHD 1m bars, evenings.
- US10Y.GBOND, US3M.GBOND, DXY.INDX are NA on live but current on eod. The
  vendor fact still holds; the snapshot no longer asks the live endpoint at
  all, reading end of day for every label and overwriting the last price
  from the collector where the symbol has bars. The snapshot falls back and records the source. No commodity symbols on this
  plan; USO.US stands in for WTI, labelled a proxy.

## Checkpoint status: all sixteen DONE

CP1 setup, CP2 criteria file and reader, CP3 EODHD client, CP4 weekly
universe (2745 names), CP5 morning discovery, CP6 collector, CP7 baseline
cache: done and committed in the first session, evidence in git history and
the sections above.

CP8 scan gathers: verified 2026-08-13. `python src\scan.py` writes
runs/YYYY-MM-DD/packet.json, every failure lands in gaps_to_fill with a
reason, no network error crashes the run. 33 API calls, ~8s.
Hardened same day: scan no longer reads the live collector file, which the
collector is still appending to at 08:45. It copies it to
runs/<date>/premarket_snapshot.jsonl, parses only newline terminated lines,
discards and counts a trailing partial line, and records bars_total plus the
last complete bar time in the packet under collector_snapshot. The collector
writes and flushes line by line. Proven with a writer holding the file open
around a truncated line.
Added during verification: the RVOL cutoff snap. The baseline lookup is an
exact minute match, so sixty seconds of scheduler jitter would have nulled
every RVOL. When the wall clock is within rvol_cutoff_snap_minutes (10) of
the scan run_time, the run_time cutoff is used. See the cutoff snap note in
CRITERIA.md.

CP9 deterministic score: `--rescore` run twice on the same packet produced
byte identical output (fc: no differences).

CP10 analyst: doc/REPORT_TEMPLATE.md (eleven fixed sections),
doc/prompt_analyst.md (the numbered rules), src/morning/analyst.py. Pipes prompt plus
template plus packet to the CLI on stdin, parses the JSON envelope, writes
report.md and analyst_usage.json, logs tokens and cost, then runs the
containment checker: every uppercase token in the report must exist in the
packet text (finance acronym stoplist excepted), exit 2 on violation.
Verified with sonnet and again with opus after the owner switched the knob.
Hardened same day, twice. First, the report survives the analyst failing: on
timeout or any CLI failure (two attempts, timeout_s per attempt), analyst.py
renders a deterministic plain table fallback straight from packet.json, puts
the reason in the disclaimer line, records status ok|timeout|failed in
analyst_usage.json, and exits 0 so render and deliver carry on. Proven with
a forced CLI failure and again live when the shim mangling caused real
timeouts. Second, the invocation became one completion instead of an agent
loop (see the CLI facts above): model back to sonnet per the owner,
timeout_s = 218, three times the slowest of the five measured runs named in
CRITERIA.md. The containment checker was also rebuilt: a claim is an
uppercase token in a table cell or with a $ prefix that names a real
universe member; prose acronyms (CEO, FOMC, CPI...) can no longer trip it,
src/tests/test_containment.py proves both directions, and a containment failure is
fatal again on every path including the fallback.

CP11 render and deliver: report.html via the markdown library (tables,
fenced_code, sane_lists). deliver.py posts to Resend through the Norton
aware TLS session, and with keys unset prints a skip and exits 0, verified.
EMAIL_FROM is optional, defaulting to Resend's onboarding sender.

CP12 picks: one row per candidate upserted on (date, ticker) from scan.py.
Ran scan twice: 12 rows both times, no duplicates. entry_ref is pm_high,
stop_ref is pm_low, the reasoning is documented in CRITERIA.md [picks].

CP13 backfill: src/night/backfill_premarket.py widens picks with pm_high_true,
pm_low_true, pm_vwap_true, pm_true_bars, pm_source_disagreement, and writes
the true 04:00 to 09:30 window from intraday 1m bars next to the morning
values, never over them. A true high below the live high is a feed
difference or a bad bar (odd lots, condition codes, late corrections), and
pm_source_disagreement records the shortfall as a percentage magnitude, not
a boolean, so noise and real errors read differently. Nothing is silently
corrected. Prints the median and worst case live versus true high gap over
recent sessions, and writes verify_intraday.json for the record. The fill
math was proven against 2026-08-12 (AAPL 330 of 330 premarket minutes);
today's rows fill tonight when intraday catches up.

CP14 outcomes: src/night/fill_outcomes.py fills next session open, high, low,
close, fifth session close, whether pm_high broke the next day, and the
excursions around entry_ref and stop_ref, on the SPY session calendar, never
weekday math. Proven idempotent: a seeded synthetic pick filled correctly
and a second run left the table hash unchanged.

CP15 scheduling: tasks/ holds five .bat jobs, each cd's to the project root,
stamps its log date with the project's own ET clock, and appends to
logs/<job>-YYYY-MM-DD.log. The 08:45 chain (scan, analyst, render, gate
table, deliver) ran end to end from the bat with rc=0 at every step.
register_tasks.ps1 registered all five: discover 07:15 (which also warms the
baseline cache, an addition to the original brief, because scan must never
fetch baselines), collector 07:20, morning chain 08:45, nightly 22:15, all
Mon to Fri, universe Sunday 20:00.

CP16 gate: src/morning/verify_morning.py prints the evidence table (ethVolume,
baseline median, pm_rvol, collector premarket high, bars) for the top
candidates and the chain logs it every morning. data/UNVERIFIED exists;
deliver.py refuses to email while it does, proven with keys present in the
environment: refusal message, zero HTTP calls, exit 0. Nothing in the code
deletes or recreates the marker on its own; `verify_morning.py --arm`
recreates it deliberately.

## What remains

1. The definitive collector volume verification (the last CP6 debt) now
   lands with the FIRST LIVE morning's nightly. The 2026-08-13 rows were
   all marked source='test' by the 2026-08-14 migration and the backfill
   only touches live rows, so no verify_intraday.json will appear for
   2026-08-13 and none is owed: its collector file held midday test bars,
   not a premarket window. Check runs/(first live date)/verify_intraday.json
   after that evening's 22:15 run. Healthy means most symbols within one
   percent on identical minutes.
2. First real morning (tomorrow is scheduled): everything fires from Task
   Scheduler. Review the gate table in logs/morning-chain-YYYY-MM-DD.log.
   When ethVolume, baseline medians, RVOLs, premarket highs and bar counts
   look sane, go live: delete data/UNVERIFIED and set RESEND_API_KEY and
   EMAIL_TO in .env. Until both happen, mornings produce reports on disk and
   email nothing.
3. Longer term, as CRITERIA.md's header says: once picks holds a few hundred
   filled outcome rows, revisit the seed thresholds because the data said so.
4. The notable movers section: SPECIFIED BELOW, NOT BUILT. Everything it
   rests on is built, tested and committed. The section itself is not. Its
   specification is the "Layer 4" section immediately below, written out in
   full on 2026-08-17 so that no part of the design lives only in a
   conversation.

## Layer 4: the notable movers section, specified

Ordered by the owner on 2026-08-16, settled over the two days after, and
amended on 2026-08-17 by three rulings recorded in DECISIONS.md. This is the
whole design. Where a point was decided while writing this down rather than by
the owner, it says so, so it can be overruled cheaply.

### Already built, do not rebuild

- CRITERIA.md [Notable]: list_size 5, min_abs_gap_pct 1,
  min_sessions_for_move_sigma 20, min_return_stdev_pct 0.1, and the prose
  above them stating what the section is and is not.
- data/universe-closes-<date>.json, written by discover at 07:15. sessions
  names the three session dates as c1, c2, c3; closes holds
  {SYMBOL: {c1, c2, c3}}; universe_examined, names_with_at_least_one_close
  and third_session_available carry the denominators. c1 is the prior session
  close, c2 the one before it, c3 the third back. The third session costs one
  extra bulk call, a flat 100 credits, and is bought rather than read from
  gap_stats so that all three closes carry ONE vintage. A name missing from a
  session is null there and is never backfilled from a neighbouring session.
  THIS IS THE SECTION'S ONLY PRICE SOURCE for every name the collector did
  not hear.
- gap_stats.return_stdev_20d: the standard deviation of daily close to close
  returns in percent over the trailing 20 sessions, null below
  min_sessions_for_move_sigma returns. Computed from a close only filtered
  list rather than from the bar list the other columns use, because that one
  drops bars missing an open.
- vintage check (e) and _LEG_NEWEST_SESSION_BACK: per row validation of
  notable_movers. leg and as_of_session are REQUIRED fields, and a row
  missing either fails rather than being skipped. All three emitted legs
  already validate against the table as it stands: premarket stamps today,
  every universe leg stamps the prior session.
- analyst._REQUIRED_TABLES: the vacuum detector requires the day and swing
  watchlist tables BY NAME. A notable movers table contributes claims to
  validate but can never satisfy that requirement.
- conftest.watchlist_headers and watchlist_table: fixtures build their tables
  from REPORT_TEMPLATE.md, so a template header change breaks them loudly.

### Still to build

The scan fields and the section assembly in src/morning/scan.py, the section
in doc/REPORT_TEMPLATE.md, rule 10 in doc/prompt_analyst.md, the claims, and
the CHANGELOG and DECISIONS entries.

### 4.1 Scope fence

Additive to the report only. It does not touch picks, scoring, eligibility,
conviction, CRITERIA's day_setup or swing_setup, pool_recall, or any recall
measurement. NOTHING HERE MAY WRITE A ROW TO PICKS, because picks is the
record of what the trading screen claimed and mixing briefing names into it
would destroy the measurement. If a step seems to need a picks column, stop
and report rather than adding one.

The section reads exactly two files it does not own, universe.json for market
caps and data/universe-closes-<date>.json for prices, plus the collector bars
scan already holds in memory. It does not read pool_recall.json, does not
import pool_recall, and shares no code with it. The fence around the recall
measurement therefore needs nothing to hold it: there is no connection to
sever and no byte identical rebuild to check.

### 4.2 Per candidate fields in scan

For every candidate, stored in the packet beside gap_pct:

- move_sigma: gap_pct divided by return_stdev_20d. A quiet megacap moving 2
  percent and a thin small cap moving 6 percent land at comparable numbers,
  which is the whole point. The premarket move spans one session, so the
  square root scaling in 4.3 multiplies the denominator by 1 here.
- gap_2session: the move from c2 to the current premarket price.
- gap_3session: the move from c3 to the current premarket price.

Add nothing to CRITERIA's setup blocks. These are report fields, not screen
conditions, and neither evaluate_eligibility nor score_candidate reads them.

move_sigma is null with a recorded reason when return_stdev_20d is null or
below min_return_stdev_pct. Never a substituted number, never a silent drop.

### 4.3 The legs

Every row carries leg and as_of_session, and the section's rows may mix legs
by design. The leg names the WINDOW: the number of sessions the move SPANS,
not the age of its baseline. as_of_session names the NEWEST datum in the row,
which is the one that can go stale, and it is what vintage validates. The
lookback lives in the leg label alone. See the docstring on
_LEG_NEWEST_SESSION_BACK for why the labelling is anchored that way.

Three legs are emitted, all from data the 07:15 discover already bought:

  leg            the move                  span        as_of    population
  premarket      c1 to the collector       overnight   today    collector
                 price                     to 08:45             names
  prior_session  c2 to c1                  1 session   prior    universe
  two_session    c3 to c1                  2 sessions  prior    universe

Every universe leg reads data/universe-closes-<date>.json and nothing else.
One file, one vintage, no cross module read, and the same three closes serve
both universe legs. The prior session leg is a CLOSE TO CLOSE move rather
than an open gap: close to close carries the whole session, both the
discontinuity at the open and the drift after it, where an open gap carries
only the discontinuity. For a briefing, which asks what happened to a name
rather than what the screen could have traded, the whole session is the
better measure.

The premarket leg covers only the names the collector heard, at most
subscribe_cap of the universe, and it reads bars_by_symbol rather than the
candidate list: every subscribed name is eligible, not only the twelve that
survived the screen. Its baseline is c1 from the same file.

No leg carries today's regular session move, because the report is written
before the open.

THE THREE SESSION LEG HAS NO SOURCE and is not emitted. Under the naming
above, where a leg is named for the sessions its move spans, a three session
move universe wide needs a fourth close and the file holds three. Two ways to
get one, neither taken here because both are the owner's call rather than the
builder's: discover buys a fourth bulk call, 100 credits a morning and 500 a
week against a 4,945 credit universe build, exactly the trade it already makes
for the third close; or the endpoint becomes today's premarket price, which
only the collector names have, which would put the leg back to covering 50
names and reintroduce the mixed endpoint 4.4 exists to prevent. The name stays
in _LEG_NEWEST_SESSION_BACK, where it costs nothing and would validate
correctly if a row ever carried it.

### 4.3.1 move_sigma scales with the square root of the span

Every leg carries a move_sigma. The denominator return_stdev_20d is a ONE DAY
return standard deviation, so an n session move is divided by
return_stdev_20d times the square root of n: 1 for premarket and
prior_session, the square root of 2 for two_session. A two session move is
then directly comparable to a one session move in sigma terms, which is what
lets the four labelled lists in 4.4 be read as one section even though no
single list ranks across legs.

STATE THIS ASSUMPTION IN THE DOCSTRING where the scaling is computed. Square
root of time scaling assumes daily returns are INDEPENDENT. Consecutive moves
in one name frequently are not, because momentum and a multi day catalyst both
produce runs, and dependent returns accumulate faster than the square root
allows. The scaled sigma is therefore an UNDERESTIMATE of how unusual a
sustained run is. That is the safe direction for a briefing: it cannot inflate
a name into the section, it can only keep one out.

Where the sustained mover is caught, so this is not re-litigated later. A
large quiet name up 2 percent on each of two consecutive sessions surfaces on
list 1 for the unusualness of its prior session move, since a quiet name's
sigma is small and 2 percent over it is large, and on list 3 for the size of
its two session move. The scaling's work is to stop the two session leg
overstating that name by the square root of 2, not to move it between lists.

### 4.4 The four lists

Four lists, list_size (5) names each. EVERY LIST RANKS WITHIN ONE LEG. No
ranked list mixes two legs, because ranking a premarket move against a prior
session move would compare a fresher window against an older one and would
put the 50 collector names, already selected for gap propensity and news,
into the same ordering as the 2,704 names nothing selected. They would
dominate systematically and the section would end up restating the watchlist
it exists not to restate.

  1. move_sigma descending, PRIOR SESSION leg, universe wide.
  2. market cap descending among names whose absolute prior session move
     clears min_abs_gap_pct, PRIOR SESSION leg, universe wide.
  3. absolute two session move descending, TWO SESSION leg, universe wide.
  4. move_sigma descending, PREMARKET leg, the collector names only.

List 3 ranks on the raw move rather than on sigma, as the original brief
specified. It is the size list for the multi session window, where list 1 is
the unusualness list for the single session one.

List 4's key is decided here rather than by the owner and is cheap to
overrule: move_sigma is the section's headline measure and these are its
freshest moves.

Market cap comes from universe.json. A name with no market cap on file is not
a pass and not a fail: it was never examined against the floor, it is counted
separately, and it cannot appear in list 2.

Deduplication is WITHIN a leg, never across legs. A name selected by both
list 1 and list 2 becomes one row carrying both reasons, on the pool_source
precedent in discover.py. A name selected on two different legs stays TWO
rows, because they are two measurements of different windows at different
vintages, and a row can carry only one leg and one as_of_session. The
template must therefore not imply one row per name.

A name already on the day or swing watchlist appears here anyway, and the row
says so inline. It is not suppressed. Two sections selecting the same name on
different grounds is information; hiding it is not. Expect most list 4 rows
to carry the mark, since that list draws from the pool the watchlist came
from, and that is precisely why the premarket leg was given its own list
instead of being allowed to crowd the others.

### 4.5 Row fields

ticker, leg, as_of_session, the move on that leg, move_sigma, market cap, the
catalyst headline where one was fetched, and the also on watchlist mark.
price_time where the leg has one, which is the premarket leg alone, and
vintage holds that one to the premarket window as well as to the session.

### 4.6 Catalysts

No news is fetched for any name outside the existing candidate set. Doing so
would multiply the call count over a set an order of magnitude larger, and
this section is a briefing rather than a screen.

A name with no news fetched is marked NOT CHECKED, never "no catalyst", per
the existing rule. The two are different facts and the report says which one
it is holding.

### 4.7 The template section

One section in doc/REPORT_TEMPLATE.md headed "Notable movers", placed after
the swing watchlist and before market trends. Its fixed text, which the model
reproduces exactly rather than composing:

- These names were selected for the size and unusualness of their move,
  rather than for tradeability.
- They have not been screened against the day or swing criteria.
- No conviction applies to any of them.
- Every row states which leg produced it and the session it is as of.
- No leg can carry today's regular session move, because this report is
  written before the open.
- A name may appear on more than one row, once per leg, because a row carries
  one window and one vintage. Added here rather than by the owner, because
  deduplication within a leg makes it possible.

The table carries a Ticker column, so containment applies to this section
exactly as it does to the watchlists: every ticker in it must exist in the
packet. It cannot satisfy the vacuum detector, which requires the two
watchlist tables by name.

### 4.8 The prompt rule

doc/prompt_analyst.md gains rule 10, after the existing nine: the model may
DESCRIBE these names, and may not assign them a conviction, may not move them
onto a watchlist, and may not imply a setup.

### 4.9 Degrade and skip

The section records what it could not do rather than emitting a bare empty
list. A missing universe-closes file, a missing third close, a collector that
heard nothing, a quota degraded run: each is a named reason in the packet,
and the section says which leg it lost.

The denominator is the universe, not the survivors. The section reports
universe_examined from the closes file as what it examined, alongside, per
leg, how many names carried both of the closes that leg needs. Zero examined
is a different outcome from zero selected and the section reports both
numbers.

### 4.10 Done when

- A run produces the section from universe wide data rather than from the
  candidates, and the examined count equals the universe size rather than any
  filtered subset of it.
- No leg reads pool_recall.json and nothing in the section imports
  pool_recall.
- A name moving under the 3 percent discovery gap floor appears in it when
  its move_sigma is high.
- No picks row exists for any name that appears only here.
- Every leg carries a move_sigma, and a name up 2 percent on each of two
  sessions ranks above a name up 2 percent on one.
- No single ranked list mixes two legs, and a collector name appears on list
  4 rather than displacing universe names from list 1.
- A packet with a prior_session row mis-stamped as premarket fails
  vintage.enforce, and a row missing its leg fails rather than being ignored.
  Already proven by claim_notable_legs in src/tests/test_vintage.py.
- The new claims are wired into run_tests.SUITE. run_tests does not discover
  claims: it imports a hardcoded SUITE and calls each module's main(), so an
  unwired claim is dead code.

### Known and accepted, outside this layer

A row whose leg says two_session while its move is arithmetically a one
session move is caught by neither the freshness labelling nor any other check
here. Vintage checks that the newest datum is the session claimed, not that
the move spans the window its label names. This is recorded on
_LEG_NEWEST_SESSION_BACK and is deliberately not being fixed now: closing it
would need the section to publish its endpoints so the arithmetic can be
rechecked, which is a change to the section rather than to the gate.

## Reinstated review items, with outcomes

Items that surfaced in review and kept falling off. Each line records what
actually happened to it, dated, so none of them silently becomes folklore.

- Containment fail open outside the universe: FIXED 2026-08-14. The universe
  holds common stock only, so every ETF, including the eight context tickers
  the report names every morning, was invisible to the claim check. Claims
  are now validated against the union of universe.json and the CRITERIA.md
  [collector] context list (analyst._claimable_symbols), and the regression
  test gained the case: QQQ claimed in a table while absent from the packet
  is caught.
- The --effort setting: COMPARED AND SWITCHED 2026-08-14. One medium effort
  run on the 2026-08-13 packet against that morning's low effort report:
  medium covered all 12 candidates individually in Technical signals where
  low compressed six names into one vague sentence ("mostly sit below their
  prior day highs"), and its Skips and traps carried actionable per name
  lines (WDAY: trade only against the confirmed prior day high, not a
  premarket level). Five timed medium runs: 97.4, 86.5, 97.7, 91.1, 92.4
  seconds, all clean single completions, about 25 seconds slower than low.
  CRITERIA [analyst] now reads effort = medium with timeout_s = 293 (3x the
  slowest of the five). One CRITERIA edit flips it back if a real morning
  says otherwise.
- The sibling consumer on the shared key: IDENTIFIED 2026-08-14. Three
  sibling projects under the same parent directory reference EODHD:
  AlphaFinanceLab, StockResearcherLab, and OptionsWheelLab. The 2026-08-13
  evening burn (about 50k calls between 20:00 and 23:03 ET) lines up with
  AlphaFinanceLab, an on demand .NET worker over an S&P 500 arena whose
  repo was last touched at 19:55 that evening; none of the three runs from
  Task Scheduler, so sibling spend is manual and unpredictable. Action for
  the owner: EODHD issues more than one token per account; give
  PremarketDesk its own so consumption becomes attributable and one project
  cannot starve the other. Until then, the preflight and the 429 circuit
  breaker are the defense.

## The first live morning, 2026-08-14

The first fully scheduled morning ran clean at every step and published a
report about the previous session. The bulk /real-time endpoint serves the last
completed session, so at 08:45 it priced yesterday, while prior_high came from
end of day history and was correct; the two met in a gate that compared a
session's close against its own high and could never pass, which is why both
watchlists were empty and why the report explained that as a dull tape.

From this date the running record splits in two. What changed and when is in
doc/CHANGELOG.md. Why a choice went the way it did is in doc/DECISIONS.md.
This file keeps the build history up to that morning and the open items below.

Open after that morning:

- CLOSED 2026-08-14, same day. Discover no longer ranks on the bulk feed at
  all; selection is a prior built from earnings, overnight news, prior
  session movers and recent runners. See DECISIONS.md 2026-08-14,
  "selection is a prior built before the open".
- CLOSED 2026-08-14: the ordering was measured and adopted. gap_propensity
  within tier with a floor of 4 slots, 0.1164 mean subscribed recall against
  the dollar volume key's 0.0842. See DECISIONS.md 2026-08-14.
- OPEN, replacing it: the subscription cap, which now bounds recall far more
  than ordering does. Ordering fully retuned moved recall from 0.0842 to
  0.1164; the pool being ordered holds 0.6193, and the gap is the cap. At
  caps of 42, 67, 92 and 142 recall runs 0.1164, 0.1578, 0.1864, 0.2236 and
  does not flatten. This is a purchasing decision, not a code one: the 50
  socket cap belongs to the vendor. Table in DECISIONS.md.
- pm_rvol's numerator covers 07:20 onward while its denominator accumulates
  from 04:00, so the ratio understates. Closing that needs a second baseline
  keyed to the collector window and a rewarm of the cache.
- The gate marker data/UNVERIFIED is still in place and should stay there
  until a morning's gate table has been read with the new price and clock
  columns in it.

## Operating notes

- The machine must be awake at trigger times; Task Scheduler does not wake
  it by default. See tasks/README.md.
- The analyst step spent 0.47 dollars equivalent on the one opus medium
  morning measured so far, 2026-08-14, recorded in that day's
  analyst_usage.json. One morning is not a range, and no second measurement
  exists yet. The knobs are CRITERIA.md [analyst] model and effort.
- Every job appends to a dated log in logs/. The morning chain stops on the
  first failure, so an empty inbox with a log that stops at scan means the
  packet failed, not the mail.
- To take the schedule down: `powershell -ExecutionPolicy Bypass -File
  tasks\register_tasks.ps1 -Unregister`.
