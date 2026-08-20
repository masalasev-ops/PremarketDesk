@echo off
rem PremarketDesk 22:15 nightly job: true premarket backfill for today's
rem picks, the definitive collector volume verification, then the outcome
rem fill for every pick old enough to have outcomes.
rem
rem Called with the argument "catchup" it runs the vendor-lag half only, which
rem is the backfill and the outcome fill, and skips pool recall and the archive
rem rebuild. The 07:00 registration passes it. Until 2026-08-20 that firing ran
rem the whole job, and pool_recall measures the session it is invoked ON, so
rem every weekday at 07:00 it asked the vendor for a session that had not
rem opened, got an empty payload, and wrote gapped 0, addressable 0, recall 0.0
rem over the real measurement the 22:15 pass had taken. The evening pass is the
rem one with a closed session to measure; the morning pass has nothing to add.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
rem src/ is the import root and every module lives in a package under it,
rem so scripts are run with -m rather than by path. PYTHONPATH is what puts
rem src/ on sys.path; running a file by path would put its own package
rem directory there instead and every `from core import config` would fail.
set PYTHONPATH=%CD%\src
rem Every step this job runs records its outcome under this name in
rem data\job-status.jsonl. See CRITERIA.md [job status].
set PMD_JOB=nightly
rem PMD_JOB stays "nightly" for both firings. They are two passes of one job,
rem and monitor_jobs.JOB_STATUS_NAMES maps the nightly to that one name: a
rem second name here would mean the catch-up's step records were never read,
rem which is the silent mismatch that table exists to prevent.
set MODE=%~1
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\nightly-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, nightly skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

rem Refresh the exchange calendar here so the 08:45 chain never fetches it.
rem scan.py sets ALLOW_NETWORK false, so a stale calendar in the morning is
rem used as it stands and recorded rather than blocking the window on a fetch
rem and its retries. Never fails the chain: a stale calendar is survivable and
rem the morning says so in the packet.
echo ===== calendar refresh started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m ops.market_today --refresh >> "%LOG%" 2>&1
echo ===== calendar refresh finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

echo ===== backfill started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.backfill_premarket >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== backfill finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== outcomes started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.fill_outcomes >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== outcomes finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

if /i "%MODE%"=="catchup" (
    echo ===== catchup mode, pool recall and archive skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

rem What the morning's candidate pool missed, measured against every name in
rem the universe that actually gapped at the open. Never fails the chain: a
rem recall measurement is a diagnostic and nothing downstream reads it.
echo ===== pool recall started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.pool_recall >> "%LOG%" 2>&1
echo ===== pool recall finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem The archive also rebuilds here so a morning that failed after the scan
rem still gets archived the same evening.
echo ===== archive started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.build_archive >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== archive finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
