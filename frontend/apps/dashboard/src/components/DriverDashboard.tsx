'use client';

import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
    TrendingUp, Car, Zap, Utensils, Plus, Trash2,
    Navigation, Receipt, RotateCcw, Clock,
    Battery, BatteryCharging, WifiOff, Download,
    MapPin, Gauge, LogOut, Cpu, RefreshCw, Cloud, Loader2, Check,
    ShieldAlert
} from 'lucide-react';

// ─── Constants ─────────────────────────────────────────────────────────────
const AZURE_BASE = 'https://summitos-api.azurewebsites.net/api';
const VERSION = "2.1.0-CLEAN";
const TAG_FILTERS = ['Uber', 'Jackie', 'Esmeralda'] as const;

// ─── Types ──────────────────────────────────────────────────────────────────
interface Trip {
    id: number;
    type: 'Uber' | 'Private';
    fare: number;
    tip?: number;
    fees: number;
    insurance: number;
    otherFees: number;
    timestamp: string;
    duration_minutes?: number;
    tessie_drive_id?: string;
    distance_miles?: number;
    validation_status?: 'Verified' | 'Mismatch' | null;
    ocr_suggested?: any;
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

interface TripForm {
    type: 'Uber' | 'Private';
    fare: string;
    tip: string;
    fees: string;
    insurance: string;
    otherFees: string;
}

interface ExpenseForm {
    category: keyof Expenses;
    amount: string;
    note: string;
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
    title, data, icon, onDelete, accentColor,
}: {
    title: string; data: Expense[]; icon: React.ReactNode;
    onDelete: (id: number) => void; accentColor: string;
}) => (
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
        <div className="max-h-[260px] overflow-y-auto">
            {data.length === 0
                ? <p className="p-8 text-center text-xs text-gray-600 italic font-mono">// no entries</p>
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
    </div>
);

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
    uber: 'bg-white/10 text-white border-white/20',
    jackie: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
    esmeralda: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
};
const tagStyle = (tag: string | null) => {
    const key = (tag ?? '').toLowerCase();
    for (const [k, v] of Object.entries(TAG_STYLE)) if (key.includes(k)) return v;
    return 'bg-gray-700/30 text-gray-400 border-gray-600/30';
};
const tagTripType = (tag: string | null): 'Uber' | 'Private' => {
    const lower = (tag ?? '').toLowerCase();
    return lower.includes('uber') ? 'Uber' : 'Private';
};

// ─── Tessie Drives Panel ─────────────────────────────────────────────────────
const TessieDrivesPanel = ({
    onImport,
    selectedDate
}: {
    onImport: (drive: TessieDrive) => void;
    selectedDate: string;
}) => {
    const [drives, setDrives] = useState<TessieDrive[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [importedIds, setImportedIds] = useState<Set<string>>(new Set());

    useEffect(() => {
        setLoading(true);
        setError(false);
        const fetchAll = async () => {
            try {
                const today = new Date();
                const target = new Date(selectedDate + 'T12:00:00');
                const diffMs = today.getTime() - target.getTime();
                const daysBack = Math.max(1, Math.ceil(diffMs / 86_400_000) + 1);
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

                // Merge & deduplicate by tessie_drive_id
                const seen = new Set<string>();
                const merged: TessieDrive[] = [];
                for (const batch of results) {
                    for (const d of batch) {
                        if (!seen.has(d.tessie_drive_id)) {
                            seen.add(d.tessie_drive_id);
                            merged.push(d);
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
        };
        fetchAll();
    }, [selectedDate]);

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

// ─── Intelligence Sync Panel ─────────────────────────────────────────────────
const IntelligenceSyncPanel: React.FC<{ selectedDate: string }> = ({ selectedDate }) => {
    const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
    const [logs, setLogs] = useState<string[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        setStatus('running');
        setLogs([`> Starting bulk OCR match for ${files.length} screenshots...`]);

        let successCount = 0;
        let failCount = 0;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            setLogs(prev => [...prev, `> Uploading (${i + 1}/${files.length}): ${file.name}...`]);

            const formData = new FormData();
            formData.append('file', file);

            try {
                const resp = await fetch(`${AZURE_BASE}/operations/upload-screenshot`, {
                    method: 'POST',
                    body: formData
                });
                const data = await resp.json();

                if (data.success) {
                    successCount++;
                    setLogs(prev => [
                        ...prev,
                        `> [SUCCESS] MATCHED: ${file.name}`,
                        `  Earnings: $${data.result.card.driver_earnings}`,
                        `  Fare: $${data.result.card.rider_payment}`,
                        `  Trip updated.`
                    ]);
                } else {
                    failCount++;
                    setLogs(prev => [...prev, `> [ERROR] ${data.error || data.result?.message || 'Failed to match screenshot'}`]);
                }
            } catch (err: any) {
                failCount++;
                setLogs(prev => [...prev, `> [CRITICAL] Upload failed: ${err.message}`]);
            }
        }
        
        setStatus(failCount === 0 ? 'success' : 'error');
        setLogs(prev => [...prev, `> Bulk upload complete. ${successCount} matched, ${failCount} failed.`]);
        
        // Reset input so the same files can be selected again if needed
        if (fileInputRef.current) fileInputRef.current.value = '';
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
        } catch (e: any) {
            setStatus('error');
            setLogs(prev => [...prev, `> [CRITICAL] ${e.message}`]);
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
            } else {
                setStatus('error');
                setLogs(prev => [...prev, ...(data.logs || []), `> [ERROR] ${data.error}`]);
            }
        } catch (e: any) {
            setStatus('error');
            setLogs(prev => [...prev, `> [CRITICAL] ${e.message}`]);
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
                <button
                    disabled={status === 'running'}
                    onClick={() => fileInputRef.current?.click()}
                    className="flex flex-col items-center justify-center gap-0.5 py-3 rounded-xl text-[10px] font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/25 transition-all disabled:opacity-50"
                >
                    <input 
                        type="file" 
                        ref={fileInputRef} 
                        onChange={handleFileUpload} 
                        accept="image/*" 
                        multiple
                        className="hidden" 
                    />
                    <span>Upload Screenshot</span>
                    <span className="text-[8px] font-normal text-emerald-400/50 normal-case">Direct OCR Match</span>
                </button>
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



const DriverDashboard = () => {
    const [lastSync, setLastSync] = useState<string | null>(() => {
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

    const [trips, setTrips] = useState<Trip[]>(() => {
        if (typeof window === 'undefined') return [];
        try { return JSON.parse(localStorage.getItem('cos_trips') ?? '[]'); } catch { return []; }
    });
    const [expenses, setExpenses] = useState<Expenses>(() => {
        if (typeof window === 'undefined') return { fastfood: [], charging: [] };
        try { return JSON.parse(localStorage.getItem('cos_expenses') ?? 'null') ?? { fastfood: [], charging: [] }; } catch { return { fastfood: [], charging: [] }; }
    });

    const [pendingDrive, setPendingDrive] = useState<TessieDrive | null>(null);


    const [tripForm, setTripForm] = useState<TripForm>({
        type: 'Uber', fare: '', tip: '', fees: '', insurance: '', otherFees: '',
    });
    const [expenseForm, setExpenseForm] = useState<ExpenseForm>({
        category: 'fastfood', amount: '', note: '',
    });
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
    const [editingTripId, setEditingTripId] = useState<number | null>(null);
    const [showResetConfirm, setShowResetConfirm] = useState(false);

    const tripFormRef = useRef<HTMLDivElement>(null);
    const expenseFormRef = useRef<HTMLDivElement>(null);

    // ── Persist to localStorage on every change ──────────────────────────────
    useEffect(() => { localStorage.setItem('cos_trips', JSON.stringify(trips)); }, [trips]);
    useEffect(() => { localStorage.setItem('cos_expenses', JSON.stringify(expenses)); }, [expenses]);

    // ── Auto-advance to a new day at midnight ────────────────────────────────
    useEffect(() => {
        const checkDay = () => {
            const today = getTodayMST();
            const storedDate = localStorage.getItem('cos_session_date');
            if (storedDate && storedDate !== today) {
                // Midnight crossed — reset session automatically
                // But only if we are currently on "Today"
                const currentSelected = localStorage.getItem('cos_selected_date');
                if (!currentSelected || currentSelected === storedDate) {
                    localStorage.removeItem('cos_trips');
                    localStorage.removeItem('cos_expenses');
                    localStorage.removeItem('cos_session_start');
                    localStorage.setItem('cos_session_date', today);
                    localStorage.setItem('cos_selected_date', today);
                    setTrips([]);
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
    
    const fetchFromCloud = useCallback(async (date: string) => {
        setIsFetchingCloud(true);
        try {
            const resp = await fetch(`${AZURE_BASE}/driver/sync?date=${date}&t=${Date.now()}`, {
                cache: 'no-store'
            });
            if (resp.ok) {
                const data = await resp.json();
                if (data.success) {
                    // Only update if we actually got data back to avoid wiping local work 
                    // unless the cloud is explicitly the source of truth.
                    // For syncing, cloud IS the source of truth.
                    setTrips(data.trips || []);
                    setExpenses(data.expenses || { fastfood: [], charging: [] });
                    const now = new Date().toLocaleTimeString();
                    const tripCount = (data.trips || []).length;
                    setLastSync(`${now} (${tripCount} trips)`);
                    localStorage.setItem('cos_last_sync', `${now} (${tripCount} trips)`);
                    console.log(`Cloud data synced: ${tripCount} trips found.`);
                }
            }
        } catch (err) {
            console.error('Failed to fetch from cloud:', err);
        } finally {
            setIsFetchingCloud(false);
        }
    }, []);

    useEffect(() => {
        fetchFromCloud(selectedDate);
    }, [selectedDate, fetchFromCloud]);

    const stats = useMemo(() => {
        const totalVolume = trips.reduce((sum, t) => sum + (t.fare || 0) + (t.tip || 0), 0);
        const totalFees = trips.reduce((sum, t) => sum + (t.fees || 0) + (t.insurance || 0) + (t.otherFees || 0), 0);
        const driverPay = totalVolume - totalFees;
        
        const foodTotal = expenses.fastfood.reduce((sum, e) => sum + (e.amount || 0), 0);
        const chargingTotal = expenses.charging.reduce((sum, e) => sum + (e.amount || 0), 0);
        
        const uberTrips = trips.filter((t) => t.type === 'Uber').length;
        const privateTrips = trips.filter((t) => t.type === 'Private').length;
        
        // --- Improved Hourly Rate Logic ---
        const isToday = selectedDate === getTodayMST();
        let activeHours = 0;

        if (isToday) {
            // Shift-based tracking for today (real-time)
            activeHours = (Date.now() - sessionStart.getTime()) / 3_600_000;
        } else if (trips.length > 0) {
            // Activity-based tracking for historical days
            const sorted = [...trips].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
            const start = new Date(sorted[0].timestamp).getTime();
            const end = new Date(sorted[sorted.length - 1].timestamp).getTime();
            const spanHours = (end - start) / 3_600_000;
            
            // If the span is less than 6 hours, assume a standard 6-hour shift floor 
            // for historical reporting unless they've logged more than 6 hours of drive time.
            activeHours = Math.max(spanHours + 1.0, 6.0); 
        }
        
        const profit = driverPay - foodTotal - chargingTotal;
        const hourlyRate = activeHours > 0.5 ? profit / activeHours : 0;
        
        return {
            volume: totalVolume,
            fees: totalFees,
            driverPay: driverPay,
            food: foodTotal, 
            charging: chargingTotal,
            profit, 
            uberCount: uberTrips, 
            privateCount: privateTrips, 
            hourlyRate,
            activeHours
        };
    }, [trips, expenses, sessionStart, selectedDate]);


    const addTrip = (e: React.FormEvent) => {
        e.preventDefault();
        if (!tripForm.fare) return;

        const newTrip: Trip = {
            id: editingTripId ?? Date.now(),
            type: tripForm.type,
            fare: parseFloat(tripForm.fare) || 0,
            tip: tripForm.type === 'Uber' ? (parseFloat(tripForm.tip) || 0) : undefined,
            fees: parseFloat(tripForm.fees) || 0,
            insurance: parseFloat(tripForm.insurance) || 0,
            otherFees: parseFloat(tripForm.otherFees) || 0,
            timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`,
            tessie_drive_id: pendingDrive?.tessie_drive_id,
            distance_miles: pendingDrive?.distance_miles
        };

        if (editingTripId) {
            setTrips(trips.map(t => t.id === editingTripId ? newTrip : t));
            setEditingTripId(null);
        } else {
            setTrips([newTrip, ...trips]);
        }

        setTripForm({ type: 'Uber', fare: '', tip: '', fees: '', insurance: '', otherFees: '' });
        setPendingDrive(null);
    };

    const handleEditTrip = (trip: Trip) => {
        setEditingTripId(trip.id);
        setTripForm({
            type: trip.type,
            fare: trip.fare.toString(),
            tip: (trip.tip ?? '').toString(),
            fees: trip.fees.toString(),
            insurance: trip.insurance.toString(),
            otherFees: trip.otherFees.toString()
        });
        tripFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const addExpense = (e: React.FormEvent) => {
        e.preventDefault();
        if (!expenseForm.amount) return;
        setExpenses((prev) => ({
            ...prev,
            [expenseForm.category]: [{
                id: Date.now(),
                amount: parseFloat(expenseForm.amount) || 0,
                note: expenseForm.note,
                timestamp: `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`,
            }, ...prev[expenseForm.category]],
        }));
        setExpenseForm({ ...expenseForm, amount: '', note: '' });
    };

    const deleteTrip = (id: number) => setTrips(trips.filter((t) => t.id !== id));
    const deleteExpense = (cat: keyof Expenses, id: number) =>
        setExpenses((prev) => ({ ...prev, [cat]: prev[cat].filter((e) => e.id !== id) }));
    const resetSession = () => {
        localStorage.removeItem('cos_trips');
        localStorage.removeItem('cos_expenses');
        localStorage.removeItem('cos_session_start');
        localStorage.setItem('cos_session_date', getTodayMST());
        const d = new Date();
        setSessionStart(d);
        localStorage.setItem('cos_session_start', d.toISOString());
        setTrips([]); setExpenses({ fastfood: [], charging: [] }); setShowResetConfirm(false);
    };

    const [syncing, setSyncing] = useState(false);
    const [syncStatus, setSyncStatus] = useState<'idle' | 'success' | 'error'>('idle');

    const syncToCloud = async () => {
        if (trips.length === 0 && expenses.fastfood.length === 0 && expenses.charging.length === 0) {
            alert("Nothing to sync yet! Add some trips or expenses first.");
            return;
        }
        setSyncing(true);
        setSyncStatus('idle');
        try {
            const resp = await fetch(`${AZURE_BASE}/driver/sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trips, expenses })
            });
            if (resp.ok) {
                setSyncStatus('success');
                setTimeout(() => setSyncStatus('idle'), 3000);
            } else {
                setSyncStatus('error');
            }
        } catch (err) {
            console.error('Sync failed:', err);
            setSyncStatus('error');
        } finally {
            setSyncing(false);
        }
    };

    /** Called from TessieDrivesPanel — pre-fill the trip form and scroll to it */
    const handleImportDrive = (drive: TessieDrive) => {
        setPendingDrive(drive);
        setTripForm({
            type: tagTripType(drive.tag),
            fare: '',
            tip: '',
            fees: '',
            insurance: '',
            otherFees: '',
        });
        tripFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const handleImportCharge = (charge: TessieCharge) => {
        setExpenseForm({
            category: 'charging',
            amount: '',
            note: `Tesla EV Charging – ${charge.energy_added_kwh.toFixed(1)} kWh${charge.location ? ` @ ${charge.location}` : ''}${charge.time_mst ? ` (${charge.time_mst})` : ''}`,
        });
        expenseFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const inputCls = 'w-full p-2.5 text-sm bg-black/30 border border-white/10 rounded-xl text-white placeholder-gray-600 font-mono focus:outline-none focus:border-cyan-500/50 focus:shadow-[0_0_15px_rgba(0,242,255,0.15)] transition-all';

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

    return (
        <div className="min-h-screen bg-black text-white flex items-center justify-center p-8">
            <div className="text-center space-y-4">
                <h1 className="text-4xl font-bold text-cyan-400">SummitOS Debug</h1>
                <p className="text-gray-400 font-mono">Dashboard v{VERSION} is attempting to render...</p>
                <div className="p-4 bg-white/5 border border-white/10 rounded-xl">
                    <p className="text-xs text-gray-500">Selected Date: {selectedDate}</p>
                    <p className="text-xs text-gray-500">User: {azureUser || 'Guest'}</p>
                </div>
                <button 
                    onClick={() => window.location.reload()}
                    className="px-6 py-2 bg-cyan-500 text-black font-bold rounded-lg"
                >
                    Hard Refresh
                </button>
            </div>
        </div>
    );
};

export default DriverDashboard;
