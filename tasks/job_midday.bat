@echo off
rem PremarketDesk 12:00 midday job. Two steps: scan_midday builds the packet,
rem render_midday lays it out. No model runs here and no narrative is written,
rem so there is no analyst step, no containment check and no delivery gate.
rem See CRITERIA.md [Midday], "Why this pass has no narrative".
rem
rem The hour is not arbitrary. us-quote-delayed's REGULAR hours behaviour is
rem what was measured on 2026-08-17, at 09:56:12 against a 09:57 fetch, and its
rem premarket behaviour is untested. EODHD does not publish today's intraday
rem bars until overnight, measured 2026-08-31, so this pass cannot read the
rem endpoint the nightly measures the morning with.
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
set PMD_JOB=midday
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\midday-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, midday skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== midday scan started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m midday.scan_midday >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== midday scan finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== midday render started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m midday.render_midday >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== midday render finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
