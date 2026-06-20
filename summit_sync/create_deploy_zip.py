"""
create_deploy_zip.py — summit_sync deploy package builder.
SECURITY: Excludes .env, local.settings.json, credentials/ before zipping.
Run from the /summit_sync directory.
"""
import os
import sys
import zipfile
import subprocess

EXCLUDE_DIRS = {
    "venv", ".venv", "__pycache__", ".git", ".vscode",
    "scripts", "node_modules", "dashboard",
}

BLOCKED_BASENAMES = {
    ".env",
    "local.settings.json",
    "client_secret.json",
}

EXCLUDE_FILES = {
    "local.settings.json",
    "create_deploy_zip.py",
    "deploy.zip",
    "validate_before_zip.py",
}

# Subdirectory prefixes that are fully excluded
EXCLUDE_SUBDIR_PREFIXES = ["credentials/"]

EXCLUDE_EXTS = {".zip", ".pyc", ".pyo", ".pem", ".key", ".p12"}

OUTPUT_ZIP = "summit_sync_deploy_pkg.zip"


def is_env_file(name: str) -> bool:
    return name.startswith(".env")


def should_exclude(rel_path: str, name: str, is_dir: bool) -> bool:
    if is_dir:
        return name in EXCLUDE_DIRS
    rel_forward = rel_path.replace("\\", "/")
    for prefix in EXCLUDE_SUBDIR_PREFIXES:
        if rel_forward.startswith(prefix):
            return True
    if name in BLOCKED_BASENAMES or name in EXCLUDE_FILES:
        return True
    if is_env_file(name):
        return True
    _, ext = os.path.splitext(name)
    return ext in EXCLUDE_EXTS


def run_validator(base: str) -> None:
    """Run backend/validate_before_zip.py as the security gate."""
    validator = os.path.join(base, "..", "backend", "validate_before_zip.py")
    validator = os.path.normpath(validator)
    if not os.path.exists(validator):
        print("ERROR: validate_before_zip.py not found — cannot proceed without security check.")
        sys.exit(1)
    print("[pre-zip] Running security validation...")
    result = subprocess.run([sys.executable, validator, "--dir", base], capture_output=False)
    if result.returncode != 0:
        print("\nABORT: Security validation failed. No zip was created.")
        sys.exit(1)


def create_zip():
    base = os.path.dirname(os.path.abspath(__file__))

    # SECURITY GATE
    run_validator(base)

    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)
        print(f"Removed old {OUTPUT_ZIP}")

    written = 0
    skipped_secrets = []

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(base):
            rel_root = os.path.relpath(root, base).replace("\\", "/")
            dirs[:] = [d for d in dirs if not should_exclude(rel_root, d, is_dir=True)]

            for fname in files:
                rel_path = os.path.join(rel_root, fname).replace("\\", "/").lstrip("./")
                if should_exclude(rel_path, fname, is_dir=False):
                    if is_env_file(fname) or fname in BLOCKED_BASENAMES:
                        skipped_secrets.append(rel_path)
                    continue
                abs_path = os.path.join(root, fname)
                arc_path = os.path.relpath(abs_path, base)
                zf.write(abs_path, arc_path)
                written += 1

    size_mb = os.path.getsize(OUTPUT_ZIP) / (1024 * 1024)
    print(f"Created {OUTPUT_ZIP} — {written} files, {size_mb:.1f} MB")
    if skipped_secrets:
        print(f"  Excluded {len(skipped_secrets)} secret file(s): {', '.join(skipped_secrets)}")


if __name__ == "__main__":
    create_zip()
