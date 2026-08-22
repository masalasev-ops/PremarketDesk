@echo off
rem PremarketDesk one off probe, NOT part of any chain and NOT a scheduled
rem step. It fires at the same clock the morning chain fires, 08:45, and asks
rem two questions of one Alpaca sweep.
rem
rem Does the free tier serve a premarket window during a RUNNING session. Every
rem request research\probe_alpaca_live.py ever made ended its window at the wall
rem clock, which reaches into the delay the vendor documents, so all 46 of them
rem were refused before the feed was consulted and DECISIONS.md 2026-08-17 read
rem those refusals as a measurement of the feed. One request on Saturday
rem 2026-08-22 asked for the window the delay ALLOWS and got a 200, but that
rem window held no trading. Nobody has yet asked this vendor a question it
rem would answer about a live session.
rem
rem And what the socket actually captured of the tape, on the morning the
rem correction is being applied to. CRITERIA [Collector] premarket_capture_rate
rem is 0.1172, measured against EODHD 1m intraday hours after the fact across
rem four sessions. This measures both sides of that ratio on one tape, over the
rem minutes both tapes carry, at 08:45 on the session it describes.
rem
rem It spends NO EODHD quota, so it cannot compete with the morning chain for
rem the shared counter, and it writes nothing the chain reads. About six Alpaca
rem requests against a 200 per minute limit. Precisely: the ops.market_today
rem guard below makes two calls to the meter endpoint, and the meter reads the
rem same figure at entry and exit, so the counter moves by zero.
rem
rem It runs BESIDE the morning chain rather than before or after it, on purpose:
rem the whole question is what the feed serves at the clock production asks, and
rem a run at 09:15 answers a different one. The probe itself waits 30 seconds
rem past 08:45 before firing, because the window it asks for ends at a fixed
rem 08:30 while the vendor's refusal rule is relative to the wall clock, and
rem firing at 08:44:58 asks for a window inside the documented delay.
rem
rem Registered as a single one time trigger:
rem   powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1 -Capture 2026-08-24
rem Delete the task and this file once DECISIONS carries the answer:
rem   schtasks /Delete /TN "\PremarketDesk\probe-capture" /F
rem
rem PMD_JOB is deliberately not set. This is not a scheduled step, it writes no
rem status record, and CRITERIA.md [job status steps] must not gain a step that
rem is meant to stop existing.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
rem src/ is the import root and every module lives in a package under it, so
rem scripts are run with -m rather than by path. PYTHONPATH is what puts src/
rem on sys.path; running a file by path would put its own package directory
rem there instead and every `from core import config` would fail.
set PYTHONPATH=%CD%\src
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\probe-capture-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, capture probe skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== capture probe started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m research.probe_capture_live >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== capture probe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
