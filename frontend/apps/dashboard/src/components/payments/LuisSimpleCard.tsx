import { useEffect, useState } from 'react'
import { fetchLuisSummary, type LuisSimpleSummary } from './api'

const STATUS_COLOR: Record<string, string> = {
  Good: 'text-emerald-400',
  Bad: 'text-[var(--accent-red)]',
  Pending: 'text-[var(--text-muted)]',
}

function LuisSimpleCard() {
  const [data, setData] = useState<LuisSimpleSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLuisSummary()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  const monthLabel = data?.month
    ? new Date(`${data.month}-01T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    : ''

  return (
    <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)]">
      <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider mb-4">
        Luis Canales {monthLabel && `— ${monthLabel}`}
      </h4>

      {loading ? (
        <p className="text-xs text-[var(--text-muted)]">Loading...</p>
      ) : !data ? (
        <p className="text-xs text-[var(--text-muted)]">Unable to load.</p>
      ) : (
        <div className="space-y-1.5 text-sm font-mono">
          <p className="text-white">Days tracked: <span className="font-bold">{data.days_tracked}</span></p>
          <p className="text-emerald-400">Good days: <span className="font-bold">{data.good_count}</span></p>
          <p className="text-[var(--accent-red)]">Bad days: <span className="font-bold">{data.bad_count}</span></p>
          <p className={data.late_count > 0 ? 'text-amber-400' : 'text-[var(--text-muted)]'}>
            Late payments: <span className="font-bold">{data.late_count}</span>
          </p>
          <p className="text-white">Balance owed: <span className="font-bold">${data.balance_owed.toFixed(2)}</span></p>
          <p className={STATUS_COLOR[data.today_status.split(' ')[0]] || 'text-white'}>
            Today: <span className="font-bold">{data.today_status}</span>
          </p>
        </div>
      )}
    </div>
  )
}

export default LuisSimpleCard
