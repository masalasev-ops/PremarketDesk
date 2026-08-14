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
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\probe-live-v1-%TODAY%.log

%PY% src\market_today.py >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, probe skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== probe started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\probe_live_v1.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== probe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
