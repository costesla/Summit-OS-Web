/**
 * lib/api.ts — Centralised API client for SummitOS frontend
 *
 * Architecture note:
 *   The Next.js frontend is deployed as a **static export** to Azure Static Web Apps.
 *   Static exports do NOT execute Next.js API routes (/app/api/*) in production.
 *
 *   All API calls therefore go directly to the Azure Functions backend:
 *     https://summitos-api.azurewebsites.net/api/<endpoint>
 *
 *   AZURE_FUNCTION_URL  →  set in Azure SWA environment variables (no NEXT_PUBLIC_ prefix
 *                          because it is read server-side during build or passed via
 *                          NEXT_PUBLIC_AZURE_FUNCTION_URL for client-side static bundles)
 *
 *   AZURE_FUNCTION_KEY  →  set in Azure SWA environment variables (NEVER commit this)
 *
 * Local dev:
 *   Set NEXT_PUBLIC_AZURE_FUNCTION_URL=http://localhost:7071 in .env.local
 */

const BASE_URL = (
  process.env.NEXT_PUBLIC_AZURE_FUNCTION_URL ||
  process.env.AZURE_FUNCTION_URL ||
  "https://summitos-api.azurewebsites.net"
).replace(/\/$/, ""); // strip trailing slash

const FUNCTION_KEY =
  process.env.NEXT_PUBLIC_AZURE_FUNCTION_KEY ||
  process.env.AZURE_FUNCTION_KEY ||
  "";

/** Build standard request headers — injects function key if available */
function headers(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = {
    "Content-Type": "application/json",
    ...extra,
  };
  if (FUNCTION_KEY) {
    h["x-functions-key"] = FUNCTION_KEY;
  }
  return h;
}

/** Generic fetch wrapper with structured error handling */
async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}/api/${path.replace(/^\//, "")}`;

  const response = await fetch(url, {
    ...options,
    headers: headers(options.headers as Record<string, string>),
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.error || err.message || detail;
    } catch {
      // body wasn't JSON — use status text
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Typed API methods
// ─────────────────────────────────────────────────────────────────────────────

export interface CheckoutPayload {
  customerName: string;
  customerEmail: string;
  customerPhone: string;
  pickup: string;
  dropoff: string;
  appointmentStart: string;
  price: string;
  passengers: number;
  tripDistance?: string;
  tripDuration?: string;
  successUrl: string;
  cancelUrl: string;
}

export interface CheckoutResponse {
  id: string;
  url: string;
}

/** POST /api/create-checkout-session → Python Azure Function */
export async function createCheckoutSession(
  payload: CheckoutPayload
): Promise<CheckoutResponse> {
  return apiFetch<CheckoutResponse>("create-checkout-session", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────────────────

export interface BookPayload {
  name?: string;
  customerName?: string;
  email?: string;
  customerEmail?: string;
  phone?: string;
  customerPhone?: string;
  pickup: string;
  dropoff: string;
  price: string;
  pickupTime?: string;
  appointmentStart?: string;
  paymentMethod?: string;
  passengers?: number;
}

export interface BookResponse {
  success: boolean;
  message?: string;
  error?: string;
}

/** POST /api/book → Python Azure Function (receipt + calendar booking) */
export async function submitBooking(payload: BookPayload): Promise<BookResponse> {
  return apiFetch<BookResponse>("book", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────────────────

export interface CalendarAvailabilityResponse {
  success: boolean;
  slots: Array<{ start: string; end: string }>;
}

/** GET /api/calendar-availability?date=YYYY-MM-DD */
export async function getCalendarAvailability(
  date: string
): Promise<CalendarAvailabilityResponse> {
  return apiFetch<CalendarAvailabilityResponse>(
    `calendar-availability?date=${encodeURIComponent(date)}`
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export interface DailySyncResponse {
  success: boolean;
  message?: string;
  logs?: string[];
  error?: string;
}

/** POST /api/daily-sync → Python Azure Function */
export async function triggerDailySync(date?: string): Promise<DailySyncResponse> {
  return apiFetch<DailySyncResponse>("daily-sync", {
    method: "POST",
    body: JSON.stringify(date ? { date } : {}),
  });
}

// ─────────────────────────────────────────────────────────────────────────────

export interface PricingResponse {
  success: boolean;
  price?: string;
  breakdown?: Record<string, unknown>;
  error?: string;
}

/** GET /api/pricing?pickup=...&dropoff=... */
export async function getPricing(
  pickup: string,
  dropoff: string,
  passengers = 1
): Promise<PricingResponse> {
  const params = new URLSearchParams({
    pickup,
    dropoff,
    passengers: String(passengers),
  });
  return apiFetch<PricingResponse>(`pricing?${params}`);
}
