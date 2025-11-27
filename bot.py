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
    "Не сегодня.",
    "Сегодня мимо.",
    "Может завтра.",
    "Не стоит.",
    "Сегодня нет.",
]

EVENING_MESSAGES = [
    "Держись.",
    "Ещё чуть-чуть.",
    "Почти прошёл день.",
    "Не сегодня.",
]

NIGHT_MESSAGES = [
    "Молодец.",
    "Справился.",
    "День позади.",
    "💪",
]

MILESTONES = {
    7: "Неделя 💪",
    14: "Две недели 🔥",
    30: "Месяц 💎",
    60: "Два месяца 👑",
    90: "Три месяца ⭐",
    180: "Полгода 🏆",
    365: "Год 🎯"
}

TECHNIQUES = {
    "💨 Дыши": "Вдох 4 сек → задержка 7 сек → выдох 8 сек.\n\nПовтори 3 раза.",
    "🏃 Движение": "20 отжиманий или 100 приседаний.\n\nФизика перебивает химию.",
    "🚿 Холод": "Холодный душ 2 минуты.\n\nШок системе = перезагрузка.",
}

# =====================================================
# Клавиатуры
# =====================================================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("😔 Тяжело"), KeyboardButton("📊 Дни")],
        [KeyboardButton("👊"), KeyboardButton("⏸ Пауза")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_start_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True)

def get_help_keyboard():
    keyboard = [
        [KeyboardButton("💨 Дыши")],
        [KeyboardButton("🏃 Движение")],
        [KeyboardButton("🚿 Холод")],
        [KeyboardButton("💬 Не помогло")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_relapse_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Да, сорвался"), KeyboardButton("Нет, держусь")]],
        resize_keyboard=True
    )

# =====================================================
# Работа с данными
# =====================================================
def load_user_data():
    with FileLock(LOCK_FILE):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}

def save_user_data(data):
    with FileLock(LOCK_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_days_count(user_id):
    data = load_user_data()
    if str(user_id) in data and "start_date" in data[str(user_id)]:
        start_date = datetime.fromisoformat(data[str(user_id)]["start_date"])
        return (datetime.now() - start_date).days
    return 0

def get_total_days(user_id):
    """Общее количество успешных дней"""
    data = load_user_data()
    return data.get(str(user_id), {}).get("total_days", 0)

def get_attempts(user_id):
    """Количество попыток"""
    data = load_user_data()
    return data.get(str(user_id), {}).get("attempts", 1)

def reset_counter(user_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    
    # Сохраняем прогресс
    current_days = get_days_count(user_id)
    total = data[str(user_id)].get("total_days", 0)
    attempts = data[str(user_id)].get("attempts", 1)
    
    data[str(user_id)]["total_days"] = total + current_days
    data[str(user_id)]["attempts"] = attempts + 1
    data[str(user_id)]["start_date"] = datetime.now().isoformat()
    save_user_data(data)

def can_broadcast_today(user_id):
    data = load_user_data()
    if str(user_id) not in data or "last_broadcast" not in data[str(user_id)]:
        return True
    last = datetime.fromisoformat(data[str(user_id)]["last_broadcast"])
    return last.date() < datetime.now().date()

def mark_broadcast_sent(user_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    data[str(user_id)]["last_broadcast"] = datetime.now().isoformat()
    save_user_data(data)

def get_all_active_users():
    data = load_user_data()
    return [int(uid) for uid, ud in data.items() if ud.get("active", False)]

def store_message_id(user_id, message_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    if "message_ids" not in data[str(user_id)]:
        data[str(user_id)]["message_ids"] = []
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
# Отправка сообщений
# =====================================================
async def send_msg(bot, chat_id, text, save=True):
    """Отправка БЕЗ клавиатуры"""
    msg = await bot.send_message(chat_id, text)
    if save:
        store_message_id(chat_id, msg.message_id)
    return msg

async def return_to_main(bot, chat_id):
    """Возврат к основной клавиатуре"""
    await bot.send_message(chat_id, ".", reply_markup=get_main_keyboard())
    # Удаляем точку сразу
    try:
        msg = await bot.send_message(chat_id, ".")
        await bot.delete_message(chat_id, msg.message_id)
    except:
        pass

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
    data = load_user_data()
    
    if str(chat_id) not in data:
        data[str(chat_id)] = {}
    if "start_date" not in data[str(chat_id)]:
        data[str(chat_id)]["start_date"] = datetime.now().isoformat()
        data[str(chat_id)]["attempts"] = 1
    data[str(chat_id)]["active"] = True
    save_user_data(data)

    # Приветствие БЕЗ сохранения
    await context.bot.send_message(
        chat_id,
        "Три напоминания в день.\nЧат чистится в полночь.\n\nНе сегодня.",
        reply_markup=get_main_keyboard()
    )

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
    data = load_user_data()
    if str(chat_id) in data:
        data[str(chat_id)]["active"] = False
        save_user_data(data)
    
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()
    
    await context.bot.send_message(
        chat_id,
        "Остановлено.",
        reply_markup=get_start_keyboard()
    )

# =====================================================
# Обработка сообщений
# =====================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    # Сброс state при любой кнопке основного меню
    if text in ["📊 Дни", "👊", "⏸ Пауза", "▶ Начать"] and context.user_data.get('in_help_mode'):
        context.user_data['in_help_mode'] = False
        await return_to_main(context.bot, chat_id)

    if text == "▶ Начать":
        await start(update, context)
        return

    elif text == "😔 Тяжело":
        context.user_data['in_help_mode'] = True
        await context.bot.send_message(
            chat_id,
            "Попробуй:",
            reply_markup=get_help_keyboard()
        )
        return

    elif text in TECHNIQUES:
        await send_msg(context.bot, chat_id, TECHNIQUES[text])
        # Автовозврат через 5 секунд
        await asyncio.sleep(5)
        if context.user_data.get('in_help_mode'):
            context.user_data['in_help_mode'] = False
            await return_to_main(context.bot, chat_id)
        return

    elif text == "💬 Не помогло":
        context.user_data['in_help_mode'] = False
        context.user_data['awaiting_relapse'] = True
        await context.bot.send_message(
            chat_id,
            "Сорвался?",
            reply_markup=get_relapse_keyboard()
        )
        return

    elif context.user_data.get('awaiting_relapse'):
        if text == "Да, сорвался":
            reset_counter(chat_id)
            context.user_data['awaiting_relapse'] = False
            await send_msg(context.bot, chat_id, "Ничего. Продолжаем.")
            await return_to_main(context.bot, chat_id)
        elif text == "Нет, держусь":
            context.user_data['awaiting_relapse'] = False
            await send_msg(context.bot, chat_id, "Молодец.")
            await return_to_main(context.bot, chat_id)
        return

    elif text == "👊":
        if not can_broadcast_today(chat_id):
            await send_msg(context.bot, chat_id, "Уже отправлял.")
            return
        
        for uid in get_all_active_users():
            if uid != chat_id:
                try:
                    await send_msg(context.bot, uid, "👊")
                    await asyncio.sleep(0.05)
                except:
                    pass
        
        mark_broadcast_sent(chat_id)
        await send_msg(context.bot, chat_id, "✓")
        return

    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        total = get_total_days(chat_id) + days
        attempts = get_attempts(chat_id)
        
        if total == 0:
            msg = "День 1"
        else:
            avg = total // attempts if attempts > 0 else 0
            msg = f"Сейчас: {days}\nВсего: {total}\nПопыток: {attempts}\nСреднее: {avg} дней"
        
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
