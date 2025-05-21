import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv
from base64 import b64encode

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

    # если GPT-total «плавает» > 5 %
    if abs(calc["calories"] - data["total"]["calories"]) > calc["calories"] * 0.05:
        data["total"] = calc               # подменяем кривой total
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
    }},
    ...
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
        print("🧾 GPT raw response:\n", raw)

        # Если markdown-блок — чистим
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()

        # Находим JSON внутри текста
        start = raw.find("{")
        end = raw.rfind("}") + 1
        json_str = raw[start:end]

        print("📦 Extracted JSON:\n", json_str)

        data = json.loads(json_str)
        data = reconcile_total(data)
        return data

    except Exception as e:
        print("❌ GPT parsing error:", e)
        return {}

import re, json
from base64 import b64encode

async def analyze_image(image_bytes: bytes) -> dict:
    """Анализирует изображение и возвращает КБЖУ"""
    try:
        base64_image = b64encode(image_bytes).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Ты нутрициолог. Проанализируй изображение блюда и рассчитай примерное количество калорий, белков, жиров и углеводов. "
                            "Ответ верни строго в формате JSON как указано ниже:\n"
                            "{\n"
                            "  \"total\": {\n"
                            "    \"calories\": 500,\n"
                            "    \"protein\": 25.0,\n"
                            "    \"fat\": 20.0,\n"
                            "    \"carbs\": 50.0\n"
                            "  },\n"
                            "  \"breakdown\": [\n"
                            "    {\n"
                            "      \"item\": \"куриная грудка\",\n"
                            "      \"calories\": 250,\n"
                            "      \"protein\": 25.0,\n"
                            "      \"fat\": 5.0,\n"
                            "      \"carbs\": 0.0\n"
                            "    }\n"
                            "  ]\n"
                            "}"
                        )
                    }
                ]
            }
        ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.3,
        )

        content = response.choices[0].message.content.strip()

        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        data = json.loads(content)
        return reconcile_total(data)

    except Exception as e:
        print(f"❌ Image parsing error: {e}")
        return {}


def is_detailed_description(text: str) -> bool:
    return bool(re.search(r'\d{2,3}\s*(г|грам|ml|мл)', text.lower()))
