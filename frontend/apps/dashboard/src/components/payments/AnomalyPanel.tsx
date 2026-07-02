import { useEffect, useState, useCallback } from 'react'
import { AlertTriangle, Check, Loader2 } from 'lucide-react'
import { fetchAnomalies, resolveAnomaly, type Transaction } from './api'

interface AnomalyPanelProps {
  onCountChange?: (count: number) => void
}

function AnomalyPanel({ onCountChange }: AnomalyPanelProps) {
  const [anomalies, setAnomalies] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [resolvingId, setResolvingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetchAnomalies()
      setAnomalies(res.anomalies)
      onCountChange?.(res.count)
    } catch {
      setAnomalies([])
    } finally {
      setLoading(false)
    }
  }, [onCountChange])

  useEffect(() => {
    load()
  }, [load])

  const handleResolve = async (paymentId: string) => {
    try {
      setResolvingId(paymentId)
      await resolveAnomaly(paymentId)
      await load()
    } finally {
      setResolvingId(null)
    }
  }

  return (
    <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)]">
      <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider mb-4 flex items-center gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" /> Anomaly Flags
      </h4>

      {loading ? (
        <p className="text-xs text-[var(--text-muted)]">Loading...</p>
      ) : anomalies.length === 0 ? (
        <p className="text-xs text-[#555] italic">No open flags.</p>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {anomalies.map((a) => (
            <div key={a.payment_id} className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-[var(--accent-red)]/5 border border-[var(--accent-red)]/20">
              <div className="min-w-0">
                <p className="text-[11px] font-bold text-white truncate">{a.counterparty || 'Unknown'} — ${a.amount.toFixed(2)}</p>
                <p className="text-[9px] text-[var(--text-muted)]">{a.date} · {a.account}</p>
                <p className="text-[9px] text-[var(--accent-red)] mt-0.5">{a.anomaly_reason}</p>
              </div>
              <button
                onClick={() => handleResolve(a.payment_id)}
                disabled={resolvingId === a.payment_id}
                className="shrink-0 p-1.5 rounded-lg bg-white/5 hover:bg-emerald-500/20 hover:text-emerald-400 text-[var(--text-muted)] transition-all"
                title="Mark resolved"
              >
                {resolvingId === a.payment_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default AnomalyPanel
