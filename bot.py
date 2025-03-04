import os
import logging
import asyncio
import json
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.redis import RedisStorage

# Загружаем переменные окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
SUPPORT_GROUP_ID = os.getenv("SUPPORT_GROUP_ID")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=RedisStorage.from_url("redis://localhost:6379"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Определяем клавиатуры
start_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Начать")]], resize_keyboard=True
)
city_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Калининград"), KeyboardButton(text="Другой регион"), KeyboardButton(text="Другая страна")]],
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
type_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Юрист"), KeyboardButton(text="Адвокат")]],
    resize_keyboard=True,
)

# Класс состояний для консультации
class ConsultationState(StatesGroup):
    waiting_for_city = State()
    waiting_for_custom_city = State()
    waiting_for_role = State()
    waiting_for_type = State()
    waiting_for_contact_method = State()
    waiting_for_name = State()
    waiting_for_query = State()
    waiting_for_phone = State()
    waiting_for_operator_reply = State()

# Функция для отправки уведомления в группу поддержки
async def notify_support(data: dict):
    msg = (
        f"📢 Новый запрос на консультацию!\n\n"
        f"🏙 Город: {data.get('city', 'Не указан')}\n"
        f"👤 Статус: {data.get('role', 'Не указан')}\n"
        f"📞 Способ связи: {data.get('contact_method', 'Не указан')}\n"
        f"📛 Имя/Компания: {data.get('name', 'Не указано')}\n"
        f"📲 Телефон: {data.get('phone', 'Не указан')}\n"
        f"📲 Необходим: {data.get('type', 'Не указан')}\n"
        f"💬 Запрос: {data.get('query', 'Не указан')}\n"
        f"🆔 User ID: {data.get('user_id', 'Не указан')}"
    )
    try:
        await bot.send_message(SUPPORT_GROUP_ID, msg)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения в группу поддержки: {e}")

@dp.message(Command("start", ignore_case=True))
async def start(message: types.Message, state: FSMContext):
    await state.set_data({"user_id": message.from_user.id})
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Этот бот создан, чтобы помочь вам в решении юридических вопросов. 🏛️\n\n"
        "🔹 Просто оставьте заявку и укажите удобный способ связи.\n"
        "🔹 Наши специалисты рассмотрят ваш запрос и предложат оптимальное решение.\n\n"
        "📌 Нажмите кнопку ниже, чтобы начать.",
        reply_markup=start_kb,
    )
    await ConsultationState.waiting_for_city.set()

@dp.message(ConsultationState.waiting_for_city, F.text == "Начать")
async def ask_city(message: types.Message, state: FSMContext):
    await message.answer("Из какого вы города?", reply_markup=city_kb)

@dp.message(ConsultationState.waiting_for_city, F.text.in_(["Другой регион", "Другая страна"]))
async def ask_custom_city(message: types.Message, state: FSMContext):
    await message.answer("Введите название вашего города:", reply_markup=ReplyKeyboardRemove())
    await ConsultationState.waiting_for_custom_city.set()

@dp.message(ConsultationState.waiting_for_custom_city)
async def save_custom_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Кем вы являетесь?", reply_markup=role_kb)
    await ConsultationState.waiting_for_role.set()

@dp.message(ConsultationState.waiting_for_city, F.text.in_(["Калининград", "Калининградская область", "Другой город"]))
async def ask_role(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Кем вы являетесь?", reply_markup=role_kb)
    await ConsultationState.waiting_for_role.set()

@dp.message(ConsultationState.waiting_for_role, F.text.in_(["Физ лицо", "Юр лицо"]))
async def ask_type(message: types.Message, state: FSMContext):
    await state.update_data(role=message.text)
    explanation = (
        "🔹 Адвокат – ведет уголовные дела, представляет в суде, оказывает защиту.\n"
        "🔹 Юрист – консультации по договорам, недвижимости, бизнесу, оформлению документов, представляет в суде, оказывает защиту."
    )
    await message.answer(f"Кто вам необходим?\n\n{explanation}", reply_markup=type_kb)
    await ConsultationState.waiting_for_type.set()

@dp.message(ConsultationState.waiting_for_type, F.text.in_(["Адвокат", "Юрист"]))
async def ask_contact_method(message: types.Message, state: FSMContext):
    await state.update_data(type=message.text)
    await message.answer("Как вам удобнее получить консультацию?", reply_markup=contact_kb)
    await ConsultationState.waiting_for_contact_method.set()

@dp.message(ConsultationState.waiting_for_contact_method, F.text.in_(["В чате", "По телефону"]))
async def ask_name(message: types.Message, state: FSMContext):
    await state.update_data(contact_method=message.text)
    prompt = "Напишите название вашей компании." if (await state.get_data()).get("role") == "Юр лицо" else "Как к вам обращаться?"
    await message.answer(prompt, reply_markup=ReplyKeyboardRemove())
    await ConsultationState.waiting_for_name.set()

@dp.message(ConsultationState.waiting_for_name)
async def ask_query(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Укажите ваш запрос или ситуацию, с которой вы обращаетесь.")
    await ConsultationState.waiting_for_query.set()

@dp.message(ConsultationState.waiting_for_query)
async def ask_phone_or_confirm(message: types.Message, state: FSMContext):
    await state.update_data(query=message.text)
    data = await state.get_data()
    if data.get("contact_method") == "По телефону":
        await message.answer("Напишите ваш номер телефона.")
        await ConsultationState.waiting_for_phone.set()
    else:
        await confirm_contact(message, state)

@dp.message(ConsultationState.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await confirm_contact(message, state)

async def confirm_contact(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data.setdefault("phone", "—")
    data["consultation_active"] = True
    data["user_id"] = message.from_user.id
    await state.update_data(**data)

    # Отправляем уведомление в группу поддержки
    await notify_support(data)

    if data.get("contact_method") == "По телефону":
        await message.answer(
            "✅ Ваш запрос принят! Если не хотите ждать звонка, позвоните нам самостоятельно по номеру: \n"
            "📞 [ +7 (911) 458-39-39](tel:+79114583939)",
            parse_mode="Markdown"
        )
    else:
        await message.answer("Ожидайте, с вами свяжется оператор в чате.")
    
    await ConsultationState.waiting_for_operator_reply.set()

@dp.message(ConsultationState.waiting_for_operator_reply, F.chat.type == "private")
async def forward_user_message_to_operator(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("consultation_active"):
        try:
            await bot.send_message(
                SUPPORT_GROUP_ID,
                f"📩 *Новое сообщение от клиента:*\n\n"
                f"👤 {data.get('name', 'Не указано')}\n"
                f"📞 {data.get('phone', 'Не указан')}\n"
                f"💬 {message.text}\n\n"
                f"🆔 User ID: {message.from_user.id}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Ошибка пересылки сообщения оператору: {e}")
    else:
        await message.answer("Вы можете задать новый вопрос.")

@dp.message(Command("reply", ignore_case=True))
async def operator_reply(message: types.Message, state: FSMContext):
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

@dp.message(F.chat.type == "private", F.text.startswith("/reply"))
async def handle_reply_from_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("consultation_active"):
        try:
            await bot.send_message(
                SUPPORT_GROUP_ID,
                f"📩 *Ответ от клиента:*\n\n"
                f"👤 {data.get('name', 'Не указано')}\n"
                f"📞 {data.get('phone', 'Не указан')}\n"
                f"💬 {message.text}\n\n"
                f"🆔 User ID: {message.from_user.id}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Ошибка пересылки сообщения оператору: {e}")
    else:
        await message.answer("Консультация завершена. Вы можете задать новый вопрос.")

async def main():
    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Программа завершена.")
