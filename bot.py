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

logging.basicConfig(format='%(asctime)s — %(levelname)s — %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

DATA_FILE = "user_data.json"
LOCK_FILE = DATA_FILE + ".lock"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Сообщения
MORNING_MESSAGES = [
    "Привет. Давай сегодня не будем, хорошо?", "Доброе утро, брат. Не сегодня.", "Привет. Держимся сегодня, да?",
    "Доброе. Сегодня дел много, нет наверное.", "Привет. Сегодня обойдёмся и так пиздец.", "Утро. Давай только не сегодня.",
    "Привет, брат. Сегодня пожалуй что ну его нахуй знаешь.", "Доброе утро. Не сегодня же.", "Привет. Сегодня точно не надо.",
    "Доброе! Давай сегодня без этого.", "Утро. Денег жалко да и ну его.", "Привет. Сегодня не хочу.",
    "Братан, доброе. Сегодня точно нет.", "Эй. Сегодня не в тему.", "Доброе утро. Только не сегодня.",
    "Привет. Может завтра, но сегодня нет.", "Доброе утро, сегодня как-то meh.", "Эй. Сегодня не стоит."
]

EVENING_MESSAGES = [
    "Брат, не сегодня. Держись.", "Эй, я тут. Давай не сегодня.", "Привет. Сегодня держимся, помнишь?",
    "Брат, держись. Сегодня нет.", "Эй. Ещё чуть-чуть. Не сегодня.", "Я с тобой. Сегодня точно нет.",
    "Привет. Давай обойдёмся.", "Брат, мы же решили — не сегодня.", "Держись там. Сегодня мимо.",
    "Привет. Сегодня пропустим.", "Эй. Сегодня точно можно без этого.", "Братан, сегодня не надо.",
    "Привет. Может завтра, сегодня мимо.", "Как дела? Сегодня обойдёмся.", "Эй, брат. Сегодня не будем.",
    "Привет. Сегодня точно ни к чему.", "Братан, ну может завтра, а сегодня нет?"
]

NIGHT_MESSAGES = [
    "Ты молодец. До завтра.", "Красавчик. Спокойной.", "Держался сегодня. Уважаю.", "Сегодня справились. До завтра.",
    "Молодец, держишься.", "Ещё один день позади.", "Ты сильный. До завтра.", "Сегодня получилось. Отдыхай.",
    "Справился. Уважение.", "Держался весь день. Красава.", "Нормально прошёл день.", "Сегодня справились. Отдыхай.",
    "Ещё один день прошёл. До завтра.", "Держались сегодня. Молодцы.", "День зачётный. Спокойной.",
    "Справились. До завтра.", "Сегодня получилось. Отдыхай."
]

MILESTONES = {
    3: "Три дня уже. Неплохо идём.", 7: "Неделя прошла. Продолжаем.", 14: "Две недели! Хорошо идёт.",
    30: "Месяц. Серьёзно уважаю.", 60: "Два месяца. Сильный результат.", 90: "Три месяца! Ты реально крутой.",
    180: "Полгода. Это впечатляет.", 365: "Год. Легенда."
}

HELP_TECHNIQUES = [
    "Дыши так: вдох носом 4 сек → задержи дыхание и считай до 4 → выдох ртом 4 секунды → задержи дыхание считай до 4. Повтори 6–8 раз. Тяга уходит за минуту — работает всегда.",
    "Падай и делай 25 отжиманий или приседаний до жжения. Пока мышцы горят — мозг забывает про всё.",
    "Ледяная вода на лицо и шею — 30 секунд. Шок — и тяга отпустила.",
    "Выйди на балкон. Просто стой и дыши 3–5 минут. Даже в мороз.",
    "Пей ледяную воду медленно, маленькими глотками. Пока пьёшь — отпускает.",
    "Напиши в заметки 3 вещи, за которые сегодня благодарен. Хоть «я живой». Мозг переключается.",
    "Съешь лимон, горчицу, имбирь, перец — что угодно острое или кислое. Жжёт рот — башка молчит.",
    "Ходи быстрым шагом по квартире 3 минуты под любой трек. Главное — не стой.",
    "Сядь ровно, закрой глаза, дыши. Минута тишины — как перезагрузка.",
    "Покрути плечами, разомни шею. Напряжение уходит — тревога тоже.",
    "Поставь таймер на 10 минут и скажи: «Подожду, потом решу». В 95% случаев через 10 минут уже не надо.",
    "Посмотри в зеркало и скажи вслух: «Я сильнее этой хуйни». Да, тупо звучит. Но работает."
]

# Клавиатуры — жёстко, по-мужски
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("✊ Держусь")],
        [KeyboardButton("😔 Тяжело"), KeyboardButton("📊 Дни")],
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("⏸ Пауза")],
        [KeyboardButton("❤️ Спасибо")]
    ], resize_keyboard=True)

def get_start_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True)

def get_heavy_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Помочь себе")],
        [KeyboardButton("Срыв"), KeyboardButton("Чуть не сорвался")],
        [KeyboardButton("Назад")]
    ], resize_keyboard=True)

def get_one_more_help_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("Ещё способ"), KeyboardButton("Назад")]], resize_keyboard=True)

# Данные
def load_user_data():
    with FileLock(LOCK_FILE):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
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
        return (datetime.now() - datetime.fromisoformat(data[user_str]["start_date"])).days
    return 0

def reset_counter(user_id):
    data = load_user_data()
    user_str = str(user_id)
    current = get_days_count(user_id)
    best = data[user_str].get("best_streak", 0)
    if current > best:
        data[user_str]["best_streak"] = current
    data[user_str]["start_date"] = datetime.now().isoformat()
    save_user_data(data)

def get_all_active_users():
    return [int(uid) for uid, info in load_user_data().items() if info.get("active")]

# Закреплённое
async def update_pinned_progress(bot, chat_id):
    days = get_days_count(chat_id)
    best = load_user_data().get(str(chat_id), {}).get("best_streak", 0)
    text = f"День {days} • Лучший стрик: {best}"
    data = load_user_data()
    user_str = str(chat_id)
    pinned_id = data[user_str].get("pinned_message_id")
    try:
        if pinned_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=pinned_id, text=text)
        else:
            msg = await bot.send_message(chat_id=chat_id, text=text)
            await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
            data[user_str]["pinned_message_id"] = msg.message_id
            save_user_data(data)
    except:
        pass

# Отправка
async def send_message(bot, chat_id, text, reply_markup=None, save_for_deletion=True):
    markup = reply_markup or get_main_keyboard()
    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    if save_for_deletion:
        data = load_user_data()
        str_id = str(chat_id)
        data.setdefault(str_id, {}).setdefault("message_ids", []).append(msg.message_id)
        save_user_data(data)
    return msg

# Рассылки
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not load_user_data().get(str(chat_id), {}).get("active"):
        return
    days = get_days_count(chat_id)
    text = MILESTONES.get(days, random.choice(MORNING_MESSAGES))
    await send_message(context.bot, chat_id, text)
    await update_pinned_progress(context.bot, chat_id)

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not load_user_data().get(str(chat_id), {}).get("active"):
        return
    await send_message(context.bot, chat_id, random.choice(EVENING_MESSAGES))

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not load_user_data().get(str(chat_id), {}).get("active"):
        return
    await send_message(context.bot, chat_id, random.choice(NIGHT_MESSAGES))
    await update_pinned_progress(context.bot, chat_id)

async def midnight_clean_chat(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    ids = data.get(user_str, {}).get("message_ids", [])
    data[user_str]["message_ids"] = []
    save_user_data(data)
    for msg_id in ids:
        try:
            await context.bot.delete_message(chat_id, msg_id)
            await asyncio.sleep(0.05)
        except:
            pass

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_user_data()
    user_str = str(chat_id)
    data.setdefault(user_str, {})
    data[user_str].update({
        "start_date": datetime.now().isoformat(),
        "active": True,
        "state": "normal",
        "best_streak": data[user_str].get("best_streak", 0)
    })
    save_user_data(data)

    await send_message(context.bot, chat_id,
        "Привет, брат.\n\n"
        "Я буду писать три раза в день — просто напомню: сегодня не надо.\n\n"
        "Когда тяжело — жми «✊ Держусь».\n"
        "Все, кто тоже в деле, получат пуш. Без слов. Просто узнают, что ты ещё здесь.\n"
        "Можешь жать до 5 раз в день, если совсем пиздец.\n\n"
        "Держись.",
        save_for_deletion=False
    )
    await update_pinned_progress(context.bot, chat_id)

    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    context.job_queue.run_daily(send_morning_message, time(9, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"morning_{chat_id}")
    context.job_queue.run_daily(send_evening_message, time(18, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"evening_{chat_id}")
    context.job_queue.run_daily(send_night_message, time(23, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"night_{chat_id}")
    context.job_queue.run_daily(midnight_clean_chat, time(0, 1, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"midnight_{chat_id}")

# Держусь — до 5 раз в день, не чаще чем раз в 30 минут
async def handle_hold_button(chat_id, context):
    data = load_user_data()
    user_str = str(chat_id)
    data.setdefault(user_str, {})

    today = datetime.now().date()
    last_date = data[user_str].get("hold_date")
    last_time = data[user_str].get("hold_time")
    count = data[user_str].get("hold_count", 0)

    if str(last_date) != str(today):
        count = 0

    if last_time:
        last_dt = datetime.fromisoformat(last_time)
        if (datetime.now() - last_dt).total_seconds() < 1800:
            await send_message(context.bot, chat_id, "Погоди ещё немного, брат. Только что было.")
            return

    if count >= 5:
        await send_message(context.bot, chat_id, "Сегодня уже 5 раз. Ты реально держишься, брат. Горжусь тобой. ✊\nЗавтра снова сможешь.")
        return

    await send_message(context.bot, chat_id, random.choice([
        "Отправил. ✊", "Молодец. ✊", "Красава. ✊", "Респект. ✊", "Так держать. ✊"
    ]), save_for_deletion=False)

    for uid in get_all_active_users():
        if uid != chat_id:
            try:
                await context.bot.send_message(uid, "✊")
                await asyncio.sleep(0.08)
            except:
                pass

    data[user_str]["hold_time"] = datetime.now().isoformat()
    data[user_str]["hold_date"] = str(today)
    data[user_str]["hold_count"] = count + 1
    save_user_data(data)

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_str = str(chat_id)
    data = load_user_data()
    state = data.get(user_str, {}).get("state", "normal")

    if state == "heavy_menu":
        if text == "Помочь себе":
            await send_message(context.bot, chat_id, random.choice(HELP_TECHNIQUES), get_one_more_help_keyboard(), False)
            data[user_str]["state"] = "help_mode"
            save_user_data(data)
            return
        if text == "Срыв":
            reset_counter(chat_id)
            await send_message(context.bot, chat_id, "Ничего страшного.\nНачнём заново. Ты молодец, что сказал честно.", get_main_keyboard(), False)
            await update_pinned_progress(context.bot, chat_id)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return
        if text == "Чуть не сорвался":
            await send_message(context.bot, chat_id, "Красавчик. Это и есть победа. ✊", get_main_keyboard(), False)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return
        if text == "Назад":
            await send_message(context.bot, chat_id, "Держись.", get_main_keyboard(), False)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return

    if state == "help_mode":
        if text == "Ещё способ":
            await send_message(context.bot, chat_id, random.choice(HELP_TECHNIQUES), get_one_more_help_keyboard(), False)
            return
        if text == "Назад":
            await send_message(context.bot, chat_id, "Держись там.", get_main_keyboard(), False)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return

    if text == "▶ Начать":
        await start(update, context)
    elif text == "👋 Ты тут?":
        await asyncio.sleep(random.uniform(2.8, 5.5))
        await send_message(context.bot, chat_id, random.choice(["Тут.", "Привет.", "А куда я денусь?", "Тут, брат.", "Ага."]))
        await asyncio.sleep(random.uniform(2, 4.5))
        await send_message(context.bot, chat_id, random.choice(["Держусь.", "Я не буду.", "Борюсь.", "Все норм.", "Я рядом."]))
    elif text == "✊ Держусь":
        await handle_hold_button(chat_id, context)
    elif text == "😔 Тяжело":
        data[user_str]["state"] = "heavy_menu"
        save_user_data(data)
        await send_message(context.bot, chat_id, "Что будем делать?", get_heavy_keyboard(), False)
    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        msg = "Первый день." if days == 0 else "Прошёл 1 день." if days == 1 else f"Прошло {days} дней."
        await send_message(context.bot, chat_id, msg)
    elif text == "❤️ Спасибо":
        await send_message(context.bot, chat_id,
            "Спасибо, брат. ❤️\n\nЕсли хочешь поддержать:\nСбер 2202 2084 3481 5313\n\nГлавное — держись.",
            save_for_deletion=False)
    elif text == "⏸ Пауза":
        await stop(update, context)

# Запуск
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Кент на посту ✊")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
