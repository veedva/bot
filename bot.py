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
    raise ValueError("BOT_TOKEN не установлен! Установите переменную окружения BOT_TOKEN")

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
    "Доброе. Сегодня дел много, нет наверное.",
    "Привет. Сегодня обойдёмся и так пиздец.",
    "Утро. Давай только не сегодня.",
    "Привет, брат. Сегодня пожалуй что ну его нахуй знаешь.",
    "Доброе утро. Не сегодня же.",
    "Привет. Сегодня точно не надо.",
    "Доброе! Давай сегодня без этого.",
    "Утро. Денег жалко да и ну его.",
    "Привет. Сегодня легко обойдёмся.",
    "Братан, доброе. Сегодня точно нет.",
    "Эй. Сегодня не в тему.",
    "Доброе утро. Только не сегодня.",
    "Привет. Может завтра, но сегодня нет.",
    "Утро. Сегодня спокойно обходимся.",
    "Эй. Сегодня не стоит."
]

EVENING_MESSAGES = [
    "Брат, не сегодня. Держись.",
    "Эй, я тут. Давай не сегодня.",
    "Привет. Сегодня держимся, помнишь?",
    "Брат, держись. Сегодня нет.",
    "Эй. Ещё чуть-чуть. Не сегодня.",
    "Я с тобой. Сегодня точно нет.",
    "Привет. Давай обойдёмся.",
    "Брат, мы же решили — не сегодня.",
    "Держись там. Сегодня мимо.",
    "Привет. Сегодня пропустим.",
    "Эй. Сегодня точно можно без этого.",
    "Братан, сегодня не надо.",
    "Привет. Может завтра, сегодня мимо.",
    "Как дела? Сегодня обойдёмся.",
    "Эй, брат. Сегодня не будем.",
    "Привет. Сегодня точно ни к чему.",
    "Братан, ну может завтра, а сегодня нет?"
]

NIGHT_MESSAGES = [
    "Ты молодец. До завтра.",
    "Красавчик. Спокойной.",
    "Держался сегодня. Уважаю.",
    "Сегодня справились. До завтра.",
    "Молодец, держишься.",
    "Ещё один день позади.",
    "Ты сильный. До завтра.",
    "Сегодня получилось. Отдыхай.",
    "Справился. Уважение.",
    "Держался весь день. Красава.",
    "Нормально прошёл день.",
    "Сегодня справились. Отдыхай.",
    "Ещё один день прошёл. До завтра.",
    "Держались сегодня. Молодцы.",
    "День зачётный. Спокойной.",
    "Справились. До завтра.",
    "Сегодня получилось. Отдыхай."
]

MILESTONES = {
    3: "Три дня уже. Неплохо идём.",
    7: "Неделя прошла. Продолжаем.",
    14: "Две недели! Хорошо идёт.",
    30: "Месяц. Серьёзно уважаю.",
    60: "Два месяца. Сильный результат.",
    90: "Три месяца! Ты реально крутой.",
    180: "Полгода. Это впечатляет.",
    365: "Год. Легенда."
}

# =====================================================
# Клавиатуры
# =====================================================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("💪 Держитесь!"), KeyboardButton("📊 Дни")],
        [KeyboardButton("❤️ Спасибо"), KeyboardButton("⏸ Пауза")]
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
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

def save_user_data(data):
    with FileLock(LOCK_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_days_count(user_id):
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data and "start_date" in data[user_str]:
        start_date = datetime.fromisoformat(data[user_str]["start_date"])
        return (datetime.now() - start_date).days
    return 0

def reset_counter(user_id):
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        data[user_str] = {}
    data[user_str]["start_date"] = datetime.now().isoformat()
    save_user_data(data)

def can_broadcast_today(user_id):
    data = load_user_data()
    user_str = str(user_id)
    if "last_broadcast" not in data.get(user_str, {}):
        return True
    last = datetime.fromisoformat(data[user_str]["last_broadcast"])
    return last.date() < datetime.now().date()

def mark_broadcast_sent(user_id):
    data = load_user_data()
    user_str = str(user_id)
    if user_str not in data:
        data[user_str] = {}
    data[user_str]["last_broadcast"] = datetime.now().isoformat()
    save_user_data(data)

def get_all_active_users():
    data = load_user_data()
    return [int(uid) for uid, ud in data.items() if ud.get("active", False)]

# =====================================================
# Очистка чата ночью (только временные сообщения)
# =====================================================
async def midnight_clean_chat(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    if user_str not in data or "message_ids" not in data[user_str]:
        return

    message_ids = data[user_str]["message_ids"]
    data[user_str]["message_ids"] = []
    save_user_data(data)

    deleted = 0
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id, msg_id)
            deleted += 1
            await asyncio.sleep(0.05)
        except:
            pass
    logger.info(f"Очистил {deleted} сообщений у пользователя {chat_id}")

# =====================================================
# Отправка сообщений
# =====================================================
async def send_message(bot, chat_id, text, reply_markup=None, save_for_deletion=True):
    final_markup = reply_markup or get_main_keyboard()
    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=final_markup)

    if save_for_deletion:
        data = load_user_data()
        user_str = str(chat_id)
        if user_str not in data:
            data[user_str] = {}
        data[user_str].setdefault("message_ids", [])
        data[user_str]["message_ids"].append(msg.message_id)
        save_user_data(data)
    return msg

# =====================================================
# Рассылки
# =====================================================
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    if not data.get(user_str, {}).get("active", False):
        return
    days = get_days_count(chat_id)
    text = MILESTONES.get(days, random.choice(MORNING_MESSAGES))
    await send_message(context.bot, chat_id, text)

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    if not data.get(user_str, {}).get("active", False):
        return
    text = random.choice(EVENING_MESSAGES)
    await send_message(context.bot, chat_id, text)

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    if not data.get(user_str, {}).get("active", False):
        return
    text = random.choice(NIGHT_MESSAGES)
    await send_message(context.bot, chat_id, text)

# =====================================================
# Команды
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_user_data()
    user_str = str(chat_id)
    if user_str not in data:
        data[user_str] = {}

    data[user_str]["start_date"] = datetime.now().isoformat()
    data[user_str]["active"] = True
    data[user_str]["awaiting_relapse"] = False
    save_user_data(data)

    await send_message(
        context.bot, chat_id,
        "Привет.\n\n"
        "Я буду писать три раза в день, просто чтобы напомнить: сегодня — не надо.\n\n"
        "Если нажмёшь 🔥 Держитесь! — всем остальным придёт пуш. Просто чтобы знали: они не одни.\n\n"
        "Чат чистится каждую ночь. Всё строго между нами.\n\n"
        "Держись.",
        save_for_deletion=False
    )

    # Удаляем старые задачи
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    # Запускаем новые
    context.job_queue.run_daily(send_morning_message, time=time(9, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"morning_{chat_id}")
    context.job_queue.run_daily(send_evening_message, time=time(18, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"evening_{chat_id}")
    context.job_queue.run_daily(send_night_message, time=time(23, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"night_{chat_id}")
    context.job_queue.run_daily(midnight_clean_chat, time=time(0, 1, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"midnight_{chat_id}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_user_data()
    user_str = str(chat_id)
    if user_str in data:
        data[user_str]["active"] = False
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
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_str = str(chat_id)
    data = load_user_data()

    # Проверяем, ждём ли ответ на "Сорвался?"
    if data.get(user_str, {}).get("awaiting_relapse", False):
        if text == "Да":
            reset_counter(chat_id)
            await send_message(context.bot, chat_id, "Ничего страшного. Начнём снова.", reply_markup=get_main_keyboard(), save_for_deletion=False)
        elif text == "Нет":
            await send_message(context.bot, chat_id, random.choice([
                "Красава, держись.", "Молодец.", "Уважаю.", "Ты справишься.", "Так держать, брат."
            ]), reply_markup=get_main_keyboard(), save_for_deletion=False)
        
        data[user_str]["awaiting_relapse"] = False
        save_user_data(data)
        return

    # Основные кнопки
    if text == "▶ Начать":
        await start(update, context)
        return

    if text == "👋 Ты тут?":
        await asyncio.sleep(random.uniform(2.8, 5.5))
        await send_message(context.bot, chat_id, random.choice([
            "Тут.", "На связи.", "А куда я денусь?", "Здесь.", "Тут, как всегда.",
            "Конечно тут.", "Тут. Дышу.", "На посту.", "Как штык.", "Тут. Не переживай."
        ]))
        await asyncio.sleep(random.uniform(2.0, 4.5))
        await send_message(context.bot, chat_id, random.choice([
            "Держимся сегодня.", "Сегодня мимо.", "Всё по плану.", "Не сегодня.",
            "Ты справишься.", "Я рядом.", "Держись.", "Так держать.", "Ты в деле."
        ]))
        return

    if text == "❤️ Спасибо":
        await send_message(context.bot, chat_id,
            "Спасибо, брат, что оценил. ❤️\n\n"
            "Если хочешь поддержать (на Золофт, кофе или просто так):\n"
            "Сбер: 2202 2084 3481 5313\n\n"
            "Главное — держись.\n"
            "Мы справимся.",
            save_for_deletion=False
        )
        return

    if text == "💪 Держитесь!":
        if not can_broadcast_today(chat_id):
            await send_message(context.bot, chat_id, "Сегодня уже отправлял. Завтра снова сможешь.")
            return

        await send_message(context.bot, chat_id, "Спасибо, ты тоже держись!")
        emoji = random.choice(["💪", "🫶", "🤝", "✊", "🔥"])
        for uid in get_all_active_users():
            if uid != chat_id:
                try:
                    await send_message(context.bot, uid, emoji)
                    await asyncio.sleep(0.08)
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление {uid}: {e}")
        mark_broadcast_sent(chat_id)
        return

    if text == "😔 Тяжело":
        techniques = [
            "Сделай «дыхание спецназа»:\n\n• Вдох носом 4 секунды\n• Задержка 4 секунды\n• Выдох ртом 4 секунды\n• Задержка после выдоха 4 секунды\n\nПовтори 6–8 раз. Тяга уйдёт.",
            "Сделай 20 приседаний или отжиманий прямо сейчас.",
            "Включи холодную воду и подставь руки/лицо на 30 секунд.",
            "Выйди на балкон или открой окно — 5 минут свежего воздуха.",
            "Выпей стакан холодной воды медленно.",
            "Напиши в заметки 3 вещи, за которые ты сегодня благодарен.",
            "Съешь что-то кислое или острое.",
            "Походи по комнате 2 минуты быстрым шагом.",
            "Сядь ровно, выпрями спину, закрой глаза — 60 секунд.",
            "Сделай растяжку шеи и плеч — 10 кругов в каждую сторону."
        ]
        await send_message(context.bot, chat_id, random.choice(techniques))

        data[user_str]["awaiting_relapse"] = True
        save_user_data(data)

        await send_message(context.bot, chat_id, "Сорвался?", reply_markup=get_relapse_keyboard())
        return

    if text == "📊 Дни":
        days = get_days_count(chat_id)
        if days == 0:
            msg = "Первый день. Начинаем."
        elif days == 1:
            msg = "Прошёл 1 день."
        else:
            msg = f"Прошло {days} дней."
        await send_message(context.bot, chat_id, msg)
        return

    if text == "⏸ Пауза":
        await stop(update, context)
        return

# =====================================================
# Запуск б796ота
# =====================================================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен и работает")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
