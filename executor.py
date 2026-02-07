from fs_ops import create_dir, create_file, update_file

def scaffold_flask(project: str):
    create_dir(project)
    create_file(
        f"{project}/app.py",
        """from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello from generated Flask app"
"""
    )
    create_file(f"{project}/requirements.txt", "Flask\n")

def execute(plan: dict):
    for step in plan.get("steps", []):
        action = step["action"]

        if action == "create_dir":
            create_dir(step["path"])
        elif action == "create_file":
            create_file(step["path"], step.get("content", ""))
        elif action == "update_file":
            update_file(step["path"], step["content"])
        elif action == "scaffold_flask":
            scaffold_flask(plan["project"])
        else:
            raise ValueError(f"Unsupported action: {action}")
