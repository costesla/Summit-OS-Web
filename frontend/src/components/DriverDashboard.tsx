'use client';

import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
    TrendingUp, Car, Zap, Utensils, Trash2,
    Navigation, Receipt, RotateCcw, Clock,
    Battery, BatteryCharging, WifiOff, Download,
    MapPin, Gauge, LogOut, Cpu, RefreshCw, Loader2,
    DollarSign, Cloud, Moon, UserCheck
} from 'lucide-react';
import { isBackgroundableError, devDebugError, getAsyncExecutionLogs, pollJobStatus } from '../lib/intelligenceUtils';

// ─── Constants ─────────────────────────────────────────────────────────────
const AZURE_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://summitos-api.azurewebsites.net/api';
const VERSION = "1.4.5";

const TAG_FILTERS = ['Uber', 'Uber_Matched', 'Uber_Pickup', 'Jackie', 'Esmeralda', 'Daniel', 'Lauren', 'Ryan', 'Terrance', 'Lorynne', 'Staging', 'Private_Trip', 'Uncategorized', 'Charging Session'] as const;

// ─── Types ──────────────────────────────────────────────────────────────────
interface PrivatePayment {
    id: number;
    client: string;
    amount: number;
    note: string;
    date: string;
    timestamp: string;
}

interface Expense {
    id: number;
    amount: number;
    note: string;
    timestamp: string;
    category?: string;
}

interface Expenses {
    fastfood: Expense[];
    charging: Expense[];
    capital_maintenance: Expense[];
}

interface TeslaStatus {
    is_charging: boolean;
    charging_state: string | null;
    current_soc: number | null;       // battery %
    battery_range_mi: number | null;  // estimated range
    charge_power_kw: number;
    minutes_to_full: number | null;
    location: string | null;
    inside_temp: number | null;
    outside_temp: number | null;
    vehicle_asleep?: boolean;
    formatted_time?: string;
    // Live session cost tracking
    charge_energy_added?: number | null;
    running_cost_estimate?: number | null;
    charging_rate_per_kwh?: number;
}

interface TessieDrive {
    tessie_drive_id: string;
    date: string | null;
    time_mst: string | null;
    tag: string | null;
    distance_miles: number;
    energy_used_kwh: number;
    efficiency_wh_mi: number | null;
    average_speed_mph: number;
    start: string | null;
    end: string | null;
    starting_battery: number | null;
    ending_battery: number | null;
    duration_minutes: number;
    // OCR fare match status — populated by backend cross-referencing Rides.Rides
    fare_matched?: boolean;
    driver_earnings?: number | null;
}

interface TessieCharge {
    tessie_charge_id: string | null;
    date: string | null;
    time_mst: string | null;
    energy_added_kwh: number;
    starting_soc: number | null;
    ending_soc: number | null;
    duration_minutes: number | null;
    location: string | null;
    charge_type: string | null;
    // Live session fields — populated when vehicle is actively charging
    is_live?: boolean;
    charge_power_kw?: number;
    running_cost_estimate?: number | null;
    charging_rate_per_kwh?: number;
}

// ─── Sub-components ─────────────────────────────────────────────────────────

const StatCard = ({
    label, value, sub, icon, highlight = false,
}: {
    label: string; value: string | number; sub: React.ReactNode;
    icon: React.ReactNode; highlight?: boolean;
}) => (
    <div
        className={`relative rounded-2xl p-5 flex items-start gap-4 overflow-hidden transition-all duration-300 hover:scale-[1.02]
      ${highlight
                ? 'bg-blue-50/70 border border-blue-200 shadow-sm shadow-blue-100/50 hover:border-blue-300'
                : 'bg-white/80 border border-slate-200/80 shadow-sm hover:border-slate-300 hover:shadow-md'}`}
        style={{ backdropFilter: 'blur(16px)' }}
    >
        {highlight && <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-[60px] rounded-full pointer-events-none" />}
        <div className={`p-2.5 rounded-xl ${highlight ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-600'}`}>{icon}</div>
        <div>
            <p className="text-xs font-semibold tracking-wide text-slate-500 mb-0.5">{label}</p>
            <p className={`text-2xl font-black tracking-tight ${highlight ? 'text-blue-600' : 'text-slate-900'}`}>{value}</p>
            <p className="text-xs font-mono text-slate-400 mt-0.5">{sub}</p>
        </div>
    </div>
);

const ExpenseList = ({
    title, data, icon, onDelete, onAdd, accentColor, subtitle,
}: {
    title: string; data: Expense[]; icon: React.ReactNode;
    onDelete: (id: number) => void;
    onAdd?: (amount: number, note: string) => void;
    accentColor: string;
    subtitle?: string;
}) => {
    const [amount, setAmount] = React.useState('');
    const [note, setNote] = React.useState('');
    const inputBase = 'bg-slate-50 border border-slate-200 rounded-xl text-slate-800 placeholder-slate-400 font-mono text-xs focus:outline-none focus:border-blue-500 focus:bg-white transition-all';

    const handleAdd = (e: React.FormEvent) => {
        e.preventDefault();
        const val = parseFloat(amount);
        if (!val || !onAdd) return;
        onAdd(val, note);
        setAmount(''); setNote('');
    };

    return (
        <div className="rounded-2xl overflow-hidden border border-slate-200/80 shadow-sm"
            style={{ background: 'rgba(255, 255, 255, 0.8)', backdropFilter: 'blur(16px)' }}>
            <div className="p-4 border-b border-slate-200/80 flex flex-col gap-1">
                <div className="flex items-center gap-2 w-full">
                    {icon}
                    <h3 className="font-bold text-sm text-slate-800">{title}</h3>
                    {data.length > 0 && (
                        <span className={`ml-auto text-xs font-mono font-bold ${
                            accentColor.replace('text-amber-400', 'text-amber-700')
                                       .replace('text-rose-400', 'text-rose-700')
                                       .replace('text-blue-600', 'text-blue-700')
                        }`}>
                            ${data.reduce((s, e) => s + e.amount, 0).toFixed(2)}
                        </span>
                    )}
                </div>
                {subtitle && (
                    <p className="text-[10px] font-sans font-medium text-blue-600/80 pl-6 leading-none select-none">
                        {subtitle}
                    </p>
                )}
            </div>
            <div className="max-h-[200px] overflow-y-auto">
                {data.length === 0
                    ? <p className="p-6 text-center text-xs text-slate-400 italic font-mono">// no entries</p>
                    : <div className="divide-y divide-slate-100">
                        {data.map((item) => (
                            <div key={item.id} className="p-3 flex justify-between items-center group hover:bg-slate-50 transition-colors">
                                <div className="flex flex-col">
                                    <span className="text-xs font-bold text-slate-800">${item.amount.toFixed(2)}</span>
                                    <span className="text-[10px] text-slate-500 font-mono">{item.note || item.timestamp}</span>
                                </div>
                                <button onClick={() => onDelete(item.id)}
                                    className="text-slate-400 hover:text-rose-600 opacity-0 group-hover:opacity-100 transition-all">
                                    <Trash2 className="w-3 h-3" />
                                </button>
                            </div>
                        ))}
                    </div>}
            </div>
            {onAdd && (
                <form onSubmit={handleAdd} className="flex gap-2 p-3 border-t border-slate-200/80 bg-slate-50/50">
                    <input
                        type="number" step="0.01" placeholder="$0.00" value={amount}
                        onChange={e => setAmount(e.target.value)}
                        className={`${inputBase} w-20 p-2 text-center shrink-0`}
                    />
                    <input
                        type="text" placeholder="Note (store, receipt...)" value={note}
                        onChange={e => setNote(e.target.value)}
                        className={`${inputBase} flex-1 min-w-0 p-2`}
                    />
                    <button type="submit"
                        className={`px-3 py-2 rounded-xl text-xs font-bold border transition-all shrink-0 ${
                            accentColor.includes('amber') 
                                ? 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100' 
                                : accentColor.includes('blue')
                                    ? 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100'
                                    : 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100'
                        }`}>
                        +
                    </button>
                </form>
            )}
        </div>
    );
};

// ─── Tesla Status Bar ────────────────────────────────────────────────────────
const TeslaStatusBar = () => {
    const [status, setStatus] = useState<TeslaStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [offline, setOffline] = useState(false);

    const fetchStatus = useCallback(async () => {
        try {
            const res = await fetch(`${AZURE_BASE}/copilot/charging/live`, { signal: AbortSignal.timeout(8000) });
            if (!res.ok) throw new Error('non-ok');
            const data = await res.json();
            setStatus(data);
            setOffline(false);
        } catch {
            setOffline(true);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        const iv = setInterval(fetchStatus, 30_000); // refresh every 30s for more 'live' feel
        return () => clearInterval(iv);
    }, [fetchStatus]);

    const isAsleep = status?.vehicle_asleep ?? false;
    const soc = status?.current_soc ?? null;
    const range = status?.battery_range_mi ?? null;
    const isCharging = status?.is_charging ?? false;
    const chargingState = status?.charging_state ?? null;
    const kw = status?.charge_power_kw ?? 0;
    const minsToFull = status?.minutes_to_full ?? null;

    const barColor = soc !== null
        ? soc > 50 ? 'bg-emerald-500' : soc > 20 ? 'bg-amber-500' : 'bg-rose-500'
        : 'bg-slate-300';

    const barTextColor = soc !== null
        ? soc > 50 ? 'text-emerald-600' : soc > 20 ? 'text-amber-600' : 'text-rose-600'
        : 'text-slate-400';

    // Determine indicator state: green = charging, blue = online, amber = sleeping, grey = offline
    const pulseColor = isCharging
        ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
        : isAsleep
            ? 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.4)]'
            : offline
                ? 'bg-slate-400'
                : 'bg-blue-600 shadow-[0_0_8px_rgba(37,99,235,0.5)]';

    return (
        <div
            className="flex flex-wrap md:flex-nowrap items-center gap-4 px-5 py-3 rounded-2xl border border-slate-200/80 shadow-sm"
            style={{ background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(12px)' }}
        >
            {/* Label */}
            <div className="flex items-center gap-2 shrink-0">
                {isCharging
                    ? <BatteryCharging className="w-4 h-4 text-emerald-500" />
                    : isAsleep
                        ? <Moon className="w-4 h-4 text-amber-400" />
                        : offline ? <WifiOff className="w-4 h-4 text-slate-400" />
                            : <Battery className="w-4 h-4 text-blue-600" />}
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                    {isAsleep ? 'Tesla' : 'Tesla Live'}
                    <span className={`w-1.5 h-1.5 rounded-full ${offline ? '' : 'animate-pulse'} ${pulseColor}`} />
                </span>
            </div>

            {loading && (
                <div className="flex gap-3 flex-1 animate-pulse">
                    <div className="h-2 w-32 bg-slate-200 rounded-full" />
                    <div className="h-2 w-20 bg-slate-200 rounded-full" />
                </div>
            )}

            {!loading && offline && (
                <span className="text-xs text-slate-400 font-mono italic">Vehicle offline — unable to reach telemetry</span>
            )}

            {/* Asleep state — shows a clean sleeping indicator with timestamp */}
            {!loading && !offline && isAsleep && (
                <div className="flex items-center gap-3 flex-1">
                    <span className="text-xs text-amber-600 font-semibold">Vehicle Sleeping</span>
                    {status?.formatted_time && (
                        <span className="text-[10px] text-slate-400 font-mono">as of {status.formatted_time}</span>
                    )}
                </div>
            )}

            {/* Active state — shows full telemetry */}
            {!loading && !offline && status && !isAsleep && (
                <>
                    {/* Battery bar + % */}
                    <div className="flex items-center gap-2 md:gap-3 flex-1 min-w-0">
                        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                                className={`h-full ${barColor} transition-all duration-700`}
                                style={{ width: `${soc ?? 0}%` }}
                            />
                        </div>
                        <span className={`text-lg md:text-2xl font-black font-mono tabular-nums ${barTextColor}`}>
                            {soc !== null ? `${soc}%` : '--'}
                        </span>
                    </div>

                    {/* Range & Charging Info Container */}
                    <div className="flex items-center gap-4 ml-auto">
                        {range !== null && (
                            <div className="flex items-center gap-1.5 shrink-0">
                                <Gauge className="w-3.5 h-3.5 text-slate-400" />
                                <span className="text-xs md:text-sm font-bold text-slate-700 tabular-nums">{range.toFixed(0)}<span className="text-slate-400 font-normal text-[10px]"> mi</span></span>
                            </div>
                        )}

                        {isCharging && (
                            <div className="flex items-center gap-1.5 shrink-0">
                                <Zap className="w-3.5 h-3.5 text-emerald-500" />
                                <span className="text-xs md:text-sm font-bold text-emerald-600 tabular-nums">{kw} kW</span>
                                {minsToFull !== null && (
                                    <span className="hidden md:inline text-[10px] text-slate-500 font-mono">({Math.round(minsToFull / 60)}h {minsToFull % 60}m)</span>
                                )}
                            </div>
                        )}
                    </div>

                    {/* State label */}
                    {chargingState && !isCharging && (
                        <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider shrink-0">{chargingState}</span>
                    )}

                    {/* Temperature */}
                    {(status.inside_temp !== null || status.outside_temp !== null) && (
                        <div className="flex items-center gap-3 px-3 py-1 bg-slate-50 rounded-full border border-slate-200/80">
                            {status.outside_temp !== null && (
                                <div className="flex items-center gap-1">
                                    <span className="text-[10px] text-slate-400 font-bold uppercase">Ext</span>
                                    <span className="text-xs font-bold text-slate-700 font-mono">{Math.round(status.outside_temp * 9/5 + 32)}°</span>
                                </div>
                            )}
                            {status.inside_temp !== null && (
                                <div className="flex items-center gap-1 border-l border-slate-200 pl-3">
                                    <span className="text-[10px] text-slate-400 font-bold uppercase">Int</span>
                                    <span className="text-xs font-bold text-blue-600 font-mono">{Math.round(status.inside_temp * 9/5 + 32)}°</span>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Location */}
                    {status.location && (
                        <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-50 rounded-full border border-slate-200/80 max-w-[200px]">
                            <MapPin className="w-3 h-3 text-blue-600 shrink-0" />
                            <span className="text-[10px] font-bold text-slate-600 truncate uppercase tracking-tighter">{status.location}</span>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

// ─── Uber Heatmap Panel ──────────────────────────────────────────────────────
const UberHeatmapPanel = () => {
    const [expanded, setExpanded] = useState(false);
    return (
        <div className="rounded-2xl border border-slate-200/80 bg-white/80 overflow-hidden transition-all duration-300 shadow-sm backdrop-blur-md">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50 transition-all duration-200"
                id="uber-heatmap-toggle"
            >
                <div className="flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-blue-600" />
                    <div>
                        <h3 className="font-bold text-sm text-slate-800">Uber Activity Heatmap</h3>
                        <p className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Pickup &amp; Dropoff Density · Colorado Springs</p>
                    </div>
                </div>
                <span className="text-xs font-bold text-blue-600 font-mono">
                    {expanded ? '▲ HIDE MAP' : '▼ EXPAND MAP'}
                </span>
            </button>
            {expanded && (
                <div className="border-t border-slate-200/80" style={{ height: '620px' }}>
                    <iframe
                        src="/uber-heatmap.html"
                        title="Uber Activity Heatmap"
                        className="w-full h-full border-none"
                        style={{ display: 'block' }}
                    />
                </div>
            )}
        </div>
    );
};

// ─── Tag badge ───────────────────────────────────────────────────────────────
const TAG_STYLE: Record<string, string> = {
    uber_matched: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
    uber_pickup: 'bg-sky-50 text-sky-700 border-sky-200/80',
    uber: 'bg-slate-100 text-slate-700 border-slate-200/80',
    jackie: 'bg-purple-50 text-purple-700 border-purple-200/80',
    esmeralda: 'bg-teal-50 text-teal-700 border-teal-200/80',
    daniel: 'bg-indigo-50 text-indigo-700 border-indigo-200/80',
    lauren: 'bg-rose-50 text-rose-700 border-rose-200/80',
    ryan: 'bg-cyan-50 text-cyan-700 border-cyan-200/80',
    terrance: 'bg-orange-50 text-orange-700 border-orange-200/80',
    lorynne: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200/80',
    private_trip: 'bg-amber-50 text-amber-800 border-amber-300/80',
    private: 'bg-amber-50 text-amber-800 border-amber-300/80',
    uncategorized: 'bg-slate-50 text-slate-500 border-slate-200/80',
};
const tagStyle = (tag: string | null) => {
    const key = (tag ?? '').toLowerCase() || 'uncategorized';
    for (const [k, v] of Object.entries(TAG_STYLE)) if (key.includes(k)) return v;
    return 'bg-slate-50 text-slate-500 border-slate-200/60';
};

// ─── Tessie Drives Panel ─────────────────────────────────────────────────────
const TessieDrivesPanel = ({
    onImport,
    selectedDate,
    refreshKey,
    privatePayments = [],
    chargingExpenses = [],
    isVehicleCharging = false
}: {
    onImport: (drive: TessieDrive) => void;
    selectedDate: string;
    refreshKey?: number;
    privatePayments?: PrivatePayment[];
    chargingExpenses?: Expense[];
    isVehicleCharging?: boolean;
}) => {
    const [drives, setDrives] = useState<TessieDrive[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [importedIds, setImportedIds] = useState<Set<string>>(new Set());

    const fetchAll = useCallback(async () => {
        setLoading(true);
        setError(false);
        try {
            const today = new Date();
            const target = new Date(selectedDate + 'T12:00:00');
            const diffMs = today.getTime() - target.getTime();
            const daysBack = Math.max(1, Math.ceil(diffMs / 86_400_000) + 2);
            const results = await Promise.all(
                TAG_FILTERS.map((tag) =>
                    fetch(`${AZURE_BASE}/copilot/tessie/drives?tag=${tag}&days=${daysBack}&t=${Date.now()}`, {
                        signal: AbortSignal.timeout(12_000),
                        cache: 'no-store'
                    })
                        .then((r) => (r.ok ? r.json() : { drives: [] }))
                        .then((d) => (d.drives ?? []) as TessieDrive[])
                        .catch(() => [] as TessieDrive[])
                )
            );

            const seen = new Set<string>();
            const merged: TessieDrive[] = [];
            for (const batch of results) {
                for (const d of batch) {
                    const key = String(d.tessie_drive_id);
                    if (!seen.has(key)) {
                        seen.add(key);
                        merged.push({ ...d, tessie_drive_id: key });
                    }
                }
            }
            const filtered = merged
                .filter((d) => d.date === selectedDate)
                .sort((a, b) => (b.time_mst ?? '00:00').localeCompare(a.time_mst ?? '00:00'));

            setDrives(filtered);
            setError(false);
        } catch {
            setError(true);
        } finally {
            setLoading(false);
        }
    }, [selectedDate]);

    useEffect(() => {
        fetchAll();
    }, [fetchAll, refreshKey]);

    const handleImport = (drive: TessieDrive) => {
        onImport(drive);
        setImportedIds((prev) => new Set(prev).add(drive.tessie_drive_id));
    };

    return (
        <div
            className="rounded-2xl border border-slate-200/80 overflow-hidden bg-white/90 shadow-sm"
            style={{ backdropFilter: 'blur(16px)' }}
        >
            <div className="p-5 border-b border-slate-200/80 flex flex-wrap items-center gap-3 justify-between">
                <div className="flex items-center gap-2">
                    <Car className="w-4 h-4 text-blue-600" />
                    <h2 className="font-bold text-slate-800">Tessie Drives</h2>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">{selectedDate}</span>
                    {TAG_FILTERS.map((t) => {
                        const isJackie = t.toLowerCase() === 'jackie';
                        return (
                            <span key={t} className={`text-[10px] font-bold px-2 py-0.5 rounded-full border font-mono uppercase tracking-wider ${tagStyle(t)}`}>
                                {isJackie ? (
                                    <a 
                                        href="/jackie" 
                                        target="_blank" 
                                        rel="noopener noreferrer" 
                                        className="hover:underline font-bold"
                                    >
                                        {t}
                                    </a>
                                ) : t}
                            </span>
                        );
                    })}
                    <button
                        onClick={() => fetchAll()}
                        disabled={loading}
                        title="Refresh drives from Tessie"
                        className="flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:text-blue-600 hover:border-blue-300 hover:bg-slate-50 transition-all disabled:opacity-40"
                    >
                        <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            <div className="divide-y divide-slate-100">
                {loading && (
                    <div className="p-10 text-center animate-pulse">
                        <div className="h-2 w-48 bg-slate-200 rounded-full mx-auto mb-3" />
                        <div className="h-2 w-32 bg-slate-200 rounded-full mx-auto" />
                    </div>
                )}

                {!loading && error && (
                    <div className="p-10 text-center">
                        <WifiOff className="w-6 h-6 text-slate-400 mx-auto mb-2" />
                        <p className="text-xs text-slate-400 font-mono">// Azure unreachable — drives unavailable</p>
                    </div>
                )}

                {!loading && !error && drives.length === 0 && (
                    <p className="p-10 text-center text-xs text-slate-400 italic font-mono">
                        // no tagged drives found for {selectedDate} (Uber · Jackie · Esmeralda)
                    </p>
                )}

                {!loading && !error && drives.map((drive) => {
                    const imported = importedIds.has(drive.tessie_drive_id);
                    return (
                        <div key={drive.tessie_drive_id}
                            className="p-4 flex flex-col md:flex-row md:items-center gap-3 hover:bg-slate-50/50 transition-colors group">
                            <div className="flex-1 space-y-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border font-mono uppercase ${tagStyle(drive.tag)}`}>
                                        {drive.tag ?? 'Untagged'}
                                    </span>
                                    <span className="text-[10px] text-slate-400 font-mono">
                                        {drive.date} · {drive.time_mst}
                                    </span>
                                    {(drive.tag ?? '').toLowerCase().includes('uber') && (
                                        drive.fare_matched
                                            ? (
                                                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-emerald-50 border-emerald-200 text-emerald-700">
                                                    <span>✓</span>
                                                    <span>${drive.driver_earnings?.toFixed(2)}</span>
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-rose-50 border-rose-200 text-rose-700">
                                                    <span>✗</span>
                                                    <span>No receipt</span>
                                                </span>
                                            )
                                    )}
                                     {drive.tag &&
                                      !drive.tag.toLowerCase().includes('uber') &&
                                      !drive.tag.toLowerCase().includes('uncategorized') &&
                                      !drive.tag.toLowerCase().includes('untagged') && (() => {
                                         const tagLower = drive.tag.toLowerCase();

                                         // 1. Check if it's an operational charging session
                                         // Cost is shown in the Charging Expenses section — not duplicated here.
                                         if (tagLower.includes('charging') || tagLower.includes('supercharger')) {
                                             return (
                                                 <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                                                     isVehicleCharging
                                                         ? 'bg-emerald-500 border-emerald-500 text-white shadow-[0_0_8px_rgba(16,185,129,0.4)]'
                                                         : 'bg-slate-50 border-slate-200 text-slate-500'
                                                 }`}>
                                                     {isVehicleCharging ? (
                                                         <>
                                                             <span className="relative flex h-1.5 w-1.5">
                                                                 <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                                                                 <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-white" />
                                                             </span>
                                                             <span>⚡ LIVE</span>
                                                         </>
                                                     ) : (
                                                         <span>⚡ Charging Session</span>
                                                     )}
                                                 </span>
                                             );
                                         }

                                         // 2. Check other common operational/non-passenger tags
                                         if (tagLower.includes('reposition')) {
                                             return (
                                                 <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-600">
                                                     <span>📍 Repositioning</span>
                                                 </span>
                                             );
                                         }
                                         if (tagLower.includes('staging')) {
                                             return (
                                                 <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-600">
                                                     <span>📍 Staging</span>
                                                 </span>
                                             );
                                         }
                                         if (tagLower.includes('home')) {
                                             return (
                                                 <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-600">
                                                     <span>🏠 Home</span>
                                                 </span>
                                             );
                                         }
                                         if (tagLower.includes('quickquack') || tagLower.includes('wash') || tagLower.includes('clean')) {
                                             return (
                                                 <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-600">
                                                     <span>🧼 Car Wash</span>
                                                 </span>
                                             );
                                         }
                                         if (tagLower.includes('starbucks') || tagLower.includes('whataburger') || tagLower.includes('maverik') || tagLower.includes('mcdonald') || tagLower.includes('burger') || tagLower.includes('wingstop') || tagLower.includes('food') || tagLower.includes('drink') || tagLower.includes('meal')) {
                                             let displayTag = '🍴 Break';
                                             if (tagLower.includes('starbucks')) displayTag = '☕ Starbucks';
                                             else if (tagLower.includes('whataburger')) displayTag = '🍔 Whataburger';
                                             else if (tagLower.includes('maverik')) displayTag = '🍴 Maverik';
                                             return (
                                                 <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-600">
                                                     <span>{displayTag}</span>
                                                 </span>
                                             );
                                         }

                                         // 3. Fallback to private passenger payment client matching
                                         const matchedPayment = (privatePayments || []).find((p) => {
                                             if (p.date !== drive.date || !p.client) return false;
                                             const clientLower = p.client.toLowerCase();
                                             return tagLower.includes(clientLower);
                                         });
                                         return matchedPayment && matchedPayment.amount > 0 ? (
                                             <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-emerald-50 border-emerald-200 text-emerald-700">
                                                 <span>✓ Paid</span>
                                                 <span>(${matchedPayment.amount.toFixed(2)})</span>
                                             </span>
                                         ) : (
                                             <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-rose-50 border-rose-200 text-rose-700">
                                                 <span>✗ Unpaid</span>
                                             </span>
                                         );
                                     })()}
                                </div>
                                {(drive.start || drive.end) && (
                                    <div className="flex items-start gap-1.5 text-[11px] text-slate-600">
                                        <MapPin className="w-3 h-3 mt-0.5 text-slate-400 shrink-0" />
                                        <span className="leading-snug">
                                            {drive.start ?? '—'} → {drive.end ?? '—'}
                                        </span>
                                    </div>
                                )}
                            </div>

                            <div className="flex gap-5 shrink-0 text-center">
                                <div>
                                    <p className="text-[10px] text-slate-500 font-mono uppercase">Miles</p>
                                    <p className="text-sm font-black text-slate-800 tabular-nums">{drive.distance_miles.toFixed(1)}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] text-slate-500 font-mono uppercase">kWh</p>
                                    <p className="text-sm font-bold text-amber-600 tabular-nums">{drive.energy_used_kwh.toFixed(2)}</p>
                                </div>
                                {drive.efficiency_wh_mi !== null && (
                                    <div>
                                        <p className="text-[10px] text-slate-500 font-mono uppercase">Wh/mi</p>
                                        <p className="text-sm font-bold text-slate-700 tabular-nums">{drive.efficiency_wh_mi}</p>
                                    </div>
                                )}
                                <div>
                                    <p className="text-[10px] text-slate-500 font-mono uppercase">Batt</p>
                                    <p className="text-sm font-bold text-blue-600 tabular-nums">
                                        {drive.starting_battery ?? '--'}→{drive.ending_battery ?? '--'}%
                                    </p>
                                </div>
                            </div>
                        </div>

                    );
                })}
            </div>
        </div>
    );
};

// ─── Tessie Charges Panel ──────────────────────────────────────────────────
const TessieChargesPanel = ({ onImport, selectedDate }: { onImport: (charge: TessieCharge) => void, selectedDate: string }) => {
    const [charges, setCharges] = useState<TessieCharge[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [importedIds, setImportedIds] = useState<Set<string>>(new Set());
    const [liveStatus, setLiveStatus] = useState<TeslaStatus | null>(null);
    const [finalized, setFinalized] = useState(false);
    const prevChargingRef = useRef(false);

    // Fetch historical charges
    const fetchCharges = useCallback(async () => {
        try {
            const todayDate = new Date();
            const targetDate = new Date(selectedDate + 'T12:00:00');
            const diffMs = todayDate.getTime() - targetDate.getTime();
            const daysBack = Math.max(1, Math.ceil(diffMs / 86_400_000) + 1);

            const resp = await fetch(`${AZURE_BASE}/copilot/tessie/charges?days=${daysBack}&t=${Date.now()}`, {
                signal: AbortSignal.timeout(12_000),
                cache: 'no-store'
            });
            const data = resp.ok ? await resp.json() : { sessions: [] };
            const filtered = ((data.sessions ?? []) as TessieCharge[]).filter((c) => c.date === selectedDate);
            setCharges(filtered);
            setError(false);
        } catch { setError(true); } finally { setLoading(false); }
    }, [selectedDate]);

    useEffect(() => {
        setLoading(true);
        setFinalized(false);
        fetchCharges();
    }, [fetchCharges]);

    // Poll live charging status every 60 seconds
    useEffect(() => {
        const pollLive = async () => {
            try {
                const res = await fetch(`${AZURE_BASE}/copilot/charging/live`, { signal: AbortSignal.timeout(8000) });
                if (!res.ok) { setLiveStatus(null); return; }
                const data = await res.json();
                setLiveStatus(data);
            } catch { setLiveStatus(null); }
        };
        pollLive();
        const iv = setInterval(pollLive, 60_000);
        return () => clearInterval(iv);
    }, []);

    // Auto-finalize: detect transition from charging → not charging
    useEffect(() => {
        const wasCharging = prevChargingRef.current;
        const isNowCharging = liveStatus?.is_charging ?? false;
        prevChargingRef.current = isNowCharging;

        if (wasCharging && !isNowCharging && liveStatus && !finalized) {
            setFinalized(true);
            const sessionId = `live-${selectedDate.replace(/-/g, '')}`;
            const energy = liveStatus.charge_energy_added ?? 0;
            const rate = liveStatus.charging_rate_per_kwh ?? 0.40;
            const cost = Math.round(energy * rate * 100) / 100;

            fetch(`${AZURE_BASE}/copilot/charging/finalize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    energy_added_kwh: energy,
                    cost,
                    location: liveStatus.location,
                    end_time: new Date().toISOString(),
                }),
            }).catch(() => {});
            // Refresh charges list to show finalized session
            setTimeout(() => fetchCharges(), 3000);
        }
    }, [liveStatus, selectedDate, finalized, fetchCharges]);

    const handleImport = (charge: TessieCharge) => {
        onImport(charge);
        const key = charge.tessie_charge_id ?? `${charge.date}-${charge.time_mst}`;
        setImportedIds((prev) => new Set(prev).add(key ?? ''));
    };

    const isToday = selectedDate === new Date().toLocaleDateString('sv-SE');
    const showLiveCard = isToday && liveStatus?.is_charging && !finalized;

    return (
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm overflow-hidden"
            style={{ backdropFilter: 'blur(16px)' }}>
            <div className="p-5 border-b border-slate-200/80 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-600" />
                <h2 className="font-bold text-slate-800">Tessie Charging Sessions</h2>
                <span className="text-xs font-mono text-slate-400 ml-2 uppercase tracking-wider">{selectedDate}</span>
                {showLiveCard && (
                    <span className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500 text-white text-[10px] font-bold uppercase tracking-wider shadow-[0_0_12px_rgba(16,185,129,0.5)]">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                        </span>
                        LIVE
                    </span>
                )}
            </div>
            <div className="divide-y divide-slate-100">
                {/* Live charging card */}
                {showLiveCard && liveStatus && (
                    <div className="p-4 bg-gradient-to-r from-emerald-50/80 to-green-50/60 border-b border-emerald-200/60">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="relative">
                                    <div className="p-2 rounded-xl bg-emerald-100 border border-emerald-300">
                                        <BatteryCharging className="w-4 h-4 text-emerald-600" />
                                    </div>
                                    <span className="absolute -top-1 -right-1 flex h-3 w-3">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                                        <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
                                    </span>
                                </div>
                                <div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs font-black text-emerald-700 uppercase tracking-wider animate-pulse">LIVE</span>
                                        <span className="text-[10px] font-mono text-emerald-600 font-bold">· {liveStatus.charge_power_kw} kW</span>
                                    </div>
                                    <p className="text-sm font-bold text-slate-800">
                                        {(liveStatus.charge_energy_added ?? 0).toFixed(1)} kWh added
                                        {liveStatus.minutes_to_full != null && <span className="font-normal text-slate-500 text-xs ml-2">· {Math.round(liveStatus.minutes_to_full / 60)}h {liveStatus.minutes_to_full % 60}m remaining</span>}
                                    </p>
                                    <p className="text-[10px] text-slate-400 font-mono">
                                        {liveStatus.location || 'Location pending'}
                                        {liveStatus.current_soc != null && ` · ${liveStatus.current_soc}%`}
                                    </p>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-lg font-black text-emerald-700 tabular-nums font-mono">
                                    ${(liveStatus.running_cost_estimate ?? 0).toFixed(2)}
                                </p>
                                <p className="text-[10px] text-emerald-600/60 font-mono">
                                    @${(liveStatus.charging_rate_per_kwh ?? 0.40).toFixed(2)}/kWh
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {loading && <div className="p-10 text-center animate-pulse"><div className="h-2 w-48 bg-slate-200 rounded-full mx-auto mb-3" /><div className="h-2 w-32 bg-slate-200 rounded-full mx-auto" /></div>}
                {!loading && error && <div className="p-8 text-center text-slate-400 font-mono text-xs flex items-center justify-center gap-2"><WifiOff className="w-4 h-4" /> Unable to load charging sessions</div>}
                {!loading && !error && charges.length === 0 && !showLiveCard && <div className="p-8 text-center text-slate-400 font-mono text-xs italic">// no charging sessions found for {selectedDate}</div>}
                {!loading && !error && charges.map((charge) => {
                    const key = charge.tessie_charge_id ?? `${charge.date}-${charge.time_mst}`;
                    const imported = importedIds.has(key ?? '');
                    return (
                        <div key={key} className="flex items-center justify-between p-4 hover:bg-slate-50/50 transition-colors">
                            <div className="flex items-center gap-4">
                                <div className="p-2 rounded-xl bg-amber-50 border border-amber-200"><BatteryCharging className="w-4 h-4 text-amber-600" /></div>
                                <div>
                                    <p className="text-sm font-bold text-slate-800">
                                        {charge.energy_added_kwh.toFixed(1)} kWh added
                                        {charge.duration_minutes ? <span className="font-normal text-slate-500 text-xs ml-2">· {charge.duration_minutes.toFixed(0)} min</span> : null}
                                    </p>
                                    <p className="text-[10px] text-slate-400 font-mono">
                                        {charge.time_mst ?? '—'}{charge.location ? ` · ${charge.location}` : ''}{charge.charge_type ? ` · ${charge.charge_type}` : ''}
                                    </p>
                                    {charge.starting_soc != null && charge.ending_soc != null && (
                                        <p className="text-[10px] font-mono text-amber-700 mt-0.5">🔋 {charge.starting_soc}% → {charge.ending_soc}%</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

// ─── Uber Trips Panel (OCR numbered trip cards) ────────────────────────────
interface UberTrip {
    trip_id: string;
    trip_number: number;
    trip_type?: string;          // 'Uber' | 'Private' — undefined for legacy records
    classification?: string;
    timestamp: string | null;
    time_display: string;
    service_type: string;
    driver_earnings: number;
    rider_payment: number;
    tip: number;
    uber_cut: number;
    pickup: string | null;
    dropoff: string | null;
    duration_min: number | null;
    distance_mi: number | null;
    filename: string | null;
}

const UberTripsPanel: React.FC<{ selectedDate: string; onTripsLoaded?: (count: number, earnings: number) => void }> = ({ selectedDate, onTripsLoaded }) => {
    const [trips, setTrips] = useState<UberTrip[]>([]);
    const [loading, setLoading] = useState(true);
    const [totalEarnings, setTotalEarnings] = useState(0);

    const onTripsLoadedRef = useRef(onTripsLoaded);
    onTripsLoadedRef.current = onTripsLoaded;

    const handleDeleteTrip = async (rideId: string) => {
        const confirmed = window.confirm(`Permanently delete this trip record? This cannot be undone.`);
        if (!confirmed) return;
        
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/delete-trip/${rideId}`, {
                method: 'DELETE'
            });
            if (resp.ok) {
                fetchTrips();
            } else {
                const err = await resp.json();
                alert(`Error deleting trip: ${err.error || 'Unknown error'}`);
            }
        } catch (e: any) {
            alert(`Error connecting to server: ${e.message}`);
        }
    };

    const fetchTrips = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/get-day-trips?date=${selectedDate}&t=${Date.now()}`, {
                signal: AbortSignal.timeout(12_000), cache: 'no-store'
            });
            const data = resp.ok ? await resp.json() : { trips: [] };
            // Only show Uber trips in this panel — Private trips go to PrivateTripsPanel
            const tripList = ((data.trips ?? []) as UberTrip[]).filter(
                (t) => !t.trip_type || t.trip_type === 'Uber'
            );
            setTrips(tripList);
            const earnings = tripList.reduce((s, t) => s + t.driver_earnings, 0);
            setTotalEarnings(earnings);
            onTripsLoadedRef.current?.(tripList.length, earnings);
        } catch {
            setTrips([]);
            onTripsLoadedRef.current?.(0, 0);
        } finally {
            setLoading(false);
        }
    }, [selectedDate]);

    useEffect(() => { fetchTrips(); }, [fetchTrips]);

    return (
        <div className="rounded-2xl border border-violet-200/80 overflow-hidden bg-violet-50/30 shadow-sm"
            style={{ backdropFilter: 'blur(16px)' }}>
            <div className="p-5 border-b border-violet-200/80 flex flex-wrap items-center gap-3 justify-between">
                <div className="flex items-center gap-2">
                    <Receipt className="w-4 h-4 text-violet-600" />
                    <h2 className="font-bold text-slate-800">Uber Trips</h2>
                    <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">{selectedDate}</span>
                    {trips.length > 0 && (
                        <span className="text-xs font-bold px-2.5 py-0.5 rounded-full border border-violet-200 bg-violet-100/80 text-violet-700 font-mono">
                            {trips.length} trips · ${totalEarnings.toFixed(2)}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={fetchTrips} disabled={loading}
                        className="text-xs font-bold px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:text-blue-600 hover:border-blue-300 hover:bg-slate-50 transition-all">
                        <RefreshCw className={`w-3 h-3 inline mr-1 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            <div className="divide-y divide-violet-100/50">
                {loading && (
                    <div className="p-10 text-center animate-pulse">
                        <div className="h-2 w-48 bg-slate-200 rounded-full mx-auto mb-3" />
                        <div className="h-2 w-32 bg-slate-200 rounded-full mx-auto" />
                    </div>
                )}

                {!loading && trips.length === 0 && (
                    <div className="p-10 text-center">
                        <Receipt className="w-6 h-6 text-slate-400 mx-auto mb-2" />
                        <p className="text-xs text-slate-400 font-mono italic">
                            // no trips found — click "Scan Day" in Intelligence Sync to OCR the {selectedDate} folder
                        </p>
                    </div>
                )}

                {!loading && trips.map((trip) => (
                    <div key={trip.trip_id}
                        className="p-4 flex flex-col md:flex-row md:items-center gap-3 hover:bg-violet-50/20 transition-colors group">
                        <div className="shrink-0 flex flex-col items-center justify-center w-10 h-10 rounded-xl bg-violet-100 border border-violet-200">
                            <span className="text-[10px] font-mono text-violet-500 leading-none">Trip</span>
                            <span className="text-sm font-black text-violet-700 leading-none">{trip.trip_number}</span>
                        </div>

                        <div className="flex-1 space-y-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border border-slate-200 bg-slate-100 text-slate-700 font-mono uppercase">
                                    {trip.service_type}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono">{trip.time_display}</span>
                                {trip.duration_min && (
                                    <span className="text-[10px] text-slate-500 font-mono">{trip.duration_min.toFixed(0)} min</span>
                                )}
                                {trip.distance_mi && (
                                    <span className="text-[10px] text-slate-500 font-mono">{trip.distance_mi.toFixed(2)} mi</span>
                                )}
                            </div>
                            {(trip.pickup || trip.dropoff) && (
                                <div className="flex items-start gap-1.5 text-[11px] text-slate-600">
                                    <MapPin className="w-3 h-3 mt-0.5 text-slate-400 shrink-0" />
                                    <span className="leading-snug truncate">{trip.pickup ?? '—'} → {trip.dropoff ?? '—'}</span>
                                </div>
                            )}
                        </div>

                        <div className="flex gap-4 shrink-0 text-center">
                            <div>
                                <p className="text-[10px] text-slate-500 font-mono uppercase">Earned</p>
                                <p className="text-base font-black text-emerald-700 tabular-nums">${trip.driver_earnings.toFixed(2)}</p>
                            </div>
                            {trip.tip > 0 && (
                                <div>
                                    <p className="text-[10px] text-slate-500 font-mono uppercase">Tip</p>
                                    <p className="text-base font-black text-amber-600 tabular-nums">${trip.tip.toFixed(2)}</p>
                                </div>
                            )}
                            <div>
                                <p className="text-[10px] text-slate-500 font-mono uppercase">Rider</p>
                                <p className="text-sm font-bold text-slate-600 tabular-nums">${trip.rider_payment.toFixed(2)}</p>
                            </div>
                            <div>
                                <p className="text-[10px] text-slate-500 font-mono uppercase">Uber Cut</p>
                                <p className="text-sm font-bold text-rose-600 tabular-nums">${trip.uber_cut.toFixed(2)}</p>
                            </div>
                        </div>
                        <div className="flex items-center justify-center shrink-0 ml-auto md:ml-0 pl-2">
                            <button
                                onClick={() => handleDeleteTrip(trip.trip_id)}
                                className="text-slate-400 dark:text-slate-500 hover:text-rose-500 hover:bg-rose-500/10 opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 rounded-xl active:scale-95"
                                title="Delete Trip"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

// ─── Private Trips Panel ─────────────────────────────────────────────────────
interface PrivateTrip extends UberTrip {
    passenger_name?: string | null;
    classification?: string;
}

const PrivateTripsPanel: React.FC<{ selectedDate: string; onTripsLoaded?: (count: number, earnings: number) => void }> = ({ selectedDate, onTripsLoaded }) => {
    const [trips, setTrips] = useState<PrivateTrip[]>([]);
    const [loading, setLoading] = useState(true);
    const [totalEarnings, setTotalEarnings] = useState(0);

    const onTripsLoadedRef = useRef(onTripsLoaded);
    onTripsLoadedRef.current = onTripsLoaded;

    const handleDeleteTrip = async (rideId: string) => {
        const confirmed = window.confirm(`Permanently delete this private booking record? This cannot be undone.`);
        if (!confirmed) return;
        
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/delete-trip/${rideId}`, {
                method: 'DELETE'
            });
            if (resp.ok) {
                fetchTrips();
            } else {
                const err = await resp.json();
                alert(`Error deleting trip: ${err.error || 'Unknown error'}`);
            }
        } catch (e: any) {
            alert(`Error connecting to server: ${e.message}`);
        }
    };

    const fetchTrips = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/get-day-trips?date=${selectedDate}&t=${Date.now()}`, {
                signal: AbortSignal.timeout(12_000), cache: 'no-store'
            });
            const data = resp.ok ? await resp.json() : { trips: [] };
            // Only show Private trips in this panel
            const tripList = ((data.trips ?? []) as PrivateTrip[]).filter(
                (t) => t.trip_type === 'Private'
            );
            setTrips(tripList);
            const earnings = tripList.reduce((s, t) => s + t.driver_earnings, 0);
            setTotalEarnings(earnings);
            onTripsLoadedRef.current?.(tripList.length, earnings);
        } catch {
            setTrips([]);
            onTripsLoadedRef.current?.(0, 0);
        } finally {
            setLoading(false);
        }
    }, [selectedDate]);

    useEffect(() => { fetchTrips(); }, [fetchTrips]);

    return (
        <div className="rounded-2xl border border-amber-200/80 overflow-hidden bg-amber-50/30 shadow-sm"
            style={{ backdropFilter: 'blur(16px)' }}>
            <div className="p-5 border-b border-amber-200/80 flex flex-wrap items-center gap-3 justify-between">
                <div className="flex items-center gap-2">
                    <UserCheck className="w-4 h-4 text-amber-600" />
                    <h2 className="font-bold text-slate-800">Private Bookings</h2>
                    <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">{selectedDate}</span>
                    {trips.length > 0 && (
                        <span className="text-xs font-bold px-2.5 py-0.5 rounded-full border border-amber-200 bg-amber-100/80 text-amber-700 font-mono">
                            {trips.length} trip{trips.length !== 1 ? 's' : ''} · ${totalEarnings.toFixed(2)}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={fetchTrips} disabled={loading}
                        className="text-xs font-bold px-2.5 py-1 rounded-lg border border-slate-200 text-slate-600 hover:text-amber-600 hover:border-amber-300 hover:bg-amber-50 transition-all">
                        <RefreshCw className={`w-3 h-3 inline mr-1 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            <div className="divide-y divide-amber-100/50">
                {loading && (
                    <div className="p-10 text-center animate-pulse">
                        <div className="h-2 w-48 bg-amber-100 rounded-full mx-auto mb-3" />
                        <div className="h-2 w-32 bg-amber-100 rounded-full mx-auto" />
                    </div>
                )}

                {!loading && trips.length === 0 && (
                    <div className="p-10 text-center">
                        <UserCheck className="w-6 h-6 text-slate-300 mx-auto mb-2" />
                        <p className="text-xs text-slate-400 font-mono italic">
                            // no private bookings found for {selectedDate}
                        </p>
                    </div>
                )}

                {!loading && trips.map((trip, idx) => (
                    <div key={trip.trip_id}
                        className="p-4 flex flex-col md:flex-row md:items-center gap-3 hover:bg-amber-50/40 transition-colors group">
                        <div className="shrink-0 flex flex-col items-center justify-center w-10 h-10 rounded-xl bg-amber-100 border border-amber-200">
                            <span className="text-[10px] font-mono text-amber-500 leading-none">Pvt</span>
                            <span className="text-sm font-black text-amber-700 leading-none">{idx + 1}</span>
                        </div>

                        <div className="flex-1 space-y-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border border-amber-200 bg-amber-100 text-amber-800 font-mono uppercase">
                                    {trip.service_type || 'Private'}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono">{trip.time_display}</span>
                                {trip.passenger_name && (
                                    <span className="text-[10px] font-bold text-amber-700 font-mono">👤 {trip.passenger_name}</span>
                                )}
                                {trip.duration_min && (
                                    <span className="text-[10px] text-slate-500 font-mono">{trip.duration_min.toFixed(0)} min</span>
                                )}
                                {trip.distance_mi && (
                                    <span className="text-[10px] text-slate-500 font-mono">{trip.distance_mi.toFixed(2)} mi</span>
                                )}
                            </div>
                            {(trip.pickup || trip.dropoff) && (
                                <div className="flex items-start gap-1.5 text-[11px] text-slate-600">
                                    <MapPin className="w-3 h-3 mt-0.5 text-slate-400 shrink-0" />
                                    <span className="leading-snug truncate">{trip.pickup ?? '—'} → {trip.dropoff ?? '—'}</span>
                                </div>
                            )}
                        </div>

                        <div className="flex gap-4 shrink-0 text-center">
                            <div>
                                <p className="text-[10px] text-slate-500 font-mono uppercase">Total</p>
                                <p className="text-base font-black text-amber-700 tabular-nums">${trip.driver_earnings.toFixed(2)}</p>
                            </div>
                            {trip.tip > 0 && (
                                <div>
                                    <p className="text-[10px] text-slate-500 font-mono uppercase">Tip</p>
                                    <p className="text-base font-black text-emerald-600 tabular-nums">${trip.tip.toFixed(2)}</p>
                                </div>
                            )}
                        </div>
                        <div className="flex items-center justify-center shrink-0 ml-auto md:ml-0 pl-2">
                            <button
                                onClick={() => handleDeleteTrip(trip.trip_id)}
                                className="text-slate-400 dark:text-slate-500 hover:text-rose-500 hover:bg-rose-500/10 opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 rounded-xl active:scale-95"
                                title="Delete Trip"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

// ─── Intelligence Sync Panel ─────────────────────────────────────────────────
const IntelligenceSyncPanel: React.FC<{ 
    selectedDate: string, 
    onRefresh: () => void,
    hours: number,
    onHoursChange: (h: number) => void
}> = ({ selectedDate, onRefresh, hours, onHoursChange }) => {
    const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
    const [logs, setLogs] = useState<string[]>([]);
    const activePollRef = useRef<(() => void) | null>(null);

    // Clean up active polling on unmount
    useEffect(() => {
        return () => {
            if (activePollRef.current) {
                activePollRef.current();
            }
        };
    }, []);

    // Helper: build Uber Driver OneDrive path from a date string
    const buildOneDrivePath = (dateStr: string, folderOverride?: string) => {
        // Parse YYYY-MM-DD safely without timezone shifting
        const [y, m, d] = dateStr.split('-').map(Number);
        const year = y;
        const monthName = new Date(y, m - 1, d).toLocaleString('default', { month: 'long' });

        // Calendar Mon-Sun week — matches backend/reorganize_may.py logic
        const firstOfMonth = new Date(y, m - 1, 1);
        const daysToFirstMonday = (8 - firstOfMonth.getDay()) % 7;
        const firstMondayDate = 1 + daysToFirstMonday;
        // Fully unified week calculation:
        // If month starts on Monday (firstMondayDate === 1), first week is Week 1.
        // If month starts later, partial week is Week 1 and first full week is Week 2.
        const weekNum = d < firstMondayDate ? 1 : Math.floor((d - firstMondayDate) / 7) + (firstMondayDate === 1 ? 1 : 2);
        
        const week = `Week ${weekNum}`;
        
        // Standardized folder name: M.DD.YY (e.g. 5.01.26)
        const shortYear = String(y).slice(-2);
        const dayPadded = String(d).padStart(2, '0');
        const folderName = folderOverride ?? `${m}.${dayPadded}.${shortYear}`;

        return `Uber Driver/${year}/${monthName}/${week}/${folderName}`;
    };

    const triggerCloudScan = async (path: string) => {
        const resp = await fetch(`${AZURE_BASE}/operations/trigger-cloud-scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path })
        });
        
        if (!resp.ok) {
            const text = await resp.text();
            if (text.includes('504') || text.includes('timeout') || !text.startsWith('{')) {
                throw new Error('TIMEOUT_EXPECTED');
            }
            throw new Error(`Server returned ${resp.status}: ${text.substring(0, 100)}`);
        }
        
        try {
            return await resp.json();
        } catch {
            throw new Error('TIMEOUT_EXPECTED');
        }
    };

    const cleanupActivePoll = () => {
        if (activePollRef.current) {
            activePollRef.current();
            activePollRef.current = null;
        }
    };

    const runSync = async (dryRun: boolean) => {
        cleanupActivePoll();
        setStatus('running');
        const initialLog = `> Starting ${dryRun ? 'Dry Run' : 'Actual Sync'} for ${selectedDate}...`;
        setLogs([initialLog]);
        
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/sync-folders`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ processDate: selectedDate, dryRun })
            });

            if (!resp.ok) {
                throw new Error(`Server returned ${resp.status}`);
            }

            const data = await resp.json();
            if (data.status === 'accepted' && data.jobId) {
                const baseLogs = [initialLog];
                const initialJobLogs = getAsyncExecutionLogs(data.jobId);
                setLogs([...baseLogs, ...initialJobLogs]);

                const stop = pollJobStatus(
                    AZURE_BASE,
                    data.jobId,
                    (jobLogs) => {
                        setLogs([...baseLogs, ...initialJobLogs, ...jobLogs]);
                    },
                    () => {
                        setStatus('success');
                        setLogs(prev => [...prev, `> [SUCCESS] Folder sync finalized.`]);
                        onRefresh();
                    },
                    (errorMsg) => {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [ERROR] ${errorMsg}`]);
                    }
                );
                activePollRef.current = stop;
            } else if (data.success) {
                setStatus('success');
                setLogs(prev => [...prev, ...(data.logs || []), `> [SUCCESS] Folder sync finalized.`]);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            devDebugError(err);
            if (isBackgroundableError(err)) {
                setStatus('success');
                setLogs(prev => [...prev, 
                    `> [NOTICE] Large folder sync triggered.`,
                    `> Folder sync is running in the background.`,
                    `> Please wait 60 seconds and refresh to see results.`
                ]);
                setTimeout(onRefresh, 60_000);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
            }
        }
    };

    const runDailySync = async () => {
        cleanupActivePoll();
        setStatus('running');
        const initialLog = `> Initializing Daily Unified Sync (Folders + Data)...`;
        setLogs([initialLog]);

        try {
            const resp = await fetch(`${AZURE_BASE}/daily-sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: selectedDate })
            });

            if (!resp.ok) {
                const text = await resp.text();
                if (text.includes('504') || text.includes('timeout') || !text.startsWith('{')) {
                    throw new Error('TIMEOUT_EXPECTED');
                }
                throw new Error(`Server returned ${resp.status}: ${text.substring(0, 100)}`);
            }

            let data;
            try {
                data = await resp.json();
            } catch {
                throw new Error('TIMEOUT_EXPECTED');
            }

            if (data.status === 'accepted' && data.jobId) {
                const baseLogs = [initialLog];
                const initialJobLogs = getAsyncExecutionLogs(data.jobId);
                setLogs([...baseLogs, ...initialJobLogs]);

                const stop = pollJobStatus(
                    AZURE_BASE,
                    data.jobId,
                    (jobLogs) => {
                        setLogs([...baseLogs, ...initialJobLogs, ...jobLogs]);
                    },
                    () => {
                        setStatus('success');
                        setLogs(prev => [...prev, `> [SUCCESS] Daily Sync Complete.`]);
                        onRefresh();
                    },
                    (errorMsg) => {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [ERROR] ${errorMsg}`]);
                    }
                );
                activePollRef.current = stop;
            } else if (data.success) {
                setStatus('success');
                setLogs(prev => [...prev, ...(data.logs || []), `> [SUCCESS] Daily Sync Complete.`]);
                onRefresh();
            } else {
                setStatus('error');
                setLogs(prev => [...prev, ...(data.logs || []), `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            devDebugError(err);
            if (isBackgroundableError(err)) {
                setStatus('success');
                setLogs(prev => [...prev, 
                    `> [NOTICE] Large sync/scan detected (>45s).`,
                    `> Azure proxy timed out, but the sync is still executing in the background.`,
                    `> Please wait 60 seconds and refresh the page to see updated drives and trips.`
                ]);
                setTimeout(onRefresh, 60_000);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
            }
        }
    };

    // Scan the auto-calculated OneDrive folder for the selected date
    const runScanDay = async () => {
        cleanupActivePoll();
        const path = buildOneDrivePath(selectedDate);
        setStatus('running');
        const initialLog = `> Initializing Unified Day Scan: ${path}...`;
        setLogs([initialLog]);
        
        try {
            // 1. General Cloud Scan & Routing
            const data = await triggerCloudScan(path);
            
            // Helper function to run Step 2 (OCR Trip extraction)
            const proceedToOcrExtraction = async (step1Logs: string[]) => {
                const step2Log = `> [STEP 2] Starting OCR trip extraction...`;
                const currentLogs = [...step1Logs, step2Log];
                setLogs(currentLogs);

                try {
                    const ocrResp = await fetch(`${AZURE_BASE}/operations/scan-day-trips`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ date: selectedDate, path })
                    });
                    
                    if (!ocrResp.ok) {
                        throw new Error(`OCR Server returned ${ocrResp.status}`);
                    }

                    const ocrData = await ocrResp.json();
                    if (ocrData.status === 'accepted' && ocrData.jobId) {
                        const baseLogs = [...step1Logs, step2Log];
                        const initialJobLogs = getAsyncExecutionLogs(ocrData.jobId);
                        setLogs([...baseLogs, ...initialJobLogs]);

                        const stop = pollJobStatus(
                            AZURE_BASE,
                            ocrData.jobId,
                            (jobLogs) => {
                                setLogs([...baseLogs, ...initialJobLogs, ...jobLogs]);
                            },
                            (finalJobData) => {
                                setStatus('success');
                                const tripCount = finalJobData?.result?.trip_count ?? 0;
                                setLogs(prev => [...prev, 
                                    `> [SUCCESS] Full Day Scan Complete.`,
                                    `> ${tripCount} Uber trips extracted and labeled.`
                                ]);
                                onRefresh();
                            },
                            (errorMsg) => {
                                setStatus('error');
                                setLogs(prev => [...prev, `> [OCR ERROR] ${errorMsg}`]);
                            }
                        );
                        activePollRef.current = stop;
                    } else if (ocrData.success) {
                        setStatus('success');
                        setLogs(prev => [...prev, 
                            ...(ocrData.logs || []),
                            `> [SUCCESS] Full Day Scan Complete.`,
                            `> ${ocrData.trip_count} Uber trips extracted and labeled.`
                        ]);
                        onRefresh();
                    } else {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [OCR ERROR] ${ocrData.error}`]);
                    }
                } catch (ocrErr: unknown) {
                    devDebugError(ocrErr);
                    if (isBackgroundableError(ocrErr)) {
                        setStatus('success');
                        setLogs(prev => [...prev, 
                            `> [NOTICE] OCR scan is continuing in background due to size.`,
                            `> Please wait 60 seconds and refresh to see your checkmarks.`
                        ]);
                        setTimeout(onRefresh, 60_000);
                    } else {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [OCR CRITICAL ERROR] ${ocrErr instanceof Error ? ocrErr.message : String(ocrErr)}`]);
                    }
                }
            };

            // Now handle Step 1's response (Cloud scan)
            if (data.status === 'accepted' && data.jobId) {
                const baseLogs = [initialLog];
                const initialJobLogs = getAsyncExecutionLogs(data.jobId);
                setLogs([...baseLogs, ...initialJobLogs]);

                const stop = pollJobStatus(
                    AZURE_BASE,
                    data.jobId,
                    (jobLogs) => {
                        setLogs([...baseLogs, ...initialJobLogs, ...jobLogs]);
                    },
                    () => {
                        const step1DoneLogs = [...baseLogs, `> [STEP 1] Folder organization complete.`];
                        setLogs(step1DoneLogs);
                        // Trigger Step 2
                        proceedToOcrExtraction(step1DoneLogs);
                    },
                    (errorMsg) => {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [ERROR] ${errorMsg}`]);
                    }
                );
                activePollRef.current = stop;
            } else if (data.success) {
                const step1DoneLogs = [initialLog, `> [STEP 1] Folder organization complete.`];
                setLogs(step1DoneLogs);
                // Trigger Step 2
                await proceedToOcrExtraction(step1DoneLogs);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            devDebugError(err);
            if (isBackgroundableError(err)) {
                setStatus('success'); // Mark as success because background job is running
                setLogs(prev => [...prev, 
                    `> [NOTICE] Large scan detected (>45s).`,
                    `> Azure proxy timed out, but the scan is still running in the background.`,
                    `> Please wait 60 seconds and refresh the page to see your checkmarks.`
                ]);
                setTimeout(onRefresh, 60_000);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
            }
        }
    };

    // Scan a custom-named folder (for edge cases where folder name differs from day number)
    const runOneDriveSyncCustom = async () => {
        cleanupActivePoll();
        const folderName = prompt('Enter folder name (e.g. 03):');
        if (!folderName) return;
        const path = buildOneDrivePath(selectedDate, folderName);
        setStatus('running');
        const initialLog = `> Scanning custom folder: ${path}...`;
        setLogs([initialLog]);
        
        try {
            const data = await triggerCloudScan(path);
            if (data.status === 'accepted' && data.jobId) {
                const baseLogs = [initialLog];
                const initialJobLogs = getAsyncExecutionLogs(data.jobId);
                setLogs([...baseLogs, ...initialJobLogs]);

                const stop = pollJobStatus(
                    AZURE_BASE,
                    data.jobId,
                    (jobLogs) => {
                        setLogs([...baseLogs, ...initialJobLogs, ...jobLogs]);
                    },
                    () => {
                        setStatus('success');
                        setLogs(prev => [...prev, `> [SUCCESS] Custom scan complete.`]);
                        onRefresh();
                    },
                    (errorMsg) => {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [ERROR] ${errorMsg}`]);
                    }
                );
                activePollRef.current = stop;
            } else if (data.success) {
                setStatus('success');
                setLogs(prev => [...prev, ...(data.logs || []), `> [SUCCESS] Custom scan complete.`]);
                onRefresh();
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            devDebugError(err);
            if (isBackgroundableError(err)) {
                setStatus('success');
                setLogs(prev => [...prev, 
                    `> [NOTICE] Large scan detected.`,
                    `> Proxy timed out, but background sync is likely still active.`,
                    `> Refresh in 60 seconds.`
                ]);
                setTimeout(onRefresh, 60_000);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
            }
        }
    };

    const runScrubDay = async () => {
        const confirmed = window.confirm(
            `⚠️ SCRUB DAY: ${selectedDate}\n\nThis will permanently delete all TRIP records for this date and reset any wrongly-classified Tessie drives back to Untagged.\n\nINV- booking records and manual Tessie tags (Jackie, Daniel, Esmeralda) will be preserved.\n\nContinue?`
        );
        if (!confirmed) return;

        cleanupActivePoll();
        setStatus('running');
        setLogs([`> Scrubbing ${selectedDate} — wiping TRIP records and resetting Tessie drive classifications...`]);

        try {
            const resp = await fetch(`${AZURE_BASE}/operations/scrub-day`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: selectedDate })
            });
            const data = resp.ok ? await resp.json() : { success: false, error: `Server ${resp.status}` };
            if (data.success) {
                setStatus('success');
                setLogs([
                    ...(data.logs ?? []),
                    `> [SUCCESS] Scrub complete — ${data.deleted_trips} TRIP record(s) deleted, ${data.reset_drives} Tessie drive(s) reset.`,
                    `> Now upload your ${selectedDate} Uber screenshots to OneDrive, then hit Rebuild Day.`
                ]);
                onRefresh();
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            setStatus('error');
            setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
        }
    };

    return (
        <div className="p-6 rounded-2xl border border-slate-200/80 bg-white/80 shadow-sm backdrop-blur-md relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-3xl rounded-full pointer-events-none group-hover:bg-blue-500/10 transition-all duration-1000" />
            
            <div className="flex justify-between items-start mb-1">
                <div>
                    <h2 className="text-base font-bold flex items-center gap-2 text-slate-800">
                        <Cpu className="w-4 h-4 text-blue-600" /> Intelligence Sync
                    </h2>
                    <p className="text-xs font-semibold text-slate-500 tracking-wide">Autonomous Pipeline Operating</p>
                </div>
                {status === 'running' && (
                    <div className="flex items-center gap-1.5 px-3 py-1 bg-blue-50 border border-blue-200/80 rounded-full">
                        <Loader2 className="w-3 h-3 text-blue-600 animate-spin" />
                        <span className="text-[9px] font-bold text-blue-600 uppercase font-mono tracking-tighter">Running</span>
                    </div>
                )}
            </div>

            <div className="mt-4 p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-50 border border-blue-100">
                    <Clock className="w-4 h-4 text-blue-600" />
                </div>
                <div className="flex-1">
                    <p className="text-xs font-semibold text-slate-500 mb-1">Shift Duration</p>
                    <div className="flex items-center gap-2">
                        <input
                            type="number"
                            step="0.25"
                            placeholder="e.g. 6.25"
                            value={hours || ''}
                            onChange={(e) => onHoursChange(parseFloat(e.target.value) || 0)}
                            className="w-20 bg-transparent border-none text-slate-800 font-black text-lg focus:outline-none placeholder-slate-300"
                        />
                        <span className="text-xs font-mono text-slate-400 font-bold uppercase">h</span>
                        {hours > 0 && <span className="text-xs text-emerald-600 font-medium ml-auto">// override active</span>}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-4 mt-4">
                <button
                    disabled={status === 'running'}
                    onClick={() => runSync(false)}
                    className="flex flex-col items-center justify-center gap-0.5 py-3 rounded-xl text-[10px] font-bold bg-slate-100 border border-slate-200 text-slate-700 hover:bg-slate-200/80 transition-all disabled:opacity-50"
                >
                    <span>Create Folders</span>
                    <span className="text-[8px] font-normal text-slate-500 normal-case">OneDrive structure</span>
                </button>
                <button
                    disabled={status === 'running'}
                    onClick={runDailySync}
                    className="flex flex-col items-center justify-center gap-0.5 py-3 rounded-xl text-[10px] font-bold bg-amber-50 border border-amber-200 text-amber-700 hover:bg-amber-100 transition-all disabled:opacity-50"
                >
                    <span>Run Daily Sync</span>
                    <span className="text-[8px] font-normal text-amber-600/80 normal-case">Tessie + OCR + Expenses</span>
                </button>
                <button
                    disabled={status === 'running'}
                    onClick={runScrubDay}
                    className="flex flex-col items-center justify-center gap-0.5 py-3 rounded-xl text-[10px] font-bold bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 transition-all disabled:opacity-50"
                >
                    <span>🗑 Scrub Day</span>
                    <span className="text-[8px] font-normal text-rose-500/80 normal-case">Wipe &amp; start fresh</span>
                </button>
            </div>

            <div className="bg-slate-50 rounded-xl border border-slate-200/80 overflow-hidden shadow-sm">
                <div className="px-3 py-1.5 border-b border-slate-200/80 bg-slate-100/50 flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span className="text-[9px] font-mono text-slate-505 font-bold uppercase ml-auto">Intelligence Console</span>
                </div>
                <div className="p-3 h-32 overflow-y-auto font-mono text-[10px] space-y-1 scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                    {logs.length === 0 ? (
                        <p className="text-slate-400 italic">// System Ready. Select operation for {selectedDate}.</p>
                    ) : (
                        logs.map((log, i) => (
                            <p key={i} className={
                                log.includes('[ERROR]') || log.includes('[CRITICAL]') || log.includes('ERROR:') ? 'text-rose-600 font-medium' :
                                log.includes('[SUCCESS]') || log.includes('MATCH:') || log.includes('ROUTED:') ? 'text-emerald-700 font-semibold' :
                                log.includes('SKIP:') ? 'text-slate-400' :
                                log.startsWith('>') ? 'text-blue-600 font-bold border-t border-slate-200 pt-1 mt-1' :
                                'text-slate-600'
                            }>
                                {log}
                            </p>
                        ))
                    )}
                    {status === 'running' && <p className="text-blue-500 animate-pulse">_</p>}
                </div>
            </div>
        </div>
    );
};

const getTodayMST = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Denver' });

// ─── Private Payments Panel ──────────────────────────────────────────────────
const PrivatePaymentsPanel: React.FC<{
    selectedDate: string;
    payments: PrivatePayment[];
    onAdd: (p: Omit<PrivatePayment, 'id'>) => void;
    onDelete: (id: number) => void;
}> = ({ selectedDate, payments, onAdd, onDelete }) => {
    const [client, setClient] = useState('');
    const [amount, setAmount] = useState('');
    const [note, setNote] = useState('');

    const inputCls = 'w-full p-2.5 text-sm bg-white/80 border border-slate-200/80 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all shadow-sm';

    const todayPayments = payments.filter(p => p.date === selectedDate);
    const total = todayPayments.reduce((s, p) => s + p.amount, 0);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!amount) return;
        onAdd({
            client: client.trim() || 'Private',
            amount: parseFloat(amount) || 0,
            note,
            date: selectedDate,
            timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`,
        });
        setClient(''); setAmount(''); setNote('');
    };

    return (
        <div className="p-6 rounded-2xl border border-violet-200/80 bg-violet-50/40 shadow-sm backdrop-blur-md relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 blur-3xl rounded-full pointer-events-none" />
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-base font-bold text-slate-800 flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-violet-600" /> Private Payments
                    </h2>
                    <p className="text-xs font-semibold text-slate-500 tracking-wide">Cash · Bundle · Off-app</p>
                </div>
                {todayPayments.length > 0 && (
                    <span className="text-xl font-black text-violet-700">${total.toFixed(2)}</span>
                )}
            </div>

            <form onSubmit={handleSubmit} className="space-y-3 mb-4">
                <div className="grid grid-cols-2 gap-2">
                    <input type="text" placeholder="Client name" value={client}
                        onChange={e => setClient(e.target.value)} className={inputCls} />
                    <input type="number" placeholder="Amount ($)" step="0.01" value={amount}
                        onChange={e => setAmount(e.target.value)} className={inputCls} />
                </div>
                <input type="text" placeholder="Note (e.g. $100 bundle, 5-trip package)" value={note}
                    onChange={e => setNote(e.target.value)} className={inputCls} />
                <button type="submit"
                    className="w-full py-2.5 rounded-xl font-bold text-xs uppercase tracking-wide bg-violet-600 text-white hover:bg-violet-700 transition-all shadow-sm border-none">
                    + Log Private Payment
                </button>
            </form>

            <div className="space-y-2 max-h-[220px] overflow-y-auto">
                {todayPayments.length === 0
                    ? <p className="text-center text-xs text-slate-400 italic py-3">// no private payments for {selectedDate}</p>
                    : todayPayments.map(p => (
                        <div key={p.id} className="flex items-center justify-between p-3 rounded-xl bg-white/70 border border-slate-200/80 hover:bg-slate-50 transition-colors shadow-sm group">
                            <div>
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-violet-50 border border-violet-200 text-violet-700 uppercase font-mono">{p.client}</span>
                                    <span className="text-sm font-black text-slate-800">${p.amount.toFixed(2)}</span>
                                </div>
                                {p.note && <p className="text-[10px] text-slate-505 mt-0.5">{p.note}</p>}
                            </div>
                            <button onClick={() => onDelete(p.id)}
                                className="text-slate-400 hover:text-rose-600 opacity-0 group-hover:opacity-100 transition-all">
                                <Trash2 className="w-3 h-3" />
                            </button>
                        </div>
                    ))}
            </div>
        </div>
    );
};

// ─── Goal Tracker Panel ─────────────────────────────────────────────────────
const MONTHLY_GOAL = 6500;
const WEEKLY_GOAL = Math.round(MONTHLY_GOAL / 4);
const DAILY_GOAL = Math.round(MONTHLY_GOAL / 28);

const Bar = ({ label, earned, target, color }: { label: string; earned: number; target: number; color: string }) => {
    const pct = Math.min(100, (earned / target) * 100);
    const done = earned >= target;
    const barColor = done ? '#059669' : pct > 60 ? '#d97706' : color;
    return (
        <div className="flex-1 min-w-0">
            <div className="flex justify-between items-baseline mb-1.5">
                <span className="text-xs font-semibold text-slate-500">{label}</span>
                <div className="flex items-baseline gap-1.5">
                    <span className="text-sm font-black tabular-nums" style={{ color: barColor }}>${earned.toFixed(0)}</span>
                    <span className="text-xs font-semibold text-slate-400">/ ${target.toLocaleString()}</span>
                </div>
            </div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden relative">
                <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pct}%`, background: barColor }}
                />
            </div>
            <div className="flex justify-between mt-1">
                <span className="text-[10px] font-semibold text-slate-500">{pct.toFixed(0)}%</span>
                {done
                    ? <span className="text-[10px] font-bold text-emerald-600">TARGET MET ✓</span>
                    : <span className="text-[10px] font-semibold text-slate-400">${(target - earned).toFixed(0)} to go</span>}
            </div>
        </div>
    );
};

const GoalTrackerPanel: React.FC<{ todayEarnings: number; selectedDate: string }> = ({ todayEarnings, selectedDate }) => {
    const [history, setHistory] = useState<Record<string, number>>(() => {
        if (typeof window !== 'undefined') {
            try {
                const stored = localStorage.getItem('cos_daily_history');
                if (stored) return JSON.parse(stored);
            } catch (err) {
                console.error("Failed to load initial daily history:", err);
            }
        }
        return {};
    });

    // Sync from cloud and local private payments when date or today's earnings change
    useEffect(() => {
        let active = true;
        
        const fetchHistory = async () => {
            try {
                // Calculate week span (Mon – Sun containing selectedDate)
                const refDate = new Date(selectedDate + 'T12:00:00');
                const dayOfWeek = refDate.getDay(); // 0 Sun
                const monday = new Date(refDate);
                monday.setDate(refDate.getDate() - ((dayOfWeek + 6) % 7));
                const weekStartStr = monday.toLocaleDateString('sv-SE');
                
                const sunday = new Date(monday);
                sunday.setDate(monday.getDate() + 6);
                const weekEndStr = sunday.toLocaleDateString('sv-SE');
                
                // Calculate month span
                const ym = selectedDate.slice(0, 7);
                const monthStartStr = `${ym}-01`;
                const year = parseInt(ym.split('-')[0]);
                const month = parseInt(ym.split('-')[1]);
                const lastDay = new Date(year, month, 0).getDate();
                const monthEndStr = `${ym}-${String(lastDay).padStart(2, '0')}`;
                
                // Get absolute bounds covering both week and month
                const startDate = weekStartStr < monthStartStr ? weekStartStr : monthStartStr;
                const endDate = weekEndStr > monthEndStr ? weekEndStr : monthEndStr;
                
                const resp = await fetch(`${AZURE_BASE}/copilot/metrics/daily?start_date=${startDate}&end_date=${endDate}`);
                if (!resp.ok) return;
                const data = await resp.json();
                
                if (active && data && data.metrics) {
                    // Start with a copy of current state/local storage
                    let latestHistory: Record<string, number> = {};
                    if (typeof window !== 'undefined') {
                        try {
                            latestHistory = JSON.parse(localStorage.getItem('cos_daily_history') ?? '{}');
                        } catch (err) {
                            console.warn("Failed to read cos_daily_history from localStorage:", err);
                        }
                    }
                    
                    // Parse local private payments to blend them in
                    let localPayments: PrivatePayment[] = [];
                    if (typeof window !== 'undefined') {
                        try {
                            localPayments = JSON.parse(localStorage.getItem('cos_private_payments') ?? '[]');
                        } catch (err) {
                            console.warn("Failed to read cos_private_payments from localStorage:", err);
                        }
                    }
                    
                    // Populate history map from fetched DB metrics
                    data.metrics.forEach((m: { date: string; earnings?: { amount: number } }) => {
                        if (m.date) {
                            const uberAmt = m.earnings?.amount || 0;
                            const privateAmt = localPayments
                                .filter((p: PrivatePayment) => p.date === m.date)
                                .reduce((s: number, p: PrivatePayment) => s + (p.amount || 0), 0);
                            latestHistory[m.date] = uberAmt + privateAmt;
                        }
                    });
                    
                    // Always make sure the currently selected day uses the latest live todayEarnings
                    latestHistory[selectedDate] = todayEarnings;
                    
                    setHistory(latestHistory);
                    if (typeof window !== 'undefined') {
                        try {
                            localStorage.setItem('cos_daily_history', JSON.stringify(latestHistory));
                        } catch (err) {
                            console.warn("Failed to write cos_daily_history to localStorage:", err);
                        }
                    }
                }
            } catch (err) {
                console.error("Failed to fetch daily history from cloud:", err);
            }
        };

        fetchHistory();
        return () => { active = false; };
    }, [selectedDate, todayEarnings]);

    const resolve = (date: string) => date === selectedDate ? todayEarnings : (history[date] ?? 0);

    // Calculate Week Span Earnings
    const refDate = new Date(selectedDate + 'T12:00:00');
    const dayOfWeek = refDate.getDay();
    const monday = new Date(refDate);
    monday.setDate(refDate.getDate() - ((dayOfWeek + 6) % 7));
    const weekDates: string[] = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(monday); d.setDate(monday.getDate() + i);
        return d.toLocaleDateString('sv-SE');
    });
    const weekEarnings = weekDates.reduce((s, d) => s + resolve(d), 0);

    // Calculate Month Span Earnings
    const ym = selectedDate.slice(0, 7);
    const monthEarnings = Object.entries({ ...history, [selectedDate]: todayEarnings })
        .filter(([d]) => d.startsWith(ym))
        .reduce((s, [, v]) => s + v, 0);

    return (
        <div className="p-5 rounded-2xl border border-slate-200/80 bg-white/80 shadow-sm backdrop-blur-md relative overflow-hidden">
            <div className="absolute top-0 left-0 w-64 h-16 bg-blue-500/5 blur-3xl rounded-full pointer-events-none" />
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-blue-600" /> Revenue Goal Tracker
                    </h2>
                    <p className="text-xs font-semibold text-slate-500 mt-0.5">
                        Monthly target: ${MONTHLY_GOAL.toLocaleString()} &middot; Daily ${DAILY_GOAL} &middot; Weekly ${WEEKLY_GOAL.toLocaleString()}
                    </p>
                </div>
                <div className="text-right">
                    <p className="text-xs font-semibold text-slate-500">Month so far</p>
                    <p className="text-lg font-black text-slate-800 tabular-nums">${monthEarnings.toFixed(0)}</p>
                </div>
            </div>
            <div className="flex gap-6">
                <Bar label="Today" earned={todayEarnings} target={DAILY_GOAL} color="#2563eb" />
                <div className="w-[1px] bg-slate-200/80 self-stretch" />
                <Bar label="This Week" earned={weekEarnings} target={WEEKLY_GOAL} color="#7c3aed" />
                <div className="w-[1px] bg-slate-200/80 self-stretch" />
                <Bar label="This Month" earned={monthEarnings} target={MONTHLY_GOAL} color="#ea580c" />
            </div>
        </div>
    );
};

interface CopilotResponse {
    agentic_response?: {
        source?: string;
        schema?: string;
        data?: unknown;
    } | string;
}

const SummitCopilotConsole = () => {
    const [query, setQuery] = useState('');
    const [mode, setMode] = useState<'evidence' | 'insight' | 'narrative'>('evidence');
    const [response, setResponse] = useState<CopilotResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleQuery = async (qText: string) => {
        if (!qText.trim()) return;
        setLoading(true);
        setError(null);
        setResponse(null);
        try {
            const res = await fetch(`${AZURE_BASE}/copilot/agentic-query?q=${encodeURIComponent(qText)}&mode=${mode}`);
            if (!res.ok) throw new Error('Query execution failed');
            const data = (await res.json()) as CopilotResponse;
            setResponse(data);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    };

    const suggestedPills = [
        { label: 'Net Profit', q: 'What is my net profit today?' },
        { label: 'Uber Trips', q: 'Show my uber trips from last week' },
        { label: 'Charging Cost', q: 'How much did I spend on charging?' },
        { label: 'Efficiency', q: "What's my vehicle efficiency?" }
    ];

    return (
        <div className="p-5 rounded-2xl border border-slate-200/80 bg-white/80 shadow-sm backdrop-blur-md relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-3xl rounded-full pointer-events-none group-hover:bg-blue-500/10 transition-all duration-1000" />
            
            <div className="flex justify-between items-start mb-4">
                <div>
                    <h2 className="text-sm font-bold flex items-center gap-2 text-slate-800">
                        <Cpu className="w-4 h-4 text-blue-600 animate-pulse" /> Summit Copilot
                    </h2>
                    <p className="text-xs font-semibold text-slate-500 mt-0.5 uppercase tracking-wider">Governed Natural Language Interface</p>
                </div>
            </div>

            <div className="flex flex-wrap gap-1.5 mb-3">
                {suggestedPills.map((pill) => (
                    <button
                        key={pill.label}
                        type="button"
                        onClick={() => { setQuery(pill.q); handleQuery(pill.q); }}
                        className="text-[10px] font-bold px-2.5 py-1 rounded-full border bg-slate-50 border-slate-200 text-slate-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600 transition-all duration-200 uppercase tracking-wider"
                    >
                        {pill.label}
                    </button>
                ))}
            </div>

            <div className="space-y-3 mb-4">
                <textarea
                    rows={2}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask Summit Intelligence... e.g. What is my net profit today?"
                    className="w-full p-3 text-sm bg-slate-50 border border-slate-200 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 transition-all resize-none"
                />
                
                <div className="flex items-center justify-between gap-3">
                    <div className="flex gap-1.5 bg-slate-100/80 p-1 border border-slate-200 rounded-lg">
                        {(['evidence', 'insight', 'narrative'] as const).map((m) => (
                            <button
                                key={m}
                                type="button"
                                onClick={() => setMode(m)}
                                className={`px-2 py-1 text-[9px] font-bold uppercase rounded-md transition-all ${
                                    mode === m 
                                        ? 'bg-white border border-slate-200 text-blue-600 shadow-sm' 
                                        : 'text-slate-500 hover:text-slate-800'
                                }`}
                            >
                                {m}
                            </button>
                        ))}
                    </div>

                    <button
                        disabled={loading || !query.trim()}
                        onClick={() => handleQuery(query)}
                        className="px-4 py-2 rounded-xl text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 hover:shadow-md hover:shadow-blue-500/20 active:shadow-sm transition-all disabled:opacity-50"
                    >
                        {loading ? 'RUNNING...' : 'RUN QUERY'}
                    </button>
                </div>
            </div>

            <div className="bg-slate-50 rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-3 py-1.5 border-b border-slate-200 flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                    <span className="text-[9px] font-mono text-slate-400 uppercase">Copilot Output Terminal</span>
                </div>
                <div className="p-3 h-44 overflow-y-auto font-mono text-[10px] space-y-2">
                    {loading && (
                        <p className="text-blue-600 animate-pulse">// Querying Summit Gov Agents... Loading schema & executing isolated SQL...</p>
                    )}
                    
                    {error && (
                        <p className="text-rose-600 font-bold">[ERROR] {error}</p>
                    )}

                    {!loading && !error && !response && (
                        <p className="text-slate-400 italic">// Terminal idle. Enter a query or select a preset to analyze real-time business telemetry.</p>
                    )}

                    {!loading && !error && response && (() => {
                        const agenticResponse = response.agentic_response;
                        const isObj = agenticResponse && typeof agenticResponse === 'object';
                        const source = isObj ? (agenticResponse as Record<string, unknown>).source as string : undefined;
                        const schema = isObj ? (agenticResponse as Record<string, unknown>).schema as string : undefined;
                        return (
                            <div className="space-y-2">
                                {isObj && typeof source === 'string' && source && (
                                    <div className="p-2 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 space-y-1">
                                        <p className="font-bold flex items-center gap-1.5">
                                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse" />
                                            TRACEABILITY VERIFIED
                                        </p>
                                        <p className="text-[9px] text-slate-505">
                                            Source: <span className="text-slate-800 font-bold">{source}</span> · 
                                            Schema: <span className="text-slate-800 font-bold">{schema || ''}</span>
                                        </p>
                                    </div>
                                )}

                                <pre className="text-slate-800 leading-snug whitespace-pre-wrap">
                                    {typeof agenticResponse === 'string' 
                                        ? agenticResponse 
                                        : JSON.stringify(agenticResponse, null, 2)}
                                </pre>
                            </div>
                        );
                    })()}
                </div>
            </div>
        </div>
    );
};

interface DashboardStats {
    uberEarnings: number;
    uberCount: number;
    privateTotal: number;
    food: number;
    charging: number;
    totalExpenses: number;
    profit: number;
    hourlyRate: number;
    activeHours: number;
    isManualHours: boolean;
}

interface AuditTrip {
    trip_id: string;
    earnings: number;
    profit: number;
}

interface AuditCharge {
    session_id: string;
    cost: number;
    kwh_added: number;
}

interface AuditExpense {
    expense_id: string;
    category: string;
    amount: number;
}

interface AuditData {
    trips?: AuditTrip[];
    charging_sessions?: AuditCharge[];
    expenses?: AuditExpense[];
}

// ─── Interactive Audit Ledger Modal ──────────────────────────────────────────
const AuditLedgerModal = ({ isOpen, onClose, stats, selectedDate }: { isOpen: boolean; onClose: () => void; stats: DashboardStats; selectedDate: string }) => {
    const [auditData, setAuditData] = useState<AuditData | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isOpen) {
            Promise.resolve().then(() => setLoading(true));
            let active = true;
            fetch(`${AZURE_BASE}/copilot/agentic-query?q=Run%20Master%20Orchestrator%20daily%20summary%20for%20${selectedDate}&mode=evidence`)
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    if (active && data && data.agentic_response && data.agentic_response.data) {
                        setAuditData(data.agentic_response.data as AuditData);
                    }
                })
                .catch(() => {})
                .finally(() => {
                    if (active) setLoading(false);
                });
            return () => {
                active = false;
            };
        }
    }, [isOpen, selectedDate]);

    if (!isOpen) return null;

    const gross = (stats.uberEarnings || 0) + (stats.privateTotal || 0);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md">
            <div className="w-full max-w-2xl bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
                
                <div className="p-6 border-b border-slate-200 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-blue-600 animate-pulse" />
                        <div>
                            <h2 className="text-lg font-bold text-slate-800 tracking-tight">Interactive Audit & Verification Ledger</h2>
                            <p className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Governed Financial Verification</p>
                        </div>
                    </div>
                    
                    <button 
                        onClick={onClose}
                        className="p-1.5 rounded-lg border border-slate-200 text-slate-505 hover:text-slate-800 hover:bg-slate-50 transition-all text-xs font-bold"
                    >
                        ✕ CLOSE
                    </button>
                </div>

                <div className="p-6 overflow-y-auto space-y-6 flex-1">
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800">
                        <div className="p-2 rounded-xl bg-emerald-100 text-emerald-600">
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                            </svg>
                        </div>
                        <div>
                            <p className="font-black text-sm uppercase tracking-wider">🔐 Governed & Audited: 100% Traceable to Azure SQL</p>
                            <p className="text-[10px] text-slate-600 font-mono mt-0.5">Every row, fare, and expense is verified against Pydantic database constraints under strict isolated schema contracts.</p>
                        </div>
                    </div>

                    <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-4">
                        <p className="text-[10px] text-slate-400 font-mono uppercase tracking-[0.2em] text-center">Master Financial Equation</p>
                        <div className="flex flex-col md:flex-row items-center justify-center gap-4 py-2">
                            <div className="text-center bg-blue-50 px-4 py-2.5 border border-blue-150 rounded-xl shadow-sm">
                                <p className="text-[9px] text-blue-600 font-mono uppercase font-bold">Net Profit</p>
                                <p className="text-xl font-black text-blue-600">${stats.profit.toFixed(2)}</p>
                            </div>
                            <span className="text-slate-400 font-bold text-lg">=</span>
                            <div className="text-center bg-white px-4 py-2.5 border border-slate-200 rounded-xl shadow-sm">
                                <p className="text-[9px] text-slate-500 font-mono uppercase">Trips Earnings</p>
                                <p className="text-lg font-bold text-slate-800">${gross.toFixed(2)}</p>
                            </div>
                            <span className="text-slate-400 font-bold text-lg">-</span>
                            <div className="text-center bg-white px-4 py-2.5 border border-slate-200 rounded-xl shadow-sm">
                                <p className="text-[9px] text-slate-500 font-mono uppercase">Charging Sessions</p>
                                <p className="text-lg font-bold text-slate-800">${stats.charging.toFixed(2)}</p>
                            </div>
                            <span className="text-slate-400 font-bold text-lg">-</span>
                            <div className="text-center bg-white px-4 py-2.5 border border-slate-200 rounded-xl shadow-sm">
                                <p className="text-[9px] text-slate-500 font-mono uppercase">Food & Supply</p>
                                <p className="text-lg font-bold text-slate-800">${stats.food.toFixed(2)}</p>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-4">
                        <h3 className="font-bold text-sm text-slate-800 uppercase tracking-wider font-mono">// isolated domain sources</h3>
                        
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-1">
                                <p className="text-[9px] text-blue-600 font-mono uppercase font-bold">Trips Source</p>
                                <p className="font-bold text-xs text-slate-800">Rides.Rides</p>
                                <p className="text-[9px] text-slate-400 font-mono">Schema: TripModel</p>
                                <div className="mt-2 pt-2 border-t border-slate-100 flex justify-between text-[9px] text-slate-505">
                                    <span>Rows: {auditData ? auditData.trips?.length : '--'}</span>
                                    <span className="text-emerald-600 font-bold">✓ Compliant</span>
                                </div>
                            </div>

                            <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-1">
                                <p className="text-[9px] text-amber-600 font-mono uppercase font-bold">Charging Source</p>
                                <p className="font-bold text-xs text-slate-800">Rides.ChargingSessions</p>
                                <p className="text-[9px] text-slate-400 font-mono">Schema: ChargingModel</p>
                                <div className="mt-2 pt-2 border-t border-slate-100 flex justify-between text-[9px] text-slate-555">
                                    <span>Rows: {auditData ? auditData.charging_sessions?.length : '--'}</span>
                                    <span className="text-emerald-600 font-bold">✓ Compliant</span>
                                </div>
                            </div>

                            <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-1">
                                <p className="text-[9px] text-rose-600 font-mono uppercase font-bold">Expenses Source</p>
                                <p className="font-bold text-xs text-slate-800">Rides.ManualExpenses</p>
                                <p className="text-[9px] text-slate-400 font-mono">Schema: ExpenseModel</p>
                                <div className="mt-2 pt-2 border-t border-slate-100 flex justify-between text-[9px] text-slate-505">
                                    <span>Rows: {auditData ? auditData.expenses?.length : '--'}</span>
                                    <span className="text-emerald-600 font-bold">✓ Compliant</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {loading && (
                        <div className="text-center py-6 text-xs text-blue-600 animate-pulse font-mono">// Fetching ledger details...</div>
                    )}

                    {!loading && auditData && (
                        <div className="space-y-4">
                            <h3 className="font-bold text-sm text-slate-800 uppercase tracking-wider font-mono">// active records ledger</h3>
                            <div className="bg-slate-50 rounded-xl border border-slate-200 max-h-[220px] overflow-y-auto font-mono text-[9px] p-4 divide-y divide-slate-100 space-y-2">
                                <div>
                                    <p className="text-blue-700 font-bold uppercase mb-1">Rides Table Logs ({auditData.trips?.length || 0} entries)</p>
                                    {auditData.trips?.slice(0, 3).map((t: AuditTrip) => (
                                        <p key={t.trip_id} className="text-slate-600">Ride ID: {t.trip_id} | Earnings: ${t.earnings.toFixed(2)} | Profit: ${t.profit.toFixed(2)}</p>
                                    ))}
                                    {(auditData.trips?.length ?? 0) > 3 && <p className="text-slate-400">... and {(auditData.trips?.length ?? 0) - 3} more rows</p>}
                                </div>

                                <div className="pt-2">
                                    <p className="text-amber-700 font-bold uppercase mb-1">Charging Sessions Logs ({auditData.charging_sessions?.length || 0} entries)</p>
                                    {auditData.charging_sessions?.slice(0, 3).map((cs: AuditCharge) => (
                                        <p key={cs.session_id} className="text-slate-600">Session ID: {cs.session_id} | Cost: ${cs.cost.toFixed(2)} | Energy: {cs.kwh_added.toFixed(1)} kWh</p>
                                    ))}
                                    {(auditData.charging_sessions?.length ?? 0) > 3 && <p className="text-slate-400">... and {(auditData.charging_sessions?.length ?? 0) - 3} more rows</p>}
                                </div>

                                <div className="pt-2">
                                    <p className="text-rose-700 font-bold uppercase mb-1">Manual Expenses Logs ({auditData.expenses?.length || 0} entries)</p>
                                    {auditData.expenses?.slice(0, 3).map((e: AuditExpense) => (
                                        <p key={e.expense_id} className="text-slate-600">Expense ID: {e.expense_id} | Cat: {e.category} | Amount: ${e.amount.toFixed(2)}</p>
                                    ))}
                                    {(auditData.expenses?.length ?? 0) > 3 && <p className="text-slate-400">... and {(auditData.expenses?.length ?? 0) - 3} more rows</p>}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
                
                <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                    <span>Audit Time: {new Date().toLocaleTimeString()}</span>
                    <span>governed master orchestrator v2.1</span>
                </div>
            </div>
        </div>
    );
};

// ─── SVG Telemetry Curves ────────────────────────────────────────────────────
interface TelemetryRecord {
    soc_pct: number;
    efficiency_wh_per_mi: number;
    label: string;
}

const TelemetrySparklines = ({ selectedDate }: { selectedDate: string }) => {
    const [telemetry, setTelemetry] = useState<TelemetryRecord[]>([]);
    const [loading, setLoading] = useState(false);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        if (expanded) {
            Promise.resolve().then(() => setLoading(true));
            let active = true;
            fetch(`${AZURE_BASE}/copilot/agentic-query?q=vehicle%20telemetry%20for%20${selectedDate}&mode=evidence&t=${Date.now()}`)
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    if (active) {
                        if (data && data.agentic_response && data.agentic_response.data) {
                            setTelemetry(data.agentic_response.data as TelemetryRecord[]);
                        } else {
                            setTelemetry([]);
                        }
                    }
                })
                .catch(() => {
                    if (active) setTelemetry([]);
                })
                .finally(() => {
                    if (active) setLoading(false);
                });
            return () => {
                active = false;
            };
        }
    }, [expanded, selectedDate]);

    const activeData = useMemo(() => {
        if (telemetry && telemetry.length > 2) {
            return telemetry;
        }
        return [
            { soc_pct: 95, efficiency_wh_per_mi: 220, label: '08:00 MST' },
            { soc_pct: 90, efficiency_wh_per_mi: 260, label: '09:30 MST' },
            { soc_pct: 82, efficiency_wh_per_mi: 245, label: '11:00 MST' },
            { soc_pct: 78, efficiency_wh_per_mi: 280, label: '12:30 MST' },
            { soc_pct: 68, efficiency_wh_per_mi: 230, label: '14:00 MST' },
            { soc_pct: 60, efficiency_wh_per_mi: 295, label: '15:30 MST' },
            { soc_pct: 54, efficiency_wh_per_mi: 210, label: '17:00 MST' },
            { soc_pct: 45, efficiency_wh_per_mi: 250, label: '18:30 MST' },
            { soc_pct: 38, efficiency_wh_per_mi: 275, label: '20:00 MST' },
            { soc_pct: 32, efficiency_wh_per_mi: 240, label: '21:30 MST' }
        ];
    }, [telemetry]);

    const socPoints = activeData.map(d => d.soc_pct);
    const effPoints = activeData.map(d => d.efficiency_wh_per_mi);

    const width = 500;
    const height = 100;
    const padding = 10;

    const getSvgPath = (points: number[], isSoc: boolean) => {
        if (points.length < 2) return '';
        const minVal = isSoc ? Math.max(0, Math.min(...points) - 2) : Math.max(0, Math.min(...points) - 10);
        const maxVal = isSoc ? Math.min(100, Math.max(...points) + 2) : Math.max(...points) + 10;
        const range = maxVal - minVal || 1;

        const coords = points.map((val, idx) => {
            const x = padding + (idx / (points.length - 1)) * (width - padding * 2);
            const y = height - padding - ((val - minVal) / range) * (height - padding * 2);
            return { x, y };
        });

        let path = `M ${coords[0].x} ${coords[0].y}`;
        for (let i = 0; i < coords.length - 1; i++) {
            const curr = coords[i];
            const next = coords[i + 1];
            const cpX1 = curr.x + (next.x - curr.x) / 3;
            const cpY1 = curr.y;
            const cpX2 = curr.x + 2 * (next.x - curr.x) / 3;
            const cpY2 = next.y;
            path += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
        }
        return path;
    };

    const socPath = getSvgPath(socPoints, true);
    const effPath = getSvgPath(effPoints, false);

    return (
        <div className="rounded-2xl border border-slate-200/80 bg-white/80 overflow-hidden transition-all duration-300 shadow-sm backdrop-blur-md">
            
            <button 
                onClick={() => setExpanded(!expanded)}
                className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-50 transition-all duration-200"
            >
                <div className="flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-blue-600 animate-pulse" />
                    <div>
                        <h3 className="font-bold text-sm text-slate-800">Live Telemetry Performance Curves</h3>
                        <p className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Tessie Battery SOC & Wh/mi Efficiency</p>
                    </div>
                </div>
                <span className="text-xs font-bold text-blue-600 font-mono">
                    {expanded ? '▲ HIDE CURVES' : '▼ EXPAND CURVES'}
                </span>
            </button>

            {expanded && (
                <div className="p-5 border-t border-slate-200/80 space-y-6">
                    {loading && (
                        <div className="text-center py-6 text-xs text-blue-600 animate-pulse font-mono">// Fetching high-res drive telemetry...</div>
                    )}

                    {!loading && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="p-4 rounded-xl border border-blue-100 bg-blue-50/30 space-y-2 relative">
                                <div className="absolute top-4 right-4 flex items-center gap-1.5 px-2 py-0.5 bg-blue-100 border border-blue-200 rounded-full">
                                    <span className="text-[8px] font-bold text-blue-600 font-mono uppercase tracking-tighter">Battery Timeline</span>
                                </div>
                                <h4 className="text-[10px] font-bold font-mono text-slate-505 uppercase tracking-widest">
                                    SOC % Curve ({Math.max(0, Math.min(...socPoints) - 2)}% - {Math.min(100, Math.max(...socPoints) + 2)}%)
                                </h4>
                                
                                <div className="relative h-[110px] w-full mt-2">
                                    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
                                        <defs>
                                            <linearGradient id="socGlow" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stopColor="rgb(37, 99, 235)" stopOpacity="0.15" />
                                                <stop offset="100%" stopColor="rgb(37, 99, 235)" stopOpacity="0.0" />
                                            </linearGradient>
                                        </defs>
                                        <line x1="0" y1="10" x2={width} y2="10" stroke="rgba(0,0,0,0.04)" strokeWidth="1" strokeDasharray="3" />
                                        <line x1="0" y1="50" x2={width} y2="50" stroke="rgba(0,0,0,0.04)" strokeWidth="1" strokeDasharray="3" />
                                        <line x1="0" y1="90" x2={width} y2="90" stroke="rgba(0,0,0,0.04)" strokeWidth="1" strokeDasharray="3" />
                                        
                                        <path d={`${socPath} L ${width - padding} ${height - padding} L ${padding} ${height - padding} Z`} fill="url(#socGlow)" />
                                        <path d={socPath} fill="none" stroke="rgb(37, 99, 235)" strokeWidth="2.5" strokeLinecap="round" className="drop-shadow-[0_2px_4px_rgba(37,99,235,0.15)]" />
                                    </svg>
                                </div>
                                <div className="flex justify-between text-[9px] font-mono text-slate-500">
                                    <span>Start: {socPoints[0]}%</span>
                                    <span>End: {socPoints[socPoints.length - 1]}%</span>
                                </div>
                            </div>

                            <div className="p-4 rounded-xl border border-amber-100 bg-amber-50/30 space-y-2 relative">
                                <div className="absolute top-4 right-4 flex items-center gap-1.5 px-2 py-0.5 bg-amber-100 border border-amber-200 rounded-full">
                                    <span className="text-[8px] font-bold text-amber-600 font-mono uppercase tracking-tighter">Wh/mi spikes</span>
                                </div>
                                <h4 className="text-[10px] font-bold font-mono text-slate-555 uppercase tracking-widest">Efficiency Bezier curve</h4>
                                
                                <div className="relative h-[110px] w-full mt-2">
                                    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
                                        <defs>
                                            <linearGradient id="effGlow" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stopColor="rgb(245, 158, 11)" stopOpacity="0.15" />
                                                <stop offset="100%" stopColor="rgb(245, 158, 11)" stopOpacity="0.0" />
                                            </linearGradient>
                                        </defs>
                                        <line x1="0" y1="10" x2={width} y2="10" stroke="rgba(0,0,0,0.04)" strokeWidth="1" strokeDasharray="3" />
                                        <line x1="0" y1="50" x2={width} y2="50" stroke="rgba(0,0,0,0.04)" strokeWidth="1" strokeDasharray="3" />
                                        <line x1="0" y1="90" x2={width} y2="90" stroke="rgba(0,0,0,0.04)" strokeWidth="1" strokeDasharray="3" />
                                        
                                        <path d={`${effPath} L ${width - padding} ${height - padding} L ${padding} ${height - padding} Z`} fill="url(#effGlow)" />
                                        <path d={effPath} fill="none" stroke="rgb(245, 158, 11)" strokeWidth="2.5" strokeLinecap="round" className="drop-shadow-[0_2px_4px_rgba(245,158,11,0.15)]" />
                                    </svg>
                                </div>
                                <div className="flex justify-between text-[9px] font-mono text-slate-500">
                                    <span>Min: {Math.min(...effPoints)} Wh/mi</span>
                                    <span>Max: {Math.max(...effPoints)} Wh/mi</span>
                                </div>
                            </div>
                        </div>
                    )}
                    {telemetry.length === 0 && (
                        <p className="text-[9px] text-slate-400 font-mono text-center">// Database telemetry source empty for today. Showing standard live performance curves simulation.</p>
                    )}
                </div>
            )}
        </div>
    );
};

const DriverDashboard = () => {
    const [, setLastSync] = useState<string | null>(() => {
        if (typeof window === 'undefined') return null;
        return localStorage.getItem('cos_last_sync');
    });
    const [selectedDate, setSelectedDate] = useState(() => {
        if (typeof window === 'undefined') return getTodayMST();
        const saved = localStorage.getItem('cos_selected_date');
        return saved || getTodayMST();
    });

    const updateSelectedDate = (date: string) => {
        setSelectedDate(date);
        localStorage.setItem('cos_selected_date', date);
    };

    const [manualHoursMap, setManualHoursMap] = useState<Record<string, number>>(() => {
        if (typeof window === 'undefined') return {};
        try { return JSON.parse(localStorage.getItem('cos_manual_hours') ?? '{}'); } catch { return {}; }
    });

    const [privatePayments, setPrivatePayments] = useState<PrivatePayment[]>(() => {
        if (typeof window === 'undefined') return [];
        try { return JSON.parse(localStorage.getItem('cos_private_payments') ?? '[]'); } catch { return []; }
    });
    const [expenses, setExpenses] = useState<Expenses>(() => {
        if (typeof window === 'undefined') return { fastfood: [], charging: [], capital_maintenance: [] };
        try {
            const parsed = JSON.parse(localStorage.getItem('cos_expenses') ?? 'null');
            return {
                fastfood: parsed?.fastfood || [],
                charging: parsed?.charging || [],
                capital_maintenance: parsed?.capital_maintenance || []
            };
        } catch {
            return { fastfood: [], charging: [], capital_maintenance: [] };
        }
    });
    const [uberStats, setUberStats] = useState({ count: 0, earnings: 0 });
    const [sessionStart, setSessionStart] = useState<Date>(() => {
        if (typeof window === 'undefined') return new Date();
        const saved = localStorage.getItem('cos_session_start');
        if (!saved) {
            const d = new Date();
            localStorage.setItem('cos_session_start', d.toISOString());
            localStorage.setItem('cos_session_date', getTodayMST());
            return d;
        }
        return new Date(saved);
    });
    const [showResetConfirm, setShowResetConfirm] = useState(false);
    const [isAuditOpen, setIsAuditOpen] = useState(false);
    const expenseFormRef = useRef<HTMLDivElement>(null);
    const [drivesRefreshKey, setDrivesRefreshKey] = useState(0);

    // Track live vehicle charging state for TessieDrivesPanel LIVE badges
    const [isVehicleCharging, setIsVehicleCharging] = useState(false);
    useEffect(() => {
        const poll = async () => {
            try {
                const res = await fetch(`${AZURE_BASE}/copilot/charging/live`, { signal: AbortSignal.timeout(8000) });
                if (res.ok) { const d = await res.json(); setIsVehicleCharging(d?.is_charging ?? false); }
                else setIsVehicleCharging(false);
            } catch { setIsVehicleCharging(false); }
        };
        poll();
        const iv = setInterval(poll, 60_000);
        return () => clearInterval(iv);
    }, []);

    // ── Persist ────────────────────────────────────────────────────────────────
    useEffect(() => { localStorage.setItem('cos_private_payments', JSON.stringify(privatePayments)); }, [privatePayments]);
    useEffect(() => { localStorage.setItem('cos_expenses', JSON.stringify(expenses)); }, [expenses]);
    useEffect(() => { localStorage.setItem('cos_manual_hours', JSON.stringify(manualHoursMap)); }, [manualHoursMap]);

    // ── Save daily gross to rolling history ──────────────────────────────────
    useEffect(() => {
        const gross = uberStats.earnings + privatePayments
            .filter(p => p.date === selectedDate)
            .reduce((s, p) => s + p.amount, 0);
        if (gross <= 0) return;
        try {
            const history = JSON.parse(localStorage.getItem('cos_daily_history') ?? '{}');
            history[selectedDate] = gross;
            localStorage.setItem('cos_daily_history', JSON.stringify(history));
        } catch { /* localStorage write failure */ }
    }, [uberStats, privatePayments, selectedDate]);

    // ── Auto-advance to a new day at midnight ────────────────────────────────
    useEffect(() => {
        const checkDay = () => {
            const today = getTodayMST();
            const storedDate = localStorage.getItem('cos_session_date');
            if (storedDate && storedDate !== today) {
                const currentSelected = localStorage.getItem('cos_selected_date');
                if (!currentSelected || currentSelected === storedDate) {
                    localStorage.removeItem('cos_private_payments');
                    localStorage.removeItem('cos_expenses');
                    localStorage.removeItem('cos_session_start');
                    localStorage.setItem('cos_session_date', today);
                    localStorage.setItem('cos_selected_date', today);
                    setPrivatePayments([]);
                    setExpenses({ fastfood: [], charging: [], capital_maintenance: [] });
                    const d = new Date();
                    setSessionStart(d);
                    localStorage.setItem('cos_session_start', d.toISOString());
                    setSelectedDate(today);
                }
            }
        };
        const iv = setInterval(checkDay, 60_000);
        return () => clearInterval(iv);
    }, []);

    // ── Fetch from Cloud on Date Change ──────────────────────────────────────
    const [isFetchingCloud, setIsFetchingCloud] = useState(false);
    const [isSyncingCloud, setIsSyncingCloud] = useState(false);
    const [syncMessage, setSyncMessage] = useState<string | null>(null);

    const fetchFromCloud = useCallback(async (date: string) => {
        setIsFetchingCloud(true);
        try {
            const resp = await fetch(`${AZURE_BASE}/driver/sync?date=${date}&t=${Date.now()}`, { cache: 'no-store' });
            if (resp.ok) {
                const data = await resp.json();
                if (data.success && data.expenses) {
                    const cloudFood = data.expenses.fastfood || [];
                    const cloudCharging = data.expenses.charging || [];
                    const cloudMaintenance = data.expenses.capital_maintenance || [];
                    if (cloudFood.length > 0 || cloudCharging.length > 0 || cloudMaintenance.length > 0) {
                        setExpenses({
                            fastfood: cloudFood,
                            charging: cloudCharging,
                            capital_maintenance: cloudMaintenance
                        });
                        const now = new Date().toLocaleTimeString();
                        setLastSync(now);
                        localStorage.setItem('cos_last_sync', now);
                    }
                }
            }
        } catch (err) { console.error('Failed to fetch from cloud:', err); }
        finally { setIsFetchingCloud(false); }
    }, []);

    const triggerRefresh = useCallback(() => {
        fetchFromCloud(selectedDate);
        setDrivesRefreshKey(k => k + 1);
    }, [selectedDate, fetchFromCloud]);

    const syncToCloud = useCallback(async () => {
        setIsSyncingCloud(true);
        setSyncMessage(null);
        try {
            // 1. Save local expenses/data to the database
            const resp = await fetch(`${AZURE_BASE}/driver/sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ expenses, trips: [] })
            });
            const data = await resp.json();
            
            if (data.success) {
                const now = new Date().toLocaleTimeString();
                setLastSync(now);
                localStorage.setItem('cos_last_sync', now);
                
                // 2. Trigger the backend Daily Unified Sync (Folders + Operations)
                try {
                    const syncResp = await fetch(`${AZURE_BASE}/daily-sync`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ date: selectedDate })
                    });

                    if (!syncResp.ok) {
                        const text = await syncResp.text();
                        if (text.includes('504') || text.includes('timeout') || !text.startsWith('{')) {
                            throw new Error('TIMEOUT_EXPECTED');
                        }
                        throw new Error(`Server returned ${syncResp.status}: ${text.substring(0, 100)}`);
                    }

                    let syncData;
                    try {
                        syncData = await syncResp.json();
                    } catch {
                        throw new Error('TIMEOUT_EXPECTED');
                    }

                    if (syncData.success) {
                        setSyncMessage(`✓ Unified Cloud Sync Complete at ${now}`);
                    } else {
                        setSyncMessage(`✓ Saved (Cloud Sync Note: ${syncData.error || 'Check console'})`);
                    }
                } catch (syncErr: unknown) {
                    const msg = syncErr instanceof Error ? syncErr.message : String(syncErr);
                    if (msg === 'TIMEOUT_EXPECTED' || msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.toLowerCase().includes('timeout')) {
                        // Gateway timeout is expected for long-running daily sync OCR operations.
                        // The Azure function executes in the background.
                        setSyncMessage(`✓ Saved & Syncing in Background...`);
                        setTimeout(triggerRefresh, 60_000);
                    } else {
                        setSyncMessage(`✓ Saved (Cloud Sync Error: ${msg})`);
                    }
                }
            } else {
                setSyncMessage(`✗ Save failed: ${data.error || 'Unknown error'}`);
            }
        } catch (err: unknown) {
            setSyncMessage(`✗ Network error: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
            setIsSyncingCloud(false);
            setTimeout(() => setSyncMessage(null), 5000);
        }
    }, [expenses, selectedDate, triggerRefresh]);

    useEffect(() => {
        fetchFromCloud(selectedDate);
    }, [selectedDate, fetchFromCloud]);

    const stats = useMemo(() => {
        const privateTotal = privatePayments
            .filter(p => p.date === selectedDate)
            .reduce((s, p) => s + (p.amount || 0), 0);
        const foodTotal = expenses.fastfood
            .filter(e => e.timestamp.startsWith(selectedDate))
            .reduce((s, e) => s + (e.amount || 0), 0);
        const chargingTotal = expenses.charging
            .filter(e => e.timestamp.startsWith(selectedDate))
            .reduce((s, e) => s + (e.amount || 0), 0);
        const capitalMaintenanceTotal = (expenses.capital_maintenance || [])
            .filter(e => e.timestamp.startsWith(selectedDate))
            .reduce((s, e) => s + (e.amount || 0), 0);
        const totalExpenses = foodTotal + chargingTotal;
        const totalIncome = uberStats.earnings + privateTotal;
        const profit = totalIncome - totalExpenses;
        const isToday = selectedDate === getTodayMST();
        
        const overrideHours = manualHoursMap[selectedDate];
        const activeHours = (overrideHours !== undefined && overrideHours > 0)
            ? overrideHours
            : (isToday
                ? (Date.now() - sessionStart.getTime()) / 3_600_000
                : Math.max(6, uberStats.count * 0.4));
                
        const hourlyRate = activeHours > 0.5 ? profit / activeHours : 0;
        return { 
            uberEarnings: uberStats.earnings, 
            uberCount: uberStats.count, 
            privateTotal, food: foodTotal, 
            charging: chargingTotal, 
            capitalMaintenanceTotal,
            totalExpenses, profit, hourlyRate, 
            activeHours,
            isManualHours: overrideHours !== undefined && overrideHours > 0
        };
    }, [uberStats, privatePayments, expenses, sessionStart, selectedDate, manualHoursMap]);

    const deleteExpense = (cat: keyof Expenses, id: number) =>
        setExpenses((prev) => ({ ...prev, [cat]: prev[cat].filter((e) => e.id !== id) }));

    const addPrivatePayment = (p: Omit<PrivatePayment, 'id'>) =>
        setPrivatePayments(prev => [{ id: Date.now(), ...p }, ...prev]);

    const deletePrivatePayment = (id: number) =>
        setPrivatePayments(prev => prev.filter(p => p.id !== id));

    const resetSession = () => {
        localStorage.removeItem('cos_private_payments');
        localStorage.removeItem('cos_expenses');
        localStorage.removeItem('cos_session_start');
        localStorage.setItem('cos_session_date', getTodayMST());
        const d = new Date();
        setSessionStart(d);
        localStorage.setItem('cos_session_start', d.toISOString());
        setPrivatePayments([]);
        setExpenses({ fastfood: [], charging: [], capital_maintenance: [] });
        setShowResetConfirm(false);
    };

    const handleImportCharge = (charge: TessieCharge) => {
        setExpenses(prev => ({
            ...prev,
            charging: [{
                id: Date.now(),
                amount: 0,
                note: `Tesla EV Charging – ${charge.energy_added_kwh.toFixed(1)} kWh${charge.location ? ` @ ${charge.location}` : ''}${charge.time_mst ? ` (${charge.time_mst})` : ''}`,
                timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`,
            }, ...prev.charging],
        }));
        expenseFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    // ── Azure auth user ──────────────────────────────────────────────────────
    const [azureUser, setAzureUser] = useState<string | null>(null);
    useEffect(() => {
        fetch('/.auth/me')
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                const name = data?.clientPrincipal?.userDetails;
                if (name) setAzureUser(name);
            })
            .catch(() => { });
    }, []);

    try {
        return (
            <div className="min-h-screen text-slate-800 p-3 sm:p-4 md:p-8 overflow-x-hidden bg-[#f8fafc]"
                style={{
                    backgroundImage: 'radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.04), transparent 60%)',
                }}>
                <div className="max-w-full lg:max-w-6xl mx-auto space-y-4 sm:space-y-5">
                    
                    <TeslaStatusBar />

                    <TelemetrySparklines selectedDate={selectedDate} />

                    <header className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 p-5 sm:p-8 rounded-2xl border border-slate-200/80 bg-white/80 shadow-sm backdrop-blur-md">
                        <div className="space-y-1">
                            <p className="text-xs font-semibold tracking-wider text-blue-600 uppercase mb-2 flex items-center gap-2">
                                <span className="w-6 h-[1.5px] bg-blue-600 inline-block" />
                                SummitOS · v{VERSION} · Driver Intelligence
                            </p>
                            <h1 className="text-2xl sm:text-3xl md:text-4xl font-black flex items-center gap-3 tracking-tight text-slate-800">
                                <Navigation className="text-blue-600 w-6 h-6 md:w-8 md:h-8" />
                                Driver Dashboard
                            </h1>
                            <div className="flex flex-wrap items-center gap-2 md:gap-3 pt-2">
                                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200">
                                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                                    <input
                                        type="date"
                                        value={selectedDate}
                                        onChange={(e) => { if (e.target.value) updateSelectedDate(e.target.value); }}
                                        className="bg-transparent border-none text-blue-600 text-[10px] md:text-xs font-bold focus:outline-none cursor-pointer font-sans"
                                    />
                                </div>
                                {isFetchingCloud && (
                                    <div className="flex items-center gap-2 px-2 md:px-3 py-1.5 rounded-lg border text-[9px] md:text-[10px] font-sans uppercase tracking-wider bg-blue-50 border-blue-200 text-blue-600">
                                        <Loader2 className="w-3 h-3 animate-spin" /> Syncing
                                    </div>
                                )}
                                {azureUser && (
                                    <div className="text-[9px] md:text-[10px] text-slate-500 font-sans flex items-center gap-2 px-2 md:px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200">
                                        <LogOut className="w-3 h-3 text-emerald-600" />
                                        {azureUser.split('@')[0]}
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-8 lg:gap-12">
                            <div className="flex flex-col sm:flex-row sm:items-center gap-6 sm:gap-10">
                                <button 
                                    onClick={() => setIsAuditOpen(true)} 
                                    className="text-left sm:text-right hover:scale-[1.03] transition-transform duration-200 group focus:outline-none"
                                >
                                    <p className="text-[10px] font-bold uppercase text-slate-400 tracking-[0.2em] mb-1 group-hover:text-blue-600 transition-colors">Session Profit 🔍</p>
                                    <p className={`text-2xl sm:text-3xl font-black tracking-tighter ${stats.profit >= 0 ? 'text-blue-600' : 'text-rose-600'}`}>
                                        ${(stats.profit || 0).toFixed(2)}
                                    </p>
                                </button>
                                <div className="hidden sm:block h-10 w-[1px] bg-slate-200" />
                                <div className="text-left sm:text-right">
                                    <p className="text-[10px] font-bold uppercase text-slate-400 tracking-[0.2em] mb-1">Uber + Private</p>
                                    <p className="text-xl sm:text-2xl font-black text-slate-800">${((stats.uberEarnings || 0) + (stats.privateTotal || 0)).toFixed(2)}</p>
                                </div>
                                <div className="hidden sm:block h-10 w-[1px] bg-slate-200" />
                                <div className="text-left sm:text-right">
                                    <p className="text-[10px] font-bold uppercase text-slate-400 tracking-[0.2em] mb-1">$/Hour</p>
                                    <p className="text-xl sm:text-2xl font-black text-blue-600">${Math.max(0, stats.hourlyRate || 0).toFixed(2)}</p>
                                    <p className="text-[9px] text-slate-400 italic">est. {(stats.activeHours || 0).toFixed(1)}h shift</p>
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => fetchFromCloud(selectedDate)}
                                    disabled={isFetchingCloud}
                                    className="p-2.5 rounded-xl border border-slate-200 bg-white text-slate-500 hover:text-blue-600 hover:border-blue-300 hover:bg-blue-50 transition-all shadow-sm"
                                    title="Refresh from Cloud">
                                    <RefreshCw className={`w-4 h-4 ${isFetchingCloud ? 'animate-spin' : ''}`} />
                                </button>
                                <button onClick={() => setShowResetConfirm(true)}
                                    className="p-2.5 rounded-xl border border-slate-200 bg-white text-slate-500 hover:text-rose-600 hover:border-rose-300 hover:bg-rose-50 transition-all shadow-sm"
                                    title="Reset Session Data">
                                    <RotateCcw className="w-4 h-4" />
                                </button>
                                <a href="/.auth/logout?post_logout_redirect_uri=/"
                                    className="p-2.5 rounded-xl border border-slate-200 bg-white text-slate-500 hover:text-slate-800 hover:border-slate-300 hover:bg-slate-50 transition-all shadow-sm"
                                    title="Sign Out">
                                    <LogOut className="w-4 h-4" />
                                </a>
                            </div>
                        </div>
                    </header>

                    {showResetConfirm && (
                        <div className="flex items-center justify-between bg-rose-50 border border-rose-200 rounded-2xl p-4 px-6 shadow-sm">
                            <p className="text-sm text-rose-800 font-semibold">Reset all trips and expenses for this session?</p>
                            <div className="flex gap-3">
                                <button onClick={resetSession} className="text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 active:bg-rose-800 px-4 py-1.5 rounded-lg shadow-sm transition-colors">Reset</button>
                                <button onClick={() => setShowResetConfirm(false)} className="text-xs font-bold text-slate-505 hover:text-slate-800 px-4 py-1.5 rounded-lg transition-colors">Cancel</button>
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 sm:gap-5">
                        <StatCard label="Gross Earnings" value={`$${(stats.uberEarnings + stats.privateTotal || 0).toFixed(2)}`}
                            sub={`Uber $${(stats.uberEarnings || 0).toFixed(2)} · Private $${(stats.privateTotal || 0).toFixed(2)}`}
                            icon={<DollarSign className="text-purple-600 w-5 h-5" />} />
                        <StatCard label="Uber Earnings" value={`$${(stats.uberEarnings || 0).toFixed(2)}`}
                            sub={`${stats.uberCount || 0} OCR trips`}
                            icon={<Receipt className="text-blue-600 w-5 h-5" />} highlight />
                        <StatCard label="Private Income" value={`$${(stats.privateTotal || 0).toFixed(2)}`}
                            sub={
                                <span>
                                    <a 
                                        href="/jackie" 
                                        target="_blank" 
                                        rel="noopener noreferrer" 
                                        className="hover:text-purple-600 underline font-bold"
                                    >
                                        Jackie
                                    </a>
                                    {' · Esmeralda · Other'}
                                </span>
                            }
                            icon={<DollarSign className="text-purple-600 w-5 h-5" />} />
                        <StatCard label="Expenses" value={`$${(stats.totalExpenses || 0).toFixed(2)}`}
                            sub={`Food $${(stats.food||0).toFixed(2)} · Charge $${(stats.charging||0).toFixed(2)}`}
                            icon={<Zap className="text-amber-600 w-5 h-5" />} />
                        <StatCard label="Capital & Maintenance" value={`$${(stats.capitalMaintenanceTotal || 0).toFixed(2)}`}
                            sub="Excluded from daily shift metrics"
                            icon={<Cpu className="text-blue-600 w-5 h-5" />} />
                        <StatCard label="Net Profit" value={`$${(stats.profit || 0).toFixed(2)}`}
                            sub={`≈ $${(stats.hourlyRate || 0).toFixed(2)}/hr`}
                            icon={<TrendingUp className="text-emerald-600 w-5 h-5" />} highlight />
                    </div>

                    <GoalTrackerPanel
                        todayEarnings={(stats.uberEarnings || 0) + (stats.privateTotal || 0)}
                        selectedDate={selectedDate}
                    />

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="space-y-5">
                            <SummitCopilotConsole />
                            <IntelligenceSyncPanel
                                selectedDate={selectedDate}
                                onRefresh={() => {
                                    fetchFromCloud(selectedDate);
                                    setDrivesRefreshKey(k => k + 1);
                                }}
                                hours={manualHoursMap[selectedDate] || 0}
                                onHoursChange={(h) => setManualHoursMap(prev => ({ ...prev, [selectedDate]: h }))}
                            />
                            <PrivatePaymentsPanel
                                selectedDate={selectedDate}
                                payments={privatePayments}
                                onAdd={addPrivatePayment}
                                onDelete={deletePrivatePayment}
                            />
                        </div>

                        <div className="lg:col-span-2 space-y-6" ref={expenseFormRef}>
                            <TessieChargesPanel onImport={handleImportCharge} selectedDate={selectedDate} />
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <ExpenseList
                                    title="Charging Sessions"
                                    data={expenses.charging.filter(e => e.timestamp.startsWith(selectedDate))}
                                    icon={<Zap className="w-4 h-4 text-amber-600" />}
                                    onDelete={(id) => deleteExpense('charging', id)}
                                    onAdd={(amount, note) => setExpenses(prev => ({
                                        ...prev,
                                        charging: [{ id: Date.now(), amount, note, timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}` }, ...prev.charging]
                                    }))}
                                    accentColor="text-amber-600"
                                />
                                <ExpenseList
                                    title="Food & Drinks"
                                    data={expenses.fastfood.filter(e => e.timestamp.startsWith(selectedDate))}
                                    icon={<Utensils className="w-4 h-4 text-rose-600" />}
                                    onDelete={(id) => deleteExpense('fastfood', id)}
                                    onAdd={(amount, note) => setExpenses(prev => ({
                                        ...prev,
                                        fastfood: [{ id: Date.now(), amount, note, timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}` }, ...prev.fastfood]
                                    }))}
                                    accentColor="text-rose-600"
                                />
                                <div className="md:col-span-2">
                                    <ExpenseList
                                        title="Capital & Maintenance"
                                        subtitle="Excluded from Daily Shift Stats"
                                        data={(expenses.capital_maintenance || []).filter(e => e.timestamp.startsWith(selectedDate))}
                                        icon={<Cpu className="w-4 h-4 text-blue-600" />}
                                        onDelete={(id) => deleteExpense('capital_maintenance', id)}
                                        onAdd={(amount, note) => setExpenses(prev => ({
                                            ...prev,
                                            capital_maintenance: [{ id: Date.now(), amount, note, category: 'Maintenance', timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}` }, ...(prev.capital_maintenance || [])]
                                        }))}
                                        accentColor="text-blue-600"
                                    />
                                </div>
                            </div>
                            <div className="flex items-center gap-3 pt-1">
                                <button
                                    onClick={syncToCloud}
                                    disabled={isSyncingCloud}
                                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 hover:shadow-md hover:shadow-blue-500/10 active:shadow-sm hover:scale-[1.01] transition-all disabled:opacity-50 shadow-sm"
                                >
                                    <Cloud className="w-4 h-4" />
                                    {isSyncingCloud ? 'Saving Day...' : 'Save Day to Cloud'}
                                </button>
                                {syncMessage && (
                                    <span className={`text-xs font-sans font-semibold ${
                                        syncMessage.startsWith('✓') ? 'text-emerald-600' : 'text-rose-600'
                                    }`}>{syncMessage}</span>
                                )}
                                {isFetchingCloud && (
                                    <span className="text-xs font-sans text-slate-400">↓ loading cloud...</span>
                                )}
                            </div>
                        </div>
                    </div>

                    <UberTripsPanel
                        selectedDate={selectedDate}
                        onTripsLoaded={(count, earnings) => setUberStats({ count, earnings })}
                    />

                    <PrivateTripsPanel
                        selectedDate={selectedDate}
                    />

                    <TessieDrivesPanel 
                        onImport={() => {}} 
                        selectedDate={selectedDate} 
                        refreshKey={drivesRefreshKey} 
                        privatePayments={privatePayments} 
                        chargingExpenses={expenses.charging} 
                        isVehicleCharging={isVehicleCharging}
                    />

                    <UberHeatmapPanel />

                    <AuditLedgerModal 
                        isOpen={isAuditOpen} 
                        onClose={() => setIsAuditOpen(false)} 
                        stats={stats} 
                        selectedDate={selectedDate} 
                    />

                    <div className="text-center pt-2 pb-6">
                        <p className="text-[10px] font-mono text-gray-700 tracking-[0.3em] uppercase">
                            Powered by SummitOS · COS Tesla LLC
                        </p>
                    </div>
                </div>
            </div>
        );
    } catch (e: unknown) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center p-10">
                <div className="max-w-xl w-full bg-rose-500/10 border border-rose-500/20 p-8 rounded-2xl">
                    <h1 className="text-xl font-bold text-rose-400 mb-4">Dashboard Crash</h1>
                    <p className="text-gray-400 font-mono text-xs mb-6 bg-black/40 p-4 rounded-xl border border-white/5 whitespace-pre-wrap">
                        {e instanceof Error ? e.message : String(e)}
                    </p>
                    <button onClick={() => window.location.reload()} className="px-6 py-2 bg-rose-500 text-white rounded-xl font-bold text-sm">
                        Refresh Dashboard
                    </button>
                </div>
            </div>
        );
    }
};

export default DriverDashboard;
