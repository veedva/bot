import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import time, datetime, timedelta
import random
import json
import os
from pytz import timezone
from filelock import FileLock

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота из переменной окружения
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен. Добавьте его в переменные окружения Railway.")

# Файл для хранения данных пользователей
DATA_FILE = 'user_data.json'

# Московский часовой пояс
MOSCOW = timezone('Europe/Moscow')

# Сообщения для утра (9:00)
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

# Сообщения для вечера (18:00)
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
    "Братан, ну может завтра, а сегодня нет?",
    "Эй. Сегодня спокойно можем без этого."
]

# Сообщения на ночь (23:00)
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
    "Сегодня получилось. Отдыхай.",
    "День позади. Горжусь. Отдыхай.",
    "Держался. Ты сильный. Спи."
]

# Ответы на кнопки
HOLDING_RESPONSES = [
    "Молодец, я тоже держусь",
    "Красава, брат. Я с тобой",
    "Сильный. Я тоже держусь сегодня",
    "Уважаю. Держимся вместе",
    "Отлично, брат. Продолжаем",
    "Молодчина. Я тоже",
    "Так держать. Я рядом"
]

DIDNT_RELAPSE_RESPONSES = [
    "Красава, держись. Я с тобой.",
    "Молодец, брат. Ты сильный.",
    "Уважаю. Держимся вместе.",
    "Ты справляешься. Горжусь тобой.",
    "Сильный духом. Я рядом.",
    "Ты можешь. Держись, братан."
]

# Вехи для поздравлений (в днях)
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

def load_user_data():
    """Загрузка данных пользователей из файла"""
    lock_path = DATA_FILE + ".lock"
    with FileLock(lock_path):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {}

def save_user_data(data):
    """Сохранение данных пользователей в файл"""
    lock_path = DATA_FILE + ".lock"
    with FileLock(lock_path):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_main_keyboard():
    """Создание основной клавиатуры"""
    keyboard = [
        [KeyboardButton("👋 Ты тут?"), KeyboardButton("😔 Тяжело")],
        [KeyboardButton("📊 Дни"), KeyboardButton("⏸ Пауза")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_start_keyboard():
    """Клавиатура для старта"""
    keyboard = [[KeyboardButton("▶ Начать")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_relapse_keyboard():
    """Клавиатура для подтверждения срыва"""
    keyboard = [[KeyboardButton("Да"), KeyboardButton("Нет")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_days_count(user_id):
    """Получить количество дней для пользователя"""
    data = load_user_data()
    if str(user_id) in data and 'start_date' in data[str(user_id)]:
        start_date_str = data[str(user_id)]['start_date']
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).astimezone(MOSCOW)
        now = datetime.now(MOSCOW)
        days = (now - start_date).days
        return days
    return 0

def reset_counter(user_id):
    """Сброс счётчика дней"""
    data = load_user_data()
    if str(user_id) in data:
        data[str(user_id)]['start_date'] = datetime.now(MOSCOW).isoformat()
        save_user_data(data)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Сохраняем дату старта
    data = load_user_data()
    if str(chat_id) not in data:
        data[str(chat_id)] = {}
    
    # Если это первый запуск или счётчик был сброшен, начинаем с нуля
    if 'start_date' not in data[str(chat_id)]:
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
    
    # Удаляем старые задачи если есть
    current_jobs = context.job_queue.get_jobs_by_name(f"morning_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    current_jobs = context.job_queue.get_jobs_by_name(f"evening_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    current_jobs = context.job_queue.get_jobs_by_name(f"night_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    # Запускаем ежедневные сообщения (в московском времени)
    context.job_queue.run_daily(
        send_morning_message,
        time=time(hour=9, minute=0, second=0, tzinfo=MOSCOW),
        chat_id=chat_id,
        name=f"morning_{chat_id}",
        data=chat_id
    )
    
    context.job_queue.run_daily(
        send_evening_message,
        time=time(hour=18, minute=0, second=0, tzinfo=MOSCOW),
        chat_id=chat_id,
        name=f"evening_{chat_id}",
        data=chat_id
    )
    
    context.job_queue.run_daily(
        send_night_message,
        time=time(hour=23, minute=0, second=0, tzinfo=MOSCOW),
        chat_id=chat_id,
        name=f"night_{chat_id}",
        data=chat_id
    )
    
    logger.info(f"Пользователь {user.first_name} ({user.id}) запустил бота")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stop или кнопки Стоп"""
    chat_id = update.effective_chat.id
    
    # Отмечаем как неактивного
    data = load_user_data()
    if str(chat_id) in data:
        data[str(chat_id)]['active'] = False
        save_user_data(data)
    
    # Удаляем все задачи для этого пользователя
    jobs = context.job_queue.get_jobs_by_name(f"morning_{chat_id}")
    for job in jobs:
        job.schedule_removal()
    
    jobs = context.job_queue.get_jobs_by_name(f"evening_{chat_id}")
    for job in jobs:
        job.schedule_removal()
    
    jobs = context.job_queue.get_jobs_by_name(f"night_{chat_id}")
    for job in jobs:
        job.schedule_removal()
    
    await update.message.reply_text(
        "Напоминания остановлены. Нажми ▶ Начать чтобы возобновить.",
        reply_markup=get_start_keyboard()
    )
    logger.info(f"Пользователь {update.effective_user.id} остановил бота")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset - сброс счётчика"""
    chat_id = update.effective_chat.id
    reset_counter(chat_id)
    await update.message.reply_text("Счётчик обнулён. Начинаем заново.")
    logger.info(f"Пользователь {chat_id} сбросил счётчик")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений и кнопок"""
    text = update.message.text
    chat_id = update.effective_chat.id
    
    if text == "▶ Начать":
        await start(update, context)
    
    elif text == "👋 Ты тут?":
        response = random.choice(HOLDING_RESPONSES)
        await update.message.reply_text(response)
    
    elif text == "😔 Тяжело":
        context.user_data['awaiting_relapse_confirm'] = True
        await update.message.reply_text(
            "Брат, ты сорвался?",
            reply_markup=get_relapse_keyboard()
        )
    
    elif text == "📊 Дни":
        days = get_days_count(chat_id)
        if days == 0:
            await update.message.reply_text("Первый день. Начинаем.")
        elif days == 1:
            await update.message.reply_text("Прошёл 1 день")
        else:
            if days in MILESTONES:
                await update.message.reply_text(f"{MILESTONES[days]}\n\nВсего прошло {days} дней.")
            else:
                await update.message.reply_text(f"Прошло {days} дней")
    
    elif text == "⏸ Пауза":
        await stop(update, context)
    
    # Обработка подтверждения срыва
    elif context.user_data.get('awaiting_relapse_confirm'):
        if text == "Да":
            reset_counter(chat_id)
            await update.message.reply_text(
                "Ничего страшного. Начнём снова завтра.",
                reply_markup=get_main_keyboard()
            )
            logger.info(f"Пользователь {chat_id} подтвердил срыв")
        elif text == "Нет":
            response = random.choice(DIDNT_RELAPSE_RESPONSES)
            await update.message.reply_text(
                response,
                reply_markup=get_main_keyboard()
            )
        context.user_data['awaiting_relapse_confirm'] = False

async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    """Отправка утреннего сообщения"""
    chat_id = context.job.data
    data = load_user_data()
    user_data = data.get(str(chat_id), {})
    if not user_data.get('active', True):
        return
    
    days = get_days_count(chat_id)
    
    # Проверяем вехи
    if days in MILESTONES:
        message = MILESTONES[days]
        await context.bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Отправлено поздравление на {days} дней пользователю {chat_id}")
    else:
        message = random.choice(MORNING_MESSAGES)
        await context.bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Отправлено утреннее сообщение пользователю {chat_id}")

async def send_evening_message(context: ContextTypes.DEFAULT_TYPE):
    """Отправка вечернего сообщения"""
    chat_id = context.job.data
    data = load_user_data()
    user_data = data.get(str(chat_id), {})
    if not user_data.get('active', True):
        return
    
    message = random.choice(EVENING_MESSAGES)
    await context.bot.send_message(chat_id=chat_id, text=message)
    logger.info(f"Отправлено вечернее сообщение пользователю {chat_id}")

async def send_night_message(context: ContextTypes.DEFAULT_TYPE):
    """Отправка ночного сообщения"""
    chat_id = context.job.data
    data = load_user_data()
    user_data = data.get(str(chat_id), {})
    if not user_data.get('active', True):
        return
    
    message = random.choice(NIGHT_MESSAGES)
    await context.bot.send_message(chat_id=chat_id, text=message)
    logger.info(f"Отправлено ночное сообщение пользователю {chat_id}")

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("reset", reset_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()