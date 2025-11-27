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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

DATA_FILE = "user_data.json"
LOCK_FILE = DATA_FILE + ".lock"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =====================================================
# ТВОИ ОРИГИНАЛЬНЫЕ СООБЩЕНИЯ — ВСЁ СОХРАНЕНО
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
    return ReplyKeyboardMarkup([
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("✊ Держусь"), KeyboardButton("📊 Дни")],
        [KeyboardButton("❤️ Спасибо"), KeyboardButton("⏸ Пауза")]
    ], resize_keyboard=True)

def get_start_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True)

def get_heavy_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("Помочь себе")],
        [KeyboardButton("Срыв"), KeyboardButton("Чуть не сорвался (но держусь!)")],
        [KeyboardButton("Назад")]
    ], resize_keyboard=True)

def get_one_more_help_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("Ещё один способ"), KeyboardButton("Назад")]], resize_keyboard=True)

# =====================================================
# Техники помощи
# =====================================================
HELP_TECHNIQUES = [
    "Бери и дыши так: вдох носом на 4 секунды → задержи дыхание на 4 → выдох ртом на 4 → опять задержи на 4. Повтори 6–8 раз подряд. Через минуту мозг переключается и тяга уходит, проверено тысячу раз.",
    "Прямо сейчас падай и делай 20–30 отжиманий или приседаний до жжения в мышцах. Пока мышцы горят — башка не думает о херне.",
    "Открой кран с ледяной водой и суй туда лицо + шею на 20–30 секунд. Мозг получает шок и на несколько минут забывает про всё остальное.",
    "Выйди на балкон или просто открой окно настежь. Стоять и дышать свежим воздухом 3–5 минут. Даже если -20, всё равно выйди.",
    "Налей самый холодный стакан воды из-под крана и пей медленно-медленно, маленькими глотками. Пока пьёшь — тяга слабеет.",
    "Возьми телефон, открой заметки и напиши три вещи, за которые ты сегодня реально благодарен. Хоть «не просрал день», хоть «есть крыша над головой». Мозг переключается на позитив.",
    "Съешь что-то максимально кислое или острое: дольку лимона, ложку горчицы, кусок имбиря, чили-перец. Жжёт рот — башка забывает про тягу.",
    "Включи любой трек и просто ходи быстрым шагом по квартире 3–4 минуты. Главное — не останавливаться.",
    "Сядь на стул или на пол, выпрями спину, руки на колени, закрой глаза и просто сиди минуту молча. Ничего не делай, просто дыши. Это как перезагрузка.",
    "Делай круговые движения плечами назад-вперёд по 15 раз в каждую сторону, потом наклоны головы. Мышцы расслабляются, тревога уходит.",
    "Поставь таймер на 10 минут и говори себе: «Я просто подожду 10 минут, потом решу». В 95 % случаев через 10 минут уже не хочется.",
    "Открой камеру на телефоне, посмотри себе в глаза и скажи вслух: «Я сильнее этой хуйни». Даже если звучит тупо — работает."
]

# =====================================================
# Работа с данными
# =====================================================
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
    data[user_str]["last_broadcast"] = datetime.now().isoformat()
    save_user_data(data)

def get_all_active_users():
    data = load_user_data()
    return [int(uid) for uid, user in data.items() if user.get("active", False)]

# =====================================================
# Закреплённое сообщение
# =====================================================
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

# =====================================================
# Отправка сообщений
# =====================================================
async def send_message(bot, chat_id, text, reply_markup=None, save_for_deletion=True):
    final_markup = reply_markup or get_main_keyboard()
    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=final_markup)

    if save_for_deletion:
        data = load_user_data()
        user_str = str(chat_id)
        data[user_str].setdefault("message_ids", []).append(msg.message_id)
        save_user_data(data)
    return msg

# =====================================================
# Рассылки — твой главный инструмент
# =====================================================
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    days = get_days_count(chat_id)
    text = MILESTONES.get(days, random.choice(MORNING_MESSAGES))
    await send_message(context.bot, chat_id, text)
    await update_pinned_progress(context.bot, chat_id)

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    await send_message(context.bot, chat_id, random.choice(EVENING_MESSAGES))

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get("active", False):
        return
    await send_message(context.bot, chat_id, random.choice(NIGHT_MESSAGES))
    await update_pinned_progress(context.bot, chat_id)

async def midnight_clean_chat(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    if "message_ids" not in data.get(user_str, {}):
        return
    for msg_id in data[user_str].pop("message_ids", []):
        try:
            await context.bot.delete_message(chat_id, msg_id)
            await asyncio.sleep(0.05)
        except:
            pass
    save_user_data(data)

# =====================================================
# Старт и стоп
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_user_data()
    user_str = str(chat_id)
    if user_str not in data:
        data[user_str] = {}

    data[user_str].update({
        "start_date": datetime.now().isoformat(),
        "active": True,
        "state": "normal",
        "best_streak": data[user_str].get("best_streak", 0)
    })
    save_user_data(data)

    await send_message(
        context.bot, chat_id,
        "Привет.\n\n"
        "Я буду писать три раза в день — просто напомнить: сегодня не надо.\n\n"
        "Нажимай иногда «✊ Держусь» — так все поймут, что ты ещё в деле.\n\n"
        "Удачи, брат.",
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

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_user_data()
    user_str = str(chat_id)
    if user_str in data:
        data[user_str]["active"] = False
        data[user_str]["state"] = "normal"
        save_user_data(data)

    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    await send_message(context.bot, chat_id, "Остановлено. Нажми ▶ Начать, когда будешь готов.", get_start_keyboard(), save_for_deletion=False)

# =====================================================
# Обработка сообщений
# =====================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_str = str(chat_id)
    data = load_user_data()
    state = data.get(user_str, {}).get("state", "normal")

    # Меню "Тяжело"
    if state == "heavy_menu":
        if text == "Помочь себе":
            await send_message(context.bot, chat_id, random.choice(HELP_TECHNIQUES), get_one_more_help_keyboard(), save_for_deletion=False)
            data[user_str]["state"] = "help_mode"
            save_user_data(data)
            return
        if text == "Срыв":
            reset_counter(chat_id)
            await send_message(context.bot, chat_id, "Ничего страшного.\nНачнём заново. Ты молодец, что сказал честно.", get_main_keyboard(), save_for_deletion=False)
            await update_pinned_progress(context.bot, chat_id)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return
        if text == "Чуть не сорвался (но держусь!)":
            await send_message(context.bot, chat_id, "Красавчик. Это и есть победа. 🔥", get_main_keyboard(), save_for_deletion=False)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return
        if text == "Назад":
            await send_message(context.bot, chat_id, "Держись.", get_main_keyboard(), save_for_deletion=False)
            data[user_str]["state"] = "normal"
            save_user_data(data)
            return

    if state == "help_mode":
        if text == "Ещё один способ":
            await send_message(context.bot, chat_id, random.choice(HELP_TECHNIQUES), get_one_more_help_keyboard(), save_for_deletion=False)
            return
        if text == "Назад":
            await send_message(context.bot, chat_id, "Держись там.", get_main_keyboard(), save_for_deletion=False)
            data[user_str]["state"] = "normal"
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
            "Конечно тут.", "Тут я, тут.", "Ага.", "Привет.", "Тут. Не переживай."
        ]))
        await asyncio.sleep(random.uniform(2.0, 4.5))
        await send_message(context.bot, chat_id, random.choice([
            "Держимся сегодня.", "Сегодня кстати полегче", "Всё по плану.", "Не сегодня.",
            "Ты справишься.", "Я рядом.", "Держись.", "Все нормально будет.", "Я в деле. Ты в деле?"
        ]))
        return
    if text == "✊ Держусь":
        if not can_broadcast_today(chat_id):
            await send_message(context.bot, chat_id, "Сегодня уже отправлял. Завтра снова сможешь.")
            return
        await send_message(context.bot, chat_id, "Все правильно, держись, брат.", save_for_deletion=False)
        for uid in get_all_active_users():
            if uid != chat_id:
                try:
                    await context.bot.send_message(uid, "✊")
                    await asyncio.sleep(0.08)
                except:
                    pass
        mark_broadcast_sent(chat_id)
        return
    if text == "😔 Тяжело":
        data[user_str]["state"] = "heavy_menu"
        save_user_data(data)
        await send_message(context.bot, chat_id, "Что будем делать?", get_heavy_keyboard(), save_for_deletion=False)
        return
    if text == "📊 Дни":
        days = get_days_count(chat_id)
        msg = "Первый день." if days == 0 else "Прошёл 1 день." if days == 1 else f"Прошло {days} дней."
        await send_message(context.bot, chat_id, msg)
        return
    if text == "❤️ Спасибо":
        await send_message(context.bot, chat_id,
            "Спасибо, брат. ❤️\n\n"
            "Если хочешь поддержать:\n"
            "Сбер: 2202 2084 3481 5313\n\n"
            "Главное — держись.",
            save_for_deletion=False)
        return
    if text == "⏸ Пауза":
        await stop(update, context)
        return

# =====================================================
# Запуск
# =====================================================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен — финальная релизная версия")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
