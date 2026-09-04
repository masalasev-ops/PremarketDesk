@echo off
rem PremarketDesk nightly job, ONE scheduled task with three triggers since
rem 2026-09-02: 22:15 on weekdays runs the whole night, 07:00 on weekdays runs
rem the vendor-lag half only, and Sunday 21:00 rebuilds the weekly universe.
rem Which of the three this firing is comes from the clock, not from an
rem argument, because Task Scheduler gives a task one action and the three
rem used to be three tasks (nightly, nightly-catchup, universe) that were
rem three places for one schedule to drift.
rem
rem   full      22:15 weekdays: true premarket backfill for today's picks, the
rem             definitive collector volume verification, the outcome fill,
rem             truth, the paper ledger, pool recall, the prune, the weekly
rem             page and the archive rebuild.
rem   catchup   07:00 weekdays: the backfill and the outcome fill only. Until
rem             2026-08-20 that firing ran the whole job, and pool_recall
rem             measures the session it is invoked ON, so at 07:00 it asked
rem             for a session that had not opened and wrote recall 0.0 over
rem             the evening's real measurement.
rem   universe  Sunday 21:00: the weekly discovery universe and the gap
rem             propensity sweep, under PMD_JOB universe and its own log, so
rem             every reader of those records sees what it always saw.
rem
rem A hand run may pass the mode as its argument (full, catchup, universe)
rem and skip the clock; that is the only reason the argument still exists.
setlocal
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
rem src/ is the import root and every module lives in a package under it,
rem so scripts are run with -m rather than by path. PYTHONPATH is what puts
rem src/ on sys.path; running a file by path would put its own package
rem directory there instead and every `from core import config` would fail.
set PYTHONPATH=%CD%\src
set MODE=%~1
if "%MODE%"=="" (
    for /f "usebackq delims=" %%m in (`%PY% -c "from core import ettime; n=ettime.now_et(); print('universe' if n.weekday()==6 else ('catchup' if n.hour<12 else 'full'))"`) do set MODE=%%m
)
if "%MODE%"=="" set MODE=full
for /f "usebackq delims=" %%d in (`%PY% -c "from core import ettime; print(ettime.today_str())"`) do set TODAY=%%d
if "%TODAY%"=="" set TODAY=undated
if not exist logs mkdir logs

if /i "%MODE%"=="universe" goto universe

rem Every step this job runs records its outcome under this name in
rem data\job-status.jsonl. See CRITERIA.md [job status].
set PMD_JOB=nightly
rem PMD_JOB stays "nightly" for the full and the catch-up firings. They are
rem two passes of one job, and monitor_jobs.JOB_STATUS_NAMES maps the nightly
rem to that one name: a second name here would mean the catch-up's step
rem records were never read, which is the silent mismatch that table exists
rem to prevent.
set LOG=logs\nightly-%TODAY%.log

%PY% -m ops.market_today >> "%LOG%" 2>&1
if %ERRORLEVEL% equ 3 (
    echo ===== market closed today, nightly skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

rem Refresh the exchange calendar here so the 08:45 chain never fetches it.
rem scan.py sets ALLOW_NETWORK false, so a stale calendar in the morning is
rem used as it stands and recorded rather than blocking the window on a fetch
rem and its retries. Never fails the chain: a stale calendar is survivable and
rem the morning says so in the packet.
echo ===== calendar refresh started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m ops.market_today --refresh >> "%LOG%" 2>&1
echo ===== calendar refresh finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem FIRST, before anything else touches the tree. It copies the day's premarket
rem capture and packet outside the working tree, and those are the only two
rem artifacts here that cannot be rebuilt. Never fails the chain: an unmade
rem copy is not a reason to skip a night's work, and the step reports a
rem disagreement rather than resolving one. See CRITERIA.md [Backup].
echo ===== backup started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.backup_evidence >> "%LOG%" 2>&1
echo ===== backup finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

echo ===== backfill started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.backfill_premarket >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== backfill finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

echo ===== outcomes started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.fill_outcomes >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ===== outcomes finished rc=%RC% %DATE% %TIME% ===== >> "%LOG%"
if %RC% neq 0 exit /b %RC%

if /i "%MODE%"=="catchup" (
    echo ===== catchup mode, pool recall and archive skipped %DATE% %TIME% ===== >> "%LOG%"
    exit /b 0
)

rem What premarket volume actually was, from Alpaca's full SIP tape, written
rem beside the morning's estimate and never over it. Alpaca serves sip for a
rem session that is over and refuses it for one that is running, which is why
rem this is here and not in the 08:45 chain. Never fails the chain: the record
rem is better with it and the morning does not read it. It spends no EODHD
rem quota. See CRITERIA.md [Truth].
echo ===== truth started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.true_volume >> "%LOG%" 2>&1
echo ===== truth finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem What ONE written rule in CRITERIA.md [Paper] would have done with each of
rem today's picks, booked against the MEASURED reference levels and Alpaca's
rem one minute bars. AFTER truth, because it reads entry_ref_true,
rem stop_ref_true and fill_plausible, and every one of those is written by the
rem step above. It trades the PICK'S OWN session, which is not the session
rem night.fill_outcomes measures; see the module docstring. Never fails the
rem chain: a ledger is a record and nothing downstream reads it. It spends no
rem EODHD quota.
echo ===== paper started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.paper_ledger >> "%LOG%" 2>&1
echo ===== paper finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem What the morning's candidate pool missed, measured against every name in
rem the universe that actually gapped at the open. Never fails the chain: a
rem recall measurement is a diagnostic and nothing downstream reads it.
echo ===== pool recall started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.pool_recall >> "%LOG%" 2>&1
echo ===== pool recall finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem Freeze each session's desk payload BEFORE the prune runs. The order is
rem load bearing: prune's third interlock refuses to drop a duplicate snapshot
rem until desk.json.gz exists for that session, because the collector file is
rem the whole day and the snapshot is a point in time cut of it, so a session
rem whose bars were never frozen cannot have its tape path redrawn exactly.
rem Run the other way round this frees nothing and refuses every session.
rem Never fails the chain.
echo ===== compact started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m desk.compact >> "%LOG%" 2>&1
echo ===== compact finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem Delete the dated data files past their retention window, then sweep runs/.
rem Never fails the chain: unfreed disk is not a reason to fail a night, and
rem the step reports what it kept as well as what it took. Under data/ it
rem deletes only what its PRUNABLE whitelist names, which is one file class;
rem see CRITERIA.md [Universe] the closes retention note for what is
rem deliberately NOT in it. Under runs/ it COMPRESSES past CRITERIA
rem [Retention] hot_sessions and deletes exactly one thing, the duplicate
rem premarket_snapshot.jsonl, under the three interlocks above.
echo ===== prune started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.prune_data >> "%LOG%" 2>&1
echo ===== prune finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem One page saying whether the week worked, rendered from what the steps
rem above have just finished writing. It reads and renders: no vendor call, no
rem new table, no measurement of its own. Last of the reading steps so every
rem source it reads is already current. Never fails the chain.
echo ===== weekly started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m night.weekly_page >> "%LOG%" 2>&1
echo ===== weekly finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"

rem The desk, rebuilt last so it inlines what every step above has just
rem written, including tonight's outcomes and the compaction. It also rebuilds
rem here so a morning that failed after the scan still reaches a screen the
rem same evening, which is what the retired archive step did. Full rebuild
rem from disk, never an append. Never fails the chain.
echo ===== desk started %DATE% %TIME% ===== >> "%LOG%"
%PY% -m desk.render --no-compact >> "%LOG%" 2>&1
echo ===== desk finished rc=%ERRORLEVEL% %DATE% %TIME% ===== >> "%LOG%"
exit /b 0

:universe
rem The Sunday firing. No trading day guard: Sunday is closed by definition
rem and the guard would stand the rebuild down. Every later script refuses to
rem run when universe.json is more than [Universe] max_age_days stale, so this
rem is the firing that keeps the week alive. Until 2026-09-02 this was
rem job_universe.bat under its own task; the log name and PMD_JOB are kept so
rem the watchdog, the job trail and the archive read exactly what they did.
set PMD_JOB=universe
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
