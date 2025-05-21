# ✅ supabase_client.py — helper layer for Supabase 💾
"""
Функции, которые вызываются из ppitanieal.py:
• user_exists, save_user_data, get_user_profile
• get_user_targets  – расчёт дневной нормы по LBM
• save_weight / save_steps  (+steps_exist_for_date, get_steps_for_date)
• save_meal  – сохраняет калории/БЖУ блюда
• get_nutrition_for_date – суммирует еду за дату
• save_burned_calories / get_burned_calories – сохраняет/получает сожженные калории

Структура таблиц (минимум):
┌──────────────── users ────────────────┐   ┌──────────── meals ────────────┐
│ id (uuid, PK, default uuid)           │   │ id (uuid, PK)                 │
│ user_id  text UNIQUE                  │   │ user_id text                  │
│ weight   numeric                      │   │ date date                     │
│ height   integer                      │   │ description text              │
│ bodyfat  numeric                      │   │ calories integer              │
│ created_at timestamp default now()    │   │ protein numeric               │
│                                       │   │ fat numeric                   │
│                                       │   │ carbs numeric                 │
└───────────────────────────────────────┘   └───────────────────────────────┘

┌──────────── burned_calories ──────────┐   ┌─────── Nutrition Bot ─────────┐
│ id (uuid, PK)                         │   │ id | user_id | date           │
│ user_id text                          │   │    | weight numeric           │
│ date date                             │   │    | steps integer            │
│ calories integer                      │   │                               │
└───────────────────────────────────────┘   └───────────────────────────────┘
"""
import os
from datetime import date
from supabase import create_client, Client
from dotenv import load_dotenv
from postgrest.exceptions import APIError

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ───────────────────────── users helpers ─────────────────────────

def user_exists(user_id: int) -> bool:
    res = supabase.table("users").select("id").eq("user_id", str(user_id)).execute()
    return bool(res.data)

def save_user_data(user_id: int, weight: float, height: int, bodyfat: float):
    payload = {
        "user_id": str(user_id),
        "weight": weight,
        "height": height,
        "bodyfat": bodyfat,
    }
    supabase.table("users").upsert(payload, on_conflict="user_id").execute()


def get_user_profile(user_id: int):
    res = supabase.table("users").select("weight, height, bodyfat").eq("user_id", str(user_id)).single().execute()
    return res.data if res.data else None

# ───────────── дневная норма (lean‑mass based) ─────────────

def _calc_targets(weight: float, bodyfat: float):
    lean = weight * (1 - bodyfat / 100)
    cal = round(lean * 30)  # поддержание 30 ккал/кг LBM
    protein = round(lean * 2)  # г/день
    fat = round(lean * 1)      # г/день
    carbs = max(0, round((cal - protein * 4 - fat * 9) / 4))
    return {"calories": cal, "protein": protein, "fat": fat, "carbs": carbs}

def get_user_targets(user_id: int):
    prof = get_user_profile(user_id)
    if not prof:
        return {"calories": 2000, "protein": 100, "fat": 70, "carbs": 200}
    return _calc_targets(prof['weight'], prof['bodyfat'])

# ──────────── last weight helper ────────────

def get_last_weight(user_id: int, *, exclude_date: date | None = None):
    q = supabase.table("Nutrition Bot").select("weight, date").eq("user_id", str(user_id))
    if exclude_date:
        q = q.neq("date", str(exclude_date))
    res = q.order("date", desc=True).limit(1).execute()
    if res.data:
        return res.data[0].get("weight")
    return None

# ───────────────────────── weight / steps ───────────────────────

def _get_record(user_id: int, d: date):
    res = supabase.table("Nutrition Bot").select("id, weight, steps").eq("user_id", str(user_id)).eq("date", str(d)).execute()
    return res.data[0] if res.data else None

def save_weight(user_id: int, weight: float, *, date: date):
    rec = _get_record(user_id, date)
    if rec:
        supabase.table("Nutrition Bot").update({"weight": weight}).eq("id", rec['id']).execute()
    else:
        supabase.table("Nutrition Bot").insert({"user_id": str(user_id), "date": str(date), "weight": weight}).execute()


def save_steps(user_id: int, steps: int, *, date: date):
    rec = _get_record(user_id, date)
    if rec:
        supabase.table("Nutrition Bot").update({"steps": steps}).eq("id", rec['id']).execute()
    else:
        supabase.table("Nutrition Bot").insert({"user_id": str(user_id), "date": str(date), "steps": steps}).execute()


def get_steps_for_date(user_id: int, d: date):
    rec = _get_record(user_id, d)
    if rec:
        return rec.get("steps")
    return None

def steps_exist_for_date(user_id: int, d: date) -> bool:
    return get_steps_for_date(user_id, d) is not None

# ───────────────────────── Meals / Nutrition ───────────────────

def save_meal(user_id: int, desc: str, cal: int, prot: float, fat: float, carbs: float):
    supabase.table("meals").insert({
        "user_id": str(user_id),
        "date": str(date.today()),
        "description": desc,
        "calories": cal,
        "protein": prot,
        "fat": fat,
        "carbs": carbs,
    }).execute()


def get_nutrition_for_date(user_id: int, d: date):
    res = supabase.table("meals").select("calories, protein, fat, carbs").eq("user_id", str(user_id)).eq("date", str(d)).execute()
    if not res.data:
        return None
    total = {"calories": 0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    for r in res.data:
        total["calories"] += r.get("calories") or 0
        total["protein"] += r.get("protein") or 0
        total["fat"]     += r.get("fat") or 0
        total["carbs"]   += r.get("carbs") or 0
    return total

def save_burned_calories(user_id: int, calories: int, date: date) -> None:
    """Сохраняет сожженные калории за день"""
    try:
        # Проверяем, есть ли уже запись за этот день
        res = supabase.table("burned_calories").select("id") \
            .eq("user_id", str(user_id)) \
            .eq("date", str(date)) \
            .execute()
        
        if res.data:
            # Обновляем существующую запись
            supabase.table("burned_calories") \
                .update({"calories": calories}) \
                .eq("id", res.data[0]["id"]) \
                .execute()
        else:
            # Создаем новую запись
            supabase.table("burned_calories").insert({
                "user_id": str(user_id),
                "date": str(date),
                "calories": calories
            }).execute()
    except APIError as e:
        print(f"❌ Failed to save burned calories: {e}")

def get_burned_calories(user_id: int, date: date) -> int:
    """Возвращает сожженные калории за день"""
    try:
        res = supabase.table("burned_calories").select("calories") \
            .eq("user_id", str(user_id)) \
            .eq("date", str(date)) \
            .execute()
        return res.data[0]["calories"] if res.data else 0
    except APIError as e:
        print(f"❌ Failed to get burned calories: {e}")
        return 0

# В самый конец файла:
__all__ = [
    "save_meal", "save_weight", "save_steps", "get_last_weight",
    "get_nutrition_for_date", "get_steps_for_date", "steps_exist_for_date",
    "user_exists", "save_user_data", "get_user_targets", "get_user_profile",
    "supabase"  # ← ВАЖНО: чтобы ppitanieal.py мог импортировать его
]
