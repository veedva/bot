import logging
import random
import json
import os
import asyncio
from datetime import time, datetime
from pytz import timezone
from filelock import FileLock
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

DATA_FILE = 'user_data.json'
MOSCOW = timezone('Europe/Moscow')

# === УТРО (9:00) ===
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
    "Привет. Сегодня легко обойдёмся.",
    "Братан, доброе. Сегодня точно нет.",
    "Эй. Сегодня не в тему, согласен?",
    "Доброе утро. Давай только не сегодня.",
    "Привет. Может завтра, но сегодня нет.",
    "Утро, брат. Сегодня спокойно обходимся.",
    "Эй. Сегодня точно не стоит, да?",
    "Привет. Держимся сегодня, как договорились."
]

# === ВЕЧЕР (18:00) — с количеством дней, полностью нейтрально ===
EVENING_BASE = [
    "Брат, не сегодня. Держись.",
    "Эй, я тут. Давай не сегодня.",
    "Хочется, знаю. Но не сегодня.",
    "Привет. Сегодня держимся, помнишь?",
    "Брат, держись. Сегодня нет.",
    "Эй. Ещё чуть-чуть. Не сегодня.",
    "Я с тобой. Сегодня точно нет.",
    "Привет. Давай обойдёмся, а?",
    "Брат, мы же решили — не сегодня.",
    "Держись там. Сегодня мимо.",
    "Привет. Давай сегодня пропустим.",
    "Эй. Сегодня точно можно без этого.",
    "Братан, сегодня не надо, согласен?",
    "Привет. Может завтра, сегодня мимо.",
    "Как дела? Сегодня обойдёмся легко.",
    "Эй, брат. Давай сегодня не будем.",
    "Привет. Сегодня точно ни к чему это.",
    "Братан, ну может завтра, а сегодня нет?",
    "Эй. Сегодня спокойно можем без этого."
]

# === НОЧЬ (23:00) — с количеством дней ===
NIGHT_MESSAGES = [
    "Ты молодец. До завтра, братан.",
    "Красавчик. Спокойной ночи.",
    "Держался сегодня. Уважаю. Спи.",
    "Сегодня справились. До завтра, брат.",
    "Молодец, держишься. Спокойной ночи.",
    "Ещё один день позади. Горжусь. Спи.",
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
    "Сегодня получилось. Отдыхай.",
    "День позади. Горжусь. Отдыхай.",
    "Держался. Ты сильный. Спи."
]

# Вехи
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

# === КНОПКИ ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("📊 Дни"), KeyboardButton("⏸ Пауза")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_start_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True)

def get_relapse_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("Да"), KeyboardButton("Нет")]], resize_keyboard=True)

# === ДАННЫЕ ===
def load_user_data():
    with FileLock(DATA_FILE + ".lock"):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {}

def save_user_data(data):
    with FileLock(DATA_FILE + ".lock"):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_days_count(user_id):
    data = load_user_data()
    if str(user_id) in data and 'start_date' in data[str(user_id)]:
        start = datetime.fromisoformat(data[str(user_id)]['start_date'].replace('Z', '+00:00')).astimezone(MOSCOW)
        return (datetime.now(MOSCOW) - start).days
    return 0

def reset_counter(user_id):
    data = load_user_data()
    if str(user_id) in data:
        data[str(user_id)]['start_date'] = datetime.now(MOSCOW).isoformat()
        save_user_data(data)

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    data = load_user_data()
    if str(chat_id) not in data:
        data[str(chat_id)] = {}
    data[str(chat_id)]['start_date'] = datetime.now(MOSCOW).isoformat()
    data[str(chat_id)]['active'] = True
    save_user_data(data)

    await update.message.reply_text(
        f"Привет, {user.first_name}.\n\n"
        "Я буду писать тебе трижды в день:\n"
        "• Утром в 9:00\n"
        "• Вечером в 18:00\n"
        "• На ночь в 23:00\n\n"
        "Держимся вместе. Не сегодня.",
        reply_markup=get_main_keyboard()
    )

    # Перезапуск задач
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    context.job_queue.run_daily(send_morning_message, time(hour=9, minute=0, tzinfo=MOSCOW), chat_id=chat_id, name=f"morning_{chat_id}", data=chat_id)
    context.job_queue.run_daily(send_evening_message, time(hour=18, minute=0, tzinfo=MOSCOW), chat_id=chat_id, name=f"evening_{chat_id}", data=chat_id)
    context.job_queue.run_daily(send_night_message, time(hour=23, minute=0, tzinfo=MOSCOW), chat_id=chat_id, name=f"night_{chat_id}", data=chat_id)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_user_data()
    if str(chat_id) in data:
        data[str(chat_id)]['active'] = False
        save_user_data(data)
    await update.message.reply_text("Напоминания остановлены. Нажми ▶ Начать чтобы возобновить.", reply_markup=get_start_keyboard())

# === СООБЩЕНИЯ ===
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    if not load_user_data().get(str(chat_id), {}).get('active', True):
        return
    days = get_days_count(chat_id)
    if days in MILESTONES:
        await context.bot.send_message(chat_id=chat_id, text=MILESTONES[days])
    else:
        await context.bot.send_message(chat_id=chat_id, text=random.choice(MORNING_MESSAGES))

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    if not load_user_data().get(str(chat_id), {}).get('active', True):
        return
    days = get_days_count(chat_id)
    base = random.choice(EVENING_BASE)
    if days == 0:
        extra = "Сегодня первый день. Пошли."
    elif days == 1:
        extra = "Один день позади. Нормально начал."
    elif days < 10:
        extra = f"{days} дней подряд. Это уже серьёзно."
    elif days < 30:
        extra = f"{days} дней. Ты в деле, брат."
    elif days < 90:
        extra = f"{days} дней. Горжусь тобой."
    else:
        extra = f"{days} дней. Легенда."
    await context.bot.send_message(chat_id=chat_id, text=f"{base}\n\n{extra}")

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    if not load_user_data().get(str(chat_id), {}).get('active', True):
        return
    days = get_days_count(chat_id)
    base = random.choice(NIGHT_MESSAGES)
    extra = f"{days} дней подряд. Ты сильный. Спи спокойно."
    await context.bot.send_message(chat_id=chat_id, text=f"{base}\n\n{extra}")

# === ОБРАБОТКА КНОПОК ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "▶ Начать":
        await start(update, context)

    elif text == "👋 Ты тут?":
        first = random.choice([
            "Тут, брат.", "А куда я денусь?", "Здесь. Как всегда.", "На связи.", "Тут, братан.",
            "Конечно тут.", "Тут. Дышу ровно.", "На посту.", "Как штык.", "Тут. Не переживай.",
            "Всегда на месте.", "Тут, брат. Куда ж я денусь.", "На связи, как договаривались.", "Тут. Живой."
        ])
        await update.message.reply_text(first)
        await asyncio.sleep(random.uniform(1.9, 3.3))
        second = random.choice([
            "Держимся сегодня. Вместе.",
            "Сегодня мимо. Точно.",
            "Всё по плану. Держись.",
            "Держишь слово — уважаю.",
            "Сегодня наш день.",
            "Не сегодня, брат.",
            "Так держать.",
            "Ты в деле.",
            "Всё под контролем.",
            "Я рядом.",
            "Вместе идём.",
            "Ты справишься.",
            "Горжусь тобой.",
            "Всё будет по-нашему.",
            "Ты молодец. Реально."
        ])
        await context.bot.send_message(chat_id=chat_id, text=second)

    elif text == "😔 Тяжело":
        context.user_data['awaiting_relapse_confirm'] = True
        await update.message.reply_text("Брат, ты сорвался?", reply_markup=get_relapse_keyboard())

    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        if days == 0:
            await update.message.reply_text("Первый день. Начинаем.")
        elif days == 1:
            await update.message.reply_text("Прошёл 1 день")
        else:
            await update.message.reply_text(f"Прошло {days} дней")

    elif text == "⏸ Пауза":
        await stop(update, context)

    elif context.user_data.get('awaiting_relapse_confirm'):
        if text == "Да":
            reset_counter(chat_id)
            await update.message.reply_text("Ничего страшного. Начнём снова завтра.", reply_markup=get_main_keyboard())
        elif text == "Нет":
            await update.message.reply_text(random.choice([
                "Красава, держись.", "Молодец, брат.", "Уважаю.", "Ты справишься."
            ]), reply_markup=get_main_keyboard())
        context.user_data['awaiting_relapse_confirm'] = False

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
