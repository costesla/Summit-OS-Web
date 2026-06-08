# Onboarding a New Private Client in SummitOS

To onboard a new private client, follow these steps to ensure their bookings are correctly synced, classified, and styled on the dashboard:

## Step 1: Outlook Bookings Convention
When scheduling a booking for the new client, ensure the Event / Appointment start subject or the unique booking ID follows the **`INV-{ClientName}-...`** prefix convention.
* **Example**: `INV-LORYNNE-Saturday-1352`
* The ingestion logic dynamically retrieves all client names starting with `INV-` from the database.

## Step 2: Backend Classification (Automated)
The backend dynamically derives the client name from the bookings database by checking for `INV-` records using the `get_known_client_names` function in:
1. [database.py (Backend)](file:///C:/Users/PeterTeehan/OneDrive%20-%20COS%20Tesla%20LLC/COS%20Tesla%20-%20Website/Summit-OS-Web-master/backend/services/database.py)
2. [database.py (Summit Sync)](file:///C:/Users/PeterTeehan/OneDrive%20-%20COS%20Tesla%20LLC/COS%20Tesla%20-%20Website/Summit-OS-Web-master/summit_sync/lib/database.py)

This allows any Tessie drives tagged with the client's name (case-insensitive) to be automatically classified as private trips for that client. No backend code changes are required for new clients.

## Step 3: Frontend styling in DriverDashboard
To add a visual badge filter and specific colors for the client on the dashboard:
1. Open [DriverDashboard.tsx](file:///C:/Users/PeterTeehan/OneDrive%20-%20COS%20Tesla%20LLC/COS%20Tesla%20-%20Website/Summit-OS-Web-master/frontend/src/components/DriverDashboard.tsx).
2. Locate the `TAG_FILTERS` array and add the client's capitalized name to the list (e.g., `Lorynne`):
   ```typescript
   const TAG_FILTERS = [..., 'Terrance', 'Lorynne', 'Staging', ...] as const;
   ```
3. Locate the `TAG_STYLE` mapping and add a Tailwind badge style mapping for the lowercase version of the client's name (e.g., `lorynne`):
   ```typescript
   lorynne: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200/80',
   ```
