import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from supabase_client import save_weight, save_steps, save_food

# Получаем переменные
TOKEN = os.getenv("TOKEN")
USER_ID_RAW = os.getenv("USER_ID")

print("TOKEN:", "OK" if TOKEN else "MISSING")
print("USER_ID:", USER_ID_RAW or "MISSING")

if not TOKEN or not USER_ID_RAW:
    raise ValueError("❗ Переменные TOKEN и USER_ID обязательны")

USER_ID = int(USER_ID_RAW)

def is_active_hour():
    now = datetime.now(ZoneInfo("Europe/Vilnius"))
    return 8 <= now.hour < 21

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

async def handle_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "вес" in text:
        try:
            weight = float(text.split("вес")[1].strip())
            save_weight(update.effective_user.id, weight)
            await update.message.reply_text(f"📉 Вес {weight} кг сохранён! Отлично держишь темп!")
        except:
            await update.message.reply_text("⚠️ Не смог распознать вес.")
    elif "шаги" in text:
        try:
            steps = int(text.split("шаги")[1].strip())
            save_steps(update.effective_user.id, steps)
            await update.message.reply_text(f"🚶‍♂️ Шаги {steps} записаны. Продолжай в том же духе!")
        except:
            await update.message.reply_text("⚠️ Не смог распознать количество шагов.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/track"), handle_track))
    print("🚀 Бот запущен в polling-режиме")
    app.run_polling()

if __name__ == "__main__":
    main()
