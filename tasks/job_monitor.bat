@echo off
rem PremarketDesk watchdog. Checks Task Scheduler and the dated job logs,
rem reruns what is safe (see CRITERIA.md [monitor]), and reports the rest.
rem Exit 1 means something needs a human eye; the detail is in the log.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
rem Every step this job runs records its outcome under this name in
rem data\job-status.jsonl. See CRITERIA.md [job status].
set PMD_JOB=monitor
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\monitor-%TODAY%.log

%PY% src\market_today.py >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, monitor skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== monitor run %DATE% %TIME% ===== >> "%LOG%"
%PY% src\monitor_jobs.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== monitor finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
