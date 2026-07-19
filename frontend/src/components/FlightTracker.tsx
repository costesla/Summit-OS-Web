"use client";

import { useState } from "react";
import { Plane, Search, ArrowRight, Clock, AlertCircle, Navigation, Gauge } from "lucide-react";

const API = "https://summitos-api.azurewebsites.net/api/flight-status";

type Airport = { code?: string | null; city?: string | null };
type Live = {
    latitude?: number; longitude?: number; altitude_ft?: number;
    ground_speed_kts?: number; heading_deg?: number;
} | null;
type FlightData = {
    flight_number: string;
    airline?: string | null;
    airline_code?: string | null;
    status?: string | null;
    origin?: Airport;
    destination?: Airport;
    scheduled_arrival_mt?: string | null;
    estimated_arrival_mt?: string | null;
    delay_minutes?: number | null;
    aircraft_type?: string | null;
    progress_percent?: number | null;
    cancelled?: boolean;
    live?: Live;
    sources?: { schedule?: string | null; live?: string | null };
};

function isAirborne(d: FlightData): boolean {
    return !!d.live && typeof d.live.altitude_ft === "number" && d.live.altitude_ft > 0;
}

function badge(d: FlightData, airborne: boolean) {
    if (d.cancelled) return { label: "Cancelled", cls: "bg-red-100 text-red-700" };
    if (typeof d.delay_minutes === "number" && d.delay_minutes >= 15)
        return { label: `Delayed ${d.delay_minutes} min`, cls: "bg-amber-100 text-amber-700" };
    if (airborne) return { label: "In the air", cls: "bg-blue-100 text-blue-700" };
    const s = (d.status || "").toLowerCase();
    if (s.includes("arriv") || s.includes("landed")) return { label: d.status || "Arrived", cls: "bg-emerald-100 text-emerald-700" };
    if (s.includes("en route") || s.includes("airborne")) return { label: d.status || "En route", cls: "bg-blue-100 text-blue-700" };
    return { label: d.status || "Scheduled", cls: "bg-slate-100 text-slate-600" };
}

export default function FlightTracker() {
    const [flightNum, setFlightNum] = useState("");
    const [flightData, setFlightData] = useState<FlightData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const checkFlight = async () => {
        if (!flightNum) return;
        setLoading(true);
        setError("");
        setFlightData(null);
        try {
            const res = await fetch(API, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ flightNumber: flightNum }),
            });
            const data = await res.json();
            if (res.ok && data.success && data.found) {
                setFlightData(data.data);
            } else if (res.ok && data.success && !data.found) {
                setError("No flight found for that number right now. Double-check the flight number (e.g. UA123) and try again.");
            } else {
                setError(data.error || "Flight lookup failed. Please try again.");
            }
        } catch {
            setError("Couldn't reach the flight service. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-panel p-6 sm:p-8 w-full">
            <div className="flex items-center gap-2 mb-5">
                <Plane size={18} className="text-blue-600" />
                <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
                    Flight Status
                </h3>
            </div>

            <div className="flex gap-2 mb-2">
                <input
                    type="text"
                    placeholder="Enter a flight number, e.g. UA123"
                    value={flightNum}
                    onChange={(e) => setFlightNum(e.target.value.toUpperCase())}
                    onKeyDown={(e) => e.key === "Enter" && checkFlight()}
                    className="flex-1"
                    style={{ marginBottom: 0 }}
                />
                <button
                    onClick={checkFlight}
                    disabled={loading}
                    aria-label="Track flight"
                    className="btn-primary flex items-center justify-center !px-5 !py-0 disabled:opacity-60"
                >
                    <Search size={18} />
                </button>
            </div>

            {loading && (
                <p className="mt-4 text-sm text-[var(--color-text-muted)] animate-pulse">
                    Checking schedules and live position…
                </p>
            )}
            {error && (
                <p className="mt-4 text-sm text-red-600 flex items-start gap-1.5">
                    <AlertCircle size={16} className="mt-0.5 shrink-0" />
                    <span>{error}</span>
                </p>
            )}

            {flightData && (() => {
                const airborne = isAirborne(flightData);
                const b = badge(flightData, airborne);
                const delayed = typeof flightData.delay_minutes === "number" && flightData.delay_minutes >= 15;
                return (
                    <div className="mt-6 space-y-5">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-lg font-bold text-[var(--color-text-main)] leading-tight">
                                    {flightData.airline || flightData.airline_code || "Flight"}
                                </p>
                                <p className="text-xs text-[var(--color-text-muted)]">
                                    {flightData.flight_number}
                                    {flightData.aircraft_type ? ` · ${flightData.aircraft_type}` : ""}
                                </p>
                            </div>
                            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${b.cls}`}>
                                {b.label}
                            </span>
                        </div>

                        {/* Route */}
                        <div className="flex items-center justify-between rounded-2xl bg-white/60 border border-white/70 px-5 py-4">
                            <div className="text-center min-w-0">
                                <span className="block text-2xl font-bold text-[var(--color-text-main)]">
                                    {flightData.origin?.code || "—"}
                                </span>
                                <span className="block text-xs text-[var(--color-text-muted)] truncate max-w-[9rem]">
                                    {flightData.origin?.city || "Origin"}
                                </span>
                            </div>
                            <ArrowRight className="text-blue-500 shrink-0" size={22} />
                            <div className="text-center min-w-0">
                                <span className="block text-2xl font-bold text-blue-600">
                                    {flightData.destination?.code || "—"}
                                </span>
                                <span className="block text-xs text-[var(--color-text-muted)] truncate max-w-[9rem]">
                                    {flightData.destination?.city || "Destination"}
                                </span>
                            </div>
                        </div>

                        {/* Arrival timing */}
                        <div className="rounded-2xl bg-white/60 border border-white/70 px-5 py-4">
                            <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] mb-2">
                                <Clock size={14} /> <span>Arrival (Mountain Time)</span>
                            </div>
                            <div className="flex items-baseline gap-3">
                                <span className={`text-2xl font-bold ${delayed ? "text-amber-600" : "text-[var(--color-text-main)]"}`}>
                                    {flightData.estimated_arrival_mt || flightData.scheduled_arrival_mt || "—"}
                                </span>
                                {delayed && flightData.scheduled_arrival_mt && (
                                    <span className="text-sm text-[var(--color-text-muted)] line-through">
                                        {flightData.scheduled_arrival_mt}
                                    </span>
                                )}
                            </div>
                            {typeof flightData.delay_minutes === "number" && (
                                <p className={`mt-1 text-xs ${flightData.delay_minutes >= 15 ? "text-amber-600" : flightData.delay_minutes <= -5 ? "text-emerald-600" : "text-[var(--color-text-muted)]"}`}>
                                    {flightData.delay_minutes >= 15
                                        ? `${flightData.delay_minutes} min behind schedule`
                                        : flightData.delay_minutes <= -5
                                            ? `${Math.abs(flightData.delay_minutes)} min early`
                                            : "On time"}
                                </p>
                            )}
                        </div>

                        {/* Live telemetry (only when airborne) */}
                        {airborne && flightData.live && (
                            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl bg-blue-50/70 border border-blue-100 px-5 py-3 text-sm">
                                <span className="flex items-center gap-1.5 text-blue-700 font-medium">
                                    <span className="relative flex h-2 w-2">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-600" />
                                    </span>
                                    Live
                                </span>
                                {typeof flightData.live.altitude_ft === "number" && (
                                    <span className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
                                        <Navigation size={14} /> {flightData.live.altitude_ft.toLocaleString()} ft
                                    </span>
                                )}
                                {typeof flightData.live.ground_speed_kts === "number" && (
                                    <span className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
                                        <Gauge size={14} /> {flightData.live.ground_speed_kts} kts
                                    </span>
                                )}
                            </div>
                        )}

                        <p className="text-[10px] text-[var(--color-text-muted)] text-right">
                            {flightData.sources?.schedule ? `Schedule: ${flightData.sources.schedule}` : ""}
                            {flightData.sources?.live && airborne ? ` · Live: ${flightData.sources.live}` : ""}
                        </p>
                    </div>
                );
            })()}

            {!flightData && !loading && !error && (
                <p className="mt-4 text-sm text-[var(--color-text-muted)]">
                    Enter a flight number to see its arrival time, delay, and live position.
                </p>
            )}
        </div>
    );
}
