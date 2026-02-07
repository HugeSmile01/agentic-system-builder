import shutil
import os

def zip_project(project: str) -> str:
    base = os.path.join("workspace", project)
    output = os.path.join("workspace", project)
    shutil.make_archive(output, "zip", base)
    return f"{output}.zip"
