@echo off
rem PremarketDesk 08:45 morning chain: scan, analyst, render, deliver.
rem Stops on the first failure, so a bad packet never reaches the model and a
rem bad report never reaches email. deliver.py itself refuses to send while
rem the data\UNVERIFIED gate marker exists or while email keys are unset.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
rem Every step this job runs records its outcome under this name in
rem data\job-status.jsonl. See CRITERIA.md [job status].
set PMD_JOB=morning-chain
for /f "usebackq delims=" %%d in (`%PY% -c "import sys; sys.path.insert(0, 'src'); import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs
set LOG=logs\morning-chain-%TODAY%.log

%PY% src\market_today.py >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, morning chain skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

echo ===== scan started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\scan.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== scan finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== analyst started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\analyst.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== analyst finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== render started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\render_report.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== render finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

rem The gate table is printed into the log every morning for the human to
rem review. It does not stop the chain: deliver.py itself enforces the gate.
echo ===== gate table %DATE% %TIME% ===== >> "%LOG%"
%PY% src\verify_morning.py >> "%LOG%" 2>&1

echo ===== deliver started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\deliver.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== deliver finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== archive started %DATE% %TIME% ===== >> "%LOG%"
%PY% src\build_archive.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== archive finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
exit /b %RC%
