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
import re
import random

tracemalloc.start()

# Глобальные переменные
global_token = None

# Создаем StatesGroup для управления состоянием
class BonusState(StatesGroup):
    SelectUser = State()
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
    message_text = ("Привет\! Здесь ты можешь изменить количество бонусов у любого студента\.\n"
                    "Для этого введи его фамилию \(с большой или маленькой буквы не имеет значения\)\, "
                    "а затем нажимай на кнопки чтобы изменить количество бонусов\.")
    print(message.chat.id, 'Только что прожал /start')
    await bot.send_message(message.chat.id, message_text, parse_mode="MarkdownV2")
    await message.delete()
    await state.finish()

# Обработчик ввода имени пользователя
@dp.message_handler(lambda message: message.text and re.match(r'^[А-Яа-я]+$', message.text), state="*")
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
                            keyboard = InlineKeyboardMarkup(row_width=1)
                            for item in items:
                                name = item.get('name')
                                balance_bonus = item.get('balance_bonus')
                                button = InlineKeyboardButton(f"{name} - Баланс: {balance_bonus}", callback_data=f'select_user_{item["id"]}')
                                keyboard.add(button)

                            sent_message = await bot.send_message(
                                message.chat.id,
                                f"Выберите пользователя с фамилией '{user_name}':",
                                reply_markup=keyboard
                            )
                            print(user_name, 'здесь ввели фамилию')
                            await state.update_data(items=items, message_id=sent_message.message_id)  # Сохраняем данные о пользователях и ID сообщения в состоянии
                        else:
                            await message.reply(f"Студент с фамилией '{user_name}' не найден.")
                    else:
                        await message.reply("Произошла ошибка при получении информации о студенте.")
        except aiohttp.ClientError:
            await message.reply("Не удалось подключиться к AlfaCRM API.")
    else:
        await bot.send_message(message.chat.id, text="У тебя нет прав)))")

# Обработчик callback-кнопок для выбора пользователя
@dp.callback_query_handler(lambda c: c.data.startswith('select_user_'), state="*")
async def select_user(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.data.split('_')[2]
    
    # Получаем данные о пользователе из состояния
    data = await state.get_data()
    items = data.get('items', [])

    # Находим пользователя в списке items
    selected_user = next((item for item in items if item['id'] == int(user_id)), None)
    
    if selected_user:
        # Получаем актуальное количество бонусов пользователя
        balance_bonus = selected_user.get('balance_bonus', 0)
        
        # Обновляем данные состояния, включая 'balance_bonus'
        await state.update_data(user_id=user_id, balance_bonus=balance_bonus)
        
        # Переходим к следующему шагу
        await BonusState.InputCustom.set()
        
        # Вызываем функцию process_bonus_operation с bonus_change = 0,
        # чтобы показать текущий баланс бонусов
        await process_bonus_operation(callback_query, state, 0)



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
    user_id = data.get('user_id')
    items = data.get('items', [])
    current_balance_bonus = data.get('balance_bonus', 0)
    changed_balance_bonus = current_balance_bonus + bonus_change

    # Находим пользователя в списке items
    selected_user = next((item for item in items if item['id'] == int(user_id)), None)
    if selected_user:
        user_name = selected_user.get('name')
        print(user_name, 'кого он выбрал')
        # Обновляем текст существующего сообщения
        await bot.edit_message_text(
            chat_id=callback_query.from_user.id,
            message_id=data['message_id'],
            text=f"ID: {user_id}\nИмя: {user_name}\nБаланс бонусов: {changed_balance_bonus}",
            reply_markup=create_inline_keyboard()   
        )
    else:
        await bot.send_message(callback_query.from_user.id, "Ошибка: не удалось найти информацию о пользователе.")

    # Сохраняем измененное количество бонусов в контексте состояния
    await state.update_data(balance_bonus=changed_balance_bonus)


# Обработчик кнопки подтверждения
@dp.callback_query_handler(lambda c: c.data == 'confirm', state=BonusState.InputCustom)
async def process_confirm_button(callback_query: types.CallbackQuery, state: FSMContext):
    global global_token
    # Получаем данные из контекста состояния
    data = await state.get_data()
    user_id = data.get('user_id')
    changed_balance_bonus = data.get('balance_bonus', 0)
    print(changed_balance_bonus, 'это сколько у него теперь бонусов')
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

@dp.message_handler(Command("dontgiveup"), state="*")
async def cmd_dontgiveup(message: types.Message, state: FSMContext):
    motivational_phrases = [
        "Не сдавайся! Ты сильнее, чем думаешь.",
        "Трудности – это лишь временные испытания. Ты справишься!",
        "Каждая неудача – это шанс стать сильнее.",
        "Сегодня – первый день оставшейся части твоей жизни. Делай его значимым!",
        "Ты можешь достичь всего, что захочешь. Верь в себя!",
        "Будь настойчивым, и твои мечты сбудутся.",
        "Не бойся идти вперёд. Большинство великих достижений начинаются с первого шага.",
        "Твои возможности бесконечны. Только ты решаешь, куда направить свой путь.",
        "Сложности — это лишь препятствия на пути к успеху.",
        "Ты уникален и способен на великие вещи. Верь в себя!",
        "Даже самый долгий путь начинается с первого шага. Постарайся!",
        "Сделай сегодня лучше, чем вчера, и завтра будет лучше, чем сегодня.",
        "Помни, что ты можешь преодолеть любые трудности. Ты сильнее, чем кажешься.",
        "Верь в свои силы, и всё будет возможно.",
        "Успех приходит к тем, кто не боится провалов. Просто продолжай двигаться вперёд.",
        "Твои возможности неограничены. Ограничения существуют только в твоем воображении.",
        "Не забывай, что каждый день — это новый шанс быть лучше, чем вчера.",
        "Ты силен, умён и способен на многое. Поверь в себя!",
        "Будь смелым. Будь уникальным. Будь тем, кем ты хочешь быть.",
        "Ты можешь изменить свою жизнь. Просто начни действовать прямо сейчас.",
        "Трудности — это временные испытания. Не позволяй им определить твой путь.",
        "Твоя уверенность — ключ к успеху. Верь в свои силы!",
        "Будь настойчивым, и твои мечты сбудутся.",
        "Ты умнее, сильнее и креативнее, чем ты думаешь. Дай себе шанс!",
        "Возможности всегда рядом. Просто открой глаза и поверь в свой потенциал.",
        "Ты уникален и способен на великие вещи. Верь в себя и свой путь.",
    ]

    vids = [
        "немного мотивасьёна.mp4",
        "немного мотивасьёна 2.mp4",
        "немного мотивасьёна 3.mp4",
        "немного мотивасьёна 4.mp4",
        "немного мотивасьёна 5.mp4",
        "немного мотивасьёна 6.mp4",
        "немного мотивасьёна 7.mp4"
    ]

    selected_phrase = random.choice(motivational_phrases)
    random_vids = random.choice(vids)
    await bot.send_message(message.chat.id, selected_phrase)
    await bot.send_video(message.chat.id, open(random_vids, 'rb'))

    await state.finish()

# Обработчик всех текстовых сообщений, не подходящих под другие обработчики
@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_other_messages(message: types.Message):
    await message.reply("Буквы какие-то, я тупая заскриптованая машина, а ты хочешь общения как с человеком...\n"
                        "Нажми еще раз на /start чтобы узнать что я могу сделать для тебя и в этот раз прочитай повнимательнее\n"
                        "Но если реально что-то не так напиши - https://t.me/Lunatuks")
    
@dp.message_handler(content_types=types.ContentType.VIDEO)
async def handle_other_messages(message: types.Message):
    await message.reply("Зачем мне твои видео?\n"
                        "Я все равно не смогу их просмотреть, лучше отправь это моему создателю - https://t.me/Lunatuks")
    
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_other_messages(message: types.Message):
    await message.reply("Неплохо, но я не ценитель такого\n"
                        "Лучше отправь это моему создателю - https://t.me/Lunatuks")
    
@dp.message_handler(content_types=types.ContentType.AUDIO)
async def handle_other_messages(message: types.Message):
    await message.reply("Норм тречок, я себе добавлю")

    


async def main():
    asyncio.create_task(update_token_periodically())

    # Установка обработчиков
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    dp.register_message_handler(handle_user_id, lambda message: message.text and re.match(r'^[А-Яа-я]+$', message.text), state="*")
    dp.register_callback_query_handler(select_user, lambda c: c.data.startswith('select_user_'), state="*")
    dp.register_callback_query_handler(process_add_button, lambda c: c.data.startswith('add_'), state=BonusState.InputCustom)
    dp.register_callback_query_handler(process_subtract_button, lambda c: c.data.startswith('subtract_'), state=BonusState.InputCustom)
    dp.register_callback_query_handler(process_input_custom_button, lambda c: c.data == 'input_custom', state=BonusState.InputCustom)
    dp.register_callback_query_handler(process_confirm_button, lambda c: c.data == 'confirm', state=BonusState.InputCustom)
    dp.register_message_handler(handle_other_messages, content_types=types.ContentType.TEXT)
    
    # Запуск бота
    await dp.start_polling()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
