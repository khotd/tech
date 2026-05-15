# Dating Bot — этапы 1-4

**Чеклист для защиты:** [ЗАЩИТА.md](ЗАЩИТА.md) · **Запуск одной командой (Docker):** в корне выполни `powershell -ExecutionPolicy Bypass -File .\go.ps1`

Проект доведен до полноценного демо под практику и систему оценивания: бот, API, ранжирование по уровням ТЗ, Redis, Celery, RabbitMQ (события), MinIO (S3), метрики, CI, JMeter-план, Docker Compose.

## Что реализовано по этапам

### Этап 1. Планирование и проектирование
- Выделены 2 сервиса: `bot` (интерфейс пользователя) и `backend` (бизнес-логика + API).
- Спроектирована модель данных: `users`, `profiles`, `photos`, `likes`, `profile_ratings`.
- Добавлены индексы для ускорения матчинг-запросов:
  - `profiles(is_active, rating_score DESC)`
  - `likes(from_id, to_id, action)`
- В `startup` backend выполняется проверка/добавление новых колонок (совместимость со старой БД без ручной миграции).

### Этап 2. Базовая функциональность
- Telegram-бот на `aiogram 3`.
- Регистрация по `/start` через Telegram ID, **реферальная ссылка** `https://t.me/<bot>?start=<код>` (код выдаётся после регистрации).
- Пошаговое создание анкеты (FSM): имя, возраст, пол, город, **город для поиска пары**, описание, **интересы через запятую**, фото.
- UX в стиле Дайвинчика:
  - reply-меню: `💘 Смотреть анкеты`, `📝 Моя анкета`, `📷 Добавить фото`, `🔄 Обновить выдачу`
  - inline-кнопки в выдаче: `💚 Лайк`, `👎 Скип`, `⏸ Пауза`
  - загрузка фото в анкету прямо из Telegram (по `file_id`)
  - перелистывание фото в карточке анкеты (`⬅️`/`➡️`)
  - раздел `Моя анкета` с выводом текущих данных и кнопками обновления имени/возраста/описания/фото
  - удаление фото из `Моя анкета` по кнопке

### Этап 3. Анкеты и ранжирование
- CRUD по анкете:
  - `POST /profile/create`
  - `GET /profile/{user_id}`
  - `PUT /profile/{user_id}`
  - `DELETE /profile/{user_id}`
  - `POST /profile/photo/upload`
- Алгоритм ранжирования по уровням из «Практики»:
  1. **Primary**: полнота, фото, предпочтения (пол, возраст, **город пары**), **пересечение интересов**.
  2. **Behavioral**: лайки/скипы, взаимные лайки, диалоги после мэтча, активность, **бонус за время суток последней активности**.
  3. **Combined**: `0.6 * primary + 0.4 * behavioral` + **бонус за рефералов / приглашение по коду**.
- Redis-кэширование выдачи:
  - очередь из 10 кандидатов на пользователя
  - автоматическая догрузка при исчерпании
  - ручная очистка через `POST /matching/refresh/{telegram_id}`

### Этап 4. Дополнительные функции
- **RabbitMQ**: события `user_registered`, `profile_upsert`, `like`, `skip`, `match`, `photo_*`, `matching_refresh` (см. `backend/rabbit_events.py`). Потребитель: `python -m backend.event_consumer` из корня репозитория.
- **MinIO (S3)**: при `USE_MINIO=true` фото скачиваются из Telegram Bot API и кладутся в бакет; в БД хранится URL и `telegram_file_id` для показа в Telegram.
- **Celery** (брокер Redis, как и раньше):
  - `recalculate_all_ratings_task` — периодический пересчет рейтингов (каждые 10 минут через beat).
  - таблица `profile_ratings` для истории пересчетов.
- **Оптимизация БД**:
  - индексы + актуализация `last_active_at`, при мэтче увеличивается `dialogs_started`.
- **Метрики и логирование**:
  - Prometheus `GET /metrics`, middleware latency, логи backend.
- **CI/CD**: GitHub Actions `.github/workflows/ci.yml` — `pytest backend/test_api.py`.
- **Нагрузка**: `load_tests/dating_smoke.jmx` + инструкция `load_tests/README.md`.
- **Инфраструктура**: `docker-compose.yml` (Redis + RabbitMQ + MinIO).
- **Тестирование**: `backend/test_api.py`.

---

## Структура

```text
dating-bot/
├── ЗАЩИТА.md
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci.yml
├── scripts/defense-up.ps1
├── bot/bot.py
├── backend/
│   ├── app.py
│   ├── ranking.py
│   ├── cache.py
│   ├── tasks.py
│   ├── rabbit_events.py
│   ├── minio_storage.py
│   ├── event_consumer.py
│   ├── seed_mock_data.py
│   └── test_api.py
├── load_tests/dating_smoke.jmx
├── models.py
├── config.py
├── requirements.txt
└── README.md
```

## Быстрый запуск (локально)

1) Установить зависимости:

```powershell
pip install -r requirements.txt
```

2) Поднять Redis, RabbitMQ и MinIO (проще одной командой):

```powershell
docker compose up -d
```

Создай бакет `dating-photos` в консоли MinIO: http://127.0.0.1:9001 (логин/пароль `minioadmin` / `minioadmin` по умолчанию из compose).

3) Скопируй `.env.example` в `.env`, задай `BOT_TOKEN`. Для загрузки фото в MinIO: `USE_MINIO=true` и убедись, что backend может достучаться до MinIO (`MINIO_ENDPOINT`).

4) Запустить backend:

```powershell
python backend/app.py
```

5) Запустить Telegram-бота:

```powershell
python bot/bot.py
```

6) Запустить Celery worker:

```powershell
celery -A backend.tasks.celery_app worker --loglevel=info
```

7) Запустить Celery beat (в отдельном терминале):

```powershell
celery -A backend.tasks.celery_app beat --loglevel=info
```

8) (Опционально) Потребитель событий RabbitMQ:

```powershell
python -m backend.event_consumer
```

### Полный стек в Docker (рекомендуется на защиту)

Из корня (нужен `.env` с `BOT_TOKEN`):

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1
```

Поднимаются Postgres, Redis, RabbitMQ, MinIO, API, Celery, consumer. **Бот запускается отдельным окном на Windows** (так стабильно с Telegram). Подробности — в [ЗАЩИТА.md](ЗАЩИТА.md).

## Проверки

- Healthcheck backend: `GET /health`
- Метрики: `GET /metrics`
- Ручная проверка бота:
  - `/start` -> заполнить анкету
  - `📷 Добавить фото` -> отправить фото в чат
  - `💘 Смотреть анкеты` -> ставить лайки/скипы
  - проверить взаимный лайк и сообщение о мэтче

## Тесты

```powershell
pytest backend/test_api.py -q
```

## Переменные окружения

В `.env` (см. `.env.example`):

```env
BOT_TOKEN=...
DATABASE_URL=sqlite+aiosqlite:///dating_bot.db
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@127.0.0.1:5672/
RABBITMQ_QUEUE=dating.events
USE_MINIO=false
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=dating-photos
MINIO_SECURE=false
MINIO_PUBLIC_BASE=
```
