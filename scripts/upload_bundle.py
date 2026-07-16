#!/usr/bin/env python3
"""
Publish a signed .aab to the Google Play internal testing track.

Official Google Play Android Developer API v3 only — google-api-python-client
and google-auth. No third-party CLI ever sees the service account key.

    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/play-service-account.json"
    export SUMMITOS_PACKAGE_NAME="com.costesla.app"
    python scripts/upload_bundle.py ./app-release.aab

Setup: docs/deploy-api-setup.md

Transaction model: Play edits are all-or-nothing. We insert() an edit, upload
into it, assign the track, then commit(). Nothing reaches the store until
commit() succeeds — so any failure simply abandons the edit and leaves the
listing untouched. That is the safety property this script is built around.

Only Category B changes (name / icon / manifest / targetSdkVersion) need this;
website content ships without a Play release.
"""
import argparse
import os
import sys

ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
DEFAULT_TRACK = "internal"
# 5 MiB chunks: resumable upload survives a flaky connection without restarting.
CHUNK_SIZE = 5 * 1024 * 1024


def fail(msg: str, code: int = 1) -> "None":
    print(f"\n  ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def preflight(bundle_path: str) -> str:
    """Check everything we can before touching the network."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        fail(
            "GOOGLE_APPLICATION_CREDENTIALS is not set.\n"
            '  export GOOGLE_APPLICATION_CREDENTIALS="/path/to/play-service-account.json"\n'
            "  See docs/deploy-api-setup.md"
        )
    if not os.path.isfile(creds_path):
        fail(f"Service account key not found at: {creds_path}")

    package_name = os.environ.get("SUMMITOS_PACKAGE_NAME")
    if not package_name:
        fail(
            "SUMMITOS_PACKAGE_NAME is not set.\n"
            '  export SUMMITOS_PACKAGE_NAME="com.costesla.app"'
        )

    if not os.path.isfile(bundle_path):
        fail(
            f"Bundle not found: {bundle_path}\n"
            "  Run `bubblewrap build` first, or pass the path explicitly."
        )
    if not bundle_path.endswith(".aab"):
        fail(
            f"Expected an .aab app bundle, got: {bundle_path}\n"
            "  (.apk files cannot be uploaded to a Play release track.)"
        )

    size_mb = os.path.getsize(bundle_path) / (1024 * 1024)
    print(f"  bundle   : {bundle_path} ({size_mb:.1f} MB)")
    print(f"  package  : {package_name}")
    print(f"  key      : {creds_path}")
    return package_name


def build_service():
    try:
        import google.auth
        from googleapiclient.discovery import build
    except ImportError:
        fail(
            "Missing Google libraries.\n"
            "  pip install -r scripts/requirements-deploy.txt"
        )

    # google.auth.default() reads GOOGLE_APPLICATION_CREDENTIALS. The key path
    # stays in the environment; it is never embedded here.
    credentials, _ = google.auth.default(scopes=[ANDROID_PUBLISHER_SCOPE])
    return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)


def upload_bundle(service, package_name, edit_id, bundle_path):
    """Resumable, chunked upload into the open edit. Returns the versionCode."""
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(
        bundle_path,
        mimetype="application/octet-stream",
        resumable=True,
        chunksize=CHUNK_SIZE,
    )
    request = service.edits().bundles().upload(
        editId=edit_id,
        packageName=package_name,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"\r  uploading… {int(status.progress() * 100)}%", end="", flush=True)
    print("\r  uploading… 100%")

    version_code = response.get("versionCode")
    if version_code is None:
        raise RuntimeError(f"Upload returned no versionCode: {response}")
    return version_code


def assign_track(service, package_name, edit_id, version_code, track, notes):
    """Point the track at the new versionCode. versionCodes must be strings."""
    body = {
        "releases": [
            {
                "versionCodes": [str(version_code)],
                "status": "completed",
            }
        ]
    }
    if notes:
        body["releases"][0]["releaseNotes"] = [{"language": "en-US", "text": notes}]

    service.edits().tracks().update(
        editId=edit_id,
        packageName=package_name,
        track=track,
        body=body,
    ).execute()


def abandon(service, package_name, edit_id):
    """Explicitly drop the edit. Uncommitted edits expire on their own, so this
    is politeness, not correctness — never let cleanup mask the real error."""
    if not edit_id:
        return
    try:
        service.edits().delete(editId=edit_id, packageName=package_name).execute()
        print("  edit abandoned; the store was not modified.")
    except Exception as e:  # noqa: BLE001
        print(f"  (could not delete edit {edit_id}: {e} — it will expire on its own)")


def main():
    parser = argparse.ArgumentParser(description="Upload a signed .aab to Google Play.")
    parser.add_argument("bundle", nargs="?", default="./app-release.aab", help="path to the .aab")
    parser.add_argument("--track", default=DEFAULT_TRACK, help=f"release track (default: {DEFAULT_TRACK})")
    parser.add_argument("--notes", default=None, help="release notes for en-US")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation for non-internal tracks")
    args = parser.parse_args()

    print("\nPlay bundle upload\n" + "-" * 40)
    package_name = preflight(args.bundle)
    print(f"  track    : {args.track}")

    # Guard rail: internal is testers-only and safe to automate. Anything else
    # ships to real users, so make that an explicit, deliberate act.
    if args.track != DEFAULT_TRACK and not args.yes:
        print(
            f"\n  '{args.track}' is not the internal test track — this can reach real users.\n"
            f"  Re-run with --yes if that is genuinely what you want."
        )
        sys.exit(2)

    service = build_service()
    edit_id = None
    try:
        edit_id = service.edits().insert(body={}, packageName=package_name).execute()["id"]
        print(f"  edit     : {edit_id} (open)")

        version_code = upload_bundle(service, package_name, edit_id, args.bundle)
        print(f"  uploaded : versionCode {version_code}")

        assign_track(service, package_name, edit_id, version_code, args.track, args.notes)
        print(f"  assigned : versionCode {version_code} -> '{args.track}'")

        service.edits().commit(editId=edit_id, packageName=package_name).execute()
        print(f"\n  COMMITTED — versionCode {version_code} is live on '{args.track}'.\n")
    except KeyboardInterrupt:
        print("\n  interrupted.")
        abandon(service, package_name, edit_id)
        sys.exit(130)
    except Exception as e:  # noqa: BLE001
        # Nothing was committed, so the store is unchanged regardless.
        print(f"\n  FAILED: {e}", file=sys.stderr)
        abandon(service, package_name, edit_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
