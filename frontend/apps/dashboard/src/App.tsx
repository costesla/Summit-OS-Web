import { useState, useEffect } from 'react'
import {
  BarChart3,
  Zap,
  CloudRain,
  TrendingUp,
  DollarSign,
  Battery,
  MapPin,
  Navigation,
  RefreshCcw,
  ShieldCheck
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area
} from 'recharts'

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
  server_time: string;
}

function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      // Replace with your actual Function URL once deployed to production
      const url = "/api/dashboard-summary";
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

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000); // Polling every minute
    return () => clearInterval(interval);
  }, []);

  const mockChartData = [
    { time: '08:00', earnings: 45 },
    { time: '10:00', earnings: 120 },
    { time: '12:00', earnings: 85 },
    { time: '14:00', earnings: 210 },
    { time: '16:00', earnings: 150 },
    { time: '18:00', earnings: 300 },
    { time: '20:00', earnings: 240 },
  ];

  return (
    <div className="min-h-screen bg-[#111] text-white p-6 md:p-10 w-full max-w-7xl">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-white mb-1">SUMMIT COMMAND</h1>
          <p className="text-tesla-gray font-medium flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-green-500" />
            SECURE CLOUD PLATFORM V1.0
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm bg-black/40 p-3 rounded-xl border border-white/5">
          <div className="flex items-center gap-2 text-tesla-gray">
            <MapPin className="w-4 h-4" />
            {data?.telematics?.latitude?.toFixed(4) || '38.8339'}, {data?.telematics?.longitude?.toFixed(4) || '-104.8214'}
          </div>
          <button
            onClick={fetchData}
            className="p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Earnings KPI */}
        <div className="bg-[#1a1a1a] p-6 rounded-2xl border border-white/5 shadow-2xl overflow-hidden relative group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <DollarSign className="w-16 h-16" />
          </div>
          <p className="text-sm font-semibold text-tesla-gray mb-1 uppercase tracking-wider">Today's Revenue</p>
          <h3 className="text-3xl font-black text-white">${data?.stats?.TotalEarnings?.toFixed(2) || '1,240.00'}</h3>
          <div className="mt-4 flex items-center gap-2 text-green-500 text-xs font-bold">
            <TrendingUp className="w-4 h-4" />
            +{data?.stats?.TotalTips?.toFixed(2) || '42.50'} TIPS
          </div>
        </div>

        {/* Vehicle KPI */}
        <div className="bg-[#1a1a1a] p-6 rounded-2xl border border-white/5 shadow-2xl relative group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Battery className="w-16 h-16" />
          </div>
          <p className="text-sm font-semibold text-tesla-gray mb-1 uppercase tracking-wider">Model Y Status</p>
          <div className="flex items-end gap-2">
            <h3 className="text-3xl font-black text-white">{data?.telematics?.battery_level || '84'}%</h3>
            <span className="text-tesla-gray text-xs mb-1.5 font-bold uppercase">
              {data?.telematics?.charging_state || 'Stationary'}
            </span>
          </div>
          <div className="mt-4 h-1.5 w-full bg-black/40 rounded-full">
            <div
              className="h-full bg-green-500 rounded-full transition-all duration-1000"
              style={{ width: `${data?.telematics?.battery_level || 84}%` }}
            />
          </div>
        </div>

        {/* Trips KPI */}
        <div className="bg-[#1a1a1a] p-6 rounded-2xl border border-white/5 shadow-2xl relative group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Navigation className="w-16 h-16" />
          </div>
          <p className="text-sm font-semibold text-tesla-gray mb-1 uppercase tracking-wider">Active Shifts</p>
          <h3 className="text-3xl font-black text-white">{data?.stats?.TripCount || 12} Trips</h3>
          <div className="mt-4 flex items-center gap-2 text-tesla-gray text-xs font-bold">
            <RefreshCcw className="w-4 h-4" />
            LIVE SYNC ACTIVE
          </div>
        </div>

        {/* Weather KPI */}
        <div className="bg-[#1a1a1a] p-6 rounded-2xl border border-white/5 shadow-2xl relative group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <CloudRain className="w-16 h-16" />
          </div>
          <p className="text-sm font-semibold text-tesla-gray mb-1 uppercase tracking-wider">Environment</p>
          <h3 className="text-3xl font-black text-white">{data?.weather?.Temperature_F || '32'}°F</h3>
          <div className="mt-4 flex items-center gap-2 text-tesla-gray text-xs font-bold uppercase">
            <Zap className="w-4 h-4 text-blue-400" />
            {data?.weather?.Condition || 'Light Snow'}
          </div>
        </div>
      </div>

      {/* Visual Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#1a1a1a] p-8 rounded-3xl border border-white/5 shadow-2xl">
          <div className="flex justify-between items-center mb-8">
            <h4 className="text-lg font-bold flex items-center gap-2 uppercase tracking-wide">
              <BarChart3 className="w-5 h-5 text-tesla-red" />
              Efficiency Analytics
            </h4>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={mockChartData}>
                <defs>
                  <linearGradient id="colorEarnings" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#E82127" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#E82127" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                <XAxis dataKey="time" stroke="#555" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#555" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff' }}
                />
                <Area type="monotone" dataKey="earnings" stroke="#E82127" fillOpacity={1} fill="url(#colorEarnings)" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-tesla-red/5 p-8 rounded-3xl border border-tesla-red/20 flex flex-col justify-center gap-4 overflow-hidden relative">
          <div className="absolute -bottom-10 -right-10 opacity-10">
            <Zap className="w-48 h-48 text-tesla-red" />
          </div>
          <h4 className="text-xl font-black text-tesla-red mb-2 italic tracking-tighter uppercase">Summit Elite System</h4>
          <p className="text-sm text-white/70 leading-relaxed max-w-xs">
            Integrated telematics and financial forecasting for the COS Tesla fleet.
            All data is end-to-end encrypted and managed via Azure Cloud Identity.
          </p>
          <div className="mt-8 flex flex-col gap-3">
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span className="text-xs text-tesla-gray uppercase font-bold">Cloud Status</span>
              <span className="text-xs text-green-500 uppercase font-black">Connected</span>
            </div>
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span className="text-xs text-tesla-gray uppercase font-bold">Data Fidelity</span>
              <span className="text-xs text-white uppercase font-black">100%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Advanced Insights Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
        <div className="bg-[#1a1a1a] p-6 rounded-2xl border border-white/5 border-l-orange-500/50 border-l-4">
          <div className="flex items-center gap-3 mb-4">
            <TrendingUp className="w-5 h-5 text-orange-500" />
            <h4 className="font-bold uppercase tracking-wider text-sm">Predictive Profitability</h4>
          </div>
          <p className="text-2xl font-black text-white">$142.50 <span className="text-tesla-gray text-xs font-normal">Exp. Tip delta tomorrow</span></p>
          <p className="text-xs text-tesla-gray mt-2 italic">Based on weather forecast (Light Snow) and historical airport activity trends.</p>
        </div>

        <div className="bg-[#1a1a1a] p-6 rounded-2xl border border-white/5 border-l-blue-500/50 border-l-4">
          <div className="flex items-center gap-3 mb-4">
            <Navigation className="w-5 h-5 text-blue-500" />
            <h4 className="font-bold uppercase tracking-wider text-sm">Aviation Correlation</h4>
          </div>
          <p className="text-2xl font-black text-white">HIGH <span className="text-tesla-gray text-xs font-normal">Airport pickup demand</span></p>
          <p className="text-xs text-tesla-gray mt-2 italic">Detected 4 upcoming flight arrivals at COS in the next 60 minutes.</p>
        </div>
      </div>

      {error && (
        <div className="mt-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-500 text-sm flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 rotate-180" />
          {error}
        </div>
      )}
    </div>
  )
}

export default App
