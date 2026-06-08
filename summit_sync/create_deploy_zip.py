import os
import zipfile

EXCLUDE_DIRS  = {"venv", ".venv", "__pycache__", ".git", ".vscode", "scripts", "local_watcher.py", "node_modules", "dashboard"}
EXCLUDE_FILES = {"local.settings.json", "create_deploy_zip.py", "deploy.zip"}
EXCLUDE_EXTS  = {".zip", ".pyc", ".pyo"}

OUTPUT_ZIP = "summit_sync_deploy_pkg.zip"

def should_exclude(path, name, is_dir):
    if is_dir:
        return name in EXCLUDE_DIRS
    if name in EXCLUDE_FILES:
        return True
    _, ext = os.path.splitext(name)
    return ext in EXCLUDE_EXTS

def create_zip():
    base = os.path.dirname(os.path.abspath(__file__))
    written = 0

    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)
        print(f"Removed old {OUTPUT_ZIP}")

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not should_exclude(root, d, is_dir=True)]

            for fname in files:
                if should_exclude(root, fname, is_dir=False):
                    continue
                abs_path = os.path.join(root, fname)
                arc_path = os.path.relpath(abs_path, base)
                zf.write(abs_path, arc_path)
                written += 1

    size_mb = os.path.getsize(OUTPUT_ZIP) / (1024 * 1024)
    print(f"Created {OUTPUT_ZIP} — {written} files, {size_mb:.1f} MB")

if __name__ == "__main__":
    create_zip()
