import logging
import random
import json
import os
import asyncio
from datetime import time, datetime
from collections import defaultdict
from filelock import FileLock
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Ошибка: переменная окружения BOT_TOKEN не установлена!")

DATA_FILE = 'user_data.json'
LOCK_FILE = DATA_FILE + '.lock'
DELETE_DELAY = 10  # секунды до удаления сообщения

# =====================================================
# Сообщения и вехи
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
    "Привет. Сегодня легко обойдёмся.",
    "Братан, доброе. Сегодня точно нет.",
    "Эй. Сегодня не в тему, согласен?",
    "Доброе утро. Давай только не сегодня.",
    "Привет. Может завтра, но сегодня нет.",
    "Утро, брат. Сегодня спокойно обходимся.",
    "Эй. Сегодня точно не стоит, да?"
]

EVENING_MESSAGES = [
    "Брат, не сегодня. Держись.",
    "Эй, я тут. Давай не сегодня.",
    "Хочется, знаю. Но не сегодня.",
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

TU_TUT_RESPONSES = [
    ["Тут, брат.", "Держимся."],
    ["На связи.", "Сегодня мимо."],
    ["Конечно тут.", "Ты справишься."],
    ["Здесь.", "Горжусь тобой."],
    ["Я с тобой."],
    ["Тут, держусь.", "Ты тоже держись."],
    ["Здесь, брат. 💪"],
    ["На месте.", "Не сегодня, помнишь?"],
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
# Кнопки
# =====================================================
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("🔥 Держусь!"), KeyboardButton("📊 Дни")],
        [KeyboardButton("⏸ Пауза")]
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
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {}

def save_user_data(data):
    with FileLock(LOCK_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_days_count(user_id):
    data = load_user_data()
    if str(user_id) in data and 'start_date' in data[str(user_id)]:
        start_date = datetime.fromisoformat(data[str(user_id)]['start_date'])
        days = (datetime.now() - start_date).days
        return days
    return 0

def reset_counter(user_id):
    data = load_user_data()
    if str(user_id) in data:
        data[str(user_id)]['start_date'] = datetime.now().isoformat()
        save_user_data(data)

def can_broadcast_today(user_id):
    data = load_user_data()
    if str(user_id) not in data:
        return True
    last_broadcast = data[str(user_id)].get('last_broadcast')
    if not last_broadcast:
        return True
    last_date = datetime.fromisoformat(last_broadcast).date()
    today = datetime.now().date()
    return last_date < today

def mark_broadcast_sent(user_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    data[str(user_id)]['last_broadcast'] = datetime.now().isoformat()
    save_user_data(data)

def get_all_active_users():
    data = load_user_data()
    active_users = []
    for user_id, user_data in data.items():
        if user_data.get('active', False):
            active_users.append(int(user_id))
    return active_users

def store_message_id(user_id, message_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    if 'message_ids' not in data[str(user_id)]:
        data[str(user_id)]['message_ids'] = []
    data[str(user_id)]['message_ids'].append(message_id)
    data[str(user_id)]['message_ids'] = data[str(user_id)]['message_ids'][-50:]
    save_user_data(data)

def save_welcome_message_id(user_id, message_id):
    data = load_user_data()
    if str(user_id) not in data:
        data[str(user_id)] = {}
    data[str(user_id)]['welcome_message_id'] = message_id
    save_user_data(data)

def delete_old_welcome(user_id):
    data = load_user_data()
    if str(user_id) in data:
        return data[str(user_id)].pop('welcome_message_id', None)
    return None

def get_and_clear_message_ids(user_id):
    data = load_user_data()
    if str(user_id) in data and 'message_ids' in data[str(user_id)]:
        ids = data[str(user_id)]['message_ids']
        data[str(user_id)]['message_ids'] = []
        save_user_data(data)
        return ids
    return []

# =====================================================
# Управление автоделитом
# =====================================================
delete_tasks = defaultdict(list)

async def send_with_autodelete(bot, chat_id, text, reply_markup=None, keep_keyboard=False):
    # Сохраняем клавиатуру на последнем сообщении
    if keep_keyboard:
        reply_markup = get_main_keyboard()

    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    
    # Сохраняем ID для удаления
    store_message_id(chat_id, msg.message_id)

    # Отменяем старые задачи для этого чата
    for task in delete_tasks[chat_id]:
        if not task.done():
            task.cancel()

    async def delete_task():
        await asyncio.sleep(DELETE_DELAY)
        try:
            await bot.delete_message(chat_id, msg.message_id)
            # Удаляем из данных
            data = load_user_data()
            if str(chat_id) in data and 'message_ids' in data[str(chat_id)]:
                if msg.message_id in data[str(chat_id)]['message_ids']:
                    data[str(chat_id)]['message_ids'].remove(msg.message_id)
                    save_user_data(data)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение {msg.message_id}: {e}")

    task = asyncio.create_task(delete_task())
    delete_tasks[chat_id].append(task)
    delete_tasks[chat_id] = [t for t in delete_tasks[chat_id] if not t.done()]

    return msg

async def clean_chat(bot, chat_id):
    for task in delete_tasks.get(chat_id, []):
        if not task.done():
            task.cancel()
    delete_tasks[chat_id] = []

    message_ids = get_and_clear_message_ids(chat_id)
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except:
            pass

    old_welcome = delete_old_welcome(chat_id)
    if old_welcome:
        try:
            await bot.delete_message(chat_id, old_welcome)
        except:
            pass

# =====================================================
# Напоминания
# =====================================================
async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get('active', True):
        return
    days = get_days_count(chat_id)
    text = MILESTONES.get(days, random.choice(MORNING_MESSAGES))
    await send_with_autodelete(context.bot, chat_id, text, keep_keyboard=True)
    logger.info(f"Утреннее сообщение отправлено пользователю {chat_id}")

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get('active', True):
        return
    text = random.choice(EVENING_MESSAGES)
    await send_with_autodelete(context.bot, chat_id, text, keep_keyboard=True)
    logger.info(f"Вечернее сообщение отправлено пользователю {chat_id}")

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_user_data()
    if not data.get(str(chat_id), {}).get('active', True):
        return
    text = random.choice(NIGHT_MESSAGES)
    await send_with_autodelete(context.bot, chat_id, text, keep_keyboard=True)
    logger.info(f"Ночное сообщение отправлено пользователю {chat_id}")

# =====================================================
# Команды
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await clean_chat(context.bot, chat_id)

    msg_text = "Привет.\nЯ буду писать тебе время от времени. Диалоги стираются, не переживай.\n\nДержись. Не сегодня."
    msg = await send_with_autodelete(context.bot, chat_id, msg_text, keep_keyboard=True)
    save_welcome_message_id(chat_id, msg.message_id)

    data = load_user_data()
    if str(chat_id) not in data:
        data[str(chat_id)] = {}
    data[str(chat_id)]['start_date'] = data[str(chat_id)].get('start_date', datetime.now().isoformat())
    data[str(chat_id)]['active'] = True
    data[str(chat_id)]['message_ids'] = []
    save_user_data(data)

    # Удаляем старые задания
    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    context.job_queue.run_daily(send_morning_message, time=time(hour=9, minute=0), chat_id=chat_id, name=f"morning_{chat_id}")
    context.job_queue.run_daily(send_evening_message, time=time(hour=18, minute=0), chat_id=chat_id, name=f"evening_{chat_id}")
    context.job_queue.run_daily(send_night_message, time=time(hour=23, minute=0), chat_id=chat_id, name=f"night_{chat_id}")

    logger.info(f"Пользователь {chat_id} запустил бота")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await clean_chat(context.bot, chat_id)

    data = load_user_data()
    if str(chat_id) in data:
        data[str(chat_id)]['active'] = False
        save_user_data(data)

    for name in [f"morning_{chat_id}", f"evening_{chat_id}", f"night_{chat_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    await send_with_autodelete(context.bot, chat_id, "Напоминания остановлены. Нажми ▶ Начать чтобы возобновить.", keep_keyboard=True)
    logger.info(f"Пользователь {chat_id} остановил бота")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    reset_counter(chat_id)
    await send_with_autodelete(context.bot, chat_id, "Счётчик обнулён. Начинаем заново.", keep_keyboard=True)
    logger.info(f"Пользователь {chat_id} сбросил счётчик")

# =====================================================
# Обработка сообщений
# =====================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id

    if text in ["▶ Начать", "⏸ Пауза"]:
        await clean_chat(context.bot, chat_id)
        try: await update.message.delete()
        except: pass

    if text == "▶ Начать":
        await start(update, context)

    elif text == "👋 Ты тут?":
        responses = random.choice(TU_TUT_RESPONSES)
        for i, resp in enumerate(responses):
            if i > 0:
                await asyncio.sleep(random.uniform(1.0, 2.0))
            await send_with_autodelete(context.bot, chat_id, resp, keep_keyboard=True)

    elif text == "🔥 Держусь!":
        if not can_broadcast_today(chat_id):
            await send_with_autodelete(context.bot, chat_id, "Ты уже отправил сигнал сегодня. Завтра снова сможешь.", keep_keyboard=True)
            return

        await send_with_autodelete(context.bot, chat_id, "Сигнал отправлен. Ты молодец! 💪", keep_keyboard=True)

        all_users = get_all_active_users()
        for user_id in all_users:
            if user_id != chat_id:
                try:
                    await context.bot.send_message(user_id, "💪\n\nКто-то справляется. Ты тоже можешь.", reply_markup=get_main_keyboard())
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        mark_broadcast_sent(chat_id)

    elif text == "😔 Тяжело":
        context.user_data['awaiting_relapse_confirm'] = True
        await send_with_autodelete(context.bot, chat_id, "Брат, ты сорвался?", reply_markup=get_relapse_keyboard(), keep_keyboard=True)

    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        msg_text = "Первый день. Начинаем." if days==0 else f"Прошло {days} дней" if days>1 else "Прошёл 1 день"
        await send_with_autodelete(context.bot, chat_id, msg_text, keep_keyboard=True)

    elif text == "⏸ Пауза":
        await stop(update, context)

    elif context.user_data.get('awaiting_relapse_confirm'):
        if text == "Да":
            reset_counter(chat_id)
            await send_with_autodelete(context.bot, chat_id, "Ничего страшного. Начнём снова.", keep_keyboard=True)
            logger.info(f"Пользователь {chat_id} подтвердил срыв")
        elif text == "Нет":
            responses = ["Красава, держись. Я с тобой.", "Молодец, брат. Ты сильный.", "Уважаю. Держимся вместе."]
            await send_with_autodelete(context.bot, chat_id, random.choice(responses), keep_keyboard=True)
        context.user_data['awaiting_relapse_confirm'] = False

# =====================================================
# Запуск
# =====================================================
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
