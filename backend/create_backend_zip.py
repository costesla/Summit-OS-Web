"""
create_backend_zip.py
Creates backend_deploy_clean.zip for Azure Functions zip-deploy.
Run from the /backend directory.

SECURITY: Calls validate_before_zip.py before writing any zip.
Excluded: venv, __pycache__, .git, scratch/, test files, *.zip,
          local.settings.json, .env, config/.env, finance_mcp/.env,
          credentials/, *.pem, *.key, *.p12
"""
import os
import sys
import zipfile
import subprocess

EXCLUDE_DIRS = {
    "venv32", "venv", ".venv", "__pycache__", ".git", "scratch",
    ".python_packages", "Quarantine",
}

# These relative subdirectories are fully excluded
EXCLUDE_SUBDIR_PREFIXES = [
    "finance_mcp/",
    "credentials/",
]

EXCLUDE_FILES = {
    "local.settings.json",
    "create_backend_zip.py",
    "validate_before_zip.py",
}

EXCLUDE_EXTS = {".zip", ".pyc", ".pyo", ".pem", ".key", ".p12"}

# Any file whose basename matches these is blocked regardless of directory
BLOCKED_BASENAMES = {
    ".env",
    "local.settings.json",
    "client_secret.json",
}

# Any file whose basename STARTS with .env is blocked
def is_env_file(name: str) -> bool:
    return name.startswith(".env")

OUTPUT_ZIP = "backend_deploy_clean.zip"


def should_exclude(rel_path: str, name: str, is_dir: bool) -> bool:
    if is_dir:
        return name in EXCLUDE_DIRS
    # Check subdirectory prefixes
    rel_forward = rel_path.replace("\\", "/")
    for prefix in EXCLUDE_SUBDIR_PREFIXES:
        if rel_forward.startswith(prefix):
            return True
    # Check blocked basenames
    if name in BLOCKED_BASENAMES or name in EXCLUDE_FILES:
        return True
    # Check .env* pattern
    if is_env_file(name):
        return True
    # Check extensions
    _, ext = os.path.splitext(name)
    return ext in EXCLUDE_EXTS


def run_validator(base: str) -> None:
    """Run validate_before_zip.py against the backend directory. Abort if it fails."""
    validator = os.path.join(base, "validate_before_zip.py")
    if not os.path.exists(validator):
        print("ERROR: validate_before_zip.py not found — cannot proceed without security check.")
        sys.exit(1)
    print("[pre-zip] Running security validation...")
    result = subprocess.run([sys.executable, validator, "--dir", base], capture_output=False)
    if result.returncode != 0:
        print()
        print("ABORT: Security validation failed. No zip was created.")
        print("Fix the violations above, then re-run.")
        sys.exit(1)


def create_zip():
    base = os.path.dirname(os.path.abspath(__file__))

    # SECURITY GATE: must pass before any zip is written
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
                    # Log skipped secret files by name only (no content)
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
