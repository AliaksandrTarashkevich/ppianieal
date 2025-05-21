import os
import re
import json
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
        data = reconcile_total(data)     # ⬅️ добавили проверку
        return data


    except Exception as e:
        print("❌ GPT parsing error:", e)
        return {}

