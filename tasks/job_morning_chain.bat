@echo off
rem PremarketDesk 08:45 morning chain: scan, analyst, render, verify, deliver, archive.
rem Stops on the first failure, so a bad packet never reaches the model and a
rem bad report never reaches email. deliver.py itself refuses to send while
rem the data\UNVERIFIED gate marker exists or while email keys are unset.
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
set PMD_JOB=morning-chain
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\morning-chain-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, morning chain skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== scan started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.scan >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== scan finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== analyst started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.analyst >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== analyst finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== render started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.render_report >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== render finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

rem The gate table is printed into the log every morning for the human to
rem review. It does not stop the chain: deliver.py itself enforces the gate.
echo ===== gate table %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.verify_morning >> "%LOG%" 2>&1

echo ===== deliver started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.deliver >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== deliver finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== archive started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.build_archive >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== archive finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

rem The desk, so this morning's screens are there before the open. It reads
rem and renders: no vendor call and no measurement of its own. Never fails the
rem chain, because a report that was delivered is not undone by a page that
rem did not draw.
echo ===== desk started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m desk.render >> "%LOG%" 2>&1
echo ===== desk finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"
exit /b 0
