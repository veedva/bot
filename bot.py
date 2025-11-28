import logging
import random
import json
import os
import asyncio
from datetime import datetime, time
from filelock import FileLock
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import pytz

logging.basicConfig(
    format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

DATA_FILE = "user_data.json"
LOCK_FILE = DATA_FILE + ".lock"
MOSCOW_TZ = pytz.timezone("Europe/Moscow")
NOW = lambda: datetime.now(MOSCOW_TZ)

# Сообщения
MORNING_MESSAGES = [
    "Привет. Давай сегодня не будем, хорошо?",
    "Доброе утро, брат. Не сегодня.",
    "Привет. Держимся сегодня, да?",
    "Доброе. Сегодня дел много, нет наверное.",
    "Привет. Сегодня обойдёмся и так пиздец.",
    "Утро. Давай только не сегодня.",
    "Привет, брат. Сегодня пожалуй что ну его нахуй, знаешь.",
    "Доброе утро. НУ не прям сегодня же.",
    "Привет. Сегодня точно не надо.",
    "Доброе! Давай сегодня без этого.",
    "Утро. Денег жалко, да и ну его.",
    "Привет. Сегодня легко обойдёмся и без этого.",
    "Братан, доброе. Сегодня точно нет.",
    "Эй. Сегодня не в тему.",
    "Доброе утро. Только не сегодня.",
    "Привет. Может завтра, но сегодня нет.",
    "Утро. Сегодня спокойно обходимся.",
    "Че как? Сегодня не стоит пожалуй."
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
    30: "Месяц. Серьёзно, уважаю.",
    60: "Два месяца. Сильный результат.",
    90: "Три месяца! Ты реально крутой.",
    180: "Полгода. Это впечатляет.",
    365: "Год. Легенда."
}

HELP_TECHNIQUES = [
    "Бери и дыши так по кругу: вдох носом 4 секунды → задержи дыхание считая до 4 → выдох ртом 4 секунды → не дыши 4 секунды. Повтори 6–8 раз подряд. Через минуту мозг переключается и тяга уходит, проверено тысячу раз.",
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

TU_TUT_FIRST = ["Тут.", "Привет.", "А куда я денусь?", "Здесь.", "Тут, как всегда.", "Да, да, привет.", "Че как?", "Ага.", "Здраствуй.", "Тут. Не переживай."]
TU_TUT_SECOND = ["Держимся.", "Я с тобой.", "Всё по плану?", "Не хочу сегодня.", "Сегодня не буду.", "Я рядом.", "Держись.", "Все будет нормально.", "Я в деле.", "Всё под контролем."]

HOLD_RESPONSES = ["Отправлено. ✊", "Молодец. ✊", "Красава. ✊", "Респект. ✊", "Так держать. ✊"]

# ----------------------- Работа с данными -----------------------
def load_data():
    with FileLock(LOCK_FILE):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

def save_data(data):
    with FileLock(LOCK_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "start_date": NOW().isoformat(),
            "active": False,
            "state": "normal",
            "best_streak": 0,
            "hold_count": 0,
            "hold_date": None,
            "hold_time": None,
            "used_tips": [],
            "menu_message_id": None,
            "pinned_message_id": None,
        }
        save_data(data)
    return data, data[uid]

def get_days(user_id):
    _, user = get_user(user_id)
    if user.get("start_date"):
        start = datetime.fromisoformat(user["start_date"])
        return (NOW() - start).days
    return 0

def reset_streak(user_id):
    data, user = get_user(user_id)
    current = get_days(user_id)
    if current > user.get("best_streak", 0):
        user["best_streak"] = current
    user["start_date"] = NOW().isoformat()
    user["hold_count"] = 0
    user["hold_date"] = None
    user["hold_time"] = None
    save_data(data)

def get_next_tip(user_data: dict) -> str:
    used = user_data.setdefault("used_tips", [])
    if len(used) >= len(HELP_TECHNIQUES):
        used.clear()
    available = [i for i in range(len(HELP_TECHNIQUES)) if i not in used]
    choice = random.choice(available)
    used.append(choice)
    return HELP_TECHNIQUES[choice]

# ----------------------- Отправка сообщений -----------------------
async def send(bot, chat_id, text, reply_markup=None, save_message=False):
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")
    if save_message:
        data, user = get_user(chat_id)
        user.setdefault("menu_message_id", msg.message_id)
        save_data(data)
    return msg

async def update_pin(bot, chat_id):
    days = get_days(chat_id)
    _, user = get_user(chat_id)
    best = user.get("best_streak", 0)
    text = f"Первый день • Лучший стрик: {best}" if days == 0 else f"День {days} • Лучший стрик: {best}"
    pin_id = user.get("pinned_message_id")
    try:
        if pin_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=pin_id, text=text)
        else:
            msg = await bot.send_message(chat_id, text)
            await bot.pin_chat_message(chat_id, msg.message_id, disable_notification=True)
            data, _ = get_user(chat_id)
            data[str(chat_id)]["pinned_message_id"] = msg.message_id
            save_data(data)
    except Exception as e:
        logger.warning(f"Ошибка pin для {chat_id}: {e}")

# ----------------------- Inline меню -----------------------
def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("✊ Держусь", callback_data="hold"),
            InlineKeyboardButton("😔 Тяжело", callback_data="heavy"),
        ],
        [
            InlineKeyboardButton("📊 Дни", callback_data="days"),
            InlineKeyboardButton("👋 Ты тут?", callback_data="tu_tut"),
        ],
        [
            InlineKeyboardButton("❤️ Спасибо", callback_data="thanks"),
            InlineKeyboardButton("⏸ Пауза", callback_data="pause"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_heavy_menu():
    keyboard = [
        [
            InlineKeyboardButton("💪 Помочь себе", callback_data="help"),
            InlineKeyboardButton("😅 Чуть не сорвался", callback_data="almost"),
        ],
        [
            InlineKeyboardButton("😞 Срыв", callback_data="fail"),
            InlineKeyboardButton("↩️ Назад", callback_data="back"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_help_menu():
    keyboard = [
        [
            InlineKeyboardButton("🔄 Ещё способ", callback_data="next_tip"),
        ],
        [
            InlineKeyboardButton("↩️ Назад", callback_data="back_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------------- Работа с пушами -----------------------
async def push_message(bot, chat_id, messages):
    _, user = get_user(chat_id)
    if not user.get("active"):
        return
    msg = random.choice(messages)
    await send(bot, chat_id, msg)

async def morning_job(context):
    for uid in get_active_users():
        await push_message(context.bot, uid, MORNING_MESSAGES)
        await update_pin(context.bot, uid)

async def evening_job(context):
    for uid in get_active_users():
        await push_message(context.bot, uid, EVENING_MESSAGES)

async def night_job(context):
    for uid in get_active_users():
        await push_message(context.bot, uid, NIGHT_MESSAGES)
        await update_pin(context.bot, uid)

def get_active_users():
    return [int(uid) for uid, u in load_data().items() if u.get("active")]

# ----------------------- Обработка Callback -----------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data, user = get_user(chat_id)
    state = user.get("state", "normal")
    
    if query.data == "hold":
        await query.message.edit_text("✊ Держишься. Молодец!", reply_markup=get_main_menu())
    elif query.data == "heavy":
        user["state"] = "heavy_menu"
        save_data(data)
        await query.message.edit_text("Что будем делать?", reply_markup=get_heavy_menu())
    elif query.data == "days":
        days = get_days(chat_id)
        best = user.get("best_streak", 0)
        msg = "Первый день." if days == 0 else "Прошёл 1 день." if days == 1 else f"Прошло {days} дней."
        if best > 0 and best != days:
            msg += f"\n\nТвой лучший стрик: {best} дней."
        await query.message.edit_text(msg, reply_markup=get_main_menu())
    elif query.data == "tu_tut":
        await query.message.edit_text(random.choice(TU_TUT_FIRST) + "\n" + random.choice(TU_TUT_SECOND), reply_markup=get_main_menu())
    elif query.data == "thanks":
        await query.message.edit_text(
            "Спасибо, брат. ❤️\n\nЕсли хочешь поддержать:\nСбер 2202 2084 3481 5313\n\nГлавное — держись.",
            reply_markup=get_main_menu()
        )
    elif query.data == "pause":
        user["active"] = False
        save_data(data)
        await query.message.edit_text("Уведомления приостановлены. Жми ▶ Начать, когда будешь готов.", reply_markup=None)
    elif query.data == "help":
        user["state"] = "help_mode"
        save_data(data)
        tip = get_next_tip(user)
        await query.message.edit_text(tip, reply_markup=get_help_menu())
    elif query.data == "almost":
        await query.message.edit_text("Братан, держись. Помни: каждый день важно продержаться.", reply_markup=get_main_menu())
    elif query.data == "fail":
        reset_streak(chat_id)
        await query.message.edit_text("Ничего страшного.\nНачнём заново. Ты молодец, что сказал честно.", reply_markup=get_main_menu())
    elif query.data == "back":
        user["state"] = "normal"
        save_data(data)
        await query.message.edit_text("Держись.", reply_markup=get_main_menu())
    elif query.data == "next_tip":
        tip = get_next_tip(user)
        await query.message.edit_text(tip, reply_markup=get_help_menu())
    elif query.data == "back_main":
        user["state"] = "normal"
        save_data(data)
        await query.message.edit_text("Держись.", reply_markup=get_main_menu())

# ----------------------- Старт и остановка -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data, user = get_user(chat_id)
    user["active"] = True
    user["state"] = "normal"
    save_data(data)
    
    # Приветствие
    await send(context.bot, chat_id,
        "Привет, брат.\n\n"
        "Я буду писать три раза в день — просто напомнить: сегодня не надо.\n\n"
        "Когда тяжело — жми «✊ Держусь».\n"
        "Все получат пуш. Просто узнают, что ты ещё здесь.\n"
        "Можешь жать до 5 раз в день, если совсем пиздец.\n\n"
        "Держись, я рядом.",
        reply_markup=None
    )
    # Меню «че как?»
    await send(context.bot, chat_id, "че как?", reply_markup=get_main_menu(), save_message=True)

# ----------------------- Ошибки -----------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

# ----------------------- Планирование -----------------------
def schedule_jobs(app):
    app.job_queue.run_daily(morning_job, time(9, 0, tzinfo=MOSCOW_TZ))
    app.job_queue.run_daily(evening_job, time(18, 0, tzinfo=MOSCOW_TZ))
    app.job_queue.run_daily(night_job, time(23, 0, tzinfo=MOSCOW_TZ))

# ----------------------- Основной запуск -----------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)
    schedule_jobs(app)
    logger.info("Кент на посту ✊")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
