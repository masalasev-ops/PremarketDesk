@echo off
rem PremarketDesk quota meter sampler. NOT one of the twenty five scheduled steps
rem and NOT part of any chain: it is an instrument, it writes no job status
rem record, and CRITERIA.md [job status steps] must not gain an entry for it,
rem because the watchdog would then expect it and report it overdue.
rem
rem Fires every thirty minutes, all day, every day, and takes ONE reading per
rem firing. Forty eight calls a day against a shared hundred thousand.
rem
rem The job trail answers "which step spent what". This answers "when", which
rem the job trail cannot: eleven tasks sit in two short windows with nothing at
rem all between the 22:45 monitor and the 07:00 catch-up, and that overnight
rem silence is where a sibling project draining the shared key is invisible.
rem
rem One shot per firing rather than a --loop process, so a crash costs one
rem sample rather than silencing the sampler for the rest of the day.
rem
rem PMD_JOB is deliberately not set: a hand run and a scheduled run are the
rem same thing here, and the trail's own source column already says a sampler
rem wrote the row.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
set PYTHONPATH=%CD%\src
if not exist logs mkdir logs
%PY% -m ops.meter_sampler >> "logs\meter-sampler.log" 2>&1
exit /b %ERRORLEVEL%
