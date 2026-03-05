'use client';

import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
    TrendingUp, Car, Zap, Utensils, Plus, Trash2,
    Navigation, Receipt, RotateCcw, Clock,
    Battery, BatteryCharging, WifiOff, Download,
    MapPin, Gauge, LogOut
} from 'lucide-react';

// ─── Constants ─────────────────────────────────────────────────────────────
const AZURE_BASE = 'https://summitos-api.azurewebsites.net/api';
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
    tessie_drive_id?: string;
    distance_miles?: number;
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
        const iv = setInterval(fetchStatus, 300_000); // refresh every 5 min
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
                <span className="text-[10px] font-bold uppercase tracking-[0.25em] font-mono text-gray-500">Tesla Live</span>
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
                    <div className="flex items-center gap-3 flex-1 min-w-[160px]">
                        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                            <div
                                className={`h-full ${barColor} transition-all duration-700`}
                                style={{ width: `${soc ?? 0}%` }}
                            />
                        </div>
                        <span className={`text-sm font-black font-mono tabular-nums ${barColor.replace('bg-', 'text-')}`}>
                            {soc !== null ? `${soc}%` : '--'}
                        </span>
                    </div>

                    {/* Range */}
                    {range !== null && (
                        <div className="flex items-center gap-1.5 shrink-0">
                            <Gauge className="w-3.5 h-3.5 text-gray-500" />
                            <span className="text-sm font-bold text-white tabular-nums">{range.toFixed(0)}<span className="text-gray-600 font-normal text-xs"> mi</span></span>
                        </div>
                    )}

                    {/* Charging info */}
                    {isCharging && (
                        <div className="flex items-center gap-1.5 shrink-0">
                            <Zap className="w-3.5 h-3.5 text-emerald-400" />
                            <span className="text-sm font-bold text-emerald-400 tabular-nums">{kw} kW</span>
                            {minsToFull !== null && (
                                <span className="text-xs text-gray-500 font-mono">({Math.round(minsToFull / 60)}h {minsToFull % 60}m to full)</span>
                            )}
                        </div>
                    )}

                    {/* State label */}
                    {chargingState && !isCharging && (
                        <span className="text-[10px] text-gray-600 font-mono uppercase tracking-wider shrink-0">{chargingState}</span>
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
}: {
    onImport: (drive: TessieDrive) => void;
}) => {
    const [drives, setDrives] = useState<TessieDrive[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [importedIds, setImportedIds] = useState<Set<string>>(new Set());
    const [selectedDate, setSelectedDate] = useState('2026-03-02');

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
                        fetch(`${AZURE_BASE}/copilot/tessie/drives?tag=${tag}&days=${daysBack}`, {
                            signal: AbortSignal.timeout(12_000),
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
                    <input
                        type="date"
                        value={selectedDate}
                        onChange={(e) => { if (e.target.value) setSelectedDate(e.target.value); }}
                        className="text-xs font-mono bg-black/40 border border-white/12 text-cyan-400 rounded-xl px-3 py-1.5 focus:outline-none focus:border-cyan-500/50 cursor-pointer"
                    />
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
const DriverDashboard = () => {
    const [trips, setTrips] = useState<Trip[]>([]);
    const [expenses, setExpenses] = useState<Expenses>({ fastfood: [], charging: [] });
    const [tripForm, setTripForm] = useState<TripForm>({
        type: 'Uber', fare: '', tip: '', fees: '', insurance: '', otherFees: '',
    });
    const [expenseForm, setExpenseForm] = useState<ExpenseForm>({
        category: 'fastfood', amount: '', note: '',
    });
    const [sessionStart] = useState<Date>(new Date());
    const [showResetConfirm, setShowResetConfirm] = useState(false);
    const tripFormRef = useRef<HTMLDivElement>(null);

    const stats = useMemo(() => {
        const totalEarnings = trips.reduce((sum, t) => sum + t.fare + (t.tip || 0), 0);
        const totalFees = trips.reduce((sum, t) => sum + t.fees + t.insurance + t.otherFees, 0);
        const netEarnings = totalEarnings - totalFees;
        const foodTotal = expenses.fastfood.reduce((sum, e) => sum + e.amount, 0);
        const chargingTotal = expenses.charging.reduce((sum, e) => sum + e.amount, 0);
        const uberTrips = trips.filter((t) => t.type === 'Uber').length;
        const privateTrips = trips.filter((t) => t.type === 'Private').length;
        const elapsedHours = (Date.now() - sessionStart.getTime()) / 3_600_000;
        const profit = netEarnings - foodTotal - chargingTotal;
        const hourlyRate = elapsedHours > 0.1 ? profit / elapsedHours : 0;
        return {
            gross: totalEarnings, fees: totalFees, net: netEarnings,
            food: foodTotal, charging: chargingTotal,
            profit, uberCount: uberTrips, privateCount: privateTrips, hourlyRate,
        };
    }, [trips, expenses, sessionStart]);

    const addTrip = (e: React.FormEvent) => {
        e.preventDefault();
        if (!tripForm.fare) return;
        setTrips([{
            id: Date.now(),
            type: tripForm.type,
            fare: parseFloat(tripForm.fare) || 0,
            tip: tripForm.type === 'Uber' ? (parseFloat(tripForm.tip) || 0) : undefined,
            fees: parseFloat(tripForm.fees) || 0,
            insurance: parseFloat(tripForm.insurance) || 0,
            otherFees: parseFloat(tripForm.otherFees) || 0,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }, ...trips]);
        setTripForm({ type: 'Uber', fare: '', tip: '', fees: '', insurance: '', otherFees: '' });
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
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            }, ...prev[expenseForm.category]],
        }));
        setExpenseForm({ ...expenseForm, amount: '', note: '' });
    };

    const deleteTrip = (id: number) => setTrips(trips.filter((t) => t.id !== id));
    const deleteExpense = (cat: keyof Expenses, id: number) =>
        setExpenses((prev) => ({ ...prev, [cat]: prev[cat].filter((e) => e.id !== id) }));
    const resetSession = () => { setTrips([]); setExpenses({ fastfood: [], charging: [] }); setShowResetConfirm(false); };

    /** Called from TessieDrivesPanel — pre-fill the trip form and scroll to it */
    const handleImportDrive = (drive: TessieDrive) => {
        setTripForm({
            type: tagTripType(drive.tag),
            fare: '',
            fees: '',
            insurance: '',
            otherFees: '',
        });
        tripFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        <div className="min-h-screen text-white p-4 md:p-8"
            style={{
                background: '#05080a',
                backgroundImage: 'radial-gradient(circle at 50% 0%, hsla(185,90%,55%,0.12), transparent 55%), linear-gradient(to bottom, #05080a, #000)',
            }}>
            <div className="max-w-6xl mx-auto space-y-5">

                {/* ── Header ── */}
                <header
                    className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-2xl border border-white/8"
                    style={{ background: 'rgba(255,255,255,0.03)', backdropFilter: 'blur(20px)' }}
                >
                    <div>
                        <p className="text-[10px] font-bold tracking-[0.4em] text-cyan-400 uppercase font-mono mb-2 flex items-center gap-2">
                            <span className="w-6 h-[1px] bg-cyan-400 inline-block" />
                            COS Tesla · Driver Mode
                        </p>
                        <h1 className="text-3xl font-bold flex items-center gap-3 tracking-tight">
                            <Navigation className="text-cyan-400 w-7 h-7" />
                            Driver Dashboard
                        </h1>
                        <p className="text-gray-500 font-mono text-xs mt-1 tracking-wider">
                            SESSION · {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                            {azureUser && <span className="ml-3 text-cyan-400/60">· {azureUser}</span>}
                        </p>
                    </div>

                    <div className="flex items-end gap-8">
                        <div className="text-right">
                            <p className="text-[10px] font-bold uppercase text-gray-600 tracking-[0.2em] font-mono">Net Profit</p>
                            <p className={`text-4xl font-black tracking-tighter ${stats.profit >= 0 ? 'text-cyan-400' : 'text-rose-400'}`}
                                style={{ textShadow: stats.profit >= 0 ? '0 0 30px rgba(0,242,255,0.5)' : '0 0 30px rgba(244,63,94,0.4)' }}>
                                ${stats.profit.toFixed(2)}
                            </p>
                        </div>
                        <div className="text-right">
                            <p className="text-[10px] font-bold uppercase text-gray-600 tracking-[0.2em] font-mono">Est. $/hr</p>
                            <p className="text-2xl font-black text-white">${Math.max(0, stats.hourlyRate).toFixed(2)}</p>
                        </div>
                        <button onClick={() => setShowResetConfirm(true)}
                            className="p-2 rounded-xl border border-white/10 text-gray-600 hover:text-rose-400 hover:border-rose-500/30 transition-all"
                            title="Reset Day">
                            <RotateCcw className="w-4 h-4" />
                        </button>
                        <a href="/.auth/logout?post_logout_redirect_uri=/"
                            className="p-2 rounded-xl border border-white/10 text-gray-600 hover:text-rose-400 hover:border-rose-500/30 transition-all flex items-center gap-1.5 text-xs font-mono"
                            title="Sign Out">
                            <LogOut className="w-4 h-4" />
                        </a>
                    </div>
                </header>

                {/* ── Tesla Status Bar ── */}
                <TeslaStatusBar />

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
                    <StatCard label="Total Trips" value={trips.length}
                        sub={`${stats.uberCount} Uber · ${stats.privateCount} Private`}
                        icon={<Car className="text-cyan-400 w-5 h-5" />} />
                    <StatCard label="Gross" value={`$${stats.gross.toFixed(2)}`}
                        sub={`Fees: $${stats.fees.toFixed(2)}`}
                        icon={<TrendingUp className="text-cyan-400 w-5 h-5" />} highlight />
                    <StatCard label="Charging" value={`$${stats.charging.toFixed(2)}`} sub="Fuel & Power"
                        icon={<Zap className="text-amber-400 w-5 h-5" />} />
                    <StatCard label="Fast Food" value={`$${stats.food.toFixed(2)}`} sub="Meals & Drinks"
                        icon={<Utensils className="text-rose-400 w-5 h-5" />} />
                </div>

                {/* ── Main Grid ── */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                    {/* Forms Column */}
                    <div className="space-y-5">

                        {/* Trip Entry */}
                        <div ref={tripFormRef}
                            className="p-6 rounded-2xl border border-white/8"
                            style={{ background: 'rgba(255,255,255,0.03)', backdropFilter: 'blur(16px)' }}>
                            <h2 className="text-base font-bold mb-4 flex items-center gap-2 text-white">
                                <Plus className="w-4 h-4 text-cyan-400" /> Log New Trip
                            </h2>
                            <form onSubmit={addTrip} className="space-y-3">
                                <div className="grid grid-cols-2 gap-2">
                                    {(['Uber', 'Private'] as const).map((t) => (
                                        <button key={t} type="button"
                                            onClick={() => setTripForm({ ...tripForm, type: t })}
                                            className={`p-2 rounded-xl text-sm font-bold transition-all border ${tripForm.type === t
                                                ? t === 'Uber'
                                                    ? 'bg-white text-black border-white'
                                                    : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-[0_0_15px_rgba(0,242,255,0.15)]'
                                                : 'bg-white/5 text-gray-500 border-white/8 hover:border-white/20'}`}>
                                            {t}
                                        </button>
                                    ))}
                                </div>
                                <div>
                                    <label className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] font-mono mb-1 block">Passenger Paid ($)</label>
                                    <input type="number" step="0.01" className={inputCls} value={tripForm.fare}
                                        onChange={(e) => setTripForm({ ...tripForm, fare: e.target.value })} placeholder="0.00" />
                                </div>
                                {tripForm.type === 'Uber' && (
                                    <div>
                                        <label className="text-[10px] font-bold text-emerald-500/80 uppercase tracking-[0.2em] font-mono mb-1 block">Tip ($) <span className="text-gray-600 normal-case tracking-normal">optional</span></label>
                                        <input type="number" step="0.01" className={inputCls + ' focus:border-emerald-500/50 focus:shadow-[0_0_15px_rgba(16,185,129,0.15)]'} value={tripForm.tip}
                                            onChange={(e) => setTripForm({ ...tripForm, tip: e.target.value })} placeholder="0.00" />
                                    </div>
                                )}
                                <div className="grid grid-cols-3 gap-2">
                                    {[{ key: 'fees', label: 'Fees' }, { key: 'insurance', label: 'Insur.' }, { key: 'otherFees', label: 'Other' }].map(({ key, label }) => (
                                        <div key={key}>
                                            <label className="text-[10px] font-bold text-gray-600 uppercase tracking-[0.15em] font-mono mb-1 block">{label}</label>
                                            <input type="number" step="0.01" className={inputCls}
                                                value={tripForm[key as keyof TripForm]}
                                                onChange={(e) => setTripForm({ ...tripForm, [key]: e.target.value })} placeholder="0.00" />
                                        </div>
                                    ))}
                                </div>
                                <button type="submit"
                                    className="w-full py-3 rounded-xl font-bold text-sm text-black transition-all hover:brightness-110 hover:-translate-y-0.5"
                                    style={{ background: 'linear-gradient(135deg, hsl(185,70%,40%), hsl(190,100%,60%), hsl(185,70%,40%))', boxShadow: '0 4px 20px rgba(0,242,255,0.25)' }}>
                                    LOG TRIP
                                </button>
                            </form>
                        </div>

                        {/* Expense Entry */}
                        <div className="p-6 rounded-2xl border border-white/8"
                            style={{ background: 'rgba(255,255,255,0.03)', backdropFilter: 'blur(16px)' }}>
                            <h2 className="text-base font-bold mb-4 flex items-center gap-2 text-white">
                                <Receipt className="w-4 h-4 text-rose-400" /> Log Expense
                            </h2>
                            <form onSubmit={addExpense} className="space-y-4">
                                <div className="flex gap-2">
                                    {[
                                        { key: 'fastfood', label: '🍔 Food', active: 'bg-rose-500/15 border-rose-500/40 text-rose-300' },
                                        { key: 'charging', label: '⚡ Charge', active: 'bg-amber-500/15 border-amber-500/40 text-amber-300' },
                                    ].map(({ key, label, active }) => (
                                        <button key={key} type="button"
                                            onClick={() => setExpenseForm({ ...expenseForm, category: key as keyof Expenses })}
                                            className={`flex-1 p-2 rounded-xl text-sm font-bold border transition-all ${expenseForm.category === key ? active : 'bg-white/5 border-white/8 text-gray-500 hover:border-white/20'}`}>
                                            {label}
                                        </button>
                                    ))}
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    <input type="number" step="0.01" placeholder="Amount" className={inputCls}
                                        value={expenseForm.amount}
                                        onChange={(e) => setExpenseForm({ ...expenseForm, amount: e.target.value })} />
                                    <input type="text" placeholder="Note" className={inputCls}
                                        value={expenseForm.note}
                                        onChange={(e) => setExpenseForm({ ...expenseForm, note: e.target.value })} />
                                </div>
                                <button type="submit"
                                    className="w-full py-3 rounded-xl font-bold text-sm text-white bg-white/8 border border-white/12 hover:bg-white/12 hover:border-white/20 transition-all">
                                    ADD EXPENSE
                                </button>
                            </form>
                        </div>
                    </div>

                    {/* Trips + Expenses Column */}
                    <div className="lg:col-span-2 space-y-5">

                        {/* Trip History Table */}
                        <div className="rounded-2xl border border-white/8 overflow-hidden"
                            style={{ background: 'rgba(255,255,255,0.02)', backdropFilter: 'blur(16px)' }}>
                            <div className="p-5 border-b border-white/8 flex justify-between items-center">
                                <h2 className="font-bold text-white flex items-center gap-2">
                                    <Clock className="w-4 h-4 text-cyan-400" /> Recent Trips
                                </h2>
                                <span className="text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-3 py-1 rounded-full font-mono uppercase tracking-widest">
                                    Today · {trips.length} trips
                                </span>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead>
                                        <tr className="text-[10px] text-gray-600 uppercase font-mono tracking-widest border-b border-white/5">
                                            <th className="px-5 py-3">Type</th>
                                            <th className="px-5 py-3 text-right">Fare</th>
                                            <th className="px-5 py-3 text-right">Deducted</th>
                                            <th className="px-5 py-3 text-right">Net</th>
                                            <th className="px-5 py-3 text-right">Margin</th>
                                            <th className="px-5 py-3" />
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {trips.length === 0
                                            ? <tr><td colSpan={6} className="px-5 py-16 text-center text-gray-700 italic font-mono text-sm">// no trips recorded yet</td></tr>
                                            : trips.map((trip) => {
                                                const deducted = trip.fees + trip.insurance + trip.otherFees;
                                                const net = trip.fare - deducted;
                                                const margin = trip.fare > 0 ? (net / trip.fare) * 100 : 0;
                                                return (
                                                    <tr key={trip.id} className="hover:bg-white/3 transition-colors group">
                                                        <td className="px-5 py-4">
                                                            <div className="flex items-center gap-2">
                                                                <span className={`w-1.5 h-1.5 rounded-full ${trip.type === 'Uber' ? 'bg-white' : 'bg-cyan-400 shadow-[0_0_8px_rgba(0,242,255,0.6)]'}`} />
                                                                <div>
                                                                    <p className="font-bold text-sm text-white">{trip.type}</p>
                                                                    <p className="text-[10px] text-gray-600 font-mono">{trip.timestamp}{trip.distance_miles ? ` · ${trip.distance_miles.toFixed(1)}mi` : ''}</p>
                                                                </div>
                                                            </div>
                                                        </td>
                                                        <td className="px-5 py-4 text-right font-mono text-gray-300">
                                                            ${trip.fare.toFixed(2)}
                                                            {trip.tip ? <span className="ml-1.5 text-[9px] font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">+${trip.tip.toFixed(2)} tip</span> : null}
                                                        </td>
                                                        <td className="px-5 py-4 text-right font-mono text-rose-400 text-xs">{deducted > 0 ? `-$${deducted.toFixed(2)}` : '—'}</td>
                                                        <td className="px-5 py-4 text-right">
                                                            <span className="text-sm font-black text-cyan-400" style={{ textShadow: '0 0 10px rgba(0,242,255,0.4)' }}>${net.toFixed(2)}</span>
                                                        </td>
                                                        <td className="px-5 py-4 text-right">
                                                            <span className={`text-xs font-mono px-2 py-0.5 rounded ${margin >= 80 ? 'bg-emerald-500/10 text-emerald-400' : margin >= 60 ? 'bg-amber-500/10 text-amber-400' : 'bg-rose-500/10 text-rose-400'}`}>
                                                                {margin.toFixed(0)}%
                                                            </span>
                                                        </td>
                                                        <td className="px-5 py-4 text-right">
                                                            <button onClick={() => deleteTrip(trip.id)}
                                                                className="text-gray-700 hover:text-rose-400 transition-all opacity-0 group-hover:opacity-100">
                                                                <Trash2 className="w-3.5 h-3.5" />
                                                            </button>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                    </tbody>
                                </table>
                            </div>
                            {trips.length > 0 && (
                                <div className="px-5 py-4 border-t border-white/8 flex justify-between items-center">
                                    <span className="text-[10px] text-gray-600 font-mono uppercase tracking-widest">Session Total</span>
                                    <div className="flex gap-6">
                                        <div className="text-right">
                                            <p className="text-[10px] text-gray-600 font-mono">GROSS</p>
                                            <p className="text-sm font-bold text-white">${stats.gross.toFixed(2)}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-[10px] text-gray-600 font-mono">FEES</p>
                                            <p className="text-sm font-bold text-rose-400">-${stats.fees.toFixed(2)}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-[10px] text-gray-600 font-mono">NET</p>
                                            <p className="text-sm font-black text-cyan-400" style={{ textShadow: '0 0 10px rgba(0,242,255,0.4)' }}>${stats.net.toFixed(2)}</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Expense Lists */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                            <ExpenseList title="Food Expenses" data={expenses.fastfood}
                                icon={<Utensils className="w-4 h-4 text-rose-400" />}
                                onDelete={(id) => deleteExpense('fastfood', id)} accentColor="text-rose-400" />
                            <ExpenseList title="Charging Log" data={expenses.charging}
                                icon={<Zap className="w-4 h-4 text-amber-400" />}
                                onDelete={(id) => deleteExpense('charging', id)} accentColor="text-amber-400" />
                        </div>
                    </div>
                </div>

                {/* ── Tessie Drives Panel (full width) ── */}
                <TessieDrivesPanel onImport={handleImportDrive} />

                {/* Footer */}
                <div className="text-center pt-2 pb-6">
                    <p className="text-[10px] font-mono text-gray-700 tracking-[0.3em] uppercase">
                        Powered by SummitOS · COS Tesla LLC
                    </p>
                </div>
            </div>
        </div>
    );
};

export default DriverDashboard;
