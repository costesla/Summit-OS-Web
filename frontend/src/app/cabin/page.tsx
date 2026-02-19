
"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
    Wind,
    Thermometer,
    Wifi,
    WifiOff,
    Lock,
    Gauge,
    Mountain,
    BatteryCharging,
    Battery,
    Snowflake,
    Flame,
    ChevronUp,
    ChevronDown,
    Power,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────
interface CabinState {
    speed: number;
    elevation: number;
    inside_temp_f: number | null;
    outside_temp_f: number | null;
    climate_on: boolean;
    target_temp_f: number;
    seats: { rl: number; rr: number; rc: number };
    windows_vented: boolean;
    battery_level: number | null;
    battery_range_mi: number | null;
    charging_state: string | null;
}

const API_BASE = "";

const INITIAL_STATE: CabinState = {
    speed: 0,
    elevation: 0,
    inside_temp_f: null,
    outside_temp_f: null,
    climate_on: false,
    target_temp_f: 72,
    seats: { rl: 0, rr: 0, rc: 0 },
    windows_vented: false,
    battery_level: null,
    battery_range_mi: null,
    charging_state: null,
};

// ─── Heat level helper ───────────────────────────────────────────────
const HEAT_LABELS = ["Off", "Low", "Med", "High"];
const HEAT_COLORS = [
    "from-white/5 to-white/5 border-white/10",
    "from-amber-900/40 to-amber-800/20 border-amber-700/40",
    "from-orange-800/50 to-orange-700/25 border-orange-600/50",
    "from-red-700/50 to-orange-600/30 border-red-500/60",
];

// ─── Component ───────────────────────────────────────────────────────
function CabinContent() {
    const searchParams = useSearchParams();
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const router = require("next/navigation").useRouter();
    const token = searchParams.get("token");

    const [authorized, setAuthorized] = useState<boolean | null>(null);
    const [manualToken, setManualToken] = useState("");
    const [state, setState] = useState<CabinState>(INITIAL_STATE);
    const [connected, setConnected] = useState(false);
    const [sending, setSending] = useState<string | null>(null);

    const handleLogin = (e: React.FormEvent) => {
        e.preventDefault();
        if (manualToken.trim()) {
            router.push(`/cabin?token=${manualToken.trim()}`);
        }
    };

    // ── Fetch State ──────────────────────────────────────────────────
    const fetchState = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(`${API_BASE}/api/cabin/state?token=${token}`);
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            if (data && !data.error) {
                setState((prev) => ({ ...prev, ...data }));
                setConnected(true);
            }
        } catch {
            setConnected(false);
        }
    }, [token]);

    // ── Auth + Polling ───────────────────────────────────────────────
    useEffect(() => {
        if (!token) {
            setAuthorized(false);
            return;
        }
        setAuthorized(true);
        fetchState();
        const interval = setInterval(fetchState, 6000);
        return () => clearInterval(interval);
    }, [token, fetchState]);

    // ── Send Command ─────────────────────────────────────────────────
    const sendCommand = async (payload: Record<string, unknown>) => {
        setSending(payload.command as string);
        try {
            await fetch(`${API_BASE}/api/cabin/command`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, ...payload }),
            });
        } catch (e) {
            console.error("Command failed", e);
        } finally {
            setTimeout(() => setSending(null), 600);
        }
    };

    // ── Seat Toggle ──────────────────────────────────────────────────
    const toggleSeat = (seat: "rear_left" | "rear_right" | "rear_center") => {
        const key = seat === "rear_left" ? "rl" : seat === "rear_right" ? "rr" : "rc";
        const next = ((state.seats[key] || 0) + 1) % 4;
        setState((p) => ({ ...p, seats: { ...p.seats, [key]: next } }));
        sendCommand({ command: "seat_heater", seat, level: next });
    };

    // ── Window Toggle ────────────────────────────────────────────────
    const toggleWindows = () => {
        const next = !state.windows_vented;
        setState((p) => ({ ...p, windows_vented: next }));
        sendCommand({ command: next ? "vent_windows" : "close_windows" });
    };

    // ── Climate Toggle ───────────────────────────────────────────────
    const toggleClimate = () => {
        const next = !state.climate_on;
        setState((p) => ({ ...p, climate_on: next }));
        sendCommand({ command: next ? "start_climate" : "stop_climate" });
    };

    // ── Temp Adjust ──────────────────────────────────────────────────
    const adjustTemp = (delta: number) => {
        const next = Math.max(60, Math.min(85, state.target_temp_f + delta));
        setState((p) => ({ ...p, target_temp_f: next }));
        sendCommand({ command: "set_temp", temp_f: next });
    };

    // ── Unauthorized ─────────────────────────────────────────────────
    // ─── Enter Key Screen (Unauthorized) ─────────────────────────────
    if (authorized === false) {
        return (
            <div className="min-h-screen bg-black text-white flex items-center justify-center p-6">
                <div className="w-full max-w-sm space-y-8">
                    <div className="text-center space-y-4">
                        <div className="w-20 h-20 mx-auto rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center shadow-[0_0_30px_rgba(6,182,212,0.1)]">
                            <Lock size={32} className="text-cyan-400" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold tracking-tight">Cabin Console</h1>
                            <p className="text-gray-500 text-sm mt-2">
                                Enter your 6-digit access code to connect.
                            </p>
                        </div>
                    </div>

                    <form onSubmit={handleLogin} className="space-y-4">
                        <div className="space-y-2">
                            <input
                                type="text"
                                inputMode="numeric"
                                pattern="[0-9]*"
                                maxLength={6}
                                value={manualToken}
                                onChange={(e) => setManualToken(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                placeholder="000000"
                                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-center text-white placeholder:text-gray-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all font-mono text-2xl tracking-[0.5em]"
                                autoFocus
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={!manualToken}
                            className="w-full bg-cyan-500 hover:bg-cyan-400 text-black font-bold py-4 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            <Power size={18} />
                            Connect to Vehicle
                        </button>
                    </form>

                    <div className="text-center">
                        <p className="text-[10px] text-gray-700 uppercase tracking-widest">
                            Authorized Passengers Only
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    // ── Loading ──────────────────────────────────────────────────────
    if (authorized === null) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    // ── Battery % Bar ────────────────────────────────────────────────
    const batteryPct = state.battery_level ?? 0;
    const batteryColor =
        batteryPct > 50 ? "bg-green-500" : batteryPct > 20 ? "bg-yellow-500" : "bg-red-500";
    const isCharging = state.charging_state === "Charging";

    return (
        <div className="min-h-screen bg-black text-white font-sans selection:bg-cyan-500/30">
            {/* ─── Header ─────────────────────────────────────────────── */}
            <header className="fixed top-0 w-full bg-black/60 backdrop-blur-xl border-b border-white/[.06] z-50">
                <div className="flex justify-between items-center max-w-md mx-auto px-5 py-4">
                    <div>
                        <h1 className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.3em]">
                            Summit OS
                        </h1>
                        <p className="text-base font-semibold text-white mt-0.5">Cabin Console</p>
                    </div>
                    <div className="flex items-center gap-2">
                        {connected ? (
                            <>
                                <Wifi size={14} className="text-emerald-400" />
                                <span className="text-[10px] text-emerald-400 font-mono tracking-wider">LIVE</span>
                            </>
                        ) : (
                            <>
                                <WifiOff size={14} className="text-red-400" />
                                <span className="text-[10px] text-red-400 font-mono tracking-wider">OFFLINE</span>
                            </>
                        )}
                    </div>
                </div>
            </header>

            <main className="pt-24 pb-16 px-5 max-w-md mx-auto space-y-6">
                {/* ─── Telemetry Cards ────────────────────────────────────── */}
                <div className="grid grid-cols-3 gap-3">
                    <TelemetryCard
                        icon={<Gauge size={16} className="text-cyan-400" />}
                        label="Speed"
                        value={state.speed != null ? Math.round(state.speed) : "--"}
                        unit="mph"
                    />
                    <TelemetryCard
                        icon={<Mountain size={16} className="text-blue-400" />}
                        label="Elevation"
                        value={state.elevation ? state.elevation.toLocaleString() : "--"}
                        unit="ft"
                    />
                    <TelemetryCard
                        icon={<Thermometer size={16} className="text-orange-400" />}
                        label="Outside"
                        value={state.outside_temp_f != null ? `${state.outside_temp_f}°` : "--"}
                        unit=""
                    />
                </div>

                {/* ─── Climate Control ────────────────────────────────────── */}
                <section className="rounded-3xl border border-white/[.06] bg-gradient-to-b from-white/[.03] to-transparent p-5 space-y-5">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-[0.2em] flex items-center gap-2">
                            <Thermometer size={14} /> Climate
                        </h2>
                        <button
                            onClick={toggleClimate}
                            disabled={sending === "start_climate" || sending === "stop_climate"}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-wider transition-all ${state.climate_on
                                ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                                : "bg-white/5 text-gray-500 border border-white/10 hover:bg-white/10"
                                }`}
                        >
                            <Power size={12} />
                            {state.climate_on ? "On" : "Off"}
                        </button>
                    </div>

                    {/* Temperature Dial */}
                    <div className="flex items-center justify-center gap-6">
                        <button
                            onClick={() => adjustTemp(-1)}
                            className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center hover:bg-blue-500/10 hover:border-blue-500/30 transition-all active:scale-90"
                        >
                            <ChevronDown size={20} className="text-blue-400" />
                        </button>

                        <div className="text-center">
                            <div className="text-5xl font-bold font-mono tabular-nums tracking-tight">
                                {state.target_temp_f}
                                <span className="text-lg text-gray-600 font-normal">°F</span>
                            </div>
                            {state.inside_temp_f != null && (
                                <p className="text-[11px] text-gray-500 mt-1">
                                    Cabin: {state.inside_temp_f}°F
                                </p>
                            )}
                        </div>

                        <button
                            onClick={() => adjustTemp(1)}
                            className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center hover:bg-red-500/10 hover:border-red-500/30 transition-all active:scale-90"
                        >
                            <ChevronUp size={20} className="text-red-400" />
                        </button>
                    </div>
                </section>

                {/* ─── Seat Heaters ───────────────────────────────────────── */}
                <section className="space-y-3">
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Flame size={14} /> Seat Heaters
                    </h2>
                    <div className="grid grid-cols-3 gap-3">
                        <SeatButton label="Rear Left" level={state.seats.rl} onClick={() => toggleSeat("rear_left")} />
                        <SeatButton label="Center" level={state.seats.rc} onClick={() => toggleSeat("rear_center")} />
                        <SeatButton label="Rear Right" level={state.seats.rr} onClick={() => toggleSeat("rear_right")} />
                    </div>
                </section>

                {/* ─── Atmosphere ─────────────────────────────────────────── */}
                <section className="space-y-3">
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Wind size={14} /> Atmosphere
                    </h2>
                    <button
                        onClick={toggleWindows}
                        className="w-full rounded-2xl border border-white/[.06] bg-white/[.02] p-4 flex justify-between items-center hover:bg-white/[.04] transition-all active:scale-[0.98]"
                    >
                        <div className="text-left">
                            <span className="block text-sm font-semibold text-white">
                                {state.windows_vented ? "Windows Vented" : "Windows Closed"}
                            </span>
                            <span className="text-[11px] text-gray-500">
                                {state.windows_vented ? "Tap to close" : "Tap for fresh air"}
                            </span>
                        </div>
                        <div
                            className={`w-11 h-6 rounded-full p-0.5 transition-colors duration-300 ${state.windows_vented ? "bg-cyan-500" : "bg-gray-700"
                                }`}
                        >
                            <div
                                className={`w-5 h-5 rounded-full bg-white shadow-md transition-transform duration-300 ${state.windows_vented ? "translate-x-5" : "translate-x-0"
                                    }`}
                            />
                        </div>
                    </button>
                </section>

                {/* ─── Trunk Access ───────────────────────────────────────── */}
                <section className="space-y-3">
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Lock size={14} /> Access
                    </h2>
                    <button
                        onClick={() => sendCommand({ command: "open_trunk" })}
                        disabled={sending === "open_trunk"}
                        className="w-full h-16 rounded-2xl border border-white/[.06] bg-white/[.03] hover:bg-white/[.06] active:scale-95 transition-all flex flex-col items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <span className="text-sm font-semibold text-white">Open Trunk</span>
                        <span className="text-[10px] text-gray-500 uppercase tracking-wider">Tap to toggle</span>
                    </button>
                </section>

                {/* ─── Battery ────────────────────────────────────────────── */}
                {state.battery_level != null && (
                    <section className="rounded-2xl border border-white/[.06] bg-white/[.02] p-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <h2 className="text-xs font-bold text-gray-500 uppercase tracking-[0.2em] flex items-center gap-2">
                                {isCharging ? (
                                    <BatteryCharging size={14} className="text-green-400" />
                                ) : (
                                    <Battery size={14} />
                                )}
                                Battery
                            </h2>
                            <span className="text-sm font-bold font-mono">
                                {batteryPct}%
                                {state.battery_range_mi != null && (
                                    <span className="text-gray-500 font-normal ml-1.5">
                                        · {Math.round(state.battery_range_mi)} mi
                                    </span>
                                )}
                            </span>
                        </div>
                        <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-700 ease-out ${batteryColor}`}
                                style={{ width: `${batteryPct}%` }}
                            />
                        </div>
                        {isCharging && (
                            <p className="text-[11px] text-green-400 font-mono flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                                Charging in progress
                            </p>
                        )}
                    </section>
                )}

                {/* ─── Footer ─────────────────────────────────────────────── */}
                <div className="pt-4 text-center">
                    {/* ─── Footer ─────────────────────────────────────────────── */}
                    <div className="pt-4 text-center">
                        {/* Footer removed per request */}
                    </div>
                </div>
            </main>
        </div>
    );
}

// ─── Sub-components ──────────────────────────────────────────────────

function TelemetryCard({
    icon,
    label,
    value,
    unit,
}: {
    icon: React.ReactNode;
    label: string;
    value: string | number;
    unit: string;
}) {
    return (
        <div className="rounded-2xl border border-white/[.06] bg-white/[.02] p-3 flex flex-col items-center justify-center text-center min-h-[88px]">
            <div className="mb-1">{icon}</div>
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</span>
            <div className="flex items-baseline gap-0.5 mt-0.5">
                <span className="text-xl font-bold font-mono tabular-nums">{value}</span>
                {unit && <span className="text-[10px] text-gray-600">{unit}</span>}
            </div>
        </div>
    );
}

function SeatButton({
    label,
    level,
    onClick,
}: {
    label: string;
    level: number;
    onClick: () => void;
}) {
    return (
        <button
            onClick={onClick}
            className={`relative h-28 rounded-2xl border bg-gradient-to-b transition-all active:scale-95 flex flex-col items-center justify-center gap-2 ${HEAT_COLORS[level]}`}
        >
            {level > 0 && (
                <Flame
                    size={18}
                    className={`transition-all ${level === 1 ? "text-amber-400/60" : level === 2 ? "text-orange-400" : "text-red-400"
                        }`}
                />
            )}
            {level === 0 && <Snowflake size={18} className="text-gray-600" />}
            <span className="text-[11px] font-medium text-gray-300">{label}</span>
            <div className="flex gap-1">
                {[1, 2, 3].map((l) => (
                    <div
                        key={l}
                        className={`w-1.5 h-1.5 rounded-full transition-colors ${l <= level ? "bg-white" : "bg-white/10"
                            }`}
                    />
                ))}
            </div>
            <span className="text-[9px] text-gray-500 uppercase tracking-wider">
                {HEAT_LABELS[level]}
            </span>
        </button>
    );
}

// ─── Page Export with Suspense ────────────────────────────────────────
export default function CabinPage() {
    return (
        <Suspense
            fallback={
                <div className="min-h-screen bg-black flex items-center justify-center">
                    <div className="text-center space-y-3">
                        <div className="w-8 h-8 mx-auto border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
                        <p className="text-xs text-gray-500 font-mono tracking-wider">INITIALIZING CABIN...</p>
                    </div>
                </div>
            }
        >
            <CabinContent />
        </Suspense>
    );
}
