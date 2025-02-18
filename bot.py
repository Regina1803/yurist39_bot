import os
import logging
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from redis import Redis
from dotenv import load_dotenv
import json

# Загружаем переменные окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID"))

# Подключение к Redis
redis_client = Redis(host='localhost', port=6379, decode_responses=True)
storage = RedisStorage2("localhost", 6379)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)

# Логирование
logging.basicConfig(level=logging.INFO)

# Клавиатуры
start_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Начать"))
city_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("Калининград"),
    KeyboardButton("Калининградская область"),
    KeyboardButton("Другой город")
)
role_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("Физ лицо"),
    KeyboardButton("Юр лицо")
)
contact_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("В чате"),
    KeyboardButton("По телефону")
)
confirm_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("Подождать звонка"),
    KeyboardButton("Позвонить сразу")
)

# Классы состояний
class ConsultationState(StatesGroup):
    waiting_for_query = State()
    waiting_for_operator_reply = State()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Добро пожаловать! Нажмите 'Начать', чтобы продолжить.", reply_markup=start_kb)

@dp.message_handler(lambda message: message.text == "Начать")
async def ask_city(message: types.Message):
    await message.answer("Из какого вы города?", reply_markup=city_kb)

@dp.message_handler(lambda message: message.text in ["Калининград", "Калининградская область", "Другой город"])
async def ask_role(message: types.Message):
    redis_client.hset(message.from_user.id, mapping={"city": message.text})
    await message.answer("Кем вы являетесь?", reply_markup=role_kb)

@dp.message_handler(lambda message: message.text in ["Физ лицо", "Юр лицо"])
async def ask_contact_method(message: types.Message):
    redis_client.hset(message.from_user.id, "role", message.text)
    await message.answer("Как вам удобнее получить консультацию?", reply_markup=contact_kb)

@dp.message_handler(lambda message: message.text in ["В чате", "По телефону"])
async def ask_name(message: types.Message):
    redis_client.hset(message.from_user.id, "contact_method", message.text)
    if redis_client.hget(message.from_user.id, "role") == "Юр лицо":
        await message.answer("Напишите название вашей компании.")
    else:
        await message.answer("Как к вам обращаться?")

@dp.message_handler()
async def ask_query(message: types.Message):
    redis_client.hset(message.from_user.id, "name", message.text)
    await message.answer("Укажите ваш запрос или ситуацию, с которой вы обращаетесь.")

@dp.message_handler()
async def ask_phone(message: types.Message):
    redis_client.hset(message.from_user.id, "query", message.text)
    if redis_client.hget(message.from_user.id, "contact_method") == "По телефону":
        await message.answer("Напишите ваш номер телефона.")
    else:
        await confirm_contact(message)

@dp.message_handler()
async def confirm_contact(message: types.Message):
    redis_client.hset(message.from_user.id, "phone", message.text)
    user_info = redis_client.hgetall(message.from_user.id)
    phone = user_info.get("phone", "—") if user_info.get("contact_method") == "По телефону" else "—"
    
    msg = (f"📢 Новый запрос на консультацию!\n\n"
           f"🏙 Город: {user_info.get('city')}\n"
           f"👤 Статус: {user_info.get('role')}\n"
           f"📞 Способ связи: {user_info.get('contact_method')}\n"
           f"📛 Имя/Компания: {user_info.get('name')}\n"
           f"📲 Телефон: {phone}\n"
           f"💬 Запрос: {user_info.get('query')}\n"
           f"🆔 User ID: {message.from_user.id}")
    
    if SUPPORT_GROUP_ID:
        await bot.send_message(SUPPORT_GROUP_ID, msg)
    
    await message.answer("Ожидайте, с вами свяжется оператор в чате.")
    await ConsultationState.waiting_for_operator_reply.set()

@dp.message_handler(commands=['reply'])
async def operator_reply(message: types.Message):
    args = message.text.split(maxsplit=2)
    
    if len(args) < 3:
        await message.reply("Используйте формат: /reply user_id текст")
        return
    
    user_id = args[1]
    response_text = args[2]
    
    if redis_client.exists(user_id):
        try:
            await bot.send_message(user_id, f"✉️ *Ответ от оператора:*\n\n{response_text}", parse_mode="Markdown")
            await message.answer("✅ Ответ отправлен пользователю.")
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке сообщения: {e}")
    else:
        await message.answer("❌ Ошибка: пользователь не найден в базе.")

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
