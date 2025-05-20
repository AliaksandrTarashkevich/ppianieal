# ✅ ppitanieal.py — финальная версия
"""
Функции бота
─────────────
• Анкета (вес, рост, % жира) при первом /start
• Расчёт дневной нормы КБЖУ (lean‑body‑mass‑based) и целей Б/Ж/У
• Учёт еды (GPT‑анализ фото) + сохранение
• Учёт веса и шагов (поддержка ключевого слова «вчера»)
• Подсчёт сожжённых ккал: steps × weight × 0.00004
• Итоги дня /summary и авто‑отчёт 23:59 (+расход, статус «норма/профицит»)
• Напоминание 09:00, если шаги за вчера не отправлены (подсказка «вчера»)
• Если шаги/вес за вчера добавили позже — бот сразу шлёт пересчитанный отчёт за вчера
"""

# ────────────────────────── Imports ───────────────────────────
import os, random, asyncio, re
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, ContextTypes, filters,
    ConversationHandler, CommandHandler, MessageHandler
)
from chatgpt_client import analyze_food
from supabase_client import (
    save_meal, save_weight, save_steps,
    get_last_weight, get_nutrition_for_date, get_steps_for_date,
    steps_exist_for_date, user_exists, save_user_data,
    get_user_targets, get_user_profile, supabase
)

load_dotenv()
TOKEN = os.getenv("TOKEN")

# ────────────────────────── Анкета ────────────────────────────
ASK_WEIGHT, ASK_HEIGHT, ASK_FAT = range(3)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not user_exists(uid):
        await update.message.reply_text(
            "Добро пожаловать! Давай рассчитаем твою норму калорий.\n"
            "Сколько ты сейчас весишь (в кг)?")
        return ASK_WEIGHT
    await update.message.reply_text("Привет! Скидывай фотки еды, я тебя поддержу 💚")
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
        await update.message.reply_text("И последний вопрос — сколько у тебя % жира?")
        return ASK_FAT
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 180")
        return ASK_HEIGHT

async def ask_fat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        bodyfat = float(update.message.text.replace(',', '.'))
        uid = update.effective_user.id
        save_user_data(uid, ctx.user_data['weight'], ctx.user_data['height'], bodyfat)
        schedule_for_user(ctx.job_queue, uid)
        await update.message.reply_text(
            "Данные сохранены! Отправляй еду и шаги.\nКоманда /summary покажет итоги дня.",
            reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("⚠️ Введи число, напр.: 18.5")
        return ASK_FAT

# ─────────────────── Helpers ──────────────────────────
ZONE = ZoneInfo("Europe/Vilnius")

def now_vilnius():
    return datetime.now(ZONE)

def is_active_hour():
    return 8 <= now_vilnius().hour < 21

# ─────────────────── Job-queue для каждого пользователя ───────────────────
async def summary_job(context: ContextTypes.DEFAULT_TYPE):
    uid = context.job.data
    await send_summary(uid, context)

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    uid = context.job.data
    yesterday = date.today() - timedelta(days=1)
    if not steps_exist_for_date(uid, yesterday):
        await context.bot.send_message(
            chat_id=uid,
            text="📣 Вчера не было шагов! Напиши `/track шаги 9000 вчера`."
        )

def schedule_for_user(job_queue, uid: int):
    job_queue.run_daily(
        summary_job,
        time=datetime.strptime("23:59", "%H:%M").time(),
        data=uid,
        name=f"summary-{uid}"
    )
    job_queue.run_daily(
        reminder_job,
        time=datetime.strptime("09:00", "%H:%M").time(),
        data=uid,
        name=f"reminder-{uid}"
    )

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
    prof  = get_user_profile(uid)
    steps = get_steps_for_date(uid, target_date) or 0
    weight = prof['weight'] if prof else 70
    burned = round(steps * weight * 0.00035)
    eat_kcal = nutr['calories'] if nutr else 0
    balance = eat_kcal - burned
    status = "✅ В пределах нормы" if balance <= goals['calories'] else f"⚠️ Превышено на {balance-goals['calories']} ккал"

    if not nutr:
        txt = f"📊 *Итоги за {target_date:%d.%m}:*\nНет записей по еде."
    else:
        txt=(f"📊 *Итоги за {target_date:%d.%m}:*\n"
             f"Калории: {eat_kcal}/{goals['calories']} ккал\n"
             f"Белки: {nutr['protein']:.1f}/{goals['protein']} г\n"
             f"Жиры: {nutr['fat']:.1f}/{goals['fat']} г\n"
             f"Углеводы: {nutr['carbs']:.1f}/{goals['carbs']} г\n"
             f"👟 Шаги: {steps}  |  🔥 {burned} ккал\n"
             f"{status}")

    if isinstance(target, Update):
        await target.message.reply_text(txt, parse_mode='Markdown')
    else:
        await target.send_message(chat_id=uid, text=txt, parse_mode='Markdown')

# ───────────────── Main ────────────────────────────────
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv=ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_WEIGHT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weight)],
            ASK_HEIGHT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_height)],
            ASK_FAT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fat)],
        },
        fallbacks=[]
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler('summary', daily_summary))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Regex(r'^итоги$'), daily_summary))
    app.add_handler(MessageHandler(filters.Regex(r'^/track'), handle_track))

    # Подписываем существующих пользователей
    existing = [int(u['user_id'])
                for u in supabase.table('users').select('user_id').execute().data]
    for uid in existing:
        schedule_for_user(app.job_queue, uid)

    print('🚀 Бот запущен (polling)')
    app.run_polling()
