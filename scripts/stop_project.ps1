$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$PidFile = Join-Path $ProjectRoot "data\backend_runtime\project_processes.json"

if (-not (Test-Path $PidFile)) {
    Write-Host "فایل PID پیدا نشد. احتمالاً پروژه با Launcher اجرا نشده است." -ForegroundColor Yellow
    exit 0
}

try { $State = Get-Content $PidFile -Raw | ConvertFrom-Json }
catch {
    Write-Host "فایل PID قابل خواندن نیست." -ForegroundColor Red
    exit 1
}

$Pids = @($State.backend_shell_pid, $State.frontend_shell_pid) | Where-Object { $_ -and $_ -gt 0 }
foreach ($ProcessId in $Pids) {
    Write-Host "Stopping process tree PID $ProcessId ..."
    taskkill /PID $ProcessId /T /F | Out-Null
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "Frontend و Backend متوقف شدند." -ForegroundColor Green
