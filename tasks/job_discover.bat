@echo off
rem PremarketDesk 07:15 discovery job: build and rank the candidate pool into
rem watchlist.json, then warm the premarket volume baseline cache at the scan
rem cutoff for the names that pool subscribed the collector to, not the whole
rem file, which also carries the rows below the cut. The baseline
rem warm lives here and not in the 08:45 chain because CRITERIA.md says the
rem baseline is never fetched during the morning run.
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
set PMD_JOB=discover
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\discover-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, discover skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== discover started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m selection.discover >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== discover finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== baseline warm started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m collect.baseline >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== baseline warm finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
