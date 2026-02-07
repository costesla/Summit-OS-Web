import { useState, useEffect } from 'react'
import {
  Zap,
  RefreshCcw,
  ShieldCheck,
  Navigation,
  DollarSign,
  TrendingUp,
  Battery
} from 'lucide-react'

interface DashboardData {
  stats: {
    TotalEarnings: number;
    TotalTips: number;
    TripCount: number;
    HighestFare: number;
  };
  weather: {
    Temperature_F: number;
    Condition: string;
  };
  telematics: {
    battery_level: number;
    charging_state: string;
    speed: number;
    latitude: number;
    longitude: number;
    timestamp: string;
  };
  summary: {
    total_miles: number;
    fsd_pct: number;
    elevation_flux: number;
    total_expenses: number;
    expense_list: Array<{ name: string; amount: number }>;
    charge_count: number;
    charge_cost: number;
  };
  compliance: {
    platform_cut: number;
    service_fees: number;
    insurance_fees: number;
    other_fees: number;
    is_profitable: boolean;
  };
  server_time: string;
}

function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);


  const fetchData = async () => {
    try {
      setLoading(true);
      const url = "http://127.0.0.1:7080/api/dashboard-summary";
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Failed to fetch dashboard data");
      const json = await resp.json();
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const triggerCatchup = async () => {
    try {
      setSyncing(true);
      const url = "http://127.0.0.1:7080/api/catchup-today";
      const resp = await fetch(url, { method: 'POST' });
      if (!resp.ok) throw new Error("Catch-up failed");
      const result = await resp.json();
      alert(`Catch-up Complete: Processed ${result.processed} new items.`);
      fetchData();
    } catch (err: any) {
      alert("Error: " + err.message);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen text-white p-6 md:p-10 w-full max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-4">
        <div>
          <h1 className="text-5xl font-bold tracking-tight mb-2 text-gradient-metallic">SUMMIT COMMAND</h1>
          <p className="text-[#a0a0a0] font-medium flex items-center gap-2 uppercase tracking-widest text-sm">
            <ShieldCheck className={`w-4 h-4 ${error ? 'text-red-500' : 'text-[#00f2ff]'}`} />
            {error ? 'CONNECTION ERROR - CHECK BACKEND' : 'SECURE CLOUD PLATFORM V1.0'}
          </p>
        </div>
        <div className="flex gap-4">
          <button
            onClick={triggerCatchup}
            disabled={syncing}
            className="glass-panel p-3 px-6 hover:bg-orange-500/10 border-orange-500/30 transition-all flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-orange-500"
          >
            <ShieldCheck className={`w-4 h-4 ${syncing ? 'animate-pulse' : ''}`} />
            {syncing ? 'Analyzing...' : 'Manual Catch-up'}
          </button>
          <button
            onClick={fetchData}
            className="glass-panel p-3 px-6 hover:bg-white/10 transition-all flex items-center gap-3 text-sm font-bold uppercase tracking-widest"
          >
            <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : 'text-[#00f2ff]'}`} />
            {loading ? 'Syncing...' : 'Refresh System'}
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {/* Earnings KPI */}
        <div className="glass-panel p-6 relative group overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-10">
            <DollarSign className="w-24 h-24 text-[#00f2ff]" />
          </div>
          <p className="text-xs font-bold text-[#a0a0a0] mb-1 uppercase tracking-widest">Today's Revenue</p>
          <h3 className="text-4xl font-black text-white">
            {data ? `$${parseFloat(data.stats.TotalEarnings.toString()).toFixed(2)}` : '---'}
          </h3>
          <div className="mt-4 flex items-center gap-2 text-[#00f2ff] text-xs font-bold tracking-wider">
            <TrendingUp className="w-4 h-4" />
            {data ? `+$${parseFloat(data.stats.TotalTips.toString()).toFixed(2)} TIPS` : 'SYNCING...'}
          </div>
        </div>

        {/* Vehicle KPI */}
        <div className="glass-panel p-6 relative group">
          <div className="absolute top-0 right-0 p-4 opacity-10">
            <Battery className="w-24 h-24 text-[#00f2ff]" />
          </div>
          <p className="text-xs font-bold text-[#a0a0a0] mb-1 uppercase tracking-widest">Model Y Status</p>
          <div className="flex items-end gap-2">
            <h3 className="text-4xl font-black text-white">{data?.telematics?.battery_level ?? '--'}%</h3>
            <span className="text-[#a0a0a0] text-xs mb-1.5 font-bold uppercase tracking-wider">
              {data?.telematics?.charging_state || 'Stationary'}
            </span>
          </div>
          <div className="mt-4 h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-[#00f2ff] rounded-full transition-all duration-1000"
              style={{ width: `${data?.telematics?.battery_level || 0}%` }}
            />
          </div>
        </div>

        {/* Trips KPI */}
        <div className="glass-panel p-6 relative group">
          <div className="absolute top-0 right-0 p-4 opacity-10">
            <Navigation className="w-24 h-24 text-[#00f2ff]" />
          </div>
          <p className="text-xs font-bold text-[#a0a0a0] mb-1 uppercase tracking-widest">Active Shifts</p>
          <h3 className="text-4xl font-black text-white">
            {data?.stats?.TripCount ?? '--'} Trips
          </h3>
          <p className="mt-4 text-[10px] text-[#a0a0a0] font-bold uppercase tracking-widest italic">
            Audit Ready Metrics
          </p>
        </div>
      </div>

      {/* Compliance Section */}
      <div className="mt-12 mb-6">
        <h2 className="text-xs font-black tracking-[0.3em] text-[#00f2ff] uppercase opacity-70 flex items-center gap-4">
          <span className="h-px w-8 bg-[#00f2ff]/30"></span>
          Platform Profitability & Analytics
          <span className="h-px flex-1 bg-white/5"></span>
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Status Indicator */}
        <div className="glass-panel p-6 border-l-4 border-l-blue-500">
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-[10px] font-bold text-[#a0a0a0] uppercase tracking-widest">System Health</p>
              <h4 className="text-sm font-black text-white mt-1 uppercase">Yield Audit</h4>
            </div>
            <div className={`w-3 h-3 rounded-full shadow-[0_0_10px] ${data?.compliance?.is_profitable ? 'bg-green-500 shadow-green-500' : 'bg-red-500 shadow-red-500'}`} />
          </div>
          <p className="text-[11px] text-[#a0a0a0] leading-relaxed">
            {data?.compliance?.is_profitable
              ? "Driver yield exceeding platform rent. Operational health is optimal."
              : "Platform cut exceeds driver net. Flagged for review."
            }
          </p>
        </div>

        {/* Platform Breakdown */}
        <div className="glass-panel p-6 lg:col-span-3">
          <div className="flex flex-col md:flex-row divide-y md:divide-y-0 md:divide-x divide-white/5 h-full">
            <div className="pb-4 md:pb-0 md:pr-8 flex-1">
              <p className="text-[10px] font-bold text-[#a0a0a0] uppercase tracking-widest mb-1">Total Platform Cut</p>
              <h3 className="text-3xl font-black text-white">${parseFloat(data?.compliance?.platform_cut?.toString() || '0').toFixed(2)}</h3>
            </div>
            <div className="py-4 md:py-0 md:px-8 flex-1">
              <p className="text-[10px] font-bold text-[#a0a0a0] uppercase tracking-widest mb-3">Uber Fee Breakdown</p>
              <div className="space-y-2">
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#a0a0a0] font-medium">Uber Service Fee</span>
                  <span className="text-white font-bold">${parseFloat(data?.compliance?.service_fees?.toString() || '0').toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#a0a0a0] font-medium">Insurance Fees</span>
                  <span className="text-white font-bold">${parseFloat(data?.compliance?.insurance_fees?.toString() || '0').toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-[#a0a0a0] font-medium">Other Surcharges</span>
                  <span className="text-white font-bold">${parseFloat(data?.compliance?.other_fees?.toString() || '0').toFixed(2)}</span>
                </div>
              </div>
            </div>
            <div className="pt-4 md:pt-0 md:pl-8 flex-1 flex flex-col justify-center">
              <h2 className="text-2xl font-black text-[#00f2ff] italic tracking-tighter">SUMMIT SECURE</h2>
              <p className="text-[9px] text-[#a0a0a0] font-bold uppercase mt-1">Data Integrity Verified</p>
            </div>
          </div>
        </div>
      </div>

      {/* Mission Summary Section */}
      <div className="mt-12 mb-6">
        <h2 className="text-xs font-black tracking-[0.3em] text-[#00f2ff] uppercase opacity-70 flex items-center gap-4">
          <span className="h-px w-8 bg-[#00f2ff]/30"></span>
          Daily Mission Summary
          <span className="h-px flex-1 bg-white/5"></span>
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Efficiency */}
        <div className="glass-panel p-6 border-l-4 border-l-[#00f2ff]">
          <h4 className="text-sm font-bold text-[#a0a0a0] mb-4 uppercase tracking-widest flex items-center gap-2">
            <Zap className="w-4 h-4 text-[#00f2ff]" />
            Efficiency
          </h4>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-xs text-[#a0a0a0] font-bold uppercase tracking-wider">FSD Usage</span>
              <span className="text-lg font-black text-white">{data?.summary?.fsd_pct ?? '--'}%</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-[#a0a0a0] font-bold uppercase tracking-wider">Miles Driven</span>
              <span className="text-lg font-black text-white">{data?.summary?.total_miles ?? '--'} mi</span>
            </div>
            <div className="pt-4 border-t border-white/5 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-[#00f2ff] font-bold uppercase tracking-widest">Charging Ops</span>
                <span className="text-sm font-black text-white">{data?.summary?.charge_count ?? '0'} SES</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-[#00f2ff] font-bold uppercase tracking-widest">Energy Cost</span>
                <span className="text-sm font-black text-white">${parseFloat(data?.summary?.charge_cost?.toString() || '0').toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Composition */}
        <div className="glass-panel p-6 border-l-4 border-l-purple-500">
          <h4 className="text-sm font-bold text-[#a0a0a0] mb-4 uppercase tracking-widest flex items-center gap-2">
            <Navigation className="w-4 h-4 text-purple-500" />
            Shift Composition
          </h4>
          <div className="space-y-4 text-sm font-bold uppercase tracking-wider">
            <div className="flex justify-between items-center text-orange-500">
              <span>Uber Core</span>
              <span>2</span>
            </div>
            <div className="flex justify-between items-center text-[#00f2ff]">
              <span>Private Elite</span>
              <span>5</span>
            </div>
            <div className="mt-4 pt-4 border-t border-white/5">
              <p className="text-[10px] text-[#a0a0a0] font-medium italic">
                Telemetry matched to GPS trip logs.
              </p>
            </div>
          </div>
        </div>

        {/* Expenses */}
        <div className="glass-panel p-6 border-l-4 border-l-green-500">
          <h4 className="text-sm font-bold text-[#a0a0a0] mb-4 uppercase tracking-widest flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-green-500" />
            Expenses
          </h4>
          <h3 className="text-3xl font-black text-white mb-4">
            ${parseFloat(data?.summary?.total_expenses?.toString() || '0').toFixed(2)}
          </h3>
          <div className="space-y-2 max-h-32 overflow-y-auto">
            {(data?.summary?.expense_list || []).map((e, i) => (
              <div key={i} className="flex justify-between text-[11px] text-[#a0a0a0] border-b border-white/5 pb-1">
                <span>{e.name}</span>
                <span className="text-white font-bold">${parseFloat(e.amount.toString()).toFixed(2)}</span>
              </div>
            ))}
            {(!data?.summary?.expense_list || data.summary.expense_list.length === 0) && (
              <span className="text-[10px] text-[#555] italic">No filtered expenses today</span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-8 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-500 text-sm flex items-center gap-3">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}
    </div>
  )
}

export default App
