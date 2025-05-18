import os
import asyncio
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import time

# Получаем переменные из окружения
TOKEN = os.getenv("TOKEN")
USER_ID_RAW = os.getenv("USER_ID")

if not TOKEN or not USER_ID_RAW:
    raise ValueError("❗ Переменные окружения TOKEN и USER_ID должны быть заданы")

try:
    USER_ID = int(USER_ID_RAW)
except ValueError:
    raise ValueError("❗ USER_ID должен быть целым числом")

print("✅ Переменные окружения загружены.")
print("📡 Бот запускается...")

support_messages = [
    "Отличный выбор!",
    "Ты молодец, что заботишься о себе!",
    "Выглядит вкусно! Горд тобой!",
    "Сила в регулярности — так держать!",
    "Питайся и побеждай 💪"
]

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = random.choice(support_messages)
    await update.message.reply_text(reply)
    print("📷 Получена фотка. Ответ отправлен.")

async def remind(bot):
    await bot.send_message(chat_id=USER_ID, text="Ты уже кушал сегодня? 🍽️")
    print("🔔 Напоминание отправлено.")

def schedule_reminders(bot):
    scheduler = BackgroundScheduler(timezone="Europe/Vilnius")
    scheduler.add_job(lambda: asyncio.run(remind(bot)), 'cron', hour=10, minute=0)
    scheduler.add_job(lambda: asyncio.run(remind(bot)), 'cron', hour=15, minute=0)
    scheduler.add_job(lambda: asyncio.run(remind(bot)), 'cron', hour=19, minute=0)
    scheduler.start()
    print("⏰ Планировщик запущен.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Скидывай фотки еды, я тебя поддержу 💚")
    print("👋 Получена команда /start")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    schedule_reminders(app.bot)

    print("🚀 Бот запущен. Ждёт события...")
    app.run_polling()
