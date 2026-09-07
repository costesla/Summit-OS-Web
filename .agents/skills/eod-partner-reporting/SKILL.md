---
name: eod-partner-reporting
description: Automated End-of-Day (EOD) executive reporting, financial reconciliation, itemized spending breakdown, vector pie chart generation, and multi-recipient Microsoft Graph dispatch for COS Tesla LLC.
---

# EOD Partner Reporting & Executive Intelligence Skill

## 1. Overview & Purpose
This skill encapsulates the end-to-end architecture and operational procedures for generating, reconciling, and dispatching daily End-of-Day (EOD) executive performance briefings for **COS Tesla LLC / Summit Intelligence 2.0**.

Every daily shift produces:
* **Gross Revenue:** Reconciled sum of on-app Uber rideshare fares + passenger tips + direct private client charter invoices.
* **Daily OpEx:** Itemized Supercharging energy costs + verified road meal & incidental receipts.
* **CapEx & Servicing:** Isolated vehicle asset maintenance tracking.
* **Net Operating Profit:** Gross Revenue - Daily OpEx.
* **Trip Count:** Exact count of completed revenue rides (Uber TRIP- rows + completed private charter bookings).

---

## 2. Serverless Runtime & Filesystem Architecture (Azure Functions)

> [!IMPORTANT]
> In Azure Functions Linux App Services running under `WEBSITE_RUN_FROM_PACKAGE=1`, `/home/site/wwwroot` is a **read-only squashfs image**.

### Serverless File Isolation Protocol:
1. **Never Write to Repository Folders**: Attempting `os.makedirs("backend/archive")` or writes to local relative paths throws `OSError: [Errno 30] Read-only file system`.
2. **Ephemeral Directory Pattern**: All dynamically rendered PDFs, raw markdowns, and temporary JSON ledgers must target `tempfile.gettempdir()`:
   ```python
   temp_session_id = f"{date_str}_{uuid4().hex[:8]}"
   archive_dir = os.path.join(tempfile.gettempdir(), "summitos", "partner_reports", temp_session_id)
   ```
3. **Mandatory Cleanup in `finally:`**: Azure Function instances reuse warm worker environments. Always remove temporary directories inside a `finally:` block:
   ```python
   finally:
       if os.path.exists(archive_dir):
           shutil.rmtree(archive_dir, ignore_errors=True)
   ```
4. **Container Dependencies**: Ensure `reportlab>=4.0.0` is permanently declared in `backend/requirements.txt` so the Oryx build pack compiles C extensions and Python modules into the container package.

---

## 3. Dynamic Data Binding & Zero Prototype Enforcement

Never use static mock arrays or hardcoded fallback expense data. All reports must derive exclusively from the live database:

1. **Energy Management (Supercharging)**: Pulled from `db.get_expenses_by_date(date_str)` filtered to category `charging`. Clean timestamps (`HH:MM`) and locations with `clean_location()` helper.
2. **Road Meals & Incidentals**: Pulled from `db.get_expenses_by_date(date_str)` filtered to `fastfood`.
3. **Completed Rides**: Derived from trips matching `id.startswith(('TRIP-', 'INV-'))` or `driver_earnings > 0`.
4. **Vector Pie Chart**: Rendered on the fly via `ReportLab` drawing canvas using dynamic percentage ratios of Net Profit vs Supercharging vs Road Incidentals.

---

## 4. Dual-Reconciliation Financial Integrity Gates
Before any report can be archived or emailed, the engine validates the following mathematical constraints:
1. **Operating Profit Constraint**: `Gross Revenue - Total OpEx == Net Operating Profit (+/- .01)`
2. **Revenue Mix Constraint**: `Uber Platform Revenue + Private Charter Revenue == Total Gross Revenue (+/- .01)`
3. **Net Margin Calculation**: `Net Operating Margin % = (Net Operating Profit / Gross Revenue) * 100`

---

## 5. Core Engine Components
### A. Backend Route & Service Layer
* **API Route**: `tools/partner-eod-report` in [backend/api/driver.py](file:///c:/Users/PeterTeehan/OneDrive - COS Tesla LLC/COS Tesla - Website/Summit-OS-Web-master/backend/api/driver.py)
* **Processing Engine**: `services.eod_engine_production.ProductionEODEngine`
* **PDF Generator**: `services.pdf_generator.ExecutivePDFGenerator` (ReportLab vector Pie chart)
* **Audit Ledger**: `services.audit_ledger.AuditLedgerManager`
* **Mail Dispatch**: `services.graph.GraphClient.send_partner_eod_email()`

### B. Microsoft Graph Cloud Email Dispatch
* **Tenant ID**: `1cd94367-e5ad-4827-90a9-cc4c6124a340` (costesla.com)
* **Client ID**: `3908fbac-03a0-4670-acf9-3bb24188747b` (SummitOS)
* **Primary Recipients (TO)**: Luis Canales (`luis9189@gmail.com`) and selected partners.
* **Mandatory CC**: Peter Teehan (`peter.teehan@costesla.com`) included on every dispatch.
* **Payload Format**: `saveToSentItems: true` placed at the root level of the Graph payload.
