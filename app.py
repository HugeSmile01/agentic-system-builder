import io
import json
import logging
import os
import pathlib
import secrets
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash
import jwt

import google.generativeai as genai

# Initialize Flask app
app = Flask(__name__, static_folder="static")
app.config.update(
    JSON_SORT_KEYS=False,
    JSONIFY_PRETTYPRINT_REGULAR=False,
    SECRET_KEY=os.getenv("SECRET_KEY", secrets.token_hex(32))
)

CORS(app, resources={r"/*": {"origins": "*"}})
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per hour"])
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", app.config["SECRET_KEY"])
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Use /tmp for writable paths on Vercel (read-only filesystem)
_is_vercel = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
_tmp_base = "/tmp" if _is_vercel else "."
DATA_ROOT = os.getenv("DATA_ROOT", os.path.join(_tmp_base, "generated"))
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(_tmp_base, "data", "agentic.db"))

FS_BASE_DIR = pathlib.Path(DATA_ROOT).resolve()
try:
    FS_BASE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    FS_BASE_DIR = pathlib.Path("/tmp/generated").resolve()
    FS_BASE_DIR.mkdir(parents=True, exist_ok=True)

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

_supabase_client = None


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

class ApiError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def json_error(message, status=400, detail=None):
    payload = {"error": message, "timestamp": datetime.now(timezone.utc).isoformat()}
    if detail:
        payload["detail"] = detail
    return jsonify(payload), status


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
    try:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        sqlite_path = pathlib.Path("/tmp/data/agentic.db")
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    
    # Users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT
        )
    """)
    
    # Projects table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
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
        )
    """)
    
    # Generated files table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS generated_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            file_type TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    """)
    
    # Project iterations table (for refinement tracking)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_iterations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            iteration_number INTEGER NOT NULL,
            refined_prompt TEXT NOT NULL,
            plan TEXT,
            review_notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    """)
    
    conn.commit()
    return conn


# ============================================================================
# JWT AUTHENTICATION
# ============================================================================

def generate_token(user_id, email):
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ApiError("Token has expired", 401)
    except jwt.InvalidTokenError:
        raise ApiError("Invalid token", 401)


def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise ApiError("Missing or invalid authorization header", 401)
        
        token = auth_header.replace("Bearer ", "", 1).strip()
        try:
            payload = verify_token(token)
            request.user_id = payload["user_id"]
            request.user_email = payload["email"]
            return f(*args, **kwargs)
        except ApiError:
            raise
    return decorated_function


# ============================================================================
# LLM FUNCTIONS (Multi-Model Support)
# ============================================================================

def call_llm(prompt, model="gemini-1.5-flash", temperature=0.7, max_tokens=4000):
    """
    Call LLM with support for Gemini (free tier with high limits)
    """
    if not prompt:
        raise ApiError("Prompt is required for LLM call")
    
    try:
        if model.startswith("gemini") and GEMINI_KEY:
            model_obj = genai.GenerativeModel(
                model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
            )
            response = model_obj.generate_content(prompt)
            return response.text
        else:
            raise ApiError("No LLM model configured. Please set GEMINI_KEY.")
    except Exception as exc:
        logger.exception("LLM call failed")
        raise ApiError(f"LLM error: {str(exc)}", 500)


# ============================================================================
# AGENTIC SYSTEM FUNCTIONS
# ============================================================================

def refine_user_prompt(user_input, context=None):
    """
    PLANNER AGENT: Refines user input into a detailed, actionable prompt
    """
    prompt = f"""You are an expert system architect and prompt engineer. Refine the following user request into a comprehensive, detailed specification for building a software system.

User Request:
{user_input}

{f"Additional Context: {context}" if context else ""}

Provide a refined specification that includes:
1. **Project Goal**: Clear, specific objective
2. **Target Audience**: Who will use this system and their technical level
3. **Core Features**: Detailed list of must-have features (minimum 5)
4. **Technical Requirements**: 
   - Programming language and framework
   - Database requirements
   - API integrations needed
   - Authentication/security needs
5. **UI/UX Requirements**: Design style, responsiveness, accessibility
6. **Constraints**: Hosting platform (Vercel), performance, scalability
7. **Success Criteria**: How to measure if the system works correctly

Be specific, technical, and comprehensive. Output as structured JSON with keys: goal, audience, features (array), technical_requirements (object), ui_requirements (object), constraints (array), success_criteria (array).
"""
    
    response = call_llm(prompt, temperature=0.3)
    
    # Try to parse JSON, fallback to structured text
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Extract information even if not perfect JSON
        return {
            "goal": user_input,
            "raw_refinement": response,
            "features": [],
            "technical_requirements": {},
            "ui_requirements": {},
            "constraints": ["Deploy to Vercel", "Use free-tier services"],
            "success_criteria": []
        }


def create_system_plan(refined_spec):
    """
    PLANNER AGENT: Creates detailed implementation plan
    """
    spec_str = json.dumps(refined_spec, indent=2)
    
    prompt = f"""You are a senior software architect. Create a detailed implementation plan for this system:

{spec_str}

Provide a comprehensive plan that includes:

1. **Architecture Overview**: System architecture pattern (e.g., MVC, microservices, serverless)
2. **File Structure**: Complete directory and file structure
3. **Implementation Steps**: Ordered list of development steps (minimum 8 steps)
4. **Technology Stack**: Specific technologies, libraries, and versions
5. **Data Models**: Database schema and relationships
6. **API Endpoints**: RESTful endpoints with methods and purposes
7. **Security Measures**: Authentication, authorization, data protection
8. **Deployment Strategy**: How to deploy to Vercel
9. **Testing Strategy**: Unit tests, integration tests, E2E tests
10. **Risk Assessment**: Potential challenges and mitigation strategies

Output as detailed JSON with these exact keys.
"""
    
    response = call_llm(prompt, temperature=0.2, max_tokens=6000)
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {
            "architecture": "Modern web application",
            "file_structure": [],
            "implementation_steps": [],
            "technology_stack": {},
            "raw_plan": response
        }


def generate_project_files(plan, refined_spec):
    """
    EXECUTOR AGENT: Generates actual code files based on plan
    """
    files = {}
    
    # Generate backend file (Python/Flask for Vercel)
    backend_prompt = f"""Generate a complete, production-ready Flask backend (app.py) for this system:

Plan: {json.dumps(plan, indent=2)}
Spec: {json.dumps(refined_spec, indent=2)}

Requirements:
- Use Flask with proper error handling
- Include JWT authentication
- Integrate with Supabase for database
- Use environment variables for secrets
- Include comprehensive API endpoints
- Add input validation
- Include CORS configuration
- Add rate limiting
- Production-ready code with comments

Output ONLY the complete Python code, no explanations.
"""
    
    backend_code = call_llm(backend_prompt, max_tokens=8000)
    files["app.py"] = clean_code_output(backend_code)
    
    # Generate frontend file (React/HTML)
    frontend_prompt = f"""Generate a complete, production-ready mobile-first web interface for this system:

Plan: {json.dumps(plan, indent=2)}
Spec: {json.dumps(refined_spec, indent=2)}

Requirements:
- Single HTML file with embedded CSS and JavaScript
- Mobile-first responsive design optimized for iPhone
- Modern, beautiful UI with smooth animations
- Integration with the Flask backend API
- JWT authentication flow (login/register)
- All core features implemented
- Error handling and loading states
- Accessibility features
- Production-ready code

Output ONLY the complete HTML code, no explanations.
"""
    
    frontend_code = call_llm(frontend_prompt, max_tokens=8000)
    files["index.html"] = clean_code_output(frontend_code)
    
    # Generate requirements.txt
    requirements = """Flask==3.0.3
Flask-CORS==5.0.0
flask-limiter>=2.9,<3.0
PyJWT==2.8.0
google-generativeai==0.8.3
supabase==2.7.5
python-dotenv==1.0.0
"""
    files["requirements.txt"] = requirements
    
    # Generate vercel.json
    vercel_config = {
        "version": 2,
        "builds": [{"src": "app.py", "use": "@vercel/python"}],
        "routes": [{"src": "/(.*)", "dest": "app.py"}],
        "env": {
            "GEMINI_KEY": "@gemini_key",
            "SUPABASE_URL": "@supabase_url",
            "SUPABASE_KEY": "@supabase_key",
            "JWT_SECRET": "@jwt_secret"
        }
    }
    files["vercel.json"] = json.dumps(vercel_config, indent=2)
    
    # Generate README.md
    readme = f"""# {refined_spec.get('goal', 'Generated System')}

## Overview
{refined_spec.get('goal', 'AI-generated system')}

## Features
{chr(10).join(f"- {feature}" for feature in refined_spec.get('features', []))}

## Technology Stack
- **Backend**: Flask (Python)
- **Frontend**: HTML/CSS/JavaScript
- **Database**: Supabase
- **AI**: Google Gemini
- **Authentication**: JWT
- **Deployment**: Vercel

## Setup Instructions

### 1. Environment Variables
Create a `.env` file:
```
GEMINI_KEY=your_gemini_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
JWT_SECRET=your_secret_key
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Locally
```bash
python app.py
```

### 4. Deploy to Vercel
```bash
vercel --prod
```

## API Endpoints
See the API documentation in the code comments.

## Generated by
Agentic System Builder - AI-powered autonomous system generation
"""
    files["README.md"] = readme
    
    # Generate .env.example
    env_example = """GEMINI_KEY=your_gemini_api_key_here
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
JWT_SECRET=your_random_secret_key_min_32_chars
"""
    files[".env.example"] = env_example
    
    return files


def review_generated_code(files, plan, refined_spec):
    """
    REVIEWER AGENT: Reviews generated code for quality, security, and completeness
    """
    files_summary = "\n".join([f"- {name} ({len(content)} chars)" for name, content in files.items()])
    
    prompt = f"""You are a senior code reviewer. Review this generated system for quality, security, and completeness.

Generated Files:
{files_summary}

Original Plan:
{json.dumps(plan, indent=2)[:1000]}...

Review Criteria:
1. **Security**: Authentication, input validation, SQL injection prevention, XSS protection
2. **Code Quality**: Readability, modularity, error handling, comments
3. **Completeness**: All features implemented, all files present
4. **Best Practices**: Industry standards, design patterns, performance
5. **Deployment Readiness**: Vercel compatibility, environment variables, dependencies

Provide review as JSON:
{{
    "overall_score": 0-100,
    "security_issues": ["issue1", "issue2"],
    "quality_issues": ["issue1"],
    "missing_features": ["feature1"],
    "recommendations": ["rec1", "rec2"],
    "deployment_ready": true/false,
    "summary": "Brief summary"
}}
"""
    
    response = call_llm(prompt, temperature=0.3)
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {
            "overall_score": 75,
            "security_issues": [],
            "quality_issues": [],
            "missing_features": [],
            "recommendations": ["Review code manually"],
            "deployment_ready": True,
            "summary": response[:500],
            "raw_review": response
        }


def refactor_code(files, review_feedback):
    """
    REFACTORER AGENT: Applies improvements based on review feedback
    """
    if review_feedback.get("overall_score", 100) >= 90:
        return files, "Code quality excellent, no refactoring needed"
    
    refactored_files = {}
    issues = review_feedback.get("security_issues", []) + review_feedback.get("quality_issues", [])
    
    if not issues:
        return files, "No critical issues to refactor"
    
    # Refactor critical files (app.py, index.html)
    for filename in ["app.py", "index.html"]:
        if filename not in files:
            continue
            
        prompt = f"""Refactor this code to fix the following issues:

Issues to fix:
{chr(10).join(f"- {issue}" for issue in issues[:5])}

Original code:
```
{files[filename][:4000]}
```

Provide the complete refactored code with fixes applied. Output ONLY code, no explanations.
"""
        
        try:
            refactored_code = call_llm(prompt, max_tokens=8000)
            refactored_files[filename] = clean_code_output(refactored_code)
        except Exception as e:
            logger.error(f"Refactoring failed for {filename}: {e}")
            refactored_files[filename] = files[filename]
    
    # Keep other files unchanged
    for filename, content in files.items():
        if filename not in refactored_files:
            refactored_files[filename] = content
    
    return refactored_files, f"Refactored {len(refactored_files)} files"


def clean_code_output(code_text):
    """Remove markdown code fences and clean up LLM output"""
    code_text = code_text.strip()
    
    # Remove markdown code fences
    if code_text.startswith("```"):
        lines = code_text.split("\n")
        # Remove first line (```python or ```html etc)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code_text = "\n".join(lines)
    
    return code_text.strip()


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({
        "error": error.message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), error.status_code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logger.exception("Unexpected error")
    return json_error("Internal server error", status=500, detail=str(error))


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

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
        # Check if user exists
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise ApiError("User already exists", 409)
        
        # Create user
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, full_name) VALUES (?, ?, ?)",
            (email, password_hash, full_name)
        )
        conn.commit()
        
        user_id = cursor.lastrowid
        token = generate_token(user_id, email)
        
        return jsonify({
            "token": token,
            "user": {
                "id": user_id,
                "email": email,
                "full_name": full_name
            }
        })
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
            (email,)
        ).fetchone()
        
        if not user or not check_password_hash(user["password_hash"], password):
            raise ApiError("Invalid credentials", 401)
        
        # Update last login
        conn.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],)
        )
        conn.commit()
        
        token = generate_token(user["id"], user["email"])
        
        return jsonify({
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"]
            }
        })
    finally:
        conn.close()


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def get_current_user():
    conn = get_sqlite_connection()
    try:
        user = conn.execute(
            "SELECT id, email, full_name, created_at FROM users WHERE id = ?",
            (request.user_id,)
        ).fetchone()
        
        if not user:
            raise ApiError("User not found", 404)
        
        return jsonify(dict(user))
    finally:
        conn.close()


# ============================================================================
# PROJECT ENDPOINTS
# ============================================================================

@app.route("/api/projects", methods=["GET"])
@require_auth
def list_projects():
    conn = get_sqlite_connection()
    try:
        projects = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
            (request.user_id,)
        ).fetchall()
        
        return jsonify({"projects": [dict(p) for p in projects]})
    finally:
        conn.close()


@app.route("/api/projects", methods=["POST"])
@limiter.limit("10 per hour")
@require_auth
def create_project():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    goal = data.get("goal", "").strip()
    
    if not name or not goal:
        raise ApiError("Project name and goal are required")
    
    conn = get_sqlite_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO projects (user_id, name, description, goal, audience, ui_style, constraints, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')""",
            (request.user_id, name, description, goal,
             data.get("audience", ""), data.get("ui_style", ""), data.get("constraints", ""))
        )
        conn.commit()
        
        return jsonify({
            "id": cursor.lastrowid,
            "name": name,
            "status": "draft"
        })
    finally:
        conn.close()


@app.route("/api/projects/<int:project_id>", methods=["GET"])
@require_auth
def get_project(project_id):
    conn = get_sqlite_connection()
    try:
        project = conn.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        # Get iterations
        iterations = conn.execute(
            "SELECT * FROM project_iterations WHERE project_id = ? ORDER BY iteration_number DESC",
            (project_id,)
        ).fetchall()
        
        # Get files
        files = conn.execute(
            "SELECT * FROM generated_files WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        
        return jsonify({
            "project": dict(project),
            "iterations": [dict(i) for i in iterations],
            "files": [dict(f) for f in files]
        })
    finally:
        conn.close()


# ============================================================================
# AGENTIC SYSTEM ENDPOINTS
# ============================================================================

@app.route("/api/refine-prompt", methods=["POST"])
@limiter.limit("20 per hour")
@require_auth
def refine_prompt_endpoint():
    """Step 1: Refine user input into detailed specification"""
    data = request.get_json() or {}
    user_input = data.get("prompt", "").strip()
    project_id = data.get("project_id")
    
    if not user_input:
        raise ApiError("Prompt is required")
    
    try:
        refined = refine_user_prompt(user_input, data.get("context"))
        
        # Save iteration if project_id provided
        if project_id:
            conn = get_sqlite_connection()
            try:
                # Verify project ownership
                project = conn.execute(
                    "SELECT id FROM projects WHERE id = ? AND user_id = ?",
                    (project_id, request.user_id)
                ).fetchone()
                
                if project:
                    # Get iteration number
                    last_iteration = conn.execute(
                        "SELECT MAX(iteration_number) as max_iter FROM project_iterations WHERE project_id = ?",
                        (project_id,)
                    ).fetchone()
                    
                    next_iteration = (last_iteration["max_iter"] or 0) + 1
                    
                    conn.execute(
                        """INSERT INTO project_iterations (project_id, iteration_number, refined_prompt)
                           VALUES (?, ?, ?)""",
                        (project_id, next_iteration, json.dumps(refined))
                    )
                    conn.commit()
            finally:
                conn.close()
        
        return jsonify({
            "refined": refined,
            "original": user_input
        })
    except Exception as e:
        logger.exception("Prompt refinement failed")
        raise ApiError(f"Refinement failed: {str(e)}", 500)


@app.route("/api/generate-plan", methods=["POST"])
@limiter.limit("15 per hour")
@require_auth
def generate_plan_endpoint():
    """Step 2: Generate implementation plan"""
    data = request.get_json() or {}
    refined_spec = data.get("refined_spec")
    project_id = data.get("project_id")
    
    if not refined_spec:
        raise ApiError("Refined specification is required")
    
    try:
        plan = create_system_plan(refined_spec)
        
        # Update iteration with plan
        if project_id:
            conn = get_sqlite_connection()
            try:
                conn.execute(
                    """UPDATE project_iterations 
                       SET plan = ?
                       WHERE project_id = ? 
                       AND iteration_number = (SELECT MAX(iteration_number) FROM project_iterations WHERE project_id = ?)""",
                    (json.dumps(plan), project_id, project_id)
                )
                conn.commit()
            finally:
                conn.close()
        
        return jsonify({"plan": plan})
    except Exception as e:
        logger.exception("Plan generation failed")
        raise ApiError(f"Plan generation failed: {str(e)}", 500)


@app.route("/api/generate-system", methods=["POST"])
@limiter.limit("5 per hour")
@require_auth
def generate_system_endpoint():
    """Step 3: Generate complete system with code"""
    data = request.get_json() or {}
    plan = data.get("plan")
    refined_spec = data.get("refined_spec")
    project_id = data.get("project_id")
    
    if not plan or not refined_spec:
        raise ApiError("Plan and refined specification are required")
    
    try:
        # Generate files
        logger.info("Generating project files...")
        files = generate_project_files(plan, refined_spec)
        
        # Review code
        logger.info("Reviewing generated code...")
        review = review_generated_code(files, plan, refined_spec)
        
        # Refactor if needed
        logger.info("Applying refactoring...")
        final_files, refactor_msg = refactor_code(files, review)
        
        # Save to database
        if project_id:
            conn = get_sqlite_connection()
            try:
                # Delete old files
                conn.execute("DELETE FROM generated_files WHERE project_id = ?", (project_id,))
                
                # Save new files
                for filename, content in final_files.items():
                    file_type = filename.split(".")[-1] if "." in filename else "txt"
                    conn.execute(
                        """INSERT INTO generated_files (project_id, filename, content, file_type)
                           VALUES (?, ?, ?, ?)""",
                        (project_id, filename, content, file_type)
                    )
                
                # Update iteration with review
                conn.execute(
                    """UPDATE project_iterations 
                       SET review_notes = ?
                       WHERE project_id = ? 
                       AND iteration_number = (SELECT MAX(iteration_number) FROM project_iterations WHERE project_id = ?)""",
                    (json.dumps(review), project_id, project_id)
                )
                
                # Update project status
                conn.execute(
                    "UPDATE projects SET status = 'generated', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (project_id,)
                )
                
                conn.commit()
            finally:
                conn.close()
        
        return jsonify({
            "files": {name: len(content) for name, content in final_files.items()},
            "review": review,
            "refactor_message": refactor_msg,
            "total_files": len(final_files)
        })
    except Exception as e:
        logger.exception("System generation failed")
        raise ApiError(f"Generation failed: {str(e)}", 500)


@app.route("/api/projects/<int:project_id>/export", methods=["GET"])
@limiter.limit("10 per hour")
@require_auth
def export_project(project_id):
    """Export project as ZIP file"""
    conn = get_sqlite_connection()
    try:
        # Verify ownership
        project = conn.execute(
            "SELECT name FROM projects WHERE id = ? AND user_id = ?",
            (project_id, request.user_id)
        ).fetchone()
        
        if not project:
            raise ApiError("Project not found", 404)
        
        # Get all files
        files = conn.execute(
            "SELECT filename, content FROM generated_files WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        
        if not files:
            raise ApiError("No files to export", 404)
        
        # Create ZIP
        buffer = io.BytesIO()
        project_name = project["name"].replace(" ", "_")
        
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                zipf.writestr(f"{project_name}/{file['filename']}", file["content"])
        
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{project_name}.zip"
        )
    finally:
        conn.close()


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gemini_configured": bool(GEMINI_KEY),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "version": "2.0.0"
    })


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api")
def api_info():
    return jsonify({
        "service": "Agentic System Builder API",
        "version": "2.0.0",
        "author": "John Rish Ladica",
        "endpoints": [
            "/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/me",
            "/api/projects",
            "/api/refine-prompt",
            "/api/generate-plan",
            "/api/generate-system",
            "/api/projects/<id>/export"
        ]
    })


if __name__ == "__main__":
    # Initialize database
    get_sqlite_connection().close()
    app.run(host="0.0.0.0", port=5000, debug=False)
