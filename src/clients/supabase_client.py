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
│ gender   text                         │   │ protein numeric               │
│ created_at timestamp default now()    │   │ fat numeric                   │
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
import base64
from pathlib import Path

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print("🔍 DEBUG: Checking Supabase configuration")
print(f"URL configured: {'Yes' if SUPABASE_URL else 'No'}")
print(f"ANON_KEY configured: {'Yes' if SUPABASE_ANON_KEY else 'No'}")
print(f"SERVICE_ROLE_KEY configured: {'Yes' if SUPABASE_SERVICE_ROLE_KEY else 'No'}")

# Создаем клиенты
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Проверяем подключение
try:
    # Пробуем получить список таблиц
    tables = supabase.table("users").select("count").limit(1).execute()
    print("✅ Supabase connection successful")
except Exception as e:
    print(f"❌ Supabase connection error: {e}")

# Константы для режимов дефицита
DEFICIT_MODES = {
    "Лёгкий": 0,
    "Средний": 500,
    "Экстремальный": 750
}

# ───────────────────────── users helpers ─────────────────────────

def user_exists(user_id: int) -> bool:
    res = supabase.table("users").select("id").eq("user_id", str(user_id)).execute()
    return bool(res.data)

def save_user_data(user_id: int, weight: float, height: int, bodyfat: float, gender: str, deficit_mode: str = "Лёгкий"):
    """Сохраняет данные пользователя"""
    try:
        payload = {
            "user_id": str(user_id),
            "weight": weight,
            "height": height,
            "bodyfat": bodyfat,
            "gender": gender,
            "deficit": DEFICIT_MODES[deficit_mode]
        }
        print(f"🔍 DEBUG: Saving user data for {user_id}: {payload}")
        result = supabase.table("users").upsert(payload, on_conflict="user_id").execute()
        print(f"✅ User data saved successfully: {result.data}")
        return True
    except Exception as e:
        print(f"❌ Failed to save user data: {e}")
        return False

def set_deficit_mode(user_id: int, mode: str) -> None:
    """Обновляет режим дефицита пользователя"""
    if mode not in DEFICIT_MODES:
        raise ValueError(f"Неверный режим дефицита: {mode}")
    
    deficit = DEFICIT_MODES[mode]
    
    try:
        # Verify user exists
        current = supabase.table("users").select("*").eq("user_id", str(user_id)).single().execute()
        if not current.data:
            raise ValueError(f"User {user_id} not found in database")
        
        # Update deficit
        supabase.table("users").update({
            "deficit": deficit
        }).eq("user_id", str(user_id)).execute()
            
    except Exception as e:
        print(f"❌ Failed to update deficit: {e}")
        raise

def get_user_profile(user_id: int):
    try:
        res = supabase.table("users").select("weight, height, bodyfat, gender, deficit").eq("user_id", str(user_id)).single().execute()
        return res.data if res.data else None
    except Exception as e:
        print(f"❌ Failed to get user profile: {e}")
        return None

# ───────────── дневная норма (lean‑mass based) ─────────────

def _calc_targets(weight: float, bodyfat: float, deficit: int = 0):
    """Рассчитывает цели на основе сухой массы тела и дефицита"""
    lean = weight * (1 - bodyfat / 100)
    base_cal = round(lean * 30)
    cal = base_cal - deficit
    protein = round(lean * 2)
    fat = round(lean * 1)
    carbs = max(0, round((cal - protein * 4 - fat * 9) / 4))
    
    return {"calories": cal, "protein": protein, "fat": fat, "carbs": carbs}

def get_user_targets(user_id: int):
    prof = get_user_profile(user_id)
    if not prof:
        return {"calories": 2000, "protein": 100, "fat": 70, "carbs": 200}
    
    deficit = prof.get('deficit', 0)
    if deficit is None:
        deficit = 0
    
    return _calc_targets(prof['weight'], prof['bodyfat'], deficit)

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

# ───────────────────────── Images Storage ───────────────────────
def get_image_url(file_name: str) -> str:
    """Получает приватный URL картинки с токеном доступа"""
    try:
        print(f"🔍 DEBUG: Getting signed URL for {file_name}")
        # Получаем signed URL с ограниченным временем действия (24 часа)
        signed_url = supabase_admin.storage.from_('nutritionbot').create_signed_url(file_name, 86400)
        print(f"✅ Got signed URL: {signed_url}")
        return signed_url['signedURL']
    except Exception as e:
        print(f"⚠️ Failed to get image URL: {e}")
        print(f"Error details: {str(e)}")
        return None

def init_storage():
    """Проверяет доступность хранилища"""
    try:
        # Пробуем получить URL тестового изображения
        test_url = get_image_url('male-bodyfat.jpg')
        if test_url:
            print("✅ Storage access successful")
        else:
            print("⚠️ Storage access failed")
    except Exception as e:
        print(f"⚠️ Storage access warning: {e}")
        print("ℹ️ Bot will continue working without image support")

def upload_image(file_path: str, file_name: str):
    """Загружает картинку в Storage"""
    with open(file_path, 'rb') as f:
        supabase.storage.from_('nutritionbot').upload(file_name, f)

# В самый конец файла:
__all__ = [
    "save_meal", "save_weight", "save_steps", "get_last_weight",
    "get_nutrition_for_date", "get_steps_for_date", "steps_exist_for_date",
    "user_exists", "save_user_data", "get_user_targets", "get_user_profile",
    "save_burned_calories", "get_burned_calories",
    "supabase"  # ← ВАЖНО: чтобы ppitanieal.py мог импортировать его
]
