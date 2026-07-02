import { useEffect, useState } from 'react'
import { fetchBillCalendar, type BillEntry } from './api'

const STATUS_STYLE: Record<BillEntry['status'], string> = {
  paid_on_time: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
  paid_variant: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
  overdue: 'bg-[var(--accent-red)]/10 border-[var(--accent-red)]/30 text-[var(--accent-red)]',
  upcoming: 'bg-white/5 border-white/10 text-[var(--text-muted)]',
}

const STATUS_LABEL: Record<BillEntry['status'], string> = {
  paid_on_time: 'Paid',
  paid_variant: 'Variant',
  overdue: 'Overdue',
  upcoming: 'Upcoming',
}

function BillCalendar() {
  const [obligations, setObligations] = useState<BillEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<BillEntry | null>(null)
  const month = new Date().toISOString().slice(0, 7)

  useEffect(() => {
    fetchBillCalendar(month)
      .then((res) => setObligations(res.obligations))
      .catch(() => setObligations([]))
      .finally(() => setLoading(false))
  }, [month])

  return (
    <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)]">
      <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider mb-4">Monthly Bill Calendar</h4>

      {loading ? (
        <p className="text-xs text-[var(--text-muted)]">Loading...</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {obligations.map((ob) => (
            <button
              key={`${ob.obligation_id}-${ob.expected_day}`}
              onClick={() => setSelected(ob)}
              className={`text-left p-2.5 rounded-lg border transition-all hover:brightness-110 ${STATUS_STYLE[ob.status]}`}
            >
              <p className="text-[10px] font-bold uppercase tracking-wider truncate">{ob.name}</p>
              <p className="text-[9px] opacity-80">Day {ob.expected_day} · ${ob.expected_amount.toFixed(2)}</p>
              <p className="text-[8px] font-black uppercase mt-0.5">{STATUS_LABEL[ob.status]}</p>
            </button>
          ))}
          {obligations.length === 0 && (
            <p className="text-xs text-[#555] italic col-span-full">No recurring obligations seeded yet.</p>
          )}
        </div>
      )}

      {selected && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
          onClick={() => setSelected(null)}
        >
          <div className="glass rounded-2xl p-6 max-w-sm w-full" onClick={(e) => e.stopPropagation()}>
            <h4 className="text-sm font-black text-white uppercase mb-4">{selected.name}</h4>
            <div className="space-y-2 text-xs text-[var(--text-muted)]">
              <p>Account: <span className="text-white font-bold">...{selected.account}</span></p>
              <p>Expected: <span className="text-white font-bold">${selected.expected_amount.toFixed(2)} on day {selected.expected_day}</span></p>
              <p>Status: <span className="font-bold">{STATUS_LABEL[selected.status]}</span></p>
              {selected.matched_amount != null && (
                <p>Matched: <span className="text-white font-bold">${selected.matched_amount.toFixed(2)} on {selected.matched_date}</span></p>
              )}
            </div>
            <button
              onClick={() => setSelected(null)}
              className="mt-6 w-full py-2 rounded-lg bg-white/5 hover:bg-white/10 text-xs font-bold uppercase tracking-widest text-white transition-all"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default BillCalendar
