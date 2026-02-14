"""Agentic System Builder – Flask application entry point.

A production-ready, autonomous AI system that generates complete software
systems through an intelligent multi-agent workflow.

Author: John Rish Ladica
Affiliation: Student Leader, SLSU-HC – Society of Information Technology Students (SITS)
"""

import io
import json
import logging
import os
import secrets
import zipfile
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from lib.auth import ApiError, generate_token, require_auth
from lib.database import get_sqlite_connection, SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY
from lib.agents import (
    refine_user_prompt,
    create_system_plan,
    generate_project_files,
    review_generated_code,
    refactor_code,
)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="static")
app.config.update(
    JSON_SORT_KEYS=False,
    JSONIFY_PRETTYPRINT_REGULAR=False,
    SECRET_KEY=os.getenv("SECRET_KEY", secrets.token_hex(32)),
)

CORS(app, resources={r"/*": {"origins": "*"}})
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per hour"])

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({
        "error": error.message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), error.status_code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logger.exception("Unexpected error")
    return jsonify({
        "error": "Internal server error",
        "detail": str(error),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 500


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------

@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("5 per hour")
def register():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    full_name = data.get("full_name", "").strip()

    if not email or not password:
        raise ApiError("Email and password are required")
    if len(password) < 8:
        raise ApiError("Password must be at least 8 characters")

    conn = get_sqlite_connection()
    try:
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise ApiError("User already exists", 409)

        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, password_hash, full_name),
        )
        conn.commit()
        user_id = cursor.lastrowid
        return jsonify({"token": generate_token(user_id, email), "user": {"id": user_id, "email": email, "full_name": full_name}})
    finally:
        conn.close()


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per hour")
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        raise ApiError("Email and password are required")

    conn = get_sqlite_connection()
    try:
        user = conn.execute(
            "SELECT id, email, password_hash, full_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            raise ApiError("Invalid credentials", 401)

        conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        conn.commit()
        return jsonify({"token": generate_token(user["id"], user["email"]), "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"]}})
    finally:
        conn.close()


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def get_current_user():
    conn = get_sqlite_connection()
    try:
        user = conn.execute(
            "SELECT id, email, full_name, created_at FROM users WHERE id = ?",
            (request.user_id,),
        ).fetchone()
        if not user:
            raise ApiError("User not found", 404)
        return jsonify(dict(user))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

@app.route("/api/projects", methods=["GET"])
@require_auth
def list_projects():
    conn = get_sqlite_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
            (request.user_id,),
        ).fetchall()
        return jsonify({"projects": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route("/api/projects", methods=["POST"])
@limiter.limit("10 per hour")
@require_auth
def create_project():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    goal = data.get("goal", "").strip()

    if not name or not goal:
        raise ApiError("Project name and goal are required")

    conn = get_sqlite_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO projects (user_id, name, description, goal, audience, ui_style, constraints, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')",
            (request.user_id, name, data.get("description", "").strip(), goal, data.get("audience", ""), data.get("ui_style", ""), data.get("constraints", "")),
        )
        conn.commit()
        return jsonify({"id": cursor.lastrowid, "name": name, "status": "draft"})
    finally:
        conn.close()


@app.route("/api/projects/<int:project_id>", methods=["GET"])
@require_auth
def get_project(project_id):
    conn = get_sqlite_connection()
    try:
        project = conn.execute("SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, request.user_id)).fetchone()
        if not project:
            raise ApiError("Project not found", 404)

        iterations = conn.execute("SELECT * FROM project_iterations WHERE project_id = ? ORDER BY iteration_number DESC", (project_id,)).fetchall()
        files = conn.execute("SELECT * FROM generated_files WHERE project_id = ?", (project_id,)).fetchall()
        return jsonify({"project": dict(project), "iterations": [dict(i) for i in iterations], "files": [dict(f) for f in files]})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agentic system endpoints
# ---------------------------------------------------------------------------

@app.route("/api/refine-prompt", methods=["POST"])
@limiter.limit("20 per hour")
@require_auth
def refine_prompt_endpoint():
    """Step 1: Refine user input into a detailed specification."""
    data = request.get_json() or {}
    user_input = data.get("prompt", "").strip()
    project_id = data.get("project_id")

    if not user_input:
        raise ApiError("Prompt is required")

    refined = refine_user_prompt(user_input, data.get("context"))

    if project_id:
        conn = get_sqlite_connection()
        try:
            project = conn.execute("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, request.user_id)).fetchone()
            if project:
                row = conn.execute("SELECT MAX(iteration_number) as max_iter FROM project_iterations WHERE project_id = ?", (project_id,)).fetchone()
                next_iter = (row["max_iter"] or 0) + 1
                conn.execute("INSERT INTO project_iterations (project_id, iteration_number, refined_prompt) VALUES (?, ?, ?)", (project_id, next_iter, json.dumps(refined)))
                conn.commit()
        finally:
            conn.close()

    return jsonify({"refined": refined, "original": user_input})


@app.route("/api/generate-plan", methods=["POST"])
@limiter.limit("15 per hour")
@require_auth
def generate_plan_endpoint():
    """Step 2: Generate implementation plan."""
    data = request.get_json() or {}
    refined_spec = data.get("refined_spec")
    project_id = data.get("project_id")

    if not refined_spec:
        raise ApiError("Refined specification is required")

    plan = create_system_plan(refined_spec)

    if project_id:
        conn = get_sqlite_connection()
        try:
            conn.execute(
                "UPDATE project_iterations SET plan = ? WHERE project_id = ? AND iteration_number = (SELECT MAX(iteration_number) FROM project_iterations WHERE project_id = ?)",
                (json.dumps(plan), project_id, project_id),
            )
            conn.commit()
        finally:
            conn.close()

    return jsonify({"plan": plan})


@app.route("/api/generate-system", methods=["POST"])
@limiter.limit("5 per hour")
@require_auth
def generate_system_endpoint():
    """Step 3: Generate, review, and refactor a complete system."""
    data = request.get_json() or {}
    plan = data.get("plan")
    refined_spec = data.get("refined_spec")
    project_id = data.get("project_id")

    if not plan or not refined_spec:
        raise ApiError("Plan and refined specification are required")

    logger.info("Generating project files …")
    files = generate_project_files(plan, refined_spec)

    logger.info("Reviewing generated code …")
    review = review_generated_code(files, plan, refined_spec)

    logger.info("Applying refactoring …")
    final_files, refactor_msg = refactor_code(files, review)

    if project_id:
        conn = get_sqlite_connection()
        try:
            conn.execute("DELETE FROM generated_files WHERE project_id = ?", (project_id,))
            for filename, content in final_files.items():
                file_type = filename.rsplit(".", 1)[-1] if "." in filename else "txt"
                conn.execute("INSERT INTO generated_files (project_id, filename, content, file_type) VALUES (?, ?, ?, ?)", (project_id, filename, content, file_type))
            conn.execute(
                "UPDATE project_iterations SET review_notes = ? WHERE project_id = ? AND iteration_number = (SELECT MAX(iteration_number) FROM project_iterations WHERE project_id = ?)",
                (json.dumps(review), project_id, project_id),
            )
            conn.execute("UPDATE projects SET status = 'generated', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
            conn.commit()
        finally:
            conn.close()

    return jsonify({"files": {n: len(c) for n, c in final_files.items()}, "review": review, "refactor_message": refactor_msg, "total_files": len(final_files)})


@app.route("/api/projects/<int:project_id>/export", methods=["GET"])
@limiter.limit("10 per hour")
@require_auth
def export_project(project_id):
    """Export project as a downloadable ZIP archive."""
    conn = get_sqlite_connection()
    try:
        project = conn.execute("SELECT name FROM projects WHERE id = ? AND user_id = ?", (project_id, request.user_id)).fetchone()
        if not project:
            raise ApiError("Project not found", 404)

        files = conn.execute("SELECT filename, content FROM generated_files WHERE project_id = ?", (project_id,)).fetchall()
        if not files:
            raise ApiError("No files to export", 404)

        buf = io.BytesIO()
        project_name = project["name"].replace(" ", "_")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.writestr(f"{project_name}/{f['filename']}", f["content"])
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{project_name}.zip")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Health & informational endpoints
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gemini_configured": bool(GEMINI_KEY),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "version": "3.0.0",
    })


@app.route("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.route("/api")
def api_info():
    return jsonify({
        "service": "Agentic System Builder API",
        "version": "3.0.0",
        "author": "John Rish Ladica – SLSU-HC SITS",
        "endpoints": [
            "/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/me",
            "/api/projects",
            "/api/refine-prompt",
            "/api/generate-plan",
            "/api/generate-system",
            "/api/projects/<id>/export",
        ],
    })


# ---------------------------------------------------------------------------
# Local development server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    get_sqlite_connection().close()
    app.run(host="0.0.0.0", port=5000, debug=False)
