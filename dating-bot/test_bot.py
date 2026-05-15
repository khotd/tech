import asyncio
import os
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

async def test():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не найден в .env")
        return
    bot = Bot(token=BOT_TOKEN)
    try:
        print("Подключение к Telegram...")
        me = await bot.get_me()
        print(f'Бот: @{me.username} - {me.first_name}')
        print(f'ID: {me.id}')
        print('✅ Токен работает!')
    except Exception as e:
        print(f'❌ Ошибка: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(test())
