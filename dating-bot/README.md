# Dating Bot — этапы 1-4

Проект доведен до полноценного демо формата под практику: есть архитектура, работающий Telegram-бот, система анкет и ранжирования, кэш Redis, отложенные задачи через Celery, метрики и базовые тесты.

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
- Регистрация пользователя по `/start` через Telegram ID.
- Пошаговое создание анкеты (FSM) с валидацией.
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
- Алгоритм ранжирования (по минимуму из каждого уровня):
  1. **Primary**: полнота анкеты + бонус за фото + матч по пользовательским предпочтениям.
  2. **Behavioral**: лайк/скип соотношение + признаки взаимности + активность.
  3. **Combined**: весовая модель `0.6 * primary + 0.4 * behavioral`.
- Redis-кэширование выдачи:
  - очередь из 10 кандидатов на пользователя
  - автоматическая догрузка при исчерпании
  - ручная очистка через `POST /matching/refresh/{telegram_id}`

### Этап 4. Дополнительные функции
- **Celery**:
  - `recalculate_all_ratings_task` — периодический пересчет рейтингов (каждые 10 минут через beat).
  - таблица `profile_ratings` для истории пересчетов.
- **Оптимизация БД**:
  - индексы + актуализация `last_active_at`.
- **Метрики и логирование**:
  - Prometheus-метрики `GET /metrics` (RPS и latency по endpoint).
  - структурные логи backend.
- **Тестирование**:
  - smoke-тесты API в `backend/test_api.py`.

---

## Структура

```text
dating-bot/
├── bot/
│   └── bot.py
├── backend/
│   ├── app.py
│   ├── ranking.py
│   ├── cache.py
│   ├── tasks.py
│   ├── seed_mock_data.py
│   └── test_api.py
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

2) Убедиться, что Redis запущен (`redis://localhost:6379/0`).

3) Запустить backend:

```powershell
python backend/app.py
```

4) Запустить Telegram-бота:

```powershell
python bot/bot.py
```

5) Запустить Celery worker:

```powershell
celery -A backend.tasks.celery_app worker --loglevel=info
```

6) Запустить Celery beat (в отдельном терминале):

```powershell
celery -A backend.tasks.celery_app beat --loglevel=info
```

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

В `.env` должны быть:

```env
BOT_TOKEN=...
DATABASE_URL=sqlite+aiosqlite:///dating_bot.db
REDIS_URL=redis://localhost:6379/0
```
