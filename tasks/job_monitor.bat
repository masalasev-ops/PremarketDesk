@echo off
rem PremarketDesk watchdog. Checks Task Scheduler and the dated job logs,
rem reruns what is safe (see CRITERIA.md [monitor]), and reports the rest.
rem Exit 1 means something needs a human eye; the detail is in the log.
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
set PMD_JOB=monitor
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\monitor-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, monitor skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== monitor run %DATE% %TIME% ===== >> "%LOG%"
%PY% -m ops.monitor_jobs >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== monitor finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
