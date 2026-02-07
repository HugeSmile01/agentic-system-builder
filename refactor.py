from fs_ops import update_file

ALLOWED_ACTIONS = {"update_file"}

def apply_review(review_data: dict) -> list:
    applied = []

    for issue in review_data.get("issues", []):
        fix = issue.get("fix", {})
        if fix.get("action") not in ALLOWED_ACTIONS:
            continue

        file_path = issue["file"].replace("workspace/", "")
        update_file(file_path, fix["content"])
        applied.append(file_path)

    return applied
