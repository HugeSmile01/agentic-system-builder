import json
import google.generativeai as genai

SYSTEM_PROMPT = """
You are a planning agent.

Convert the user's request into an ordered execution plan.

Allowed actions:
- create_dir
- create_file
- update_file
- scaffold_flask

Respond ONLY with valid JSON:

{
  "project": "project_name",
  "steps": [
    {
      "action": "create_dir",
      "path": "relative/path",
      "content": "optional"
    }
  ]
}

No markdown. No explanations.
"""

def plan(prompt: str) -> dict:
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(SYSTEM_PROMPT + "\nUser: " + prompt)

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]

    return json.loads(text)
