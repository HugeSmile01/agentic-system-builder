"""Multi-agent pipeline: Planner → Executor → Reviewer → Refactorer."""

import json
import logging

from lib.llm import call_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_code_output(code_text):
    """Remove markdown code fences from LLM output."""
    code_text = code_text.strip()
    if code_text.startswith("```"):
        lines = code_text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code_text = "\n".join(lines)
    return code_text.strip()


def _parse_json_response(text, fallback):
    """Try to parse *text* as JSON, returning *fallback* on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return fallback


# ---------------------------------------------------------------------------
# Planner Agent
# ---------------------------------------------------------------------------

def refine_user_prompt(user_input, context=None):
    """Refine raw user input into a structured specification."""
    prompt = (
        "You are an expert system architect and prompt engineer. "
        "Refine the following user request into a comprehensive, detailed "
        "specification for building a software system.\n\n"
        f"User Request:\n{user_input}\n\n"
        + (f"Additional Context: {context}\n\n" if context else "")
        + "Provide a refined specification that includes:\n"
        "1. **Project Goal**: Clear, specific objective\n"
        "2. **Target Audience**: Who will use this system\n"
        "3. **Core Features**: Detailed list (minimum 5)\n"
        "4. **Technical Requirements**: Language, framework, database, auth\n"
        "5. **UI/UX Requirements**: Design style, responsiveness\n"
        "6. **Constraints**: Hosting (Vercel), performance, scalability\n"
        "7. **Success Criteria**: Measurable outcomes\n\n"
        "Output as structured JSON with keys: goal, audience, features (array), "
        "technical_requirements (object), ui_requirements (object), "
        "constraints (array), success_criteria (array)."
    )
    response = call_llm(prompt, temperature=0.3)
    return _parse_json_response(response, {
        "goal": user_input,
        "raw_refinement": response,
        "features": [],
        "technical_requirements": {},
        "ui_requirements": {},
        "constraints": ["Deploy to Vercel", "Use free-tier services"],
        "success_criteria": [],
    })


def create_system_plan(refined_spec):
    """Create a detailed implementation plan from a refined specification."""
    spec_str = json.dumps(refined_spec, indent=2)
    prompt = (
        "You are a senior software architect. Create a detailed implementation "
        f"plan for this system:\n\n{spec_str}\n\n"
        "Include:\n"
        "1. Architecture Overview\n"
        "2. File Structure\n"
        "3. Implementation Steps (minimum 8)\n"
        "4. Technology Stack\n"
        "5. Data Models\n"
        "6. API Endpoints\n"
        "7. Security Measures\n"
        "8. Deployment Strategy (Vercel)\n"
        "9. Testing Strategy\n"
        "10. Risk Assessment\n\n"
        "Output as detailed JSON."
    )
    response = call_llm(prompt, temperature=0.2, max_tokens=6000)
    return _parse_json_response(response, {
        "architecture": "Modern web application",
        "file_structure": [],
        "implementation_steps": [],
        "technology_stack": {},
        "raw_plan": response,
    })


# ---------------------------------------------------------------------------
# Executor Agent
# ---------------------------------------------------------------------------

def generate_project_files(plan, refined_spec):
    """Generate all code files for a project."""
    files = {}

    # Backend
    backend_prompt = (
        "Generate a complete, production-ready Flask backend (app.py):\n\n"
        f"Plan: {json.dumps(plan, indent=2)}\nSpec: {json.dumps(refined_spec, indent=2)}\n\n"
        "Requirements: Flask, JWT auth, Supabase, env vars, CORS, rate limiting.\n"
        "Output ONLY the complete Python code."
    )
    files["app.py"] = _clean_code_output(call_llm(backend_prompt, max_tokens=8000))

    # Frontend
    frontend_prompt = (
        "Generate a complete, mobile-first web interface:\n\n"
        f"Plan: {json.dumps(plan, indent=2)}\nSpec: {json.dumps(refined_spec, indent=2)}\n\n"
        "Requirements: Single HTML, responsive, dark theme, API integration, JWT auth.\n"
        "Output ONLY the complete HTML code."
    )
    files["index.html"] = _clean_code_output(call_llm(frontend_prompt, max_tokens=8000))

    # Supporting files
    files["requirements.txt"] = (
        "Flask==3.0.3\nFlask-CORS==5.0.0\nflask-limiter>=2.9,<3.0\n"
        "PyJWT==2.8.0\ngoogle-generativeai==0.8.3\nsupabase>=2.11.0,<3.0.0\n"
        "python-dotenv==1.0.0\n"
    )

    files["vercel.json"] = json.dumps(
        {
            "version": 2,
            "builds": [{"src": "app.py", "use": "@vercel/python"}],
            "routes": [{"src": "/(.*)", "dest": "app.py"}],
            "env": {
                "GEMINI_KEY": "@gemini_key",
                "SUPABASE_URL": "@supabase_url",
                "SUPABASE_KEY": "@supabase_key",
                "JWT_SECRET": "@jwt_secret",
            },
        },
        indent=2,
    )

    goal = refined_spec.get("goal", "Generated System")
    features = refined_spec.get("features", [])
    files["README.md"] = (
        f"# {goal}\n\n## Features\n"
        + "\n".join(f"- {f}" for f in features)
        + "\n\n## Quick Start\n```bash\npip install -r requirements.txt\npython app.py\n```\n\n"
        "## Deploy\n```bash\nvercel --prod\n```\n\n"
        "*Generated by Agentic System Builder*\n"
    )

    files[".env.example"] = (
        "GEMINI_KEY=your_gemini_api_key_here\n"
        "SUPABASE_URL=your_supabase_project_url\n"
        "SUPABASE_KEY=your_supabase_anon_key\n"
        "JWT_SECRET=your_random_secret_key_min_32_chars\n"
    )

    return files


# ---------------------------------------------------------------------------
# Reviewer Agent
# ---------------------------------------------------------------------------

def review_generated_code(files, plan, refined_spec):
    """Review generated code for quality and security."""
    summary = "\n".join(f"- {n} ({len(c)} chars)" for n, c in files.items())
    prompt = (
        "You are a senior code reviewer. Review this system:\n\n"
        f"Files:\n{summary}\n\nPlan:\n{json.dumps(plan, indent=2)[:1000]}...\n\n"
        "Review for: security, quality, completeness, best practices, Vercel readiness.\n"
        "Output JSON: overall_score (0-100), security_issues, quality_issues, "
        "missing_features, recommendations, deployment_ready, summary."
    )
    response = call_llm(prompt, temperature=0.3)
    return _parse_json_response(response, {
        "overall_score": 75,
        "security_issues": [],
        "quality_issues": [],
        "missing_features": [],
        "recommendations": ["Review code manually"],
        "deployment_ready": True,
        "summary": response[:500],
        "raw_review": response,
    })


# ---------------------------------------------------------------------------
# Refactorer Agent
# ---------------------------------------------------------------------------

def refactor_code(files, review_feedback):
    """Apply improvements based on review feedback."""
    if review_feedback.get("overall_score", 100) >= 90:
        return files, "Code quality excellent, no refactoring needed"

    issues = review_feedback.get("security_issues", []) + review_feedback.get(
        "quality_issues", []
    )
    if not issues:
        return files, "No critical issues to refactor"

    refactored = {}
    for filename in ["app.py", "index.html"]:
        if filename not in files:
            continue
        prompt = (
            "Refactor this code to fix:\n"
            + "\n".join(f"- {i}" for i in issues[:5])
            + f"\n\nCode:\n```\n{files[filename][:4000]}\n```\n"
            "Output ONLY the complete refactored code."
        )
        try:
            refactored[filename] = _clean_code_output(
                call_llm(prompt, max_tokens=8000)
            )
        except Exception as exc:
            logger.error("Refactoring failed for %s: %s", filename, exc)
            refactored[filename] = files[filename]

    for name, content in files.items():
        if name not in refactored:
            refactored[name] = content

    return refactored, f"Refactored {len(refactored)} files"
