import os
import logging
import asyncio
from dotenv import load_dotenv
from keep_alive import keep_alive

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command  # Используем фильтр для команд

# Загружаем переменные окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID"))

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Логирование
logging.basicConfig(level=logging.INFO)

# Клавиатуры
start_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Начать")]], resize_keyboard=True
)
city_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Калининград"),
            KeyboardButton(text="Калининградская область"),
            KeyboardButton(text="Другой город"),
        ]
    ],
    resize_keyboard=True,
)
role_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Физ лицо"), KeyboardButton(text="Юр лицо")]],
    resize_keyboard=True,
)
contact_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="В чате"), KeyboardButton(text="По телефону")]],
    resize_keyboard=True,
)
confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Подождать звонка"), KeyboardButton(text="Позвонить сразу")]
    ],
    resize_keyboard=True,
)

# Словарь для хранения данных пользователей
user_data = {}

# Классы состояний
class ConsultationState(StatesGroup):
    waiting_for_operator_reply = State()  # Ожидание ответа оператора (для связи в чате)

# Обработчик команды /start (с использованием фильтра Command)
@dp.message(Command("start", ignore_case=True))
async def start(message: types.Message):
    user_data[message.from_user.id] = {}
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Этот бот создан, чтобы помочь вам в решении юридических вопросов. 🏛️\n\n"
        "🔹 Просто оставьте заявку и укажите удобный способ связи.\n"
        "🔹 Наши специалисты рассмотрят ваш запрос и предложат оптимальное решение.\n\n"
        "📌 <b>Нажмите кнопку ниже, чтобы начать.</b>", 
        reply_markup=start_kb,
        parse_mode="HTML"
    )


# Первый шаг – выбор кнопки "Начать"
@dp.message(F.text == "Начать")
async def ask_city(message: types.Message):
    await message.answer("Из какого вы города?", reply_markup=city_kb)

# Выбор города
@dp.message(F.text.in_(["Калининград", "Калининградская область", "Другой город"]))
async def ask_role(message: types.Message):
    if message.from_user.id not in user_data:
        user_data[message.from_user.id] = {}
    user_data[message.from_user.id]["city"] = message.text
    await message.answer("Кем вы являетесь?", reply_markup=role_kb)

# Выбор статуса (физ.лицо / юр.лицо)
@dp.message(F.text.in_(["Физ лицо", "Юр лицо"]))
async def ask_contact_method(message: types.Message):
    if message.from_user.id not in user_data:
        user_data[message.from_user.id] = {}
    user_data[message.from_user.id]["role"] = message.text
    await message.answer("Как вам удобнее получить консультацию?", reply_markup=contact_kb)

# Выбор способа связи – в чате или по телефону
@dp.message(F.text.in_(["В чате", "По телефону"]))
async def ask_name(message: types.Message):
    user_data[message.from_user.id]["contact_method"] = message.text
    if user_data[message.from_user.id]["role"] == "Юр лицо":
        await message.answer("Напишите название вашей компании.")
    else:
        await message.answer("Как к вам обращаться?")

# Сохранение имени (или названия компании) и запрос дальнейшей информации
@dp.message(lambda m: m.from_user.id in user_data and "name" not in user_data[m.from_user.id])
async def ask_query(message: types.Message):
    user_data[message.from_user.id]["name"] = message.text
    await message.answer("Укажите ваш запрос или ситуацию, с которой вы обращаетесь.")

# Получение текста запроса и, в зависимости от выбранного способа связи, либо запрашиваем телефон, либо завершаем сбор данных
@dp.message(lambda m: m.from_user.id in user_data and "query" not in user_data[m.from_user.id])
async def ask_phone(message: types.Message, state: FSMContext):
    user_data[message.from_user.id]["query"] = message.text
    if user_data[message.from_user.id]["contact_method"] == "По телефону":
        await message.answer("Напишите ваш номер телефона.")
    else:
        # Если способ связи "В чате", номер телефона не требуется – завершаем сбор данных
        await confirm_contact(message, state, phone_input=False)

# Обработчик для ввода номера телефона (если выбран способ «По телефону»)
@dp.message(lambda m: m.from_user.id in user_data 
            and user_data[m.from_user.id].get("contact_method") == "По телефону"
            and "phone" not in user_data[m.from_user.id])
async def process_phone(message: types.Message, state: FSMContext):
    await confirm_contact(message, state, phone_input=True)

# Вспомогательная функция для финализации запроса и отправки сообщения в группу поддержки
async def confirm_contact(message: types.Message, state: FSMContext, phone_input: bool):
    if phone_input:
        user_data[message.from_user.id]["phone"] = message.text
    else:
        user_data[message.from_user.id]["phone"] = "—"

    user_info = user_data[message.from_user.id]
    phone = user_info["phone"]

    msg = (
        f"📢 Новый запрос на консультацию!\n\n"
        f"🏙 Город: {user_info.get('city', 'Не указан')}\n"
        f"👤 Статус: {user_info.get('role', 'Не указан')}\n"
        f"📞 Способ связи: {user_info.get('contact_method', 'Не указан')}\n"
        f"📛 Имя/Компания: {user_info.get('name', 'Не указано')}\n"
        f"📲 Телефон: {phone}\n"
        f"💬 Запрос: {user_info.get('query', 'Не указан')}\n"
        f"🆔 User ID: {message.from_user.id}"
    )

    if SUPPORT_GROUP_ID:
        await bot.send_message(SUPPORT_GROUP_ID, msg)

    if user_info["contact_method"] == "По телефону":
        await message.answer("С вами свяжутся в ближайшее время.", reply_markup=confirm_kb)
    else:
        await message.answer("Ожидайте, с вами свяжется оператор в чате.")
        # Переводим пользователя в состояние ожидания ответа оператора
        await state.set_state(ConsultationState.waiting_for_operator_reply)

# Обработчик для сообщений от пользователей, находящихся в состоянии ожидания ответа оператора (в чате)
@dp.message(ConsultationState.waiting_for_operator_reply)
async def handle_user_query(message: types.Message, state: FSMContext):
    user_info = user_data.get(message.from_user.id, {})
    # Если в тексте окажется команда /reply, убираем её
    cleaned_query = message.text.lstrip("/reply").strip()

    msg = (
        f"💬 Новый запрос в чате!\n\n"
        f"🏙 Город: {user_info.get('city', 'Не указан')}\n"
        f"👤 Статус: {user_info.get('role', 'Не указан')}\n"
        f"📛 Имя/Компания: {user_info.get('name', 'Не указано')}\n"
        f"💬 Запрос: {cleaned_query}\n"
        f"🆔 User ID: {message.from_user.id}"
    )

    if SUPPORT_GROUP_ID:
        await bot.send_message(SUPPORT_GROUP_ID, msg)

    await message.answer("Ожидайте, оператор скоро ответит.")
    # После отправки запроса можно сбросить состояние
    await state.clear()

# Обработчик для оператора, позволяющий ответить пользователю через команду /reply
@dp.message(Command("reply", ignore_case=True))
async def operator_reply(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Используйте формат: /reply user_id текст")
        return
    try:
        user_id = int(args[1])
        response_text = args[2]
        await bot.send_message(
            user_id,
            f"✉️ *Ответ от оператора:*\n\n{response_text}",
            parse_mode="Markdown",
        )
        await message.answer("✅ Ответ отправлен пользователю.")
    except ValueError:
        await message.answer("❌ Ошибка: Некорректный user_id.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке сообщения: {e}")

# Фолбэк-обработчик для неизвестных сообщений.
# Если сообщение начинается со слеша (команда), то не обрабатываем его здесь.
@dp.message()
async def default_handler(message: types.Message):
    if message.text and message.text.startswith("/"):
        return
    if message.from_user.id not in user_data:
        await message.answer(
            "Пожалуйста, используйте команду /start для начала диалога.",
            reply_markup=start_kb,
        )
    elif message.text == "Начать":
        await ask_city(message)
    else:
        await message.answer("Неизвестная команда. Пожалуйста, следуйте инструкциям.")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()  # Для обеспечения «живости» (например, на Repl.it)
    asyncio.run(main())
