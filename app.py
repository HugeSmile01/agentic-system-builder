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
import sqlite3
import zipfile
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from lib.auth import (
    ApiError,
    generate_token,
    generate_password_reset_token,
    verify_password_reset_token,
    require_auth,
)
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

API_VERSION = "3.1.0"

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


@app.route("/api/auth/update-profile", methods=["PUT"])
@require_auth
def update_profile():
    """Update user profile information."""
    data = request.get_json() or {}
    full_name = data.get("full_name", "").strip()
    
    if not full_name:
        raise ApiError("Full name is required")
    
    conn = get_sqlite_connection()
    try:
        conn.execute(
            "UPDATE users SET full_name = ? WHERE id = ?",
            (full_name, request.user_id),
        )
        conn.commit()
        return jsonify({"message": "Profile updated successfully", "full_name": full_name})
    finally:
        conn.close()


@app.route("/api/auth/change-password", methods=["PUT"])
@require_auth
def change_password():
    """Change user password."""
    data = request.get_json() or {}
    current_password = data.get("current_password", "").strip()
    new_password = data.get("new_password", "").strip()
    
    if not current_password or not new_password:
        raise ApiError("Current and new passwords are required")
    if len(new_password) < 8:
        raise ApiError("New password must be at least 8 characters")
    
    conn = get_sqlite_connection()
    try:
        user = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (request.user_id,),
        ).fetchone()
        
        if not user or not check_password_hash(user["password_hash"], current_password):
            raise ApiError("Current password is incorrect", 401)
        
        new_password_hash = generate_password_hash(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, request.user_id),
        )
        conn.commit()
        return jsonify({"message": "Password changed successfully"})
    finally:
        conn.close()


@app.route("/api/auth/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")
def forgot_password():
    """Request password reset token."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    
    if not email:
        raise ApiError("Email is required")
    
    conn = get_sqlite_connection()
    try:
        user = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        
        # Always return success to prevent email enumeration
        if user:
            token = generate_password_reset_token(email)
            # In production, send this token via email
            logger.info(f"Password reset token generated for {email}")
            # TODO: Send email with reset link
        
        return jsonify({
            "message": "If an account exists with this email, a reset link has been sent"
        })
    finally:
        conn.close()


@app.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """Reset password using reset token."""
    data = request.get_json() or {}
    token = data.get("token", "").strip()
    new_password = data.get("new_password", "").strip()
    
    if not token or not new_password:
        raise ApiError("Token and new password are required")
    if len(new_password) < 8:
        raise ApiError("Password must be at least 8 characters")
    
    payload = verify_password_reset_token(token)
    email = payload.get("email")
    
    conn = get_sqlite_connection()
    try:
        user = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        
        if not user:
            raise ApiError("User not found", 404)
        
        new_password_hash = generate_password_hash(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, user["id"]),
        )
        conn.commit()
        return jsonify({"message": "Password reset successfully"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

@app.route("/api/projects", methods=["GET"])
@require_auth
def list_projects():
    """List projects with optional search, filter, and pagination."""
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 50))))
    offset = (page - 1) * per_page
    
    conn = get_sqlite_connection()
    try:
        # Build WHERE clause
        where_clauses = ["user_id = ?"]
        params = [request.user_id]
        
        if search:
            where_clauses.append("(name LIKE ? OR description LIKE ? OR goal LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if status_filter:
            where_clauses.append("status = ?")
            params.append(status_filter)
        
        where_clause = " WHERE " + " AND ".join(where_clauses)
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM projects{where_clause}"
        total = conn.execute(count_query, params).fetchone()[0]
        
        # Get paginated results
        query = f"SELECT * FROM projects{where_clause} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params_with_pagination = params + [per_page, offset]
        rows = conn.execute(query, params_with_pagination).fetchall()
        
        return jsonify({
            "projects": [dict(r) for r in rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        })
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


@app.route("/api/projects/<int:project_id>", methods=["PUT"])
@require_auth
def update_project(project_id):
    """Update project details."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    
    if not name:
        raise ApiError("Project name is required")
    
    conn = get_sqlite_connection()
    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        conn.execute(
            "UPDATE projects SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (name, description, project_id)
        )
        conn.commit()
        return jsonify({"message": "Project updated successfully", "id": project_id})
    finally:
        conn.close()


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
@require_auth
def delete_project(project_id):
    """Delete a project and all associated data."""
    conn = get_sqlite_connection()
    try:
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        # Delete associated data
        conn.execute("DELETE FROM generated_files WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_iterations WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_collaborators WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        
        return jsonify({"message": "Project deleted successfully"})
    finally:
        conn.close()


@app.route("/api/projects/<int:project_id>/collaborators", methods=["GET"])
@require_auth
def list_collaborators(project_id):
    """List project collaborators."""
    conn = get_sqlite_connection()
    try:
        # Verify user has access to project
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        collaborators = conn.execute(
            """SELECT c.id, c.user_id, c.role, c.added_at, u.email, u.full_name
               FROM project_collaborators c
               JOIN users u ON c.user_id = u.id
               WHERE c.project_id = ?
               ORDER BY c.added_at DESC""",
            (project_id,)
        ).fetchall()
        
        return jsonify({"collaborators": [dict(c) for c in collaborators]})
    finally:
        conn.close()


@app.route("/api/projects/<int:project_id>/collaborators", methods=["POST"])
@require_auth
def add_collaborator(project_id):
    """Add a collaborator to a project."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    role = data.get("role", "viewer").strip()
    
    if not email:
        raise ApiError("Email is required")
    if role not in ["viewer", "editor"]:
        raise ApiError("Role must be 'viewer' or 'editor'")
    
    conn = get_sqlite_connection()
    try:
        # Verify user owns the project
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        # Find user by email
        user = conn.execute(
            "SELECT id, email FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        
        if not user:
            raise ApiError("User not found", 404)
        
        # Don't add owner as collaborator
        if user["id"] == request.user_id:
            raise ApiError("Cannot add project owner as collaborator", 400)
        
        # Add collaborator
        try:
            conn.execute(
                "INSERT INTO project_collaborators (project_id, user_id, role) VALUES (?, ?, ?)",
                (project_id, user["id"], role)
            )
            conn.commit()
            return jsonify({
                "message": "Collaborator added successfully",
                "user_id": user["id"],
                "email": user["email"],
                "role": role
            })
        except sqlite3.IntegrityError:
            raise ApiError("User is already a collaborator", 409)
    finally:
        conn.close()


@app.route("/api/projects/<int:project_id>/collaborators/<int:user_id>", methods=["DELETE"])
@require_auth
def remove_collaborator(project_id, user_id):
    """Remove a collaborator from a project."""
    conn = get_sqlite_connection()
    try:
        # Verify user owns the project
        project = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        result = conn.execute(
            "DELETE FROM project_collaborators WHERE project_id = ? AND user_id = ?",
            (project_id, user_id)
        )
        conn.commit()
        
        if result.rowcount == 0:
            raise ApiError("Collaborator not found", 404)
        
        return jsonify({"message": "Collaborator removed successfully"})
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
    """Enhanced health check with database connectivity."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gemini_configured": bool(GEMINI_KEY),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "version": API_VERSION,
    }
    
    # Check database connectivity
    try:
        conn = get_sqlite_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = "error"
        health_status["database_error"] = str(e)
        health_status["status"] = "degraded"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


@app.route("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.route("/api")
def api_info():
    return jsonify({
        "service": "Agentic System Builder API",
        "version": API_VERSION,
        "author": "John Rish Ladica – SLSU-HC SITS",
        "endpoints": {
            "health": "/health",
            "authentication": [
                "/api/auth/register",
                "/api/auth/login",
                "/api/auth/me",
                "/api/auth/update-profile",
                "/api/auth/change-password",
                "/api/auth/forgot-password",
                "/api/auth/reset-password",
            ],
            "projects": [
                "/api/projects",
                "/api/projects/<id>",
                "/api/projects/<id>/export",
                "/api/projects/<id>/collaborators",
            ],
            "generation": [
                "/api/refine-prompt",
                "/api/generate-plan",
                "/api/generate-system",
            ],
        },
        "features": [
            "JWT Authentication",
            "Password Reset",
            "Profile Management",
            "Project Collaboration",
            "Multi-Agent Code Generation",
            "Search and Filtering",
            "Rate Limiting",
        ],
    })


# ---------------------------------------------------------------------------
# Local development server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    get_sqlite_connection().close()
    app.run(host="0.0.0.0", port=5000, debug=False)
