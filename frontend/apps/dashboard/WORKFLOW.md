# SummitOS Driver Dashboard — Daily Operations Workflow

**Dashboard URL:** [www.dashboardcostesla.com](https://www.dashboardcostesla.com)

---

## Overview

The SummitOS Driver Dashboard tracks daily Uber earnings, Tesla telemetry, and business expenses. Data flows from three sources:

| Source | What it provides |
|---|---|
| **Tessie** | Vehicle telemetry — drive distance, battery, timestamps |
| **Uber card screenshots** | Earnings — fare, tip, driver earnings, platform cut |
| **Manual entry** | Expenses — fast food, charging costs |

These three sources must be combined in the correct order each day for the dashboard to show accurate numbers.

---

## Daily Workflow

### Prerequisites — Do This First

> **Before running any sync, label your drives in Tessie.**

1. Open the **Tessie app** or [tessie.com](https://tessie.com)
2. Navigate to **Drives** for the date you are processing
3. Tag each drive with the appropriate label:
   - `Uber` — for Uber rideshare trips
   - `Jackie` — for Jackie private drives
   - `Esmeralda` — for Esmeralda private drives
4. Untagged drives are **ignored by the sync pipeline** — they will not appear in the dashboard

---

### Step 1 — Select the Date

On the dashboard, use the **date picker in the header** to select the date you are processing.

> Default is today (Mountain Time). Change this to yesterday or a past date if you are doing catch-up logging.

---

### Step 2 — Rebuild Day

Click the **Rebuild Day** button in the Intelligence Sync panel.

**What it does (in order):**
1. ✅ Creates the OneDrive folder structure: `Uber Driver/YYYY/Month/Week N/DD/`
2. ✅ Pulls Tessie drives and charging sessions for the selected date into SQL
3. ✅ Uber-tagged drives are saved as `Classification = Uber_Dropoff` in the database
4. ✅ Runs a cloud scan of OneDrive for any existing screenshots

> **This must run before Match Screenshots.** The drive records must exist in SQL before screenshots can match to them.

---

### Step 3 — Upload Screenshots

> ⚠️ **Note (May 2026):** Samsung has terminated its OneDrive auto-sync partnership. Screenshots must be uploaded manually until a replacement auto-sync solution is configured.

**Option A — Direct Upload on Dashboard (Preferred)**
Use the **Upload Screenshot** button directly on the dashboard. You can select **multiple screenshots at once** (e.g. `Ctrl + A` or dragging to select) from your device — they are sent directly to the OCR engine and processed sequentially without needing OneDrive at all.

**Option B — Manual OneDrive Upload**
If using OneDrive, place screenshots in the date folder:
```
OneDrive → Uber Driver → YYYY → Month → Week N → DD
```
Example for May 1st: `Uber Driver/2026/May/Week 1/01`

Then run **Match Screenshots** from the dashboard.

**Screenshot filename format** — the filename timestamp is what the matcher uses to find the correct Tessie drive:

| Format | Example |
|---|---|
| `Screenshot_YYYYMMDD_HHMMSS.jpg` | `Screenshot_20260501_143022.jpg` |
| `Screenshot YYYY-MM-DD HHMMSS.jpg` | `Screenshot 2026-05-01 143022.jpg` |
| `Screenshot_YYYY-MM-DD-HH-MM-SS.jpg` | `Screenshot_2026-05-01-14-30-22.jpg` |

---

### Step 4 — Match Screenshots

Click the **Match Screenshots** button in the Intelligence Sync panel.

**What it does:**
1. Scans OneDrive Camera Roll and Screenshots folders for `.jpg`/`.png` files
2. Runs Azure OCR on each image to extract:
   - `Your earnings` → driver earnings
   - `Rider payment` → total fare paid by rider
   - `Added tip` → tip amount
3. Extracts the timestamp from the **filename**
4. Searches SQL for an unmatched `Uber_Dropoff` drive within **±4 hours** of the screenshot timestamp
5. On match: updates the ride record with fare, tip, earnings, and platform cut
6. Matched rides appear in **Recent Trips** with `Classification = Uber_Matched`

**Match criteria summary:**

| Requirement | Detail |
|---|---|
| OCR must find "Your earnings" | Drive must be labeled `Uber` in Tessie first |
| Screenshot filename must include date/time | Standard phone screenshot naming works |
| Tessie drive must exist within ±4 hours | Run Rebuild Day before this step |
| Drive must not already be matched | Prevents double-counting |

**If a screenshot returns NO_MATCH:**
- The Tessie drive may not have been labeled `Uber` before Rebuild Day ran
- The screenshot filename may be missing a timestamp
- The time gap between the screenshot and drive end time may exceed 4 hours
- → Re-label in Tessie, re-run Rebuild Day, then try Match Screenshots again

---

### Step 5 — Log Expenses Manually

Use the **expense entry forms** on the dashboard to log daily costs:

- **Fast Food** — meals purchased while driving
- **Charging** — EV charging sessions not captured by Tessie

Enter the amount and a note for each expense. These are saved immediately to the cloud and appear in the Expenses section.

> **Do not use the banking sync** — auto bank sync is disabled because it pulls historical data that distorts daily numbers. All expenses are entered manually.

---

### Step 6 — Review Daily Numbers

After completing the above steps, the dashboard displays:

| Metric | Source |
|---|---|
| Total Earnings | Sum of `Driver_Earnings` from matched Uber rides |
| Total Tips | Sum of `Tip` from matched rides |
| Net Profit | Earnings − Fast Food expenses − Charging expenses |
| Trip Count | Number of `Uber_Matched` or `Manual_Entry` rides |
| Miles Driven | Sum of `Distance_mi` from Tessie telemetry |

---

## Sync Panel Reference

| Button | API Endpoint | What It Does |
|---|---|---|
| **Create Folders** | `POST /operations/sync-folders` | Creates the OneDrive date folder structure only |
| **Rebuild Day** | `POST /daily-sync` | Full sync: Tessie + folders + cloud scan |
| **Match Screenshots** | `POST /operations/trigger-cloud-scan` | OCR scan and Uber card matching only |

---

## Data Flow Diagram

```
Tessie App
  └─ Label drives (Uber / Jackie / Esmeralda)
        ↓
  Dashboard → Rebuild Day
        ↓ Pulls tagged drives into SQL
        ↓ Classification = 'Uber_Dropoff'

OneDrive (Camera Roll / Screenshots)
  └─ Upload Uber trip detail card screenshots
        ↓
  Dashboard → Match Screenshots
        ↓ OCR extracts fare, tip, earnings
        ↓ Matches to Uber_Dropoff drive (±4 hrs)
        ↓ Classification → 'Uber_Matched'
        ↓ Fare, Tip, Driver_Earnings written to SQL

Dashboard → Recent Trips
  └─ Shows rides WHERE:
       Fare > 0
       OR Classification = 'Manual_Entry'
       OR Classification = 'Uber_Matched'

Dashboard → Expense Forms
  └─ Manual entry: Fast Food, Charging
       ↓ Saved to Rides.ManualExpenses
```

---

## Troubleshooting

### Trips not appearing in Recent Trips
- Confirm drives are labeled in Tessie **before** running Rebuild Day
- Run Rebuild Day again after labeling
- Check that Match Screenshots ran successfully and returned MATCHED status in the console log

### Screenshot returns NO_MATCH
- The drive classification in SQL may still be `Uber_Core` instead of `Uber_Dropoff` — check Tessie tag
- The screenshot filename may lack a timestamp — rename it to include date/time
- The time gap may be > 4 hours — this can happen with late-night uploads

### Dashboard shows blank / no data
- Confirm the selected date in the header matches the date you synced
- Do a hard refresh: **Ctrl + Shift + R** (Windows) or **Cmd + Shift + R** (Mac)
- If still blank, check the Intelligence Console log after running Rebuild Day for errors

### Build/deployment issues
Always run a local build before pushing changes to the dashboard:
```bash
cd frontend/apps/dashboard
npm run build
```
A failed build on Azure will silently serve the last working bundle — no error is shown on the site.

---

## Key File Locations

| Component | Path |
|---|---|
| Dashboard UI | `frontend/apps/dashboard/src/components/DriverDashboard.tsx` |
| Tessie Sync Service | `backend/services/tessie_sync.py` |
| Screenshot OCR Matcher | `backend/services/uber_matcher.py` |
| Cloud Watcher (OneDrive scan) | `backend/services/cloud_watcher.py` |
| Operations API | `backend/api/operations.py` |
| Driver Sync API | `backend/api/driver.py` |
| Database Queries | `backend/services/database.py` |
| Azure Deploy Workflow | `.github/workflows/azure-static-web-apps-dashboard.yml` |

---

*Last updated: May 2, 2026 — SummitOS v2.1.0*
