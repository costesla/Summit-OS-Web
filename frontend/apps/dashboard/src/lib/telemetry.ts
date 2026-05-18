/**
 * SummitOS Dashboard — Telemetry Module (spec-compliant entry point)
 *
 * Exports the exact function signatures specified in the Phase 3 contract:
 *   logEvent(name, props)
 *   logError(error, context)
 *   logTiming(name, ms, props)
 *
 * Also re-exports the full telemetry object and EVENTS vocabulary
 * for use throughout the application.
 *
 * Env vars (Vite-safe, no secrets):
 *   VITE_TELEMETRY_ENABLED   — set to "false" to silence
 *   VITE_TELEMETRY_SINK_URL  — optional remote sink (e.g. Azure Monitor)
 */

// ─── Config ───────────────────────────────────────────────────────────────────
const ENABLED = import.meta.env.VITE_TELEMETRY_ENABLED !== 'false'
const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? 'unknown'
const SINK_URL: string | null = import.meta.env.VITE_TELEMETRY_SINK_URL ?? null

// ─── Session ID (tab-scoped, no PII) ─────────────────────────────────────────
const SESSION_ID = Math.random().toString(36).slice(2, 10)

// ─── Types ────────────────────────────────────────────────────────────────────
type Level = 'info' | 'warn' | 'error'

interface TelemetryPayload {
  ts: string
  level: Level
  event: string
  props?: Record<string, unknown>
  version: string
  session: string
}

// ─── Operational Event Vocabulary ─────────────────────────────────────────────
// These names are the formal contract between the dashboard and SummitOS Intelligence.
// Aligned to WORKFLOW.md step names.
export const EVENTS = {
  // App lifecycle
  APP_INIT:                 'app_init',
  PAGE_VIEW:                'page_view',
  WORKFLOW_READY:           'workflow_ready',         // ← spec required

  // Daily sync pipeline
  SYNC_STARTED:             'sync_started',
  SYNC_COMPLETED:           'sync_completed',
  SYNC_FAILED:              'sync_failed',
  SYNC_REQUESTED:           'sync_requested',         // ← spec required

  // Tessie
  TESSIE_TAGS_CONFIRMED:    'tessie_tags_confirmed',  // ← spec required (tessie_tagging_confirmed also aliased)
  TESSIE_TAGGING_CONFIRMED: 'tessie_tagging_confirmed',
  TESSIE_DRIVES_LOADED:     'tessie_drives_loaded',
  TESSIE_DRIVE_IMPORTED:    'tessie_drive_imported',

  // Screenshots / OCR
  UBER_CARDS_UPLOADED:        'uber_cards_uploaded',
  SCREENSHOT_MATCH_STARTED:   'screenshot_match_started',
  SCREENSHOT_MATCH_COMPLETED: 'screenshot_match_completed',
  SCREENSHOT_NO_MATCH:        'screenshot_no_match',

  // Expenses
  MANUAL_EXPENSE_ADDED: 'manual_expense_added',
  EXPENSE_DELETED:      'expense_deleted',

  // API
  API_REQUEST_FAILED:   'api_request_failed',        // ← spec required
  API_CALL_STARTED:     'api_call_started',
  API_CALL_COMPLETED:   'api_call_completed',
  API_FAILURE:          'api_failure',

  // Errors
  JS_ERROR:            'js_error',
  UNHANDLED_REJECTION: 'unhandled_rejection',
} as const

export type EventName = typeof EVENTS[keyof typeof EVENTS]

// ─── Core emit ────────────────────────────────────────────────────────────────
function emit(
  level: Level,
  event: string,
  props?: Record<string, unknown>,
): void {
  if (!ENABLED) return

  const payload: TelemetryPayload = {
    ts: new Date().toISOString(),
    level,
    event,
    props,
    version: APP_VERSION,
    session: SESSION_ID,
  }

  const prefix = `[SummitOS:${level.toUpperCase()}]`
  if (level === 'error') {
    console.error(prefix, event, payload)
  } else if (level === 'warn') {
    console.warn(prefix, event, payload)
  } else {
    console.info(prefix, event, payload)
  }

  if (SINK_URL) {
    void fetch(SINK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => { /* intentional — telemetry must never crash the app */ })
  }
}

// ─── Public API — Phase 3 spec-required function signatures ──────────────────

/**
 * Log a named operational event with optional properties.
 * @example logEvent('sync_started', { date: '2026-05-18' })
 */
export function logEvent(name: string, props?: Record<string, unknown>): void {
  emit('info', name, props)
}

/**
 * Log an error with structured context.
 * @example logError(new Error('timeout'), { endpoint: '/api/sync' })
 */
export function logError(error: unknown, context?: Record<string, unknown>): void {
  const message = error instanceof Error ? error.message : String(error)
  const stack = error instanceof Error ? error.stack : undefined
  emit('error', 'js_error', { message, stack, ...context })
}

/**
 * Log a timing measurement (e.g. API response time).
 * @example logTiming('api_response', 342, { endpoint: '/daily-sync' })
 */
export function logTiming(name: string, ms: number, props?: Record<string, unknown>): void {
  emit('info', name, { durationMs: ms, ...props })
}

// ─── Extended API — typed helpers ────────────────────────────────────────────
export const telemetry = {
  info:  (event: string, message?: string, data?: Record<string, unknown>) =>
    emit('info',  event, { message, ...data }),
  warn:  (event: string, message?: string, data?: Record<string, unknown>) =>
    emit('warn',  event, { message, ...data }),
  error: (event: string, message?: string, data?: Record<string, unknown>) =>
    emit('error', event, { message, ...data }),
  track: (event: EventName, data?: Record<string, unknown>) =>
    emit('info', event, data),

  // Convenience: spec function names as methods
  logEvent,
  logError,
  logTiming,
}

export default telemetry
