import { apiGet, apiPost, BASE_URL, API_FUNCTION_KEY } from '../../lib/apiClient'

export interface ScorecardMetric {
  actual: number
  target: number
}

export interface Scorecard {
  date: string
  gross_earnings: ScorecardMetric
  supercharging: ScorecardMetric
  food_dining: ScorecardMetric
  luis_tier: string
  luis_balance: number
}

export interface LuisLogEntry {
  date: string
  amount_sent: number
  expected_amount: number
  tier: string
  deferred_amount: number
  running_balance: number
  notes: string | null
}

export interface LuisBalance {
  current_balance: number
  today: LuisLogEntry | null
  history: LuisLogEntry[]
}

export interface BillEntry {
  obligation_id: string
  name: string
  account: string
  expected_day: number
  expected_amount: number
  expected_date: string
  status: 'paid_on_time' | 'paid_variant' | 'overdue' | 'upcoming'
  matched_amount: number | null
  matched_date: string | null
}

export interface Transaction {
  payment_id: string
  date: string
  account: string
  direction: 'inbound' | 'outbound'
  counterparty: string
  amount: number
  category: string
  subcategory: string | null
  recurring_flag: boolean
  anomaly_flag: boolean
  anomaly_reason: string | null
  notes: string | null
}

export interface TransactionFilters {
  account?: string
  category?: string
  from?: string
  to?: string
  anomaly?: boolean
}

function toSearchParams(params: TransactionFilters): URLSearchParams {
  const search = new URLSearchParams()
  if (params.account) search.set('account', params.account)
  if (params.category) search.set('category', params.category)
  if (params.from) search.set('from', params.from)
  if (params.to) search.set('to', params.to)
  if (params.anomaly) search.set('anomaly', 'true')
  return search
}

export const fetchScorecard = (date: string) =>
  apiGet<Scorecard>(`/financials/payments/scorecard?date=${date}`)

export const fetchLuisBalance = () =>
  apiGet<LuisBalance>(`/financials/payments/luis/balance`)

export interface LuisSimpleSummary {
  month: string
  days_tracked: number
  good_count: number
  bad_count: number
  late_count: number
  balance_owed: number
  today_status: string
}

export const fetchLuisSummary = (month?: string) =>
  apiGet<LuisSimpleSummary>(`/financials/luis${month ? `?month=${month}` : ''}`)

export const fetchBillCalendar = (month: string) =>
  apiGet<{ month: string; obligations: BillEntry[] }>(`/financials/payments/bills/calendar?month=${month}`)

export const fetchAnomalies = () =>
  apiGet<{ count: number; anomalies: Transaction[] }>(`/financials/payments/anomalies`)

export const fetchTransactions = (params: TransactionFilters) =>
  apiGet<{ transactions: Transaction[] }>(`/financials/payments/transactions?${toSearchParams(params).toString()}`)

export const triggerSync = () =>
  apiPost<{ success: boolean; transactions_saved?: number; errors?: string[] }>(`/financials/payments/sync`, {})

export const resolveAnomaly = (paymentId: string, resolutionNote?: string) =>
  apiPost<{ success: boolean }>(`/financials/payments/anomaly/resolve`, {
    payment_id: paymentId,
    resolution_note: resolutionNote,
  })

export const reassignLuisPayment = (paymentId: string, targetDate: string) =>
  apiPost<{ success: boolean; error?: string; original_date?: string; target_date?: string }>(
    `/financials/payments/luis/reassign`,
    { payment_id: paymentId, target_date: targetDate },
  )

// ── Manual Ledger (Jackie & Luis) ────────────────────────────────────────────
// Amounts are strings end-to-end: a JSON number would be parsed as a float and
// could round a cent before the server ever sees it.

export type ManualPersonKey = 'JACKIE' | 'LUIS'
export type ManualEntryType = 'Charge' | 'Payment' | 'Credit'

export interface ManualLedgerEntry {
  entryId: string
  personKey: ManualPersonKey
  entryType: ManualEntryType
  amount: string
  effectiveDate: string
  note: string | null
  voided: boolean
  revisionNumber: number
}

export interface ManualLedgerPerson {
  personKey: ManualPersonKey
  activated: boolean
  openingBalance: string
  balance: string
  entries: ManualLedgerEntry[]
}

export interface ManualLedgerResponse {
  people: Record<string, ManualLedgerPerson>
}

export interface ManualEntryInput {
  personKey: ManualPersonKey
  entryType: ManualEntryType
  amount: string
  effectiveDate: string
  note?: string | null
  idempotencyKey?: string
}

/** `asOf` returns the closing balance for that date rather than the running
 *  total, so the panel can agree with the date-scoped Balance Sheet header. */
export const fetchManualLedger = (asOf?: string) =>
  apiGet<ManualLedgerResponse>(
    asOf ? `/financials/manual-ledger?asOf=${encodeURIComponent(asOf)}` : '/financials/manual-ledger',
  )

export const createManualEntry = (input: ManualEntryInput) =>
  apiPost<{ success: boolean; entry: ManualLedgerEntry; balance: string }>(
    '/financials/manual-ledger/entry',
    input,
  )

export const editManualEntry = (entryId: string, input: ManualEntryInput) =>
  apiPost<{ success: boolean; entry_id: string; balance: string }>(
    `/financials/manual-ledger/entry/${encodeURIComponent(entryId)}/edit`,
    input,
  )

export const voidManualEntry = (entryId: string, personKey: ManualPersonKey, reason?: string) =>
  apiPost<{ success: boolean; voided: boolean; balance?: string }>(
    `/financials/manual-ledger/entry/${encodeURIComponent(entryId)}/void`,
    { personKey, reason },
  )

export const transactionsExportUrl = (params: TransactionFilters) => {
  const search = toSearchParams(params)
  // A plain <a href> download can't send headers, so the function key goes
  // in the `code` query param, which require_function_key also accepts.
  if (API_FUNCTION_KEY) search.set('code', API_FUNCTION_KEY)
  return `${BASE_URL}/financials/payments/transactions/export?${search.toString()}`
}
