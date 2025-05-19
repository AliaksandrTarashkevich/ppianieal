import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from supabase_client import save_weight, save_steps, save_food
from dotenv import load_dotenv
load_dotenv()


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

import re

async def handle_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    print("DEBUG текст:", repr(text))
    user_id = update.effective_user.id

    if "вес" in text:
        match = re.search(r"вес[^0-9\-]*([\d]+(?:[.,]\d+)?)", text)
        if match:
            try:
                weight = float(match.group(1).replace(",", "."))
                save_weight(user_id, weight)
                await update.message.reply_text(f"📉 Вес {weight} кг сохранён! Отличная работа!")
            except Exception as e:
                print("Ошибка при сохранении веса:", e)
                await update.message.reply_text("⚠️ Не удалось сохранить вес.")
        else:
            await update.message.reply_text("⚠️ Не смог распознать вес.")

    elif "шаги" in text:
        match = re.search(r"шаги[^0-9\-]*([\d]+)", text)
        if match:
            try:
                steps = int(match.group(1))
                save_steps(user_id, steps)
                await update.message.reply_text(f"🚶 {steps} шагов записано! Так держать!")
            except Exception as e:
                print("Ошибка при сохранении шагов:", e)
                await update.message.reply_text("⚠️ Не удалось сохранить шаги.")
        else:
            await update.message.reply_text("⚠️ Не смог распознать количество шагов.")
    else:
        await update.message.reply_text("📎 Используй формат: /track вес 88.4 или /track шаги 10000")


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/track"), handle_track))
    print("🚀 Бот запущен в polling-режиме")
    app.run_polling()

if __name__ == "__main__":
    main()
