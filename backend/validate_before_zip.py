#!/usr/bin/env python3
"""
validate_before_zip.py — Pre-zip security gate for SummitOS backend deploys.

Usage:
    python validate_before_zip.py [--dir <path>]

Scans the staged directory for secret-bearing files BEFORE creating a zip.
Aborts with exit code 1 and a clear error if any are found.
NEVER prints file contents — only filenames.

Called automatically by make_deploy.ps1 / deploy_backend.ps1.
"""
import os
import sys
import argparse

# Files that must NEVER be included in a deploy zip
BLOCKED_EXACT = {
    '.env',
    'local.settings.json',
    '.env.local',
    '.env.production',
    '.env.development',
    '.env.sharepoint',
    '.env.test',
    '.env.receipt-engine.template',
}

# Subdirectory-scoped blocks (relative paths)
BLOCKED_PATHS = {
    'config/.env',
    'finance_mcp/.env',
    'credentials/client_secret.json',
}

# Files that look like secrets but are safe templates/examples (no real creds)
ALLOWED_SUFFIXES = {
    '.env.template',
    '.env.example',
    '.env.sample',
}

# Filename patterns that indicate secrets (checked against basename)
BLOCKED_PATTERNS = [
    lambda f: f.startswith('.env') and not any(f.endswith(s) for s in ALLOWED_SUFFIXES),
    lambda f: f.endswith('-settings.json'),
    lambda f: f.endswith('_settings.json'),
    lambda f: f.endswith('.pem'),
    lambda f: f.endswith('.key'),
    lambda f: f.endswith('.p12'),
    lambda f: 'client_secret' in f and f.endswith('.json'),
    lambda f: f == 'local.settings.json',
]


def load_funcignore(root_dir: str) -> set:
    """Load .funcignore entries as a set of relative path patterns."""
    funcignore_path = os.path.join(root_dir, '.funcignore')
    entries = set()
    if os.path.exists(funcignore_path):
        with open(funcignore_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    entries.add(line.rstrip('/'))
    return entries


def is_covered_by_funcignore(rel_path: str, funcignore: set) -> bool:
    """Return True if rel_path is explicitly listed in .funcignore (exact or prefix match)."""
    fname = os.path.basename(rel_path)
    for entry in funcignore:
        if rel_path == entry or fname == entry:
            return True
        # Prefix match for directory entries (e.g. 'scripts/' covers 'scripts/foo.py')
        if entry.endswith('/') and rel_path.startswith(entry):
            return True
        # Glob-style: entry without trailing slash covers directory
        if rel_path.startswith(entry + '/'):
            return True
    return False


def scan_directory(root_dir: str) -> list[str]:
    """Walk root_dir and return list of relative paths that must not be zipped
    AND are not already acknowledged in .funcignore."""
    funcignore = load_funcignore(root_dir)
    violations = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip venv and __pycache__ — not secret, just noise
        dirnames[:] = [
            d for d in dirnames
            if d not in {'venv32', 'venv', '.venv', '__pycache__', '.git', 'node_modules', '.pytest_cache'}
        ]
        for fname in filenames:
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, root_dir).replace('\\', '/')
            basename = fname.lower()

            is_blocked = False

            # Exact filename match
            if fname in BLOCKED_EXACT or fname.lower() in BLOCKED_EXACT:
                is_blocked = True

            # Relative path match (e.g. config/.env)
            elif rel_path in BLOCKED_PATHS:
                is_blocked = True

            # Pattern match
            elif any(check(basename) for check in BLOCKED_PATTERNS):
                is_blocked = True

            if is_blocked and not is_covered_by_funcignore(rel_path, funcignore):
                violations.append(rel_path)

    return sorted(set(violations))


def main():
    parser = argparse.ArgumentParser(description='Pre-zip security gate for deploy packages.')
    parser.add_argument('--dir', default='.', help='Directory to scan (default: current directory)')
    args = parser.parse_args()

    scan_dir = os.path.abspath(args.dir)
    if not os.path.isdir(scan_dir):
        print(f'ERROR: {scan_dir} is not a directory.', file=sys.stderr)
        sys.exit(1)

    print(f'[validate_before_zip] Scanning: {scan_dir}')
    violations = scan_directory(scan_dir)

    if violations:
        print()
        print('=' * 70)
        print('SECURITY ABORT — SECRET FILES DETECTED IN DEPLOY STAGING AREA')
        print('=' * 70)
        print()
        print('The following files must NOT be included in a deploy zip:')
        for v in violations:
            print(f'  [X]  {v}')
        print()
        print('ACTION REQUIRED:')
        print('  1. Add these files to backend/.funcignore')
        print('  2. Remove them from the staging directory')
        print('  3. Re-run the deploy script')
        print()
        print('DO NOT commit or upload the zip. Rotate any exposed credentials.')
        print('=' * 70)
        sys.exit(1)
    else:
        print('[validate_before_zip] PASS — no secret files detected. Safe to zip.')
        sys.exit(0)


if __name__ == '__main__':
    main()
