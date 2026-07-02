import { useEffect, useState, useCallback } from 'react'
import { Download } from 'lucide-react'
import { fetchTransactions, transactionsExportUrl, type Transaction, type TransactionFilters } from './api'

function TransactionTable() {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [account, setAccount] = useState('')
  const [category, setCategory] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [anomalyOnly, setAnomalyOnly] = useState(false)

  const filters: TransactionFilters = { account: account || undefined, category: category || undefined, from: from || undefined, to: to || undefined, anomaly: anomalyOnly }

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetchTransactions(filters)
      setTransactions(res.transactions)
    } catch {
      setTransactions([])
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, category, from, to, anomalyOnly])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)]">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider">Transactions</h4>
        <a
          href={transactionsExportUrl(filters)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-[10px] font-bold uppercase tracking-wider text-white transition-all"
        >
          <Download className="w-3 h-3" /> Export CSV
        </a>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <select value={account} onChange={(e) => setAccount(e.target.value)} className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white font-sans">
          <option value="">All Accounts</option>
          <option value="9776">...9776 (Business)</option>
          <option value="2085">...2085 (Personal)</option>
        </select>
        <input
          type="text"
          placeholder="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-[#555]"
        />
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white" />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white" />
        <label className="flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
          <input type="checkbox" checked={anomalyOnly} onChange={(e) => setAnomalyOnly(e.target.checked)} />
          Anomalies only
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[var(--text-muted)] uppercase tracking-widest text-[9px] border-b border-white/5">
              <th className="text-left py-2 pr-3">Date</th>
              <th className="text-left py-2 pr-3">Account</th>
              <th className="text-left py-2 pr-3">Counterparty</th>
              <th className="text-right py-2 pr-3">Amount</th>
              <th className="text-left py-2 pr-3">Direction</th>
              <th className="text-left py-2 pr-3">Category</th>
              <th className="text-left py-2">Anomaly</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="py-5 text-center text-[var(--text-muted)]">Loading...</td></tr>
            ) : transactions.length === 0 ? (
              <tr><td colSpan={7} className="py-5 text-center text-[#555] italic">No transactions match these filters.</td></tr>
            ) : (
              transactions.map((t) => (
                <tr key={t.payment_id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-1.5 pr-3 text-white">{t.date}</td>
                  <td className="py-1.5 pr-3 text-[var(--text-muted)]">...{t.account}</td>
                  <td className="py-1.5 pr-3 text-white truncate max-w-[180px]">{t.counterparty}</td>
                  <td className={`py-1.5 pr-3 text-right font-bold ${t.direction === 'inbound' ? 'text-emerald-400' : 'text-white'}`}>
                    ${t.amount.toFixed(2)}
                  </td>
                  <td className="py-1.5 pr-3 text-[var(--text-muted)] capitalize">{t.direction}</td>
                  <td className="py-1.5 pr-3 text-[var(--text-muted)]">{t.category}</td>
                  <td className="py-1.5">{t.anomaly_flag && <span className="text-[var(--accent-red)] font-bold">⚠</span>}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default TransactionTable
