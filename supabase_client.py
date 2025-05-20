import os
from supabase import create_client, Client
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from datetime import datetime, timedelta

load_dotenv()  # Make sure we load the .env file

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

print("DEBUG: SUPABASE_URL:", SUPABASE_URL)
print("DEBUG: SUPABASE_ANON_KEY:", SUPABASE_ANON_KEY)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def get_record_for_date(user_id, date):
    """Получает запись за конкретную дату"""
    try:
        response = supabase.table("Nutrition Bot")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("date", date.strftime("%Y-%m-%d"))\
            .execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        print("DEBUG: Error getting record:", str(e))
        return None

def get_last_weight(user_id):
    try:
        response = supabase.table("Nutrition Bot")\
            .select("weight")\
            .eq("user_id", user_id)\
            .order("date", desc=True)\
            .limit(1)\
            .execute()
        if response.data and len(response.data) > 0:
            return response.data[0].get("weight")
        return None
    except Exception as e:
        print("DEBUG: Error getting last weight:", str(e))
        return None

def get_steps_for_date(user_id, date):
    try:
        record = get_record_for_date(user_id, date)
        if record:
            return record.get("steps")
        return None
    except Exception as e:
        print("DEBUG: Error getting steps:", str(e))
        return None

def save_weight(user_id, weight, date=None):
    try:
        if date is None:
            date = datetime.now()
        
        last_weight = get_last_weight(user_id)
        weight_change = None
        if last_weight is not None:
            weight_change = weight - last_weight

        print(f"DEBUG: Attempting to save weight {weight} for user {user_id}")
        
        # Проверяем, есть ли уже запись за эту дату
        existing_record = get_record_for_date(user_id, date)
        
        if existing_record:
            # Обновляем существующую запись
            response = supabase.table("Nutrition Bot")\
                .update({"weight": weight})\
                .eq("id", existing_record["id"])\
                .execute()
            print("DEBUG: Updated existing weight record")
        else:
            # Создаем новую запись
            response = supabase.table("Nutrition Bot").insert({
                "user_id": user_id,
                "weight": weight,
                "date": date.strftime("%Y-%m-%d")
            }).execute()
            print("DEBUG: Created new weight record")
            
        print("DEBUG: Save response:", response)
        return {"response": response, "weight_change": weight_change}
    except Exception as e:
        print("DEBUG: Full error details:", str(e))
        print("DEBUG: Error type:", type(e))
        if hasattr(e, 'json'):
            print("DEBUG: Error JSON:", e.json())
        raise e

def save_steps(user_id, steps, date=None):
    try:
        if date is None:
            date = datetime.now()
        
        print(f"DEBUG: Attempting to save {steps} steps for user {user_id} on {date.strftime('%Y-%m-%d')}")
        
        # Проверяем, есть ли уже запись за эту дату
        existing_record = get_record_for_date(user_id, date)
        
        if existing_record:
            # Получаем текущее количество шагов
            current_steps = existing_record.get("steps", 0) or 0
            # Суммируем с новыми шагами
            total_steps = current_steps + steps
            print(f"DEBUG: Found existing record:")
            print(f"DEBUG: - Current steps: {current_steps}")
            print(f"DEBUG: - Adding steps: {steps}")
            print(f"DEBUG: - New total: {total_steps}")
            
            # Обновляем существующую запись
            response = supabase.table("Nutrition Bot")\
                .update({"steps": total_steps})\
                .eq("id", existing_record["id"])\
                .execute()
            print("DEBUG: Successfully updated steps record")
            return {"response": response, "total_steps": total_steps, "is_update": True}
        else:
            print(f"DEBUG: No existing record found, creating new one with {steps} steps")
            # Создаем новую запись
            response = supabase.table("Nutrition Bot").insert({
                "user_id": user_id,
                "steps": steps,
                "date": date.strftime("%Y-%m-%d")
            }).execute()
            print("DEBUG: Successfully created new steps record")
            return {"response": response, "total_steps": steps, "is_update": False}
            
    except Exception as e:
        print("DEBUG: Error saving steps:")
        print("DEBUG: - Error type:", type(e))
        print("DEBUG: - Error message:", str(e))
        if hasattr(e, 'json'):
            print("DEBUG: - Error JSON:", e.json())
        raise e

def save_food(user_id, food_text, calories):
    try:
        date = datetime.now()
        response = supabase.table("Nutrition Bot").insert({
            "user_id": user_id,
            "food_text": food_text,
            "calories": calories,
            "date": date.strftime("%Y-%m-%d")
        }).execute()
        return response
    except Exception as e:
        print("DEBUG: Error saving food:", str(e))
        raise e

def clean_duplicate_records(user_id):
    """Очищает дублирующиеся записи для пользователя, оставляя только последнюю запись за каждый день"""
    try:
        print(f"DEBUG: Starting cleanup for user {user_id}")
        # Получаем все записи пользователя, отсортированные по дате
        response = supabase.table("Nutrition Bot")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("date")\
            .execute()
        
        if not response.data:
            print("DEBUG: No records found for cleanup")
            return
        
        # Группируем записи по дате
        records_by_date = {}
        for record in response.data:
            date = record["date"]
            if date in records_by_date:
                records_by_date[date].append(record)
            else:
                records_by_date[date] = [record]
        
        # Удаляем дубликаты, оставляя только последнюю запись за каждый день
        for date, records in records_by_date.items():
            if len(records) > 1:
                print(f"DEBUG: Found {len(records)} records for {date}")
                # Сортируем записи по id (предполагая, что больший id = более поздняя запись)
                records.sort(key=lambda x: x["id"])
                # Удаляем все записи кроме последней
                for record in records[:-1]:
                    print(f"DEBUG: Deleting duplicate record {record['id']} for {date}")
                    supabase.table("Nutrition Bot")\
                        .delete()\
                        .eq("id", record["id"])\
                        .execute()
        
        print("DEBUG: Cleanup completed successfully")
    except Exception as e:
        print("DEBUG: Error during cleanup:", str(e))
        if hasattr(e, 'json'):
            print("DEBUG: Error JSON:", e.json())
