from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
import google.generativeai as genai
import importlib.util
import json
import os
import pathlib
import sqlite3
import subprocess
import zipfile

app = Flask(__name__, template_folder="templates")
app.config.update(
    JSON_SORT_KEYS=False,
    JSONIFY_PRETTYPRINT_REGULAR=False,
)
CORS(app)
limiter = Limiter(app, key_func=get_remote_address, default_limits=["100 per hour"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
API_KEY = os.getenv("API_KEY", "devkey")
DATA_ROOT = os.getenv("DATA_ROOT", "./generated")
SQLITE_PATH = os.getenv("SQLITE_PATH", "./data/tasks.db")
USE_CLI = os.getenv("USE_CLI", "").lower() in {"1", "true", "yes"}

_supabase_client = None


def json_error(message, status=400, detail=None):
    payload = {"error": message}
    if detail:
        payload["detail"] = detail
    return jsonify(payload), status


def get_api_key():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "", 1).strip()
    return request.headers.get("X-API-Key", "").strip()


def require_auth():
    if get_api_key() != API_KEY:
        return json_error("Unauthorized", status=401)
    return None


def ensure_data_root():
    pathlib.Path(DATA_ROOT).mkdir(parents=True, exist_ok=True)


def resolve_path(relative_path):
    ensure_data_root()
    root = pathlib.Path(DATA_ROOT).resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Path traversal detected")
    return candidate


def get_supabase_client():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    if importlib.util.find_spec("supabase") is None:
        return None
    from supabase import create_client

    _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def get_sqlite_connection():
    sqlite_path = pathlib.Path(SQLITE_PATH)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def db_backend():
    client = get_supabase_client()
    if client:
        return "supabase", client
    if USE_CLI:
        return "cli", None
    return "sqlite", None


genai.configure(api_key=GEMINI_KEY)


def call_llm(prompt, model="gemini-1.5-flash"):
    try:
        if model.startswith("gemini"):
            model_obj = genai.GenerativeModel(model)
            resp = model_obj.generate_content(
                "Agent task: Parse to JSON {action: 'list|create|update|delete', id: number or null, task: string}. "
                f"Prompt: {prompt}"
            )
            return json.loads(resp.text)
        if OPENROUTER_KEY:
            import httpx

            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={
                    "model": "google/gemini-flash-exp:free",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=15,
            )
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return {"error": str(exc)}
    return {"error": "No model configured"}


def db_tasks(action=None, task_id=None, task=None):
    backend, client = db_backend()
    if backend == "supabase":
        try:
            if action == "list":
                return {"backend": backend, "data": client.table("tasks").select("*").execute().data}
            if action == "create":
                return {"backend": backend, "data": client.table("tasks").insert({"text": task}).execute().data}
            if action == "update":
                client.table("tasks").update({"text": task}).eq("id", task_id).execute()
                return {"backend": backend, "message": f"Updated ID {task_id}"}
            if action == "delete":
                client.table("tasks").delete().eq("id", task_id).execute()
                return {"backend": backend, "message": f"Deleted ID {task_id}"}
        except Exception as exc:
            return {"backend": backend, "error": str(exc)}
    if backend == "sqlite":
        conn = get_sqlite_connection()
        try:
            if action == "list":
                rows = conn.execute("SELECT id, text, created_at FROM tasks ORDER BY id DESC").fetchall()
                return {"backend": backend, "data": [dict(row) for row in rows]}
            if action == "create":
                cursor = conn.execute("INSERT INTO tasks (text) VALUES (?)", (task,))
                conn.commit()
                return {"backend": backend, "message": f"Created ID {cursor.lastrowid}"}
            if action == "update":
                conn.execute("UPDATE tasks SET text = ? WHERE id = ?", (task, task_id))
                conn.commit()
                return {"backend": backend, "message": f"Updated ID {task_id}"}
            if action == "delete":
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                return {"backend": backend, "message": f"Deleted ID {task_id}"}
        finally:
            conn.close()
    return run_cli(action, task_id, task)


def run_cli(action, task_id=None, task=None):
    cmd = ["./cli.sh", action]
    if task_id:
        cmd.append(str(task_id))
    if task:
        cmd.append(task)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        return {"backend": "cli", "output": result.stdout.strip(), "error": result.stderr.strip()}
    except Exception:
        return {"backend": "cli", "error": "CLI unavailable"}


@app.errorhandler(HTTPException)
def handle_http_error(error):
    return json_error(error.description, status=error.code)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    return json_error("Internal server error", status=500, detail=str(error))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    backend, _ = db_backend()
    return jsonify(
        {
            "status": "ok",
            "gemini": bool(GEMINI_KEY),
            "supabase": bool(SUPABASE_URL),
            "backend": backend,
            "data_root": DATA_ROOT,
        }
    )


@app.route("/tasks", methods=["GET", "POST", "PUT", "DELETE"])
@limiter.limit("30 per minute")
def tasks():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = request.json or {}
    action = request.method.lower()
    task_id = data.get("id")
    task = data.get("task")
    if action in {"create", "update"} and not task:
        return json_error("Task text required", status=400)
    result = db_tasks(action, task_id, task)
    return jsonify(result)


@app.route("/agent", methods=["POST"])
@limiter.limit("10 per minute")
def agent():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.json or {}
    prompt = payload.get("prompt", "")
    if not prompt:
        return json_error("Prompt required", status=400)
    intent = call_llm(prompt)
    action = intent.get("action") if isinstance(intent, dict) else None
    task_id = intent.get("id") if isinstance(intent, dict) else None
    task = intent.get("task") if isinstance(intent, dict) else None
    if not action:
        return json_error("Unable to parse intent", status=400, detail=intent)
    result = db_tasks(action, task_id, task)
    return jsonify({"intent": intent, "result": result})


@app.route("/fs/list")
def fs_list():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    rel_path = request.args.get("path", "")
    try:
        target = resolve_path(rel_path)
    except ValueError as exc:
        return json_error(str(exc), status=400)
    if not target.exists():
        return json_error("Path not found", status=404)
    if not target.is_dir():
        return json_error("Path is not a directory", status=400)
    entries = []
    for entry in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        entries.append(
            {
                "name": entry.name,
                "path": str(entry.relative_to(pathlib.Path(DATA_ROOT).resolve())),
                "type": "file" if entry.is_file() else "dir",
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    return jsonify({"path": str(rel_path or "."), "entries": entries})


@app.route("/fs/read")
def fs_read():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    rel_path = request.args.get("path")
    if not rel_path:
        return json_error("Path required", status=400)
    try:
        target = resolve_path(rel_path)
    except ValueError as exc:
        return json_error(str(exc), status=400)
    if not target.exists():
        return json_error("File not found", status=404)
    if not target.is_file():
        return json_error("Path is not a file", status=400)
    return jsonify({"path": rel_path, "content": target.read_text(encoding="utf-8")})


@app.route("/fs/write", methods=["POST"])
def fs_write():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = request.json or {}
    rel_path = data.get("path")
    content = data.get("content", "")
    if not rel_path:
        return json_error("Path required", status=400)
    try:
        target = resolve_path(rel_path)
    except ValueError as exc:
        return json_error(str(exc), status=400)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return jsonify({"path": rel_path, "status": "written"})


@app.route("/fs/mkdir", methods=["POST"])
def fs_mkdir():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = request.json or {}
    rel_path = data.get("path")
    if not rel_path:
        return json_error("Path required", status=400)
    try:
        target = resolve_path(rel_path)
    except ValueError as exc:
        return json_error(str(exc), status=400)
    target.mkdir(parents=True, exist_ok=True)
    return jsonify({"path": rel_path, "status": "created"})


@app.route("/fs/delete", methods=["DELETE"])
def fs_delete():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = request.json or {}
    rel_path = data.get("path")
    if not rel_path:
        return json_error("Path required", status=400)
    try:
        target = resolve_path(rel_path)
    except ValueError as exc:
        return json_error(str(exc), status=400)
    if not target.exists():
        return json_error("Path not found", status=404)
    if target.is_dir():
        for child in target.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        target.rmdir()
    else:
        target.unlink()
    return jsonify({"path": rel_path, "status": "deleted"})


@app.route("/fs/rename", methods=["POST"])
def fs_rename():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = request.json or {}
    source = data.get("source")
    destination = data.get("destination")
    if not source or not destination:
        return json_error("Source and destination required", status=400)
    try:
        source_path = resolve_path(source)
        destination_path = resolve_path(destination)
    except ValueError as exc:
        return json_error(str(exc), status=400)
    if not source_path.exists():
        return json_error("Source not found", status=404)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.rename(destination_path)
    return jsonify({"source": source, "destination": destination, "status": "renamed"})


@app.route("/export", methods=["POST"])
def export_system():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    system_name = (request.json or {}).get("name", "system")
    folder = resolve_path(system_name)
    zip_path = pathlib.Path(f"{folder}.zip")
    folder.mkdir(parents=True, exist_ok=True)
    readme_path = folder / "README.txt"
    if not readme_path.exists():
        readme_path.write_text("Generated by Agentic System Builder\n", encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(folder):
            for file in files:
                zipf.write(
                    os.path.join(root, file),
                    arcname=os.path.relpath(os.path.join(root, file), folder),
                )
    return send_file(zip_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
