$ErrorActionPreference = "Stop"

if (-not (Test-Path "node_modules")) {
    Write-Host "وابستگی‌ها نصب نشده‌اند؛ npm install اجرا می‌شود." -ForegroundColor Yellow
    npm install
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

npm run dev
