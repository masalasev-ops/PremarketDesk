@echo off
rem PremarketDesk live ladder. Fires every two minutes from 09:30 to 10:15 on
rem weekdays and answers one question: which of this morning's published names
rem is closest to its entry, right now.
rem
rem WHY A TASK AND NOT A LOOP. One shot per firing, for the reason the meter
rem sampler gives: a crash costs one reading rather than silencing the screen
rem for the rest of the window. Two minutes is well inside the minute bar
rem resolution and the whole pass is two file reads and no vendor call.
rem
rem THE CALENDAR GUARD FIRST, like every other job. A ladder drawn on a day the
rem market is shut would show ten names waiting forever at a level nothing was
rem ever going to trade through.
rem
rem THEN THE DESK, because the ladder is only useful on a page. desk.render
rem reads and renders and makes no vendor call. NOT --no-compact: the payload
rem the page reads is the compacted one, so skipping the compact would redraw
rem the page around a ladder it had not picked up, every two minutes, forever.
rem
rem The exit code is the LADDER's, never the desk's. A page that failed to draw
rem is worth reporting; it is not worth reporting as a ladder that failed to
rem measure.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
set PYTHONPATH=%CD%\src
set PMD_JOB=ladder
for /f %%d in ('%PY% -c "from core import ettime; print(ettime.today_str())"') do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\ladder-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, ladder skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)
if %ERRORLEVEL% equ 4 (
    echo ===== dormant, ladder skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== ladder started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m morning.ladder >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== ladder finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"

echo ===== desk started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m desk.render >> "%LOG%" 2>&1
echo ===== desk finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
