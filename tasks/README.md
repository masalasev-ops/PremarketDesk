# Scheduled jobs

Ten Windows Task Scheduler tasks run PremarketDesk, from eight .bat files:
job_nightly registers twice and job_monitor registers twice. Up to three further
tasks may be present and are not part of the schedule: see One off probes at
the foot of this file. Each .bat here
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
| job_collector.bat | 07:20 | Mon to Fri | collect_premarket.py, runs to the 09:25 stop time. Since 2026-08-24 it REFUSES a watchlist that was not written today and exits non zero, rather than subscribing to the context tickers alone and looking healthy while it does. It takes one optional argument, `stale-watchlist-ok`, and only monitor_jobs passes it: past the last pass that could rerun discover inside the window, CRITERIA decides possibly wrong names beat no tape, and the flag is how that branch says it knows. See CRITERIA.md [Monitor], the stale watchlist note |
| job_morning_chain.bat | 08:45 | Mon to Fri | scan.py, analyst.py, render_report.py, verify_morning.py, deliver.py, build_archive.py, stopping on the first failure. verify_morning.py is the exception: it prints the gate table for a human and never stops the chain, because the gate is enforced by deliver.py |
| job_nightly.bat | 22:15 | Mon to Fri | TEN steps, in this order, and the list is closed: market_today.py as the trading day guard, market_today.py --refresh to renew the cached exchange calendar so the 08:45 chain never has to fetch it, backup_evidence.py to copy the two artifacts that cannot be rebuilt to somewhere outside the tree, backfill_premarket.py, fill_outcomes.py, true_volume.py to measure what premarket volume actually was from Alpaca's full SIP tape, pool_recall.py to measure what the morning's pool missed against every universe name that actually gapped, prune_data.py which is the only scheduled step in this project that DELETES anything and deletes only what its whitelist names, weekly_page.py, then build_archive.py so a broken morning still gets archived that evening. The refresh never fails the chain: a stale calendar is survivable, a failed refresh leaves yesterday's holiday list in place, and the morning records that it is stale. [corrected 2026-08-22: this listed five of the steps and named neither the backup nor the deletion, which are the two a reader most needs to know are happening] [corrected 2026-08-24: said NINE over a list of ten, which is what the .bat actually invokes; the trading day guard was being counted as free] |
| job_nightly.bat (again, as nightly-catchup) | 07:00 | Mon to Fri | the same .bat called with the argument "catchup", which runs the vendor lag half only: the trading day guard, the calendar refresh, backup_evidence.py, backfill_premarket.py and fill_outcomes.py, then stops. The five it skips are true_volume.py, pool_recall.py, prune_data.py, weekly_page.py and build_archive.py. The vendor usually publishes intraday overnight, so this fills yesterday via the catch-up sweep and finishes the volume verification before the new morning's collection is trusted. pool_recall.py and build_archive.py are skipped, because pool_recall measures the session it is invoked ON: until 2026-08-20 this firing asked for a session that had not opened and wrote gapped 0, addressable 0, recall 0.0 over the real measurement the 22:15 pass had taken |
| job_midday.bat | 12:00 | Mon to Fri | scan_midday.py then render_midday.py. Grades every live picks row against the levels the morning published, and sweeps the whole universe for names that moved today and were never named at 08:45. No model runs: the report is rendered from the packet, because midday asks closed questions. The hour is chosen, not convenient: us-quote-delayed's REGULAR hours behaviour is what was measured and its premarket behaviour is untested. It costs about 2,900 credits a session, almost all of it the per symbol universe sweep, and the preflight refuses rather than truncating because half a universe is not a market wide scan. See CRITERIA.md [Midday] |
| job_universe.bat | 21:00 | Sunday | universe.py weekly rebuild, then gap_stats.py over every name in it. The gap statistics step is the larger of the two, one counted call per universe name, measured at 2,745 calls and 421 seconds on 2026-08-13 when the universe held that many, and it produces the gap propensity discover ranks the pool by. Not 20:00: that was the exact instant of the 00:00 UTC quota reset, so which quota day the largest job in the schedule billed to was a coin toss. Not 20:30 either: the vendor's counter rolled 30 to 32 minutes late on 2026-08-16 |
| job_monitor.bat | 07:25, repeating every 30 min until 09:25, and once at 22:45 | Mon to Fri | monitor_jobs.py, the watchdog: checks that each job fired and finished, reruns what is safe |
| job_meter_sampler.bat | 00:00, repeating every 30 min for 24 hours | Every day, weekends included | meter_sampler.py takes one reading of the shared EODHD quota counter per firing, 48 a day, into `logs\meter-<quota day>.log`. It is an instrument and not a step: it sets no PMD_JOB, writes no job status record, runs no trading day guard, and CRITERIA.md [job status steps] must not gain an entry for it or the watchdog would start reporting it overdue. It exists because the job trail says which step spent what and cannot say when, and nothing else runs between the 22:45 monitor and the 07:00 catch-up |

## Registering

    powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1

Remove them all again with `-Unregister`, which also removes the one off
probe if it is armed. The times come from the clocks in `doc\CRITERIA.md`. If a
clock there changes, change the register script to match and re-register.

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

Three .bat files in this folder are NOT scheduled steps. Each answers a single
open question against a live session and is meant to be deleted once it is
answered. None sets PMD_JOB, none writes a status record, and none
appears in CRITERIA.md [job status steps], because a step that is meant to stop
existing does not belong in a list of steps the watchdog expects. None is in
the $jobs array, so a plain run of register_tasks.ps1 never resurrects one;
each has its own dated flag, and `-Unregister` removes all three.

- `job_probe_socket_cost.bat`, added 2026-08-31 and NOT yet run. It measures
  the one number the websocket still owes: the per MESSAGE cost on a heavy live
  tape. Connecting, subscribing and reconnecting were measured at exactly zero
  on 2026-08-13, twice, across runs with 9 and 12 reconnects, but both rode the
  quiet evening tape. The single window that ever streamed a heavy tape, 1,574
  trade messages, straddled the counter's 00:00 UTC daily reset and its delta
  was therefore unreadable.

  It matters now because CRITERIA [Midday] argues for moving [Collector]
  stop_time past the open. A daily high and a daily low carry no order, so the
  midday pass cannot tell whether a stop that was reached came before or after
  an intraday fill; timestamped minute bars can. Regular hours print far harder
  than premarket, so the cost that has never been measured is exactly the cost
  that extension would incur.

  Arm it for a chosen weekday with:

      powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1 -SocketCost 2026-09-01

  10:00 is past the collector's 09:25 stop, so the account wide 50 symbol cap
  is free and this cannot starve the morning it exists to make possible, and it
  is clear of the 12:00 midday job, whose REST spend would land inside the
  delta. NOTHING ELSE MAY TOUCH THE KEY WHILE IT RUNS: the counter is account
  wide, so a sibling project spending alongside it is indistinguishable from a
  per message charge. The meter sampler firing at 10:00 and 10:30 is the one
  exception and it is safe, because [Quota costs] pins the user endpoint at
  zero and three independent measurements have now closed on that.

  Armed on 2026-08-31 for 2026-09-01 10:00.

- `job_probe_socket_cap.bat`. A/B tests the EODHD trades websocket under a
  small subscription and under one at the documented 50 symbol cap,
  alternating the arms so the rising premarket rate cannot be mistaken for the
  effect. It settles the open question in doc/research/COLLECTOR_VOLUME.md,
  which proves the collector's premarket volume disagrees with EODHD's own 1m
  bars and that the check is sound, without saying why. It must not overlap
  the collector's 07:20 to 09:25 window, and it refuses any run that would.

  Arm it for a chosen morning with:

      powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1 -Probe 2026-08-21

  That registers exactly one task, `\PremarketDesk\probe-socket-cap`, with one
  trigger at 06:30 on the date given, and touches nothing else. 06:30 is
  derived, not chosen: four cycles of two arms at 120s with 90s to settle is
  28 minutes, the probe adds a 60s buffer before checking itself against
  CRITERIA [Collector] start_time, and 06:30 finishes at 06:59 with 21 minutes
  of slack. The task's execution time limit is 45 minutes so that Task
  Scheduler's own kill also lands before 07:20 if the probe hangs rather than
  exits. It wakes the machine, because the 2026-08-19 run was lost to a power
  outage at 06:20.

  A plain run of register_tasks.ps1 never registers it. Everything in the $jobs
  array comes back on every refresh of the schedule, and this task is meant to
  stop existing. `-Unregister` does remove it, because a removal that leaves
  one task behind in a folder people read as empty is worse than none.

  Armed on 2026-08-20 for 2026-08-21 06:30. Before that it had no task at all:
  the re-arm recorded in CHANGELOG.md on 2026-08-19 used `schtasks /Change`
  against a task that had never been created, so it failed silently. A probe
  meant to be deleted still needs a supported way to be created, or it gets
  created wrong, which is why `-Probe` exists rather than another hand
  improvisation.

Read the socket side back from the run's own printed report. The vendor side is
a separate command the NEXT session, because EODHD does not publish a session
until it is over, and it DOES spend one intraday call per watched symbol, eight
at present. From cmd in the project root:

    set PYTHONPATH=%CD%\src
    .venv\Scripts\python.exe -m research.probe_socket_cap --compare socket-cap-probe-2026-08-21.json

Delete the task when the question is answered:

    schtasks /Delete /TN "\PremarketDesk\probe-socket-cap" /F

- `job_probe_capture.bat`. Sweeps the universe from Alpaca over 04:00 to 08:30
  and compares the per symbol volumes against what the collector recorded on
  the same tape over the same minutes. One sweep answers both open questions:
  whether the free tier serves a window during a RUNNING session, and what the
  socket actually captured of the morning the 0.1172 correction in CRITERIA
  [Collector] premarket_capture_rate is being applied to. It spends no EODHD
  quota, writes nothing the chain reads, and about six Alpaca requests against
  a 200 per minute limit.

  Arm it for a chosen morning with:

      powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1 -Capture 2026-08-24

  That registers exactly one task, `\PremarketDesk\probe-capture`, at 08:45 on
  the date given. 08:45 is not chosen either, it is CRITERIA [Scan] run_time:
  the question is what the vendor serves at the clock production asks it, so a
  run at any other time answers a different one. It therefore runs BESIDE the
  morning chain, which is safe because it spends no shared counter and touches
  nothing the chain does. The window's 08:30 end is [Scan] run_time minus
  [Truth] documented_lag_minutes, the latest end the free tier will serve at
  that clock, and one extra request asks for the production window at the
  production clock as the control. The probe waits 30 seconds past 08:45 before
  firing, because that end is fixed while the vendor's refusal rule is relative
  to the wall clock.

  StartWhenAvailable is deliberately NOT set here, where the socket cap probe
  has it. A missed 08:45 catching up at 10:30 would record a 200 that means
  nothing. AllowStartIfOnBatteries and DontStopIfGoingOnBatteries ARE set,
  because the default refuses to start a task on battery power, so a laptop
  unplugged overnight would wake at 08:45, decline, and leave no record at all.
  A market holiday is not caught by the register script: the .bat runs
  ops.market_today and stands down on one.

  It needs the collector to have been running that morning, or half the
  comparison is missing. Read it back with:

      set PYTHONPATH=%CD%\src
      .venv\Scripts\python.exe -m research.probe_capture_live --report --date 2026-08-24

  Delete the task when the question is answered:

      schtasks /Delete /TN "\PremarketDesk\probe-capture" /F

  ANSWERED, and the task is gone. It ran 2026-08-24 08:45 and again 2026-08-26
  08:45, the second armed because the first had a collector that started at
  08:09 rather than 07:20 and so measured half a window. Both sweeps were
  SERVED and both controls were refused 403, which closes the served or
  refused question. The capture half came back 0.1298 median on the clean
  session against 0.1172 assumed, and the 118 fold spread the first sweep
  seemed to show was mostly the late start. See DECISIONS.md 2026-08-26.

  The .bat and research/probe_capture_live.py are KEPT, which is a departure
  from the two probes retired on 2026-08-17. Their questions retired together;
  this one's did not. Served or refused is closed and will not be asked again,
  while the capture share is the input to a number the whole volume floor rests
  on and gets better with sessions. Re-arm with -Capture and a date. What was
  deleted is the scheduled task, because its one time trigger had fired and a
  folder people read as the schedule must not carry entries that never will
  again.

Two further probes lived here and are gone, and only one of them settled
anything. `job_probe_live_v1.bat` went on 2026-08-17, settling that EODHD
`real-time/{symbol}` serves the last completed session rather than today's
premarket. `job_probe_alpaca_live.bat` went the same date and was read as
closing Alpaca as a live discovery source; that closure was WITHDRAWN on
2026-08-22, because every request the probe had ever made was refused before
the feed was consulted, so 46 refusals were evidence about recency and not
about a live session. Alpaca's status as a live discovery source is open and
unmeasured, which is what `job_probe_capture.bat` above is armed to settle.
The modules both wrapped stay under src/research/, which is where the evidence
is read back from. See DECISIONS.md 2026-08-22.
