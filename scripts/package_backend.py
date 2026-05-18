"""
scripts/package_backend.py
---------------------------
Creates a clean, minimal deployment zip for the Azure Function backend.

Run from the Summit-OS-Web-master directory:
    python scripts/package_backend.py

Output: backend_deploy_clean.zip  (safe to push via az functionapp deploy)

EXCLUDED (mirrors .funcignore):
  - local.settings.json / *.env / *-settings.json
  - __pycache__, *.pyc
  - test_*.py, tests/, scratch/
  - *.zip, *.log, *.ndjson
  - venv32/, .venv/, .python_packages/
  - scripts/, *.md
"""

import os
import zipfile
import fnmatch
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent / "backend"
OUTPUT_ZIP = Path(__file__).parent.parent / "backend_deploy_clean.zip"

# Patterns that should NEVER be packaged (relative to backend root)
EXCLUDE_PATTERNS = [
    "local.settings.json",
    ".env",
    ".env.*",
    "*.env.local",
    "*.env.production",
    "*.env.development",
    "*-settings.json",
    "*_settings.json",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "test_*.py",
    "*_test.py",
    "tests/",
    "diagnostic_*.py",
    "verify_*.py",
    "check_*.py",
    "scratch/",
    "*.zip",
    "*.log",
    "*.ndjson",
    "*.txt",          # run logs etc.
    "*.md",
    "venv32/",
    ".venv/",
    ".python_packages/",
    "scripts/",
    "deploy*.ps1",
    ".git/",
    ".github/",
    ".vscode/",
    ".pytest_cache/",
    "Quarantine/",
]


def _is_excluded(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    for pattern in EXCLUDE_PATTERNS:
        # Directory check
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            if dir_name in parts:
                return True
        # File glob
        if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        # Full path glob
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def build_zip():
    total_files = 0
    excluded_files = 0

    print(f"📦 Packaging backend: {BACKEND_DIR}")
    print(f"   Output → {OUTPUT_ZIP}\n")

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BACKEND_DIR):
            # Prune excluded directories in-place (prevents descending)
            dirs[:] = [
                d for d in dirs
                if not _is_excluded(
                    os.path.relpath(os.path.join(root, d), BACKEND_DIR) + "/"
                )
            ]

            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, BACKEND_DIR)
                total_files += 1

                if _is_excluded(rel_path):
                    print(f"   ✗ EXCLUDED  {rel_path}")
                    excluded_files += 1
                    continue

                zf.write(abs_path, rel_path)
                print(f"   ✓ {rel_path}")

    included = total_files - excluded_files
    size_mb = OUTPUT_ZIP.stat().st_size / 1_048_576
    print(f"\n✅ Done!")
    print(f"   Files included : {included}")
    print(f"   Files excluded : {excluded_files}")
    print(f"   Zip size       : {size_mb:.2f} MB")
    print(f"   Output         : {OUTPUT_ZIP}")


# ── Verify no secrets slipped through ─────────────────────────────────────────
FORBIDDEN_FILENAMES = {
    "local.settings.json",
}

def verify_zip(zip_path: Path):
    print("\n🔍 Verifying zip contents for secret leaks...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
    leaks = [n for n in names if os.path.basename(n) in FORBIDDEN_FILENAMES]
    if leaks:
        print(f"\n🚨 CRITICAL: Secret files detected in zip!")
        for leak in leaks:
            print(f"   ❌ {leak}")
        raise SystemExit(1)
    else:
        print("   ✅ No secret files detected. Safe to deploy.")


if __name__ == "__main__":
    build_zip()
    verify_zip(OUTPUT_ZIP)
    print(f"\n🚀 Deploy command:")
    print(f"   az functionapp deployment source config-zip \\")
    print(f"     --resource-group <your-rg> \\")
    print(f"     --name summitos-api \\")
    print(f"     --src {OUTPUT_ZIP}")
