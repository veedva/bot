"""
Переписанная версия бота — Вариант B (UX + аккуратная чистка кода)
Сохранены все тексты и логика, но:
- Единая reply-клавиатура (не меняется)
- Меню "Тяжело" и другие доп. меню — через InlineKeyboard (не дергают чат)
- Более надёжная отправка сообщений с обработкой ошибок и деактивацией пользователей
- Бродкаст "✊" сделан с ограничением параллелизма
- Центральная функция отправки send_safe
- Состояния хранятся в JSON, но код подготовлен к миграции на SQLite
- CallbackQueryHandler для inline-кнопок

Примечание: этот файл оставляет JSON как хранилище по желанию (вариант B). Для больших нагрузок рекомендую миграцию на SQLite (вариант C).
"""

import logging
import random
import json
import os
import asyncio
from datetime import datetime, date, time as dtime
from filelock import FileLock
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import pytz

logging.basicConfig(format='%(asctime)s — %(levelname)s — %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

DATA_FILE = "user_data.json"
LOCK_FILE = DATA_FILE + ".lock"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# ----- Контент (оставлен как у тебя, можно править) -----
MORNING_MESSAGES = [
    "Привет. Давай сегодня не будем, хорошо?", "Доброе утро, брат. Не сегодня.", "Привет. Держимся сегодня, да?",
    "Доброе. Сегодня дел много, нет наверное.", "Привет. Держимся сегодня, да?", "Утро. Давай только не сегодня."
]
EVENING_MESSAGES = [
    "Брат, не сегодня. Держись.", "Эй, я тут. Давай не сегодня.", "Привет. Сегодня держимся, помнишь?",
    "Брат, держись. Сегодня нет.", "Эй. Ещё чуть-чуть. Не сегодня."
]
NIGHT_MESSAGES = [
    "Ты молодец. До завтра.", "Красавчик. Спокойной.", "Держался сегодня. Уважаю.", "Сегодня справились. До завтра."
]
MILESTONES = {3: "Три дня уже. Неплохо идём.", 7: "Неделя прошла. Продолжаем.", 14: "Две недели! Хорошо идёт.",
              30: "Месяц. Серьёзно уважаю.", 60: "Два месяца. Сильный результат.", 90: "Три месяца! Ты реально крутой.",
              180: "Полгода. Это впечатляет.", 365: "Год. Легенда."}

HELP_TECHNIQUES = [
    "Дыши так: вдох носом 4 сек → задержи 4 → выдох ртом 4 → задержи 4. 6–8 раз.",
    "Падай и делай 25 отжиманий или приседаний до жжения.",
    "Ледяная вода на лицо и шею — 30 секунд.",
    "Выйди на балкон. Просто стой и дыши 3–5 минут.",
    "Пей ледяную воду медленно, маленькими глотками.",
    "Напиши в заметки 3 вещи, за которые сегодня благодарен.",
    "Съешь лимон, горчицу, имбирь, перец — что угодно острое или кислое.",
    "Ходи быстрым шагом по квартире 3 минуты под любой трек.",
    "Сядь ровно, закрой глаза, дыши. Минута тишины — как перезагрузка.",
    "Поставь таймер на 10 минут и скажи: «Подожду, потом решу»."
]

# ----- Новая единая reply-клавиатура (не меняется) -----
REPLY_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("👋 Ты тут?"), KeyboardButton("✊ Держусь")],
    [KeyboardButton("😔 Тяжело"), KeyboardButton("📊 Дни")],
    [KeyboardButton("⏸ Пауза")]
], resize_keyboard=True)

# ----- Inline клавиатуры (динамически создаются) -----
def heavy_menu_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Помочь себе", callback_data="help_self")],
        [InlineKeyboardButton("Срыв", callback_data="relapse"), InlineKeyboardButton("Чуть не сорвался", callback_data="almost")],
        [InlineKeyboardButton("Назад", callback_data="back")]
    ])

def one_more_help_inline():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Ещё способ", callback_data="more_help")], [InlineKeyboardButton("Назад", callback_data="back")]])

# ----- Работа с данными (пока JSON с блокировкой) -----

def load_user_data():
    with FileLock(LOCK_FILE):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.exception("Ошибка чтения данных, возвращаю пустой словарь: %s", e)
                return {}
        return {}


def save_user_data(data):
    with FileLock(LOCK_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ----- Вспомогательные функции -----

def get_days_count(user_id):
    data = load_user_data()
    user_str = str(user_id)
    if user_str in data and "start_date" in data[user_str]:
        try:
            start = datetime.fromisoformat(data[user_str]["start_date"])
            return (datetime.now() - start).days
        except Exception:
            return 0
    return 0


def reset_counter(user_id):
    data = load_user_data()
    user_str = str(user_id)
    current = get_days_count(user_id)
    best = data.get(user_str, {}).get("best_streak", 0)
    if current > best:
        data.setdefault(user_str, {})["best_streak"] = current
    data.setdefault(user_str, {})["start_date"] = datetime.now().isoformat()
    save_user_data(data)


def get_all_active_users():
    return [int(uid) for uid, info in load_user_data().items() if info.get("active")]

# ----- Отправка сообщений с обработкой ошибок -----

async def send_safe(bot, chat_id, text, reply_markup=None, save_for_deletion=True):
    """Отправляет сообщение, аккуратно обрабатывает ошибки и деактивирует юзера при запрете"""
    markup = reply_markup or REPLY_KEYBOARD
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        if save_for_deletion:
            data = load_user_data()
            str_id = str(chat_id)
            data.setdefault(str_id, {}).setdefault("message_ids", []).append(msg.message_id)
            save_user_data(data)
        return msg
    except Exception as e:
        # Если ошибка — возможно пользователь заблокировал бота
        logger.warning("Не удалось отправить сообщение %s: %s", chat_id, e)
        # Пробуем пометить пользователя неактивным
        try:
            data = load_user_data()
            if str(chat_id) in data:
                data[str(chat_id)]["active"] = False
                save_user_data(data)
        except Exception:
            logger.exception("Ошибка при попытке обновить статус пользователя")
        return None

# ----- Обновление закрепленного прогресса (без ошибок) -----
async def update_pinned_progress(bot, chat_id):
    days = get_days_count(chat_id)
    best = load_user_data().get(str(chat_id), {}).get("best_streak", 0)
    text = f"День {days} • Лучший стрик: {best}"
    data = load_user_data()
    user_str = str(chat_id)
    pinned_id = data.get(user_str, {}).get("pinned_message_id")
    try:
        if pinned_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=pinned_id, text=text)
        else:
            msg = await bot.send_message(chat_id=chat_id, text=text)
            try:
                await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
                data.setdefault(user_str, {})["pinned_message_id"] = msg.message_id
                save_user_data(data)
            except Exception:
                # Если не получилось запинить — не фатально
                pass
    except Exception:
        logger.exception("Ошибка при обновлении pinned progress")

# ----- Job callbacks (утро/вечер/ночь/очистка) -----
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not load_user_data().get(str(chat_id), {}).get("active"):
        return
    days = get_days_count(chat_id)
    text = MILESTONES.get(days, random.choice(MORNING_MESSAGES))
    await send_safe(context.bot, chat_id, text)
    await update_pinned_progress(context.bot, chat_id)

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not load_user_data().get(str(chat_id), {}).get("active"):
        return
    await send_safe(context.bot, chat_id, random.choice(EVENING_MESSAGES))

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not load_user_data().get(str(chat_id), {}).get("active"):
        return
    await send_safe(context.bot, chat_id, random.choice(NIGHT_MESSAGES))
    await update_pinned_progress(context.bot, chat_id)

async def midnight_clean_chat(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    user_str = str(chat_id)
    ids = data.get(user_str, {}).get("message_ids", [])
    data.setdefault(user_str, {})["message_ids"] = []
    save_user_data(data)
    for msg_id in ids:
        try:
            await context.bot.delete_message(chat_id, msg_id)
            await asyncio.sleep(0.02)
        except Exception:
            pass

# ----- Handlers -----
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

    await send_safe(context.bot, chat_id,
        "Привет, брат.\n\nЯ буду писать три раза в день, чтобы просто напомнить: сегодня не надо.\n\nКогда тяжело — жми «✊ Держусь».\nТе, кто тоже борятся — получат пуш. Увидят, что ты есть и не сдаешься.",
        save_for_deletion=False)
    await update_pinned_progress(context.bot, chat_id)

    # Удаляем старые джобы
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}", f"midnight_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    context.job_queue.run_daily(send_morning_message, dtime(9, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"morning_{chat_id}")
    context.job_queue.run_daily(send_evening_message, dtime(18, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"evening_{chat_id}")
    context.job_queue.run_daily(send_night_message, dtime(23, 0, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"night_{chat_id}")
    context.job_queue.run_daily(midnight_clean_chat, dtime(0, 1, tzinfo=MOSCOW_TZ), chat_id=chat_id, name=f"midnight_{chat_id}")

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

    await send_safe(context.bot, chat_id, "Остановлено. Жми ▶ Начать, когда будешь готов.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("▶ Начать")]], resize_keyboard=True), save_for_deletion=False)

# ----- Обработка "держусь" — теперь с ограниченным параллелизмом -----
BROADCAST_CONCURRENCY = 12  # одновременных отправок при бродкасте

async def broadcast_hold(context, origin_chat_id):
    users = get_all_active_users()
    sem = asyncio.Semaphore(BROADCAST_CONCURRENCY)
    async def send_to(uid):
        if uid == origin_chat_id:
            return
        async with sem:
            try:
                await context.bot.send_message(uid, "✊")
            except Exception:
                # тихо игнорируем — send_safe при следующей отправке пометит неактивным
                pass
    await asyncio.gather(*(send_to(u) for u in users))

async def handle_hold_button(chat_id, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_str = str(chat_id)
    data.setdefault(user_str, {})

    today = date.today()
    last_date = data[user_str].get("hold_date")
    last_time = data[user_str].get("hold_time")
    count = data[user_str].get("hold_count", 0)

    if str(last_date) != str(today):
        count = 0

    if last_time:
        try:
            last_dt = datetime.fromisoformat(last_time)
            if (datetime.now() - last_dt).total_seconds() < 1800:
                await send_safe(context.bot, chat_id, "Погоди ещё немного, брат. Только что было.")
                return
        except Exception:
            pass

    if count >= 5:
        await send_safe(context.bot, chat_id, "Сегодня это уже 5 раз. ✊\nЗавтра снова сможешь.")
        return

    await send_safe(context.bot, chat_id, random.choice(["Отправлено, молодец! ✊", "Горжусь! ✊", "Красава. ✊"]))

    # Бродкаст с ограничением параллелизма
    try:
        await broadcast_hold(context, chat_id)
    except Exception:
        logger.exception("Ошибка при бродкасте держимся")

    data[user_str]["hold_time"] = datetime.now().isoformat()
    data[user_str]["hold_date"] = str(today)
    data[user_str]["hold_count"] = count + 1
    save_user_data(data)

# ----- Обработка текстовых сообщений (основная клавиатура не меняется) -----
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_str = str(chat_id)
    data = load_user_data()
    state = data.get(user_str, {}).get("state", "normal")

    # Вариант: при переходе в heavy меню показываем inline-клавиатуру
    if text == "▶ Начать":
        await start(update, context)
        return
    if text == "👋 Ты тут?":
        await asyncio.sleep(random.uniform(0.8, 2.0))
        await send_safe(context.bot, chat_id, random.choice(["Тут.", "Привет.", "Тут, брат."]))
        await asyncio.sleep(random.uniform(0.4, 1.3))
        await send_safe(context.bot, chat_id, random.choice(["Не сдаюсь.", "Держусь.", "Мы справимся."]))
        return
    if text == "✊ Держусь":
        await handle_hold_button(chat_id, context)
        return
    if text == "😔 Тяжело":
        # Поменяли на inline-меню
        await send_safe(context.bot, chat_id, "Что будем делать?", reply_markup=heavy_menu_inline(), save_for_deletion=False)
        data.setdefault(user_str, {})["state"] = "heavy_menu"
        save_user_data(data)
        return
    if text == "📊 Дни":
        days = get_days_count(chat_id)
        msg = "Первый день." if days == 0 else "Прошёл 1 день." if days == 1 else f"Прошло {days} дней."
        await send_safe(context.bot, chat_id, msg)
        return
    if text == "❤️ Спасибо":
        await send_safe(context.bot, chat_id,
            "Спасибо, брат. ❤️\n\nЕсли хочешь поддержать:\nСбер 2202 2084 3481 5313\n\nГлавное — держись.",
            save_for_deletion=False)
        return
    if text == "⏸ Пауза":
        await stop(update, context)
        return

    # Фоллбэк — подсказываем, что есть кнопки
    await send_safe(context.bot, chat_id, "Я тут, брат. Нажми на кнопки внизу — они помогут.")

# ----- CallbackQueryHandler для inline кнопок -----
async def handle_callback(query, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    chat_id = query.message.chat.id
    user_str = str(chat_id)
    state = data.get(user_str, {}).get("state", "normal")

    await query.answer()
    code = query.data

    if code == "help_self":
        # покажем технику
        await query.message.reply_text(random.choice(HELP_TECHNIQUES), reply_markup=one_more_help_inline())
        data.setdefault(user_str, {})["state"] = "help_mode"
        save_user_data(data)
        return
    if code == "more_help":
        await query.message.reply_text(random.choice(HELP_TECHNIQUES), reply_markup=one_more_help_inline())
        return
    if code == "relapse":
        reset_counter(chat_id)
        await query.message.reply_text("Ничего страшного.\nНачнём заново. Ты молодец, что сказал честно.", reply_markup=REPLY_KEYBOARD)
        await update_pinned_progress(context.bot, chat_id)
        data.setdefault(user_str, {})["state"] = "normal"
        save_user_data(data)
        return
    if code == "almost":
        await query.message.reply_text("Красавчик. Это и есть победа. ✊", reply_markup=REPLY_KEYBOARD)
        data.setdefault(user_str, {})["state"] = "normal"
        save_user_data(data)
        return
    if code == "back":
        await query.message.reply_text("Держись.", reply_markup=REPLY_KEYBOARD)
        data.setdefault(user_str, {})["state"] = "normal"
        save_user_data(data)
        return

# ----- Запуск приложения -----

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("Кент на посту ✊ — Вариант B")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
