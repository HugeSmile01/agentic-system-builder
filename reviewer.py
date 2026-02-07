import os
import json
import google.generativeai as genai

SYSTEM_PROMPT = """
You are a code review agent.

You receive source files.
Identify issues and propose fixes.

Respond ONLY with valid JSON:

{
  "issues": [
    {
      "file": "workspace/project/file.py",
      "problem": "description",
      "fix": {
        "action": "update_file",
        "content": "FULL corrected file content"
      }
    }
  ]
}
"""

def review(project: str) -> dict:
    model = genai.GenerativeModel("gemini-1.5-flash")
    files_blob = []

    base = os.path.join("workspace", project)
    for root, _, files in os.walk(base):
        for file in files:
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                files_blob.append(f"FILE: {path}\n{f.read()}")

    response = model.generate_content(
        SYSTEM_PROMPT + "\n\n".join(files_blob)
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]

    return json.loads(text)
