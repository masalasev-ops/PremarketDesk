@echo off
rem PremarketDesk one off probe, NOT part of any chain and NOT a scheduled
rem step. It samples real-time/{symbol} every three minutes from 08:00 to
rem 09:15 and puts the collector's own bars beside each reading, to settle
rem whether that endpoint serves today's premarket or the last completed
rem session the exchange wide form serves.
rem
rem Registered as a single one time trigger for the next trading day. Delete
rem the task and this file once the question is answered:
rem   schtasks /Delete /TN "\PremarketDesk\probe-live-v1" /F
rem
rem PMD_JOB is deliberately not set. This is not a scheduled step, it writes
rem no status record, and CRITERIA.md [job status steps] must not gain a step
rem that is meant to stop existing.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
rem src/ is the import root and every module lives in a package under it,
rem so scripts are run with -m rather than by path. PYTHONPATH is what puts
rem src/ on sys.path; running a file by path would put its own package
rem directory there instead and every `from core import config` would fail.
set PYTHONPATH=%CD%\src
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\probe-live-v1-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, probe skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== probe started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m research.probe_live_v1 >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== probe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
