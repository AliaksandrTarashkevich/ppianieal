# ✅ ppitanieal.py — финальная версия
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
import os, random, asyncio, re
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, ContextTypes, filters,
    ConversationHandler, CommandHandler, MessageHandler
)
from chatgpt_client import analyze_food
from supabase_client import (
    save_meal, save_weight, save_steps,
    get_last_weight, get_nutrition_for_date, get_steps_for_date,
    steps_exist_for_date, user_exists, save_user_data,
    get_user_targets, get_user_profile, supabase,
    save_burned_calories, get_burned_calories
)

load_dotenv()
TOKEN = os.getenv("TOKEN")
ZONE = ZoneInfo("Europe/Vilnius")

ASK_WEIGHT, ASK_HEIGHT, ASK_FAT, INPUT_WEIGHT_TODAY, INPUT_WEIGHT_YESTERDAY, INPUT_STEPS_TODAY, INPUT_STEPS_YESTERDAY, INPUT_BURN = range(8)

# ────────────────────────── Клавиатура ───────────────────────────
reply_keyboard = [
    ["⚖️ Track вес сегодня", "👣 Track шаги сегодня"],
    ["📅 Track вес вчера", "🔄 Track шаги вчера"],
    ["📊 Summary", "🔥 Burn"],
    ["❓ Help"]
]
markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

# ─────────────────── Helpers ──────────────────────────
def now_vilnius():
    return datetime.now(ZONE)

def is_active_hour():
    return 8 <= now_vilnius().hour < 21

# ─────────────────── Анкета ────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not user_exists(uid):
        await update.message.reply_text(
            "Добро пожаловать! Давай рассчитаем твою норму калорий.\n"
            "Сколько ты сейчас весишь (в кг)?")
        return ASK_WEIGHT
    await update.message.reply_text("Привет! Скидывай фотки еды, я тебя поддержу 💚", reply_markup=markup)
    return ConversationHandler.END

async def ask_weight(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data['weight'] = float(update.message.text.replace(',', '.'))
        await update.message.reply_text("Спасибо! А какой у тебя рост (в см)?")
        return ASK_HEIGHT
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 85")
        return ASK_WEIGHT

async def ask_height(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data['height'] = int(update.message.text.strip())
        await update.message.reply_text("И последний вопрос — сколько у тебя % жира?")
        return ASK_FAT
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 180")
        return ASK_HEIGHT

async def ask_fat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        bodyfat = float(update.message.text.replace(',', '.'))
        uid = update.effective_user.id
        save_user_data(uid, ctx.user_data['weight'], ctx.user_data['height'], bodyfat)
        await update.message.reply_text(
            "Данные сохранены! Отправляй еду и шаги.\nКоманда /summary покажет итоги дня.",
            reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 18.5")
        return ASK_FAT

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
        f"- {i['item']}: {i['calories']} ккал, Б:{i['protein']}г, Ж:{i['fat']}г, У:{i['carbs']}г" for i in br)
    msg = (
        "🍽️ *Разбор еды:*\n"+btxt+"\n\n"+
        f"*Итого:* {total['calories']} ккал\n"
        f"Б:{total['protein']}г | Ж:{total['fat']}г | У:{total['carbs']}г")
    await update.message.reply_text(msg, parse_mode='Markdown')
    save_meal(update.effective_user.id, desc, total['calories'], total['protein'], total['fat'], total['carbs'])

# ─────────────────── Обработчики кнопок ─────────────────────────

async def handle_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    if txt == "⚖️ Track вес сегодня":
        await update.message.reply_text("Введи вес (в кг):")
        return INPUT_WEIGHT_TODAY
    if txt == "📅 Track вес вчера":
        await update.message.reply_text("Введи вес за вчера:")
        return INPUT_WEIGHT_YESTERDAY
    if txt == "👣 Track шаги сегодня":
        await update.message.reply_text("Введи шаги (сегодня):")
        return INPUT_STEPS_TODAY
    if txt == "🔄 Track шаги вчера":
        await update.message.reply_text("Введи шаги за вчера:")
        return INPUT_STEPS_YESTERDAY
    if txt == "📊 Summary":
        await send_summary(update.effective_user.id, update)
        return ConversationHandler.END
    if txt == "🔥 Burn":
        await update.message.reply_text("Введи потраченные калории за активность:")
        return INPUT_BURN
    if txt == "❓ Help":
        await send_help(update.effective_user.id, update)
        return ConversationHandler.END

# ─────────────── Новые обработчики для ввода чисел ───────────────
async def input_weight_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        w = float(update.message.text.replace(',', '.'))
        save_weight(update.effective_user.id, w, date=date.today())
        await update.message.reply_text(f"📉 Вес {w} кг сохранён (сегодня).", reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 85")
        return INPUT_WEIGHT_TODAY

async def input_weight_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        w = float(update.message.text.replace(',', '.'))
        d = date.today() - timedelta(days=1)
        save_weight(update.effective_user.id, w, date=d)
        await update.message.reply_text(f"📉 Вес {w} кг сохранён (вчера).", reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 85")
        return INPUT_WEIGHT_YESTERDAY

async def input_steps_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        steps = int(update.message.text.strip())
        save_steps(update.effective_user.id, steps, date=date.today())
        await update.message.reply_text(f"👍 Шаги за сегодня сохранены: {steps}.", reply_markup=markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи целое число, напр.: 9000")
        return INPUT_STEPS_TODAY

async def input_steps_yesterday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        steps = int(update.message.text.strip())
        d = date.today() - timedelta(days=1)
        save_steps(update.effective_user.id, steps, date=d)
        await update.message.reply_text(f"👍 Шаги за вчера сохранены: {steps}.", reply_markup=markup)
        await send_summary(update.effective_user.id, update, target_date=d)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи целое число, напр.: 9000")
        return INPUT_STEPS_YESTERDAY

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
            w = float(re.sub(r'[^0-9.,]', '', txt.split('вес',1)[1]))
            save_weight(uid, w, date=d)
            await update.message.reply_text(f"📉 Вес {w} кг сохранён ({'вчера' if is_yest else 'сегодня'}).")
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

async def send_summary(uid: int, target, *, target_date: date|None=None):
    target_date = target_date or date.today()
    nutr = get_nutrition_for_date(uid, target_date)
    goals = get_user_targets(uid)
    prof = get_user_profile(uid)
    steps = get_steps_for_date(uid, target_date) or 0
    weight = prof['weight'] if prof else 70
    
    # Получаем все сожженные калории
    steps_burned = round(steps * weight * 0.00035)  # Калории от шагов
    extra_burned = get_burned_calories(uid, target_date)  # Дополнительно сожженные калории
    total_burned = steps_burned + extra_burned
    
    eat_kcal = nutr['calories'] if nutr else 0
    
    # Формируем сообщение
    txt = f"📊 *Итоги за {target_date:%d.%m}:*\n"
    
    # Добавляем информацию о питании
    if nutr:
        txt += (
            f"Калории: {eat_kcal}/{goals['calories']} ккал\n"
            f"Белки: {nutr['protein']:.1f}/{goals['protein']} г\n"
            f"Жиры: {nutr['fat']:.1f}/{goals['fat']} г\n"
            f"Углеводы: {nutr['carbs']:.1f}/{goals['carbs']} г\n"
        )
    else:
        txt += "Нет записей по еде\n"
    
    # Добавляем информацию о сожженных калориях
    txt += f"👟 Шаги: {steps:,}  |  🔥 От шагов: {steps_burned} ккал\n"
    if extra_burned > 0:
        txt += f"💪 Доп. активность: {extra_burned} ккал\n"
    txt += f"🔥 Всего сожжено: {total_burned} ккал\n"
    
    # Считаем баланс только если есть данные о питании
    if nutr:
        balance = eat_kcal - total_burned
        if goals and 'calories' in goals:
            status = "✅ В пределах нормы" if balance <= goals['calories'] else f"⚠️ Превышено на {balance-goals['calories']} ккал"
            txt += f"Баланс: {status}"
    
    if isinstance(target, Update):
        await target.message.reply_text(txt, parse_mode='Markdown')
    else:
        await target.send_message(chat_id=uid, text=txt, parse_mode='Markdown')

# ───────────────── Планировщик задач ────────────────────
async def send_steps_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    job = ctx.job
    uid = int(job.data)
    yesterday = date.today() - timedelta(days=1)
    if not steps_exist_for_date(uid, yesterday):
        await ctx.bot.send_message(
            chat_id=uid,
            text="👋 Доброе утро! Не забудь отправить шаги за вчера (подсказка: «шаги 8000 вчера»)")

async def send_daily_summary(ctx: ContextTypes.DEFAULT_TYPE):
    job = ctx.job
    uid = int(job.data)
    await send_summary(uid, ctx.bot)

def schedule_for_user(job_queue, user_id: int):
    # Напоминание о шагах в 09:00, если не отправлены
    job_queue.run_daily(
        send_steps_reminder,
        time=time(9, 0, tzinfo=ZONE),
        data=user_id,
        name=f"reminder_{user_id}"
    )
    
    # Автоматический отчёт в 23:59
    job_queue.run_daily(
        send_daily_summary,
        time=time(23, 59, tzinfo=ZONE),
        data=user_id,
        name=f"summary_{user_id}"
    )

# ───────────────── Помощь и обновление клавиатуры ────────────────
async def send_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Что я умею:*\n"
        "• Анализировать фото еды и считать КБЖУ\n"
        "• Отслеживать вес и шаги\n"
        "• Считать сожжённые калории\n"
        "• Показывать итоги дня /summary\n\n"
        "Используй кнопки внизу для быстрого доступа к функциям.\n"
        "Если кнопки пропали — используй /keyboard",
        parse_mode='Markdown',
        reply_markup=markup
    )
    return ConversationHandler.END

async def update_keyboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обновляет клавиатуру с эмодзи"""
    await update.message.reply_text(
        "⌨️ Клавиатура обновлена!",
        reply_markup=markup
    )

# ───────────────── Main ────────────────────────────────
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчик первого запуска и анкеты
    start_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_WEIGHT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weight)],
            ASK_HEIGHT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_height)],
            ASK_FAT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fat)],
        },
        fallbacks=[]
    )
    
    # Обработчик кнопок и ввода данных
    button_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(⚖️ Track вес сегодня|📅 Track вес вчера|👣 Track шаги сегодня|🔄 Track шаги вчера|📊 Summary|🔥 Burn|❓ Help)$'), handle_button)],
        states={
            INPUT_WEIGHT_TODAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_weight_today)],
            INPUT_WEIGHT_YESTERDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_weight_yesterday)],
            INPUT_STEPS_TODAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_steps_today)],
            INPUT_STEPS_YESTERDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_steps_yesterday)],
            INPUT_BURN: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_burn)],
        },
        fallbacks=[]
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
    app.run_polling()

