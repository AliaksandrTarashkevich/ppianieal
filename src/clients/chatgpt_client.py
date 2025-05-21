import os
import re
import json
from base64 import b64encode
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Инициализируем OpenAI клиент
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def reconcile_total(data: dict) -> dict:
    """
    Если сумма в breakdown отличается от блока 'total' более чем на 5 %,
    заменяем total на пересчитанную сумму, чтобы не завышать / не занижать дневной итог.
    """
    calc = {"calories": 0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for row in data["breakdown"]:
        calc["calories"] += row["calories"]
        calc["protein"]  += row["protein"]
        calc["fat"]      += row["fat"]
        calc["carbs"]    += row["carbs"]

    if abs(calc["calories"] - data["total"]["calories"]) > calc["calories"] * 0.05:
        data["total"] = calc
    return data

def analyze_food(description: str) -> dict:
    prompt = f"""
Ты нутрициолог. Проанализируй следующее описание еды и рассчитай:
- Калории (целое число, ккал)
- Белки (в граммах, 1 знак после запятой)
- Жиры (в граммах, 1 знак после запятой)
- Углеводы (в граммах, 1 знак после запятой)

Также составь таблицу по каждому продукту с расчётом:
- Название
- Калории
- Белки
- Жиры
- Углеводы

Описание еды:
{description}

Ответ верни строго в виде JSON в следующем формате:
{{
  "total": {{
    "calories": 1234,
    "protein": 120.5,
    "fat": 60.2,
    "carbs": 150.1
  }},
  "breakdown": [
    {{
      "item": "картофель 200г",
      "calories": 170,
      "protein": 4.0,
      "fat": 0.4,
      "carbs": 40.0
    }}
  ]
}}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        print("🧾 [analyze_food] RAW GPT OUTPUT:\n", raw)

        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        json_str = raw[start:end]

        print("📦 [analyze_food] Extracted JSON:\n", json_str)

        data = json.loads(json_str)
        return reconcile_total(data)
    except Exception as e:
        print("❌ GPT parsing error:", e)
        return {}

async def detect_food_items_from_image(image_bytes: bytes) -> str:
    """Определяет названия и веса продуктов по изображению"""
    try:
        encoded = b64encode(image_bytes).decode("utf-8")
        prompt = (
            "Посмотри на фото и назови продукты с примерным весом. "
            "Формат: название 100г, продукт 50г. Без пояснений."
        )

        print("📤 [detect_food_items_from_image] Sending image prompt...")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
                    {"type": "text", "text": prompt}
                ]
            }],
            temperature=0.3,
        )

        raw = response.choices[0].message.content.strip()
        print("🖼️ [detect_food_items_from_image] RAW GPT OUTPUT:\n", raw)
        return raw

    except Exception as e:
        print(f"❌ [detect_food_items_from_image] Image ingredient detection error: {e}")
        return ""


def is_detailed_description(text: str) -> bool:
    return bool(re.search(r'\d{2,3}\s*(г|грам|ml|мл)', text.lower()))
