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
    "Привет. Давай сегодня не будем, хорошо?",
    "Доброе утро, брат. Не сегодня.",
    "Привет. Держимся сегодня, да?",
    "Доброе. Ну что, сегодня точно нет.",
    "Привет. Сегодня обойдёмся, окей?",
    "Утро. Давай только не сегодня.",
    "Привет, брат. Сегодня мимо.",
    "Доброе утро. Не сегодня же.",
    "Привет, бро. Сегодня точно не надо.",
    "Доброе! Давай сегодня без этого.",
    "Утро. Ну что, сегодня мимо?",
    "Привет. Сегодня я думаю обойдёмся.",
    "Братан, доброе. Сегодня точно нет.",
    "Эй. Сегодня не в тему, согласен?",
    "Доброе утро. Давай только не сегодня.",
    "Привет. Может завтра, но сегодня нет.",
    "Утро, брат. Сегодня спокойно обходимся без этого, а завтра посмотрим.",
    "Эй. Сегодня точно не стоит, да?"
]

EVENING_MESSAGES = [
    "Брат, не сегодня. Держись.",
    "Эй, я тут. Давай не сегодня.",
    "Привет. Сегодня держимся, помнишь?",
    "Брат, держись. Сегодня нет.",
    "Эй. Ещё чуть-чуть. Не сегодня.",
    "Я с тобой. Сегодня точно нет.",
    "Привет. Давай обойдёмся, а?",
    "Брат, мы же решили - не сегодня.",
    "Держись там. Сегодня мимо.",
    "Привет. Давай сегодня пропустим.",
    "Эй. Сегодня точно можно без этого.",
    "Братан, сегодня не надо, согласен?",
    "Привет. Может завтра, сегодня мимо.",
    "Как дела? Сегодня обойдёмся легко.",
    "Эй, брат. Давай сегодня не будем.",
    "Привет. Сегодня точно ни к чему это.",
    "Братан, ну может завтра, а сегодня нет?"
]

NIGHT_MESSAGES = [
    "Ты молодец. До завтра, братан.",
    "Красавчик. Спокойной ночи.",
    "Держался сегодня. Уважаю. Спи.",
    "Сегодня справились. До завтра, брат.",
    "Молодец, держишься. Спокойной ночи.",
    "Еще один день позади. Горжусь. Спи.",
    "Ты сильный. До завтра.",
    "Сегодня получилось. Отдыхай, братан.",
    "Справился. Уважение. Спокойной ночи.",
    "Держался весь день. Красава. Спи.",
    "Нормально прошёл день. Спокойной ночи.",
    "Сегодня справились. Отдыхай, брат.",
    "Ещё один день прошёл. До завтра, братан.",
    "Держались сегодня. Молодцы. Спи.",
    "День зачётный. Спокойной ночи.",
    "Справились. До завтра, брат.",
    "Сегодня получилось. Отдыхай."
]

MILESTONES = {
    3: "Три дня уже, братан. Неплохо идём.",
    7: "Неделя прошла. Заметил? Продолжаем.",
    14: "Две недели! Хорошо идёт, брат.",
    30: "Месяц. Серьёзно, уважаю.",
    60: "Два месяца. Сильный результат, бро.",
    90: "Три месяца! Ты реально крутой.",
    180: "Полгода, братан. Это впечатляет.",
    365: "Год. Легенда."
}

# =====================================================
# Клавиатуры
# =====================================================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("🔥 Держись!"), KeyboardButton("📊 Дни")],
        [KeyboardButton("💲 Сказать спасибо"), KeyboardButton("⏸ Пауза")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_start_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True)

def get_relapse_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("Да"), KeyboardButton("Нет")]], resize_keyboard=True)

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

def reset_counter(user_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
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

# =====================================================
# Очистка чата в полночь
# =====================================================
async def midnight_clean_chat(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if str(chat_id) not in data or "message_ids" not in data[str(chat_id)]:
        return
    message_ids = data[str(chat_id)]["message_ids"]
    data[str(chat_id)]["message_ids"] = []
    save_user_data(data)
    deleted = 0
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id, msg_id)
            deleted += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    logger.info(f"Очистил {deleted} сообщений у {chat_id}")

# =====================================================
# Отправка сообщений
# =====================================================
async def send_message(bot, chat_id, text, reply_markup=get_main_keyboard(), save_for_deletion=True):
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    if save_for_deletion:
        data = load_user_data()
        if str(chat_id) not in data:
            data[str(chat_id)] = {}
        if "message_ids" not in data[str(chat_id)]:
            data[str(chat_id)]["message_ids"] = []
        data[str(chat_id)]["message_ids"].append(msg.message_id)
        save_user_data(data)
    return msg

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
    await send_message(context.bot, chat_id, text)

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    text = random.choice(EVENING_MESSAGES)
    await send_message(context.bot, chat_id, text)

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    text = random.choice(NIGHT_MESSAGES)
    await send_message(context.bot, chat_id, text)

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
    data[str(chat_id)]["active"] = True
    save_user_data(data)

    await send_message(
        context.bot, chat_id,
        "Привет.\n\n"
        "Я буду писать три раза в день, просто напомнить: не сегодня.\n\n"
        "Если нажмёшь 🔥 Держись! — всем остальным придёт пуш. Просто чтобы знали: они не одни.\n\n"
        "Чат чистится каждую ночь. Всё строго между нами.\n\n"
        "Держись, брат.",
        save_for_deletion=False
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
    await send_message(
        context.bot, chat_id,
        "Напоминания остановлены. Нажми ▶ Начать чтобы возобновить.",
        reply_markup=get_start_keyboard(),
        save_for_deletion=False
    )

# =====================================================
# Обработка сообщений
# =====================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "▶ Начать":
        await start(update, context)
        return

    elif text == "👋 Ты тут?":
        await asyncio.sleep(random.uniform(2.8, 5.5))
        first = random.choice([
            "Тут, брат.", "А куда я денусь?", "Здесь. Как всегда.", "На связи.", "Тут, братан.",
            "Конечно тут.", "Тут. Дышу ровно.", "На посту.", "Ага.", "Тут. Не переживай.",
            "Всегда на месте.", "Тут, брат. Куда ж я денусь.", "На связи, как договаривались.", "Тут. Живой."
        ])
        await send_message(context.bot, chat_id, first)
        await asyncio.sleep(random.uniform(2.0, 4.5))
        second = random.choice([
            "Держимся сегодня. Вместе.",
            "Сегодня мимо. Точно.",
            "Всё по плану. Держись.",
            "Держишь слово — уважаю.",
            "Сегодня не хочу.",
            "Не сегодня, брат.",
            "Так держать.",
            "Ты в деле.",
            "Всё под контролем.",
            "Я рядом.",
            "Терпим, хули.",
            "Ты справишься.",
            "Горжусь тобой.",
            "Всё будет нормас.",
            "Ты молодец. Реально."
        ])
        await send_message(context.bot, chat_id, second)
        return

    elif text == "💲 Сказать спасибо":
        await send_message(
            context.bot, chat_id,
            "Спасибо, брат, что оценил. ❤️\n\n"
            "Если хочешь поддержать (на Золофт, кофе или просто так):\n"
            "💳 Сбер: 2202 2084 3481 5313\n\n"
            "Главное — держись.\n"
            "Мы справимся. 💪",
            reply_markup=get_main_keyboard()
        )
        return

    elif text == "🔥 Держись!":
        if not can_broadcast_today(chat_id):
            await send_message(context.bot, chat_id, "Ты уже отправлял сегодня. Завтра снова сможешь.")
            return
        await send_message(context.bot, chat_id, "Сигнал отправлен. Ты молодец. 💪")
        for uid in get_all_active_users():
            if uid != chat_id:
                try:
                    await send_message(context.bot, uid, "💪\n\nДержитесь, ребята! Все получится.")
                    await asyncio.sleep(0.08)
                except:
                    pass
        mark_broadcast_sent(chat_id)
        return

    elif text == "😔 Тяжело":
        context.user_data['awaiting_relapse_confirm'] = True
        await send_message(context.bot, chat_id, "Брат, ты сорвался?", reply_markup=get_relapse_keyboard())
        return

    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        msg = "Первый день. Начинаем." if days == 0 else "Прошёл 1 день" if days == 1 else f"Прошло {days} дней"
        await send_message(context.bot, chat_id, msg)
        return

    elif text == "⏸ Пауза":
        await stop(update, context)
        return

    if context.user_data.get('awaiting_relapse_confirm'):
        if text == "Да":
            reset_counter(chat_id)
            await send_message(context.bot, chat_id, "Ничего страшного. Начнём снова.", reply_markup=get_main_keyboard())
        elif text == "Нет":
            await send_message(context.bot, chat_id, random.choice([
                "Красава, держись.", "Молодец, брат.", "Уважаю.", "Ты справишься."
            ]), reply_markup=get_main_keyboard())
        context.user_data['awaiting_relapse_confirm'] = False
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
