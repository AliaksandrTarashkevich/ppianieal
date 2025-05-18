import os

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import time
import random
import asyncio

# 🛡️ Получаем значения из переменных окружения (Railway подставит их)
TOKEN = os.getenv("TOKEN")
USER_ID = int(os.getenv("USER_ID"))

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

async def remind(bot):
    await bot.send_message(chat_id=USER_ID, text="Ты уже кушал сегодня? 🍽️")

def schedule_reminders(bot):
    scheduler = BackgroundScheduler(timezone="Europe/Vilnius")
    scheduler.add_job(lambda: asyncio.run(remind(bot)), 'cron', hour=10, minute=0)
    scheduler.add_job(lambda: asyncio.run(remind(bot)), 'cron', hour=15, minute=0)
    scheduler.add_job(lambda: asyncio.run(remind(bot)), 'cron', hour=19, minute=0)
    scheduler.start()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Скидывай фотки еды, я тебя поддержу 💚")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    schedule_reminders(app.bot)

    app.run_polling()
