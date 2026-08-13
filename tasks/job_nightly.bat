@echo off
rem PremarketDesk 22:15 nightly job: true premarket backfill for today's
rem picks, the definitive collector volume verification, then the outcome
rem fill for every pick old enough to have outcomes.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\nightly-%TODAY%.log

echo ===== backfill started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\backfill_premarket.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== backfill finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== outcomes started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\fill_outcomes.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== outcomes finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

rem The archive also rebuilds here so a morning that failed after the scan
rem still gets archived the same evening.
echo ===== archive started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\build_archive.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== archive finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
