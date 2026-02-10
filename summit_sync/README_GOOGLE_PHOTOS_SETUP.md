# Google Photos API Setup Guide

To use the `google_photos_watcher.py` script, you need to set up a project in Google Cloud Platform and enable the Google Photos Library API.

## Step 1: Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the specific project dropdown at the top of the page.
3. Click **New Project**.
4. Enter a project name (e.g., "Summit Sync Watcher") and click **Create**.

## Step 2: Enable Google Photos Library API
1. In the Google Cloud Console, select your newly created project.
2. Navigate to **APIs & Services** > **Library**.
3. Search for "Google Photos Library API".
4. Click on the result and then click **Enable**.

## Step 3: Configure OAuth Consent Screen
1. Navigate to **APIs & Services** > **OAuth consent screen**.
2. Select **External** (unless you have a Google Workspace organization, then Internal might be an option, but External is standard for personal test apps) and click **Create**.
3. Fill in the required fields:
   - **App name**: Summit Sync
   - **User support email**: Your email
   - **Developer contact information**: Your email
4. Click **Save and Continue**.
5. **Scopes**: You can skip adding scopes for now, or search/add `.../auth/photoslibrary.readonly`. The script will request it automatically essentially.
6. **Test Users**: Note: Since the app is in "Testing" mode, you MUST add your own email address (`peter.teehan@gmail.com`) to the list of Test Users.
   - Click **Add Users**.
   - Enter `peter.teehan@gmail.com`.
   - Click **Save**.

## Step 4: Create Credentials
1. Navigate to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Application type: **Desktop app**.
4. Name: "Summit Watcher Script".
5. Click **Create**.
6. A popup will appear. Click **Download JSON** (the download icon) to download your `client_secret_....json` file.
7. Rename this file to `client_secret.json`.
8. Move this file into the `summit_sync/credentials/` folder in your project directory.

## Step 5: Run the Script
1. Open your terminal in the `summit_sync` directory.
2. Run the script:
   ```powershell
   python google_photos_watcher.py
   ```
3. A browser window will open asking you to sign in with your Google account.
4. **Important**: You will likely see a "Google hasn't verified this app" warning. This is normal for personal test apps.
   - Click **Advanced**.
   - Click **Go to Summit Sync (unsafe)**.
5. Grant the permission to view your Google Photos.
6. The script should now start polling for new screenshots!

## Troubleshooting
- If you see `transport_consumption_exception`, ensure you have internet access.
- If you get a 403 error, double-check that you added your email to the **Test Users** list in the OAuth Consent Screen configuration.
