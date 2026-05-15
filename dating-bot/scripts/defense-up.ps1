# Запуск полного стека для защиты (Windows / PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path ".env")) {
    Write-Host "Создай файл .env из .env.example и укажи BOT_TOKEN." -ForegroundColor Yellow
    exit 1
}

docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Готово. Проверь: http://127.0.0.1:8000/health" -ForegroundColor Green
Write-Host "RabbitMQ UI: http://127.0.0.1:15672 (guest/guest)"
Write-Host "MinIO UI:    http://127.0.0.1:9001 (minioadmin/minioadmin)"
Write-Host ""
Write-Host "Мок-данные (опционально): docker compose exec backend python backend/seed_mock_data.py"
