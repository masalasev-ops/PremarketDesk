# PremarketDesk build plan and session handoff

Last updated: 2026-08-13, mid afternoon ET. This file is the single document a
new session needs to continue the build. Read it top to bottom before touching
anything. The original checkpoint brief is restated per checkpoint below, with
status, evidence, and what remains.

## What this project is

A single-brain premarket report generator. Python on Windows. EODHD All-In-One
is the only market data provider. The narrative pass runs through the owner's
existing Claude subscription via the claude CLI. No second model, no rival
brain, no merge step, no yfinance, no Anthropic API key anywhere.

## Hard rules, none negotiable

1. EODHD is the only data source. No yfinance, no second vendor.
2. The narrative pass is `claude -p --model sonnet --output-format json` as a
   subprocess. Never the Anthropic Python SDK. Never read or set
   ANTHROPIC_API_KEY. config.py actively refuses that variable and strips it
   from .env if it ever appears.
3. Every screen threshold lives in CRITERIA.md and nowhere else. No threshold
   literal in Python. criteria.py is the strict reader and raises on any
   missing key.
4. No em dashes in code, comments, strings, or docs. Use commas, colons, or
   the word "to". This applies to this file too.
5. Work checkpoints in order, do not start one until the previous meets its
   done condition, commit at each checkpoint.
6. Premarket high, low, VWAP come from the collector file only, never inferred
   from a quote snapshot. Missing evidence is null with a recorded reason,
   never silently substituted.
7. The model narrates. Membership, eligibility, scores, and conviction are
   computed deterministically in Python before the model ever runs.

## Environment facts a new session must know

- Working directory: `e:\Stock Analysis  Tool Ideas\PremarketDesk` (two spaces
  between "Analysis" and "Tool", quote all paths).
- Python 3.14.7 at C:\Python314. Venv at `.venv`, deps: requests,
  websocket-client, markdown. Run everything with
  `.venv\Scripts\python.exe`.
- tzdata is absent, so zoneinfo cannot resolve America/New_York. ettime.py
  provides the one ET clock: zoneinfo if available, else a fixed post 2007 DST
  rule. Self test covers both 2026 transitions. Always use ettime, never naive
  datetimes.
- Norton Web/Mail Shield re-signs all HTTPS with a root whose basicConstraints
  is not marked critical. Python 3.14 enables VERIFY_X509_STRICT by default
  and rejects exactly that. Fix lives in config.tls_context() and
  config.ca_bundle(): load the Norton root from
  C:\ProgramData\Norton\Antivirus\wscert.pem, clear only the STRICT flag.
  Never verify=False. eodhd.build_session() and the websocket sslopt both use
  it.
- Norton also intermittently blocks git loose object writes with Permission
  denied. Every retry makes progress. The committed pattern: loop `git add -A`
  then `git commit` until both exit 0. A helper exists at the scratchpad as
  gitci.ps1 but any retry loop works. Do not conclude the repo is broken.
- git config: user Udayan, 272309566+masalasev-ops@users.noreply.github.com, core.autocrlf false, branch
  main. Commits so far: checkpoints 1 through 7 (6 commits, CP6 and CP7
  share one).
- PowerShell 5.1: no `&&`, use `if ($?) { }` or separate statements.
- .env holds the real EODHD token (working, verified, 100k daily request
  limit, ~45k used on 2026-08-13 by testing). RESEND_API_KEY and EMAIL_TO are
  empty, delivery must skip cleanly.
- `.claude/settings.local.json` grants broad tool permissions for this
  project. The user said to run without asking until complete or blocked.

## EODHD facts learned by probing, trust these over the docs

- Endpoints wrapped in eodhd.py and verified live: us-quote-delayed (fields
  ethVolume, ethTime ms epoch, marketCap, sharesFloat, averageVolume,
  twoHundredDayAveragePrice, previousClosePrice, name, sector, open, high,
  low, volume, lastTradePrice), real-time with ex=US (bulk live, ~18.3k rows),
  eod-bulk-last-day/US (~50k rows per session, no market cap even with
  filter=extended), eod/{symbol}, intraday/{symbol} interval=1m (04:00 to
  19:59 ET coverage, timestamps UTC epoch seconds, published a few hours
  behind live), exchange-symbol-list/{NYSE|NASDAQ} (Type field: keep only
  "Common Stock"), news (s= symbol tag filter, fields date, title, content,
  link, symbols, tags, sentiment; no publisher field, we derive it from the
  url host and label it derived), economic-events (no importance field at
  all, so CRITERIA.md owns a high importance type list), calendar/earnings
  (envelope with earnings array, fields code, report_date, date,
  before_after_market, estimate, actual), user (plan status), search.
- Symbol formats disagree: bulk live returns `A.US`, bulk EOD returns bare
  `VASO`, the websocket wants bare `AAPL`, everything else wants `AAPL.US`.
  universe.py normalizes with _norm_code, collector has _bare/_full.
- Bulk live carries ghost rows: some tickers appear twice, one current row and
  one frozen months or years old snapshot with a stale previousClose that
  fabricates enormous gaps (AZN showed +103 percent from a ghost, ADT ghost
  was from 2023). discover.normalize_bulk_live dedupes by newest timestamp and
  drops rows older than max_quote_age_hours (96). Both counts printed and
  written to watchlist.json. Never consume bulk live raw.
- Websocket wss://ws.eodhistoricaldata.com/ws/us (trades): you MUST wait for
  the {"status_code":200,"message":"Authorized"} frame before sending the
  subscribe frame. Subscribing early gets {"status":500} and a silent dead
  socket. ws.eodhd.com has a bad TLS cert, keep eodhistoricaldata.com. Trade
  message: s (bare symbol), p, v, t (ms), dp (dark pool), ms, c (conditions).
  Cap is 50 concurrent symbols.
- Trades arrive out of timestamp order. Closing a minute at the clock edge
  lost 12 percent of volume. Bars settle late_trade_grace_s (45s) before being
  written. After the fix a 40 minute run lost zero late trades.
- Live v1 (real-time/{sym} with s= for extras) cumulative volume is NOT a
  sound short window reference: measured disagreement with the trade stream in
  both directions up to +1113 percent on DIA. Its timestamp is last trade
  time, feed runs ~15.7 min behind. Use it only as the --poll degraded
  fallback and the directional --verify. The definitive check is
  `collect_premarket.py --verify-intraday` against EODHD 1m bars for
  identical minutes, run it in the evening.
- Macro snapshot: VIX.INDX and GSPC.INDX quote live. US10Y.GBOND, US3M.GBOND,
  DXY.INDX return NA on live but are current on the eod endpoint, so the scan
  tries live then falls back to eod and records the source. No commodity
  symbols on this plan (CL.COMM etc all 404), USO.US stands in for WTI and is
  labelled a proxy in CRITERIA.md and the packet.
- Demo token serves only sample symbols; the real token in .env works for
  everything above.

## Checkpoint status

### CP1 project setup: DONE, committed
.venv, three deps, .env plus .env.example, hand rolled KEY=VALUE parser in
config.py, process env wins over file, ANTHROPIC_API_KEY refused. Evidence:
`python config.py` prints OK with token loaded.

### CP2 criteria in a file: DONE, committed
CRITERIA.md holds day setup (gap>3, price>3, mcap>1B, pmRVOL>1.5, above prior
high), swing setup (gap>=8, price>3, open>prior high, open>200SMA, mcap>=800M,
catalyst required), universe, discovery, collector, baseline, scan, api knobs,
snapshot symbol map, economic importance list, catalyst tag map, score bands,
buckets. Header states seed values are from a third party article, unvalidated,
not an edge. criteria.py is the strict typed reader (rules, bands, pair maps,
clocks; indented lines are markdown code blocks and are skipped). Evidence:
`python criteria.py` prints every section.

### CP3 EODHD client: DONE, committed
eodhd.py, one _request chokepoint, retries 429 and 5xx with backoff honoring
Retry-After, never raises to callers, returns ApiResult (data, error), per run
CallLedger prints via atexit. Smoke test: us-quote-delayed AAPL.US returned
ethVolume and ethTime in one call.

### CP4 weekly universe: DONE, committed
universe.py: NYSE+NASDAQ symbol lists, Type == Common Stock only, session
dates from SPY eod history (no holiday table), 20 bulk EOD calls for history,
market cap attached last from us-quote-delayed only for names that cleared
price/liquidity/history. Wrote data/universe.json with 2745 names (range 1000
to 3000 enforced with a warning), ~170 calls, 86s. require_fresh_universe() is
the single staleness gate (max_age_days=10), verified: 9 days accepted, 11
days refused with a full explanation. All later scripts call it.

### CP5 morning discovery: DONE, committed
discover.py: one bulk live call, normalize_bulk_live (ghost row defense), gap
vs previousClose, CRITERIA floors, top 30 by absolute gap to
data/watchlist.json with feed freshness stats and universe_started_with.
Evidence: single call produced 30 names from 2745, zero rows timestamped
before today after the fix.

### CP6 collector: DONE and committed, one evening task still owed
collect_premarket.py: trades websocket, wait for Authorized then subscribe,
one minute bars settled 45s then appended once to
data/premarket/YYYY-MM-DD.jsonl, restart safe by reading back written keys
(verified 1712 rows, 1712 unique keys after overlapping runs), reconnect with
exponential backoff and full resubscribe, 50 symbol cap with context set SPY
QQQ IWM DIA TLT USO UUP VIXY never dropped and dropped names logged, --poll
Live v1 fallback stamped src=poll, zero REST calls in websocket mode
(verified). --verify is the directional Live v1 bracket. --verify-intraday is
the definitive identical minute comparison, written and untested against a
published day.
STILL OWED: in the evening (intraday publishes a few hours behind), run
`collect_premarket.py --verify-intraday 2026-08-13` and record the within one
percent result. If it fails, investigate before trusting collector volume.

### CP7 baseline: DONE, committed
baseline.py plus store.py (SQLite at data/premarketdesk.db, WAL, upserts on
natural keys). baseline(ticker, cutoff_hhmm, median_volume, sessions_used,
computed_at), 04:00 to cutoff sum over 20 sessions from one intraday call,
median stored, 7 day refresh, min 10 sessions to be usable for RVOL. Evidence:
first AAPL.US 08:45 call cost 1 API call, immediate second cost 0, cutoff
matters (07:30 median 295,808 vs 08:45 median 557,217).

### CP8 scan gathers: CODE WRITTEN, NOT YET RUN
scan.py exists and imports cleanly but has never produced a packet. It was
about to be tested when the session paused. Order inside build_packet():
1. market_snapshot: labels from CRITERIA [scan_snapshot], live first, eod
   fallback, source recorded, WTI proxy note attached.
2. final_candidates: fresh bulk live call through normalize_bulk_live, does
   not trust watchlist.json for membership, top 12 by absolute gap, provenance
   with universe_started_with recorded.
3. attach_quotes (ethVolume, ethTime, marketCap, sharesFloat, averageVolume,
   200 day average, previousClosePrice), attach_daily_history (prior day high
   and 20 day average volume from eod, today's row excluded).
4. attach_premarket_path: pm_high/low/vwap from collect_premarket.read_bars()
   only. Candidates absent from watchlist.json get nulls,
   collector_covered=false, and a pm_reason. Window provenance:
   pm_window_start, pm_window_end, bars_collected, pm_window_starts_late.
5. attach_premarket_rvol: ethVolume divided by cached baseline median for the
   run clock cutoff. Null with recorded reason when collector file missing,
   baseline under 10 sessions, or no ethVolume. Never full day RVOL.
6. attach_catalysts: news filtered by symbol tag only, last 24h, top 3 with
   title, publisher (derived from url host, labelled), url, published time,
   sentiment, tags. Empty means catalyst_found false. News call error means
   catalyst_found null (unknown), not false.
7. economic_events: US, today and tomorrow, matched against the CRITERIA high
   importance list because the feed has no importance field.
8. earnings: candidates window, plus notable tomorrow defined as universe
   members ranked by market cap.
Everything failing lands in gaps_to_fill, no network error crashes the run.
TO VERIFY CP8: run `python scan.py` and confirm runs/YYYY-MM-DD/packet.json
exists with gaps_to_fill naming every failure. Note: at the time of pause,
baseline warming for the current watchlist had NOT run yet (the command
`python baseline.py --cutoff 08:45` was interrupted). Expect pm_rvol nulls
with "no cached baseline" reasons unless you warm first. Also note packet
written at an off schedule hour will have collector bars from ad hoc test runs
(the 2026-08-13 jsonl holds midday test bars, which is fine for testing but
label it: it is not a real premarket window).

### CP9 deterministic flags and score: CODE WRITTEN inside scan.py, NOT YET VERIFIED
classify_catalyst (earnings calendar first, then news tag map from CRITERIA,
never headline regex), evaluate_eligibility (day_eligible, swing_eligible with
named failed conditions, missing data never passes), score_candidate
(catalyst class 3/2/1/0, rvol band, gap band, above prior high, above pm vwap,
mcap>=2B, per component breakdown stored, bucket green/yellow/red). scan.py
--rescore PACKET recomputes from an existing packet for the determinism test.
TO VERIFY CP9: run `python scan.py --rescore runs/<date>/packet.json` twice,
byte compare outputs (fc or diff), must be identical.

### CP10 analyst via claude CLI: NOT STARTED
Write REPORT_TEMPLATE.md with sections, exactly: title and dated subtitle, one
line disclaimer, summary, premarket gappers with full catalyst headlines, day
watchlist table, swing watchlist table, market trends, technical signals,
economic data and rates, coming up, skips and traps. No other sections.
Write prompt_analyst.md stating: use only packet.json; never invent a
catalyst, number, or headline; watchlist membership comes from the precomputed
booleans, may not add or remove; conviction comes from the precomputed bucket,
may not change; the job is narrative around decided numbers; catalyst_found
false is a skip; up on bad news is a trap; pm_rvol null must be said in the
disclaimer line; collector_covered false or window starting later than 07:20
must be said in the disclaimer line and no breakout trigger from a partial
premarket high without labelling it partial.
Build analyst.py invoking `claude -p --model sonnet --output-format json`
as a subprocess (config.py paths exist: REPORT_TEMPLATE_PATH,
ANALYST_PROMPT_PATH). Pipe prompt, template, and packet content via stdin,
write report.md into the same runs/YYYY-MM-DD directory, parse the CLI JSON
output and log token counts (the JSON carries usage fields). Do not use the
SDK, do not touch ANTHROPIC_API_KEY (the claude CLI is on PATH as
claude.ps1, invoke via ["powershell","-Command"] or resolve the .cmd shim;
test what subprocess needs on this machine).
Done when: report.md produced from packet.json alone, every ticker in it
appears in packet.json (write a checker), token usage logged.

### CP11 render and deliver: NOT STARTED
render_report.py: report.md to runs/YYYY-MM-DD/report.html via the markdown
library with tables, fenced_code, sane_lists.
deliver.py: POST to https://api.resend.com/emails (config.RESEND_SEND_URL
already defined) with the HTML as inline body to EMAIL_TO. When
RESEND_API_KEY or EMAIL_TO is absent print a skip message and exit 0, no
exception. Reuse eodhd-style TLS handling (requests session via
eodhd.build_session or config.tls_context) because Norton intercepts this
host too.
Done when: the email step skips cleanly with keys unset.

### CP12 picks table: NOT STARTED
Each run already writes runs/YYYY-MM-DD/packet.json (scan.py does this).
Add picks table to store.py schema: picks(date, ticker, day_eligible,
swing_eligible, score, conviction, gap_pct, pm_rvol, pm_high, pm_low,
pm_vwap, collector_covered, pm_window_start, prior_high, catalyst_class,
entry_ref, stop_ref) with PRIMARY KEY (date, ticker) and upsert so re-running
a day updates rather than duplicates. entry_ref and stop_ref: use pm_high as
the entry reference and pm_low (or pm_vwap, decide and document in
CRITERIA.md) as the stop reference; they are references, not advice. Insert
from scan.py after stamping, or a small picks.py called in the 08:45 chain.
Done when: re-running a day updates rows, verified by running twice and
counting.

### CP13 nightly backfill: NOT STARTED
backfill_premarket.py, run after 22:00 ET: for today's picks pull intraday 1m
04:00 to 09:30 ET, write pm_high_true, pm_low_true, pm_vwap_true into picks
next to the morning live values (ensure_columns in store.py exists for
widening). Any row where pm_high_true is LOWER than live pm_high is a source
disagreement: flag it (add a flag column), never silently overwrite, since the
true window is a superset. Report median and worst case gap between
pm_high_true and live pm_high across the last 20 sessions. Idempotent. Also
call collect_premarket.verify_against_intraday(day) here and store or log the
volume agreement for the record.

### CP14 outcome fill: NOT STARTED
fill_outcomes.py: for picks older than 1 and 5 trading days (trading days
from eod bars of SPY or the ticker itself, not weekday math), fill
next_day_open, next_day_high, next_day_close, day5_close, whether pm_high
broke intraday next day (use intraday or next day high vs pm_high), max
favourable and adverse excursion vs stop_ref. Idempotent, second run changes
no rows (verify with two runs and a row hash).

### CP15 windows scheduling: NOT STARTED
.bat files in the project (a bin/ or tasks/ folder), each: activate .venv,
run the script, append stdout and stderr to logs/<job>-YYYY-MM-DD.log (date
via %DATE% carefully or in Python). Jobs: 07:15 discover, 07:20 collector
(runs to 09:25), 08:45 scan then analyst then render then deliver (one chain
bat, stop on first failure), 22:15 backfill then outcomes, Sunday 20:00
universe. Register with schtasks /Create commands documented in the bat
folder README (or a register_tasks.ps1). Done when the 08:45 chain runs end
to end from the bat and every job writes a dated log.

### CP16 verification gate: NOT STARTED
On the first live morning: print a table for three candidates showing
ethVolume, baseline median, computed pm_rvol, collector premarket high,
bars_collected, then STOP without emailing. Suggested: a --gate flag on
scan.py or a verify_morning.py that the chain bat checks; simplest is a
marker file data/UNVERIFIED that deliver.py refuses to send past while it
exists, plus the printed table. Done when the table prints and nothing is
emailed. The user removes the marker to go live.

## Remaining work in order

1. Warm the baseline cache: `.venv\Scripts\python.exe baseline.py --cutoff
   08:45` (one intraday call per watchlist name, ~40 calls). This was the
   exact command interrupted at pause time.
2. Run scan.py, inspect packet.json and gaps_to_fill. Fix what surfaces.
3. CP9 determinism: rescore twice, byte compare. Commit CP8+CP9.
4. CP10 analyst (template, prompt, subprocess, ticker containment check,
   token log). Commit.
5. CP11 render and deliver with clean skip. Commit.
6. CP12 picks upsert, run scan twice, prove update not duplicate. Commit.
7. CP13 backfill including verify_against_intraday for the record. Commit.
8. CP14 outcomes, idempotent. Commit.
9. CP15 bat files and register script, run the 08:45 chain end to end once
   manually via the bat. Commit.
10. CP16 gate. Commit.
11. Evening of a collected day: `collect_premarket.py --verify-intraday`
    and record the result (owed for CP6, today's file holds midday test bars
    which are still comparable minutes).
12. First real morning: the whole chain fires from Task Scheduler, gate table
    prints, nothing emails until the numbers look sane.

## Testing notes for the morning chain out of hours

Running scan.py at 15:00 produces a real packet but its "premarket" numbers
describe midday test bars, and gaps_to_fill will say the collector window is
odd. That is expected and useful for plumbing tests. The first honest packet
needs a real 07:15/07:20/08:45 morning. Do not tune thresholds off an out of
hours packet.

## File inventory at pause time

- config.py: env, paths, TLS trust (Norton), run_dir
- ettime.py: ET clock, DST fallback, epoch helpers
- criteria.py: CRITERIA.md reader (rules, bands, pair maps, clocks)
- CRITERIA.md: all thresholds plus the ghost row, handshake, late trade,
  verification, snapshot proxy, economic importance notes
- eodhd.py: client, ledger, endpoints, build_session
- universe.py: weekly universe, staleness gate
- discover.py: watchlist, normalize_bulk_live ghost defense
- collect_premarket.py: websocket collector, poll fallback, verify modes
- store.py: SQLite, upsert, ensure_columns
- baseline.py: premarket volume baseline cache
- scan.py: packet gatherer plus deterministic flags and score (untested)
- data/: universe.json (2745 names), watchlist.json (30 names),
  premarket/2026-08-13.jsonl (midday test bars), premarketdesk.db (baseline
  rows for AAPL.US), ca-bundle.pem (generated)
- logs/collector-verify.log: the Live v1 comparison evidence
- Not yet existing: REPORT_TEMPLATE.md, prompt_analyst.md, analyst.py,
  render_report.py, deliver.py, backfill_premarket.py, fill_outcomes.py,
  picks table, bat files
