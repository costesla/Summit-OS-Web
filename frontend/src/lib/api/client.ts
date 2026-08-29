/**
 * SummitOS API Client
 *
 * Centralizes base URL, timeout, retries, and error normalization.
 * All dashboard API calls should go through this client so that:
 *  - Base URL changes in one place (VITE_API_BASE_URL env var)
 *  - Timeouts are consistent and observable
 *  - Failures emit telemetry events automatically
 */
import telemetry, { EVENTS } from '../telemetry'

// ─── Config ───────────────────────────────────────────────────────────────────
// Supports both the spec-required VITE_PUBLIC_API_BASE_URL and the
// existing VITE_API_BASE_URL (for backward compatibility with current Azure config).
export const BASE_URL =
  import.meta.env.VITE_PUBLIC_API_BASE_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  'https://summitos-api.azurewebsites.net/api'

const DEFAULT_TIMEOUT_MS = 15_000
const DEFAULT_RETRIES = 1

// Azure Function host key, injected at build time (VITE_API_FUNCTION_KEY
// GitHub Actions secret). The backend's require_function_key guard rejects
// requests without it. Sent on every call — routes that don't enforce it
// simply ignore the header.
export const API_FUNCTION_KEY: string | undefined = import.meta.env.VITE_API_FUNCTION_KEY || undefined

// ─── Error type ───────────────────────────────────────────────────────────────
export class ApiError extends Error {
  readonly status: number
  readonly endpoint: string

  constructor(status: number, message: string, endpoint: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.endpoint = endpoint
  }
}

// ─── Core fetch wrapper ───────────────────────────────────────────────────────
interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  body?: unknown
  timeoutMs?: number
  retries?: number
  /** Cache-bust (adds ?t= param) — default true for GET */
  cacheBust?: boolean
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = 'GET',
    body,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    retries = DEFAULT_RETRIES,
    cacheBust = method === 'GET',
  } = options

  const url = new URL(`${BASE_URL}${endpoint}`)
  if (cacheBust) url.searchParams.set('t', String(Date.now()))

  const startMs = Date.now()
  telemetry.track(EVENTS.API_CALL_STARTED, { endpoint, method })

  let lastError: unknown
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const headers: Record<string, string> = {}
      if (body) headers['Content-Type'] = 'application/json'
      if (API_FUNCTION_KEY) headers['x-functions-key'] = API_FUNCTION_KEY

      const resp = await fetch(url.toString(), {
        method,
        headers: Object.keys(headers).length ? headers : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(timeoutMs),
        cache: 'no-store',
      })

      const durationMs = Date.now() - startMs

      if (!resp.ok) {
        const text = await resp.text().catch(() => '')
        const err = new ApiError(resp.status, text || resp.statusText, endpoint)
        telemetry.error(EVENTS.API_FAILURE, err.message, {
          endpoint,
          status: resp.status,
          durationMs,
          attempt,
        })
        throw err
      }

      const data = (await resp.json()) as T
      telemetry.track(EVENTS.API_CALL_COMPLETED, { endpoint, method, durationMs, attempt })
      return data
    } catch (err) {
      lastError = err
      if (err instanceof ApiError) throw err // don't retry HTTP errors
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, 500 * (attempt + 1)))
      }
    }
  }

  const durationMs = Date.now() - startMs
  const message = lastError instanceof Error ? lastError.message : String(lastError)
  telemetry.error(EVENTS.API_FAILURE, message, { endpoint, method, durationMs })
  throw lastError
}

// ─── Convenience wrappers ─────────────────────────────────────────────────────
export const apiGet = <T>(endpoint: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
  apiRequest<T>(endpoint, { ...opts, method: 'GET' })

export const apiPost = <T>(endpoint: string, body: unknown, opts?: Omit<RequestOptions, 'method'>) =>
  apiRequest<T>(endpoint, { ...opts, method: 'POST', body })
