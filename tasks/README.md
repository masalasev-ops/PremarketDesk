# Scheduled jobs

Nine Windows Task Scheduler tasks run PremarketDesk, from seven .bat files:
job_nightly registers twice and job_monitor registers twice. Each .bat here
changes to the project root, runs its scripts with the project venv, and
appends stdout and stderr to `logs\<job>-YYYY-MM-DD.log`, with the date stamped
by the project's own ET clock so a locale change cannot mangle the file name.
The meter sampler is the one exception: it appends to a single undated
`logs\meter-sampler.log`, and the readings it takes go to the meter trail at
`logs\meter-<quota day>.log`, which is keyed by the vendor's quota day rather
than by the ET date.

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
| job_nightly.bat | 22:15 | Mon to Fri | market_today.py --refresh to renew the cached exchange calendar so the 08:45 chain never has to fetch it, then backfill_premarket.py, fill_outcomes.py, pool_recall.py to measure what the morning's pool missed against every universe name that actually gapped, then build_archive.py so a broken morning still gets archived that evening. The refresh never fails the chain: a stale calendar is survivable, a failed refresh leaves yesterday's holiday list in place, and the morning records that it is stale |
| job_nightly.bat (again, as nightly-catchup) | 07:00 | Mon to Fri | the same .bat called with the argument "catchup", which runs the vendor lag half only: the calendar refresh, backfill_premarket.py and fill_outcomes.py, then stops. The vendor usually publishes intraday overnight, so this fills yesterday via the catch-up sweep and finishes the volume verification before the new morning's collection is trusted. pool_recall.py and build_archive.py are skipped, because pool_recall measures the session it is invoked ON: until 2026-08-20 this firing asked for a session that had not opened and wrote gapped 0, addressable 0, recall 0.0 over the real measurement the 22:15 pass had taken |
| job_universe.bat | 21:00 | Sunday | universe.py weekly rebuild, then gap_stats.py over every name in it. The gap statistics step is the larger of the two, one counted call per universe name, measured at 2,745 calls and 421 seconds on 2026-08-13 when the universe held that many, and it produces the gap propensity discover ranks the pool by. Not 20:00: that was the exact instant of the 00:00 UTC quota reset, so which quota day the largest job in the schedule billed to was a coin toss. Not 20:30 either: the vendor's counter rolled 30 to 32 minutes late on 2026-08-16 |
| job_monitor.bat | 07:25, repeating every 30 min until 09:25, and once at 22:45 | Mon to Fri | monitor_jobs.py, the watchdog: checks that each job fired and finished, reruns what is safe |
| job_meter_sampler.bat | 00:00, repeating every 30 min for 24 hours | Every day, weekends included | meter_sampler.py takes one reading of the shared EODHD quota counter per firing, 48 a day, into `logs\meter-<quota day>.log`. It is an instrument and not a step: it sets no PMD_JOB, writes no job status record, runs no trading day guard, and CRITERIA.md [job status steps] must not gain an entry for it or the watchdog would start reporting it overdue. It exists because the job trail says which step spent what and cannot say when, and nothing else runs between the 22:45 monitor and the 07:00 catch-up |

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
- Every weekday job first runs `python -m ops.market_today`, the trading day
  guard at `src\ops\market_today.py`. On a weekend or an official market
  holiday (from the cached EODHD exchange calendar) it exits 3, and the .bat
  turns that into one line in the log and a clean `exit /b 0` without doing
  anything. So the tasks stay registered plain Mon to Fri and holidays take
  care of themselves. Two jobs skip the guard on purpose. The Sunday universe
  rebuild skips it because the guard counts Sunday as a non trading day, so
  wiring it in would refuse the weekly rebuild every week. The meter sampler
  skips it because the counter it reads is shared with everything else using
  the token and rolls at midnight UTC, so a day this market is closed is
  exactly a day a drain would otherwise go unrecorded.
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
  window is open and no collector is alive, discover is rerun until the
  collector has written its subscription list and never after, and a missed
  Sunday universe build is caught
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

One task in this folder is NOT a scheduled step. It answers a single open
question against a live morning and is meant to be deleted once it is
answered. It does not set PMD_JOB, writes no status record, and does not
appear in CRITERIA.md [job status steps], because a step that is meant to stop
existing does not belong in a list of steps the watchdog expects.

- `job_probe_socket_cap.bat`. A/B tests the EODHD trades websocket under a
  small subscription and under one at the documented 50 symbol cap,
  alternating the arms so the rising premarket rate cannot be mistaken for the
  effect. It settles the open question in doc/research/COLLECTOR_VOLUME.md,
  which proves the collector's premarket volume disagrees with EODHD's own 1m
  bars and that the check is sound, without saying why. It must not overlap
  the collector's 07:20 to 09:25 window, and it refuses any run that would.
  NO TASK IS CURRENTLY REGISTERED FOR IT. The re-arm recorded in CHANGELOG.md
  on 2026-08-19 used `schtasks /Change` against a task that does not exist, so
  it failed and the probe has not run since. Register it by hand for a
  premarket morning when the reading is wanted.

Read it back with `--report`, and delete the task when done:

    schtasks /Delete /TN "\PremarketDesk\probe-socket-cap" /F

Two further probes lived here and are gone, both answered and recorded in
DECISIONS.md: `job_probe_live_v1.bat` on 2026-08-17, settling that EODHD
`real-time/{symbol}` serves the last completed session rather than today's
premarket, and `job_probe_alpaca_live.bat` on the same date, closing Alpaca as
a live discovery source. The modules they wrapped stay under src/research/,
which is where the evidence behind both decisions is read back from.
