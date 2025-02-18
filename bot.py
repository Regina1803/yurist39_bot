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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функция для сохранения данных в Redis с обработкой исключений
def save_user_data(user_id, data):
    try:
        redis_client.setex(f"user:{user_id}", 1800, json.dumps(data))  # Сохраняем на 30 минут
    except Exception as e:
        logger.error(f"Ошибка сохранения данных пользователя {user_id}: {e}")

# Функция для загрузки данных пользователя с обработкой исключений
def get_user_data(user_id):
    try:
        data = redis_client.get(f"user:{user_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных пользователя {user_id}: {e}")
        return {}

# Определяем клавиатуры
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
# confirm_kb оставлен на случай будущего использования
confirm_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Подождать звонка"), KeyboardButton(text="Позвонить сразу")]],
    resize_keyboard=True,
)

# Класс состояний для консультации
class ConsultationState(StatesGroup):
    waiting_for_operator_reply = State()

@dp.message(Command("start", ignore_case=True))
async def start(message: types.Message):
    save_user_data(message.from_user.id, {})
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Этот бот создан, чтобы помочь вам в решении юридических вопросов. 🏛️\n\n"
        "🔹 Просто оставьте заявку и укажите удобный способ связи.\n"
        "🔹 Наши специалисты рассмотрят ваш запрос и предложат оптимальное решение.\n\n"
        "📌 Нажмите кнопку ниже, чтобы начать.",
        reply_markup=start_kb,
    )

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
    
    if user_data.get("role") == "Юр лицо":
        await message.answer("Напишите название вашей компании.")
    else:
        await message.answer("Как к вам обращаться?")

# Если имя/название компании ещё не сохранено – сохраняем его и запрашиваем описание ситуации
@dp.message(lambda m: "name" not in get_user_data(m.from_user.id))
async def ask_query(message: types.Message):
    user_data = get_user_data(message.from_user.id)
    user_data["name"] = message.text
    save_user_data(message.from_user.id, user_data)
    await message.answer("Укажите ваш запрос или ситуацию, с которой вы обращаетесь.")

# Если запрос ещё не сохранён – сохраняем его и запрашиваем телефон (если выбран режим "По телефону")
@dp.message(lambda m: "query" not in get_user_data(m.from_user.id))
async def ask_phone(message: types.Message, state: FSMContext):
    user_data = get_user_data(message.from_user.id)
    user_data["query"] = message.text
    save_user_data(message.from_user.id, user_data)

    if user_data.get("contact_method") == "По телефону":
        await message.answer("Напишите ваш номер телефона.")
    else:
        await confirm_contact(message, state, phone_input=False)

# Если выбран режим "По телефону", обрабатываем ввод номера телефона
@dp.message(lambda m: get_user_data(m.from_user.id).get("contact_method") == "По телефону")
async def process_phone(message: types.Message, state: FSMContext):
    await confirm_contact(message, state, phone_input=True)

# Функция подтверждения и отправки данных о заявке
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
        try:
            await bot.send_message(SUPPORT_GROUP_ID, msg)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в группу поддержки: {e}")

    if user_data.get("contact_method") == "По телефону":
        await message.answer(
            "✅ Ваш запрос принят! Если не хотите ждать звонка, позвоните нам самостоятельно по номеру: \n"
            "📞 [ +7 (911) 458-39-39](tel:+79114583939)",
            parse_mode="Markdown"
        )
    else:
        await message.answer("Ожидайте, с вами свяжется оператор в чате.")

    await state.set_state(ConsultationState.waiting_for_operator_reply)

# Пересылаем сообщения от пользователя оператору в SUPPORT_GROUP_ID
@dp.message(F.chat.type == "private", F.text.not_startswith("/reply"))
async def forward_user_message_to_operator(message: types.Message, state: FSMContext):
    user_data = get_user_data(message.from_user.id)
    if user_data.get("consultation_active"):
        try:
            await bot.send_message(
                SUPPORT_GROUP_ID,
                f"📩 *Новое сообщение от клиента:*\n\n"
                f"👤 {user_data.get('name', 'Не указано')}\n"
                f"📞 {user_data.get('phone', 'Не указан')}\n"
                f"💬 {message.text}\n\n"
                f"🆔 User ID: {message.from_user.id}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Ошибка пересылки сообщения оператору: {e}")

# Обработчик команды оператора для ответа клиенту (работает в группе поддержки)
@dp.message(Command("reply", ignore_case=True))
async def operator_reply(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Используйте формат: /reply user_id текст")
        return
    user_id_str = args[1]
    response_text = args[2]
    try:
        user_id = int(user_id_str)
        await bot.send_message(
            user_id,
            f"✉️ *Ответ от оператора:*\n\n{response_text}",
            parse_mode="Markdown",
        )
        await message.answer("✅ Ответ отправлен пользователю.")
        # Флаг consultation_active остаётся выставленным,
        # поэтому любые последующие сообщения клиента будут пересланы операторам.
    except ValueError:
        await message.answer("❌ Ошибка: Некорректный user_id.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке сообщения: {e}")
# Функция для безопасного перезапуска бота
async def restart_bot():
    while True:
        try:
            logger.info("Бот запущен!")
            await dp.start_polling(bot)
        except Exception as e:
            logger.error(f"Бот упал с ошибкой: {e}")
        finally:
            # Гарантированное закрытие сессии бота и хранилища состояний,
            # чтобы избежать накопления неосвобождённых ресурсов
            await bot.session.close()
            await storage.close()
        logger.info("Перезапуск через 5 секунд...")
        await asyncio.sleep(5)

# Основная функция запуска бота
async def main():
    try:
        await restart_bot()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Программа завершена.")
