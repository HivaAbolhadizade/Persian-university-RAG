param(
    [switch]$SkipInstall,
    [switch]$SetupOnly,
    [switch]$BackendOnly,
    [switch]$RunTests,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$StartupTimeoutSeconds = 240
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$RuntimeDir = Join-Path $ProjectRoot "data\backend_runtime"
$PidFile = Join-Path $RuntimeDir "project_processes.json"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-Port([int]$Port) {
    try {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return $null -ne $connection
    } catch {
        return $false
    }
}

function Wait-Url([string]$Url, [int]$TimeoutSeconds, [string]$Name) {
    $started = Get-Date
    while (((Get-Date) - $started).TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$Name آماده شد: $Url" -ForegroundColor Green
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Host "$Name در زمان تعیین‌شده آماده نشد: $Url" -ForegroundColor Yellow
    return $false
}

Write-Step "بررسی ساختار پروژه"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $ProjectRoot "requirements.txt"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$FrontendPackage = Join-Path $FrontendDir "package.json"

if (-not (Test-Path $PythonExe)) {
    throw "محیط .venv پیدا نشد. از ریشه پروژه اجرا کنید: py -m venv .venv"
}
if (-not (Test-Path $Requirements)) {
    throw "فایل requirements.txt پیدا نشد."
}
if (-not $SetupOnly -and -not $BackendOnly) {
    if (-not (Test-Path $FrontendPackage)) { throw "فایل frontend\package.json پیدا نشد." }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm پیدا نشد. ابتدا Node.js را نصب کنید." }
}

Write-Step "بررسی تنظیمات"
$BackendEnv = Join-Path $ProjectRoot ".env"
$BackendEnvExample = Join-Path $ProjectRoot ".env.example"
if (-not (Test-Path $BackendEnv) -and (Test-Path $BackendEnvExample)) {
    Copy-Item $BackendEnvExample $BackendEnv
    Write-Host ".env از روی نمونه ساخته شد؛ کلید واقعی را فقط در سیستم خودتان وارد کنید." -ForegroundColor Green
}

if (-not $SetupOnly -and -not $BackendOnly) {
    $FrontendEnvLocal = Join-Path $FrontendDir ".env.local"
    $RequiredFrontendEnv = "VITE_API_BASE_URL=http://127.0.0.1:$BackendPort"
    if (-not (Test-Path $FrontendEnvLocal)) {
        @"
$RequiredFrontendEnv
VITE_USE_MOCK_FALLBACK=false
"@ | Set-Content -Path $FrontendEnvLocal -Encoding UTF8
        Write-Host "frontend\.env.local ساخته شد." -ForegroundColor Green
    } else {
        $FrontendEnvContent = Get-Content $FrontendEnvLocal -Raw
        if ($FrontendEnvContent -notmatch "(?m)^VITE_API_BASE_URL=") {
            Add-Content -Path $FrontendEnvLocal -Value "`n$RequiredFrontendEnv"
        }
    }
}

if (-not $SkipInstall) {
    Write-Step "نصب یا بررسی وابستگی‌های Python"
    & $PythonExe -m pip install -r $Requirements --upgrade-strategy only-if-needed
    if ($LASTEXITCODE -ne 0) { throw "نصب وابستگی‌های Python ناموفق بود." }

    if (-not $SetupOnly -and -not $BackendOnly) {
        Write-Step "بررسی وابستگی‌های Frontend"
        $NodeModules = Join-Path $FrontendDir "node_modules"
        if (-not (Test-Path $NodeModules)) {
            Push-Location $FrontendDir
            try {
                npm install
                if ($LASTEXITCODE -ne 0) { throw "npm install ناموفق بود." }
            } finally { Pop-Location }
        } else {
            Write-Host "node_modules از قبل موجود است." -ForegroundColor Green
        }
    }
}

if ($RunTests) {
    Write-Step "اجرای تست‌های Backend"
    & $PythonExe -m pytest backend\tests -q
    if ($LASTEXITCODE -ne 0) { throw "تست‌های Backend ناموفق بود." }
}

if ($SetupOnly) {
    Write-Host "`nآماده‌سازی پروژه کامل شد." -ForegroundColor Green
    exit 0
}

if (Test-Port $BackendPort) { throw "پورت Backend یعنی $BackendPort از قبل در حال استفاده است." }
if (-not $BackendOnly -and (Test-Port $FrontendPort)) { throw "پورت Frontend یعنی $FrontendPort از قبل در حال استفاده است." }

Write-Step "اجرای Backend"
$BackendCommand = @"
Set-Location '$ProjectRoot'
& '$PythonExe' -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $BackendPort
"@
$BackendProcess = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $BackendCommand) -WorkingDirectory $ProjectRoot -PassThru
Write-Host "Backend process started. PID: $($BackendProcess.Id)" -ForegroundColor Green

$FrontendProcess = $null
if (-not $BackendOnly) {
    Write-Step "اجرای Frontend"
    $FrontendCommand = @"
Set-Location '$FrontendDir'
npm run dev -- --host 127.0.0.1 --port $FrontendPort
"@
    $FrontendProcess = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $FrontendCommand) -WorkingDirectory $FrontendDir -PassThru
    Write-Host "Frontend process started. PID: $($FrontendProcess.Id)" -ForegroundColor Green
}

@{
    backend_shell_pid = $BackendProcess.Id
    frontend_shell_pid = if ($FrontendProcess) { $FrontendProcess.Id } else { $null }
    backend_port = $BackendPort
    frontend_port = if ($BackendOnly) { $null } else { $FrontendPort }
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8

Write-Step "انتظار برای آماده‌شدن سرویس‌ها"
$BackendReady = Wait-Url -Url "http://127.0.0.1:$BackendPort/api/health" -TimeoutSeconds $StartupTimeoutSeconds -Name "Backend"

if ($BackendOnly) {
    Write-Host "`nBackend اجرا شد: http://127.0.0.1:$BackendPort/docs" -ForegroundColor Green
    exit 0
}

$FrontendReady = Wait-Url -Url "http://127.0.0.1:$FrontendPort" -TimeoutSeconds 90 -Name "Frontend"
if ($FrontendReady) { Start-Process "http://127.0.0.1:$FrontendPort" }

Write-Host "`nپروژه اجرا شد." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Backend Docs: http://127.0.0.1:$BackendPort/docs"
Write-Host "برای بستن هر دو سرویس اجرا کنید: .\scripts\stop_project.ps1"
