@echo off
rem PremarketDesk one off probe, NOT part of any chain and NOT a scheduled
rem step. It answers the one number the socket still owes, and it exists
rem because CRITERIA [Collector] stop_time is being asked to move past 09:25
rem so the midday pass can grade a fill from timestamped minute bars instead
rem of from a daily high and low that carry no order.
rem
rem WHAT IS ALREADY MEASURED, 2026-08-13, and it is not this. Two collector
rem only runs of 20 minutes read /api/user before and after while nothing else
rem touched the key. One made 10 connections, 10 full 38 symbol
rem resubscriptions and 9 reconnects; the other added 3 forced drops, for 13,
rem 13 and 12. Both moved the daily counter by exactly zero. So connecting,
rem subscribing and reconnecting are a measured zero, not an assumption.
rem
rem WHAT IS NOT. Both of those runs rode the QUIET EVENING TAPE. The one
rem window that ever streamed a heavy live tape, 1,574 trade messages,
rem straddled the counter's daily reset at 00:00 UTC and its delta was
rem therefore unreadable. So the per MESSAGE cost on a busy tape is unmeasured,
rem and it is precisely the cost that would change if the collector ran through
rem regular hours, where the tape prints far harder than it does premarket.
rem
rem 10:00 ET, and the hour is chosen. It is past the collector's 09:25 stop, so
rem the 50 symbol account wide cap is free and this cannot starve the morning
rem it is meant to make possible. It is inside regular hours, which is the tape
rem whose message rate is the open question. And it is clear of the 12:00
rem midday job, which spends REST credits and would contaminate the delta.
rem
rem Delete the task and this file once the number is written down.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
set PYTHONPATH=%CD%\src
rem PMD_JOB is deliberately NOT set. This is an instrument, not a step:
rem CRITERIA.md [job status steps] must not gain an entry for it or the
rem watchdog would start reporting it overdue.
if not exist logs mkdir logs
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
set LOG=logs\probe-socket-cost-%TODAY%.log

echo ===== socket cost probe started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m research.measure_socket_cost --minutes 20 >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== socket cost probe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
