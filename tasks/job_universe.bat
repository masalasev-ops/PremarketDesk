@echo off
rem PremarketDesk Sunday 20:00 job: rebuild the weekly discovery universe.
rem Every later script refuses to run when this is more than the CRITERIA.md
rem max_age_days stale, so this is the job that keeps the week alive.
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
set PMD_JOB=universe
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\universe-%TODAY%.log

echo ===== universe started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m selection.universe >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== universe finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

rem Gap propensity rides the universe schedule so it costs nothing at 07:15.
rem About one counted call per universe name, measured at 0.15 seconds each,
rem so roughly 2,745 calls and seven minutes once a week. It runs after the
rem universe because it reads the membership the rebuild just wrote.
echo ===== gap stats started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m selection.gap_stats >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== gap stats finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
