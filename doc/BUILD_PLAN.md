# PremarketDesk build plan and session handoff

Last updated: 2026-09-02, when the counts and clocks below were re-read
against the tree after the two phase collector landed. "What remains" was
rewritten after the full review on 2026-08-20, when items 5a and 6i were
corrected in place. The notable movers section
was specified in full under "What remains" as Layer 4 on 2026-08-17. The build history below was written on
2026-08-14, after the first live morning and the five commits that followed
it. All sixteen checkpoints are built, verified, and committed, and the seven
Task Scheduler tasks are registered [corrected 2026-09-02 evening: was "the
eleven Task Scheduler tasks"; that evening a task became one per job carrying
every trigger its job has, and tasks/register_tasks.ps1 registers seven]
[corrected 2026-09-02: was "the nine Task
Scheduler jobs"; tasks/register_tasks.ps1 registered eleven]. The system is armed but
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

1. EODHD is the only vendor in the published path. No yfinance, and no second
   vendor anywhere the morning reads. Two nightly steps read Alpaca after the
   session is over, night/true_volume.py for the truth columns and
   night/paper_ledger.py for the one minute bars the ledger books against,
   and both write beside the morning's values and never over them; see
   CRITERIA [Truth]. [corrected 2026-09-02: was "EODHD is the only data
   source. No yfinance, no second vendor."]
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
  - core/    config, criteria, ettime, store, eodhd, artifacts, glossary (the
             one place a plain English word for a column is written down), and
             since 2026-09-02 numbers (the one reading of a vendor number),
             files (the one atomic writer) and page (the one HTML shell every
             renderer wraps its body in). Infrastructure every other package
             rests on; nothing here knows what a gapper is.
  - ops/     job_status, market_today, monitor_jobs, meter_sampler,
             quantifier_flags. Whether the machine is running correctly: the
             status record, the trading day guard, the watchdog, the half
             hourly quota reading and the hand judging tool for the guard's
             flag log.
  - selection/ universe, discover, gap_stats. Which names are worth watching,
             decided before the open.
  - collect/ collect_premarket, baseline. Today's tape, and the volume
             baseline its RVOL is measured against.
  - morning/ scan, vintage, analyst, gap_reasons, render_report,
             verify_morning, deliver. The 08:45 chain in order, with
             gap_reasons the explanation pass the analyst calls for the "Why
             these gapped" section.
  - midday/  scan_midday, render_midday. The 12:00 pass, which answers the two
             questions the 08:45 report cannot because the session it is about
             has not opened yet: what today's picks did against the levels the
             morning published, and what else moved that the morning never
             named. No model and no narrative pass, because midday asks closed
             questions. It writes to nothing the morning owns.
  - night/   backup_evidence, backfill_premarket, fill_outcomes, true_volume,
             paper_ledger, pool_recall, prune_data, weekly_page, in the order
             the nightly runs them, with desk/compact between pool_recall and
             prune and desk/render last [corrected 2026-09-04: was
             build_archive, retired that morning]. What runs once the vendor
             has published the full day. true_volume and paper_ledger are the
             two modules in the tree that talk to Alpaca in production, both
             after the close and neither able to reach a report: see CRITERIA
             [Truth]. [corrected 2026-09-02: was "true_volume is the only
             module in the tree that talks to Alpaca in production", and the
             list omitted backup_evidence and paper_ledger.]
  - desk/    compact, assets, render. The one document below, rebuilt at the
             end of all three chains; compact freezes each session to
             runs/<date>/desk.json.gz, which prune_data reads. Spec: SCREENS.
  - research/ backtest_pool, float_cache, float_rotation_study,
             counterfactual_watchlist, cutoff_0830, replay_session (the live
             screen run over a finished session from Alpaca bars),
             addressable_sweep, vwap_gappers, the four probe_ scripts
             (probe_live_v1, probe_alpaca_live, probe_socket_cap,
             probe_capture_live), the four measure_ scripts
             (measure_baseline_floor, measure_bulk_cost, measure_capture_rate,
             measure_socket_cost) and the two sweep_ scripts
             (sweep_baseline_floor, sweep_capture_rate): eighteen modules,
             counted off the directory.
             [corrected 2026-09-02: was "the three measure_ scripts" and
             omitted cutoff_0830, replay_session, sweep_baseline_floor and
             probe_capture_live.] [corrected 2026-08-28: was "the two measure_
             scripts". measure_baseline_floor.py joined measure_bulk_cost.py
             and measure_socket_cost.py, and it is the instrument behind the
             measurement in CRITERIA's denominator floor note.]
             Instruments, not pipeline. Nothing downstream reads their output.
  - probe_alpaca.py sits at the TOP of src/, not under research/, and is the
             one exception to the line above: night/true_volume.py imports its
             Probe and build_session, so it is the Alpaca transport for a
             scheduled step as well as the instrument that wrote
             doc/ALPACA_PROBE.md. Deleting it stops the nightly truth pass.
  - tests/   conftest, run_tests and the fourteen test_ modules. test_regressions
             holds one claim per defect confirmed by the 2026-08-20 audit;
             they are grouped by how they were found because that is the
             only thing they have in common.
  - src/probe_alpaca.py sits at the root beside the packages: the shared
             Alpaca client the probes use. [corrected 2026-08-22: this went on
             to say "Research only, and no pipeline module imports it", which
             the entry nine lines above already contradicted and which is the
             more dangerous of the two to believe. night/true_volume.py imports
             its Probe and build_session, so this file is the Alpaca transport
             for a SCHEDULED step; deleting it stops the nightly truth pass.
             The entry above is the correct one.]
- doc/: this file, CHANGELOG.md, DECISIONS.md, CRITERIA.md,
  IMPROVEMENT_PLAN.md (the 2026-09-02 review as work packages),
  REPORT_TEMPLATE.md, prompt_analyst.md, prompt_slots.md (what the model is
  piped under CRITERIA [Analyst] mode = slots), the two architecture pages,
  ALPACA_PROBE.md (generated by src/probe_alpaca.py), sample_report.html, and
  research/ holding the written up studies this file cites: COLLECTOR_VOLUME.md,
  SCORE_INVERSION.md, COUNTERFACTUAL_WATCHLIST.md, VWAP_GAPPERS.md,
  TEMPLATE_DERIVATIONS.md, BASELINE_FLOOR.md, CAPTURE_RATE.md and
  FLOAT_ROTATION_FITS.md, eight write ups, beside collector-capture.json and
  two of the five float rotation study payloads, 2026-08-16 and 2026-08-17.
  The larger payloads live under data/research/, which is gitignored with the
  rest of data/: capture_rate_study-2026-09-01.json,
  counterfactual_watchlist-2026-09-01.json, the other three float rotation
  study payloads (2026-08-20, 2026-08-21 and the 2026-08-31 floor sweep), and
  baseline_floor_study-2026-08-28.json, the 241 name payload behind
  CRITERIA's denominator floor measurement.
  That last one carries the raw per session volumes and not only the
  derived table, so the study reruns offline: the 109.9 MB deleted on
  2026-08-21 is what that costs when it is not done
  [corrected 2026-09-02: this put every payload under doc/research; the
  directory listing is the authority and the split above is read off it]
- tasks/: nine job .bat files, register_tasks.ps1, README.md. Seven of them
  register as seven scheduled tasks, one per job, each carrying every trigger
  its job has, with the .bat telling the firings apart by the clock:
  job_nightly on THREE triggers, 22:15 and 07:00 on weekdays (the 07:00 one
  is the catch-up) and Sunday 21:00 (the weekly universe rebuild, which was
  job_universe.bat under its own task until 2026-09-02), and job_monitor on
  THREE triggers, a repeating weekday one from 07:25, a repeating one from
  12:25 and once at 22:45. job_midday joined them on
  2026-08-31 at 12:00. [corrected 2026-09-02 evening: was "ten job .bat
  files", "Eight of them register as eleven scheduled tasks", "again at 07:00
  as nightly-catchup", "monitor-midday from 12:25 and monitor-night once at
  22:45"; those four names were the same three .bat files registered again,
  and were retired that evening with job_universe.bat.] Two further .bat
  files, job_probe_capture.bat and
  job_probe_socket_cap.bat,
  sit here and are not among those seven, both of them one offs armed a
  morning at a time and both meant to be deleted once their question is
  answered. A
  plain run of the script registers neither of them, because a probe that is
  meant to be deleted must not come back every time the schedule is
  refreshed, and `-Unregister` removes both if they are there, and the
  retired socket cost task's name with them. [corrected 2026-09-02: was
  "Three further .bat files" and "removes all three"; job_probe_socket_cost.bat
  was deleted on 2026-09-01 and ten .bat files stood, nine since
  job_universe.bat went the next evening.]
  [corrected 2026-08-31: was "register as ten scheduled tasks", "not among
  those ten", "both meant to be deleted" of three files, and "registers
  neither". monitor-midday was added on 2026-08-31 and takes the count to
  eleven. The "both" predates job_probe_socket_cost, which was added on
  2026-08-31 and which -Unregister did not remove until the same day.]
  job_probe_socket_cap is the instrument for the open collector volume
  question, armed by `register_tasks.ps1 -Probe YYYY-MM-DD` at 06:30. It ran
  on 2026-08-21 and its task was removed the same day. Since 2026-09-02 that
  06:30 arm no longer works: the collector holds the socket from 04:00 to
  09:25, and research/probe_socket_cap.py reads that window from CRITERIA and
  refuses to run inside it, so a task armed at 06:30 would fire and stand
  down. The .bat and the module
  stay: the census half of its answer landed and the cap half did not, and
  re-running it on a regular hours tape after 09:25 is the one thing that would
  settle either, and the one clock the arm would now need.
  job_probe_capture is the Alpaca live capture test, armed by
  `register_tasks.ps1 -Capture YYYY-MM-DD` at 08:45, which is [Scan] run_time
  and not a chosen number: the question is what the free tier serves at the
  clock production asks it. See DECISIONS.md 2026-08-22.
  [corrected 2026-08-31: this said "It is armed for 2026-08-24, so ten tasks
  stand today and `Get-ScheduledTask -TaskPath \PremarketDesk\*` returns ten
  until it is deleted". Every part of that had gone stale. probe-capture is
  no longer registered; probe-socket-cost is, armed for 2026-09-01 10:00; and
  the recurring count is eleven rather than ten. A sentence naming a live
  count is a sentence that goes wrong the next time the schedule moves, so
  the count is not restated here: run the command and read it.]
  job_probe_socket_cost is the per message websocket cost probe, armed by
  `register_tasks.ps1 -SocketCost YYYY-MM-DD` at 10:00, inside regular hours
  and clear of both the collector's 09:25 stop and the 12:00 midday job. It
  measures the ONE number the socket still owes, and that number gates moving
  [Collector] stop_time past the open AND moving start_time earlier than
  07:20, which is the larger of the two prizes: the RVOL numerator starts at
  07:20 and its baseline denominator accumulates from 04:00, and
  [start_time was moved to 04:00 on 2026-09-02, once this probe had returned
  a per message cost of zero. See DECISIONS.md 2026-09-02 ninth. The prize
  turned out to be larger than the ratio: the published entry reference sat a
  median 1.19 percent from the true premarket high, ten to one attributable to
  the late start rather than to the feed.]
  collector_window_share puts the median cost of that mismatch at 0.366 over
  all 68 picks rows, and 0.407 over the 46 that survive the capture study's
  session guards. Both are real and neither is the other: the first is the
  number a reader takes off the table without the guards, the second is what
  data/research/capture_rate_study-2026-09-01.json publishes under
  residual_no_divisor_closes.
  RAN 2026-09-01 10:00:01 to 10:20:05 and the task and the .bat were deleted
  the same day, which is what its own header said to do once the number was
  written down. 21,306 messages on a live regular hours tape moved the vendor
  counter by ZERO. The answer and the three part decomposition it settles are
  in DECISIONS.md 2026-09-01 eighth. The module stays under src/research/,
  because research/measure_bulk_cost.py imports read_counter from it, and it
  now carries a warning: it launches collect_premarket, which writes to the
  premarket session capture, and the 2026-09-01 run put 932 regular hours
  bars in that file before they were arbitrated back out.
  job_probe_alpaca_live and job_probe_live_v1 sat here too and were deleted on
  2026-08-20 once both questions were answered and recorded in DECISIONS.md;
  their modules stay under src/research/
- data/: universe.json, watchlist.json, universe-closes-YYYY-MM-DD.json,
  premarket/YYYY-MM-DD.jsonl, premarket/YYYY-MM-DD-stats.jsonl,
  premarket/YYYY-MM-DD-subscriptions.json (what the collector asked the socket
  for, written at subscribe time), premarketdesk.db, ca-bundle.pem,
  job-status.jsonl (one line per scheduled step per run),
  exchange-details.json (the holiday cache), monitor-reruns.json,
  float_cache.json, quantifier-flags.jsonl once the guard fires on a live
  morning, UNVERIFIED (the delivery gate marker). Beside those sit the research
  instruments' outputs, which no pipeline module reads but which two open items
  above rest on: socket-cap-probe-YYYY-MM-DD.json (item A's own instrument,
  run 2026-08-19 and 2026-08-21, nothing armed after that), purged-picks-YYYY-MM-DD.jsonl (the picks rows emptied
  on 2026-08-19), addressable_sweep.json, the probe-alpaca-live and
  probe-live-v1 files, and backtest/eod and backtest/sessions.
  [2026-08-21: data/ was 145 MB and is 35 MB. backtest/bars,
  vwap_gappers_trades.csv and alpaca_assets.json were deleted on the owner's
  instruction: 109.9 MB, all of it input to the VWAP gappers study, whose
  pre-registered stop rule fired. The 748 line report keeps every table and
  both verdicts; what is gone is the ability to rerun it offline, and a rerun
  now means refetching from Alpaca. vwap_gappers.py stays and says so on
  startup. NOTHING under data/ is in git, so none of this was recoverable and
  none of it was decided here.
  data/ also gained its first retention of any kind. night/prune_data.py runs
  in the nightly and deletes universe-closes files past [Universe]
  closes_retention_days. What it may delete is a WHITELIST naming that one file
  class; premarket/, backtest/eod, backtest/sessions and runs/ are not in it
  and claim 72 holds that. See CRITERIA's closes retention note.]
- runs/YYYY-MM-DD/: packet.json, premarket_snapshot.jsonl, report.md,
  report.html, analyst_usage.json, midday_packet.json, report_midday.md and
  report_midday.html from the 12:00 pass, and once the nightly job has run,
  verify_intraday.json and pool_recall.json. Three more appear only on the
  mornings that earn them: report.slots-rejected-N.md, the model answer the
  slots check refused, kept beside the report; packet_degraded.json, written
  when a quota thinned rerun would otherwise have replaced a fuller packet;
  and premarket_snapshot.superseded.jsonl, the earlier snapshot a rerun of the
  scan set aside rather than overwrote
- site/Weekly.html: one page saying whether the week worked, rendered by
  night/weekly_page.py at the end of the 22:15 nightly. Five sections: did it
  run, is the data trustworthy, what did it publish, what did it cost, and
  does the score order anything. It reads
  job-status.jsonl, the meter trail, quantifier-flags.jsonl,
  runs/<date>/verify_intraday.json, the packets' score components, and the
  picks and paper_trades tables, and writes this file.
  [corrected 2026-08-31: was "Four sections" and named four. The score watch
  shipped as a fifth and README.md already said five.]
  No vendor call, no new table, no measurement of its own. Gitignored with the
  rest of site/
- site/PremarketDesk.html: THE DESK since 2026-09-04, when build_archive was
  retired and desk/render took its filename. Every session in one document on
  eight hash routes, each inlined gzipped and inflated in the page. Rebuilt
  whole at the end of all three chains, not by the 07:00 catch-up
  (desk/render.py, inline_sessions in CRITERIA [Screens]); gitignored

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
  still null, and the nightly task also fires job_nightly.bat at 07:00, the
  catch-up firing it recognises from the clock, so yesterday's fill and
  volume verification complete
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
  below [and back to low on 2026-09-02 with the move to slots mode, where the
  model fills marked slots rather than writing the page; CRITERIA [Analyst]
  effort carries the measurements], and five medium runs measured 97.4, 86.5, 97.7, 91.1 and 92.4
  seconds, so timeout_s is 537, derived on 2026-08-20 as three times the
  slowest morning THEN on record, 178.9 seconds of CLI time on 2026-08-19.
  The 2026-08-20 morning has since run 226.1 seconds of CLI time inside a
  231.7 second analyst step, so 537 is 2.4 times the slowest morning rather
  than three and the derivation is owed a re-run. See item 5b below and the
  timeout note in CRITERIA.md, whose table also stops at 2026-08-19.
  [corrected 2026-08-29: the re-run was owed for eight days and is done.
  timeout_s is 1007, three times the 335.7 seconds of 2026-08-27, which is the
  slowest morning on record. [monitor] job_log_stale_after_s moved with it,
  1200 to 2200, because it is derived from it. The rule never changed; its
  evidence did, twice. CRITERIA's timeout note carries every session.] [corrected 2026-08-20: was
  "timeout_s is now 293, three times the slowest", derived from those five dry
  runs. The rule is unchanged and the evidence under it is not; see the timeout
  note in CRITERIA.md for the table and the slack arithmetic.]
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
  CRITERIA.md high importance list owns that call), calendar/earnings, user.
  [corrected 2026-08-20: `search` was listed here and eodhd.py has never
  wrapped it. EodhdClient has no search method and nothing under src/ calls
  one. The two wrappers this list does not name are live_quotes, the per
  symbol real-time call no scheduled job makes, and news_feed.]
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
  by exactly zero. The /user reads themselves did not register either. The
  per message cost on a heavy live tape was the one number still owed, and it
  was measured on 2026-09-01 at ZERO across 21,306 messages on a regular hours
  tape (DECISIONS.md 2026-09-01 eighth). [corrected 2026-09-02: this said the
  cost was "still owed, measurable any weekday by running
  measure_socket_cost.py inside 04:00 to 07:15 before the jobs wake". It is
  paid, and that idle window no longer exists: the collector has held the
  socket from 04:00 since 2026-09-02.]
- Measured 2026-08-13 at 23:05 ET with measure_bulk_cost.py: ONE bulk live
  OHLCV request (real-time/AAPL.US?ex=US) moved the vendor counter by
  exactly 100 for 18,341 returned rows, in one HTTP attempt, after a 45
  second quiet watch showed zero meter drift. A flat per request rate, not
  per symbol. Verdict against the 1,000 line: NOT crossed. That measurement
  was of the bulk live call, which no scheduled job makes any more. The
  day's bulk calls are now end of day: three on each of discover's two passes,
  at 03:55 and 07:15, two for the prior session movers and one for the third
  close the briefing's two session leg needs, so six from discover; one at
  12:00 for the midday pass's prior session denominator; and two at 22:15 for
  the pool recall, at a measured 100 credits each, so about 900 a day on the
  shared 100,000. [corrected 2026-09-02: was "three at 07:15 ... and two at
  22:15 ... about 500 a day"; discover gained its 03:55 pass on 2026-09-02 and
  the midday pass its bulk day on 2026-08-31.] [corrected 2026-08-20: was
  "two at 07:15 ... about 392 a day". discover.py makes three
  eod_bulk_last_day calls and the 2026-08-20 call report counted three; 392
  was ledger arithmetic CRITERIA.md corrected away from on 2026-08-17, and it
  did not close on four calls at 100 either.]
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
  `python -m collect.collect_premarket --verify-intraday` with PYTHONPATH set
  to src, against EODHD 1m bars, evenings.
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

CP10 analyst: doc/REPORT_TEMPLATE.md (nine fixed sections)
[corrected 2026-08-20: was "eleven fixed sections"; the file has held nine
since it was written, and the architecture page has said nine throughout]
[since 2026-08-29 the file holds eleven: notable movers landed 2026-08-20 and
the record block, which quotes paper_ledger.record_so_far, on 2026-08-29. The
count in this line is left at what CP10 verified],
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
CRITERIA.md. [Superseded the same evening: the owner re-asserted opus, and
CRITERIA [analyst] has read model = opus ever since. timeout_s read 293 from
that evening until 2026-08-20, when four real mornings re-derived it to 537 on
the same 3x rule; the timeout note in CRITERIA.md carries the table. The
original text stands because it records what was true when it was written.] The containment checker was also rebuilt: a claim is an
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

CP15 scheduling: tasks/ holds five .bat jobs
[superseded, see Repository layout above: seven job .bat files register as
seven tasks today, one per job carrying every trigger the job has, the
additions since being job_monitor.bat, on three
triggers, job_meter_sampler.bat and job_midday.bat, and the universe job moved
from Sunday 20:00 to 20:30 on 2026-08-16 and to 21:00 on 2026-08-17, then
folded into job_nightly.bat's Sunday trigger on 2026-09-02;
corrected 2026-09-02 evening: was "eight job .bat files register as eleven
tasks", and earlier that day "seven job .bat files register as nine tasks"], each cd's to the project root,
stamps its log date with the project's own ET clock, and appends to
logs/<job>-YYYY-MM-DD.log. The 08:45 chain (scan, analyst, render, gate
table, deliver) ran end to end from the bat with rc=0 at every step.
register_tasks.ps1 registered all five: discover 07:15 (which also warms the
baseline cache, an addition to the original brief, because scan must never
fetch baselines), collector 07:20, morning chain 08:45, nightly 22:15, all
[the morning half of this moved on 2026-09-02: discover carries a second
trigger at 03:55 and the collector starts at 04:00 with a six hour execution
limit, because a four hour one would have killed it at 08:00.]
Mon to Fri, universe Sunday 20:00. [The universe hour moved twice after this
was written. 20:00 was the exact instant of the quota reset, so which quota
day the largest job in the schedule billed to was a coin toss; 20:30 assumed
the vendor's counter rolls on the hour, and the 2026-08-16 run measured the
roll landing 30 to 32 minutes late. It has read Sunday 21:00 since
2026-08-17, and CRITERIA [job status steps] carries the same correction.]

CP16 gate: src/morning/verify_morning.py prints the evidence table (ethVolume,
baseline median, pm_rvol, collector premarket high, bars) for the top
candidates and the chain logs it every morning. data/UNVERIFIED exists;
deliver.py refuses to email while it does, proven with keys present in the
environment: refusal message, zero HTTP calls, exit 0. Nothing in the code
deletes or recreates the marker on its own; `verify_morning.py --arm`
recreates it deliberately.

## What remains

STATE AS OF 2026-08-20, AFTER THE FULL REVIEW. A twenty agent adversarial read
of the whole tree raised 187 findings, 19 survived verification, and all 19 are
now closed with a claim each. What that review found is in CHANGELOG.md under
"2026-08-20, seventh"; the purge that preceded it is under "sixth". Items 5a
and 6i below were MIS-DOCUMENTED here, describing work that had already
shipped, and are corrected in place. The suite is 44 claims in
test_regressions plus eleven other modules, green three consecutive runs, with
the tree photograph clean.

**[2026-08-21: THE CODE IS FROZEN except for defects that make published
numbers wrong, or changes that make the record readable. The tree is 42,949
lines of Python and 14,869 of documentation, scan.py is 4,533 lines, and
CRITERIA carries 260 thresholds for a screen with five conditions. Every
finding that produced that growth was real and the aggregate is still past what
one person can audit. Before writing anything, answer: which published number
is wrong today, and where would a reader see it. No answer means the change
waits for the outcome rows. The items below are the record of what was built,
not a queue. See DECISIONS.md 2026-08-21 seventh for the rule and its
reasoning.]**

**[2026-09-02: THE REVIEW AND ITS TIERS. A four pass review of the whole tree
was written as doc/IMPROVEMENT_PLAN.md and, on the owner's instruction, its
five tiers were built the same day: five defects fixed; the report reorganised
around an at a glance strip and a Technical signals table; the narrative pass
moved to slots mode, in which analyst.fallback_report writes the whole report
and the model fills five kinds of prose slot (CRITERIA [Analyst] mode = slots,
effort = low, the measurements in CRITERIA's slots note); one page shell in
core/page.py; one float reading, one atomic writer and a criteria check in
core/; and the range confound on SCORE_INVERSION.md's register with the pick
day open and close stored for every pick. The freeze above was lifted for that
work by the owner and the items it left open are in the plan's tier notes and
in DECISIONS 2026-09-02 sixth, which are the decisions the measurements now
wait on; the owner dropped the fifth of them, the UNVERIFIED disposition, from
the plan the same day and the gate is unchanged. CHANGELOG 2026-09-02 thirty
second to thirty seventh. Later that morning GTLB opened about 25 percent
higher after reporting after the prior close and was not on the list, because
the earnings prior read only before open reporters; discover.earnings_reporters
now reads the prior session's after close rows as tier 1 (plan 0.6, CHANGELOG
thirty eighth, DECISIONS seventh). The same afternoon the owner said the
report looked unprofessional, which turned out to be three faults: a sentence
in CRITERIA shadowed the [Analyst] mode key so slots mode had never once run
and every morning was written freeform, markdown lists were rendering as
prose for want of a blank line, and the page was laid out to fit rather than
to be read. All three are fixed and the day's report regenerated in slots
mode (plan 0.7 to 0.9, CHANGELOG thirty ninth, DECISIONS eighth).]**

**[2026-09-04: the screens are specified in doc/SCREENS.md and none of them
are built. Read it first. The freeze was lifted for it. CHANGELOG fifty seventh.]**

WHAT IS ACTUALLY STILL OPEN, in one place, so a new session does not have to
reconstruct it from the numbered items below:

  A. Collector premarket volume disagrees with the vendor, and as of
     2026-08-20 the likeliest reason is measured rather than guessed (item 1).
     This is still the delivery gate. The vendor comparison that
     COLLECTOR_VOLUME.md called "the one clean reading nobody has taken" has
     now been taken: over the 2026-08-19 probe window the socket delivered
     between 2.1 and 12.1 percent of EODHD's own consolidated bars for the
     same minutes, at BOTH subscription sizes. Subscribing to fewer names buys
     nothing. The remaining fork is whether the trades stream simply omits off
     exchange volume, which no collector change reaches, or whether it marks
     those prints with a condition code the parser does not read, which is a
     fixable bug. That file answers NEITHER side: off_exchange,
     off_exchange_volume, census and keys_seen were all added to the probe
     after 2026-08-19, and until 2026-08-20 the comparison printed the missing
     off exchange counter as a measured zero, which is the reading that would
     have closed the fork the wrong way.
     [2026-08-21: THE FORK IS CLOSED, on the structural side. The probe ran at
     06:30 on a premarket tape and the census came back unanimous: all 123
     trade messages carried c=[], an empty condition list, and dp=False. There
     is no condition code for the parser to be missing, so no collector change
     reaches the missing volume and the capture calibration already shipped in
     CRITERIA [Collector] is the whole answer rather than a stopgap. 123
     messages is a small sample and it is 123 of 123; a census on a regular
     hours tape would settle it past argument and costs only socket time.
     The same run also says NOTHING about the cap: no symbol reached 20
     messages on both arms, so there is no median to take. It printed 0.58 on
     the morning and that reading has been withdrawn. What still carries "the
     cap is innocent" is the vendor comparison above, at both subscription
     sizes, plus fifty symbols at fourteen times the collector's rate losing
     none, and both were taken at 09:35 on a regular hours tape rather than
     before 07:20. See COLLECTOR_VOLUME.md, last three sections.]
  B. The notable movers section, Layer 4, IS BUILT as of 2026-08-20 and all
     four [Notable] CRITERIA keys are now read. scan.notable_movers assembles
     it, the packet carries notable_movers, REPORT_TEMPLATE.md has the section,
     prompt_analyst.md has rule 15, fallback_report emits it too, and
     tests/test_notable.py holds twenty eight claims wired into run_tests.SUITE.
     [corrected 2026-09-02: was twenty six; CLAIMS holds twenty eight entries
     today.]
     [corrected 2026-08-22: this said thirteen, which was the count on the day
     the section shipped and had not moved since. It was twenty four before
     today's two were added. The number is CLAIMS at the foot of that file and
     main() prints it; count it there rather than trusting this line.]
     What it produces on the first shipped morning is thin and correctly so:
     every return_stdev_20d in the database is null until the Sunday 21:00
     rebuild, so lists 1 and 4 come back empty on their ranking key while their
     legs are perfectly available, and list_reasons says exactly that.
     [2026-08-22: "says exactly that" was too generous. It said the lists were
     "short" and gave a reason with no state and no denominator beside it, so a
     reader could not tell a null column from a quiet market. Every ranked list
     now publishes one of four fixed states with the count it considered: see
     4.4 and 4.9 below.] Two
     things it surfaced belong to the owner and are in DECISIONS.md: universe.json
     carries at least two implausible market caps and list 2 is the first thing
     in this project that RANKS by that column, and a close to close move over
     these windows is not adjusted for corporate actions.
  C. Two threshold questions that belong to the owner, not to the code: the
     seed thresholds await a few hundred filled outcome rows (item 3, and note
     that picks was emptied on 2026-08-19 and now holds one session), and the
     day-setup eligibility question for names rescued by float rotation (item
     2b, with a second instance on 2026-08-20).
  D. Nine lower severity findings from the same review were filed at high
     severity and never adversarially verified, because the review verified
     only the top 26 of 186. Three bore on numbers already relied on. ALL
     THREE ARE NOW VERIFIED AND CLOSED, and all three were real, which is
     worth carrying forward to the six that are still unexamined: a finding
     filed without verification is not the same as a finding that is wrong.
       - probe_socket_cap.compare_to_vendor summed whole vendor minute bars
         against 120 second arms. All eight arms of the only run that exists
         started between one and thirty four seconds into a minute, so the
         inflation was not "about 1.5x", it was exactly 1.5x on every arm.
         Each bar now contributes only the fraction of itself the arm covered.
         claim_a_partial_minute_counts_only_the_seconds_it_covered.
       - float_rotation_study's cold start. Measured, not estimated: 894 of
         2,464 rescued rows, 36.3 percent of the population the shipped
         CRITERIA [Float rotation] band edges were read off, came from the
         first ten sessions, where `history` is too short for ANY name to
         carry an RVOL and every name with a float is rescued by construction.
         The rescue rate runs 84 to 93 percent across those ten and 7 to 22
         percent from the eleventh. The study now walks the warm up for
         history and refuses to tally it. RE-FITTING THE EDGES IS STILL OWED
         and is an owner decision, because the archived payload holds
         percentiles rather than rows, so the corrected distribution cannot be
         computed from it and a re-run spends Alpaca requests. See DECISIONS.md
         2026-08-20 on the warm up. claim_the_rotation_study_counts_no_warm_up_session.
       - config.ca_bundle() wrote the merged trust store with a plain
         write_text and re-serves it on mtime alone, so a truncated file
         carried a fresh mtime and would be served until certifi changed, and
         the local inspection root is appended LAST, so a truncation loses
         exactly the root that makes an intercepted connection verify. Now a
         temp sibling and os.replace, on universe.write_atomically's
         precedent, plus a refusal to merge a source that came back carrying
         no certificate at all. claim_the_trust_store_is_never_served_half_written.
     One more, found while closing them rather than filed by the review: the
     tree photograph failed about one run in six on .git/FETCH_HEAD, because
     this machine carries "git.autofetch": true and VSCode fetches every 180
     seconds. That one path is now exempt, narrowly, and
     claim_no_python_here_runs_a_git_fetch keeps the exemption honest.
  E. data/UNVERIFIED is still in place and delivery is still gated. Nothing
     about the review changes that; item A is what it is waiting on.

The numbered items below are kept as written, with their outcomes recorded,
because what a fix WAS is the useful part.

1. The definitive collector volume verification (the last CP6 debt) now
   lands with the FIRST LIVE morning's nightly. The 2026-08-13 rows were
   all marked source='test' by the 2026-08-14 migration and the backfill
   only touches live rows, so no verify_intraday.json will appear for
   2026-08-13 and none is owed: its collector file held midday test bars,
   not a premarket window. Check runs/(first live date)/verify_intraday.json
   after that evening's 22:15 run. Healthy means most symbols within one
   percent on identical minutes.

   ANSWERED 2026-08-18, AND IT IS NOT HEALTHY. The reading landed for
   2026-08-14 and was 0 of 37 symbols within one percent. Diagnosed in
   doc/research/COLLECTOR_VOLUME.md: the check is sound, the collector is at
   fault, and it is not a constant shortfall. Signed, 2026-08-17 reads -88.49
   percent across all 29 comparable symbols while 2026-08-14 comes back mixed
   and 3.83 times the vendor in aggregate, and the collector's figure for one
   ETF swings up to 181x between the two mornings where the vendor's moves
   1.1x. This is now the top open item: collector volume is the numerator of
   both pm_rvol and pm_float_rotation, so it sits under every volume score
   published so far, and it is a reason to leave data/UNVERIFIED in place
   rather than something to tidy after go live.
2. First real morning (tomorrow is scheduled): everything fires from Task
   Scheduler. Review the gate table in logs/morning-chain-YYYY-MM-DD.log.
   When ethVolume, baseline medians, RVOLs, premarket highs and bar counts
   look sane, go live: delete data/UNVERIFIED and set RESEND_API_KEY and
   EMAIL_TO in .env. Until both happen, mornings produce reports on disk and
   email nothing.
3. Longer term, as CRITERIA.md's header says: once picks holds a few hundred
   filled outcome rows, revisit the seed thresholds because the data said so.

2b. Two findings from 2026-08-18, both in DECISIONS.md that date, neither built.
   The report's "most common failed condition" sentence is computed by the model
   from twelve per candidate lists because the packet carries no tally, and on
   2026-08-18 it was false in the strongest form, claiming every candidate missed
   a condition one candidate cleared. The fix is to compute the tally in scan.py
   and have the template quote it. Separately, the day-setup eligibility question
   for names rescued by float rotation is NOT inert as 2026-08-16 third claimed,
   and 2026-08-18 is the counterexample: AS.US scored 8.0 green, cleared the
   prior high, and was the only one of twelve to do so, and its whole day_failed
   list was the null RVOL. That one is a threshold question and stays with the
   owner.
4. The notable movers section: SPECIFIED BELOW, AND BUILT ON 2026-08-20. Its
   specification is the "Layer 4" section immediately below, written out in
   full on 2026-08-17 so that no part of the design lives only in a
   conversation. The specification is kept exactly as written, including the
   four places building it proved the specification wrong, because what the
   design WAS is the useful part and each of those four is annotated where it
   stands. See CHANGELOG.md "2026-08-20, eleventh" for what shipped and
   DECISIONS.md for the five calls made while building rather than by the
   owner.

5. From the 2026-08-20 review, two of five findings that were thought open when
   this was written, both since closed: 5a described work that had already
   shipped and 5b was re-derived the same day. Neither is in the A to E list
   above. The three
   that are closed are recorded here because the closure is the useful part:
   an empty candidate pool ended scan.py with an UnboundLocalError instead of
   writing the zero candidate packet both architecture pages describe; the
   nightly calendar refresh deleted data/exchange-details.json before
   fetching, so one 22:15 vendor outage left no holiday list at all and the
   next morning assumed the market was open; and test_vintage replaced
   market_today.is_trading_day for the whole process and never restored it, so
   every suite after it in run_tests, test_entrypoints' calendar claims
   included, had been running against a weekday rule with no holidays in it.
   All three are fixed and all three now have claims. What remains open:

   5a. THE NIGHTLY NO LONGER TAKES THE COLLECTOR VOLUME MEASUREMENT. Item 1
       above is the top open question and its instrument has stopped running.
       backfill_premarket returns early when the day has no live picks rows,
       and verify_against_intraday sits after that return, so emptying picks
       on 2026-08-19 also ended the nightly's write of
       runs/<date>/verify_intraday.json. 2026-08-14, 08-17 and 08-18 have one;
       08-19 does not, and nor will any night until picks refill. Until then
       the reading has to be taken by hand:
       `python -m collect.collect_premarket --verify-intraday <date>`. The fix
       is to move that block ahead of the early return, since it reads the bar
       file and the intraday feed and needs no picks row at all. Not done here
       because it changes what a scheduled job does on a night nobody is
       watching, and the diagnosis in doc/research/COLLECTOR_VOLUME.md may
       want a different shape of reading anyway.

       [corrected 2026-08-20: the fix HAD ALREADY SHIPPED when this was
       written, and this item described work that was done.
       backfill_premarket.py calls verify_volume under the comment "Before
       anything else, and before any path that can return early", ahead of the
       early return, and unverified_sessions sweeps collected sessions with no
       picks rows. CHANGELOG.md and both architecture pages recorded it; this
       file did not, which matters because this file is what a new session is
       told to read first. The full review found the discrepancy by checking
       the code rather than the register. A separate and real hole in the same
       instrument WAS found and is now closed: the writer used write_text,
       which truncates before it writes, while the only reader skips a copy it
       cannot parse, so a crash mid write retired that session from the sweep
       forever. It writes through a temp file and renames now.]

   5b. CLOSED 2026-08-20 by re-deriving the number, and it leaves a question
       behind. CRITERIA [analyst] set timeout_s = 293 as three times the
       slowest of five dry runs (97.4, 86.5, 97.7, 91.1, 92.4 seconds). Four
       scheduled mornings have since measured 89.1, 48.4, 98.5 and 178.9
       seconds of CLI time, 54.4, 107.5 and 185.3 seconds of analyst step time
       on the three the job trail covers, with output tokens at 7,697, 4,000,
       8,954 and 16,005. The rule did not change; its evidence did. timeout_s
       is now 537, three times the slowest morning on record, and the timeout
       note in CRITERIA carries the table and the slack arithmetic: two
       attempts exhaust at 09:03 rather than 08:55, both well clear of the open
       and of the watchdog's 09:25 pass. [corrected 2026-08-29: 537 held until
       then and is 1007 now, on the same rule against the 335.7 seconds of
       2026-08-27. Two attempts exhaust at 09:18:53, still clear of the open
       and six minutes clear of the 09:25 pass.]

       WHAT IS STILL OPEN, and it is a threshold question rather than a code
       one, so it stays with the owner: the analyst step is close to DOUBLING
       every session, 54.4 to 107.5 to 185.3, and it tracks output length
       rather than model speed. 16,005 output tokens on 2026-08-19 is double
       the previous high against a template whose nine sections did not change.
       Raising the timeout buys room for that trend and explains none of it. If
       the next morning lands near 350 seconds the question is what the model
       is being asked for, not what the timeout is.

       MEASURED 2026-08-20: 231.7 seconds, 20,188 output tokens. The doubling
       did not continue, the step is now 43 percent of the 537 second timeout,
       and the growth from 185.3 is 25 percent rather than 72. One session is
       not a trend broken, but the alarming reading of this is no longer the
       best one, and the timeout has room for another session like it.

6. From reading the 2026-08-20 REPORT rather than the code, eleven findings.
   ALL ELEVEN ARE NOW CLOSED. The two material ones landed first and are in
   CHANGELOG.md: the collector volume check now reaches the packet and the
   report, and the trap verdict is decided on the balance of a ticker's
   headlines in Python rather than on the worst single one by the model. The
   nine below were accuracy and completeness rather than falsehood, each wanted
   its own argument, and each got one in the pass recorded as the fifth
   CHANGELOG entry for that date. Every one carries a claim in
   src/tests/test_regressions.py. They are kept here rather than deleted
   because what the fix WAS is the useful part, and because one of them
   is only partly recoverable.

   6a. CLOSED. A RANK CAP DROPS SIX NAMES AND THE REPORT CANNOT SAY SO. The 2026-08-20
       report said 18 cleared the price and gap floors and 12 were kept, which
       is correct and unexplained: [Scan] candidate_count is 12 and the other
       six were truncated, not screened out. candidate_provenance.ranking
       records kept: 12 without recording that a cap did it, so a reader cannot
       tell a rejected name from a cut one. Wants a capped_out count and the
       symbols, or an argument that a reader does not need them.

   6b. CLOSED. THE SCORE ROLL-CALL OMITS A TIED NAME. "MSTR and WMT green at 7" was
       written on a morning where SCSC also scored 7.0 green. Nothing false,
       but the enumeration reads as complete. This is the model summarising a
       set the packet already knows exactly, which is the same shape as the
       screen_tally problem and probably has the same answer.

   6c. CLOSED. "STRONGEST SCORED" IS DIRECTION BLIND. The gap component scores the
       ABSOLUTE gap, so AAP tied FUTU at 8 while falling 21.75 percent on an
       earnings miss, below its VWAP, its prior high and its 200 day average.
       Calling the two of them jointly the strongest scored names without
       saying the score has no sign invites the wrong read. The score is
       working as specified; the sentence describing it is not. Either the
       template says so every time, or the packet carries a direction next to
       the score.

   6d. CLOSED. A NULL RVOL AND A MEASURED LOW ONE ARE COUNTED AS ONE FAILURE.
       "premarket_rvol 10 of 12" folded in the two candidates whose RVOL could
       not be computed at all. Withholding them from the screen is right;
       presenting an unmeasured condition and a failed one under one number is
       not, and it runs against the rule that missing evidence stays visibly
       missing. screen_tally wants a third count.

   6e. CLOSED. TWO VENDOR PRIOR CLOSES FOR SCSC DISAGREED BY 1.67 PERCENT. The end of
       day record said 51.42 and the delayed quote in the same packet said
       52.2909. The gap was computed from the first, 16.34 percent; from the
       second it is 14.4. Every other candidate agreed to within rounding
       except BLSH at 0.15 percent. The packet picks one silently and should
       carry the disagreement the way pm_source_disagreement already does for
       the premarket high.

   6f. CLOSED. FOUR BARS AND 1,487 SHARES WAS DESCRIBED ONLY AS "PARTIAL". SCSC's
       entire premarket record that morning was four one minute bars, and the
       16.34 percent gap, the 56.78 VWAP and the 59.82 high all rest on it.
       pm_window_starts_late covers a window that opened twenty minutes late
       and a window that is essentially not there with the same word. Wants a
       floor below which the evidence is called what it is.

   6g. CLOSED. TWO REPLAY-ONLY PRINTS WERE DESCRIBED AS NO PRINT AT ALL. "HOV, LYTS,
       NBTX and UUP were subscribed and the socket delivered no trade for
       them" is true of HOV and LYTS, which have no row. NBTX has one bar at
       04:23 for 20 shares and UUP one at 07:00 for 1 share, both correctly
       tagged replay and correctly excluded from the window. "No trade inside
       the window" is the exact sentence and the packet's own reason string is
       what needs rewording.

   6h. CLOSED. THREE RVOL DENOMINATORS WERE UP TO SIX DAYS OLD. The 07:15 baseline
       warmed 26 and reused 24, which is the design under a seven day refresh.
       But BLSH's denominator was computed on 2026-08-14, BABA's on 08-17 and
       ASST's on 08-18, and the report presented those RVOLs beside freshly
       computed ones with no distinction. Legal and invisible. baseline
       computed_at is already in the packet per candidate; nothing reads it.

   6i. CLOSED IN PART. THE SUITE WRITES TO REAL DATA WHEN A MODULE IS RUN DIRECTLY. Running
       `python -m tests.test_containment` outside run_tests.py appends its
       fixtures to the real data/quantifier-flags.jsonl, because
       conftest.activate() is applied by run_tests and by nothing else. Found
       on 2026-08-20 by doing it: sixteen fixture rows landed in the real log,
       two of them judged, which then failed the sandboxed suite as well
       because activate() copies data/ in. The rows were removed and the real
       log holds its one genuine flag. The tree photograph cannot catch this,
       since the path already exists and only its contents change. Wants
       either a refusal to run a suite module outside the sandbox, or a
       content hash in the photograph.

       CLOSED by the first, inverted: conftest.standalone() WRAPS the hand run
       in the sandbox rather than refusing it, and every suite module routes
       its __main__ through it. Refusing would push a person chasing a failure
       toward a twelve suite pass or toward commenting the guard out.

       STILL OPEN, and it is the other half: the tree photograph compares path
       SETS, so a test that overwrites a file that already exists is invisible
       to it. A content hash over the watched paths would catch what the set
       comparison cannot. Not attempted here because it is a different question
       from the one that bit, and because hashing 414 watched paths twice a run
       wants a measurement first.

       [corrected 2026-08-20: THIS WEAKNESS DOES NOT EXIST AND DID NOT WHEN
       THIS WAS WRITTEN. snapshot_tree records ("file", st_mtime, st_size) per
       path and differences() compares the whole tuple, with an explicit
       branch saying "a same size overwrite is a real escape mode and the check
       must not start guessing which is which". A test that overwrites an
       existing file moves its mtime and is caught. The paragraph above
       described a set comparison the code has never done. What that escape
       really left behind was residue, not a hole: runs/2026-01-05 and
       runs/2026-01-06 held test_containment fixtures in the real runs tree,
       published in the archive as sessions, and they were purged the same day.
       See CHANGELOG.md "2026-08-20, sixth".]

       WHAT IS STILL OPEN IN THE SAME AREA, found by the full review and now
       closed, recorded because the shape recurs: standalone() wrapped a hand
       run in the sandbox and printed that the real runs/ was not writable from
       there, which was false. The module had already executed, so its import
       time Path constants still pointed at the real tree, and importlib.reload
       cannot rescue a module running as __main__. test_repricing.RUN_DIR was
       runs/2026-08-14 inside the sandbox and claim_three opens a database in
       it. standalone() rebinds those constants now and prints which ones it
       moved.

## Layer 4: the notable movers section, BUILT 2026-08-20

STATUS IS RECORDED IN "What remains" ITEM B ABOVE, and that is the line to read
first: the section shipped on 2026-08-20 and this heading said "specified" until
2026-08-22, which sent at least one reader looking for unbuilt work in a section
the same file records as done.

Ordered by the owner on 2026-08-16, settled over the two days after, and
amended on 2026-08-17 by three rulings recorded in DECISIONS.md. This is the
whole design, and it is now also the record of what was built from it: where the
shipped section has moved past a paragraph below, the paragraph carries a dated
note rather than being rewritten, so the original call and the change to it are
both readable. Where a point was decided while writing this down rather than by
the owner, it says so, so it can be overruled cheaply.

### Already built, do not rebuild

- CRITERIA.md [Notable]: list_size 5, min_abs_gap_pct 1,
  min_sessions_for_move_sigma 20, min_return_stdev_pct 0.1, and the prose
  above them stating what the section is and is not.
- data/universe-closes-<date>.json, written by discover at 07:15. sessions
  names the three session dates as c1, c2, c3; closes holds
  {SYMBOL: {c1, c2, c3}}; universe_examined, names_with_at_least_one_close,
  names_with_close per session, names_with_both_closes_for_leg per leg and
  third_session_available carry the denominators. The last two were added on
  2026-08-20, after an empty bulk payload left c1 null on all 2,754 rows while
  the file went on advertising names_with_at_least_one_close 2,754, and they
  are already what 4.9 below asks the section to report per leg, so do not
  recompute them. A closes file written before 2026-08-20 carries only the
  first two. c1 is the prior session
  close, c2 the one before it, c3 the third back. The third session costs one
  extra bulk call, a flat 100 credits, and is bought rather than read from
  gap_stats so that all three closes carry ONE vintage. A name missing from a
  session is null there and is never backfilled from a neighbouring session.
  THIS IS THE SECTION'S ONLY PRICE SOURCE for every name the collector did
  not hear.
- gap_stats.return_stdev_20d: the standard deviation of daily close to close
  returns in percent over the trailing [Gap stats] return_stdev_sessions, 20,
  null below [Notable] min_sessions_for_move_sigma returns. Computed from its
  own close only filtered list rather than from the bar list the other columns
  use. [corrected 2026-08-20: the reason given here was that the bar list
  "drops bars missing an open". It did until 2026-08-20, when that drop was
  found to break the close chain and each measurement was guarded on the field
  it needs instead; see CHANGELOG.md "2026-08-20, third". The list stays
  separate because it also refuses a close of zero or less.] The column is
  BUILT AND EMPTY: it was added to the code on 2026-08-17, the last gap_stats
  rebuild ran on 2026-08-16, and all 10,997 rows in the database hold null. The
  first real values arrive with the Sunday 21:00 universe rebuild, so a Layer 4
  built before then divides by nothing and every move_sigma is null with its
  reason recorded, which is correct behaviour and not a bug to hunt.
- vintage check (e) and _LEG_NEWEST_SESSION_BACK: per row validation of
  notable_movers. leg and as_of_session are REQUIRED fields, and a row
  missing either fails rather than being skipped. The table holds EXACTLY the
  three legs the section emits and nothing else: premarket stamps today, both
  universe legs stamp the prior session. Anything else is not a leg and fails.
- analyst._REQUIRED_TABLES: the vacuum detector requires the day and swing
  watchlist tables BY NAME. A notable movers table contributes claims to
  validate but can never satisfy that requirement.
- conftest.watchlist_headers and watchlist_table: fixtures build their tables
  from REPORT_TEMPLATE.md, so a template header change breaks them loudly.

### Built on 2026-08-20, and this list is what it was

The scan fields and the section assembly in src/morning/scan.py, the section
in doc/REPORT_TEMPLATE.md, one further rule at the end of doc/prompt_analyst.md,
rule 15 as that file stands today, the claims, and
the CHANGELOG and DECISIONS entries.

All of it shipped, plus four things this list did not anticipate because they
were defects rather than work: vintage.enforce was being called on a hand built
dict and so check (e) walked zero rows on every run ever made; evidence_width
had no axis for the section, so a rerun that lost it was thinner on nothing;
fallback_report writes its own headings and would have dropped the section on
any morning the model call failed; and the suite's only notable header was a
seven column hand written literal pinned by nothing, against the nine the
section publishes. [2026-08-22: ten. A price age column was added beside price
time, because the premarket leg computed the age to apply the [price age] floor
and then discarded it, so a row that CLEARED a 900 second ceiling published a
bare timestamp and left the reader to subtract it from a scan clock the report
does not print.]

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
[Collector] max_subscriptions of the universe, 50 including the eight context
tickers, and it reads bars_by_symbol rather than the
candidate list: every subscribed name is eligible, not only the twelve that
survived the screen. Its baseline is c1 from the same file.

No leg carries today's regular session move, because the report is written
before the open.

THERE IS NO THREE SESSION LEG. It was dropped on 2026-08-17 rather than left
defined and never emitted, and DECISIONS.md carries the cost and the
reasoning. Three legs are specified here, three legs are in
_LEG_NEWEST_SESSION_BACK, and three legs are emitted. If a future reader wants
that window back, the decision entry says what it costs and what it buys, and
re-adding a key to the table is one line.

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

  1. move_sigma descending BY SIZE, PRIOR SESSION leg, universe wide.
     [corrected 2026-08-28: was "move_sigma descending", which the code read
     as the signed value, so the list published the five largest RISERS and
     no decliner could reach it however unusual. Point 3 below already said
     "absolute" and point 1 was written without the sign being considered at
     all. On 2026-08-28 this dropped HRL at -8.00 sigma, the second most
     unusual move in the 2,769 name universe, to publish VEEV at +6.04.]
  2. market cap descending among names whose absolute prior session move
     clears min_abs_gap_pct, PRIOR SESSION leg, universe wide.
  3. absolute two session move descending, TWO SESSION leg, universe wide.
  4. move_sigma descending BY SIZE, PREMARKET leg, the collector names only.
     [corrected 2026-08-28: same correction as point 1 and for the same
     reason. This one was the more visible of the two, because the premarket
     leg is small: on 2026-08-28 the list published five names at 0.26 sigma
     and below while MNSO sat on the same leg at -2.51, and across the five
     mornings the list has run it lost the leg's largest move on three.]

List 3 ranks on the raw move rather than on sigma, as the original brief
specified. It is the size list for the multi session window, where list 1 is
the unusualness list for the single session one.

All three of those keys are taken on the SIZE and not on the sign, because
neither size nor unusualness has a direction: a name 8 sigma down is not less
unusual than one 6 sigma up, and a section whose stated purpose is what MOVED
cannot be blind to half the ways a name can move. The row still carries the
signed value, so the direction is on the page and only the ordering is taken
on the size. List 2 is the exception and ranks on the market cap itself, which
has no sign to take; its FLOOR already reads the absolute move.

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

[2026-08-22: EVERY LIST STATES ITS OWN OUTCOME, in one of four fixed states,
with the count it considered beside it. This was 4.9's rule and it had been
applied only to the legs. Lists 1 and 4 have come back empty on every run the
section has ever made, because return_stdev_20d is null across the gap
statistics database until the Sunday rebuild, and the report said only that
they were "short".

  - `ranked`: the list holds at least one name.
  - `uncomputable`: an input nobody has produced. Either the leg's own file was
    lost, or the column the list ranks on is null on every row the leg carries.
  - `nothing to rank`: the input arrived and carried nothing for that leg to
    measure.
  - `below the floor`: the leg measured rows, the ranking key exists, and not
    one row reached this list's own floor. The only one of the three empties
    that means the market was quiet.

Three counts travel with the state, as scan.list_report writes them: considered
is what the leg measured, qualified is what cleared this list's floor and
carried its ranking key, and selected is what it published. The whole sentence
is assembled once in scan._list_report_text and quoted word for word by
REPORT_TEMPLATE.md and by fallback_report, so the two renderers cannot drift.
Held by claim_an_empty_list_says_which_empty_it_is.]

### 4.5 Row fields

ticker, leg, as_of_session, the move on that leg, move_sigma, market cap, the
catalyst headline where one was fetched, and the also on watchlist mark.
price_time where the leg has one, which is the premarket leg alone, and
vintage holds that one to the premarket window as well as to the session.

[2026-08-22: price_age_seconds beside it, on the same rows and null on the same
ones. The [price age] floor is a CEILING of 900 seconds, so a row that survives
it can still be fifteen minutes behind the scan clock, and the scan clock is not
in the report: a reader given the stamp alone could not compute the one number
that says how stale the published price is. The premarket leg already computed
the age to apply the floor and was discarding it. Held by
claim_a_premarket_row_carries_the_age_of_its_price.]

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

doc/prompt_analyst.md gains one more rule after the existing fourteen, which is
rule 15 as the file stands today: the model may DESCRIBE these names, and may
not assign them a conviction, may not move them onto a watchlist, and may not
imply a setup. [corrected 2026-08-20: was "rule 10, after the existing nine".
The file held thirteen rules when this was written on 2026-08-17 and holds
fourteen now; rule 10 has been the display rounding rule since 2026-08-14.
Count the rules in the file rather than trusting a number written here.]

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

[2026-08-22: the same rule now applies one level down, to the four ranked
lists, which had been exempt from it since the section shipped. Each publishes
a state and a considered count, and _leg_report gained input_present so a list
can tell a leg whose file was lost from a leg whose file was read and carried
nothing. See the note at the end of 4.4 for the four states.]

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
  says otherwise. [A real morning did say otherwise. timeout_s is 537 from
  2026-08-20, derived on the same 3x rule against the slowest scheduled morning
  then on record, 178.9 seconds on 2026-08-19, rather than against the slowest
  dry run. The 2026-08-20 morning has since run 226.1 seconds, so the multiple
  is 2.4 and the rule is owed another derivation. This paragraph stands as what was true when it was
  written; the timeout note in CRITERIA.md carries the current derivation.]
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
- CLOSED 2026-09-02, from the other end. pm_rvol's numerator covered 07:20
  onward while its denominator accumulated from 04:00, so the ratio
  understated. Rather than build a second baseline keyed to the collector
  window, the collector was moved to 04:00 so the two windows agree. See
  DECISIONS.md 2026-09-02 ninth. Two consequences are open rather than
  closed: the floors in CRITERIA were fitted on the understated numbers and
  have deliberately NOT been retuned, so rows before and after that date are
  not comparable; and a name subscribed only at the 07:20 handover still has
  the old shape, which window_open_at is what records.
- The gate marker data/UNVERIFIED is still in place and should stay there
  until a morning's gate table has been read with the new price and clock
  columns in it.

## Operating notes

- The machine must be awake at trigger times; Task Scheduler does not wake
  it by default. See tasks/README.md.
- The analyst step spent 0.47 dollars equivalent on 2026-08-14, the first opus
  medium morning, and four scheduled mornings have been measured since: 0.26 on
  08-17, 0.72 on 08-18, 0.92 on 08-19 and 1.05 on 08-20, each recorded as
  total_cost_usd in that day's analyst_usage.json. It tracks output length, so
  it is climbing with the trend item 5b is watching rather than settling into a
  range. The knobs are CRITERIA.md [analyst] model and effort. [2026-09-02: and
  mode. Under slots the same packets cost 0.39 to 0.73 dollars equivalent
  against 0.92 to 1.74 freeform, and the trend this paragraph watched was the
  model reasoning about the whole page, which it no longer writes.]
- Every job appends to a dated log in logs/. The morning chain stops on the
  first failure, so an empty inbox with a log that stops at scan means the
  packet failed, not the mail.
- To take the schedule down: `powershell -ExecutionPolicy Bypass -File
  tasks\register_tasks.ps1 -Unregister`.
