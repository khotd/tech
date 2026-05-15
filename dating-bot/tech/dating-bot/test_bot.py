import asyncio
from aiogram import Bot

BOT_TOKEN = '8654697351:AAEIJBut_WSFyNmspIdtI5wXGyJyQGJCilo'

async def test():
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
