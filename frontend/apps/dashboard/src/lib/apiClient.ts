/**
 * SummitOS API Client — public entry point
 *
 * This flat re-export keeps the import path consistent with the
 * Phase 4 spec (import from 'src/lib/apiClient') while the
 * implementation lives in api/client.ts + api/endpoints.ts.
 *
 * Usage:
 *   import { apiGet, apiPost, ApiError } from '../lib/apiClient'
 *   import { api } from '../lib/apiClient'          // typed endpoint wrappers
 *   import { BASE_URL } from '../lib/apiClient'     // base URL for diagnostics
 */
export { apiGet, apiPost, apiRequest, BASE_URL, ApiError } from './api/client'
export { api } from './api/endpoints'
export type { TeslaStatus, UberTripsResponse, SyncResponse } from './api/endpoints'
