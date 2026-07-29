import { useCallback, useEffect, useState } from 'react'
import { Loader2, Ban, Pencil, X, Check } from 'lucide-react'
import {
  createManualEntry,
  editManualEntry,
  fetchManualLedger,
  voidManualEntry,
  type ManualEntryType,
  type ManualLedgerEntry,
  type ManualLedgerPerson,
  type ManualPersonKey,
} from './api'

/**
 * Manual Ledger — Jackie & Luis.
 *
 * These two are manual-entry-only: no invoice, ride, missed-day or calendar
 * logic feeds these balances. The server is the sole authority — this panel
 * never computes a balance locally, so a failed write can't leave the screen
 * showing a number the database doesn't have.
 */

const PEOPLE: { key: ManualPersonKey; label: string }[] = [
  { key: 'JACKIE', label: 'Jackie' },
  { key: 'LUIS', label: 'Luis' },
]

const ENTRY_TYPES: ManualEntryType[] = ['Charge', 'Payment', 'Credit']

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/** Display-only formatting. The authoritative value stays a string from the API. */
function money(value: string | undefined): string {
  const parsed = Number(value ?? '0')
  if (Number.isNaN(parsed)) return String(value ?? '0.00')
  return parsed.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

function PersonPanel({
  label,
  person,
  onChanged,
}: {
  label: string
  person: ManualLedgerPerson | undefined
  onChanged: () => Promise<void>
}) {
  const personKey = person?.personKey ?? 'JACKIE'
  const [amount, setAmount] = useState('')
  const [entryType, setEntryType] = useState<ManualEntryType>('Charge')
  const [effectiveDate, setEffectiveDate] = useState(today())
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyEntryId, setBusyEntryId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editAmount, setEditAmount] = useState('')

  const balance = person?.balance ?? '0.00'
  const negative = Number(balance) < 0

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (pending) return // guard against double submit / double tap
    setError(null)
    setPending(true)
    try {
      await createManualEntry({
        personKey,
        entryType,
        amount: amount.trim(),
        effectiveDate,
        note: note.trim() || null,
        // Scopes the write so a retry (mobile flake, proxy retry) collapses
        // to one entry at the database rather than double-charging.
        idempotencyKey: newIdempotencyKey(),
      })
      setAmount('')
      setNote('')
      await onChanged() // re-read server truth; never patch the balance locally
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not log entry')
    } finally {
      setPending(false)
    }
  }

  const doVoid = async (entry: ManualLedgerEntry) => {
    if (busyEntryId) return
    setError(null)
    setBusyEntryId(entry.entryId)
    try {
      await voidManualEntry(entry.entryId, personKey)
      await onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not void entry')
    } finally {
      setBusyEntryId(null)
    }
  }

  const saveEdit = async (entry: ManualLedgerEntry) => {
    if (busyEntryId) return
    setError(null)
    setBusyEntryId(entry.entryId)
    try {
      await editManualEntry(entry.entryId, {
        personKey,
        entryType: entry.entryType,
        amount: editAmount.trim(),
        effectiveDate: entry.effectiveDate,
        note: entry.note,
      })
      setEditingId(null)
      await onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not edit entry')
    } finally {
      setBusyEntryId(null)
    }
  }

  const entries = person?.entries ?? []

  return (
    <div className="space-y-3 p-3 bg-white/[0.01] border border-white/5 rounded-xl">
      <div className="flex items-center justify-between">
        <h4 className="text-[11px] font-bold font-mono text-[var(--accent-purple)] uppercase tracking-wider">
          {label}
        </h4>
        <div className="text-right">
          <div className="text-[9px] font-mono text-[var(--text-muted)] uppercase">Balance</div>
          <div
            className={`text-lg font-black tabular-nums ${negative ? 'text-[var(--accent-cyan)]' : 'text-white'}`}
            data-testid={`manual-balance-${personKey}`}
          >
            {money(balance)}
          </div>
        </div>
      </div>

      {person && !person.activated && (
        <p className="text-[10px] text-amber-400 font-mono">
          Manual ledger not activated for {label} yet — run the migration activation step.
        </p>
      )}

      <form onSubmit={submit} className="space-y-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <div className="space-y-1">
            <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Amount ($)</span>
            <input
              type="number" step="0.01" min="0.01" inputMode="decimal" placeholder="0.00"
              value={amount} onChange={(e) => setAmount(e.target.value)} required
              className="w-full p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)]"
            />
          </div>
          <div className="space-y-1">
            <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Entry Type</span>
            <select
              value={entryType} onChange={(e) => setEntryType(e.target.value as ManualEntryType)}
              className="w-full p-2 bg-[var(--bg-surface)] border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)] font-sans"
            >
              {ENTRY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t === 'Charge' ? 'Charge (owes more)' : `${t} (owes less)`}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Date</span>
            <input
              type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} required
              className="w-full p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)]"
            />
          </div>
          <div className="space-y-1">
            <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Note</span>
            <input
              type="text" placeholder="Optional" maxLength={500}
              value={note} onChange={(e) => setNote(e.target.value)}
              className="w-full p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)]"
            />
          </div>
        </div>
        <button
          type="submit" disabled={pending || !amount.trim()}
          className="px-4 py-2 bg-[var(--accent-purple)] text-white rounded-xl text-xs font-black hover:opacity-90 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {pending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Log {label} Entry
        </button>
      </form>

      {error && (
        <p className="text-[10px] text-red-400 font-mono border border-red-500/20 bg-red-500/10 rounded-lg p-2">
          {error}
        </p>
      )}

      {entries.length > 0 && (
        <div className="space-y-1 pt-1">
          <div className="text-[9px] font-mono text-[var(--text-muted)] uppercase tracking-wider">Recent Entries</div>
          {entries.slice(0, 8).map((entry) => (
            <div
              key={entry.entryId}
              className={`flex items-center justify-between gap-2 text-[11px] p-2 rounded-lg border ${
                entry.voided
                  ? 'border-white/5 bg-white/[0.01] opacity-50'
                  : 'border-white/10 bg-white/[0.02]'
              }`}
            >
              <div className="min-w-0 flex-1">
                <span className={`font-mono font-bold ${entry.voided ? 'line-through' : ''}`}>
                  {entry.entryType === 'Charge' ? '+' : '−'}{money(entry.amount)}
                </span>
                <span className="text-[var(--text-muted)] ml-2">{entry.effectiveDate}</span>
                {entry.voided && <span className="ml-2 text-[9px] font-mono text-amber-400">VOIDED</span>}
                {entry.note && <div className="text-[10px] text-[var(--text-muted)] truncate">{entry.note}</div>}
              </div>

              {!entry.voided && (
                <div className="flex items-center gap-1 shrink-0">
                  {editingId === entry.entryId ? (
                    <>
                      <input
                        type="number" step="0.01" min="0.01" value={editAmount}
                        onChange={(e) => setEditAmount(e.target.value)}
                        className="w-20 p-1 bg-white/5 border border-white/10 rounded text-[11px] text-white"
                      />
                      <button
                        type="button" onClick={() => saveEdit(entry)} disabled={busyEntryId === entry.entryId}
                        className="p-1 rounded hover:bg-white/10 text-emerald-400 disabled:opacity-50" title="Save"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button" onClick={() => setEditingId(null)}
                        className="p-1 rounded hover:bg-white/10 text-[var(--text-muted)]" title="Cancel"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => { setEditingId(entry.entryId); setEditAmount(entry.amount) }}
                        className="p-1 rounded hover:bg-white/10 text-[var(--text-muted)] hover:text-white" title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button" onClick={() => doVoid(entry)} disabled={busyEntryId === entry.entryId}
                        className="p-1 rounded hover:bg-white/10 text-[var(--text-muted)] hover:text-amber-400 disabled:opacity-50"
                        title="Void (kept for audit)"
                      >
                        {busyEntryId === entry.entryId
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Ban className="w-3.5 h-3.5" />}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ManualLedgerPanel() {
  const [people, setPeople] = useState<Record<string, ManualLedgerPerson>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchManualLedger()
      setPeople(data.people || {})
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Could not load manual ledger')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  return (
    <div className="space-y-3 p-4 bg-white/[0.02] border border-white/10 rounded-2xl">
      <div className="flex items-center justify-between">
        <h4 className="text-[11px] font-bold font-mono text-[var(--accent-purple)] uppercase tracking-wider">
          Manual Ledger — Jackie &amp; Luis
        </h4>
        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--text-muted)]" />}
      </div>
      <p className="text-[10px] text-[var(--text-muted)] font-mono">
        Manual entries only — no automatic accrual, invoice, or missed-day logic feeds these balances.
      </p>

      {loadError && (
        <p className="text-[10px] text-red-400 font-mono border border-red-500/20 bg-red-500/10 rounded-lg p-2">
          {loadError}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {PEOPLE.map(({ key, label }) => (
          <PersonPanel key={key} label={label} person={people[key]} onChanged={load} />
        ))}
      </div>
    </div>
  )
}

export default ManualLedgerPanel
