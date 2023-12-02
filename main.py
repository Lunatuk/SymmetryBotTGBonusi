import tracemalloc
from aiogram import types
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.dispatcher.filters import Command, Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import config
import asyncio
import aiohttp
import json
import logging
import os

tracemalloc.start()

# Глобальные переменные
global_token = None
# Создаем StatesGroup для управления состоянием
class BonusState(StatesGroup):
    InputCustom = State()

# Функция для создания инлайн-клавиатуры
def create_inline_keyboard():
    update_balance_bonus = [
        [InlineKeyboardButton("+50", callback_data='add_50'),
         InlineKeyboardButton("+100", callback_data='add_100'),
         InlineKeyboardButton("+150", callback_data='add_150')],
        [InlineKeyboardButton("-50", callback_data='subtract_50'),
         InlineKeyboardButton("-100", callback_data='subtract_100'),
         InlineKeyboardButton("-150", callback_data='subtract_150')],
        # [InlineKeyboardButton("Ввести свое число", callback_data='input_custom')],
        [InlineKeyboardButton("Подтвердить", callback_data='confirm')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=update_balance_bonus)

admins = [
    1267549654,
    512569038,
    920254121,
    5460153008
]

async def get_token():
    global global_token
    url = "https://symmetry.s20.online/v2api/auth/login"
    payload = {
        "email": config.EMAIL,
        "api_key": config.API_KEY
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                token = data["token"]
                global_token = token
                return token
            else:
                print("Error:", response.status)
                return None

async def update_token_periodically():
    while True:
        token = await get_token()
        if token:
            print("Received token:", token)
        await asyncio.sleep(900)  # 900 секунд = 15 минут


# Создаем экземпляры бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


@dp.message_handler(Command("start"), state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    message_text = "*Привет\\!* Здесь ты можешь *изменить колличество бонусов* у любого студента\\.\nДля этого *введи его фамилию и имя* *\\(с большой или маленькой буквы не имеет значения\\)*\\, а затем *нажимай на кнопки* чтобы изменить количество баллов\\."
    await bot.send_message(message.chat.id, message_text, parse_mode="MarkdownV2")
    await message.delete()
    await state.finish()


# Обработчик ввода имени пользователя
@dp.message_handler(lambda message: message.text and len(message.text.split()) == 2, state="*")
async def handle_user_id(message: types.Message, state: FSMContext):
    if message.chat.id in admins:
        global global_token
        user_name = message.text
        url = 'https://symmetry.s20.online/v2api/1/customer/index'
        payload = {'name': user_name}
        headers = {'Content-Type': 'application/json', 'X-ALFACRM-TOKEN': global_token}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        customer_info = await response.json()
                        items = customer_info.get('items', [])

                        if items:
                            for item in items:
                                name = item.get('name')
                                balance_bonus = item.get('balance_bonus')
                                user_id = item.get('id')
                                # Сохраняем ID пользователя и balance_bonus в контексте состояния
                                await state.update_data(user_id=user_id, name=name, balance_bonus=balance_bonus)
                                # Отправляем сообщение с запросом на ввод пользовательского числа
                                sent_message = await bot.send_message(
                                    message.from_user.id,
                                    f"ID: {user_id}\nИмя: {name}\nБаланс бонусов: {balance_bonus}",
                                    reply_markup=create_inline_keyboard()
                                )
                                # Сохраняем ID сообщения в контексте состояния
                                await state.update_data(message_id=sent_message.message_id)
                                # Переключаем состояние пользователя
                                await BonusState.InputCustom.set()
                        else:
                            await message.reply(f"Студент с именем {user_name} не найден.")
                    else:
                        await message.reply("Произошла ошибка при получении информации о студенте.")
        except aiohttp.ClientError:
            await message.reply("Не удалось подключиться к AlfaCRM API.")
    else:
        await bot.send_message(message.chat.id, text=f"У тебя нет прав)))")
        

# Обработчики callback-кнопок
@dp.callback_query_handler(lambda c: c.data.startswith('add_'), state=BonusState.InputCustom)
async def process_add_button(callback_query: types.CallbackQuery, state: FSMContext):
    bonus_to_add = int(callback_query.data.split('_')[1])
    await process_bonus_operation(callback_query, state, bonus_to_add)

@dp.callback_query_handler(lambda c: c.data.startswith('subtract_'), state=BonusState.InputCustom)
async def process_subtract_button(callback_query: types.CallbackQuery, state: FSMContext):
    bonus_to_subtract = int(callback_query.data.split('_')[1])
    await process_bonus_operation(callback_query, state, -bonus_to_subtract)

@dp.callback_query_handler(lambda c: c.data == 'input_custom', state=BonusState.InputCustom)
async def process_input_custom_button(callback_query: types.CallbackQuery, state: FSMContext):
    # Отправляем сообщение с запросом на ввод пользовательского числа
    sent_message = await bot.send_message(callback_query.from_user.id, "Введите свое число:")

    # Сохраняем ID сообщения в контексте состояния
    await state.update_data(message_id=sent_message.message_id)
    await BonusState.InputCustom.set()

async def process_bonus_operation(callback_query: types.CallbackQuery, state: FSMContext, bonus_change: int):
    # Получаем данные из контекста состояния
    data = await state.get_data()
    current_balance_bonus = data.get('balance_bonus', 0)
    changed_balance_bonus = current_balance_bonus + bonus_change

    # Сохраняем измененное количество бонусов в контексте состояния
    await state.update_data(balance_bonus=changed_balance_bonus)

    # Обновляем текст существующего сообщения
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=data['message_id'],
        text=f"ID: {data['user_id']}\nИмя: {data['name']}\nБаланс бонусов: {changed_balance_bonus}",
        reply_markup=create_inline_keyboard()
    )

# Обработчик кнопки подтверждения
@dp.callback_query_handler(lambda c: c.data == 'confirm', state=BonusState.InputCustom)
async def process_confirm_button(callback_query: types.CallbackQuery, state: FSMContext):
    global global_token
    # Получаем данные из контекста состояния
    data = await state.get_data()
    user_id = data.get('user_id')
    changed_balance_bonus = data.get('balance_bonus', 0)

    # Отправляем запрос на обновление бонусов с использованием aiohttp
    url = f'https://symmetry.s20.online/v2api/1/customer/update?id={user_id}'
    payload = {'balance_bonus': changed_balance_bonus}
    headers = {'Content-Type': 'application/json', 'X-ALFACRM-TOKEN': global_token}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    # Убираем инлайн-клавиатуру
                    await bot.edit_message_reply_markup(
                        chat_id=callback_query.from_user.id,
                        message_id=data['message_id']
                    )
                    await bot.send_message(
                        chat_id=callback_query.from_user.id,
                        text=f"Бонусы успешно обновлены!\nБаланс бонусов после изменения: {changed_balance_bonus}"
                    )
                else:
                    await bot.send_message(callback_query.from_user.id, "Произошла ошибка при обновлении бонусов.")
    except aiohttp.ClientError:
        await bot.send_message(callback_query.from_user.id, "Не удалось подключиться к AlfaCRM API.")

    # Сбрасываем состояние пользователя
    await state.finish()


# Обработчик всех текстовых сообщений, не подходящих под другие обработчики
@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_other_messages(message: types.Message):
    await message.reply("То, что ты ввел не прописано в моей программе.\nНажми еще раз на /start чтобы узнать что я могу сделать для тебя.")

async def main():
    asyncio.create_task(update_token_periodically())
    await dp.start_polling()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()

