import DailyScorecard from './DailyScorecard'
import LuisBalanceWidget from './LuisBalanceWidget'
import BillCalendar from './BillCalendar'
import AnomalyPanel from './AnomalyPanel'
import TransactionTable from './TransactionTable'

interface PaymentTrackerPanelProps {
  selectedDate: string
  onAnomalyCountChange?: (count: number) => void
}

function PaymentTrackerPanel({ selectedDate, onAnomalyCountChange }: PaymentTrackerPanelProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DailyScorecard selectedDate={selectedDate} />
        <LuisBalanceWidget />
      </div>
      <BillCalendar />
      <AnomalyPanel onCountChange={onAnomalyCountChange} />
      <TransactionTable />
    </div>
  )
}

export default PaymentTrackerPanel
