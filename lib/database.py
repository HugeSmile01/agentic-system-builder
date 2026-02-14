"""Database connections for SQLite and Supabase."""

import importlib.util
import logging
import os
import pathlib
import sqlite3

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")

_is_vercel = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
_tmp_base = "/tmp" if _is_vercel else "."
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(_tmp_base, "data", "agentic.db"))
DATA_ROOT = os.getenv("DATA_ROOT", os.path.join(_tmp_base, "generated"))

FS_BASE_DIR = pathlib.Path(DATA_ROOT).resolve()
try:
    FS_BASE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    FS_BASE_DIR = pathlib.Path(_tmp_base, "generated").resolve()
    FS_BASE_DIR.mkdir(parents=True, exist_ok=True)

_supabase_client = None

_SCHEMA_SQL = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        goal TEXT NOT NULL,
        audience TEXT,
        ui_style TEXT,
        constraints TEXT,
        status TEXT DEFAULT 'draft',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )""",
    """CREATE TABLE IF NOT EXISTS generated_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        content TEXT NOT NULL,
        file_type TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id)
    )""",
    """CREATE TABLE IF NOT EXISTS project_iterations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        iteration_number INTEGER NOT NULL,
        refined_prompt TEXT NOT NULL,
        plan TEXT,
        review_notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id)
    )""",
]


def get_supabase_client():
    """Return a cached Supabase client, or *None* when unavailable."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        if importlib.util.find_spec("supabase") is None:
            return None
        from supabase import create_client

        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _supabase_client
    except Exception as exc:
        logger.warning("Supabase unavailable: %s", exc)
        return None


def get_sqlite_connection():
    """Return an initialised SQLite connection with all tables created."""
    sqlite_path = pathlib.Path(SQLITE_PATH)
    try:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        sqlite_path = pathlib.Path(_tmp_base, "data", "agentic.db")
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    for statement in _SCHEMA_SQL:
        conn.execute(statement)
    conn.commit()
    return conn
