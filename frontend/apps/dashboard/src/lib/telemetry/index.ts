/**
 * SummitOS Dashboard — Telemetry Module
 *
 * Provides a structured, zero-secret client-side event logger.
 * Controlled by VITE_TELEMETRY_ENABLED (set in Azure Static Web App env vars).
 *
 * Vocabulary aligns with WORKFLOW.md operational events so that
 * SummitOS Intelligence can trace the daily sync pipeline.
 */

// ─── Config ──────────────────────────────────────────────────────────────────
const ENABLED = import.meta.env.VITE_TELEMETRY_ENABLED !== 'false'
const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? 'unknown'
const SINK_URL = import.meta.env.VITE_TELEMETRY_SINK_URL ?? null

// ─── Types ────────────────────────────────────────────────────────────────────
export type TelemetryLevel = 'info' | 'warn' | 'error'

export interface TelemetryEvent {
  ts: string           // ISO 8601 timestamp
  level: TelemetryLevel
  event: string        // machine-readable event name (snake_case)
  message?: string     // human-readable description
  data?: Record<string, unknown>
  version: string
  session: string
}

// ─── Session ID (scoped to tab lifetime) ─────────────────────────────────────
const SESSION_ID = Math.random().toString(36).slice(2, 10)

// ─── Operational Event Vocabulary ────────────────────────────────────────────
// These strings are the contract between the dashboard and SummitOS Intelligence.
export const EVENTS = {
  // App lifecycle
  APP_INIT:                   'app_init',
  PAGE_VIEW:                  'page_view',
  ROUTE_CHANGE:               'route_change',

  // Daily sync pipeline (mirrors WORKFLOW.md steps)
  SYNC_STARTED:               'sync_started',
  SYNC_COMPLETED:             'sync_completed',
  SYNC_FAILED:                'sync_failed',

  // Tessie
  TESSIE_TAGGING_CONFIRMED:   'tessie_tagging_confirmed',
  TESSIE_DRIVES_LOADED:       'tessie_drives_loaded',
  TESSIE_DRIVE_IMPORTED:      'tessie_drive_imported',

  // Screenshots / OCR
  UBER_CARDS_UPLOADED:        'uber_cards_uploaded',
  SCREENSHOT_MATCH_STARTED:   'screenshot_match_started',
  SCREENSHOT_MATCH_COMPLETED: 'screenshot_match_completed',
  SCREENSHOT_NO_MATCH:        'screenshot_no_match',

  // Expenses
  MANUAL_EXPENSE_ADDED:       'manual_expense_added',
  EXPENSE_DELETED:            'expense_deleted',

  // API
  API_CALL_STARTED:           'api_call_started',
  API_CALL_COMPLETED:         'api_call_completed',
  API_FAILURE:                'api_failure',

  // Errors
  JS_ERROR:                   'js_error',
  UNHANDLED_REJECTION:        'unhandled_rejection',
} as const

export type EventName = typeof EVENTS[keyof typeof EVENTS]

// ─── Core logger ─────────────────────────────────────────────────────────────
function emit(
  level: TelemetryLevel,
  event: string,
  message?: string,
  data?: Record<string, unknown>
): void {
  if (!ENABLED) return

  const payload: TelemetryEvent = {
    ts: new Date().toISOString(),
    level,
    event,
    message,
    data,
    version: APP_VERSION,
    session: SESSION_ID,
  }

  // Always log to console with structured prefix
  const prefix = `[SummitOS:${level.toUpperCase()}]`
  if (level === 'error') {
    console.error(prefix, event, payload)
  } else if (level === 'warn') {
    console.warn(prefix, event, payload)
  } else {
    console.info(prefix, event, payload)
  }

  // If a sink URL is configured (e.g. Azure Monitor / Application Insights),
  // fire-and-forget — never block the UI or throw on failure
  if (SINK_URL) {
    void fetch(SINK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {
      // Intentionally silent — telemetry must never crash the app
    })
  }
}

// ─── Public API ───────────────────────────────────────────────────────────────
export const telemetry = {
  info: (event: string, message?: string, data?: Record<string, unknown>) =>
    emit('info', event, message, data),

  warn: (event: string, message?: string, data?: Record<string, unknown>) =>
    emit('warn', event, message, data),

  error: (event: string, message?: string, data?: Record<string, unknown>) =>
    emit('error', event, message, data),

  /** Typed helper for known operational events */
  track: (event: EventName, data?: Record<string, unknown>) =>
    emit('info', event, undefined, data),
}

export default telemetry
