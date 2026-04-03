"""
Bot Service - Telegram бот на aiogram
Команды: /start, /next, /like
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import BOT_TOKEN
import aiohttp

# Включаем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище состояний
user_states = {}


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    kb = [
        [KeyboardButton(text="👤 Моя анкета")],
        [KeyboardButton(text="❤️ Лайк"), KeyboardButton(text="❌ Пропустить")],
        [KeyboardButton(text="📊 Рейтинг")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


async def register_user(telegram_id: int, username: str) -> dict:
    """Регистрация пользователя через Backend API"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "http://localhost:8000/user/register",
                json={"telegram_id": telegram_id, "username": username}
            ) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"Ошибка регистрации: {e}")
            return {"error": str(e)}


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    logger.info(f"Получен /start от {message.from_user.id}")
    
    telegram_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    result = await register_user(telegram_id, username)
    logger.info(f"Результат: {result}")
    
    if "error" in result:
        await message.answer("⚠️ Ошибка подключения к серверу.")
        return
    
    user_states[telegram_id] = {"user_id": result["user_id"]}
    
    if result.get("exists"):
        await message.answer(f"👋 С возвращением, {username}!", reply_markup=get_main_keyboard())
    else:
        await message.answer(
            f"👋 Привет, {username}!\nВаш ID: {telegram_id}\n\nЗаполните анкету!",
            reply_markup=get_main_keyboard()
        )


@dp.message(F.text == "👤 Моя анкета")
async def my_profile(message: types.Message):
    await message.answer("👤 Ваша анкета (в разработке)")


@dp.message(F.text == "❤️ Лайк")
async def like_action(message: types.Message):
    await message.answer("❤️ Лайк (в разработке)")


@dp.message(F.text == "❌ Пропустить")
async def skip_action(message: types.Message):
    await message.answer("❌ Пропущено (в разработке)")


@dp.message(F.text == "📊 Рейтинг")
async def rating_action(message: types.Message):
    await message.answer("📊 Рейтинг (в разработке)")


async def main():
    """Запуск бота"""
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("❌ Укажите BOT_TOKEN в файле .env")
        return
    
    logger.info("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
