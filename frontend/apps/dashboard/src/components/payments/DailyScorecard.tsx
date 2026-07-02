import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Zap, Utensils, DollarSign, Loader2 } from 'lucide-react'
import { fetchScorecard, triggerSync, type Scorecard } from './api'

const TIER_COLOR: Record<string, string> = {
  Full: 'text-emerald-400',
  Rough: 'text-amber-400',
  Missed: 'text-[var(--accent-red)]',
  Underpayment: 'text-[var(--accent-red)]',
  Review: 'text-amber-400',
  Pending: 'text-[var(--text-muted)]',
}

function ProgressBar({ label, actual, target, invert, icon: Icon }: {
  label: string
  actual: number
  target: number
  invert?: boolean
  icon: typeof Zap
}) {
  const pct = target > 0 ? Math.min((actual / target) * 100, 100) : 0
  const over = invert && actual > target
  const barColor = over ? 'bg-[var(--accent-red)]' : 'bg-[var(--accent-cyan)]'

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest flex items-center gap-1.5">
          <Icon className="w-3.5 h-3.5" /> {label}
        </span>
        <span className={`text-xs font-black ${over ? 'text-[var(--accent-red)]' : 'text-white'}`}>
          ${actual.toFixed(2)} <span className="text-[var(--text-muted)] font-medium">/ ${target.toFixed(2)}</span>
        </span>
      </div>
      <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function DailyScorecard({ selectedDate }: { selectedDate: string }) {
  const [data, setData] = useState<Scorecard | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [lastSync, setLastSync] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const result = await fetchScorecard(selectedDate)
      setData(result)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scorecard')
    } finally {
      setLoading(false)
    }
  }, [selectedDate])

  useEffect(() => {
    load()
  }, [load])

  const handleSync = async () => {
    try {
      setSyncing(true)
      await triggerSync()
      setLastSync(new Date().toLocaleTimeString())
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)]">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider">Daily Scorecard</h4>
          <p className="text-[9px] text-[#606060] mt-0.5">{lastSync ? `Last synced ${lastSync}` : 'Not synced this session'}</p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--accent-cyan)]/20 bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)] hover:bg-[var(--accent-cyan)]/20 text-[10px] font-bold uppercase tracking-wider transition-all"
        >
          {syncing ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          {syncing ? 'Syncing' : 'Sync Now'}
        </button>
      </div>

      {loading && !data ? (
        <p className="text-xs text-[var(--text-muted)]">Loading...</p>
      ) : data ? (
        <div className="space-y-4">
          <ProgressBar label="Gross Earnings" actual={data.gross_earnings.actual} target={data.gross_earnings.target} icon={DollarSign} />
          <ProgressBar label="Supercharging" actual={data.supercharging.actual} target={data.supercharging.target} invert icon={Zap} />
          <ProgressBar label="Food & Dining" actual={data.food_dining.actual} target={data.food_dining.target} invert icon={Utensils} />

          <div className="pt-3 border-t border-white/5 flex justify-between items-center">
            <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Luis Canales — Today</span>
            <span className={`text-xs font-black uppercase ${TIER_COLOR[data.luis_tier] || 'text-white'}`}>
              {data.luis_tier}
            </span>
          </div>
        </div>
      ) : null}

      {error && <p className="mt-3 text-[10px] text-[var(--accent-red)]">{error}</p>}
    </div>
  )
}

export default DailyScorecard
