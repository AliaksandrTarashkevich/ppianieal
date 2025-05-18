import os
import random
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Получение переменных окружения
TOKEN = os.getenv("TOKEN")
USER_ID = os.getenv("USER_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TOKEN or not USER_ID or not WEBHOOK_URL:
    raise ValueError("❗ Переменные TOKEN, USER_ID и WEBHOOK_URL должны быть заданы")

USER_ID = int(USER_ID)

def is_active_hour():
    current_hour = datetime.now().hour
    return 8 <= current_hour < 21

support_messages = [
    "Отличный выбор!",
    "Ты молодец, что заботишься о себе!",
    "Выглядит вкусно! Горд тобой!",
    "Сила в регулярности — так держать!",
    "Питайся и побеждай 💪"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_active_hour():
        await update.message.reply_text("Привет! Скидывай фотки еды, я тебя поддержу 💚")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_active_hour():
        return
    reply = random.choice(support_messages)
    await update.message.reply_text(reply)

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    await app.bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")

    await app.run_webhook(
    listen="0.0.0.0",
    port=8000,  # ← обязательно 8000
    webhook_url=WEBHOOK_URL
)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
