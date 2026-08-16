# Registers the PremarketDesk jobs with Windows Task Scheduler.
# Run from any directory: powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1
# Remove everything again with: -Unregister
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
param([switch]$Unregister)

$root = Split-Path -Parent $PSScriptRoot
$weekdays = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
$jobs = @(
    @{ Name = "discover";      Bat = "job_discover.bat";      Days = $weekdays;    Start = "07:15" },
    @{ Name = "collector";     Bat = "job_collector.bat";     Days = $weekdays;    Start = "07:20" },
    @{ Name = "morning-chain"; Bat = "job_morning_chain.bat"; Days = $weekdays;    Start = "08:45" },
    @{ Name = "nightly";       Bat = "job_nightly.bat";       Days = $weekdays;    Start = "22:15" },
    # The vendor publishes intraday overnight more often than by 22:15, so the
    # same idempotent nightly runs again before the market day: it fills
    # yesterday via the catch-up sweep and completes the volume verification
    # before the new morning's collection is trusted.
    @{ Name = "nightly-catchup"; Bat = "job_nightly.bat";      Days = $weekdays;    Start = "07:00" },
    # 20:30, NOT 20:00. The EODHD quota counter resets at 00:00 UTC, which is
    # 20:00 ET in daylight time and 19:00 in standard, so a Sunday 20:00 start
    # fired at the exact instant of the reset for half the year and which quota
    # day it billed to was a race. The universe rebuild is the largest single
    # job in the schedule, buying lookback_sessions bulk calls in one run, so
    # losing that race means spending it against a counter that has been
    # accumulating since the previous evening. 20:30 sits clear of the boundary
    # in both halves of the year.
    @{ Name = "universe";      Bat = "job_universe.bat";      Days = @("Sunday");  Start = "20:30" },
    # The watchdog: repeats through the morning window, once after the nightly.
    @{ Name = "monitor";       Bat = "job_monitor.bat";       Days = $weekdays;    Start = "07:25"; RepeatMin = 30; RepeatHours = 2 },
    @{ Name = "monitor-night"; Bat = "job_monitor.bat";       Days = $weekdays;    Start = "22:45" }
)

# One time cleanup: the first registrations used flat root level names.
foreach ($legacy in "PremarketDesk-discover", "PremarketDesk-collector",
                    "PremarketDesk-morning-chain", "PremarketDesk-nightly",
                    "PremarketDesk-universe") {
    schtasks /Delete /TN $legacy /F 2>$null | Out-Null
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

    $action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
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

if (-not $Unregister) {
    Write-Output ""
    Write-Output "In the Task Scheduler GUI: Task Scheduler Library > PremarketDesk (press F5 if open)."
    Write-Output "Every job appends to logs\<job>-YYYY-MM-DD.log in the project."
}
