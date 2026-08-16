@echo off
rem PremarketDesk one off probe, NOT part of any chain and NOT a scheduled
rem step. It sweeps the whole universe from Alpaca every five minutes from
rem 07:30 to 09:20 and records how many symbols have bars for TODAY and how
rem far behind the wall clock the newest one is.
rem
rem It settles the one thing doc/ALPACA_PROBE.md could not: that probe ran on
rem a Saturday against a completed session, so it proved historical access and
rem nothing about the live morning. DECISIONS.md 2026-08-16 proposes moving
rem discovery off the 50 slot websocket onto this sweep, and that proposal does
rem not stand unless the sweep works live.
rem
rem It spends NO EODHD quota. Prior closes come from Alpaca daily bars, so this
rem cannot compete with the 07:15 discover or the 08:45 scan for the shared
rem counter.
rem
rem Registered as a single one time trigger for the next trading day. Delete
rem the task and this file once the question is answered:
rem   schtasks /Delete /TN "\PremarketDesk\probe-alpaca-live" /F
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
set LOG=logs\probe-alpaca-live-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, probe skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== probe started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m research.probe_alpaca_live >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== probe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
