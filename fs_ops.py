import os
import shutil

BASE_DIR = os.path.abspath("workspace")

def _safe_path(path: str) -> str:
    full = os.path.abspath(os.path.join(BASE_DIR, path))
    if not full.startswith(BASE_DIR):
        raise PermissionError("Unsafe path detected")
    return full

def create_dir(path: str):
    os.makedirs(_safe_path(path), exist_ok=True)

def create_file(path: str, content: str = ""):
    full = _safe_path(path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

def update_file(path: str, content: str):
    with open(_safe_path(path), "w", encoding="utf-8") as f:
        f.write(content)

def delete_path(path: str):
    full = _safe_path(path)
    if os.path.isdir(full):
        shutil.rmtree(full)
    elif os.path.isfile(full):
        os.remove(full)
