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
        email TEXT UNIQUE NOT NULL CHECK(length(email) <= 255),
        password_hash TEXT NOT NULL CHECK(length(password_hash) <= 255),
        full_name TEXT CHECK(length(full_name) <= 255),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT
    )""",
    """CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)""",
    """CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL CHECK(length(name) <= 255 AND length(name) > 0),
        description TEXT CHECK(length(description) <= 1000),
        goal TEXT NOT NULL CHECK(length(goal) <= 5000 AND length(goal) > 0),
        audience TEXT CHECK(length(audience) <= 500),
        ui_style TEXT CHECK(length(ui_style) <= 500),
        constraints TEXT CHECK(length(constraints) <= 1000),
        status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'generated', 'archived')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )""",
    """CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)""",
    """CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)""",
    """CREATE TABLE IF NOT EXISTS generated_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        filename TEXT NOT NULL CHECK(length(filename) <= 255),
        content TEXT NOT NULL,
        file_type TEXT CHECK(length(file_type) <= 50),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    )""",
    """CREATE INDEX IF NOT EXISTS idx_generated_files_project_id ON generated_files(project_id)""",
    """CREATE TABLE IF NOT EXISTS project_iterations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        iteration_number INTEGER NOT NULL CHECK(iteration_number > 0),
        refined_prompt TEXT NOT NULL,
        plan TEXT,
        review_notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
        UNIQUE(project_id, iteration_number)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_project_iterations_project_id ON project_iterations(project_id)""",
    """CREATE TABLE IF NOT EXISTS project_collaborators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'viewer' CHECK(role IN ('viewer', 'editor')),
        added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        UNIQUE(project_id, user_id)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_project_collaborators_project_id ON project_collaborators(project_id)""",
    """CREATE INDEX IF NOT EXISTS idx_project_collaborators_user_id ON project_collaborators(user_id)""",
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
