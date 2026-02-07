import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def init_tasks():
    from supabase import create_client

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client.table("tasks").insert([{"text": "Example task"}]).execute()
