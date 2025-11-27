import logging
import random
import json
import os
import asyncio
from datetime import datetime, time
from filelock import FileLock
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import pytz

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")

DATA_FILE = "user_data.json"
LOCK_FILE = DATA_FILE + ".lock"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =====================================================
# Сообщения
# =====================================================
MORNING_MESSAGES = [
    "Не буду сегодня.",
    "Сегодня мимо.",
    "Может завтра, но не сегодня.",
    "Сегодня точно нет.",
    "Обойдусь.",
    "Не, сегодня не хочу.",
]

EVENING_MESSAGES = [
    "Держусь.",
    "Пока держусь.",
    "Сегодня нормально.",
    "Терплю.",
    "Не сегодня же.",
]

NIGHT_MESSAGES = [
    "Получилось сегодня.",
    "Норм день.",
    "Справились.",
    "Держался.",
    "💪",
]

MILESTONES = {
    3: "Три дня держусь.",
    7: "Неделя 💪",
    14: "Две недели 🔥",
    30: "Месяц 💎",
    60: "Два месяца 👑",
    90: "Три месяца ⭐",
    180: "Полгода 🏆",
    365: "Год 🎯"
}

TECHNIQUES = {
    "💨 Дыши": "Вдох 4 сек → задержка 7 сек → выдох 8 сек.\n\nПовтори 3 раза.\nМне помогает.",
    "🏃 Движение": "20 отжиманий или 100 приседаний.\n\nФизуха перебивает тягу.",
    "🚿 Холод": "Холодный душ 2 минуты.\n\nМозги на место встают.",
}

TU_TUT_FIRST = ["Тут.", "Да.", "На месте.", "Здесь.", "Ага."]
TU_TUT_SECOND = ["Держусь.", "Не курю сегодня.", "Терплю.", "Пока держусь.", "Сегодня мимо.", "Не сегодня."]

BROADCAST_EMOJIS = ["💪", "🫶", "🤝"]

WELCOME_TEXT = "Привет.\n\nБуду писать что сам делаю.\nТри раза в день.\n\nЧат чистится ночью.\n\nНе сегодня."
HELP_PROMPT = "Попробуй:"
RELAPSE_QUESTION = "Начать заново?"
RELAPSE_YES = "Ничего. Я тоже пробую снова."
RELAPSE_NO = "Понял. Держись."
BROADCAST_SENT = "Отправлено."
BROADCAST_ALREADY = "Уже отправлял."
STOP_TEXT = "Остановлено. Нажми ▶ Начать чтобы возобновить."

# =====================================================
# Клавиатуры
# =====================================================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("🔥 Держись!"), KeyboardButton("📊 Дни")],
        [KeyboardButton("⏸ Пауза")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_start_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True)

def get_help_keyboard():
    keyboard = [
        [KeyboardButton("💨 Дыши")],
        [KeyboardButton("🏃 Движение")],
        [KeyboardButton("🚿 Холод")],
        [KeyboardButton("🔄 Попробовать ещё раз")],
        [KeyboardButton("↩️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_relapse_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("Да"), KeyboardButton("Нет")]], resize_keyboard=True)

# =====================================================
# Работа с данными
# =====================================================
def load_user_data():
    try:
        with FileLock(LOCK_FILE):
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
    return {}

def save_user_data(data):
    try:
        with FileLock(LOCK_FILE):
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

def ensure_user_data(user_id):
    """Гарантирует что структура данных пользователя корректна"""
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    if "message_ids" not in data[str(user_id)]:
        data[str(user_id)]["message_ids"] = []
    if "active" not in data[str(user_id)]:
        data[str(user_id)]["active"] = False
    return data

def get_days_count(user_id):
    data = load_user_data()
    if str(user_id) in data and "start_date" in data[str(user_id)]:
        try:
            start_date = datetime.fromisoformat(data[str(user_id)]["start_date"])
            return (datetime.now() - start_date).days
        except:
            pass
    return 0

def reset_counter(user_id):
    data = ensure_user_data(user_id)
    data[str(user_id)]["start_date"] = datetime.now().isoformat()
    save_user_data(data)

def can_broadcast_today(user_id):
    data = load_user_data()
    if str(user_id) not in data or "last_broadcast" not in data[str(user_id)]:
        return True
    try:
        last = datetime.fromisoformat(data[str(user_id)]["last_broadcast"])
        return last.date() < datetime.now().date()
    except:
        return True

def mark_broadcast_sent(user_id):
    data = ensure_user_data(user_id)
    data[str(user_id)]["last_broadcast"] = datetime.now().isoformat()
    save_user_data(data)

def get_all_active_users():
    data = load_user_data()
    return [int(uid) for uid, ud in data.items() if ud.get("active", False)]

def store_message_id(user_id, message_id):
    data = ensure_user_data(user_id)
    data[str(user_id)]["message_ids"].append(message_id)
    save_user_data(data)

# =====================================================
# Очистка чата
# =====================================================
async def midnight_clean_chat(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if str(chat_id) not in data or "message_ids" not in data[str(chat_id)]:
        return
    message_ids = data[str(chat_id)]["message_ids"]
    data[str(chat_id)]["message_ids"] = []
    save_user_data(data)
    
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id, msg_id)
            await asyncio.sleep(0.05)
        except:
            pass

# =====================================================
# Утилиты для сообщений
# =====================================================
async def send_msg(bot, chat_id, text, save=True):
    """Отправка БЕЗ клавиатуры"""
    msg = await bot.send_message(chat_id, text)
    if save:
        store_message_id(chat_id, msg.message_id)
    return msg

async def reset_to_main_keyboard(bot, chat_id):
    """Возврат к основной клавиатуре без видимого сообщения"""
    msg = await bot.send_message(chat_id, "‎", reply_markup=get_main_keyboard())  # Невидимый символ
    try:
        await asyncio.sleep(0.1)
        await bot.delete_message(chat_id, msg.message_id)
    except:
        pass

def clear_user_state(context):
    """Очистка всех state флагов"""
    context.user_data['in_help_mode'] = False
    context.user_data['awaiting_relapse'] = False

# =====================================================
# Уведомления
# =====================================================
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    
    days = get_days_count(chat_id)
    text = MILESTONES.get(days, random.choice(MORNING_MESSAGES))
    await send_msg(context.bot, chat_id, text)

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    await send_msg(context.bot, chat_id, random.choice(EVENING_MESSAGES))

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    await send_msg(context.bot, chat_id, random.choice(NIGHT_MESSAGES))

# =====================================================
# Команды
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = ensure_user_data(chat_id)
    
    if "start_date" not in data[str(chat_id)]:
        data[str(chat_id)]["start_date"] = datetime.now().isoformat()
    data[str(chat_id)]["active"] = True
    save_user_data(data)

    clear_user_state(context)

    # Приветствие БЕЗ сохранения
    await context.bot.send_message(chat_id, WELCOME_TEXT, reply_markup=get_main_keyboard())

    # Перезапуск задач
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    context.job_queue.run_daily(send_morning_message, time=time(hour=9, minute=0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"morning_{chat_id}")
    context.job_queue.run_daily(send_evening_message, time=time(hour=18, minute=0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"evening_{chat_id}")
    context.job_queue.run_daily(send_night_message, time=time(hour=23, minute=0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"night_{chat_id}")
    context.job_queue.run_daily(midnight_clean_chat, time=time(hour=0, minute=1, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"midnight_{chat_id}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = ensure_user_data(chat_id)
    data[str(chat_id)]["active"] = False
    save_user_data(data)
    
    clear_user_state(context)
    
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()
    
    await context.bot.send_message(chat_id, STOP_TEXT, reply_markup=get_start_keyboard())

# =====================================================
# Обработка сообщений
# =====================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    # Основные команды всегда сбрасывают state
    if text in ["▶ Начать", "📊 Дни", "👋 Ты тут?", "🔥 Держись!", "⏸ Пауза"]:
        clear_user_state(context)

    if text == "▶ Начать":
        await start(update, context)
        return

    elif text == "👋 Ты тут?":
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await send_msg(context.bot, chat_id, random.choice(TU_TUT_FIRST))
        await asyncio.sleep(random.uniform(1.5, 2.5))
        await send_msg(context.bot, chat_id, random.choice(TU_TUT_SECOND))
        return

    elif text == "😔 Тяжело":
        context.user_data['in_help_mode'] = True
        await context.bot.send_message(chat_id, HELP_PROMPT, reply_markup=get_help_keyboard())
        return

    elif text in TECHNIQUES and context.user_data.get('in_help_mode'):
        await send_msg(context.bot, chat_id, TECHNIQUES[text])
        return

    elif text == "🔄 Попробовать ещё раз":
        context.user_data['in_help_mode'] = False
        context.user_data['awaiting_relapse'] = True
        await context.bot.send_message(chat_id, RELAPSE_QUESTION, reply_markup=get_relapse_keyboard())
        return

    elif text == "↩️ Назад":
        clear_user_state(context)
        await reset_to_main_keyboard(context.bot, chat_id)
        return

    elif context.user_data.get('awaiting_relapse'):
        if text == "Да":
            reset_counter(chat_id)
            clear_user_state(context)
            await send_msg(context.bot, chat_id, RELAPSE_YES)
            await reset_to_main_keyboard(context.bot, chat_id)
        elif text == "Нет":
            clear_user_state(context)
            await send_msg(context.bot, chat_id, RELAPSE_NO)
            await reset_to_main_keyboard(context.bot, chat_id)
        else:
            # Если написал что-то другое - сбрасываем state и возвращаем к меню
            clear_user_state(context)
            await reset_to_main_keyboard(context.bot, chat_id)
        return

    elif text == "🔥 Держись!":
        if not can_broadcast_today(chat_id):
            await send_msg(context.bot, chat_id, BROADCAST_ALREADY)
            return
        
        emoji = random.choice(BROADCAST_EMOJIS)
        
        for uid in get_all_active_users():
            if uid != chat_id:
                try:
                    await send_msg(context.bot, uid, emoji)
                    await asyncio.sleep(0.05)
                except:
                    pass
        
        mark_broadcast_sent(chat_id)
        await send_msg(context.bot, chat_id, BROADCAST_SENT)
        return

    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        if days == 0:
            msg = "Первый день."
        elif days == 1:
            msg = "Прошёл 1 день"
        else:
            msg = f"Прошло {days} дней"
        await send_msg(context.bot, chat_id, msg)
        return

    elif text == "⏸ Пауза":
        await stop(update, context)
        return

# =====================================================
# Запуск
# =====================================================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
