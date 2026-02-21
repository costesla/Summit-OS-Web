
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
    heading?: number;
    inside_temp_f: number | null;
    outside_temp_f: number | null;
    condition_text?: string;
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
    condition_text: "N/A",
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
                            COS Tesla
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

            <main className="pt-24 pb-12 px-5 max-w-md mx-auto space-y-5">
                {/* ─── Vehicle Status & Telemetry ─────────────────────────── */}
                <section className="space-y-3">
                    {/* Battery Bar */}
                    {state.battery_level != null && (
                        <div className="bg-white/[.03] rounded-xl p-3 border border-white/[.06] flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                {isCharging ? (
                                    <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                                        <BatteryCharging size={16} className="text-green-400" />
                                    </div>
                                ) : (
                                    <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center">
                                        <Battery size={16} className="text-gray-400" />
                                    </div>
                                )}
                                <div>
                                    <div className="text-sm font-bold font-mono tracking-tight flex items-baseline gap-1.5">
                                        {batteryPct}%
                                        {state.battery_range_mi != null && (
                                            <span className="text-xs text-gray-500 font-sans font-medium">
                                                {Math.round(state.battery_range_mi)} mi
                                            </span>
                                        )}
                                    </div>
                                    <div className="w-32 h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                                        <div
                                            className={`h-full rounded-full transition-all duration-700 ease-out ${batteryColor}`}
                                            style={{ width: `${batteryPct}%` }}
                                        />
                                    </div>
                                </div>
                            </div>
                            <div className="text-right space-y-0.5">
                                <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold truncate max-w-[100px]">
                                    {state.condition_text && state.condition_text !== "N/A" ? state.condition_text : "OUTSIDE"}
                                </div>
                                <div className="text-sm font-mono font-bold text-white">
                                    {state.outside_temp_f != null ? `${state.outside_temp_f}°` : "--"}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Compact Telemetry Grid */}
                    <div className="grid grid-cols-2 gap-3">
                        <div className="bg-white/[.02] border border-white/[.04] rounded-xl py-2 px-4 flex items-center justify-between">
                            <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Speed</span>
                            <span className="font-mono font-bold text-sm">{state.speed != null ? Math.round(state.speed) : "0"} <span className="text-[10px] text-gray-600 font-sans">mph</span></span>
                        </div>
                        <div className="bg-white/[.02] border border-white/[.04] rounded-xl py-2 px-4 flex items-center justify-between">
                            <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Elevation</span>
                            <span className="font-mono font-bold text-sm">{state.elevation ? state.elevation.toLocaleString() : "0"} <span className="text-[10px] text-gray-600 font-sans">ft</span></span>
                        </div>
                    </div>
                </section>

                {/* ─── Climate & Comfort ──────────────────────────────────── */}
                <section className="bg-gradient-to-b from-white/[.03] to-transparent border border-white/[.06] rounded-3xl p-1 overflow-hidden">
                    <div className="p-5 pb-2">
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center gap-2">
                                <div className={`w-2 h-2 rounded-full ${state.climate_on ? "bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.6)]" : "bg-gray-600"}`} />
                                <h2 className="text-xs font-bold text-gray-400 uppercase tracking-[0.2em]">Climate</h2>
                            </div>
                            <button
                                onClick={toggleClimate}
                                disabled={sending === "start_climate" || sending === "stop_climate"}
                                className={`h-8 px-4 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all flex items-center gap-2 ${state.climate_on
                                    ? "bg-cyan-500 text-black hover:bg-cyan-400"
                                    : "bg-white/10 text-gray-400 hover:bg-white/20"
                                    }`}
                            >
                                <Power size={12} />
                                {state.climate_on ? "ON" : "OFF"}
                            </button>
                        </div>

                        {/* Temp Control */}
                        <div className="flex items-center justify-between px-2 mb-8">
                            <button onClick={() => adjustTemp(-1)} className="w-12 h-12 rounded-full bg-white/5 border border-white/5 flex items-center justify-center text-blue-400 hover:bg-blue-500/10 active:scale-90 transition-all">
                                <ChevronDown size={24} />
                            </button>
                            <div className="text-center">
                                <div className="text-6xl font-bold font-mono tracking-tighter text-white drop-shadow-xl">{state.target_temp_f}°</div>
                                <div className="text-[11px] text-gray-500 font-medium mt-1">Cabin: {state.inside_temp_f ?? "--"}°</div>
                            </div>
                            <button onClick={() => adjustTemp(1)} className="w-12 h-12 rounded-full bg-white/5 border border-white/5 flex items-center justify-center text-red-400 hover:bg-red-500/10 active:scale-90 transition-all">
                                <ChevronUp size={24} />
                            </button>
                        </div>
                    </div>

                    {/* Integrated Seat Heaters */}
                    <div className="bg-black/20 border-t border-white/[.04] p-3 grid grid-cols-3 gap-2">
                        <SeatButton label="L" level={state.seats.rl} onClick={() => toggleSeat("rear_left")} />
                        <SeatButton label="C" level={state.seats.rc} onClick={() => toggleSeat("rear_center")} />
                        <SeatButton label="R" level={state.seats.rr} onClick={() => toggleSeat("rear_right")} />
                    </div>
                </section>

                {/* ─── Controls Grid ──────────────────────────────────────── */}
                <div className="grid grid-cols-2 gap-3">
                    {/* Windows */}
                    <button
                        onClick={toggleWindows}
                        className={`h-24 rounded-2xl border flex flex-col items-center justify-center gap-2 transition-all active:scale-95 ${state.windows_vented
                            ? "bg-cyan-500/10 border-cyan-500/30"
                            : "bg-white/[.03] border-white/[.06] hover:bg-white/[.05]"}`}
                    >
                        <Wind size={20} className={state.windows_vented ? "text-cyan-400" : "text-gray-400"} />
                        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Windows</span>
                        <div className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${state.windows_vented ? "bg-cyan-500 text-black" : "bg-white/10 text-gray-500"}`}>
                            {state.windows_vented ? "VENTED" : "CLOSED"}
                        </div>
                    </button>

                    {/* Trunk */}
                    <button
                        onClick={() => sendCommand({ command: "open_trunk" })}
                        disabled={sending === "open_trunk"}
                        className="h-24 rounded-2xl border border-white/[.06] bg-white/[.03] hover:bg-white/[.05] flex flex-col items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-50"
                    >
                        <Lock size={20} className="text-gray-400" />
                        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Trunk</span>
                        <div className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-gray-500 font-bold">
                            OPEN
                        </div>
                    </button>
                </div>

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
