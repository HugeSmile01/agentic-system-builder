import importlib.util
import os
from typing import Optional


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase_client():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    if importlib.util.find_spec("supabase") is None:
        return None
    from supabase import create_client

    return create_client(SUPABASE_URL, SUPABASE_KEY)


def init_tasks(client=None) -> Optional[dict]:
    client = client or get_supabase_client()
    if client is None:
        return {"error": "Supabase not configured"}
    client.table("tasks").insert([{"text": "Example task"}]).execute()
    return {"status": "ok"}
