'use client';

import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
    TrendingUp, Car, Zap, Utensils, Trash2,
    Navigation, Receipt, RotateCcw, Clock,
    Battery, BatteryCharging, WifiOff, Download,
    MapPin, Gauge, LogOut, Cpu, RefreshCw, Loader2,
    DollarSign, Cloud
} from 'lucide-react';


// ─── Constants ─────────────────────────────────────────────────────────────
const AZURE_BASE = 'https://summitos-api.azurewebsites.net/api';
const VERSION = "1.4.5";

const TAG_FILTERS = ['Uber', 'Uber_Matched', 'Uber_Pickup', 'Jackie', 'Esmeralda', 'Uncategorized'] as const;

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
}

interface Expenses {
    fastfood: Expense[];
    charging: Expense[];
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
}

// ─── Sub-components ─────────────────────────────────────────────────────────

const StatCard = ({
    label, value, sub, icon, highlight = false,
}: {
    label: string; value: string | number; sub: string;
    icon: React.ReactNode; highlight?: boolean;
}) => (
    <div
        className={`relative rounded-2xl p-5 flex items-start gap-4 overflow-hidden transition-all duration-300 hover:scale-[1.02]
      ${highlight
                ? 'bg-cyan-500/10 border border-cyan-500/30 shadow-[0_0_30px_rgba(0,242,255,0.08)]'
                : 'bg-white/3 border border-white/8 hover:border-white/15'}`}
        style={{ backdropFilter: 'blur(16px)' }}
    >
        {highlight && <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 blur-[60px] rounded-full pointer-events-none" />}
        <div className={`p-2.5 rounded-xl ${highlight ? 'bg-cyan-500/20' : 'bg-white/8'}`}>{icon}</div>
        <div>
            <p className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] font-mono mb-0.5">{label}</p>
            <p className={`text-2xl font-black ${highlight ? 'text-cyan-400' : 'text-white'}`}
                style={highlight ? { textShadow: '0 0 20px rgba(0,242,255,0.5)' } : {}}>{value}</p>
            <p className="text-[11px] text-gray-500 font-mono mt-0.5">{sub}</p>
        </div>
    </div>
);

const ExpenseList = ({
    title, data, icon, onDelete, onAdd, accentColor,
}: {
    title: string; data: Expense[]; icon: React.ReactNode;
    onDelete: (id: number) => void;
    onAdd?: (amount: number, note: string) => void;
    accentColor: string;
}) => {
    const [amount, setAmount] = React.useState('');
    const [note, setNote] = React.useState('');
    const inputBase = 'bg-black/30 border border-white/10 rounded-xl text-white placeholder-gray-600 font-mono text-xs focus:outline-none focus:border-cyan-500/40 transition-all';

    const handleAdd = (e: React.FormEvent) => {
        e.preventDefault();
        const val = parseFloat(amount);
        if (!val || !onAdd) return;
        onAdd(val, note);
        setAmount(''); setNote('');
    };

    return (
        <div className="rounded-2xl overflow-hidden border border-white/8"
            style={{ background: 'rgba(255,255,255,0.02)', backdropFilter: 'blur(16px)' }}>
            <div className="p-4 border-b border-white/8 flex items-center gap-2">
                {icon}
                <h3 className="font-bold text-sm text-white">{title}</h3>
                {data.length > 0 && (
                    <span className={`ml-auto text-xs font-mono font-bold ${accentColor}`}>
                        ${data.reduce((s, e) => s + e.amount, 0).toFixed(2)}
                    </span>
                )}
            </div>
            <div className="max-h-[200px] overflow-y-auto">
                {data.length === 0
                    ? <p className="p-6 text-center text-xs text-gray-600 italic font-mono">// no entries</p>
                    : <div className="divide-y divide-white/5">
                        {data.map((item) => (
                            <div key={item.id} className="p-3 flex justify-between items-center group hover:bg-white/4 transition-colors">
                                <div className="flex flex-col">
                                    <span className="text-xs font-bold text-white">${item.amount.toFixed(2)}</span>
                                    <span className="text-[10px] text-gray-500 font-mono">{item.note || item.timestamp}</span>
                                </div>
                                <button onClick={() => onDelete(item.id)}
                                    className="text-gray-700 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all">
                                    <Trash2 className="w-3 h-3" />
                                </button>
                            </div>
                        ))}
                    </div>}
            </div>
            {onAdd && (
                <form onSubmit={handleAdd} className="flex gap-2 p-3 border-t border-white/8 bg-black/20">
                    <input
                        type="number" step="0.01" placeholder="$0.00" value={amount}
                        onChange={e => setAmount(e.target.value)}
                        className={`${inputBase} w-20 p-2 text-center`}
                    />
                    <input
                        type="text" placeholder="Note (store, receipt...)" value={note}
                        onChange={e => setNote(e.target.value)}
                        className={`${inputBase} flex-1 p-2`}
                    />
                    <button type="submit"
                        className={`px-3 py-2 rounded-xl text-xs font-bold border transition-all ${accentColor} border-current bg-current/10 hover:bg-current/20`}>
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

    const soc = status?.current_soc ?? null;
    const range = status?.battery_range_mi ?? null;
    const isCharging = status?.is_charging ?? false;
    const chargingState = status?.charging_state ?? null;
    const kw = status?.charge_power_kw ?? 0;
    const minsToFull = status?.minutes_to_full ?? null;

    const barColor = soc !== null
        ? soc > 50 ? 'bg-emerald-400' : soc > 20 ? 'bg-amber-400' : 'bg-rose-500'
        : 'bg-gray-700';

    return (
        <div
            className="flex flex-wrap md:flex-nowrap items-center gap-4 px-5 py-3 rounded-2xl border border-white/8"
            style={{ background: 'rgba(255,255,255,0.02)', backdropFilter: 'blur(12px)' }}
        >
            {/* Label */}
            <div className="flex items-center gap-2 shrink-0">
                {isCharging
                    ? <BatteryCharging className="w-4 h-4 text-emerald-400" />
                    : offline ? <WifiOff className="w-4 h-4 text-gray-600" />
                        : <Battery className="w-4 h-4 text-cyan-400" />}
                <span className="text-[10px] font-bold uppercase tracking-[0.25em] font-mono text-gray-500 flex items-center gap-2">
                    Tesla Live
                    <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.5)]" />
                </span>
            </div>

            {loading && (
                <div className="flex gap-3 flex-1 animate-pulse">
                    <div className="h-2 w-32 bg-gray-800 rounded-full" />
                    <div className="h-2 w-20 bg-gray-800 rounded-full" />
                </div>
            )}

            {!loading && offline && (
                <span className="text-xs text-gray-600 font-mono italic">Vehicle offline or sleeping</span>
            )}

            {!loading && !offline && status && (
                <>
                    {/* Battery bar + % */}
                    <div className="flex items-center gap-2 md:gap-3 flex-1 min-w-0">
                        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                            <div
                                className={`h-full ${barColor} transition-all duration-700`}
                                style={{ width: `${soc ?? 0}%` }}
                            />
                        </div>
                        <span className={`text-lg md:text-2xl font-black font-mono tabular-nums ${barColor.replace('bg-', 'text-')}`}
                            style={{ textShadow: `0 0 20px ${(soc || 0) > 50 ? 'rgba(52,211,153,0.3)' : (soc || 0) > 20 ? 'rgba(251,191,36,0.3)' : 'rgba(244,63,94,0.3)'}` }}>
                            {soc !== null ? `${soc}%` : '--'}
                        </span>
                    </div>

                    {/* Range & Charging Info Container */}
                    <div className="flex items-center gap-4 ml-auto">
                        {range !== null && (
                            <div className="flex items-center gap-1.5 shrink-0">
                                <Gauge className="w-3.5 h-3.5 text-gray-500" />
                                <span className="text-xs md:text-sm font-bold text-white tabular-nums">{range.toFixed(0)}<span className="text-gray-600 font-normal text-[10px]"> mi</span></span>
                            </div>
                        )}

                        {isCharging && (
                            <div className="flex items-center gap-1.5 shrink-0">
                                <Zap className="w-3.5 h-3.5 text-emerald-400" />
                                <span className="text-xs md:text-sm font-bold text-emerald-400 tabular-nums">{kw} kW</span>
                                {minsToFull !== null && (
                                    <span className="hidden md:inline text-[10px] text-gray-500 font-mono">({Math.round(minsToFull / 60)}h {minsToFull % 60}m)</span>
                                )}
                            </div>
                        )}
                    </div>


                    {/* State label */}
                    {chargingState && !isCharging && (
                        <span className="text-[10px] text-gray-600 font-mono uppercase tracking-wider shrink-0">{chargingState}</span>
                    )}

                    {/* Temperature */}
                    {(status.inside_temp !== null || status.outside_temp !== null) && (
                        <div className="flex items-center gap-3 px-3 py-1 bg-white/5 rounded-full border border-white/5">
                            {status.outside_temp !== null && (
                                <div className="flex items-center gap-1">
                                    <span className="text-[10px] text-gray-500 font-bold uppercase">Ext</span>
                                    <span className="text-xs font-bold text-white font-mono">{Math.round(status.outside_temp * 9/5 + 32)}°</span>
                                </div>
                            )}
                            {status.inside_temp !== null && (
                                <div className="flex items-center gap-1 border-l border-white/10 pl-3">
                                    <span className="text-[10px] text-gray-500 font-bold uppercase">Int</span>
                                    <span className="text-xs font-bold text-cyan-400 font-mono">{Math.round(status.inside_temp * 9/5 + 32)}°</span>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Location */}
                    {status.location && (
                        <div className="flex items-center gap-1.5 px-3 py-1 bg-white/5 rounded-full border border-white/5 max-w-[200px]">
                            <MapPin className="w-3 h-3 text-cyan-400 shrink-0" />
                            <span className="text-[10px] font-bold text-gray-400 truncate uppercase tracking-tighter">{status.location}</span>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

// ─── Tag badge ───────────────────────────────────────────────────────────────
const TAG_STYLE: Record<string, string> = {
    uber_matched: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    uber_pickup: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
    uber: 'bg-white/10 text-white border-white/20',
    jackie: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
    esmeralda: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    uncategorized: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
};
const tagStyle = (tag: string | null) => {
    const key = (tag ?? '').toLowerCase() || 'uncategorized';
    for (const [k, v] of Object.entries(TAG_STYLE)) if (key.includes(k)) return v;
    return 'bg-gray-700/30 text-gray-400 border-gray-600/30';
};

// ─── Tessie Drives Panel ─────────────────────────────────────────────────────
const TessieDrivesPanel = ({
    onImport,
    selectedDate,
    refreshKey
}: {
    onImport: (drive: TessieDrive) => void;
    selectedDate: string;
    refreshKey?: number;
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
            // +2 buffer: one for MDT edge-cases, one to cover any Tessie processing lag
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

            // Merge & deduplicate by tessie_drive_id (coerce to string — Tessie API may return int)
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
            // Filter to selected date, sort newest-first
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
            className="rounded-2xl border border-white/8 overflow-hidden"
            style={{ background: 'rgba(255,255,255,0.02)', backdropFilter: 'blur(16px)' }}
        >
            {/* Header */}
            <div className="p-5 border-b border-white/8 flex flex-wrap items-center gap-3 justify-between">
                <div className="flex items-center gap-2">
                    <Car className="w-4 h-4 text-cyan-400" />
                    <h2 className="font-bold text-white">Tessie Drives</h2>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                    {/* The date picker is now managed globally in the header */}
                    <span className="text-[10px] font-mono text-gray-600 uppercase tracking-wider">{selectedDate}</span>
                    {TAG_FILTERS.map((t) => (
                        <span key={t} className={`text-[10px] font-bold px-2 py-0.5 rounded-full border font-mono uppercase tracking-wider ${tagStyle(t)}`}>
                            {t}
                        </span>
                    ))}
                    <button
                        onClick={() => fetchAll()}
                        disabled={loading}
                        title="Refresh drives from Tessie"
                        className="flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-lg border border-white/10 text-gray-400 hover:text-cyan-400 hover:border-cyan-500/30 transition-all disabled:opacity-40"
                    >
                        <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Body */}
            <div className="divide-y divide-white/5">
                {loading && (
                    <div className="p-10 text-center animate-pulse">
                        <div className="h-2 w-48 bg-gray-800 rounded-full mx-auto mb-3" />
                        <div className="h-2 w-32 bg-gray-800 rounded-full mx-auto" />
                    </div>
                )}

                {!loading && error && (
                    <div className="p-10 text-center">
                        <WifiOff className="w-6 h-6 text-gray-700 mx-auto mb-2" />
                        <p className="text-xs text-gray-600 font-mono">// Azure unreachable — drives unavailable</p>
                    </div>
                )}

                {!loading && !error && drives.length === 0 && (
                    <p className="p-10 text-center text-xs text-gray-600 italic font-mono">
                        // no tagged drives found for {selectedDate} (Uber · Jackie · Esmeralda)
                    </p>
                )}

                {!loading && !error && drives.map((drive) => {
                    const imported = importedIds.has(drive.tessie_drive_id);
                    return (
                        <div key={drive.tessie_drive_id}
                            className="p-4 flex flex-col md:flex-row md:items-center gap-3 hover:bg-white/3 transition-colors group">
                            {/* Left: meta */}
                            <div className="flex-1 space-y-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border font-mono uppercase ${tagStyle(drive.tag)}`}>
                                        {drive.tag ?? 'Untagged'}
                                    </span>
                                    <span className="text-[10px] text-gray-500 font-mono">
                                        {drive.date} · {drive.time_mst}
                                    </span>
                                    {/* Fare match indicator — only shown for Uber trips */}
                                    {(drive.tag ?? '').toLowerCase().includes('uber') && (
                                        drive.fare_matched
                                            ? (
                                                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-emerald-500/15 border-emerald-500/30 text-emerald-400">
                                                    <span>✓</span>
                                                    <span>${drive.driver_earnings?.toFixed(2)}</span>
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-rose-500/15 border-rose-500/30 text-rose-400">
                                                    <span>✗</span>
                                                    <span>No receipt</span>
                                                </span>
                                            )
                                    )}
                                </div>
                                {(drive.start || drive.end) && (
                                    <div className="flex items-start gap-1.5 text-[11px] text-gray-400">
                                        <MapPin className="w-3 h-3 mt-0.5 text-gray-600 shrink-0" />
                                        <span className="leading-snug">
                                            {drive.start ?? '—'} → {drive.end ?? '—'}
                                        </span>
                                    </div>
                                )}
                            </div>

                            {/* Middle: stats */}
                            <div className="flex gap-5 shrink-0 text-center">
                                <div>
                                    <p className="text-[10px] text-gray-600 font-mono uppercase">Miles</p>
                                    <p className="text-sm font-black text-white tabular-nums">{drive.distance_miles.toFixed(1)}</p>
                                </div>
                                <div>
                                    <p className="text-[10px] text-gray-600 font-mono uppercase">kWh</p>
                                    <p className="text-sm font-bold text-amber-400 tabular-nums">{drive.energy_used_kwh.toFixed(2)}</p>
                                </div>
                                {drive.efficiency_wh_mi !== null && (
                                    <div>
                                        <p className="text-[10px] text-gray-600 font-mono uppercase">Wh/mi</p>
                                        <p className="text-sm font-bold text-gray-300 tabular-nums">{drive.efficiency_wh_mi}</p>
                                    </div>
                                )}
                                <div>
                                    <p className="text-[10px] text-gray-600 font-mono uppercase">Batt</p>
                                    <p className="text-sm font-bold text-cyan-400 tabular-nums">
                                        {drive.starting_battery ?? '--'}→{drive.ending_battery ?? '--'}%
                                    </p>
                                </div>
                            </div>

                            {/* Right: import button */}
                            <button
                                onClick={() => handleImport(drive)}
                                disabled={imported}
                                className={`flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-xl border transition-all shrink-0 ${imported
                                    ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10 cursor-default'
                                    : 'border-cyan-500/30 text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20 hover:border-cyan-500/50'
                                    }`}
                            >
                                {imported
                                    ? <><span className="text-emerald-400">✓</span> Imported</>
                                    : <><Download className="w-3 h-3" /> Import</>}
                            </button>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

// ─── Main Component ──────────────────────────────────────────────────────────
const TessieChargesPanel = ({ onImport, selectedDate }: { onImport: (charge: TessieCharge) => void, selectedDate: string }) => {
    const [charges, setCharges] = useState<TessieCharge[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [importedIds, setImportedIds] = useState<Set<string>>(new Set());

    useEffect(() => {
        setLoading(true);
        const fetchCharges = async () => {
            try {
                // Calculate days to fetch based on selectedDate vs today
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
        };
        fetchCharges();
    }, [selectedDate]);

    const handleImport = (charge: TessieCharge) => {
        onImport(charge);
        const key = charge.tessie_charge_id ?? `${charge.date}-${charge.time_mst}`;
        setImportedIds((prev) => new Set(prev).add(key ?? ''));
    };

    return (
        <div className="rounded-2xl border border-white/8 overflow-hidden"
            style={{ background: 'rgba(255,255,255,0.02)', backdropFilter: 'blur(16px)' }}>
            <div className="p-5 border-b border-white/8 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-400" />
                <h2 className="font-bold text-white">Tessie Charging Sessions</h2>
                <span className="text-[10px] font-mono text-gray-600 ml-2 uppercase tracking-wider">{selectedDate}</span>
            </div>
            <div className="divide-y divide-white/5">
                {loading && <div className="p-10 text-center animate-pulse"><div className="h-2 w-48 bg-gray-800 rounded-full mx-auto mb-3" /><div className="h-2 w-32 bg-gray-800 rounded-full mx-auto" /></div>}
                {!loading && error && <div className="p-8 text-center text-gray-600 font-mono text-xs flex items-center justify-center gap-2"><WifiOff className="w-4 h-4" /> Unable to load charging sessions</div>}
                {!loading && !error && charges.length === 0 && <div className="p-8 text-center text-gray-700 font-mono text-xs italic">// no charging sessions found for {selectedDate}</div>}
                {!loading && !error && charges.map((charge) => {
                    const key = charge.tessie_charge_id ?? `${charge.date}-${charge.time_mst}`;
                    const imported = importedIds.has(key ?? '');
                    return (
                        <div key={key} className="flex items-center justify-between p-4 hover:bg-white/3 transition-colors">
                            <div className="flex items-center gap-4">
                                <div className="p-2 rounded-xl bg-amber-500/10"><BatteryCharging className="w-4 h-4 text-amber-400" /></div>
                                <div>
                                    <p className="text-sm font-bold text-white">
                                        {charge.energy_added_kwh.toFixed(1)} kWh added
                                        {charge.duration_minutes ? <span className="font-normal text-gray-500 text-xs ml-2">· {charge.duration_minutes.toFixed(0)} min</span> : null}
                                    </p>
                                    <p className="text-[10px] text-gray-600 font-mono">
                                        {charge.time_mst ?? '—'}{charge.location ? ` · ${charge.location}` : ''}{charge.charge_type ? ` · ${charge.charge_type}` : ''}
                                    </p>
                                    {charge.starting_soc != null && charge.ending_soc != null && (
                                        <p className="text-[10px] font-mono text-amber-500/60 mt-0.5">🔋 {charge.starting_soc}% → {charge.ending_soc}%</p>
                                    )}
                                </div>
                            </div>
                            <button onClick={() => handleImport(charge)} disabled={imported}
                                className={`text-xs font-bold px-3 py-1.5 rounded-lg border transition-all ${imported ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10 cursor-default' : 'border-amber-500/30 text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 hover:border-amber-500/50'}`}>
                                {imported ? <><span className="text-emerald-400">✓</span> Imported</> : <><Download className="w-3 h-3 inline mr-1" />Import</>}
                            </button>
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

    const fetchTrips = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/get-day-trips?date=${selectedDate}&t=${Date.now()}`, {
                signal: AbortSignal.timeout(12_000), cache: 'no-store'
            });
            const data = resp.ok ? await resp.json() : { trips: [] };
            const tripList = (data.trips ?? []) as UberTrip[];
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
        <div className="rounded-2xl border border-violet-500/20 overflow-hidden"
            style={{ background: 'rgba(139,92,246,0.04)', backdropFilter: 'blur(16px)' }}>
            {/* Header */}
            <div className="p-5 border-b border-violet-500/15 flex flex-wrap items-center gap-3 justify-between">
                <div className="flex items-center gap-2">
                    <Receipt className="w-4 h-4 text-violet-400" />
                    <h2 className="font-bold text-white">Uber Trips</h2>
                    <span className="text-[10px] font-mono text-gray-600 uppercase tracking-wider">{selectedDate}</span>
                    {trips.length > 0 && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300 font-mono">
                            {trips.length} trips · ${totalEarnings.toFixed(2)}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={fetchTrips} disabled={loading}
                        className="text-[10px] font-bold px-2 py-1 rounded-lg border border-white/10 text-gray-400 hover:text-white hover:border-white/20 transition-all">
                        <RefreshCw className={`w-3 h-3 inline mr-1 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Body */}
            <div className="divide-y divide-violet-500/8">
                {loading && (
                    <div className="p-10 text-center animate-pulse">
                        <div className="h-2 w-48 bg-gray-800 rounded-full mx-auto mb-3" />
                        <div className="h-2 w-32 bg-gray-800 rounded-full mx-auto" />
                    </div>
                )}

                {!loading && trips.length === 0 && (
                    <div className="p-10 text-center">
                        <Receipt className="w-6 h-6 text-gray-700 mx-auto mb-2" />
                        <p className="text-xs text-gray-600 font-mono italic">
                            // no trips found — click "Scan Day" in Intelligence Sync to OCR the {selectedDate} folder
                        </p>
                    </div>
                )}

                {!loading && trips.map((trip) => (
                    <div key={trip.trip_id}
                        className="p-4 flex flex-col md:flex-row md:items-center gap-3 hover:bg-violet-500/5 transition-colors group">

                        {/* Trip number badge */}
                        <div className="shrink-0 flex flex-col items-center justify-center w-10 h-10 rounded-xl bg-violet-500/15 border border-violet-500/25">
                            <span className="text-[10px] font-mono text-violet-400 leading-none">Trip</span>
                            <span className="text-sm font-black text-violet-300 leading-none">{trip.trip_number}</span>
                        </div>

                        {/* Left: meta */}
                        <div className="flex-1 space-y-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border border-white/15 bg-white/8 text-white font-mono uppercase">
                                    {trip.service_type}
                                </span>
                                <span className="text-[10px] text-gray-500 font-mono">{trip.time_display}</span>
                                {trip.duration_min && (
                                    <span className="text-[10px] text-gray-600 font-mono">{trip.duration_min.toFixed(0)} min</span>
                                )}
                                {trip.distance_mi && (
                                    <span className="text-[10px] text-gray-600 font-mono">{trip.distance_mi.toFixed(2)} mi</span>
                                )}
                            </div>
                            {(trip.pickup || trip.dropoff) && (
                                <div className="flex items-start gap-1.5 text-[11px] text-gray-400">
                                    <MapPin className="w-3 h-3 mt-0.5 text-gray-600 shrink-0" />
                                    <span className="leading-snug truncate">{trip.pickup ?? '—'} → {trip.dropoff ?? '—'}</span>
                                </div>
                            )}
                        </div>

                        {/* Right: earnings */}
                        <div className="flex gap-4 shrink-0 text-center">
                            <div>
                                <p className="text-[10px] text-gray-600 font-mono uppercase">Earned</p>
                                <p className="text-base font-black text-emerald-400 tabular-nums">${trip.driver_earnings.toFixed(2)}</p>
                            </div>
                            {trip.tip > 0 && (
                                <div>
                                    <p className="text-[10px] text-gray-600 font-mono uppercase">Tip</p>
                                    <p className="text-base font-black text-amber-400 tabular-nums">${trip.tip.toFixed(2)}</p>
                                </div>
                            )}
                            <div>
                                <p className="text-[10px] text-gray-600 font-mono uppercase">Rider</p>
                                <p className="text-sm font-bold text-gray-400 tabular-nums">${trip.rider_payment.toFixed(2)}</p>
                            </div>
                            <div>
                                <p className="text-[10px] text-gray-600 font-mono uppercase">Uber Cut</p>
                                <p className="text-sm font-bold text-rose-400/70 tabular-nums">${trip.uber_cut.toFixed(2)}</p>
                            </div>
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


    const runSync = async (dryRun: boolean) => {
        setStatus('running');
        setLogs([`> Starting ${dryRun ? 'Dry Run' : 'Actual Sync'} for ${selectedDate}...`]);
        try {
            const resp = await fetch(`${AZURE_BASE}/operations/sync-folders`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ processDate: selectedDate, dryRun })
            });

            const data = await resp.json();
            if (data.success) {
                setStatus('success');
                setLogs(prev => [...prev, ...(data.logs || []), `> [SUCCESS] Folder sync finalized.`]);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            setStatus('error');
            setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
        }
    };

    const runDailySync = async () => {
        setStatus('running');
        setLogs([`> Initializing Daily Unified Sync (Folders + Data)...`]);

        try {
            const resp = await fetch(`${AZURE_BASE}/daily-sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: selectedDate })
            });

            const data = await resp.json();
            if (data.success) {
                setStatus('success');
                setLogs(prev => [...prev, ...(data.logs || []), `> [SUCCESS] Daily Sync Complete.`]);
                // Refresh the drives & trips panels so newly synced data appears immediately
                onRefresh();
            } else {
                setStatus('error');
                setLogs(prev => [...prev, ...(data.logs || []), `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            setStatus('error');
            setLogs(prev => [...prev, `> [CRITICAL] ${err instanceof Error ? err.message : String(err)}`]);
        }
    };

    // Scan the auto-calculated OneDrive folder for the selected date — no prompt
    const runScanDay = async () => {
        const path = buildOneDrivePath(selectedDate);
        setStatus('running');
        setLogs([`> Initializing Unified Day Scan: ${path}...`]);
        try {
            // 1. General Cloud Scan & Routing
            const data = await triggerCloudScan(path);
            if (data.success) {
                setLogs(prev => [...prev, `> [STEP 1] Folder organization complete.`]);
                
                // 2. OCR Trip Numbering & Auto-tagging
                setLogs(prev => [...prev, `> [STEP 2] Starting OCR trip extraction...`]);
                const ocrResp = await fetch(`${AZURE_BASE}/operations/scan-day-trips`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date: selectedDate, path })
                });
                
                if (ocrResp.ok) {
                    const ocrData = await ocrResp.json();
                    if (ocrData.success) {
                        setStatus('success');
                        setLogs(prev => [...prev, 
                            ...(ocrData.logs || []),
                            `> [SUCCESS] Full Day Scan Complete.`,
                            `> ${ocrData.trip_count} Uber trips extracted and labeled.`
                        ]);
                        // Refresh everything
                        onRefresh();
                    } else {
                        setStatus('error');
                        setLogs(prev => [...prev, `> [OCR ERROR] ${ocrData.error}`]);
                    }
                } else {
                    setLogs(prev => [...prev, `> [NOTICE] OCR scan is continuing in background due to size.`]);
                    setStatus('success');
                    setTimeout(onRefresh, 60_000);
                }
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            if (msg === 'TIMEOUT_EXPECTED') {
                setStatus('success'); // Mark as success because background job is running
                setLogs(prev => [...prev, 
                    `> [NOTICE] Large scan detected (>45s).`,
                    `> Azure proxy timed out, but the scan is still running in the background.`,
                    `> Please wait 60 seconds and refresh the page to see your checkmarks.`
                ]);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [CRITICAL] ${msg}`]);
            }
        }
    };

    // Scan a custom-named folder (for edge cases where folder name differs from day number)
    const runOneDriveSyncCustom = async () => {
        const folderName = prompt('Enter folder name (e.g. 03):');
        if (!folderName) return;
        const path = buildOneDrivePath(selectedDate, folderName);
        setStatus('running');
        setLogs([`> Scanning custom folder: ${path}...`]);
        try {
            const data = await triggerCloudScan(path);
            if (data.success) {
                setStatus('success');
                setLogs(prev => [...prev, ...(data.logs || []), `> [SUCCESS] Custom scan complete.`]);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            if (msg === 'TIMEOUT_EXPECTED') {
                setStatus('success');
                setLogs(prev => [...prev, 
                    `> [NOTICE] Large scan detected.`,
                    `> Proxy timed out, but background sync is likely still active.`,
                    `> Refresh in 60 seconds.`
                ]);
            } else {
                setStatus('error');
                setLogs(prev => [...prev, `> [CRITICAL] ${msg}`]);
            }
        }
    };

    return (
        <div className="p-6 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 backdrop-blur-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 blur-3xl rounded-full pointer-events-none group-hover:bg-cyan-500/15 transition-all duration-1000" />
            
            <div className="flex justify-between items-start mb-1">
                <div>
                    <h2 className="text-base font-bold flex items-center gap-2 text-white">
                        <Cpu className="w-4 h-4 text-cyan-400" /> Intelligence Sync
                    </h2>
                    <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">Autonomous Pipeline Operating</p>
                </div>
                {status === 'running' && (
                    <div className="flex items-center gap-1.5 px-3 py-1 bg-cyan-500/10 border border-cyan-500/20 rounded-full">
                        <Loader2 className="w-3 h-3 text-cyan-400 animate-spin" />
                        <span className="text-[9px] font-bold text-cyan-400 uppercase font-mono tracking-tighter">Running</span>
                    </div>
                )}
            </div>

            {/* Manual Hours Input */}
            <div className="mt-4 p-3 rounded-xl bg-black/40 border border-white/5 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                    <Clock className="w-4 h-4 text-cyan-400" />
                </div>
                <div className="flex-1">
                    <p className="text-[9px] font-bold text-gray-500 uppercase tracking-widest mb-1">Shift Duration</p>
                    <div className="flex items-center gap-2">
                        <input
                            type="number"
                            step="0.25"
                            placeholder="e.g. 6.25"
                            value={hours || ''}
                            onChange={(e) => onHoursChange(parseFloat(e.target.value) || 0)}
                            className="w-20 bg-transparent border-none text-white font-black text-lg focus:outline-none placeholder-gray-800"
                        />
                        <span className="text-xs font-mono text-cyan-400/50 font-bold uppercase">h</span>
                        {hours > 0 && <span className="text-[9px] font-mono text-emerald-500/50 italic ml-auto">// override active</span>}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3 mb-4 mt-4">
                <button
                    disabled={status === 'running'}
                    onClick={() => runSync(false)}
                    className="flex flex-col items-center justify-center gap-0.5 py-3 rounded-xl text-[10px] font-bold bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-all disabled:opacity-50"
                >
                    <span>Create Folders</span>
                    <span className="text-[8px] font-normal text-gray-600 normal-case">OneDrive structure</span>
                </button>
                <button
                    disabled={status === 'running'}
                    onClick={runDailySync}
                    className="flex flex-col items-center justify-center gap-0.5 py-3 rounded-xl text-[10px] font-bold bg-amber-500/15 border border-amber-500/30 text-amber-400 hover:bg-amber-500/25 transition-all disabled:opacity-50"
                >
                    <span>Rebuild Day</span>
                    <span className="text-[8px] font-normal text-amber-400/50 normal-case">Tessie + Bank + Scan</span>
                </button>
                {/* Scan Day: auto-path from selected date, no prompt, no file picker */}
                <div className="flex flex-col gap-1">
                    <button
                        disabled={status === 'running'}
                        onClick={runScanDay}
                        className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2.5 rounded-t-xl text-[10px] font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/25 transition-all disabled:opacity-50"
                    >
                        <span>Scan Day</span>
                        <span className="text-[8px] font-normal text-emerald-400/50 normal-case">Auto-scan OneDrive folder</span>
                    </button>
                    <button
                        disabled={status === 'running'}
                        onClick={runOneDriveSyncCustom}
                        className="flex flex-col items-center justify-center gap-0.5 py-1.5 rounded-b-xl text-[9px] font-bold bg-emerald-500/8 border border-t-0 border-emerald-500/20 text-emerald-600 hover:text-emerald-400 hover:bg-emerald-500/15 transition-all disabled:opacity-50"
                    >
                        <span>Custom Folder ↗</span>
                    </button>
                </div>
            </div>

            {/* Console Log Window */}
            <div className="bg-black/40 rounded-xl border border-white/5 overflow-hidden">
                <div className="px-3 py-1.5 border-b border-white/5 flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    <span className="text-[9px] font-mono text-gray-600 uppercase ml-auto">Intelligence Console</span>
                </div>
                <div className="p-3 h-32 overflow-y-auto font-mono text-[10px] space-y-1 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                    {logs.length === 0 ? (
                        <p className="text-gray-700 italic">// System Ready. Select operation for {selectedDate}.</p>
                    ) : (
                        logs.map((log, i) => (
                            <p key={i} className={
                                log.includes('[ERROR]') || log.includes('[CRITICAL]') || log.includes('ERROR:') ? 'text-rose-400' :
                                log.includes('[SUCCESS]') || log.includes('MATCH:') || log.includes('ROUTED:') ? 'text-emerald-400 font-bold' :
                                log.includes('SKIP:') ? 'text-gray-500' :
                                log.startsWith('>') ? 'text-cyan-400 font-bold border-t border-white/5 pt-1 mt-1' :
                                'text-gray-300'
                            }>
                                {log}
                            </p>
                        ))
                    )}
                    {status === 'running' && <p className="text-cyan-400 animate-pulse">_</p>}
                </div>
            </div>
        </div>
    );
};

// ─── Helper: today's date string in Mountain Time ──────────────────────────
const getTodayMST = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Denver' });

// ─── Private Payments Panel ─────────────────────────────────────────────────────

const PrivatePaymentsPanel: React.FC<{
    selectedDate: string;
    payments: PrivatePayment[];
    onAdd: (p: Omit<PrivatePayment, 'id'>) => void;
    onDelete: (id: number) => void;
}> = ({ selectedDate, payments, onAdd, onDelete }) => {
    const [client, setClient] = useState('');
    const [amount, setAmount] = useState('');
    const [note, setNote] = useState('');

    const inputCls = 'w-full p-2.5 text-sm bg-black/30 border border-white/10 rounded-xl text-white placeholder-gray-600 font-mono focus:outline-none focus:border-purple-500/50 transition-all';

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
        <div className="p-6 rounded-2xl border border-purple-500/20 relative overflow-hidden"
            style={{ background: 'rgba(139,92,246,0.05)', backdropFilter: 'blur(16px)' }}>
            <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 blur-3xl rounded-full pointer-events-none" />
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-base font-bold text-white flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-purple-400" /> Private Payments
                    </h2>
                    <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">Cash · Bundle · Off-app</p>
                </div>
                {todayPayments.length > 0 && (
                    <span className="text-xl font-black text-purple-400">${total.toFixed(2)}</span>
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
                    className="w-full py-2.5 rounded-xl font-bold text-xs uppercase tracking-widest border border-purple-500/30 bg-purple-500/15 text-purple-300 hover:bg-purple-500/25 transition-all">
                    + Log Private Payment
                </button>
            </form>

            <div className="space-y-2 max-h-[220px] overflow-y-auto">
                {todayPayments.length === 0
                    ? <p className="text-center text-xs text-gray-700 italic font-mono py-3">// no private payments for {selectedDate}</p>
                    : todayPayments.map(p => (
                        <div key={p.id} className="flex items-center justify-between p-3 rounded-xl bg-white/3 border border-white/5 group">
                            <div>
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/15 border border-purple-500/30 text-purple-300 uppercase font-mono">{p.client}</span>
                                    <span className="text-sm font-black text-white">${p.amount.toFixed(2)}</span>
                                </div>
                                {p.note && <p className="text-[10px] text-gray-500 font-mono mt-0.5">{p.note}</p>}
                            </div>
                            <button onClick={() => onDelete(p.id)}
                                className="text-gray-700 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all">
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

// Declared at module scope to satisfy react-hooks/static-components
const Bar = ({ label, earned, target, color }: { label: string; earned: number; target: number; color: string }) => {
    const pct = Math.min(100, (earned / target) * 100);
    const done = earned >= target;
    const barColor = done ? '#10b981' : pct > 60 ? '#f59e0b' : color;
    return (
        <div className="flex-1 min-w-0">
            <div className="flex justify-between items-baseline mb-1.5">
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500 font-mono">{label}</span>
                <div className="flex items-baseline gap-1.5">
                    <span className="text-sm font-black tabular-nums" style={{ color: barColor }}>${earned.toFixed(0)}</span>
                    <span className="text-[9px] text-gray-600 font-mono">/ ${target.toLocaleString()}</span>
                </div>
            </div>
            <div className="h-2 rounded-full bg-white/5 overflow-hidden relative">
                <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pct}%`, background: barColor, boxShadow: `0 0 8px ${barColor}88` }}
                />
            </div>
            <div className="flex justify-between mt-1">
                <span className="text-[8px] text-gray-700 font-mono">{pct.toFixed(0)}%</span>
                {done
                    ? <span className="text-[8px] font-bold text-emerald-500 font-mono">TARGET MET ✓</span>
                    : <span className="text-[8px] text-gray-700 font-mono">${(target - earned).toFixed(0)} to go</span>}
            </div>
        </div>
    );
};

const GoalTrackerPanel: React.FC<{ todayEarnings: number; selectedDate: string }> = ({ todayEarnings, selectedDate }) => {
    const getHistory = (): Record<string, number> => {
        try { return JSON.parse(localStorage.getItem('cos_daily_history') ?? '{}'); } catch { return {}; }
    };

    const history = getHistory();
    // Use live value for selected date, stored value for all others
    const resolve = (date: string) => date === selectedDate ? todayEarnings : (history[date] ?? 0);

    // Week span (Mon – Sun containing selectedDate)
    const refDate = new Date(selectedDate + 'T12:00:00');
    const dayOfWeek = refDate.getDay(); // 0 Sun
    const monday = new Date(refDate);
    monday.setDate(refDate.getDate() - ((dayOfWeek + 6) % 7));
    const weekDates: string[] = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(monday); d.setDate(monday.getDate() + i);
        return d.toLocaleDateString('sv-SE');
    });
    const weekEarnings = weekDates.reduce((s, d) => s + resolve(d), 0);

    // Month span
    const ym = selectedDate.slice(0, 7);
    const monthEarnings = Object.entries({ ...history, [selectedDate]: todayEarnings })
        .filter(([d]) => d.startsWith(ym))
        .reduce((s, [, v]) => s + v, 0);

    // Bar is defined at module level (below) to satisfy react-hooks/static-components

    return (
        <div className="p-5 rounded-2xl border border-cyan-500/15 relative overflow-hidden"
            style={{ background: 'rgba(6,182,212,0.03)', backdropFilter: 'blur(16px)' }}>
            <div className="absolute top-0 left-0 w-64 h-16 bg-cyan-500/8 blur-3xl rounded-full pointer-events-none" />
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-cyan-400" /> Revenue Goal Tracker
                    </h2>
                    <p className="text-[9px] text-gray-600 font-mono uppercase tracking-widest mt-0.5">
                        Monthly target: ${MONTHLY_GOAL.toLocaleString()} &middot; Daily ${DAILY_GOAL} &middot; Weekly ${WEEKLY_GOAL.toLocaleString()}
                    </p>
                </div>
                <div className="text-right">
                    <p className="text-[9px] text-gray-600 font-mono uppercase tracking-wider">Month so far</p>
                    <p className="text-lg font-black text-white tabular-nums">${monthEarnings.toFixed(0)}</p>
                </div>
            </div>
            <div className="flex gap-6">
                <Bar label="Today" earned={todayEarnings} target={DAILY_GOAL} color="#06b6d4" />
                <div className="w-[1px] bg-white/5 self-stretch" />
                <Bar label="This Week" earned={weekEarnings} target={WEEKLY_GOAL} color="#8b5cf6" />
                <div className="w-[1px] bg-white/5 self-stretch" />
                <Bar label="This Month" earned={monthEarnings} target={MONTHLY_GOAL} color="#f59e0b" />
            </div>
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
        if (typeof window === 'undefined') return { fastfood: [], charging: [] };
        try { return JSON.parse(localStorage.getItem('cos_expenses') ?? 'null') ?? { fastfood: [], charging: [] }; } catch { return { fastfood: [], charging: [] }; }
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
    const expenseFormRef = useRef<HTMLDivElement>(null);
    // Bumped by IntelligenceSyncPanel callbacks to force TessieDrivesPanel to re-fetch
    const [drivesRefreshKey, setDrivesRefreshKey] = useState(0);

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
        } catch { /* localStorage write failure — non-critical */ }
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
                    setExpenses({ fastfood: [], charging: [] });
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
                    // Only overwrite local data if cloud actually has entries for this date
                    if (cloudFood.length > 0 || cloudCharging.length > 0) {
                        setExpenses({ fastfood: cloudFood, charging: cloudCharging });
                        const now = new Date().toLocaleTimeString();
                        setLastSync(now);
                        localStorage.setItem('cos_last_sync', now);
                    }
                    // If cloud is empty, keep whatever is in localStorage (don't wipe)
                }
            }
        } catch (err) { console.error('Failed to fetch from cloud:', err); }
        finally { setIsFetchingCloud(false); }
    }, []);

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
                // This consolidates all cloud saving into one action as requested
                await fetch(`${AZURE_BASE}/daily-sync`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date: selectedDate })
                });

                setSyncMessage(`✓ Unified Cloud Sync Complete at ${now}`);
            } else {
                setSyncMessage(`✗ Save failed: ${data.error || 'Unknown error'}`);
            }
        } catch (err: unknown) {
            setSyncMessage(`✗ Network error: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
            setIsSyncingCloud(false);
            setTimeout(() => setSyncMessage(null), 4000);
        }
    }, [expenses, selectedDate]);

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
        const totalExpenses = foodTotal + chargingTotal;
        const totalIncome = uberStats.earnings + privateTotal;
        const profit = totalIncome - totalExpenses;
        const isToday = selectedDate === getTodayMST();
        
        // Prioritize manual hours override
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
        setPrivatePayments([]); setExpenses({ fastfood: [], charging: [] }); setShowResetConfirm(false);
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
            <div className="min-h-screen text-white p-3 sm:p-4 md:p-8 overflow-x-hidden"
                style={{
                    background: '#05080a',
                    backgroundImage: 'radial-gradient(circle at 50% 0%, hsla(185,90%,55%,0.12), transparent 55%), linear-gradient(to bottom, #05080a, #000)',
                }}>
                <div className="max-w-full lg:max-w-6xl mx-auto space-y-4 sm:space-y-5">
                    
                    {/* ── Tesla Status Bar (TOP) ── */}
                    <TeslaStatusBar />

                    <header
                        className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 p-5 sm:p-8 rounded-2xl border border-white/8"
                        style={{ background: 'rgba(255,255,255,0.03)', backdropFilter: 'blur(24px)' }}
                    >
                        <div className="space-y-1">
                            <p className="text-[10px] font-bold tracking-[0.4em] text-cyan-400 uppercase font-mono mb-2 flex items-center gap-2">
                                <span className="w-6 h-[1px] bg-cyan-400 inline-block" />
                                SummitOS · v{VERSION} · Driver Intelligence
                            </p>
                            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold flex items-center gap-3 tracking-tight text-white">
                                <Navigation className="text-cyan-400 w-6 h-6 md:w-8 md:h-8" />
                                Driver Dashboard
                            </h1>
                            <div className="flex flex-wrap items-center gap-2 md:gap-3 pt-2">
                                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/40 border border-white/10">
                                    <Clock className="w-3 h-3 md:w-3.5 md:h-3.5 text-gray-500" />
                                    <input
                                        type="date"
                                        value={selectedDate}
                                        onChange={(e) => { if (e.target.value) updateSelectedDate(e.target.value); }}
                                        className="bg-transparent border-none text-cyan-400 text-[10px] md:text-xs font-bold focus:outline-none cursor-pointer font-mono"
                                    />
                                </div>
                                {isFetchingCloud && (
                                    <div className="flex items-center gap-2 px-2 md:px-3 py-1.5 rounded-lg border text-[9px] md:text-[10px] font-mono uppercase tracking-wider bg-cyan-500/10 border-cyan-500/20 text-cyan-400">
                                        <Loader2 className="w-3 h-3 animate-spin" /> Syncing
                                    </div>
                                )}
                                {azureUser && (
                                    <div className="text-[9px] md:text-[10px] text-gray-500 font-mono flex items-center gap-2 px-2 md:px-3 py-1.5 rounded-lg bg-white/3 border border-white/5">
                                        <LogOut className="w-3 h-3 text-emerald-500/50" />
                                        {azureUser.split('@')[0]}
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-8 lg:gap-12">
                            <div className="flex flex-col sm:flex-row sm:items-center gap-6 sm:gap-10">
                                <div className="text-left sm:text-right">
                                    <p className="text-[10px] font-bold uppercase text-gray-600 tracking-[0.2em] font-mono mb-1">Session Profit</p>
                                    <p className={`text-2xl sm:text-3xl font-black tracking-tighter ${stats.profit >= 0 ? 'text-white' : 'text-rose-400'}`}>
                                        ${(stats.profit || 0).toFixed(2)}
                                    </p>
                                </div>
                                <div className="hidden sm:block h-10 w-[1px] bg-white/5" />
                                <div className="text-left sm:text-right">
                                    <p className="text-[10px] font-bold uppercase text-gray-600 tracking-[0.2em] font-mono mb-1">Uber + Private</p>
                                    <p className={`text-xl sm:text-2xl font-black text-white/90`}>${((stats.uberEarnings || 0) + (stats.privateTotal || 0)).toFixed(2)}</p>
                                </div>
                                <div className="hidden sm:block h-10 w-[1px] bg-white/5" />
                                <div className="text-left sm:text-right">
                                    <p className="text-[10px] font-bold uppercase text-gray-600 tracking-[0.2em] font-mono mb-1">$/Hour</p>
                                    <p className="text-xl sm:text-2xl font-black text-cyan-400/80">${Math.max(0, stats.hourlyRate || 0).toFixed(2)}</p>
                                    <p className="text-[9px] text-gray-700 font-mono italic">est. {(stats.activeHours || 0).toFixed(1)}h shift</p>
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => fetchFromCloud(selectedDate)}
                                    disabled={isFetchingCloud}
                                    className="p-2.5 rounded-xl border border-cyan-500/20 bg-cyan-500/5 text-cyan-600 hover:text-cyan-400 hover:border-cyan-500/40 transition-all"
                                    title="Refresh from Cloud">
                                    <RefreshCw className={`w-4 h-4 ${isFetchingCloud ? 'animate-spin' : ''}`} />
                                </button>
                                <button onClick={() => setShowResetConfirm(true)}
                                    className="p-2.5 rounded-xl border border-white/5 bg-white/3 text-gray-600 hover:text-rose-400 hover:border-rose-500/20 transition-all"
                                    title="Reset Session Data">
                                    <RotateCcw className="w-4 h-4" />
                                </button>
                                <a href="/.auth/logout?post_logout_redirect_uri=/"
                                    className="p-2.5 rounded-xl border border-white/5 bg-white/3 text-gray-600 hover:text-white hover:border-white/20 transition-all"
                                    title="Sign Out">
                                    <LogOut className="w-4 h-4" />
                                </a>
                            </div>
                        </div>
                    </header>

                    {/* ── Reset Confirm ── */}
                    {showResetConfirm && (
                        <div className="flex items-center justify-between bg-rose-950/50 border border-rose-500/30 rounded-2xl p-4 px-6">
                            <p className="text-sm text-rose-300 font-mono">Reset all trips and expenses for this session?</p>
                            <div className="flex gap-3">
                                <button onClick={resetSession} className="text-xs font-bold text-white bg-rose-600 hover:bg-rose-500 px-4 py-1.5 rounded-lg transition-colors">Reset</button>
                                <button onClick={() => setShowResetConfirm(false)} className="text-xs font-bold text-gray-400 hover:text-white px-4 py-1.5 rounded-lg transition-colors">Cancel</button>
                            </div>
                        </div>
                    )}

                    {/* ── Stat Cards ── */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <StatCard label="Uber Earnings" value={`$${(stats.uberEarnings || 0).toFixed(2)}`}
                            sub={`${stats.uberCount || 0} OCR trips`}
                            icon={<Receipt className="text-cyan-400 w-5 h-5" />} highlight />
                        <StatCard label="Private Income" value={`$${(stats.privateTotal || 0).toFixed(2)}`}
                            sub="Jackie · Esmeralda · Other"
                            icon={<DollarSign className="text-purple-400 w-5 h-5" />} />
                        <StatCard label="Expenses" value={`$${(stats.totalExpenses || 0).toFixed(2)}`}
                            sub={`Food $${(stats.food||0).toFixed(2)} · Charge $${(stats.charging||0).toFixed(2)}`}
                            icon={<Zap className="text-amber-400 w-5 h-5" />} />
                        <StatCard label="Net Profit" value={`$${(stats.profit || 0).toFixed(2)}`}
                            sub={`≈ $${(stats.hourlyRate || 0).toFixed(2)}/hr`}
                            icon={<TrendingUp className="text-emerald-400 w-5 h-5" />} highlight />
                    </div>

                    {/* ── Goal Tracker ── */}
                    <GoalTrackerPanel
                        todayEarnings={(stats.uberEarnings || 0) + (stats.privateTotal || 0)}
                        selectedDate={selectedDate}
                    />

                    {/* ── Main Grid ── */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                        {/* Left Column */}
                        <div className="space-y-5">
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

                        {/* Right Columns */}
                        <div className="lg:col-span-2 space-y-6" ref={expenseFormRef}>
                            <TessieChargesPanel onImport={handleImportCharge} selectedDate={selectedDate} />
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <ExpenseList
                                    title="Charging Sessions"
                                    data={expenses.charging.filter(e => e.timestamp.startsWith(selectedDate))}
                                    icon={<Zap className="w-4 h-4 text-amber-400" />}
                                    onDelete={(id) => deleteExpense('charging', id)}
                                    onAdd={(amount, note) => setExpenses(prev => ({
                                        ...prev,
                                        charging: [{ id: Date.now(), amount, note, timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}` }, ...prev.charging]
                                    }))}
                                    accentColor="text-amber-400"
                                />
                                <ExpenseList
                                    title="Food & Drinks"
                                    data={expenses.fastfood.filter(e => e.timestamp.startsWith(selectedDate))}
                                    icon={<Utensils className="w-4 h-4 text-rose-400" />}
                                    onDelete={(id) => deleteExpense('fastfood', id)}
                                    onAdd={(amount, note) => setExpenses(prev => ({
                                        ...prev,
                                        fastfood: [{ id: Date.now(), amount, note, timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}` }, ...prev.fastfood]
                                    }))}
                                    accentColor="text-rose-400"
                                />
                            </div>
                            {/* Sync expenses to cloud */}
                            <div className="flex items-center gap-3 pt-1">
                                <button
                                    onClick={syncToCloud}
                                    disabled={isSyncingCloud}
                                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-cyan-500/20 border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/30 hover:scale-[1.02] transition-all disabled:opacity-50 shadow-[0_0_20px_rgba(34,211,238,0.1)]"
                                >
                                    <Cloud className="w-4 h-4" />
                                    {isSyncingCloud ? 'Saving Day...' : 'Save Day to Cloud'}
                                </button>
                                {syncMessage && (
                                    <span className={`text-xs font-mono ${
                                        syncMessage.startsWith('✓') ? 'text-emerald-400' : 'text-rose-400'
                                    }`}>{syncMessage}</span>
                                )}
                                {isFetchingCloud && (
                                    <span className="text-xs font-mono text-gray-500">↓ loading cloud...</span>
                                )}
                            </div>
                        </div>
                    </div>

                {/* ── Uber Trips Panel — OCR numbered trip cards (source of truth) ── */}
                <UberTripsPanel
                    selectedDate={selectedDate}
                    onTripsLoaded={(count, earnings) => setUberStats({ count, earnings })}
                />

                {/* ── Tessie Drives Panel (full width) ── */}
                <TessieDrivesPanel onImport={() => {}} selectedDate={selectedDate} refreshKey={drivesRefreshKey} />


                {/* Footer */}
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
