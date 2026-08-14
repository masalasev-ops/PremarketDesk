@echo off
rem PremarketDesk Sunday 20:00 job: rebuild the weekly discovery universe.
rem Every later script refuses to run when this is more than the CRITERIA.md
rem max_age_days stale, so this is the job that keeps the week alive.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\universe-%TODAY%.log

echo ===== universe started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\universe.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== universe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

rem Gap propensity rides the universe schedule so it costs nothing at 07:15.
rem About one counted call per universe name, measured at 0.15 seconds each,
rem so roughly 2,745 calls and seven minutes once a week. It runs after the
rem universe because it reads the membership the rebuild just wrote.
echo ===== gap stats started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\gap_stats.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== gap stats finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
