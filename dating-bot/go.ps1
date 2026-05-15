# Запуск: Docker (API + БД + Redis + …) и бот на этом ПК (стабильно с Telegram).
#   powershell -ExecutionPolicy Bypass -File .\go.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "Нет файла .env — скопируй .env.example в .env и вставь BOT_TOKEN." -ForegroundColor Red
    exit 1
}

Write-Host "Останавливаю старый контейнер бота (если был)..." -ForegroundColor DarkGray
docker rm -f dating-bot-bot-1 2>$null | Out-Null

Write-Host "Поднимаю Docker: Postgres, Redis, RabbitMQ, MinIO, API, Celery, consumer..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ошибка docker compose. Запусти Docker Desktop." -ForegroundColor Red
    exit $LASTEXITCODE
}

Start-Sleep -Seconds 4
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 20
    Write-Host "API: $($h | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "API не ответил — подожди 30 с и открой http://127.0.0.1:8000/health" -ForegroundColor Yellow
}

$py = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py -3" }
    else {
        Write-Host "Не найден Python. Установи 3.12+ с python.org" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Запускаю бота на этом компьютере (отдельное окно)..." -ForegroundColor Cyan
$inner = "Set-Location `"$PSScriptRoot`"; `$env:API_BASE='http://127.0.0.1:8000'; $py bot/bot.py"
Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $inner)

Write-Host ""
Write-Host "Готово. В новом окне идёт бот — в Telegram нажми /start" -ForegroundColor Green
Write-Host "Стоп Docker: docker compose down   (окно с ботом закрой вручную)"
