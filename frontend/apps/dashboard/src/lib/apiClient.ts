/**
 * SummitOS API Client — public entry point
 *
 * Flat re-export matching the Phase 4 spec import path:
 *   import { getDailySummary, fetchDriverSync } from '../lib/apiClient'
 *   import { api, apiGet, apiPost, ApiError } from '../lib/apiClient'
 *   import { logEvent, logError, logTiming } from '../lib/apiClient'
 *
 * Implementation lives in api/client.ts + api/endpoints.ts + telemetry.ts
 */
export { apiGet, apiPost, apiRequest, BASE_URL, ApiError } from './api/client'
export { api, getDailySummary, fetchDriverSync } from './api/endpoints'
export type { TeslaStatus, UberTripsResponse, SyncResponse, TessieDrivesResponse } from './api/endpoints'
export { logEvent, logError, logTiming, telemetry, EVENTS } from './telemetry'
