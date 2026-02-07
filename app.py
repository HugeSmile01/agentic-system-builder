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
                timeout=20,
            )
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.exception("LLM call failed")
                timeout=15,
            )
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return {"error": str(exc)}
    return {"error": "No model configured"}


def db_tasks(action=None, task_id=None, task=None):
    client = get_supabase_client()
    if client is None:
        return {"error": "Supabase not configured"}
    try:
        if action == "list":
            return client.table("tasks").select("*").execute().data
        if action == "create":
            return client.table("tasks").insert({"text": task}).execute().data
        if action == "update":
            client.table("tasks").update({"text": task}).eq("id", task_id).execute()
            return f"Updated ID {task_id}"
        if action == "delete":
            client.table("tasks").delete().eq("id", task_id).execute()
            return f"Deleted ID {task_id}"
    except Exception as exc:
        logger.exception("Supabase task operation failed")
        return {"error": str(exc)}
    return {"error": "Invalid action"}


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"error": error.message}), error.status_code


@app.errorhandler(500)
def handle_internal_error(_):
    return jsonify({"error": "Internal server error"}), 500
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
            "fs_base_dir": str(FS_BASE_DIR),
            "backend": backend,
            "data_root": DATA_ROOT,
        }
    )


@app.route("/tasks", methods=["GET", "POST", "PUT", "DELETE"])
@limiter.limit("20 per minute")
def tasks():
    require_auth()
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
        raise ApiError("Task text is required")
    if action in {"update", "delete"} and not task_id:
        raise ApiError("Task id is required")
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise ApiError("Supabase is required for tasks", status_code=503)
    result = db_tasks(action, task_id, task)
    return jsonify(result)


@app.route("/agent", methods=["POST"])
@limiter.limit("10 per minute")
def agent():
    require_auth()
    data = get_json_body()
    prompt = data.get("prompt", "")
    if not prompt:
        raise ApiError("Prompt is required")
    intent = call_llm(prompt)
    if not isinstance(intent, dict):
        raise ApiError("LLM response is not JSON")
    if "error" in intent:
        return jsonify({"intent": intent, "result": intent}), 502
    action = intent.get("action")
    task_id = intent.get("id")
    task = intent.get("task")
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise ApiError("Supabase is required for agent tasks", status_code=503)
    result = db_tasks(action, task_id, task)
    return jsonify({"intent": intent, "result": result})


@app.route("/fs/list", methods=["POST"])
@limiter.limit("30 per minute")
def fs_list():
    require_auth()
    data = get_json_body()
    path = data.get("path", "")
    target = safe_path(path, allow_base=True)
    if not target.exists() or not target.is_dir():
        raise ApiError("Directory not found", status_code=404)
    entries = []
    for item in sorted(target.iterdir()):
        entries.append(
            {
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size,
            }
        )
    return jsonify({"path": str(target.relative_to(FS_BASE_DIR)), "entries": entries})


@app.route("/fs/read", methods=["POST"])
@limiter.limit("30 per minute")
def fs_read():
    require_auth()
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    if not target.exists() or not target.is_file():
        raise ApiError("File not found", status_code=404)
    return jsonify({"path": str(target.relative_to(FS_BASE_DIR)), "content": target.read_text()})


@app.route("/fs/write", methods=["POST"])
@limiter.limit("20 per minute")
def fs_write():
    require_auth()
    data = get_json_body()
    content = data.get("content")
    if content is None:
        raise ApiError("Content is required")
    target = safe_path(data.get("path", ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return jsonify({"status": "ok", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/fs/replace", methods=["POST"])
@limiter.limit("20 per minute")
def fs_replace():
    require_auth()
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    find_text = data.get("find")
    replace_text = data.get("replace", "")
    count = data.get("count")
    if not target.exists() or not target.is_file():
        raise ApiError("File not found", status_code=404)
    content = target.read_text()
    updated = apply_replacements(content, find_text, replace_text, count)
    target.write_text(updated)
    return jsonify({"status": "updated", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/fs/delete", methods=["POST"])
@limiter.limit("20 per minute")
def fs_delete():
    require_auth()
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    if not target.exists() or not target.is_file():
        raise ApiError("File not found", status_code=404)
    target.unlink()
    return jsonify({"status": "deleted", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/fs/bulk", methods=["POST"])
@limiter.limit("10 per minute")
def fs_bulk():
    require_auth()
    data = get_json_body()
    files = data.get("files")
    if not isinstance(files, list):
        raise ApiError("Files must be a list")
    results = []
    for entry in files:
        if not isinstance(entry, dict):
            raise ApiError("File entry must be an object")
        file_path = entry.get("path", "")
        content = entry.get("content")
        if content is None:
            raise ApiError("Content is required for bulk write")
        target = safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        results.append({"path": str(target.relative_to(FS_BASE_DIR)), "status": "ok"})
    return jsonify({"results": results})


@app.route("/fs/mkdir", methods=["POST"])
@limiter.limit("20 per minute")
def fs_mkdir():
    require_auth()
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    target.mkdir(parents=True, exist_ok=True)
    return jsonify({"status": "created", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/fs/rmdir", methods=["POST"])
@limiter.limit("20 per minute")
def fs_rmdir():
    require_auth()
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    if not target.exists() or not target.is_dir():
        raise ApiError("Directory not found", status_code=404)
    if any(target.iterdir()):
        raise ApiError("Directory not empty", status_code=409)
    target.rmdir()
    return jsonify({"status": "removed", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/execute", methods=["POST"])
@limiter.limit("5 per minute")
def execute_plan():
    require_auth()
    data = get_json_body()
    operations = data.get("operations", [])
    results = execute_operations(operations)
    return jsonify({"results": results})


@app.route("/export", methods=["POST"])
def export_system():
    require_auth()
    data = get_json_body()
    system_name = data.get("name", "system")
    folder = safe_path(system_name)
    zip_path = folder.with_suffix(".zip")
    folder.mkdir(parents=True, exist_ok=True)
    readme_path = folder / "README.txt"
    readme_path.write_text("Generated by Agentic System Builder\n", encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(folder):
            for file in files:
                full_path = Path(root) / file
                zipf.write(
                    full_path,
                    arcname=full_path.relative_to(folder),
                )
    return send_file(zip_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
