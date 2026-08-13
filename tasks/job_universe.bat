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
exit /b %RC%
