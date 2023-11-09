import requests
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
# from aiogram.contrib.middlewares import ThrottlingMiddleware
import config
import time
import asyncio
import json

global_token = None


async def get_token():
    global global_token
    url = "https://symmetry.s20.online/v2api/auth/login"
    payload = {
        "email": config.EMAIL,
        "api_key": config.API_KEY
    }
    response = await loop.run_in_executor(None, lambda: requests.post(url, json=payload))
    if response.status_code == 200:
        data = response.json()
        token = data["token"]
        global_token = token
        return token
    else:
        print("Error:", response.status_code)
        return None

async def update_token_periodically():
    while True:
        token = await get_token()
        if token:
            print("Received token:", token)
        await asyncio.sleep(300)  # 900 секунд = 15 минут

# Создаем экземпляры бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
# dp.middleware.setup(ThrottlingMiddleware())

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    user_name = message.from_user.first_name
    await bot.send_message(message.chat.id, text=f"Ну привет {user_name}\nВведи команду /user_info или просто любой id юзера в чат")
    await message.delete()


@dp.message_handler(commands=['user_info'])
async def get_user_info(message: types.Message):
    await message.reply("Введите ID клиента:")

import tracemalloc
tracemalloc.start()
@dp.message_handler(regexp=r"^\d+$")
async def handle_user_id(message: types.Message):
    global global_token
    user_id = message.text

    url = 'https://symmetry.s20.online/v2api/1/customer/index'
    payload = {'id': user_id}
    headers = {'Content-Type': 'application/json', 'X-ALFACRM-TOKEN': global_token}

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            customer_info = response.json()
            items = customer_info.get('items', [])

            if items:
                for item in items:
                    name = item.get('name')
                    balance_bonus = item.get('balance_bonus')
                    await message.reply(f"Имя: {name}\nБаланс бонусов: {balance_bonus}")
            else:
                await message.reply(f"Клиент с ID {user_id} не найден.")
        else:
            await message.reply("Произошла ошибка при получении информации о клиенте.")
    except requests.RequestException:
        await message.reply("Не удалось подключиться к AlfaCRM API.")
snapshot = tracemalloc.take_snapshot()
tracemalloc.stop()

async def main():
    # your previous code comes here...
    asyncio.create_task(update_token_periodically())
    await dp.start_polling()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    asyncio.run(main())