param([switch]$Install)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$taskName = 'Nivaro Local Development'
Set-Location -LiteralPath $root

if ($Install) {
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $arguments = '-NoProfile -WindowStyle Hidden -File "{0}"' -f $PSCommandPath
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing -and $existing.Actions.Arguments -ne $arguments) {
        throw "The task '$taskName' already points to a different launcher."
    }
    $action = New-ScheduledTaskAction -Execute (Get-Command pwsh.exe).Source -Argument $arguments -WorkingDirectory $root
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
Set-Content -LiteralPath $log -Value "Starting Nivaro development at $(Get-Date -Format o)"
$dockerReady = $false
for ($attempt = 0; $attempt -lt 24; $attempt++) {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds 5
}
if (-not $dockerReady) {
    Add-Content -LiteralPath $log -Value 'Docker Desktop did not become ready.'
    exit 1
}

$compose = @('compose', '-p', 'nivaro', '-f', 'compose.yaml', '-f', 'compose.media.yaml', '-f', 'compose.dev.yaml', '-f', 'compose.local.yaml')
docker image inspect nivaro-web:local-development *> $null
if ($LASTEXITCODE -ne 0) {
    docker @compose build web *>> $log
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
docker @compose up -d --no-build --pull never --wait --wait-timeout 120 *>> $log
if ($LASTEXITCODE -ne 0) { exit 1 }
docker @compose watch --no-up web *>> $log
# A watcher exit during an active login should be retried by Task Scheduler.
exit 1
