@echo off
rem PremarketDesk 07:15 discovery job: write watchlist.json, then warm the
rem premarket volume baseline cache for it at the scan cutoff. The baseline
rem warm lives here and not in the 08:45 chain because CRITERIA.md says the
rem baseline is never fetched during the morning run.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\discover-%TODAY%.log

echo ===== discover started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\discover.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== discover finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== baseline warm started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\baseline.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== baseline warm finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
