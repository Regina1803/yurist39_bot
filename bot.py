import os
import logging
import asyncio
import json
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.redis import RedisStorage
from redis import Redis

# Загружаем переменные окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID"))

# Подключение к Redis
redis_client = Redis(host='localhost', port=6379, decode_responses=True)
storage = RedisStorage.from_url("redis://localhost:6379")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функции для работы с Redis
def save_user_data(user_id, data):
    redis_client.setex(f"user:{user_id}", 1800, json.dumps(data))  # 30 минут

def get_user_data(user_id):
    data = redis_client.get(f"user:{user_id}")
    return json.loads(data) if data else {}

# Очистка устаревших данных
async def clean_old_data():
    while True:
        logger.info("Очистка Redis выполняется автоматически по TTL")
        await asyncio.sleep(600)  # Каждые 10 минут

# Клавиатуры
start_kb = ReplyKeyboardMarkup([[KeyboardButton(text="Начать")]], resize_keyboard=True)
city_kb = ReplyKeyboardMarkup([
    [KeyboardButton(text="Калининград"), KeyboardButton(text="Калининградская область"), KeyboardButton(text="Другой город")]
], resize_keyboard=True)
role_kb = ReplyKeyboardMarkup([
    [KeyboardButton(text="Физ лицо"), KeyboardButton(text="Юр лицо")]
], resize_keyboard=True)
contact_kb = ReplyKeyboardMarkup([
    [KeyboardButton(text="В чате"), KeyboardButton(text="По телефону")]
], resize_keyboard=True)
confirm_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Подождать звонка"), KeyboardButton(text="Позвонить сразу")]],
    resize_keyboard=True,
)
# Классы состояний
class ConsultationState(StatesGroup):
    waiting_for_operator_reply = State()

# Обработчик команды /start
@dp.message(Command("start", ignore_case=True))
async def start(message: types.Message):
    save_user_data(message.from_user.id, {})
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Этот бот создан, чтобы помочь вам в решении юридических вопросов. 🏛️\n\n"
        "🔹 Просто оставьте заявку и укажите удобный способ связи.\n"
        "🔹 Наши специалисты рассмотрят ваш запрос и предложат оптимальное решение.\n\n"
        "📌 <b>Нажмите кнопку ниже, чтобы начать.</b>",
        reply_markup=start_kb,
        parse_mode="HTML"
    )

# Вопросы пользователю
@dp.message(F.text == "Начать")
async def ask_city(message: types.Message):
    await message.answer("Из какого вы города?", reply_markup=city_kb)

@dp.message(F.text.in_(["Калининград", "Калининградская область", "Другой город"]))
async def ask_role(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    user_data["city"] = message.text
    save_user_data(message.from_user.id, user_data)
    await message.answer("Кем вы являетесь?", reply_markup=role_kb)

@dp.message(F.text.in_(["Физ лицо", "Юр лицо"]))
async def ask_contact_method(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    user_data["role"] = message.text
    save_user_data(message.from_user.id, user_data)
    await message.answer("Как вам удобнее получить консультацию?", reply_markup=contact_kb)

@dp.message(F.text.in_(["В чате", "По телефону"]))
async def ask_name(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    user_data["contact_method"] = message.text
    save_user_data(message.from_user.id, user_data)
    
    if user_data["role"] == "Юр лицо":
        await message.answer("Напишите название вашей компании.")
    else:
        await message.answer("Как к вам обращаться?")

@dp.message(lambda m: "name" not in get_user_data(m.from_user.id))
async def ask_query(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    user_data["name"] = message.text
    save_user_data(message.from_user.id, user_data)
    await message.answer("Укажите ваш запрос или ситуацию, с которой вы обращаетесь.")

@dp.message(lambda m: "query" not in get_user_data(m.from_user.id))
async def ask_phone(message: types.Message, state: FSMContext):
    user_data = get_user_data(message.from_user.id)
    user_data["query"] = message.text
    save_user_data(message.from_user.id, user_data)

    if user_data["contact_method"] == "По телефону":
        await message.answer("Выберите удобный вариант:", reply_markup=confirm_kb)
    else:
        await confirm_contact(message, state, phone_input=False)

@dp.message(lambda m: "query" not in get_user_data(m.from_user.id))
async def ask_phone(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    user_data["query"] = message.text
    save_user_data(message.from_user.id, user_data)

    if user_data["contact_method"] == "По телефону":
        await message.answer("Выберите удобный вариант:", reply_markup=confirm_kb)
    else:
        await confirm_contact(message)

@dp.message(F.text.in_(["Подождать звонка", "Позвонить сразу"]))
async def process_phone_choice(message: types.Message):
    if message.text == "Подождать звонка":
        await message.answer("✅ Ожидайте, с вами свяжется оператор в ближайшее время.")
    else:
        await message.answer("📞 Позвоните по номеру: +7 (911) 458-39-39")

async def confirm_contact(message: types.Message, state: FSMContext, phone_input: bool):
    user_data = get_user_data(message.from_user.id)
    user_data["phone"] = message.text if phone_input else "—"
    save_user_data(message.from_user.id, user_data)

    msg = (
        f"📢 Новый запрос на консультацию!\n\n"
        f"🏙 Город: {user_data.get('city', 'Не указан')}\n"
        f"👤 Статус: {user_data.get('role', 'Не указан')}\n"
        f"📞 Способ связи: {user_data.get('contact_method', 'Не указан')}\n"
        f"📛 Имя/Компания: {user_data.get('name', 'Не указано')}\n"
        f"📲 Телефон: {user_data.get('phone', 'Не указан')}\n"
        f"💬 Запрос: {user_data.get('query', 'Не указан')}\n"
        f"🆔 User ID: {message.from_user.id}"
    )

    if SUPPORT_GROUP_ID:
        await bot.send_message(SUPPORT_GROUP_ID, msg)

    await message.answer("Ожидайте, с вами свяжется оператор в чате.")
    await state.set_state(ConsultationState.waiting_for_operator_reply)

# Ответ оператора
@dp.message(Command("reply", ignore_case=True))
async def operator_reply(message: types.Message, state: FSMContext):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Используйте формат: /reply user_id текст")
        return

    user_id, response_text = int(args[1]), args[2]

    await bot.send_message(user_id, f"✉️ *Ответ от оператора:*\n\n{response_text}", parse_mode="Markdown")
    await message.answer("✅ Ответ отправлен пользователю.")
    await state.clear()

# Перезапуск бота
async def restart_bot():
    while True:
        try:
            logger.info("Бот запущен!")
            await dp.start_polling(bot)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(restart_bot())
