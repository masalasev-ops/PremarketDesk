# PremarketDesk build plan and session handoff

Last updated: 2026-08-13, evening ET. All sixteen checkpoints are built,
verified, and committed. The five Task Scheduler jobs are registered. The
system is armed but gated: it will run every weekday morning, produce a
report, and refuse to email until a human reviews one real morning and
deletes data/UNVERIFIED. Read "What remains" below for the two open items.

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
config.py owns every path and resolves the project root as the parent of
src/, so scripts are invoked as `.venv\Scripts\python.exe src\<name>.py` from
the project root. Everything a script generates (data/, runs/, logs/) stays
at the root and is gitignored along with .env.

- src/: config, ettime, criteria, eodhd, store, universe, discover,
  collect_premarket, baseline, scan, analyst, render_report, deliver,
  backfill_premarket, fill_outcomes, verify_morning, build_archive,
  market_today (the trading day guard every weekday job runs first: exit 3
  on weekends and official holidays from the cached EODHD exchange-details
  calendar, the .bat logs one line and stops; calendar unreachable with no
  cache assumes open on purpose), monitor_jobs (the watchdog: cross checks
  Task Scheduler's last run record against each job's dated log markers,
  reruns only what is idempotent per CRITERIA [monitor], never starts a
  second live collector, caps reruns at one per job per day; scheduled
  07:25 to 09:25 every 30 minutes and once at 22:45),
  measure_socket_cost (vendor counter before and after a collector-only
  run)
- doc/: this file, CRITERIA.md, REPORT_TEMPLATE.md, prompt_analyst.md
- tasks/: five job .bat files, register_tasks.ps1, README.md
- data/: universe.json, watchlist.json, premarket/YYYY-MM-DD.jsonl,
  premarketdesk.db, ca-bundle.pem, UNVERIFIED (the delivery gate marker)
- runs/YYYY-MM-DD/: packet.json, premarket_snapshot.jsonl, report.md,
  report.html, analyst_usage.json, verify_intraday.json once the nightly job
  has run
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
  after a review batch had said sonnet. Five measured opus runs on
  2026-08-13: 65.3, 70.1, 67.0, 77.6, 65.8 seconds, num_turns 1 every time,
  ~31k tokens, about 17 cents equivalent; timeout_s is 233, three times the
  slowest.
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
  enormous gaps. discover.normalize_bulk_live dedupes by newest timestamp
  and drops rows older than max_quote_age_hours. Never consume bulk live raw.
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
  per symbol. Verdict against the 1,000 line: NOT crossed. The two daily
  bulk calls (discover 07:15, scan 08:45) cost about 200 a day on the
  shared 100,000 and the two call design stands unchanged.
- Quota preflight, same night: discover.py and scan.py read /api/user on
  entry (eodhd.preflight) and act on the shared meter, never the local
  ledger, because the key is shared and remaining quota is not a function
  of this project's own usage. Below CRITERIA.md [quota]
  degrade_below_remaining (5000) each keeps only its one unskippable bulk
  call and writes the reading into gaps_to_fill; the report disclaimer
  states the reading on both paths (REPORT_TEMPLATE.md instructs the model,
  analyst.fallback_report appends it deterministically); below
  refuse_below_remaining (500) the job exits 1 before spending anything.
  Proven by forcing the thresholds above the live reading: the refusal cost
  one call and wrote nothing, the degraded packet ran on exactly two calls,
  and the opus report's disclaimer named the reading. The same evening made
  the case for the feature unprompted: 49,999 of 100,000 were already gone
  at 23:03 on a quota day that had opened at 20:00, none of it this project.
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
- US10Y.GBOND, US3M.GBOND, DXY.INDX are NA on live but current on eod; the
  snapshot falls back and records the source. No commodity symbols on this
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
doc/prompt_analyst.md (the twelve rules), src/analyst.py. Pipes prompt plus
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
src/test_containment.py proves both directions, and a containment failure is
fatal again on every path including the fallback.

CP11 render and deliver: report.html via the markdown library (tables,
fenced_code, sane_lists). deliver.py posts to Resend through the Norton
aware TLS session, and with keys unset prints a skip and exits 0, verified.
EMAIL_FROM is optional, defaulting to Resend's onboarding sender.

CP12 picks: one row per candidate upserted on (date, ticker) from scan.py.
Ran scan twice: 12 rows both times, no duplicates. entry_ref is pm_high,
stop_ref is pm_low, the reasoning is documented in CRITERIA.md [picks].

CP13 backfill: src/backfill_premarket.py widens picks with pm_high_true,
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

CP14 outcomes: src/fill_outcomes.py fills next session open, high, low,
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

CP16 gate: src/verify_morning.py prints the evidence table (ethVolume,
baseline median, pm_rvol, collector premarket high, bars) for the top
candidates and the chain logs it every morning. data/UNVERIFIED exists;
deliver.py refuses to email while it does, proven with keys present in the
environment: refusal message, zero HTTP calls, exit 0. Nothing in the code
deletes or recreates the marker on its own; `verify_morning.py --arm`
recreates it deliberately.

## What remains

1. Tonight after 22:15 (or any evening): the nightly job runs the definitive
   collector volume verification. Check logs/nightly-2026-08-13.log and
   runs/2026-08-13/verify_intraday.json. Healthy means most symbols within
   one percent on identical minutes. This is the last CP6 debt. Note today's
   collector file holds midday test bars, not a real premarket window, which
   is fine: the comparison is minute for minute regardless of the hour. Also
   expect and ignore source disagreement flags on today's picks, because the
   live values came from those midday test bars while the true window is the
   real 04:00 to 09:30 premarket. That mismatch is synthetic and disappears
   on real mornings.
2. First real morning (tomorrow is scheduled): everything fires from Task
   Scheduler. Review the gate table in logs/morning-chain-YYYY-MM-DD.log.
   When ethVolume, baseline medians, RVOLs, premarket highs and bar counts
   look sane, go live: delete data/UNVERIFIED and set RESEND_API_KEY and
   EMAIL_TO in .env. Until both happen, mornings produce reports on disk and
   email nothing.
3. Longer term, as CRITERIA.md's header says: once picks holds a few hundred
   filled outcome rows, revisit the seed thresholds because the data said so.

## Operating notes

- The machine must be awake at trigger times; Task Scheduler does not wake
  it by default. See tasks/README.md.
- The analyst step spends roughly 1.2 to 1.6 dollars of Claude subscription
  per morning at opus. The knob is CRITERIA.md [analyst] model.
- Every job appends to a dated log in logs/. The morning chain stops on the
  first failure, so an empty inbox with a log that stops at scan means the
  packet failed, not the mail.
- To take the schedule down: `powershell -ExecutionPolicy Bypass -File
  tasks\register_tasks.ps1 -Unregister`.
