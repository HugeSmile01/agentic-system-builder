from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import google.generativeai as genai
import json
import logging
import os
from pathlib import Path
import zipfile

from supabase_client import get_supabase_client

app = Flask(__name__, template_folder="templates")
CORS(app)
limiter = Limiter(app, key_func=get_remote_address, default_limits=["100 per hour"])

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
API_KEY = os.getenv("API_KEY", "devkey")
FS_BASE_DIR = Path(os.getenv("FS_BASE_DIR", "./generated")).resolve()

FS_BASE_DIR.mkdir(parents=True, exist_ok=True)

genai.configure(api_key=GEMINI_KEY)


class ApiError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def require_auth():
    if request.headers.get("Authorization") != f"Bearer {API_KEY}":
        raise ApiError("Unauthorized", status_code=401)


def get_json_body():
    if not request.is_json:
        raise ApiError("Expected JSON body")
    return request.get_json(silent=True) or {}


def safe_path(path: str, allow_base: bool = False) -> Path:
    if not path:
        if allow_base:
            return FS_BASE_DIR
        raise ApiError("Path is required")
    resolved = (FS_BASE_DIR / path).resolve()
    if FS_BASE_DIR not in resolved.parents and resolved != FS_BASE_DIR:
        raise ApiError("Path escapes base directory", status_code=403)
    if resolved == FS_BASE_DIR and not allow_base:
        raise ApiError("Path must target a file or subdirectory")
    return resolved


def apply_replacements(content: str, find_text: str, replace_text: str, count: int | None):
    if find_text is None:
        raise ApiError("Find text is required")
    if count is not None:
        return content.replace(find_text, replace_text, int(count))
    return content.replace(find_text, replace_text)


def execute_operations(operations):
    results = []
    if not isinstance(operations, list):
        raise ApiError("Operations must be a list")
    for op in operations:
        if not isinstance(op, dict):
            raise ApiError("Operation must be an object")
        op_type = op.get("type")
        op_path = op.get("path", "")
        if op_type == "write":
            content = op.get("content")
            if content is None:
                raise ApiError("Content is required for write")
            target = safe_path(op_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            results.append(
                {"type": op_type, "path": str(target.relative_to(FS_BASE_DIR)), "status": "ok"}
            )
        elif op_type == "delete":
            target = safe_path(op_path)
            if not target.exists() or not target.is_file():
                raise ApiError("File not found", status_code=404)
            target.unlink()
            results.append(
                {"type": op_type, "path": str(target.relative_to(FS_BASE_DIR)), "status": "deleted"}
            )
        elif op_type == "mkdir":
            target = safe_path(op_path)
            target.mkdir(parents=True, exist_ok=True)
            results.append(
                {"type": op_type, "path": str(target.relative_to(FS_BASE_DIR)), "status": "created"}
            )
        elif op_type == "rmdir":
            target = safe_path(op_path)
            if not target.exists() or not target.is_dir():
                raise ApiError("Directory not found", status_code=404)
            if any(target.iterdir()):
                raise ApiError("Directory not empty", status_code=409)
            target.rmdir()
            results.append(
                {"type": op_type, "path": str(target.relative_to(FS_BASE_DIR)), "status": "removed"}
            )
        elif op_type == "replace":
            find_text = op.get("find")
            replace_text = op.get("replace", "")
            count = op.get("count")
            target = safe_path(op_path)
            if not target.exists() or not target.is_file():
                raise ApiError("File not found", status_code=404)
            content = target.read_text()
            updated = apply_replacements(content, find_text, replace_text, count)
            target.write_text(updated)
            results.append(
                {"type": op_type, "path": str(target.relative_to(FS_BASE_DIR)), "status": "updated"}
            )
        else:
            raise ApiError(f"Unsupported operation: {op_type}")
    return results


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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "gemini": bool(GEMINI_KEY),
            "supabase": bool(SUPABASE_URL),
            "fs_base_dir": str(FS_BASE_DIR),
        }
    )


@app.route("/tasks", methods=["GET", "POST", "PUT", "DELETE"])
@limiter.limit("20 per minute")
def tasks():
    require_auth()
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
