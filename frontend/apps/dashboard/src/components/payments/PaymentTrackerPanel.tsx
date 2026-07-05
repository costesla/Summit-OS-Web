import DailyScorecard from './DailyScorecard'
import LuisSimpleCard from './LuisSimpleCard'
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
        <LuisSimpleCard />
      </div>
      <BillCalendar />
      <AnomalyPanel onCountChange={onAnomalyCountChange} />
      <TransactionTable />
    </div>
  )
}

export default PaymentTrackerPanel
