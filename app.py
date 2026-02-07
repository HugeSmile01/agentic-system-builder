import json
import logging
import os
import pathlib
import sqlite3
import subprocess
import zipfile

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

import google.generativeai as genai

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(JSON_SORT_KEYS=False, JSONIFY_PRETTYPRINT_REGULAR=False)

CORS(app)
limiter = Limiter(app, key_func=get_remote_address, default_limits=["100 per hour"])
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
API_KEY = os.getenv("API_KEY", "devkey")
DATA_ROOT = os.getenv("DATA_ROOT", "./generated")
SQLITE_PATH = os.getenv("SQLITE_PATH", "./data/tasks.db")
USE_CLI = os.getenv("USE_CLI", "").lower() in {"1", "true", "yes"}

FS_BASE_DIR = pathlib.Path(DATA_ROOT).resolve()

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

_supabase_client = None


class ApiError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code



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



def get_json_body():
    data = request.get_json(silent=True)
    if data is None:
        raise ApiError("Invalid or missing JSON body")
    return data



def ensure_data_root():
    FS_BASE_DIR.mkdir(parents=True, exist_ok=True)



def safe_path(relative_path, allow_base=False):
    ensure_data_root()
    candidate = (FS_BASE_DIR / relative_path).resolve()
    if allow_base and candidate == FS_BASE_DIR:
        return candidate
    if FS_BASE_DIR not in candidate.parents:
        raise ApiError("Path traversal detected", status_code=400)
    return candidate



def apply_replacements(content, find_text, replace_text, count):
    if find_text is None:
        raise ApiError("Find text is required")
    if count is None:
        return content.replace(find_text, replace_text)
    return content.replace(find_text, replace_text, int(count))



def get_supabase_client():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        import importlib.util

        if importlib.util.find_spec("supabase") is None:
            return None
        from supabase import create_client

        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _supabase_client
    except Exception as exc:
        logger.warning("Supabase unavailable: %s", exc)
        return None



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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            purpose TEXT NOT NULL,
            audience TEXT,
            constraints TEXT,
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



def call_llm(prompt, model="gemini-1.5-flash"):
    if not prompt:
        return {"error": "Prompt is empty"}
    try:
        if model.startswith("gemini") and GEMINI_KEY:
            model_obj = genai.GenerativeModel(model)
            resp = model_obj.generate_content(prompt)
            return resp.text
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
        return {"error": str(exc)}
    return {"error": "No model configured"}



def parse_agent_intent(prompt):
    llm_prompt = (
        "Return JSON only with schema: {action: 'list|create|update|delete', id: number|null, task: string|null}. "
        f"Prompt: {prompt}"
    )
    response = call_llm(llm_prompt)
    if isinstance(response, dict) and response.get("error"):
        return response
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"error": "LLM response was not JSON", "raw": response}



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



def execute_operations(operations):
    if not isinstance(operations, list):
        raise ApiError("Operations must be a list")
    results = []
    for op in operations:
        if not isinstance(op, dict):
            results.append({"status": "error", "error": "Operation must be object"})
            continue
        op_type = op.get("type")
        path = op.get("path", "")
        try:
            if op_type == "write":
                target = safe_path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(op.get("content", ""))
                results.append({"status": "ok", "path": str(target.relative_to(FS_BASE_DIR))})
            elif op_type == "read":
                target = safe_path(path)
                results.append({"status": "ok", "path": str(target.relative_to(FS_BASE_DIR)), "content": target.read_text()})
            elif op_type == "delete":
                target = safe_path(path)
                target.unlink(missing_ok=True)
                results.append({"status": "ok", "path": str(target.relative_to(FS_BASE_DIR))})
            elif op_type == "mkdir":
                target = safe_path(path)
                target.mkdir(parents=True, exist_ok=True)
                results.append({"status": "ok", "path": str(target.relative_to(FS_BASE_DIR))})
            elif op_type == "rmdir":
                target = safe_path(path)
                target.rmdir()
                results.append({"status": "ok", "path": str(target.relative_to(FS_BASE_DIR))})
            elif op_type == "replace":
                target = safe_path(path)
                content = target.read_text()
                updated = apply_replacements(content, op.get("find"), op.get("replace", ""), op.get("count"))
                target.write_text(updated)
                results.append({"status": "updated", "path": str(target.relative_to(FS_BASE_DIR))})
            else:
                results.append({"status": "error", "error": f"Unknown op type {op_type}"})
        except Exception as exc:
            results.append({"status": "error", "error": str(exc), "path": path})
    return results



def summarize_alignment(purpose, features):
    questions = []
    fixes = []
    enhancements = []
    if not purpose:
        fixes.append("Define a clear system purpose so every feature maps to an outcome.")
    if purpose and features:
        mismatches = [item for item in features if purpose.lower() not in item.lower()]
        if mismatches:
            questions.append("Which features directly advance the stated purpose?")
            fixes.append("Remove or reframe features that do not map to the purpose statement.")
    if not features:
        questions.append("What core flows are required to fulfill the purpose?")
    enhancements.append("Add success metrics to validate the purpose after launch.")
    return {
        "alignment_summary": "Purpose-focused review generated.",
        "questions": questions,
        "fixes": fixes,
        "enhancements": enhancements,
    }


def quality_review(prompt, constraints, audience):
    issues = []
    fixes = []
    questions = []
    enhancements = []
    if not prompt:
        issues.append("Prompt is empty.")
        fixes.append("Provide a clear prompt describing the desired system behavior.")
    if not audience:
        questions.append("Who is the primary user and what is their skill level?")
    if constraints and "vercel" not in constraints.lower():
        enhancements.append("Confirm hosting requirements for Vercel deployment.")
    if prompt:
        questions.append("What edge cases could cause the system to fail?")
        enhancements.append("Add acceptance criteria for each feature.")
    return {
        "issues": issues,
        "fixes": fixes,
        "questions": questions,
        "enhancements": enhancements,
    }


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"error": error.message}), error.status_code


@app.errorhandler(HTTPException)
def handle_http_error(error):
    return json_error(error.description, status=error.code)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    return json_error("Internal server error", status=500, detail=str(error))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/prompt-studio")
def prompt_studio():
    return render_template("prompt-studio.html")


@app.route("/project-workbench")
def project_workbench():
    return render_template("project-workbench.html")


@app.route("/ops-center")
def ops_center():
    return render_template("ops-center.html")


@app.route("/health")
def health():
    backend, _ = db_backend()
    return jsonify(
        {
            "status": "ok",
            "gemini": bool(GEMINI_KEY),
            "supabase": bool(SUPABASE_URL),
            "backend": backend,
            "data_root": str(FS_BASE_DIR),
        }
    )


@app.route("/tasks", methods=["GET", "POST", "PUT", "DELETE"])
@limiter.limit("30 per minute")
def tasks():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = request.get_json(silent=True) or {}
    action = request.method.lower()
    task_id = data.get("id")
    task = data.get("task")
    if action in {"post", "put"}:
        action = "create" if action == "post" else "update"
    if action == "delete":
        action = "delete"
    if action == "get":
        action = "list"
    if action in {"create", "update"} and not task:
        raise ApiError("Task text is required")
    if action in {"update", "delete"} and not task_id:
        raise ApiError("Task id is required")
    result = db_tasks(action, task_id, task)
    return jsonify(result)


@app.route("/agent", methods=["POST"])
@limiter.limit("10 per minute")
def agent():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    prompt = data.get("prompt", "")
    if not prompt:
        raise ApiError("Prompt is required")
    intent = parse_agent_intent(prompt)
    if "error" in intent:
        return jsonify({"intent": intent, "result": intent}), 502
    action = intent.get("action")
    task_id = intent.get("id")
    task = intent.get("task")
    result = db_tasks(action, task_id, task)
    return jsonify({"intent": intent, "result": result})


@app.route("/quality-check", methods=["POST"])
@limiter.limit("15 per minute")
def quality_check():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    prompt = data.get("prompt", "")
    constraints = data.get("constraints", "")
    audience = data.get("audience", "")
    response = quality_review(prompt, constraints, audience)
    return jsonify(response)


@app.route("/alignment-check", methods=["POST"])
@limiter.limit("15 per minute")
def alignment_check():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    purpose = data.get("purpose", "")
    features = data.get("features") or []
    response = summarize_alignment(purpose, features)
    return jsonify(response)


@app.route("/project-brief", methods=["POST"])
@limiter.limit("20 per minute")
def project_brief():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    name = data.get("name", "").strip()
    purpose = data.get("purpose", "").strip()
    audience = data.get("audience", "").strip()
    constraints = data.get("constraints", "").strip()
    if not name or not purpose:
        raise ApiError("Project name and purpose are required")
    conn = get_sqlite_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO project_briefs (name, purpose, audience, constraints) VALUES (?, ?, ?, ?)",
            (name, purpose, audience, constraints),
        )
        conn.commit()
        return jsonify({"status": "ok", "id": cursor.lastrowid})
    finally:
        conn.close()


@app.route("/project-briefs", methods=["GET"])
@limiter.limit("30 per minute")
def project_briefs():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    conn = get_sqlite_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, purpose, audience, constraints, created_at FROM project_briefs ORDER BY id DESC"
        ).fetchall()
        return jsonify({"data": [dict(row) for row in rows]})
    finally:
        conn.close()


@app.route("/fs/list", methods=["POST"])
@limiter.limit("30 per minute")
def fs_list():
    auth_error = require_auth()
    if auth_error:
        return auth_error
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
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    if not target.exists() or not target.is_file():
        raise ApiError("File not found", status_code=404)
    return jsonify({"path": str(target.relative_to(FS_BASE_DIR)), "content": target.read_text()})


@app.route("/fs/write", methods=["POST"])
@limiter.limit("20 per minute")
def fs_write():
    auth_error = require_auth()
    if auth_error:
        return auth_error
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
    auth_error = require_auth()
    if auth_error:
        return auth_error
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
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    if not target.exists() or not target.is_file():
        raise ApiError("File not found", status_code=404)
    target.unlink()
    return jsonify({"status": "deleted", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/fs/bulk", methods=["POST"])
@limiter.limit("10 per minute")
def fs_bulk():
    auth_error = require_auth()
    if auth_error:
        return auth_error
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
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    target = safe_path(data.get("path", ""))
    target.mkdir(parents=True, exist_ok=True)
    return jsonify({"status": "created", "path": str(target.relative_to(FS_BASE_DIR))})


@app.route("/fs/rmdir", methods=["POST"])
@limiter.limit("20 per minute")
def fs_rmdir():
    auth_error = require_auth()
    if auth_error:
        return auth_error
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
    auth_error = require_auth()
    if auth_error:
        return auth_error
    data = get_json_body()
    operations = data.get("operations", [])
    results = execute_operations(operations)
    return jsonify({"results": results})


@app.route("/export", methods=["POST"])
@limiter.limit("5 per minute")
def export_system():
    auth_error = require_auth()
    if auth_error:
        return auth_error
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
                full_path = pathlib.Path(root) / file
                zipf.write(full_path, arcname=full_path.relative_to(folder))
    return send_file(zip_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
