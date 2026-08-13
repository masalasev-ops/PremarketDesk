# Registers the PremarketDesk jobs with Windows Task Scheduler.
# Run from any directory: powershell -ExecutionPolicy Bypass -File tasks\register_tasks.ps1
# Remove everything again with: -Unregister
#
# All times are local machine time and the machine is expected to keep US
# Eastern. If this machine ever changes time zone, re-derive these triggers
# from the clocks in doc\CRITERIA.md before re-registering.
param([switch]$Unregister)

$root = Split-Path -Parent $PSScriptRoot
$jobs = @(
    @{ Name = "PremarketDesk-discover";      Bat = "job_discover.bat";      Schedule = "WEEKLY"; Days = "MON,TUE,WED,THU,FRI"; Start = "07:15" },
    @{ Name = "PremarketDesk-collector";     Bat = "job_collector.bat";     Schedule = "WEEKLY"; Days = "MON,TUE,WED,THU,FRI"; Start = "07:20" },
    @{ Name = "PremarketDesk-morning-chain"; Bat = "job_morning_chain.bat"; Schedule = "WEEKLY"; Days = "MON,TUE,WED,THU,FRI"; Start = "08:45" },
    @{ Name = "PremarketDesk-nightly";       Bat = "job_nightly.bat";       Schedule = "WEEKLY"; Days = "MON,TUE,WED,THU,FRI"; Start = "22:15" },
    @{ Name = "PremarketDesk-universe";      Bat = "job_universe.bat";      Schedule = "WEEKLY"; Days = "SUN";                 Start = "20:00" }
)

foreach ($job in $jobs) {
    if ($Unregister) {
        schtasks /Delete /TN $job.Name /F 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Output "removed   $($job.Name)" }
        else { Write-Output "not found $($job.Name)" }
        continue
    }
    $bat = Join-Path (Join-Path $root "tasks") $job.Bat
    if (-not (Test-Path $bat)) {
        Write-Output "MISSING   $bat, skipped"
        continue
    }
    schtasks /Create /F /TN $job.Name /TR "`"$bat`"" /SC $job.Schedule /D $job.Days /ST $job.Start | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Output "registered $($job.Name) at $($job.Start) ($($job.Days))" }
    else { Write-Output "FAILED    $($job.Name), run this script from an elevated prompt if access was denied" }
}

if (-not $Unregister) {
    Write-Output ""
    Write-Output "Verify with: schtasks /Query /TN PremarketDesk-morning-chain /V /FO LIST"
    Write-Output "Every job appends to logs\<job>-YYYY-MM-DD.log in the project."
}
