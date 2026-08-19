@echo off
rem PremarketDesk one off probe, NOT part of any chain and NOT a scheduled
rem step. It A/B tests the EODHD trades websocket under a small subscription
rem and under one at the documented 50 symbol cap, alternating the arms so the
rem rising premarket rate cannot be mistaken for the effect.
rem
rem It settles the open question in doc/research/COLLECTOR_VOLUME.md. That
rem document proves the collector's premarket volume disagrees with EODHD's own
rem 1m bars by roughly a factor of ten and that the check is sound. It does not
rem say why. The only structural difference between the sessions that look right
rem and the ones that do not is 38 subscriptions against 50, and 50 is the cap.
rem
rem It must not overlap the collector's 07:20 to 09:25 window. The 50 symbol
rem pool is account wide, so a probe still holding slots would starve the very
rem morning it is meant to explain, and the probe refuses any run that would
rem overlap. It also settles 90 seconds between its own arms, because a closed
rem connection keeps its symbols for a while: on 2026-08-19 the collector
rem reconnected one second after a drop and was refused, and a restart 105
rem seconds later was not. Four cycles at two minutes plus the settles is about
rem 28 minutes.
rem
rem The probe run spends NO EODHD quota. Measured 2026-08-13: websocket
rem connections, subscribe frames and reconnects moved the account counter by
rem exactly zero. Its --compare pass is a different matter and spends one
rem intraday call per watched symbol, which is why it is a separate command
rem run by hand the session after: the vendor does not publish a session until
rem it is over, so a fetch from inside this job would buy nothing.
rem
rem Registered as a single one time trigger. Delete the task and this file once
rem the question is answered:
rem   schtasks /Delete /TN "\PremarketDesk\probe-socket-cap" /F
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
set LOG=logs\probe-socket-cap-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, probe skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== probe started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m research.probe_socket_cap --cycles 4 --seconds 120 --settle 90 >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== probe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
