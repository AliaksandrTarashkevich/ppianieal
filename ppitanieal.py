import os
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from supabase_client import save_weight, save_steps, save_food, get_steps_for_date, clean_duplicate_records
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

# Очищаем дублирующиеся записи при запуске
clean_duplicate_records(USER_ID)

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
        await update.message.reply_text("Привет! Я помогу тебе следить за здоровьем. Отправляй мне:\n"
                                      "📝 /track вес X - чтобы записать вес\n"
                                      "🚶 /track шаги X - чтобы записать шаги\n"
                                      "🍽 фото еды - для анализа питания")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_active_hour():
        return
    reply = random.choice(support_messages)
    await update.message.reply_text(reply)

async def check_steps_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет, были ли записаны шаги за вчерашний день"""
    yesterday = datetime.now(ZoneInfo("Europe/Vilnius")) - timedelta(days=1)
    steps = get_steps_for_date(USER_ID, yesterday)
    
    if steps is None:
        await context.bot.send_message(
            chat_id=USER_ID,
            text=f"📝 Не забудь записать количество шагов за вчера ({yesterday.strftime('%d.%m.%Y')})!\n"
                 f"Используй команду: /track шаги X вчера"
        )

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет ежедневный отчет в полночь"""
    # TODO: Добавить подсчет калорий и БЖУ за день
    await context.bot.send_message(
        chat_id=USER_ID,
        text="📊 Ежедневный отчет будет доступен после реализации анализа питания"
    )

import re

async def handle_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    print("DEBUG текст:", repr(text))
    user_id = update.effective_user.id

    # Определяем дату (сегодня или вчера)
    date = datetime.now(ZoneInfo("Europe/Vilnius"))
    if "вчера" in text:
        date = date - timedelta(days=1)
        text = text.replace("вчера", "").strip()

    if "вес" in text:
        match = re.search(r"вес[^0-9\-]*([\d]+(?:[.,]\d+)?)", text)
        if match:
            try:
                weight = float(match.group(1).replace(",", "."))
                result = save_weight(user_id, weight, date)
                weight_change = result.get("weight_change")
                
                message = f"📉 Вес {weight} кг "
                if "Updated existing weight record" in str(result.get("response")):
                    message += "обновлён"
                else:
                    message += "сохранён"
                
                if date.date() != datetime.now(ZoneInfo("Europe/Vilnius")).date():
                    message += f" за {date.strftime('%d.%m.%Y')}"
                
                if weight_change is not None:
                    if weight_change > 0:
                        message += f"\n📈 Изменение: +{weight_change:.1f} кг"
                    elif weight_change < 0:
                        message += f"\n📉 Изменение: {weight_change:.1f} кг"
                    else:
                        message += "\n➖ Вес не изменился"
                message += "\nОтличная работа!"
                
                await update.message.reply_text(message)
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
                result = save_steps(user_id, steps, date)
                
                # Гарантированно получаем итоговое количество шагов
                total_steps = result.get("total_steps", 0)
                print(f"DEBUG: Total steps after saving: {total_steps}")
                
                # Явно приводим к int для расчетов
                total_steps = int(total_steps)
                is_update = result.get("is_update", False)
                
                if is_update:
                    message = f"🚶 +{steps} шагов (всего за день: {total_steps})"
                else:
                    message = f"🚶 {steps} шагов записано"
                
                if date.date() != datetime.now(ZoneInfo("Europe/Vilnius")).date():
                    message += f" за {date.strftime('%d.%m.%Y')}"
                
                # Сколько шагов осталось до цели
                remaining = max(0, 10000 - total_steps)
                
                if total_steps >= 10000:
                    message += f"\n🎉 Отличный результат! Ты достиг дневной цели в 10,000 шагов!"
                    if total_steps > 10000:
                        message += f" Ты прошел на {total_steps - 10000} шагов больше!"
                else:
                    message += f"\n💪 Осталось пройти ещё {remaining} шагов до дневной цели. Ты справишься!"
                
                await update.message.reply_text(message)
            except Exception as e:
                print("Ошибка при сохранении шагов:", e)
                await update.message.reply_text("⚠️ Не удалось сохранить шаги.")
        else:
            await update.message.reply_text("⚠️ Не смог распознать количество шагов.")
    else:
        await update.message.reply_text("📎 Используй формат:\n"
                                      "/track вес 88.4 - записать вес\n"
                                      "/track шаги 10000 - записать шаги\n"
                                      "Добавь 'вчера' в конце, чтобы записать за вчерашний день")


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/track"), handle_track))
    
    # Добавляем ежедневные задачи
    job_queue = app.job_queue
    
    # Проверка шагов в 9:00
    job_queue.run_daily(
        check_steps_reminder,
        time=datetime.strptime("09:00", "%H:%M").time(),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    
    # Ежедневный отчет в 00:00
    job_queue.run_daily(
        daily_summary,
        time=datetime.strptime("00:00", "%H:%M").time(),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    
    print("🚀 Бот запущен в polling-режиме")
    app.run_polling()

if __name__ == "__main__":
    main()
