$ErrorActionPreference = "Stop"

Write-Host "University RAG Frontend Setup" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js پیدا نشد." -ForegroundColor Red
    Write-Host "Node.js LTS را نصب کنید:" -ForegroundColor Yellow
    Write-Host "winget install --id OpenJS.NodeJS.LTS -e"
    exit 1
}

$nodeVersionText = node -p "process.versions.node"
$parts = $nodeVersionText.Split(".")
$major = [int]$parts[0]
$minor = [int]$parts[1]

$supported = (($major -eq 20 -and $minor -ge 19) -or ($major -eq 22 -and $minor -ge 12) -or ($major -ge 24))

if (-not $supported) {
    Write-Host "نسخه فعلی Node.js پشتیبانی نمی‌شود: v$nodeVersionText" -ForegroundColor Red
    Write-Host "برای این پروژه Node.js 20.19+، 22.12+ یا نسخه LTS جدیدتر لازم است." -ForegroundColor Yellow
    Write-Host "Node.js را ارتقا دهید و سپس PowerShell را کامل ببندید و دوباره باز کنید:" -ForegroundColor Yellow
    Write-Host "winget upgrade --id OpenJS.NodeJS.LTS -e"
    Write-Host "اگر winget نسخه نصب‌شده را پیدا نکرد:"
    Write-Host "winget install --id OpenJS.NodeJS.LTS -e"
    exit 1
}

Write-Host "Node: v$nodeVersionText" -ForegroundColor Green
Write-Host "npm : $(npm -v)" -ForegroundColor Green

npm config set registry https://registry.npmjs.org/

if (Test-Path "node_modules") {
    Write-Host "حذف node_modules قبلی..." -ForegroundColor Cyan
    Remove-Item -Recurse -Force "node_modules"
}

if (Test-Path "package-lock.json") {
    Write-Host "حذف package-lock.json قبلی..." -ForegroundColor Cyan
    Remove-Item -Force "package-lock.json"
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env ساخته شد." -ForegroundColor Green
}

Write-Host "در حال نصب وابستگی‌ها از registry.npmjs.org..." -ForegroundColor Cyan
npm install

Write-Host "Build آزمایشی..." -ForegroundColor Cyan
npm run build

Write-Host "همه چیز آماده است." -ForegroundColor Green
Write-Host "برای اجرا: npm run dev" -ForegroundColor Yellow
