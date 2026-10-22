# Register a Windows scheduled task that starts the RugGuard supervisor at logon (hidden, auto-restart).
# Remove: Unregister-ScheduledTask -TaskName RugGuard -Confirm:$false
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$pythonw = (Get-Command pythonw).Source
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m rugguard.supervisor" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "RugGuard" -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "RugGuard collector and backfill supervisor" -Force | Out-Null
Write-Output "registered RugGuard task: $pythonw -m rugguard.supervisor (cwd $root)"
