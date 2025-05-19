import os
from supabase import create_client, Client
from dotenv import load_dotenv
from postgrest.exceptions import APIError

load_dotenv()  # Make sure we load the .env file

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

print("DEBUG: SUPABASE_URL:", SUPABASE_URL)
print("DEBUG: SUPABASE_ANON_KEY:", SUPABASE_ANON_KEY)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def save_weight(user_id, weight):
    try:
        print(f"DEBUG: Attempting to save weight {weight} for user {user_id}")
        # First, let's check if the table exists
        try:
            # Try to get table info
            table_info = supabase.table("Nutrition Bot").select("*").limit(1).execute()
            print("DEBUG: Table exists and is accessible")
        except APIError as e:
            print(f"DEBUG: Table access error: {str(e)}")
            print("DEBUG: Please check if table 'Nutrition Bot' exists in your Supabase database")
            raise

        # Now try to insert
        response = supabase.table("Nutrition Bot").insert({
            "user_id": user_id,
            "weight": weight
        }).execute()
        print("DEBUG: Save response:", response)
        return response
    except Exception as e:
        print("DEBUG: Full error details:", str(e))
        print("DEBUG: Error type:", type(e))
        if hasattr(e, 'json'):
            print("DEBUG: Error JSON:", e.json())
        raise e

def save_steps(user_id, steps):
    supabase.table("Nutrition Bot").insert({
        "user_id": user_id,
        "steps": steps
    }).execute()

def save_food(user_id, food_text, calories):
    supabase.table("Nutrition Bot").insert({
        "user_id": user_id,
        "food_text": food_text,
        "calories": calories
    }).execute()
