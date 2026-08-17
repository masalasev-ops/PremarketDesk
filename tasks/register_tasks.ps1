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
