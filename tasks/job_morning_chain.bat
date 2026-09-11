@echo off
rem PremarketDesk 08:45 morning chain: scan, analyst, render, verify, deliver,
rem desk, publish.
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
if %ERRORLEVEL% equ 4 (
    echo ===== standing down, data\DORMANT exists, morning chain skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== scan started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.scan >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== scan finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 goto :failed

echo ===== analyst started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.analyst >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== analyst finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 goto :failed

echo ===== render started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.render_report >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== render finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 goto :failed

rem The gate table is printed into the log every morning for the human to
rem review. It does not stop the chain: deliver.py itself enforces the gate.
echo ===== gate table %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.verify_morning >> "%LOG%" 2>&1

echo ===== deliver started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.deliver >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== deliver finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 goto :failed

rem The desk, so this morning's screens are there before the open. It reads
rem and renders: no vendor call and no measurement of its own. Never fails the
rem chain, because a report that was delivered is not undone by a page that
rem did not draw.
echo ===== desk started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m desk.render >> "%LOG%" 2>&1
echo ===== desk finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem Upload site/ to Cloudflare Pages, after the desk so the upload carries
rem this morning's screens. ops/publish.py reads every file first and refuses
rem on an oversized file, a credential, a local path or inline data it cannot
rem parse. It skips cleanly when the Cloudflare values are unset or while
rem data\PUBLISH_HELD exists. Never fails the chain: its exit code goes to
rem job-status, where the watchdog reads it, and a report that was delivered
rem is not undone by an upload that did not happen. This is the last step on
rem this path, so its finished line is the watchdog's finish marker for the
rem job; see monitor_jobs.JOBS.
echo ===== publish started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m ops.publish >> "%LOG%" 2>&1
echo ===== publish finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"
exit /b 0

rem A FAILED STEP STILL DRAWS THE DESK, and then exits with the failure. Until
rem 2026-09-08 every failure above did exit /b here and the desk was never
rem redrawn, so the one morning the owner most needed the page to say something
rem was the one morning it silently showed the previous session. desk.render
rem reads job-status.jsonl and puts today's failures at the top of the page.
rem
rem UNDER ITS OWN MARKER, which is load bearing rather than tidy. The watchdog
rem reads the publish step's finished line as this job's finish marker (the
rem desk's until 2026-09-11), so reusing it here would make a chain that died
rem at scan report as finished, and the one check that catches a chain which
rem never reached its end would stop working on the exact runs it exists for.
rem The publish that follows it has its own marker too, and it runs on this
rem path because a failed morning's desk is the page the owner most needs to
rem reach from wherever they are.
rem
rem The exit code is the FAILED step's, never the desk's. The scheduler, the
rem watchdog and job-status all read it, and a chain that failed must not
rem report success because the page that describes the failure drew correctly.
:failed
echo ===== desk after failure started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m desk.render >> "%LOG%" 2>&1
echo ===== desk after failure finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"
echo ===== publish after failure started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m ops.publish >> "%LOG%" 2>&1
echo ===== publish after failure finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
