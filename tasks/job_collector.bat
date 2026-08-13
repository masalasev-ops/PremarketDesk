@echo off
rem PremarketDesk 07:20 collector job. Runs the trades websocket until the
rem CRITERIA.md stop time, 09:25 ET, writing one minute bars for the
rem watchlist. This process is the only source of premarket high, low, VWAP.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\collector-%TODAY%.log

echo ===== collector started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\collect_premarket.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== collector finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
