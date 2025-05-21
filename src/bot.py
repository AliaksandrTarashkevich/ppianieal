# ✅ bot.py — финальная версия
"""
Функции бота
─────────────
• Анкета (вес, рост, % жира) при первом /start
• Расчёт дневной нормы КБЖУ (lean‑body‑mass‑based) и целей Б/Ж/У
• Учёт еды (GPT‑анализ фото) + сохранение
• Учёт веса и шагов (поддержка ключевого слова «вчера»)
• Подсчёт сожжённых ккал: steps × weight × 0.00004
• Итоги дня /summary и авто‑отчёт 23:59 (+расход, статус «норма/профицит»)
• Напоминание 09:00, если шаги за вчера не отправлены (подсказка «вчера»)
• Если шаги/вес за вчера добавили позже — бот сразу шлёт пересчитанный отчёт за вчера
• Кнопки: трекинг, саммари, активность, помощь
"""

# ────────────────────────── Imports ───────────────────────────
import os
import random
import asyncio
import re
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, ContextTypes, filters,
    ConversationHandler, CommandHandler, MessageHandler
)
from telegram.error import TelegramError

from clients.chatgpt_client import analyze_food
from clients.supabase_client import (
    save_meal, save_weight, save_steps,
    get_last_weight, get_nutrition_for_date, get_steps_for_date,
    steps_exist_for_date, user_exists, save_user_data,
    get_user_targets, get_user_profile, supabase,
    save_burned_calories, get_burned_calories, get_image_url,
    init_storage, set_deficit_mode
)
from clients.messages import (
    STEPS_REMINDER_YESTERDAY,
    MEAL_REMINDER_MORNING,
    MEAL_REMINDER_AFTERNOON,
    MEAL_REMINDER_EVENING
)

load_dotenv()
TOKEN = os.getenv("TOKEN")
ZONE = ZoneInfo("Europe/Vilnius")

ASK_WEIGHT, ASK_HEIGHT, ASK_GENDER, ASK_FAT, ASK_DEFICIT_MODE, CONFIRM_HELP, INPUT_WEIGHT_TODAY, INPUT_WEIGHT_YESTERDAY, INPUT_STEPS_TODAY, INPUT_STEPS_YESTERDAY, INPUT_BURN, CHANGE_DEFICIT_MODE, WEIGHT_MENU, STEPS_MENU = range(14)

# ────────────────────────── Мотивация ───────────────────────────
WEIGHT_LOSS_MESSAGES = [
    "📉 Отличная работа! Продолжай в том же духе! 💪",
    "📉 Прогресс налицо! Ты на верном пути 🎯",
    "📉 Вау, это успех! Так держать! 🌟",
    "📉 Результат твоих усилий виден! Молодец! ⭐️",
    "📉 Каждый грамм это победа! Ты справляешься! 🏆"
]

WEIGHT_GAIN_MESSAGES = [
    "📈 Небольшое отклонение - не проблема! Фокусируйся на своей цели 🎯",
    "📈 Помни о своих целях - у тебя все получится! 💫",
    "📈 Прогресс не всегда линейный, продолжай работать! 💪",
    "📈 Завтра новый день - новые возможности! ✨",
    "📈 Не сдавайся, следующее взвешивание будет лучше! 🌟"
]

# ────────────────────────── Клавиатура ───────────────────────────
reply_keyboard = [
    ["⚖️ Track вес", "👣 Track шаги"],
    ["📊 Summary", "🔥 Burn"],
    ["❓ Help", "⚙️ Режим"]
]
markup = ReplyKeyboardMarkup(
    reply_keyboard,
    resize_keyboard=True,
    input_field_placeholder="Используй кнопки ниже",
    is_persistent=True
)

# После определения основной клавиатуры добавляем клавиатуру для выбора пола
gender_keyboard = [["👨 Мужчина", "👩 Женщина"]]
gender_markup = ReplyKeyboardMarkup(gender_keyboard, resize_keyboard=True, one_time_keyboard=True)

# После определения других клавиатур добавим:
confirm_keyboard = [["✅ Понял!"]]
confirm_markup = ReplyKeyboardMarkup(confirm_keyboard, resize_keyboard=True, one_time_keyboard=True)

# После определения других клавиатур добавим:
deficit_keyboard = [["🟢 Лёгкий", "🟠 Средний", "🔴 Экстремальный"]]
deficit_markup = ReplyKeyboardMarkup(deficit_keyboard, resize_keyboard=True, one_time_keyboard=True)

# Добавляем клавиатуры для подменю веса и шагов
weight_keyboard = [
    ["📅 Сегодня", "↩️ Вчера"],
    ["🔙 Назад"]
]
weight_markup = ReplyKeyboardMarkup(weight_keyboard, resize_keyboard=True)

steps_keyboard = [
    ["📅 Сегодня", "↩️ Вчера"],
    ["🔙 Назад"]
]
steps_markup = ReplyKeyboardMarkup(steps_keyboard, resize_keyboard=True)

# ─────────────────── Helpers ──────────────────────────
def now_vilnius():
    return datetime.now(ZONE)

def is_active_hour():
    return 8 <= now_vilnius().hour < 21

def get_weight_change_message(old_weight: float, new_weight: float) -> str:
    """Возвращает мотивационное сообщение в зависимости от изменения веса"""
    if old_weight == new_weight:
        return None
    
    diff = new_weight - old_weight
    if diff < 0:  # Вес снизился
        return random.choice(WEIGHT_LOSS_MESSAGES)
    else:  # Вес увеличился
        return random.choice(WEIGHT_GAIN_MESSAGES)

def get_weight_trend_emoji(old_weight: float, new_weight: float) -> str:
    """Возвращает эмодзи в зависимости от изменения веса"""
    if old_weight == new_weight:
        return "⚖️"
    return "📉" if new_weight < old_weight else "📈"

# ─────────────────── Анкета ────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not user_exists(uid):
        await update.message.reply_text(
            "👋 Добро пожаловать! Давай настроим твой профиль для точного расчета нормы калорий.\n\n"
            "Сколько ты сейчас весишь (в кг)?")
        return ASK_WEIGHT
    await update.message.reply_text("Привет! Скидывай фотки еды, я тебя поддержу 💚", reply_markup=markup)
    return ConversationHandler.END

async def ask_weight(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"🔍 DEBUG: Processing weight input: {update.message.text}")
        ctx.user_data['weight'] = float(update.message.text.replace(',', '.'))
        print(f"✅ Weight saved in context: {ctx.user_data['weight']}")
        await update.message.reply_text("Отлично! А какой у тебя рост (в см)?")
        return ASK_HEIGHT
    except ValueError as e:
        print(f"❌ Error processing weight: {e}")
        await update.message.reply_text("⚠️ Введи число, напр.: 85")
        return ASK_WEIGHT

async def ask_height(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"🔍 DEBUG: Processing height input: {update.message.text}")
        ctx.user_data['height'] = int(update.message.text.strip())
        print(f"✅ Height saved in context: {ctx.user_data['height']}")
        await update.message.reply_text(
            "Теперь выбери свой пол:",
            reply_markup=gender_markup
        )
        return ASK_GENDER
    except ValueError as e:
        print(f"❌ Error processing height: {e}")
        await update.message.reply_text("⚠️ Введи число, напр.: 180")
        return ASK_HEIGHT

async def ask_gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text not in ["👨 Мужчина", "👩 Женщина"]:
        await update.message.reply_text(
            "Пожалуйста, выбери свой пол, используя кнопки ниже:",
            reply_markup=gender_markup
        )
        return ASK_GENDER
    
    ctx.user_data['gender'] = 'male' if text == "👨 Мужчина" else 'female'
    
    # Получаем URL картинки из Supabase Storage
    image_name = "male-bodyfat.jpg" if ctx.user_data['gender'] == 'male' else "female-bodyfat.jpg"
    image_url = get_image_url(image_name)
    
    if image_url:
        try:
            await update.message.reply_photo(
                image_url,
                caption="Посмотри на картинку и определи свой примерный процент жира.\n"
                       "Просто напиши число, например: 15"
            )
        except Exception as e:
            print(f"❌ Failed to send image: {e}")
            await update.message.reply_text(
                "Напиши свой примерный процент жира (число от 3 до 50).\n"
                "Например: 15"
            )
    else:
        await update.message.reply_text(
            "Напиши свой примерный процент жира (число от 3 до 50).\n"
            "Например: 15"
        )
    
    return ASK_FAT

async def ask_fat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        bodyfat = float(update.message.text.replace(',', '.'))
        if bodyfat < 3 or bodyfat > 50:
            await update.message.reply_text("⚠️ Процент жира должен быть от 3 до 50. Попробуй еще раз:")
            return ASK_FAT
            
        # Сохраняем значение в контекст
        ctx.user_data['bodyfat'] = bodyfat
        
        # Отправляем сообщение с выбором режима
        await update.message.reply_text(
            "Выбери режим похудения:\n\n"
            "🟢 Лёгкий\n"
            "Рацион основан на сухой массе тела, без искусственного дефицита.\n"
            "Ожидаемый результат: –0.2…0.4 кг/нед\n"
            "📌 Подходит для старта: организм адаптируется без стресса, вес будет снижаться за счёт активности в течение дня.\n\n"
            "🟠 Средний\n"
            "Создаём дефицит ~500 ккал от нормы.\n"
            "Ожидаемый результат: –0.5…0.8 кг/нед\n"
            "👍 Универсальный режим: сбалансирован между скоростью и устойчивостью.\n\n"
            "🔴 Экстремальный\n"
            "Создаём дефицит ~750 ккал от нормы.\n"
            "Ожидаемый результат: –0.8…1.2 кг/нед\n"
            "⚠️ Требует дисциплины и контроля самочувствия. Не рекомендуется при высокой нагрузке.",
            reply_markup=deficit_markup
        )
        return ASK_DEFICIT_MODE
        
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 18.5")
        return ASK_FAT

async def ask_deficit_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("🟢 ", "").replace("🟠 ", "").replace("🔴 ", "")
    if text not in ["Лёгкий", "Средний", "Экстремальный"]:
        await update.message.reply_text(
            "Пожалуйста, выбери режим, используя кнопки ниже:",
            reply_markup=deficit_markup
        )
        return ASK_DEFICIT_MODE
    
    uid = update.effective_user.id
    try:
        # Сохраняем все данные пользователя
        if not save_user_data(
            uid, 
            ctx.user_data['weight'],
            ctx.user_data['height'],
            ctx.user_data['bodyfat'],
            ctx.user_data['gender'],
            text
        ):
            await update.message.reply_text(
                "⚠️ Произошла ошибка при сохранении данных. Пожалуйста, попробуйте еще раз:",
                reply_markup=deficit_markup
            )
            return ASK_DEFICIT_MODE
        
        # Отправляем инструкцию
        await send_help(uid, update)
        await update.message.reply_text(
            "👆 Это основная инструкция по использованию бота. "
            "Прочитай её внимательно и нажми кнопку ниже:",
            reply_markup=confirm_markup
        )
        return CONFIRM_HELP
        
    except Exception as e:
        print(f"❌ Error in ask_deficit_mode: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте еще раз:",
            reply_markup=deficit_markup
        )
        return ASK_DEFICIT_MODE

# ─────────────────── Фото еды  ─────────────────────────
async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_active_hour():
        return
    desc = update.message.caption or "Еда без описания"
    await update.message.reply_text("🔍 Анализирую еду…")
    res = analyze_food(desc)
    if not res:
        await update.message.reply_text("⚠️ Не удалось проанализировать еду.")
        return
    total, br = res['total'], res['breakdown']
    btxt = "\n".join(
        f"- {i['item']}: {i['calories']} ккал, Б:{i['protein']:.1f}г, Ж:{i['fat']:.1f}г, У:{i['carbs']:.1f}г" for i in br)
    msg = (
        "🍽️ *Разбор еды:*\n"+btxt+"\n\n"+
        f"*Итого:* {total['calories']} ккал\n"
        f"Б:{total['protein']:.1f}г | Ж:{total['fat']:.1f}г | У:{total['carbs']:.1f}г")
    await update.message.reply_text(msg, parse_mode='Markdown')
    save_meal(update.effective_user.id, desc, total['calories'], total['protein'], total['fat'], total['carbs'])

# ─────────────────── Обработчики кнопок ─────────────────────────

async def handle_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "⚖️ Track вес":
        await update.message.reply_text(
            "Выбери, за какой день вводишь вес:",
            reply_markup=weight_markup
        )
        return WEIGHT_MENU
    if txt == "👣 Track шаги":
        await update.message.reply_text(
            "Выбери, за какой день вводишь шаги:",
            reply_markup=steps_markup
        )
        return STEPS_MENU
    if txt == "📊 Summary":
        await send_summary(update.effective_user.id, update)
        return ConversationHandler.END
    if txt == "🔥 Burn":
        await update.message.reply_text("Введи потраченные калории за активность:")
        return INPUT_BURN
    if txt == "❓ Help":
        await send_help(update.effective_user.id, update)
        return ConversationHandler.END
    if txt == "⚙️ Режим":
        return await change_deficit_mode(update, ctx)

# ─────────────── Новые обработчики для ввода чисел ───────────────
async def handle_weight_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "🔙 Назад":
        await update.message.reply_text("Выберите действие:", reply_markup=markup)
        return ConversationHandler.END
    elif txt == "📅 Сегодня":
        await update.message.reply_text("Введи вес (в кг):", reply_markup=ReplyKeyboardRemove())
        return INPUT_WEIGHT_TODAY
    elif txt == "↩️ Вчера":
        await update.message.reply_text("Введи вес за вчера:", reply_markup=ReplyKeyboardRemove())
        return INPUT_WEIGHT_YESTERDAY
    else:
        await update.message.reply_text("Пожалуйста, используй кнопки меню:", reply_markup=weight_markup)
        return WEIGHT_MENU

async def handle_steps_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "🔙 Назад":
        await update.message.reply_text("Выберите действие:", reply_markup=markup)
        return ConversationHandler.END
    elif txt == "📅 Сегодня":
        await update.message.reply_text("Введи шаги (сегодня):", reply_markup=ReplyKeyboardRemove())
        return INPUT_STEPS_TODAY
    elif txt == "↩️ Вчера":
        await update.message.reply_text("Введи шаги за вчера:", reply_markup=ReplyKeyboardRemove())
        return INPUT_STEPS_YESTERDAY
    else:
        await update.message.reply_text("Пожалуйста, используй кнопки меню:", reply_markup=steps_markup)
        return STEPS_MENU

async def input_weight_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        new_weight = float(update.message.text.replace(',', '.'))
        uid = update.effective_user.id
        
        # Получаем вчерашний вес
        yesterday = date.today() - timedelta(days=1)
        old_weight = get_last_weight(uid, exclude_date=date.today())
        
        # Сохраняем новый вес
        save_weight(uid, new_weight, date=date.today())
        
        # Формируем сообщение с правильным эмодзи
        emoji = "⚖️" if not old_weight else get_weight_trend_emoji(old_weight, new_weight)
        msg = f"{emoji} Вес {new_weight} кг сохранён (сегодня)."
        
        # Добавляем мотивационное сообщение, если есть с чем сравнить
        if old_weight:
            motivation = get_weight_change_message(old_weight, new_weight)
            if motivation:
                msg += f"\n\n{motivation}"
        
        await update.message.reply_text(msg, reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 85", reply_markup=weight_markup)
        return WEIGHT_MENU

async def input_weight_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        new_weight = float(update.message.text.replace(',', '.'))
        uid = update.effective_user.id
        yesterday = date.today() - timedelta(days=1)
        
        # Получаем предыдущий вес (за позавчера)
        day_before = yesterday - timedelta(days=1)
        old_weight = get_last_weight(uid, exclude_date=yesterday)
        
        # Сохраняем новый вес
        save_weight(uid, new_weight, date=yesterday)
        
        # Формируем сообщение с правильным эмодзи
        emoji = "⚖️" if not old_weight else get_weight_trend_emoji(old_weight, new_weight)
        msg = f"{emoji} Вес {new_weight} кг сохранён (вчера)."
        
        # Добавляем мотивационное сообщение, если есть с чем сравнить
        if old_weight:
            motivation = get_weight_change_message(old_weight, new_weight)
            if motivation:
                msg += f"\n\n{motivation}"
        
        await update.message.reply_text(msg, reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 85", reply_markup=weight_markup)
        return WEIGHT_MENU

async def input_steps_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        steps = int(update.message.text.strip())
        save_steps(update.effective_user.id, steps, date=date.today())
        await update.message.reply_text(f"👍 Шаги за сегодня сохранены: {steps}.", reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи целое число, напр.: 9000", reply_markup=steps_markup)
        return STEPS_MENU

async def input_steps_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        steps = int(update.message.text.strip())
        d = date.today() - timedelta(days=1)
        save_steps(update.effective_user.id, steps, date=d)
        await update.message.reply_text(f"👍 Шаги за вчера сохранены: {steps}.", reply_markup=markup)
        await send_summary(update.effective_user.id, update, target_date=d)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи целое число, напр.: 9000", reply_markup=steps_markup)
        return STEPS_MENU

async def input_burn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        burned = int(update.message.text.strip())
        uid = update.effective_user.id
        # Сохраняем сожженные калории
        save_burned_calories(uid, burned, date=date.today())
        await update.message.reply_text(
            f"🔥 Учтено {burned} ккал дополнительной активности",
            reply_markup=markup
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи целое число, напр.: 250")
        return INPUT_BURN

# ───────────────── Вес / Шаги ──────────────────────────
async def handle_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.lower()
    uid = update.effective_user.id
    is_yest = 'вчера' in txt
    d = date.today()-timedelta(days=1) if is_yest else date.today()

    if 'вес' in txt:
        try:
            new_weight = float(re.sub(r'[^0-9.,]', '', txt.split('вес',1)[1]))
            
            # Получаем предыдущий вес
            old_weight = get_last_weight(uid, exclude_date=d)
            
            # Сохраняем новый вес
            save_weight(uid, new_weight, date=d)
            
            # Формируем сообщение с правильным эмодзи
            emoji = "⚖️" if not old_weight else get_weight_trend_emoji(old_weight, new_weight)
            msg = f"{emoji} Вес {new_weight} кг сохранён ({'вчера' if is_yest else 'сегодня'})."
            
            # Добавляем мотивационное сообщение, если есть с чем сравнить
            if old_weight:
                motivation = get_weight_change_message(old_weight, new_weight)
                if motivation:
                    msg += f"\n\n{motivation}"
            
            await update.message.reply_text(msg)
        except Exception:
            await update.message.reply_text("⚠️ Не смог распознать вес.")

    elif 'шаги' in txt:
        try:
            steps = int(re.sub(r'[^0-9]', '', txt.split('шаги',1)[1]))
            save_steps(uid, steps, date=d)
            await update.message.reply_text(f"👍 Шаги за {'вчера' if is_yest else 'сегодня'} сохранены: {steps}.")
            if is_yest:
                await send_summary(uid, update, target_date=d)
        except Exception:
            await update.message.reply_text("⚠️ Не смог распознать количество шагов.")

# ───────────────── Итоги ───────────────────────────────
async def daily_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_summary(update.effective_user.id, update)

async def send_help(uid: int, target):
    """Отправляет справку о возможностях бота"""
    txt = (
        "📘 *Как пользоваться ботом:*\n\n"
        
        "📸 *1. Фото еды:*\n"
        "Просто отправь фото с кратким описанием еды.\n"
        "Пример:\n"
        "куриная грудка 200g, кабачок 100g, масло оливковое 5g\n\n"
        
        "⚠️ Чем точнее описание (вес, состав), тем точнее подсчёт калорий!\n\n"
        
        "Пример 1 — ✅ Хорошо:\n"
        "куриная грудка 200g, кабачок 100g, масло оливковое 5g\n\n"
        
        "Пример 2 — ❌ Плохо:\n"
        "курица с овощами (недостаточно данных)\n\n"
        
        "⚖️ *2. Вес и шаги:*\n"
        "Используй кнопки:\n\n"
        
        "• Track вес сегодня / вчера — чтобы ввести текущий вес\n"
        "• Track шаги сегодня / вчера — чтобы ввести шаги\n\n"
        
        "📊 *3. Итоги дня:*\n"
        "Нажми кнопку Summary — бот покажет КБЖУ, шаги, расход и статус (норма или превышение).\n\n"
        
        "🔥 *4. Ккал за активность:*\n"
        "Занимался спортом (велосипед, баскетбол, тренировка)?\n"
        "Нажми кнопку Burn и просто введи число — например:\n"
        "250\n"
        "Бот учтёт эти калории в итогах дня.\n\n"
        
        "🆘 *5. Подсказка:*\n"
        "Нажми Help, чтобы снова открыть эту инструкцию.\n\n"
        
        "⚙️ Бот автоматически считает всё за день, сравнивает с твоей нормой и напоминает, если ты что-то забыл.\n\n"
        
        "💪 Пользуйся ботом каждый день — и ты будешь контролировать питание и прогресс без лишних усилий!\n\n"
        
        "После нажатия кнопки «✅ Понял!» появятся все кнопки управления ботом."
    )
    
    if isinstance(target, Update):
        await target.message.reply_text(txt, parse_mode='Markdown', reply_markup=confirm_markup)
    else:
        await target.send_message(chat_id=uid, text=txt, parse_mode='Markdown', reply_markup=confirm_markup)
    return ConversationHandler.END

async def send_summary(uid: int, target, *, target_date: date|None=None):
    """Отправляет сводку за день"""
    target_date = target_date or date.today()
    
    try:
        nutr = get_nutrition_for_date(uid, target_date)
        goals = get_user_targets(uid)
        prof = get_user_profile(uid)
        steps = get_steps_for_date(uid, target_date) or 0
        weight = prof['weight'] if prof else 70
        
        print(f"🔍 DEBUG: Profile data:")
        print(f"Weight: {weight}kg")
        print(f"Body fat: {prof['bodyfat']}%")
        print(f"Goals: {goals}")
        
        # Получаем все сожженные калории
        steps_burned = round(steps * weight * 0.00035)  # Калории от шагов
        extra_burned = get_burned_calories(uid, target_date)  # Дополнительно сожженные калории
        total_burned = steps_burned + extra_burned
        
        print(f"🔥 DEBUG: Calories burned:")
        print(f"Steps: {steps} -> {steps_burned} kcal")
        print(f"Extra: {extra_burned} kcal")
        print(f"Total burned: {total_burned} kcal")
        
        eat_kcal = nutr['calories'] if nutr else 0
        daily_target = goals['calories'] + total_burned if goals else total_burned
        
        print(f"📊 DEBUG: Daily targets:")
        print(f"Base calories: {goals['calories']} kcal")
        print(f"With activity: {daily_target} kcal")
        
        # Формируем сообщение
        txt = f"📊 *Итоги за {target_date:%d.%m}:*\n"
        
        # Добавляем информацию о питании
        if nutr:
            txt += (
                f"Калории: {eat_kcal}/{daily_target} ккал (с учетом дневной активности)\n"
                f"Белки: {nutr['protein']:.1f}/{goals['protein']} г\n"
                f"Жиры: {nutr['fat']:.1f}/{goals['fat']} г\n"
                f"Углеводы: {nutr['carbs']:.1f}/{goals['carbs']} г\n"
            )
        else:
            txt += f"Нет записей по еде (дневная норма: {daily_target} ккал с учетом активности)\n"
        
        # Добавляем информацию о сожженных калориях
        txt += f"👟 Шаги: {steps:,} | 🔥 От шагов: {steps_burned} ккал\n"
        if extra_burned > 0:
            txt += f"💪 Доп. активность: {extra_burned} ккал\n"
        txt += f"🔥 Всего сожжено: {total_burned} ккал\n"
        
        # Считаем баланс
        balance = eat_kcal - total_burned
        if goals and 'calories' in goals:
            status = "✅ В пределах нормы" if balance <= goals['calories'] else f"⚠️ Превышено на {balance-goals['calories']} ккал"
            txt += f"Баланс: {status}"
        
        if isinstance(target, Update):
            await target.message.reply_text(txt, parse_mode='Markdown')
        else:
            await target.send_message(chat_id=uid, text=txt, parse_mode='Markdown')
            
    except Exception as e:
        error_txt = f"⚠️ Ошибка при формировании отчета: {str(e)}"
        if isinstance(target, Update):
            await target.message.reply_text(error_txt)
        else:
            await target.send_message(chat_id=uid, text=error_txt)

# ───────────────── Планировщик задач ────────────────────
async def send_steps_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """Напоминание о шагах за вчера (09:00)"""
    job = ctx.job
    uid = int(job.data)
    yesterday = date.today() - timedelta(days=1)
    if not steps_exist_for_date(uid, yesterday):
        await ctx.bot.send_message(
            chat_id=uid,
            text=random.choice(STEPS_REMINDER_YESTERDAY)
        )

async def send_morning_meal_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """Напоминание о завтраке (11:00)"""
    job = ctx.job
    uid = int(job.data)
    if not has_meals_in_timerange(uid, date.today(), 0, 10):
        await ctx.bot.send_message(
            chat_id=uid,
            text=random.choice(MEAL_REMINDER_MORNING)
        )

async def send_afternoon_meal_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """Напоминание об обеде (16:00)"""
    job = ctx.job
    uid = int(job.data)
    if not has_meals_in_timerange(uid, date.today(), 11, 15):
        await ctx.bot.send_message(
            chat_id=uid,
            text=random.choice(MEAL_REMINDER_AFTERNOON)
        )

async def send_evening_meal_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """Напоминание об ужине (23:00)"""
    job = ctx.job
    uid = int(job.data)
    if not has_meals_in_timerange(uid, date.today(), 16, 22):
        await ctx.bot.send_message(
            chat_id=uid,
            text=random.choice(MEAL_REMINDER_EVENING)
        )

def schedule_for_user(job_queue, user_id: int):
    """Планирует все напоминания для пользователя"""
    # Напоминание о шагах в 09:00, если не отправлены
    job_queue.run_daily(
        send_steps_reminder,
        time=time(9, 0, tzinfo=ZONE),
        data=user_id,
        name=f"steps_reminder_{user_id}"
    )
    
    # Напоминание о завтраке в 11:00
    job_queue.run_daily(
        send_morning_meal_reminder,
        time=time(11, 0, tzinfo=ZONE),
        data=user_id,
        name=f"morning_meal_{user_id}"
    )
    
    # Напоминание об обеде в 16:00
    job_queue.run_daily(
        send_afternoon_meal_reminder,
        time=time(16, 0, tzinfo=ZONE),
        data=user_id,
        name=f"afternoon_meal_{user_id}"
    )
    
    # Напоминание об ужине в 23:00
    job_queue.run_daily(
        send_evening_meal_reminder,
        time=time(23, 0, tzinfo=ZONE),
        data=user_id,
        name=f"evening_meal_{user_id}"
    )
    
    # Автоматический отчёт в 23:59
    job_queue.run_daily(
        send_daily_summary,
        time=time(23, 59, tzinfo=ZONE),
        data=user_id,
        name=f"summary_{user_id}"
    )

# ───────────────── Помощь и обновление клавиатуры ────────────────
async def update_keyboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обновляет клавиатуру с эмодзи"""
    await update.message.reply_text(
        "⌨️ Клавиатура обновлена!",
        reply_markup=markup
    )

# ───────────────── Новые обработчики для подтверждения ────────────────
async def confirm_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.text != "✅ Понял!":
            await update.message.reply_text(
                "Пожалуйста, нажми кнопку '✅ Понял!' чтобы продолжить:",
                reply_markup=confirm_markup
            )
            return CONFIRM_HELP
        
        # Отправляем пример с фото еды
        image_url = get_image_url("buckwheat.jpg")
        print(f"🔍 DEBUG: Got image URL for buckwheat.jpg: {image_url}")
        
        await update.message.reply_text(
            "👨‍🍳 Вот пример того, как нужно отправлять фото еды:",
            reply_markup=markup
        )
        
        if image_url:
            try:
                await update.message.reply_photo(
                    image_url,
                    caption="гречка 80г, курица 200g, морковь 50g, зелень"
                )
            except Exception as e:
                print(f"❌ Failed to send example image: {e}")
                # Continue even if image sending fails
        
        await update.message.reply_text(
            "Теперь ты готов к использованию бота! Отправляй фото своей еды с описанием порций в граммах 🚀",
            reply_markup=markup
        )
        
        # Schedule reminders for the new user
        uid = update.effective_user.id
        try:
            schedule_for_user(ctx.application.job_queue, uid)
            print(f"✅ Scheduled reminders for user {uid}")
        except Exception as e:
            print(f"❌ Failed to schedule reminders for user {uid}: {e}")
            # Continue even if scheduling fails
        
        return ConversationHandler.END
        
    except Exception as e:
        print(f"❌ Error in confirm_help: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте еще раз:",
            reply_markup=confirm_markup
        )
        return CONFIRM_HELP

# Добавляем новую функцию для изменения режима
async def change_deficit_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("🟢 ", "").replace("🟠 ", "").replace("🔴 ", "")
    if text == "⚙️ Режим":
        await update.message.reply_text(
            "Выбери режим похудения:\n\n"
            "🟢 Лёгкий\n"
            "Рацион основан на сухой массе тела, без искусственного дефицита.\n"
            "Ожидаемый результат: –0.2…0.4 кг/нед\n"
            "📌 Подходит для старта: организм адаптируется без стресса, вес будет снижаться за счёт активности в течение дня.\n\n"
            "🟠 Средний\n"
            "Создаём дефицит ~500 ккал от нормы.\n"
            "Ожидаемый результат: –0.5…0.8 кг/нед\n"
            "👍 Универсальный режим: сбалансирован между скоростью и устойчивостью.\n\n"
            "🔴 Экстремальный\n"
            "Создаём дефицит ~750 ккал от нормы.\n"
            "Ожидаемый результат: –0.8…1.2 кг/нед\n"
            "⚠️ Требует дисциплины и контроля самочувствия. Не рекомендуется при высокой нагрузке.",
            reply_markup=deficit_markup
        )
        return CHANGE_DEFICIT_MODE
    
    if text not in ["Лёгкий", "Средний", "Экстремальный"]:
        await update.message.reply_text(
            "Пожалуйста, выбери режим, используя кнопки ниже:",
            reply_markup=deficit_markup
        )
        return CHANGE_DEFICIT_MODE
    
    uid = update.effective_user.id
    
    # Получаем текущий профиль для сравнения
    old_profile = get_user_profile(uid)
    print(f"🔄 DEBUG: Changing deficit mode for user {uid}")
    print(f"Old profile: {old_profile}")
    
    # Устанавливаем новый режим
    set_deficit_mode(uid, text)
    
    # Получаем обновленный профиль
    new_profile = get_user_profile(uid)
    print(f"New profile: {new_profile}")
    
    # Получаем новые цели
    new_targets = get_user_targets(uid)
    print(f"New targets: {new_targets}")
    
    await update.message.reply_text(
        f"✅ Режим изменён на «{text}»\n"
        f"Новая норма калорий: {new_targets['calories']} ккал\n"
        f"(было {old_profile.get('deficit', 0)} ккал дефицита, стало {new_profile.get('deficit', 0)} ккал)",
        reply_markup=markup
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок для бота."""
    print(f"⚠️ Exception while handling an update: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Извините, произошла ошибка. Попробуйте еще раз или обратитесь к администратору."
            )
    except Exception as e:
        print(f"❌ Failed to send error message: {e}")

# ───────────────── Main ────────────────────────────────
if __name__ == '__main__':
    # Инициализируем хранилище
    init_storage()
    
    app = ApplicationBuilder().token(TOKEN).build()

    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)

    # Обработчик первого запуска и анкеты
    start_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weight)],
            ASK_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_height)],
            ASK_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_gender)],
            ASK_FAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fat)],
            ASK_DEFICIT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_deficit_mode)],
            CONFIRM_HELP: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_help)],
        },
        fallbacks=[
            CommandHandler('start', start),
            MessageHandler(filters.COMMAND, lambda u, c: ConversationHandler.END),
            MessageHandler(filters.ALL, lambda u, c: u.message.reply_text(
                "⚠️ Что-то пошло не так. Давайте начнем сначала: /start"
            ))
        ]
    )
    
    # Обработчик кнопок и ввода данных
    button_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(⚖️ Track вес|👣 Track шаги|📊 Summary|🔥 Burn|❓ Help|⚙️ Режим)$'), handle_button)],
        states={
            WEIGHT_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight_menu)],
            STEPS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_steps_menu)],
            INPUT_WEIGHT_TODAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_weight_today)],
            INPUT_WEIGHT_YESTERDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_weight_yesterday)],
            INPUT_STEPS_TODAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_steps_today)],
            INPUT_STEPS_YESTERDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_steps_yesterday)],
            INPUT_BURN: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_burn)],
            CHANGE_DEFICIT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_deficit_mode)],
        },
        fallbacks=[
            CommandHandler('start', start),
            MessageHandler(filters.COMMAND, lambda u, c: ConversationHandler.END),
            MessageHandler(filters.ALL, lambda u, c: u.message.reply_text(
                "⚠️ Неверный ввод. Используйте кнопки меню или начните сначала: /start",
                reply_markup=markup
            ))
        ]
    )

    app.add_handler(start_conv)
    app.add_handler(button_conv)  # Добавляем обработчик кнопок
    app.add_handler(CommandHandler('summary', daily_summary))
    app.add_handler(CommandHandler('help', send_help))  # Добавляем обработчик help
    app.add_handler(CommandHandler('keyboard', update_keyboard))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Regex(r'^итоги$'), daily_summary))
    app.add_handler(MessageHandler(filters.Regex(r'^/track'), handle_track))

    # Подписка на всех
    existing = [int(u['user_id']) for u in supabase.table('users').select('user_id').execute().data]
    for uid in existing:
        schedule_for_user(app.job_queue, uid)

    print('🚀 Бот запущен (polling)')
    app.run_polling(allowed_updates=Update.ALL_TYPES)

