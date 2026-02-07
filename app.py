from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

from planner import plan
from executor import execute
from reviewer import review
from refactor import apply_review
from zip_ops import zip_project

app = Flask(__name__, static_folder="web", static_url_path="/")
CORS(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

API_KEY = os.getenv("API_KEY", "devkey")

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/agent", methods=["POST"])
@limiter.limit("10 per minute")
def agent():
    if request.headers.get("Authorization") != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    if os.getenv("VERCEL"):
        return jsonify({"error": "File operations disabled on server"}), 403

    user_prompt = request.json["prompt"]
    plan_data = plan(user_prompt)
    execute(plan_data)

    return jsonify({"status": "built", "project": plan_data["project"]})

@app.route("/review/<project>", methods=["POST"])
def review_code(project):
    return jsonify(review(project))

@app.route("/refactor/<project>", methods=["POST"])
def refactor_code(project):
    applied = apply_review(request.json)
    return jsonify({"refactored_files": applied})

@app.route("/export/<project>")
def export_project(project):
    zip_path = zip_project(project)
    return send_file(zip_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
