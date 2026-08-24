@echo off
rem PremarketDesk 07:20 collector job. Runs the trades websocket until the
rem CRITERIA.md stop time, 09:25 ET, writing one minute bars for the context
rem tickers plus the watchlist rows discover marked subscribed, in the order
rem discover ranked them. This process is the only source of premarket price.
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
set PMD_JOB=collector
rem One optional argument, and only the watchdog ever passes it. Since
rem 2026-08-24 collect_premarket REFUSES a watchlist that was not written
rem today, because a power cut let Task Scheduler catch discover and this job
rem up in the same second and the collector subscribed to the previous
rem session's file while looking perfectly healthy. monitor_jobs overrules that
rem refusal in exactly one branch: past the last pass that could rerun discover
rem inside the collector window, where the choice is possibly wrong names
rem against no tape at all. See CRITERIA.md [Monitor], the stale watchlist note.
set MODE=%~1
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\collector-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, collector skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== collector started %DATE% %TIME% ===== >> "%LOG%"
if /i "%MODE%"=="stale-watchlist-ok" (
    echo ===== stale-watchlist-ok passed by the watchdog %DATE% %TIME% ===== >> "%LOG%"
    %PY% -m collect.collect_premarket --stale-watchlist-ok >> "%LOG%" 2>&1
) else (
    %PY% -m collect.collect_premarket >> "%LOG%" 2>&1
)
set RC=%ERRORLEVEL%
echo ===== collector finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
