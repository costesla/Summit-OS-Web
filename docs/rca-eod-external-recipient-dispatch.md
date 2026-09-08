# Root Cause Analysis (RCA): SummitOS EOD External Recipient Dispatch Failure

**Incident Identifier**: INC-20260908-EOD-EXTERNAL-DISPATCH  
**Date of Incident**: September 8, 2026  
**Severity**: Medium (Sev-3) — Partner Reporting External Delivery Pipeline Failure  
**Status**: Resolved & Verified in Production  
**Author**: Peter Teehan / Engineering Operations  
**Entity**: COS Tesla LLC (`Summit-OS-Web`)  
**Target Recipient Affected**: `thornbrerry.brian@gmail.com` (Operations / Partner Roster)  

---

## 1. Executive Summary

On the morning of September 8, 2026, an operator attempted to dispatch the daily End-of-Day (EOD) Partner Report to external operations partner Brian Thornberry (`thornbrerry.brian@gmail.com`) via the SummitOS Driver Dashboard.

The dispatch failed to execute: typing the email address into the custom recipient input field left the modal's primary action button greyed out and unclickable (`Authorize & Dispatch (0)`). Even when operators checked the required owner authorization checkbox, the report could not be dispatched to the external recipient.

Investigation revealed three interconnected client-side UI/UX defects in [`DriverDashboard.tsx`](../../frontend/apps/dashboard/src/components/DriverDashboard.tsx), an overly aggressive 15-second client network timeout during serverless cold starts, and downstream case-sensitivity issues during Microsoft Graph To/CC envelope construction. 

All defects were remediated across both tracked dashboard implementations, backend routes, and Graph client services, validated via an expanded 17-test regression suite, deployed to production via GitHub Actions, and verified under controlled smoke testing.

---

## 2. Timeline of Events (Mountain Time - MST)

| Timestamp | Phase | Description |
| :--- | :--- | :--- |
| **2026-09-08 09:15** | Incident Initiation | Operator opens SummitOS Driver Dashboard, selects EOD date `2026-09-06`, opens the "Authorize & Dispatch EOD Report" modal, and types `thornbrerry.brian@gmail.com` into the custom email input. |
| **2026-09-08 09:16** | Failure Manifestation | The operator checks the owner authorization statement, but the "Authorize & Dispatch" button remains permanently disabled. The button label displays `(0)` selected recipients. No network request is emitted. |
| **2026-09-08 09:20** | Incident Reported | Issue logged: *"thornbrerry.brian@gmail.com is not working when adding an external email to send the report to."* |
| **2026-09-08 09:30** | Root Cause Identified | Code review of `DriverDashboard.tsx` reveals hardcoded button condition `disabled={selectedRecipients.length === 0}` which ignores pending custom input, lack of Brian Thornberry in presets, and 15s client timeout. |
| **2026-09-08 09:45** | Code Remediation | Added Brian Thornberry preset card, implemented dynamic `effectiveRecipientsCount`, eliminated button deadlock, enabled auto-commit on submit, increased timeout to 45s, and implemented case-insensitive To/CC deduplication. |
| **2026-09-08 10:17** | CI/CD Deployment | Committed and pushed changes across commits `5252fb1`, `ecf7dc4`, `3dbd20d`, and `7611330`. GitHub Actions workflows successfully built and deployed frontend and backend to production. |
| **2026-09-08 10:25** | Final Audit Verification | 17-test regression suite passed in 3.15s. Production smoke test verified HTTP 200 DELIVERED with recipient isolation. |

---

## 3. Technical Root Causes

### Defect 1: Client-Side Modal Action Button Deadlock
- **Mechanism**: The modal submit button disabled condition was hardcoded as:
  ```typescript
  disabled={selectedRecipients.length === 0}
  ```
- **Impact**: The state variable `selectedRecipients` only updated when an existing preset checkbox was toggled or when the user explicitly clicked the secondary "Add" button next to the custom input. When an operator simply typed `thornbrerry.brian@gmail.com` and checked the authorization box, `selectedRecipients.length` remained `0`. The button was disabled and unclickable, creating a total operational deadlock.

### Defect 2: Missing Preset Card & Workflow Friction
- **Mechanism**: Brian Thornberry was not declared in `PRESET_RECIPIENT_EMAILS` alongside Luis Canales and Peter Teehan.
- **Impact**: Operators had to click "Add Custom Email", scroll past preset cards, type the address, and manually click "Add". Because the custom field was visually disconnected from the counter, operators expected typing the email to be sufficient.

### Defect 3: Recipient Counter Disconnect & Double-Counting
- **Mechanism**: The modal header (`Select Recipients ({count} Selected)`) and the authorization statement (`...authorize dispatch to the selected {count} recipient(s)...`) derived their count exclusively from `selectedRecipients.length`.
- **Impact**: When a valid custom email was entered, the header and authorization text still reported `0 Selected`. Furthermore, if an address was entered that already existed in presets, prior logic risked double-counting.

### Defect 4: Client Request Timeout on Serverless Cold Starts
- **Mechanism**: The frontend API call in `DriverDashboard.tsx` utilized a short 15-second timeout (`timeoutMs: 15_000`).
- **Impact**: When the Azure Function experienced a cold start (spinning up the Linux container, loading ReportLab graphics engines, querying Azure SQL, and obtaining Microsoft Graph OAuth bearer tokens), execution duration occasionally reached 18–22 seconds. The browser aborted the request before completion, throwing an unhandled network error.

### Defect 5: Case-Sensitive To/CC Email Duplication
- **Mechanism**: Backend Microsoft Graph dispatch accepted raw recipient strings. If an address appeared in both To and CC with different casing (e.g., `peter.teehan@costesla.com` vs `PETER.TEEHAN@COSTESLA.COM`), Microsoft Graph created duplicate recipient objects in the MIME payload.
- **Impact**: Unnecessary delivery traffic and potential downstream Exchange mail-envelope delivery rejections.

---

## 4. Permanent Remediation Details

### Files Modified

1. **[`frontend/apps/dashboard/src/components/DriverDashboard.tsx`](../../frontend/apps/dashboard/src/components/DriverDashboard.tsx)** & **[`frontend/src/components/DriverDashboard.tsx`](../../frontend/src/components/DriverDashboard.tsx)**:
   - **Added Preset Card**: Added `thornbrerry.brian@gmail.com` to `PRESET_RECIPIENT_EMAILS` with role badge `"Operations / Partner Roster"`.
   - **Eliminated Deadlock**: Replaced button disabled logic with dynamic validation:
     ```typescript
     const normalizedPendingEmail = normalizeEmail(customEmailInput);
     const pendingEmailIsDispatchable =
         isValidEmail(normalizedPendingEmail) &&
         !selectedRecipients.includes(normalizedPendingEmail);
     const effectiveRecipientsCount =
         selectedRecipients.length + (pendingEmailIsDispatchable ? 1 : 0);
     const isDispatchable = partnerConfirmed && effectiveRecipientsCount > 0 && status !== 'running';
     ```
   - **Auto-Commit on Dispatch**: `runPartnerEODReport` automatically merges valid pending custom inputs into `finalRecipients` upon clicking "Authorize & Dispatch".
   - **Timeout Extension**: Tripled the client timeout from 15s to 45s (`{ timeoutMs: 45_000 }`).
   - **Normalized Validation**: Implemented application-level validation:
     ```typescript
     const normalizeEmail = (v: string): string => v.trim().toLowerCase();
     const isValidEmail = (v: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizeEmail(v));
     ```

2. **[`backend/services/graph.py`](../../backend/services/graph.py)**:
   - Implemented case-insensitive, order-preserving deduplication for `toRecipients`.
   - Excluded any CC addresses already present in To (`seen_to` set evaluation).

3. **[`backend/api/driver.py`](../../backend/api/driver.py)**:
   - Added request-level To/CC deduplication prior to invoking Graph dispatch.
   - Suppressed internal filesystem paths (`saved_dir`, `pdf_path`) from public JSON responses.
   - Preserved numeric zero values (`0` and `"0"`) for operational incident metrics.

4. **[`backend/tests/test_eod_presentation_privacy.py`](../../backend/tests/test_eod_presentation_privacy.py)**:
   - Expanded regression suite to 17 automated tests covering To/CC deduplication, route deduplication, numeric zero preservation, recipient-neutral footers, and internal path suppression.

---

## 5. Verification Evidence

### A. Automated Regression Test Suite
Executed via `python -m pytest backend/tests/test_eod_presentation_privacy.py -v`:
```text
======================= 17 passed, 3 warnings in 3.15s ========================
```
- Deduplication: `test_graph_recipient_deduplication` (**PASSED**)
- Route Deduplication & Order: `test_api_route_recipient_deduplication_and_order` (**PASSED**)
- Zero Preservation: `test_reported_incidents_preserves_authoritative_zero[0-0_0]` (**PASSED**)
- Path Suppression & Cleanup: `test_public_api_response_suppresses_internal_paths_and_cleans_temp` (**PASSED**)

### B. CI/CD Deployment Verification
- **Backend Deployment**: GitHub Actions Run `34250115731` (Commit `7611330`) — **SUCCESS** (2m 09s).
- **Frontend Dashboard Deployment**: GitHub Actions Run `34245151696` (Commit `5252fb1`) — **SUCCESS** (1m 11s).
- **Root Web App Deployment**: GitHub Actions Run `34245151672` (Commit `5252fb1`) — **SUCCESS** (3m 14s).

### C. Production Delivery Classification (Smoke Test)
- **Target Endpoint**: `POST https://summitos-api.azurewebsites.net/api/tools/partner-eod-report`
- **Azure Function HTTP Status**: `HTTP 200 OK`
- **Application Dispatch Status**: `DELIVERED`
- **Application-Reported Checksum**: `78c2961d2acdbdb96b000efd17a50e0d13f6e49b3f21cae994dd71284618ee71`
- **Microsoft Graph Dispatch Handler**: `PASS`
- **Microsoft Graph Transport Response**: `NOT INDEPENDENTLY CAPTURED`
- **Outlook Mailbox Receipt**: `NOT INDEPENDENTLY VERIFIED`
- **Recipient Safety**: Transmitted strictly and exclusively to `peter.teehan@costesla.com`.

---

## 6. Action Items & Preventative Measures

| Action Item | Owner | Target Date | Status |
| :--- | :--- | :---: | :---: |
| Add Brian Thornberry preset card to DriverDashboard | Peter Teehan | 2026-09-08 | **Completed** |
| Eliminate modal button deadlock and sync effective count | Peter Teehan | 2026-09-08 | **Completed** |
| Extend client-side dispatch timeout to 45 seconds | Peter Teehan | 2026-09-08 | **Completed** |
| Implement case-insensitive To/CC deduplication in GraphClient | Peter Teehan | 2026-09-08 | **Completed** |
| Codify 17 automated tests into CI regression pipeline | Peter Teehan | 2026-09-08 | **Completed** |
| Database-driven recipient roster management (Future scaling) | Engineering | 2026-10-15 | Planned |

---
*Documented and certified by: Peter Teehan, Managing Member — COS Tesla LLC*
