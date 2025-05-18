import os
import random
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Получаем переменные
TOKEN = os.getenv("TOKEN")
USER_ID_RAW = os.getenv("USER_ID")

print("TOKEN:", "OK" if TOKEN else "MISSING")
print("USER_ID:", USER_ID_RAW or "MISSING")

if not TOKEN or not USER_ID_RAW:
    raise ValueError("❗ Переменные TOKEN и USER_ID обязательны")

USER_ID = int(USER_ID_RAW)

def is_active_hour():
    return 8 <= datetime.now().hour < 21

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

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("🚀 Бот запущен в polling-режиме")
    app.run_polling()

if __name__ == "__main__":
    main()
