"use client";

import { useState } from "react";
import { Plane, Search, ArrowRight, Clock, AlertCircle } from "lucide-react";

export default function FlightTracker() {
    const [flightNum, setFlightNum] = useState("");
    const [flightData, setFlightData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const checkFlight = async () => {
        if (!flightNum) return;
        setLoading(true);
        setError("");
        setFlightData(null);

        try {
            const res = await fetch("/api/flight", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ flightNumber: flightNum }),
            });
            const data = await res.json();

            if (res.ok && data.success) {
                setFlightData(data.data);
            } else {
                setError(data.error || "Flight not found.");
            }
        } catch (err) {
            setError("Failed to track flight.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel p-6 w-full h-full border-t border-[var(--color-primary)]/30">
            <h3 className="text-sm font-bold uppercase tracking-widest mb-4 text-gray-400 flex items-center gap-2">
                <Plane size={16} className="text-[var(--color-primary)]" />
                Flight Status
            </h3>

            <div className="flex gap-2 mb-6">
                <input
                    type="text"
                    placeholder="e.g. UA123"
                    value={flightNum}
                    onChange={(e) => setFlightNum(e.target.value.toUpperCase())}
                    onKeyDown={(e) => e.key === 'Enter' && checkFlight()}
                    className="bg-black/40 border border-white/10 rounded px-3 py-2 text-sm flex-1 focus:border-[var(--color-primary)] outline-none text-white transition-colors"
                />
                <button
                    onClick={checkFlight}
                    disabled={loading}
                    className="bg-[var(--color-primary)] text-black p-2 rounded hover:opacity-90 transition-opacity"
                >
                    <Search size={18} />
                </button>
            </div>

            {loading && <p className="text-xs text-gray-500 animate-pulse">Communicating with control tower...</p>}
            {error && <p className="text-xs text-red-400 flex items-center gap-1"><AlertCircle size={12} />{error}</p>}

            {flightData && (
                <div className="animate-in fade-in slide-in-from-bottom-2 space-y-4">
                    <div className="flex justify-between items-center text-sm">
                        <div className="text-center">
                            <span className="block font-bold text-2xl text-white">{flightData.departure.iata}</span>
                            <span className="text-xs text-gray-500">Origin</span>
                        </div>
                        <ArrowRight className="text-gray-600" size={20} />
                        <div className="text-center">
                            <span className="block font-bold text-2xl text-[var(--color-primary)]">{flightData.arrival.iata}</span>
                            <span className="text-xs text-gray-500">Destination</span>
                        </div>
                    </div>

                    <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                        <div className="flex justify-between items-center mb-2">
                            <span className="text-xs text-gray-400">Status</span>
                            <span className={`text-xs font-bold px-2 py-0.5 rounded ${flightData.flight_status === 'active' ? 'bg-green-500/20 text-green-400' :
                                flightData.flight_status === 'scheduled' ? 'bg-blue-500/20 text-blue-400' :
                                    'bg-gray-500/20 text-gray-400'
                                }`}>
                                {flightData.flight_status.toUpperCase()}
                            </span>
                        </div>

                        <div className="flex justify-between items-center text-xs">
                            <div className="flex items-center gap-1 text-gray-300">
                                <Clock size={12} />
                                <span>ETA</span>
                            </div>
                            <span className="font-mono text-[var(--color-primary)]">
                                {new Date(flightData.arrival.estimated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                        </div>
                    </div>

                    <div className="text-[10px] text-center text-gray-600">
                        {flightData.airline.name} • {flightData.flight.iata}
                    </div>
                </div>
            )}

            {!flightData && !loading && !error && (
                <div className="text-center py-4 opacity-50">
                    <p className="text-xs text-gray-500">Enter flight number to track arrival.</p>
                </div>
            )}
        </div>
    );
}
