# Play Store deploy — API access setup

One-time setup so `scripts/upload_bundle.py` can push a signed `.aab` to the
**internal testing** track for `com.costesla.app` using the official
**Google Play Android Developer API v3**. No third-party CLI ever holds the key.

> **When you actually need this:** only for **Category B** changes — app name,
> launcher icon, splash/manifest values, or the annual `targetSdkVersion` bump.
> Website content ships without a Play release (that's the whole point of the
> TWA). Expect to run this ~2–4 times a year. See `updating-the-app` guidance in
> `ANDROID_APP_PLAN.md`.

> ⚠️ **Don't run this while an app review is pending.** As of 2026-07-14 the first
> submission is *in review*. Uploading a new bundle mid-review can supersede or
> complicate the submission. Wait for approval.

---

## 1. Enable the API

1. Open the **Google Cloud Console** → pick (or create) the project you want to
   own this automation.
2. **APIs & Services → Library** → search **"Google Play Android Developer API"**
   → **Enable**.

## 2. Create the Service Account

1. **IAM & Admin → Service Accounts → Create service account**
   - Name: `summitos-play-publisher`
   - No GCP project roles are required — Play permissions are granted in the
     Play Console (step 3), not in GCP IAM.
2. Open the new account → **Keys → Add key → Create new key → JSON** → download.
3. **Copy the service account email** (looks like
   `summitos-play-publisher@<project>.iam.gserviceaccount.com`).

**Treat that JSON like a password.** It can publish to your app. Store it outside
the repo (this repository is **public**), e.g. `~/.secrets/play-service-account.json`,
and `chmod 600` it. Never commit it, never paste it into chat.

## 3. Grant it access in the Play Console

1. **Play Console → Users and permissions → Invite new users**.
2. Paste the **service account email**.
3. Under **App permissions**, add **COS Tesla** (`com.costesla.app`).
4. Grant, at minimum:
   - **Release → Release to testing tracks** (internal testing)
   - **Release → View app information**
   
   Do **not** grant production release rights unless you intend to automate
   production rollouts. Least privilege: this script only targets `internal`.
5. **Invite user** → the account appears immediately (no email confirmation).

> Permissions can take a few minutes to propagate. A `403` on the first run
> usually means "wait 5 minutes," not "misconfigured."

## 4. Export the environment variables

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/play-service-account.json"
export SUMMITOS_PACKAGE_NAME="com.costesla.app"
```

`GOOGLE_APPLICATION_CREDENTIALS` is the standard Google auth variable — the
script picks it up via `google.auth.default()`; the key path is never hardcoded.

Add both to your shell profile (`~/.bashrc`, `~/.zshrc`) to persist them.

## 5. Install the two official libraries

```bash
pip install -r scripts/requirements-deploy.txt
```

(`google-api-python-client` + `google-auth` — both maintained by Google.)

## 6. Run it

```bash
# from the repo root, after `bubblewrap build` produces the .aab
python scripts/upload_bundle.py ./app-release.aab
```

The script opens a transactional **edit**, uploads the bundle, assigns the
version code to the `internal` track, and commits. **If any step fails it does
not commit** — the edit is abandoned and the store is untouched.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `403 ... does not have permission` | Service account not invited in Play Console, or permissions still propagating (wait ~5 min) |
| `401 invalid_grant` | Key JSON revoked/wrong, or clock skew on the machine |
| `400 ... APK/AAB signature` | The `.aab` was signed with a key Play doesn't recognise — must be the upload key from your vaulted keystore |
| `versionCode already used` | Bump the version in `twa-manifest.json` and re-run `bubblewrap build` |
| Upload succeeds, nothing in console | The edit was never committed — check for a non-zero exit / traceback |
