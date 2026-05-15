# Нагрузочное тестирование (Apache JMeter)

1. Запусти backend: `python backend/app.py` или `uvicorn backend.app:app --host 0.0.0.0 --port 8000` из корня репозитория.
2. Открой в JMeter файл `dating_smoke.jmx`.
3. При необходимости измени host/port в сэмплерах (по умолчанию `localhost:8000`).
4. **Run** → смотри Summary Report / Aggregate Report.

Базовый план бьёт по публичным эндпоинтам `/health` и `/metrics`. Для сценариев с телом (`POST /user/register` и т.д.) добавь JSON Body и **не** используй продовый токен бота в репозитории.
