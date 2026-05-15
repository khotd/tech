import aiohttp
import asyncio

async def test():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://api.telegram.org') as resp:
                print(f'Telegram API: {resp.status}')
        except Exception as e:
            print(f'Ошибка: {e}')

asyncio.run(test())
