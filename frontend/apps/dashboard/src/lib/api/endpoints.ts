/**
 * SummitOS API Endpoints
 *
 * Typed wrappers for every backend route used by DriverDashboard.
 * Import these instead of calling fetch() directly in components.
 */
import { apiGet, apiPost } from './client'

// ─── Types (mirror DriverDashboard.tsx interface types) ───────────────────────
export interface TeslaStatus {
  is_charging: boolean
  charging_state: string | null
  current_soc: number | null
  battery_range_mi: number | null
  charge_power_kw: number
  minutes_to_full: number | null
  location: string | null
  inside_temp: number | null
  outside_temp: number | null
}

export interface TessieDrivesResponse {
  drives: Array<{
    tessie_drive_id: string
    date: string | null
    time_mst: string | null
    tag: string | null
    distance_miles: number
    energy_used_kwh: number
    efficiency_wh_mi: number | null
    average_speed_mph: number
    start: string | null
    end: string | null
    starting_battery: number | null
    ending_battery: number | null
    duration_minutes: number
    fare_matched?: boolean
    driver_earnings?: number | null
  }>
}

export interface UberTripsResponse {
  trips: Array<{
    trip_id: string
    trip_number: number
    timestamp: string | null
    time_display: string
    service_type: string
    driver_earnings: number
    rider_payment: number
    tip: number
    uber_cut: number
    pickup: string | null
    dropoff: string | null
    duration_min: number | null
    distance_mi: number | null
    filename: string | null
  }>
}

export interface SyncResponse {
  success: boolean
  logs?: string[]
  error?: string
  trip_count?: number
}

// ─── Endpoint wrappers ────────────────────────────────────────────────────────
export const api = {
  /** Live Tesla charging/status */
  getTeslaLive: () => apiGet<TeslaStatus>('/copilot/charging/live', { timeoutMs: 8_000, retries: 0 }),

  /** Tessie drives by tag */
  getTessieDrives: (tag: string, days: number) =>
    apiGet<TessieDrivesResponse>(`/copilot/tessie/drives?tag=${tag}&days=${days}`, { timeoutMs: 12_000 }),

  /** Tessie charging sessions */
  getTessieCharges: (days: number) =>
    apiGet<{ sessions: unknown[] }>(`/copilot/tessie/charges?days=${days}`, { timeoutMs: 12_000 }),

  /** OCR-extracted Uber trip cards for a date */
  getDayTrips: (date: string) =>
    apiGet<UberTripsResponse>(`/operations/get-day-trips?date=${date}`, { timeoutMs: 12_000 }),

  /** Rebuild Day — full sync (Tessie + folders + cloud scan) */
  runDailySync: (date: string) =>
    apiPost<SyncResponse>('/daily-sync', { date }),

  /** Create OneDrive folder structure only */
  syncFolders: (processDate: string, dryRun = false) =>
    apiPost<SyncResponse>('/operations/sync-folders', { processDate, dryRun }),

  /** OCR cloud scan */
  triggerCloudScan: (path: string) =>
    apiPost<SyncResponse>('/operations/trigger-cloud-scan', { path }),

  /** Full day OCR scan + trip numbering */
  scanDayTrips: (date: string, path: string) =>
    apiPost<SyncResponse>('/operations/scan-day-trips', { date, path }),
}

export default api
