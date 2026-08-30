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

## 2. Dual-Reconciliation Financial Integrity Gates
Before any report can be archived or emailed, the engine validates the following mathematical constraints:
1. Operating Profit Constraint: Gross Revenue - Total OpEx == Net Operating Profit (+/- .01)
2. Revenue Mix Constraint: Uber Platform Revenue + Private Charter Revenue == Total Gross Revenue (+/- .01)
3. Net Margin Calculation: Net Operating Margin % = (Net Operating Profit / Gross Revenue) * 100

## 3. Core Engine Components
### A. Backend Route & Service Layer
* API Route: tools/partner-eod-report in backend/api/driver.py
* Processing Engine: services.eod_engine_production.ProductionEODEngine
* PDF Generator: services.pdf_generator.ExecutivePDFGenerator (ReportLab vector Pie chart)
* Audit Ledger: services.audit_ledger.AuditLedgerManager
* Mail Dispatch: services.graph.GraphClient.send_partner_eod_email()

### B. Report Modules
1. Executive Financial Scorecard: Gross, Net Profit, Margin %, Total OpEx, Completed Trips, and Average Revenue/Trip.
2. Spending vs. Earnings vs. Charging Pie Chart: ReportLab vector Pie chart (Profit 61%, Charging 20%, Meals 19%).
3. Itemized Road Spending & Supercharging Ledger: Charging timestamps, street addresses, costs, and road receipts.
4. Run of the Day & Trip Efficiency Highlights: Top revenue segment, off-peak charging efficiency, top tipped ride.
5. Fleet Telemetry & Fun Stats: Goal pacing (109%), fleet availability (100%), customer quality rating (5.00★).

## 4. Microsoft Graph Cloud Email Dispatch
### A. Authentication & Secret Governance
* OAuth Tenant ID: 1cd94367-e5ad-4827-90a9-cc4c6124a340 (costesla.com)
* OAuth Client ID: 3908fbac-03a0-4670-acf9-3bb24188747b (SummitOS)
* Active Key ID: 5c01998e-20bb-448b-aa70-0047fe50a828 (Valid through August 2028)
* Azure Function App: summitos-api in rg-summitos-prod

### B. Dispatch Rules
* Primary Recipients (TO): Luis Canales (luis9189@gmail.com) and selected advisory contacts.
* Mandatory Owner CC (CC): Peter Teehan (peter.teehan@costesla.com) is permanently hardcoded on every external dispatch.
* Attachments: Versioned publication PDF (YYYY-MM-DD-EOD-v1.pdf) attached as base64 fileAttachment.

## 5. Quadruple Archival Vault & Cryptographic Audit Ledger
For every operational day, the engine archives 4 versioned artifacts in archive/Partner Reports/YYYY/MM Month/:
1. YYYY-MM-DD-raw-v1.txt (Verbatim ingested payload)
2. YYYY-MM-DD-EOD-v1.html (Mobile responsive briefing markup)
3. YYYY-MM-DD-EOD-v1.pdf (Publication document with vector Pie Chart)
4. YYYY-MM-DD-metadata-v1.json (Machine-readable audit receipt with SHA-256 hash)

All runs are recorded in archive/eod_audit_ledger.json with delivery timestamps, recipient rosters, and status lifecycle transitions (DELIVERED, SUBMITTED, LOCAL_SIMULATION_COMPLETED).
