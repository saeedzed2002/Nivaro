param([switch]$Install)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$taskName = 'Nivaro Local Development'
Set-Location -LiteralPath $root

if ($Install) {
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $legacyArguments = '-NoProfile -WindowStyle Hidden -File "{0}"' -f $PSCommandPath
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File "{0}"' -f $PSCommandPath
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing -and $existing.Actions.Arguments -notin @($arguments, $legacyArguments)) {
        throw "The task '$taskName' already points to a different launcher."
    }
    $shell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $action = New-ScheduledTaskAction -Execute $shell -Argument $arguments -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $options = @{
        ExecutionTimeLimit = [TimeSpan]::Zero
        MultipleInstances = 'IgnoreNew'
        AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true
        RestartCount = 5
        RestartInterval = New-TimeSpan -Minutes 1
    }
    $settings = New-ScheduledTaskSettingsSet @options
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Enable-ScheduledTask -TaskName $taskName | Out-Null
    Start-ScheduledTask -TaskName $taskName
    return
}

New-Item -ItemType Directory -Path (Join-Path $root 'work') -Force | Out-Null
$log = Join-Path $root 'work/local-dev-watch.log'
Set-Content -LiteralPath $log -Encoding utf8 -Value "Starting Nivaro development at $(Get-Date -Format o)"
Add-Content -LiteralPath $log -Encoding utf8 -Value 'Waiting for Docker Desktop.'
# Docker writes progress to stderr. Check its exit codes explicitly in Windows PowerShell.
$ErrorActionPreference = 'Continue'
function Invoke-DockerLogged {
    docker @args 2>&1 | ForEach-Object { $_.ToString() } | Out-File -LiteralPath $log -Append -Encoding utf8
    return $LASTEXITCODE
}

while ($true) {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 5
}

$compose = @('compose', '-p', 'nivaro', '-f', 'compose.yaml', '-f', 'compose.media.yaml', '-f', 'compose.dev.yaml', '-f', 'compose.orders.yaml', '-f', 'compose.events.yaml', '-f', 'compose.local.yaml')
docker image inspect nivaro-web:local-development *> $null
if ($LASTEXITCODE -ne 0) {
    if ((Invoke-DockerLogged @compose build web) -ne 0) { exit 1 }
}
$ordersImage = $env:NIVARO_ORDERS_IMAGE
if (-not $ordersImage) { $ordersImage = 'nivaro-orders:release' }
docker image inspect $ordersImage *> $null
if ($LASTEXITCODE -ne 0) {
    if ((Invoke-DockerLogged @compose build orders-init) -ne 0) { exit 1 }
}
if ((Invoke-DockerLogged @compose up -d --no-build --pull never --wait --wait-timeout 120) -ne 0) { exit 1 }
Invoke-DockerLogged @compose watch --no-up web | Out-Null
# A watcher exit during an active login should be retried by Task Scheduler.
exit 1
