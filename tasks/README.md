# Scheduled jobs

Five Windows Task Scheduler jobs run PremarketDesk. Each .bat here changes to
the project root, runs its scripts with the project venv, and appends stdout
and stderr to `logs\<job>-YYYY-MM-DD.log`, with the date stamped by the
project's own ET clock so a locale change cannot mangle the file name.

| Job | Time (ET, machine local) | Days | What it runs |
| --- | --- | --- | --- |
| job_discover.bat | 07:15 | Mon to Fri | discover.py, then baseline.py to warm the RVOL cache for the new watchlist |
| job_collector.bat | 07:20 | Mon to Fri | collect_premarket.py, runs to the 09:25 stop time |
| job_morning_chain.bat | 08:45 | Mon to Fri | scan.py, analyst.py, render_report.py, deliver.py, build_archive.py, stopping on the first failure |
| job_nightly.bat | 22:15 | Mon to Fri | backfill_premarket.py, fill_outcomes.py, then build_archive.py so a broken morning still gets archived that evening |
| job_universe.bat | 20:00 | Sunday | universe.py weekly rebuild |

## Registering

    powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1

Remove all five again with `-Unregister`. The times come from the clocks in
`doc\CRITERIA.md`. If a clock there changes, change the register script to
match and re-register.

In the Task Scheduler GUI the jobs live in their own folder: Task Scheduler
Library > PremarketDesk. Press F5 if the console was already open when they
were registered, the tree does not refresh itself.

## Things worth knowing

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
- Norton occasionally denies the first write of a file. Every script retries
  or fails loudly into its log; a one line Permission denied in a log that
  ends with rc=0 was a retry that succeeded.
