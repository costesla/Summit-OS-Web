import DailyScorecard from './DailyScorecard'
import BillCalendar from './BillCalendar'
import AnomalyPanel from './AnomalyPanel'
import TransactionTable from './TransactionTable'

interface PaymentTrackerPanelProps {
  selectedDate: string
  onAnomalyCountChange?: (count: number) => void
}

// LuisSimpleCard was removed here: Luis is manual-ledger-only, so his current
// balance comes from "Manual Ledger — Jackie & Luis" in the Expenses & Capital
// Ledger. The automatic Good/Bad day tally must not present an amount due.
// The remaining cards (scorecard, bills, anomalies, transactions) are not
// Luis-specific and are unaffected.
function PaymentTrackerPanel({ selectedDate, onAnomalyCountChange }: PaymentTrackerPanelProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4">
        <DailyScorecard selectedDate={selectedDate} />
      </div>
      <BillCalendar />
      <AnomalyPanel onCountChange={onAnomalyCountChange} />
      <TransactionTable />
    </div>
  )
}

export default PaymentTrackerPanel
