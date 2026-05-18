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

// ─── Phase 4 spec-required named wrappers ────────────────────────────────────

/**
 * Fetch the aggregated daily summary for a given date.
 * Returns drive metrics, Uber earnings, and expense totals.
 *
 * @example const summary = await getDailySummary('2026-05-18')
 */
export async function getDailySummary(date: string): Promise<{
  date: string
  uber_earnings: number
  trip_count: number
  total_miles: number
  battery_drain_kwh: number
  net_earnings: number
  drives?: TessieDrivesResponse['drives']
  trips?: UberTripsResponse['trips']
}> {
  const [drives, trips] = await Promise.allSettled([
    apiGet<TessieDrivesResponse>(`/copilot/tessie/drives?tag=Uber&days=1`),
    apiGet<UberTripsResponse>(`/operations/get-day-trips?date=${date}`),
  ])

  const driveList = drives.status === 'fulfilled' ? drives.value.drives : []
  const tripList  = trips.status === 'fulfilled'  ? trips.value.trips   : []

  const uberEarnings  = tripList.reduce((s, t) => s + t.driver_earnings, 0)
  const totalMiles    = driveList.reduce((s, d) => s + d.distance_miles, 0)
  const batteryDrain  = driveList.reduce((s, d) => s + d.energy_used_kwh, 0)

  return {
    date,
    uber_earnings: uberEarnings,
    trip_count: tripList.length,
    total_miles: totalMiles,
    battery_drain_kwh: batteryDrain,
    net_earnings: uberEarnings, // extended by caller if private payments known
    drives: driveList,
    trips: tripList,
  }
}

/**
 * Fetch and sync the driver state for a given date from the cloud.
 * Returns saved expenses, sync metadata, and success flag.
 *
 * @example const sync = await fetchDriverSync('2026-05-18')
 */
export async function fetchDriverSync(date: string): Promise<{
  success: boolean
  date: string
  expenses?: { fastfood: unknown[]; charging: unknown[] }
  error?: string
}> {
  return apiGet<{
    success: boolean
    date: string
    expenses?: { fastfood: unknown[]; charging: unknown[] }
    error?: string
  }>(`/driver/sync?date=${date}`)
}

export default api
