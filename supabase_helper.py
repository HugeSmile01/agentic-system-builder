import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def init_tasks():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {"error": "Supabase credentials not configured - skipping initialization"}
    from supabase import create_client

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client.table("tasks").insert([{"text": "Example task"}]).execute()
    return {"status": "ok"}
