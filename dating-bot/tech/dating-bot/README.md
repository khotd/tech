# Dating Bot — Этап 2: Разработка базовой функциональности

## ✅ Выполнено

- [x] Bot Service на aiogram (Telegram бот)
- [x] Команда `/start` — регистрация пользователя
- [x] Backend API на FastAPI
- [x] Регистрация по telegram_id
- [x] Модели БД (Users, Profiles, Photos, Likes, RatingLogs)
- [x] Главная клавиатура с кнопками
- [x] Тестирование работы

## 📁 Структура проекта

```
dating-bot/
├── bot/
│   └── bot.py          # Telegram бот (aiogram)
├── backend/
│   └── app.py          # FastAPI API
├── models.py           # SQLAlchemy модели
├── database.py         # Настройка БД
├── config.py           # Конфигурация
├── .env                # Переменные окружения
├── requirements.txt    # Зависимости
└── README.md           # Документация
```

## 🏗 Архитектура

Соответствует схеме из `tech/архитектура.png`:

## 🚀 Запуск

### 1. Установи зависимости:
```bash
cd C:\Users\User\Desktop\dating-bot
pip install -r requirements.txt
```

### 2. Запускаем Backend (терминал 1):
```bash
cd backend
python app.py
```

### 3. Запускаем бота (терминал 2):
```bash
python bot/bot.py
```

## API Эндпоинты

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/health` | Проверка работоспособности |
| POST | `/user/register` | Регистрация пользователя |
| GET | `/user/{telegram_id}` | Получить пользователя |
| POST | `/profile/create` | Создать анкету |
| GET | `/profile/{user_id}` | Получить анкету |

## Бот команды

- `/start` — начать работу, регистрация
- `👤 Моя анкета` — просмотр профиля
- `❤️ Лайк` — лайкнуть (заготовка)
- `❌ Пропустить` — пропустить (заготовка)
- `📊 Рейтинг` — информация о рейтинге
