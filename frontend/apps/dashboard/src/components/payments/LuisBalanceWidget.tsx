import { useEffect, useState } from 'react'
import { fetchLuisBalance, type LuisBalance } from './api'

const TIER_DOT: Record<string, string> = {
  Full: 'bg-emerald-500',
  Rough: 'bg-amber-500',
  Missed: 'bg-[var(--accent-red)]',
  Underpayment: 'bg-[var(--accent-red)]',
  Review: 'bg-amber-500',
}

function LuisBalanceWidget() {
  const [data, setData] = useState<LuisBalance | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLuisBalance()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  const now = new Date()
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
  const historyByDate = new Map((data?.history || []).map((h) => [h.date, h]))

  let fullCount = 0
  let roughCount = 0
  let missedCount = 0

  const cells = Array.from({ length: daysInMonth }, (_, i) => {
    const day = i + 1
    const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    const entry = historyByDate.get(dateStr)
    const isFuture = new Date(dateStr) > now

    if (entry?.tier === 'Full') fullCount++
    if (entry?.tier === 'Rough') roughCount++
    if (entry?.tier === 'Missed' || entry?.tier === 'Underpayment') missedCount++

    return { day, entry, isFuture }
  })

  return (
    <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)]">
      <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider mb-4">Luis Canales Balance</h4>

      {loading ? (
        <p className="text-xs text-[var(--text-muted)]">Loading...</p>
      ) : (
        <>
          <div className="flex items-end gap-3 mb-4">
            <div>
              <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-0.5">Balance Owed</p>
              <h3 className="text-3xl font-black text-white font-mono">${(data?.current_balance ?? 0).toFixed(2)}</h3>
            </div>
            {data?.today && (
              <span className="mb-1 text-[10px] font-black uppercase tracking-widest text-[var(--accent-cyan)]">
                Today: {data.today.tier}
              </span>
            )}
          </div>

          <div className="grid grid-cols-7 gap-1.5 mb-3">
            {cells.map(({ day, entry, isFuture }) => (
              <div
                key={day}
                title={entry ? `${entry.tier} — $${entry.amount_sent.toFixed(2)}` : isFuture ? 'Upcoming' : 'No data'}
                className={`aspect-square rounded flex items-center justify-center text-[9px] font-bold ${
                  entry ? TIER_DOT[entry.tier] || 'bg-white/10' : isFuture ? 'bg-white/5' : 'bg-white/10'
                } ${entry ? 'text-black/70' : 'text-[#555]'}`}
              >
                {day}
              </div>
            ))}
          </div>

          <div className="flex justify-between text-[9px] font-bold uppercase tracking-widest pt-3 border-t border-white/5">
            <span className="text-emerald-400">{fullCount} Full</span>
            <span className="text-amber-400">{roughCount} Rough</span>
            <span className="text-[var(--accent-red)]">{missedCount} Missed</span>
          </div>
        </>
      )}
    </div>
  )
}

export default LuisBalanceWidget
