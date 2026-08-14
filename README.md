# PremarketDesk

A single machine, single user premarket desk for US equities. Every weekday
morning it builds a watchlist, listens to the live premarket tape, scores the
candidates, has a language model write the narrative, and delivers one HTML
report before the open. Every evening it goes back and checks itself against
the vendor's published record.

The design has one brain and one voice: **Python decides, the model narrates.**
Membership, scores, and conviction come from code reading explicit thresholds.
The model only turns an already finished evidence packet into readable prose,
and a checker verifies the prose invented nothing.

## The hard rules

These are load bearing. The code enforces them; changing them means changing
the design, not a config value.

1. **One data source.** Every market number comes from EODHD All-In-One
   (REST and the US trades websocket). Nothing is fetched from anywhere else.
2. **Every threshold lives in `doc/CRITERIA.md`.** The strict reader in
   `src/core/criteria.py` raises on a missing key, and no decision literal is
   allowed in Python. To retune the system you edit a markdown file.
3. **The narrative pass uses the claude CLI as a subprocess**, authenticated
   by a logged in Claude subscription. There is no Anthropic SDK anywhere,
   and `src/core/config.py` actively refuses to read or pass `ANTHROPIC_API_KEY`.
4. **Missing evidence stays missing.** A field the pipeline could not get is
   null with a recorded reason. It is never filled from another day, another
   source, or a guess.
5. **Premarket high, low, and VWAP come from the project's own collector.**
   The vendor's published intraday bars are used at night to audit the
   collector, written into separate `_true` columns, never over the morning
   values. Their disagreement is itself a recorded measurement.

## A day in the life

All times are US Eastern, which the machine is expected to keep locally.

| Time | Job | What it does |
| --- | --- | --- |
| Sun 20:00 | universe | Weekly rebuild of the discovery universe, then the gap propensity sweep over every name in it, measured at 2,745 calls and 421 seconds. That propensity is what discovery ranks the pool by inside each tier |
| 07:00 | nightly-catchup | The nightly again: the vendor usually publishes yesterday's intraday overnight, so this fills anything the 22:15 run could not |
| 07:15 | discover | Builds today's candidate pool from four priors, ranks it, subscribes the collector to the top of it, warms the volume baseline |
| 07:20 to 09:25 | collector | Websocket trades to one minute bars on disk, one file per day |
| 07:25, every 30 min | monitor | The watchdog: checks each job fired and finished, reruns what is safe |
| 08:45 | morning chain | scan, analyst, render, deliver, archive, stopping at the first failure |
| 22:15 | nightly | Backfills the true premarket window, fills trade outcomes, measures what the morning's pool missed into `runs/YYYY-MM-DD/pool_recall.json`, rebuilds the archive |
| 22:45 | monitor-night | The watchdog once more, over the nightly |

```mermaid
flowchart LR
    U[universe.py<br>weekly] --> G[gap_stats.py<br>gap propensity]
    G --> D[discover.py<br>ranked candidate pool]
    U --> D
    D --> C[collect_premarket.py<br>live 1m bars]
    C --> S[scan.py<br>prices from the collector]
    S --> X{vintage.py<br>is this today?}
    X -->|no| STOP[run refused,<br>gate re-armed]
    X -->|yes| A[analyst.py<br>claude CLI, one completion]
    A --> R[render_report.py<br>HTML report]
    R --> V[deliver.py<br>email, gated]
    R --> W[build_archive.py<br>single file archive]
    S -. picks .-> B[(SQLite)]
    N[backfill_premarket.py<br>+ fill_outcomes.py<br>nightly truth] --> B
    P[pool_recall.py<br>what the pool missed] -. reads .-> B
    J[(job-status.jsonl)]
    S -. records .-> J
    C -. records .-> J
    P -. records .-> J
    J -. overdue steps .-> A
```

Every step in that diagram, and every other step a `.bat` runs, appends its
outcome to `data/job-status.jsonl` as it exits. The analyst reads it back and
names anything overdue in the morning report, which is the one channel a human
reads every day. It exists because `pool_recall.py` raised NameError on every
nightly run for a week: its exit code is ignored by design so a diagnostic
cannot break the chain, and nothing recorded that it had failed.

Every weekday job first runs `src/ops/market_today.py`, a trading day guard built
on the cached EODHD exchange calendar. It exits 3 on a weekend or an official
holiday and the calling `.bat` logs one line and stops cleanly, so the tasks
stay registered plain Monday to Friday and holidays take care of themselves.
The Sunday universe job is the one exception and runs no guard: that guard
counts Sunday as a non trading day, so wiring it in would skip the weekly
rebuild every week, and the rebuild is what keeps the following week alive.

## What you need

- **Windows 10 or 11.** Scheduling is Windows Task Scheduler plus the `.bat`
  files in `tasks/`. The pipeline itself is portable Python, but the provided
  automation is Windows.
- **Python 3.11 or newer** (developed on 3.13). Dependencies are deliberately
  tiny: `requests`, `websocket-client`, `markdown`.
- **An EODHD All-In-One subscription** and its API token. Lower EODHD tiers
  do not include the trades websocket that the collector needs.
- **The claude CLI, signed in to a Claude subscription** (Pro or Max). Install
  with `npm install -g @anthropic-ai/claude-code`, run `claude` once to log
  in. The analyst step shells out to it for exactly one completion per
  market day. No API key is used or wanted.
- **Optional: a Resend account** if you want the report emailed. Without it,
  delivery skips cleanly and the report still lands on disk.
- The machine must be **awake and on US Eastern time** during the premarket
  window. Task Scheduler triggers are machine local time; if your machine
  keeps another zone, re-derive the times in `tasks/register_tasks.ps1` from
  the clocks in `doc/CRITERIA.md` before registering. The Python code itself
  computes Eastern time internally (`src/core/ettime.py`) regardless of the
  machine zone.

## Setup

1. **Clone and create the venv at the project root.** The `.bat` jobs
   hardcode `.venv\Scripts\python.exe`, so the name and place matter:

   ```
   git clone https://github.com/masalasev-ops/PremarketDesk.git
   cd PremarketDesk
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

2. **Configure.** Copy `.env.example` to `.env` and fill in
   `EODHD_API_TOKEN`. Leave the Resend keys blank for now; you want the
   verification gate (below) to pass before any email goes out.

3. **Self check.** This creates the working directories and prints the project
   root, whether `ANTHROPIC_API_KEY` is set anywhere (it must not be), the
   masked EODHD token, whether the Resend keys are set, and the dependency
   versions:

   ```
   set PYTHONPATH=%CD%\src
   .venv\Scripts\python.exe -m core.config
   ```

4. **Arm the delivery gate.** This creates `data\UNVERIFIED`, and
   `deliver.py` refuses to email while that file exists:

   ```
   .venv\Scripts\python.exe -m morning.verify_morning --arm
   ```

5. **Build the first universe.** Normally the Sunday job's work:

   ```
   .venv\Scripts\python.exe -m selection.universe
   ```

6. **Register the scheduled jobs:**

   ```
   powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1
   ```

   They appear in the Task Scheduler GUI under Task Scheduler Library >
   PremarketDesk. `-Unregister` removes them all. Do not register these by
   hand with `schtasks /Create`; its string quoting silently stores a spaced
   path unquoted and the task dies at fire time with 0x80070002. The script
   uses the PowerShell ScheduledTasks module, which stores the path
   structurally. Details and caveats are in `tasks/README.md`.

7. **Let a real morning run**, then read the gate table that
   `src/morning/verify_morning.py` prints into `logs\morning-chain-YYYY-MM-DD.log`.
   For the first three candidates it lays the evidence out on one line: the
   price and the minute it printed, the collector's premarket volume, the
   cached baseline median, the RVOL those two produce, and the bar count
   behind it, plus any candidate dropped for having no collector coverage.
   A price with no clock beside it cannot be checked by eye, which is the
   lesson of the first live morning. You can also run any step by hand in
   pipeline order; every script is idempotent and safe to rerun.

8. **Go live.** When a morning looks right: delete `data\UNVERIFIED`, put
   `RESEND_API_KEY` and `EMAIL_TO` into `.env`. The next morning's report
   arrives by email. Everything before this point is guaranteed to send
   nothing.

## Where things land

Everything generated at runtime is git ignored and created on demand:

| Path | What |
| --- | --- |
| `data/premarketdesk.db` | SQLite (WAL): the picks table, one row per (date, ticker), carrying the pool source and tier that put each name in front of the collector; the premarket volume baseline; and gap_stats, one row per (ticker, as_of) |
| `data/premarket/` | The collector's one minute bar files, its per run stats, and the subscription list it wrote at subscribe time so the 08:45 packet can tell a silent symbol from one that was never subscribed |
| `data/job-status.jsonl` | One line per scheduled step per run: job, step, start and end in ET, status, exception type, and one count of what it produced. Written in a `finally` block, so a step killed mid run records dying. The next morning's report names any step that has not succeeded inside its window |
| `data/universe.json`, `data/watchlist.json` | The weekly universe, and the day's whole ranked candidate pool rather than only the names being listened to. Up to `max_subscribed_candidates` rows are marked `subscribed`, and that is not simply the top 42: each populated tier takes `min_slots_per_tier` first. Everything below the cut stays in the file marked `not_subscribed`, so the cut is auditable |
| `runs/YYYY-MM-DD/` | The day's evidence packet, model transcript, rendered report, verification results |
| `logs/` | One log per job per day, every step ending in a `rc=N` marker line |
| `site/PremarketDesk.html` | The whole report history as one self contained file, newest sessions embedded, older ones linked. Opens from disk, no server, no network |

## Configuration reference

`doc/CRITERIA.md` is the single place every tunable number lives: scoring
weights, gap and RVOL thresholds, session clocks, the analyst model and its
measured timeout, watchdog rerun policy, archive depth. Each value carries
its reasoning in prose next to it. Edit it and the next run picks it up; get
a key wrong and the strict reader fails loudly rather than defaulting.

Other documents:

- `doc/CHANGELOG.md` records what changed and when, newest first, and
  `doc/DECISIONS.md` records why the choices that could have gone another
  way went the way they did. Both start at 2026-08-14.
- `doc/BUILD_PLAN.md` records how the system was built and verified,
  checkpoint by checkpoint, including the environment traps that were
  actually hit. Paths in it refer to the original build machine.
- `doc/ArchitecturePremarketdesk.html` and `doc/Premarketdesk_ADayRunArc.html`
  are the architecture pages; open them in a browser.
- `doc/REPORT_TEMPLATE.md` and `doc/prompt_analyst.md` are the report shape
  and the narrative instructions piped to the CLI.
- `doc/sample_report.html` is what a finished morning report looks like.

## What it costs to run

- **EODHD:** the websocket collector was measured at zero against the
  vendor's own API counter (connections, subscribes, and reconnects
  included; `src/research/measure_socket_cost.py` reproduces the measurement). REST
  usage is a few hundred counted calls a day. Discovery spends two bulk end
  of day calls at a measured 98 counted calls each, plus one earnings
  calendar call and up to five news calls; the baseline warm spends one
  intraday call per stale name; the 08:45 scan spends a few dozen across
  quotes, history and news; the nightly spends one intraday call per pick
  plus one bulk end of day for the pool recall measurement. The weekly job
  is the largest single spend: the universe rebuild plus one call per name
  for gap propensity, measured at 2,745. Every job preflights the shared
  counter first, which is account wide across everything using your token
  and resets at midnight UTC.
- **Claude:** one non agentic completion per market day (plus at most one
  retry), on the subscription. Measured 86.5 to 97.7 seconds per report over five
  opus runs at medium reasoning effort on 2026-08-14, which is where the 293
  second timeout in `doc/CRITERIA.md` comes from, three times the slowest. If the CLI fails or times out, the morning still ships:
  `analyst.py` falls back to a plain table report built from the packet and
  says so in the report itself.

## When things go wrong

- **The watchdog usually acts first.** `src/ops/monitor_jobs.py` reruns anything
  idempotent at most once per day, restarts a dead collector only while the
  premarket window is open and no collector is alive, and never reruns
  discovery after the collector starts. Its reasoning is in
  `logs\monitor-YYYY-MM-DD.log`.
- **Antivirus TLS interception** (Norton and similar re-sign HTTPS with
  their own root): `src/core/config.py` detects the local root and widens the
  trust store instead of turning verification off. The same suites
  occasionally deny a first file write; scripts retry, and a one line
  permission error in a log that still ends `rc=0` was a survived retry.
- **The vendor publishes intraday late.** EODHD's one minute bars for a day
  often appear only overnight, so the 22:15 backfill may find nothing. That
  is what the 07:00 catch-up run is for, and unfilled days are swept up for
  several sessions after. A day is only ever filled with its own data.
- **A failed morning is visible, not silent.** The chain stops at the first
  nonzero exit, the report falls back rather than fabricates, and the
  evening archive rebuild still captures whatever the day produced.

## Disclaimer

This is personal research tooling that summarizes market data. It is not
investment advice, and nothing it prints is a recommendation to trade.
