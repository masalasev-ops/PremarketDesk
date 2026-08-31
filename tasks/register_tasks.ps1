# Registers the PremarketDesk jobs with Windows Task Scheduler.
# Run from any directory: powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1
# Remove everything again with: -Unregister
#
# Arm the one off socket cap probe for a chosen morning with:
#   ... -File tasks\register_tasks.ps1 -Probe 2026-08-21
# That registers ONE task with ONE trigger and touches nothing else, which is
# the whole reason it exists. The 2026-08-19 re-arm recorded in CHANGELOG.md
# improvised with `schtasks /Change` against a task that had never been
# created, so it failed silently, and the only probe data that exists was
# taken by hand hours later on a regular hours tape instead of the premarket
# one it was meant to measure. A probe that is meant to be deleted still needs
# a supported way to be created, or it gets created wrong.
#
# Arm the one off Alpaca capture test for a chosen morning with:
#   ... -File tasks\register_tasks.ps1 -Capture 2026-08-24
# Same shape as -Probe and for the same reason: ONE task, ONE trigger, nothing
# else touched. It fires at 08:45 beside the morning chain, spends no EODHD
# quota, and answers whether the free tier serves a running session and what
# the socket captured of it. See tasks\job_probe_capture.bat.
#
# This uses the ScheduledTasks module, not schtasks /Create, because this
# project's path contains spaces and schtasks string quoting stored the /TR
# value unquoted, which made every task die at fire time with 0x80070002,
# file not found, before the .bat even started. The module stores the action
# path structurally, so there is no quoting to get wrong.
#
# All times are local machine time and the machine is expected to keep US
# Eastern. If this machine ever changes time zone, re-derive these triggers
# from the clocks in doc\CRITERIA.md before re-registering.
param([switch]$Unregister, [string]$Probe, [string]$Capture)

$root = Split-Path -Parent $PSScriptRoot
$weekdays = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
$jobs = @(
    @{ Name = "discover";      Bat = "job_discover.bat";      Days = $weekdays;    Start = "07:15" },
    @{ Name = "collector";     Bat = "job_collector.bat";     Days = $weekdays;    Start = "07:20" },
    @{ Name = "morning-chain"; Bat = "job_morning_chain.bat"; Days = $weekdays;    Start = "08:45" },
    # 12:00, and the hour is the point. us-quote-delayed's REGULAR hours
    # behaviour is what was measured, its premarket behaviour is untested, and
    # its previousClosePrice rolls at an hour nobody has pinned down, which is
    # why the midday pass takes its denominator from a bulk day asked for by
    # date instead. See CRITERIA [Midday].
    @{ Name = "midday";        Bat = "job_midday.bat";        Days = $weekdays;    Start = "12:00" },
    @{ Name = "nightly";       Bat = "job_nightly.bat";       Days = $weekdays;    Start = "22:15" },
    # The vendor publishes intraday overnight more often than by 22:15, so the
    # same idempotent nightly runs again before the market day: it fills
    # yesterday via the catch-up sweep and completes the volume verification
    # before the new morning's collection is trusted.
    #
    # It passes "catchup", which runs the backfill and the outcome fill and
    # stops there. Without it this firing also ran pool_recall, which measures
    # the session it is invoked on, so at 07:00 it asked for a session that had
    # not opened and overwrote the previous evening's real recall figures with
    # zeros. See job_nightly.bat.
    @{ Name = "nightly-catchup"; Bat = "job_nightly.bat";      Days = $weekdays;    Start = "07:00"; Args = "catchup" },
    # 21:00, and the two earlier values are worth keeping in view because each
    # was wrong for a different reason.
    #
    # 20:00 was the exact instant of the 00:00 UTC reset (20:00 ET in daylight
    # time, 19:00 in standard), so which quota day the largest job in the
    # schedule billed to was a coin toss.
    #
    # 20:30 assumed the vendor's counter rolls ON the hour. It does not. The
    # 2026-08-16 run read 99,671 used with 329 remaining at 20:30:01 and 4,944
    # at 20:31:49, so the roll landed 30 to 32 minutes AFTER 00:00 UTC. The job
    # spent its first minute reading a counter that was 329 short of exhausted,
    # and a job carrying discover's refuse floor would have stood down on a
    # budget that was in fact about to be full.
    #
    # 21:00 gives roughly double the one lag actually observed. The lag is a
    # vendor behaviour nothing here controls, so the meter trail records
    # apiRequestsDate on every reading and a roll is visible rather than
    # inferred.
    @{ Name = "universe";      Bat = "job_universe.bat";      Days = @("Sunday");  Start = "21:00" },
    # The watchdog: repeats through the morning window, once after the nightly.
    @{ Name = "monitor";       Bat = "job_monitor.bat";       Days = $weekdays;    Start = "07:25"; RepeatMin = 30; RepeatHours = 2 },
    @{ Name = "monitor-night"; Bat = "job_monitor.bat";       Days = $weekdays;    Start = "22:45" },
    # Every day including weekends, every thirty minutes, all twenty four
    # hours. Not a step: an instrument. The job trail says which step spent
    # what and cannot say when, because nothing runs between 22:45 and 07:00
    # and that overnight silence is exactly where a sibling draining the
    # shared key would hide. One call per firing, 48 a day.
    @{ Name = "meter-sampler"; Bat = "job_meter_sampler.bat"; Days = @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"); Start = "00:00"; RepeatMin = 30; RepeatHours = 24 }
)

# The one off probe. NOT in $jobs, because everything in $jobs is registered
# by every plain run of this script and this task is meant to be deleted the
# moment it has answered doc/research/COLLECTOR_VOLUME.md. A plain run must
# never resurrect it.
#
# 06:30 is derived, not chosen. job_probe_socket_cap.bat runs 4 cycles of two
# arms at 120s with 90s to settle, which is 28 minutes, and the probe adds a
# 60s buffer before checking itself against CRITERIA [Collector] start_time,
# 07:20. It refuses any run that would still be holding socket slots when the
# collector wants them, because the fifty symbol pool is account wide. 06:30
# finishes at 06:59 and leaves 21 minutes of slack, and the execution time
# limit below is set so Task Scheduler's own kill also lands before 07:20 if
# the probe hangs rather than exits.
$probeName = "probe-socket-cap"
$probeStart = "06:30"
if ($Probe) {
    $bat = Join-Path (Join-Path $root "tasks") "job_probe_socket_cap.bat"
    if (-not (Test-Path $bat)) {
        Write-Output "MISSING   $bat. The probe was deleted, which is what was"
        Write-Output "          meant to happen once the question was answered."
        exit 1
    }
    try {
        $day = [datetime]::ParseExact($Probe, "yyyy-MM-dd", $null)
    } catch {
        Write-Output "FAILED    -Probe wants a date as yyyy-MM-dd, got '$Probe'"
        exit 1
    }
    $at = $day.Date.Add([timespan]::Parse($probeStart))
    if ($at -le (Get-Date)) {
        Write-Output "FAILED    $Probe $probeStart is in the past. A one time trigger"
        Write-Output "          already behind the clock never fires."
        exit 1
    }
    if ($day.DayOfWeek -eq "Saturday" -or $day.DayOfWeek -eq "Sunday") {
        Write-Output "FAILED    $Probe is a $($day.DayOfWeek). The probe measures a"
        Write-Output "          premarket tape, and there is not one at the weekend."
        exit 1
    }
    # StartWhenAvailable is deliberate even though it can fire the probe onto a
    # denser tape than the premarket one wanted: the probe stamps the window it
    # actually saw into its own output and refuses the only harmful case, which
    # is overlapping the collector. A late reading that says which tape it read
    # beats no reading and no log at all.
    $action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Once -At $at
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
    try {
        Register-ScheduledTask -TaskName $probeName -TaskPath "\PremarketDesk\" `
            -Action $action -Trigger $trigger -Settings $settings -Force -ErrorAction Stop | Out-Null
        Write-Output "registered PremarketDesk\$probeName once at $($at.ToString('yyyy-MM-dd HH:mm')), waking the machine if asleep"
        Write-Output "           it writes logs\probe-socket-cap-$Probe.log and spends no EODHD quota"
        Write-Output "           read it back the NEXT session, which DOES spend one intraday call per watched symbol."
        Write-Output "           From cmd in the project root, because -m needs src on the path:"
        Write-Output "             set PYTHONPATH=%CD%\src"
        Write-Output "             .venv\Scripts\python.exe -m research.probe_socket_cap --compare socket-cap-probe-$Probe.json"
        Write-Output "           delete it when the question is answered:"
        Write-Output "             schtasks /Delete /TN ""\PremarketDesk\$probeName"" /F"
    } catch {
        Write-Output "FAILED    PremarketDesk\$($probeName): $($_.Exception.Message)"
        exit 1
    }
    exit 0
}

# The one off capture test. NOT in $jobs, for the same reason the probe above
# is not: it is meant to be deleted once DECISIONS.md carries its answer, and a
# plain run of this script must never resurrect it.
#
# 08:45 is not chosen, it is [Scan] run_time. The whole question is what the
# vendor serves at the clock production asks it, so a run at any other time
# answers a different one. It runs BESIDE the morning chain, which is safe
# because it spends no EODHD quota and writes nothing the chain reads.
$captureName = "probe-capture"
$captureStart = "08:45"
if ($Capture) {
    $bat = Join-Path (Join-Path $root "tasks") "job_probe_capture.bat"
    if (-not (Test-Path $bat)) {
        Write-Output "MISSING   $bat. The capture test was deleted, which is what"
        Write-Output "          was meant to happen once the question was answered."
        exit 1
    }
    try {
        $day = [datetime]::ParseExact($Capture, "yyyy-MM-dd", $null)
    } catch {
        Write-Output "FAILED    -Capture wants a date as yyyy-MM-dd, got '$Capture'"
        exit 1
    }
    $at = $day.Date.Add([timespan]::Parse($captureStart))
    if ($at -le (Get-Date)) {
        Write-Output "FAILED    $Capture $captureStart is in the past. A one time trigger"
        Write-Output "          already behind the clock never fires."
        exit 1
    }
    if ($day.DayOfWeek -eq "Saturday" -or $day.DayOfWeek -eq "Sunday") {
        Write-Output "FAILED    $Capture is a $($day.DayOfWeek). This test measures a live"
        Write-Output "          premarket against a live collector, and there is neither"
        Write-Output "          at the weekend. A market holiday is not caught here: the"
        Write-Output "          .bat checks ops.market_today and stands down on one."
        exit 1
    }
    # StartWhenAvailable is deliberately NOT set. A missed 08:45 that fires at
    # 10:30 would sweep a window the vendor serves for a reason that has
    # nothing to do with production, and record a 200 that reads as an answer.
    # The probe itself refuses a run started more than twenty minutes early and
    # labels a control fired late, so a late catch up run would be caught, but
    # the cleanest outcome for a missed morning is no record rather than one
    # that has to be read carefully.
    $action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -Once -At $at
    # AllowStartIfOnBatteries is not a default and has to be asked for. The
    # default REFUSES to start a task on battery power, so a laptop unplugged
    # overnight wakes at 08:45, declines to run, and leaves no record at all.
    # DontStopIfGoingOnBatteries is the same fact at the other end: without it
    # a run that starts on mains and loses power mid sweep is killed.
    $settings = New-ScheduledTaskSettingsSet -WakeToRun `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    try {
        Register-ScheduledTask -TaskName $captureName -TaskPath "\PremarketDesk\" `
            -Action $action -Trigger $trigger -Settings $settings -Force -ErrorAction Stop | Out-Null
        Write-Output "registered PremarketDesk\$captureName once at $($at.ToString('yyyy-MM-dd HH:mm')), waking the machine if asleep"
        Write-Output "           waking works from sleep and not from a powered off machine"
        Write-Output "           it writes logs\probe-capture-$Capture.log, spends no EODHD quota,"
        Write-Output "           and needs the collector to have been running that morning"
        Write-Output "           read it back with:"
        Write-Output "             set PYTHONPATH=%CD%\src"
        Write-Output "             .venv\Scripts\python.exe -m research.probe_capture_live --report --date $Capture"
        Write-Output "           delete it when the question is answered:"
        Write-Output "             schtasks /Delete /TN ""\PremarketDesk\$captureName"" /F"
    } catch {
        Write-Output "FAILED    PremarketDesk\$($captureName): $($_.Exception.Message)"
        exit 1
    }
    exit 0
}

foreach ($job in $jobs) {
    $taskPath = "\PremarketDesk\"
    if ($Unregister) {
        try {
            Unregister-ScheduledTask -TaskName $job.Name -TaskPath $taskPath -Confirm:$false -ErrorAction Stop
            Write-Output "removed   PremarketDesk\$($job.Name)"
        } catch {
            Write-Output "not found PremarketDesk\$($job.Name)"
        }
        continue
    }

    $bat = Join-Path (Join-Path $root "tasks") $job.Bat
    if (-not (Test-Path $bat)) {
        Write-Output "MISSING   $bat, skipped"
        continue
    }

    # -Argument is passed structurally like -Execute, so the spaced project
    # path is not involved and the schtasks quoting trap does not apply here.
    # Only nightly-catchup carries one today.
    if ($job.Args) {
        $action = New-ScheduledTaskAction -Execute $bat -Argument $job.Args -WorkingDirectory $root
    } else {
        $action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
    }
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $job.Days -At $job.Start
    if ($job.RepeatMin) {
        # Weekly triggers cannot take repetition parameters directly in this
        # PowerShell version, so borrow the repetition block from a once
        # trigger, which can.
        $repeater = New-ScheduledTaskTrigger -Once -At $job.Start `
            -RepetitionInterval (New-TimeSpan -Minutes $job.RepeatMin) `
            -RepetitionDuration (New-TimeSpan -Hours $job.RepeatHours)
        $trigger.Repetition = $repeater.Repetition
    }
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 4)

    try {
        Register-ScheduledTask -TaskName $job.Name -TaskPath $taskPath `
            -Action $action -Trigger $trigger -Settings $settings -Force -ErrorAction Stop | Out-Null
        $repeat = ""
        if ($job.RepeatMin) { $repeat = ", repeating every $($job.RepeatMin)m for $($job.RepeatHours)h" }
        Write-Output "registered PremarketDesk\$($job.Name) at $($job.Start) ($($job.Days -join ','))$repeat"
    } catch {
        Write-Output "FAILED    PremarketDesk\$($job.Name): $($_.Exception.Message)"
    }
}

if ($Unregister) {
    # The probe is not in $jobs, so the loop above cannot have reached it. A
    # removal that leaves one task behind is worse than no removal, because
    # the folder then looks empty in the GUI listing people actually read.
    try {
        Unregister-ScheduledTask -TaskName $probeName -TaskPath "\PremarketDesk\" `
            -Confirm:$false -ErrorAction Stop
        Write-Output "removed   PremarketDesk\$probeName"
    } catch {
        Write-Output "not found PremarketDesk\$probeName"
    }
    try {
        Unregister-ScheduledTask -TaskName $captureName -TaskPath "\PremarketDesk\" `
            -Confirm:$false -ErrorAction Stop
        Write-Output "removed   PremarketDesk\$captureName"
    } catch {
        Write-Output "not found PremarketDesk\$captureName"
    }
}

if (-not $Unregister) {
    Write-Output ""
    Write-Output "In the Task Scheduler GUI: Task Scheduler Library > PremarketDesk (press F5 if open)."
    Write-Output "Every job appends to logs\<job>-YYYY-MM-DD.log in the project."
}
