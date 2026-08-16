# Scheduled jobs

Eight Windows Task Scheduler tasks run PremarketDesk. Each .bat here changes to
the project root, runs its scripts with the project venv, and appends stdout
and stderr to `logs\<job>-YYYY-MM-DD.log`, with the date stamped by the
project's own ET clock so a locale change cannot mangle the file name.

Each .bat sets `PYTHONPATH` to the project's `src` directory and invokes its
steps as `python -m package.module`. src/ is the import root and every module
lives in a package under it (core, ops, selection, collect, morning, night,
research, tests), so running a file by path would put that package's own
directory on `sys.path` instead of src, and every `from core import config`
would fail. If you add a step, use `-m`, not a path.

Each .bat also sets `PMD_JOB` to its own name. Every step it runs appends one
line to `data\job-status.jsonl` as it exits, and that name is what says which
job the step ran under. Running a script by hand records `manual` instead,
which is worth being able to tell apart: an ad hoc rerun that succeeded is
still a success, but it is not evidence that the schedule fired.

`PMD_JOB` decides one more thing: who owns an artifact under `runs\`. A
scheduled run sets it and may rewrite what it writes, including for past dates,
because backfill's 07:00 catch-up pass legitimately fills yesterday. A hand run
sets nothing, so `pool_recall`, `backfill_premarket` and the collector's
`--snapshot` mode all REFUSE to replace an existing artifact and write beside it
with a `.handrun` name instead, printing what they spared and its size. Pass
`--overwrite` when you mean it. This exists because a hand run of `snapshot_bars`
against a past session destroyed that morning's frozen 08:45 file, and the only
reason it was noticed is that a test happened to read it.

| Job | Time (ET, machine local) | Days | What it runs |
| --- | --- | --- | --- |
| job_discover.bat | 07:15 | Mon to Fri | discover.py builds and ranks the candidate pool, then baseline.py warms the RVOL cache for the subscribed names only, not the whole pool |
| job_collector.bat | 07:20 | Mon to Fri | collect_premarket.py, runs to the 09:25 stop time |
| job_morning_chain.bat | 08:45 | Mon to Fri | scan.py, analyst.py, render_report.py, verify_morning.py, deliver.py, build_archive.py, stopping on the first failure. verify_morning.py is the exception: it prints the gate table for a human and never stops the chain, because the gate is enforced by deliver.py |
| job_nightly.bat | 22:15 | Mon to Fri | backfill_premarket.py, fill_outcomes.py, pool_recall.py to measure what the morning's pool missed against every universe name that actually gapped, then build_archive.py so a broken morning still gets archived that evening |
| job_nightly.bat (again, as nightly-catchup) | 07:00 | Mon to Fri | the same idempotent run before the market day: the vendor usually publishes intraday overnight, so this fills yesterday via the catch-up sweep and finishes the volume verification before the new morning's collection is trusted |
| job_universe.bat | 20:00 | Sunday | universe.py weekly rebuild, then gap_stats.py over every name in it. The gap statistics step is the larger of the two, measured at 2,745 calls and 421 seconds, and it produces the gap propensity discover ranks the pool by |
| job_monitor.bat | 07:25, repeating every 30 min until 09:25, and once at 22:45 | Mon to Fri | monitor_jobs.py, the watchdog: checks that each job fired and finished, reruns what is safe |

## Registering

    powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1

Remove them all again with `-Unregister`. The times come from the clocks in
`doc\CRITERIA.md`. If a clock there changes, change the register script to
match and re-register.

In the Task Scheduler GUI the jobs live in their own folder: Task Scheduler
Library > PremarketDesk. Press F5 if the console was already open when they
were registered, the tree does not refresh itself.

## Things worth knowing

- Two steps have their exit code ignored on purpose, and both still record
  their outcome. `verify_morning.py` prints the gate table for a human and
  must not stop the chain, because the gate is enforced by `deliver.py`.
  `pool_recall.py` is a diagnostic and nothing downstream reads it. An ignored
  exit code is a decision about control flow and never a decision about
  visibility: pool_recall raised NameError on every nightly run for a week and
  nothing said so, which is why `data\job-status.jsonl` exists and why the
  next morning's report names any step overdue against its window in
  `doc\CRITERIA.md [job status steps]`.
- Every weekday job first runs `src\market_today.py`, the trading day guard.
  On a weekend or an official market holiday (from the cached EODHD exchange
  calendar) the job writes one line to its log and exits 0 without doing
  anything. So the tasks stay registered plain Mon to Fri and holidays take
  care of themselves.
- The machine must be awake at trigger time. Task Scheduler does not wake a
  sleeping laptop by default; enable "wake the computer to run this task" in
  the task's properties, or keep the machine plugged in and awake weekday
  mornings.
- The morning chain stops at the first non zero exit, so a failed scan never
  reaches the model and a failed report never reaches email.
- deliver.py sends nothing while `data\UNVERIFIED` exists (the first morning
  verification gate) and skips cleanly while RESEND_API_KEY or EMAIL_TO are
  unset, so registering these tasks before going live is safe.
- The watchdog's rerun policy lives in CRITERIA.md [monitor]. In short: the
  morning chain and the nightly are idempotent and get rerun automatically
  (at most once per day each), a dead collector is restarted only while its
  window is open and no collector is alive, discover is never rerun after
  the collector window opens, and a missed Sunday universe build is caught
  on a later weekday morning rather than the next one: the rerun triggers on
  universe.json's age against CRITERIA [monitor] universe_rerun_after_days,
  so a file written the previous Sunday is not stale enough to trip it until
  that many days have passed. Everything it decides is in
  logs\monitor-YYYY-MM-DD.log, and a nonzero Last Result on the monitor
  task means something needs a human eye.
- Norton occasionally denies the first write of a file. Every script retries
  or fails loudly into its log; a one line Permission denied in a log that
  ends with rc=0 was a retry that succeeded.

## One off probes

Two tasks in this folder are NOT scheduled steps. They answer a single open
question against a live morning and are meant to be deleted once it is
answered. Neither sets PMD_JOB, neither writes a status record, and neither
appears in CRITERIA.md [job status steps], because a step that is meant to stop
existing does not belong in a list of steps the watchdog expects.

- `job_probe_live_v1.bat`, 07:55, one time. Samples EODHD `real-time/{symbol}`
  every three minutes from 08:00 to 09:15 with the collector's own bars beside
  each reading, to settle whether that endpoint ticks during premarket or
  serves the last completed session the way the exchange wide form does.
  Costs about 26 EODHD calls.
- `job_probe_alpaca_live.bat`, 07:25, one time. Sweeps the whole universe from
  Alpaca every five minutes from 07:30 to 09:20 and records how many symbols
  have bars for TODAY and how far behind the wall clock the newest one is.
  doc/ALPACA_PROBE.md measured the same sweep at 4 requests and about a second,
  but on a Saturday against a completed session, so it proved historical access
  and nothing about a live morning. DECISIONS.md 2026-08-16 proposes moving
  discovery off the 50 slot websocket onto this sweep, and that proposal does
  not stand unless it works live. Costs NO EODHD quota at all: prior closes
  come from Alpaca daily bars, so it cannot compete with the 07:15 discover or
  the 08:45 scan for the shared counter.

Read either back with `--report`, and delete the task when done:

    schtasks /Delete /TN "\PremarketDesk\probe-live-v1" /F
    schtasks /Delete /TN "\PremarketDesk\probe-alpaca-live" /F
