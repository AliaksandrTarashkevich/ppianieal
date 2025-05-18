import os
import random
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Получение переменных окружения
TOKEN = os.getenv("TOKEN")
USER_ID_RAW = os.getenv("USER_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# 🔍 Логируем, чтобы понять, что передано
print("TOKEN:", "OK" if TOKEN else "MISSING")
print("USER_ID:", USER_ID_RAW or "MISSING")
print("WEBHOOK_URL:", WEBHOOK_URL or "MISSING")

# Проверка наличия всех переменных
if not TOKEN or not USER_ID_RAW or not WEBHOOK_URL:
    raise ValueError("❗ Переменные TOKEN, USER_ID и WEBHOOK_URL должны быть заданы")

try:
    USER_ID = int(USER_ID_RAW)
except ValueError:
    raise ValueError("❗ USER_ID должен быть числом")

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

    print(f"✅ Устанавливаю webhook: {WEBHOOK_URL}")
    await app.bot.set_webhook(WEBHOOK_URL)

    await app.run_webhook(
        listen="0.0.0.0",
        port=8000,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
