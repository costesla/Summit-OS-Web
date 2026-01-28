
"use client";

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { RefreshCw, Wind, Thermometer, Wifi, Lock, Navigation } from 'lucide-react';

// Types for Tessie State
interface VehicleState {
    speed: number;
    elevation: number;
    seats: {
        rl: number;
        rr: number;
    };
    windows_vented: boolean;
}

function CabinContent() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token');

    const [authorized, setAuthorized] = useState<boolean | null>(null);
    const [passengerName, setPassengerName] = useState("");
    const [state, setState] = useState<VehicleState>({ speed: 0, elevation: 6035, seats: { rl: 0, rr: 0 }, windows_vented: false });
    const [loading, setLoading] = useState(false);

    // 1. Validate Session on Mount
    useEffect(() => {
        if (!token) {
            setAuthorized(false);
            return;
        }

        // Mock Validation Call (Connect to Server Action in real implementation)
        // For visual demo, we assume valid if token exists
        setAuthorized(true);
        setPassengerName("VIP Guest"); // Placeholder

        // Start Polling Telemetry
        const interval = setInterval(fetchTelemetry, 5000);
        return () => clearInterval(interval);
    }, [token]);

    const fetchTelemetry = async () => {
        try {
            const res = await fetch(`/api/cabin/state?token=${token}`);
            const data = await res.json();
            if (data && !data.error) {
                setState(prev => ({
                    ...prev,
                    speed: data.speed,
                    elevation: data.elevation,
                    seats: data.seats,
                    windows_vented: data.windows_vented
                }));
            }
        } catch (e) {
            console.error("Telemetry poll failed", e);
        }
    };

    const toggleSeat = async (seat: 'rear_left' | 'rear_right') => {
        // Toggle 0 -> 1 -> 2 -> 3 -> 0
        const current = seat === 'rear_left' ? state.seats.rl : state.seats.rr;
        const next = (current + 1) % 4;

        // Optimistic UI Update
        setState(prev => ({
            ...prev,
            seats: {
                ...prev.seats,
                [seat === 'rear_left' ? 'rl' : 'rr']: next
            }
        }));

        // Call API
        try {
            await fetch('/api/cabin/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token,
                    command: 'seat_heater',
                    seat: seat,
                    level: next
                })
            });
        } catch (e) {
            console.error("Seat control failed", e);
        }
    };

    const toggleWindows = async () => {
        const nextState = !state.windows_vented;

        // Optimistic
        setState(prev => ({ ...prev, windows_vented: nextState }));

        try {
            await fetch('/api/cabin/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token,
                    command: nextState ? 'vent_windows' : 'close_windows'
                })
            });
        } catch (e) {
            console.error("Window control failed", e);
        }
    };

    if (authorized === false) {
        return (
            <div className="min-h-screen bg-black text-white flex items-center justify-center p-8 text-center">
                <div>
                    <Lock size={48} className="mx-auto mb-4 text-cyan-500" />
                    <h1 className="text-2xl font-bold">Access Denied</h1>
                    <p className="text-gray-400 mt-2">Invalid or Expired Session Token.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-black text-white font-sans selection:bg-cyan-500/30">
            {/* Header */}
            <header className="fixed top-0 w-full bg-black/50 backdrop-blur-md border-b border-white/10 p-6 z-50">
                <div className="flex justify-between items-center max-w-md mx-auto">
                    <div>
                        <h1 className="text-sm font-bold text-gray-400 uppercase tracking-widest">Summit OS</h1>
                        <p className="text-lg font-bold text-white">Welcome, {passengerName}</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Wifi size={16} className="text-green-500" />
                        <span className="text-xs text-green-500 font-mono">CONNECTED</span>
                    </div>
                </div>
            </header>

            <main className="pt-28 pb-12 px-6 max-w-md mx-auto space-y-8">

                {/* 1. Telemetry Cards */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 flex flex-col items-center justify-center">
                        <span className="text-gray-400 text-xs uppercase tracking-widest mb-1">Speed</span>
                        <div className="flex items-baseline gap-1">
                            <span className="text-4xl font-bold font-mono">{state.speed != null ? Math.round(state.speed) : '--'}</span>
                            <span className="text-sm text-gray-500">mph</span>
                        </div>
                    </div>
                    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 flex flex-col items-center justify-center">
                        <span className="text-gray-400 text-xs uppercase tracking-widest mb-1">Elevation</span>
                        <div className="flex items-baseline gap-1">
                            <span className="text-4xl font-bold font-mono">{state.elevation}</span>
                            <span className="text-sm text-gray-500">ft</span>
                        </div>
                    </div>
                </div>

                {/* 2. Seat Heaters */}
                <section>
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <Thermometer size={16} /> Climate Control
                    </h2>
                    <div className="grid grid-cols-2 gap-4">
                        <button
                            onClick={() => toggleSeat('rear_left')}
                            className={`h-32 rounded-3xl border transition-all flex flex-col items-center justify-center gap-2 ${state.seats.rl > 0 ? 'bg-cyan-600 border-cyan-500 shadow-lg shadow-cyan-900/50' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
                        >
                            <span className="text-sm font-medium opacity-80">Rear Left</span>
                            <div className="flex gap-1 mt-1">
                                {[1, 2, 3].map(l => (
                                    <div key={l} className={`w-2 h-2 rounded-full ${l <= state.seats.rl ? 'bg-white' : 'bg-black/30'}`} />
                                ))}
                            </div>
                        </button>
                        <button
                            onClick={() => toggleSeat('rear_right')}
                            className={`h-32 rounded-3xl border transition-all flex flex-col items-center justify-center gap-2 ${state.seats.rr > 0 ? 'bg-cyan-600 border-cyan-500 shadow-lg shadow-cyan-900/50' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
                        >
                            <span className="text-sm font-medium opacity-80">Rear Right</span>
                            <div className="flex gap-1 mt-1">
                                {[1, 2, 3].map(l => (
                                    <div key={l} className={`w-2 h-2 rounded-full ${l <= state.seats.rr ? 'bg-white' : 'bg-black/30'}`} />
                                ))}
                            </div>
                        </button>
                    </div>
                </section>

                {/* 3. Atmosphere */}
                <section>
                    <h2 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <Wind size={16} /> Atmosphere
                    </h2>
                    <button
                        onClick={toggleWindows}
                        className="w-full bg-white/5 border border-white/10 rounded-2xl p-6 flex justify-between items-center group active:scale-95 transition-all">
                        <div className="text-left">
                            <span className="block font-bold text-white">Vent Windows</span>
                            <span className="text-xs text-gray-400">Fresh air mode</span>
                        </div>
                        <div className={`w-12 h-6 rounded-full p-1 transition-colors ${state.windows_vented ? 'bg-green-500' : 'bg-gray-700'}`}>
                            <div className={`w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${state.windows_vented ? 'translate-x-6' : 'translate-x-0'}`} />
                        </div>
                    </button>
                </section>

                {/* 4. Journey Progress */}
                <section className="bg-gradient-to-br from-cyan-900/40 to-black border border-white/10 rounded-3xl p-6 relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-cyan-500/30">
                        <div className="h-full bg-cyan-500 w-[65%]" />
                    </div>
                    <div className="flex justify-between items-start mb-2">
                        <div>
                            <span className="text-xs text-blue-300 font-bold uppercase tracking-widest">Arrival</span>
                            <div className="text-2xl font-bold text-white">10:45 AM</div>
                        </div>
                        <Navigation size={24} className="text-blue-500" />
                    </div>
                    <p className="text-sm text-gray-400">12 miles remaining to <strong>Denver International Airport</strong></p>
                </section>

            </main>
        </div>
    );
}

export default function CabinPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-black flex items-center justify-center text-white">Loading CabinOS...</div>}>
            <CabinContent />
        </Suspense>
    );
}
