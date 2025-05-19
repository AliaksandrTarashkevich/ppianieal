import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def save_weight(user_id, weight):
    supabase.table("user_data").insert({
        "user_id": user_id,
        "weight": weight,
    }).execute()

def save_steps(user_id, steps):
    supabase.table("user_data").insert({
        "user_id": user_id,
        "steps": steps,
    }).execute()

def save_food(user_id, food_text, calories):
    supabase.table("user_data").insert({
        "user_id": user_id,
        "food_text": food_text,
        "calories": calories
    }).execute()
