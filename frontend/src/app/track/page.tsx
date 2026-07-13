"use client";

import { useEffect, useRef, useState } from "react";
import Navbar from "@/components/Navbar";
import dynamic from "next/dynamic";
import type { PosData } from "@/components/LiveMap";
import { Gauge, Compass, CloudSun, Wind, Droplets } from "lucide-react";

const LiveMap = dynamic(() => import("../../components/LiveMap"), {
    ssr: false,
    loading: () => <div className="h-screen flex items-center justify-center text-blue-400">CONNECTING TO TESLA GPS...</div>
});

/*
 * B2 Track experience: the page owns a single vehicle-location poll and feeds
 * LiveMap in controlled mode (overridePos), so the map and the status card
 * share one data source instead of polling twice.
 */

// vehicle-location returns more than LiveMap's PosData consumes
interface VehicleTelemetry extends PosData {
    ignition?: boolean;
    updatedAt?: string;
}

interface WeatherNow {
    temp_f: number;
    humidity: number;
    wind_mph: number;
    condition: string;
}

const API = "https://summitos-api.azurewebsites.net/api";
const POLL_MS = 20_000;        // matches the interval LiveMap used standalone
const WEATHER_REFRESH_MS = 10 * 60_000;
const STALE_AFTER_MIN = 10;

// No ETA: the backend exposes no trip-state source (see PWA research C4).
// State is derived from what the telemetry actually contains.
function deriveState(pos: VehicleTelemetry | null): { label: string; tone: string } {
    if (!pos) return { label: "Connecting", tone: "text-gray-400" };
    if (pos.privacy) return { label: "Docked", tone: "text-blue-400" };
    if ((pos.speed ?? 0) > 0) return { label: "En Route", tone: "text-green-400" };
    if (pos.ignition) return { label: "Idle", tone: "text-amber-400" };
    return { label: "Parked", tone: "text-gray-300" };
}

function agoLabel(updatedAt?: string): string | null {
    if (!updatedAt) return null;
    const ms = Date.now() - new Date(updatedAt).getTime();
    if (Number.isNaN(ms)) return null;
    const min = Math.round(ms / 60_000);
    if (min < 1) return "just now";
    if (min < 60) return `${min} min ago`;
    return `${Math.round(min / 60)} hr ago`;
}

export default function TrackPage() {
    const [pos, setPos] = useState<VehicleTelemetry | null>(null);
    const [offline, setOffline] = useState(false);
    const [weather, setWeather] = useState<WeatherNow | null>(null);
    const posRef = useRef<VehicleTelemetry | null>(null);
    const weatherFetchedAt = useRef(0);

    // ── Vehicle telemetry poll (single source for map + status card) ──
    useEffect(() => {
        let cancelled = false;
        const fetchLocation = async () => {
            try {
                const res = await fetch(`${API}/vehicle-location`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data: VehicleTelemetry = await res.json();
                if (!cancelled && data) {
                    setPos(data);
                    posRef.current = data;
                    setOffline(false);
                }
            } catch {
                if (!cancelled) setOffline(true);
            }
        };
        fetchLocation();
        const iv = setInterval(fetchLocation, POLL_MS);
        return () => { cancelled = true; clearInterval(iv); };
    }, []);

    // ── Weather at the vehicle position (first fix + every 10 min) ──
    useEffect(() => {
        let cancelled = false;
        const fetchWeather = async () => {
            const p = posRef.current;
            if (!p || p.lat == null || p.long == null) return;
            if (Date.now() - weatherFetchedAt.current < WEATHER_REFRESH_MS) return;
            try {
                const res = await fetch(`${API}/weather/forecast?lat=${p.lat}&lng=${p.long}`);
                if (!res.ok) return;
                const data = await res.json();
                if (!cancelled && data?.current) {
                    setWeather(data.current as WeatherNow);
                    weatherFetchedAt.current = Date.now();
                }
            } catch {
                // weather card just stays hidden — never block the tracker on it
            }
        };
        // small delay so the first position fix lands before the first attempt
        const first = setTimeout(fetchWeather, 3_000);
        const iv = setInterval(fetchWeather, 60_000); // gate inside enforces the 10-min refresh
        return () => { cancelled = true; clearTimeout(first); clearInterval(iv); };
    }, []);

    const state = deriveState(pos);
    const ago = agoLabel(pos?.updatedAt);
    const stale = pos?.updatedAt
        ? Date.now() - new Date(pos.updatedAt).getTime() > STALE_AFTER_MIN * 60_000
        : false;

    return (
        <main className="min-h-screen bg-black">
            <Navbar />
            <div className="h-screen w-full relative">
                {pos ? (
                    <LiveMap className="h-full w-full" overridePos={pos} />
                ) : (
                    <div className="h-full flex items-center justify-center text-blue-400 animate-pulse">
                        {offline ? <span className="text-red-400">Tracker Offline</span> : "CONNECTING TO TESLA GPS..."}
                    </div>
                )}

                {/* Header pill */}
                <div className="absolute top-24 left-1/2 -translate-x-1/2 bg-black/80 backdrop-blur-md px-6 py-3 rounded-full border border-white/10 z-[1000] text-center">
                    <h1 className="text-white font-bold tracking-widest text-sm mb-1 uppercase">Live Vehicle Telemetry</h1>
                    <p className="text-xs text-gray-400">Real-time GPS tracking via Tessie API</p>
                </div>

                {/* Bottom overlay cards — lifted above the app tab bar in standalone mode */}
                <div className="absolute inset-x-0 bottom-6 [@media(display-mode:standalone)]:bottom-24 z-[1000] px-4 flex flex-wrap justify-center gap-3 pointer-events-none">
                    {/* Status card */}
                    <div className="pointer-events-auto bg-black/80 backdrop-blur-md border border-white/10 rounded-2xl px-5 py-4 min-w-[240px]">
                        <div className="flex items-center justify-between gap-6 mb-2">
                            <div>
                                <p className="text-white font-bold text-sm">Thor · Tesla Model Y</p>
                                <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">COS Tesla Fleet</p>
                            </div>
                            <span className={`text-xs font-bold uppercase tracking-wider ${state.tone}`}>{state.label}</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-300">
                            <span className="flex items-center gap-1.5">
                                <Gauge size={14} className="text-blue-400" aria-hidden="true" />
                                {Math.round(pos?.speed ?? 0)} mph
                            </span>
                            <span className="flex items-center gap-1.5">
                                <Compass size={14} className="text-blue-400" aria-hidden="true" />
                                {pos?.heading ?? 0}°
                            </span>
                            {ago && (
                                <span className={`ml-auto font-mono text-[10px] ${stale ? "text-amber-400" : "text-gray-500"}`}>
                                    {stale ? "signal delayed · " : ""}{ago}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Weather card (at vehicle location) */}
                    {weather && (
                        <div className="pointer-events-auto bg-black/80 backdrop-blur-md border border-white/10 rounded-2xl px-5 py-4 min-w-[200px]">
                            <div className="flex items-center gap-2 mb-2">
                                <CloudSun size={16} className="text-yellow-400" aria-hidden="true" />
                                <span className="text-white font-bold text-sm">{Math.round(weather.temp_f)}°F</span>
                                <span className="text-xs text-gray-400">{weather.condition}</span>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-gray-300">
                                <span className="flex items-center gap-1.5">
                                    <Wind size={13} className="text-blue-400" aria-hidden="true" />
                                    {Math.round(weather.wind_mph)} mph
                                </span>
                                <span className="flex items-center gap-1.5">
                                    <Droplets size={13} className="text-blue-400" aria-hidden="true" />
                                    {weather.humidity}%
                                </span>
                                <span className="ml-auto font-mono text-[10px] text-gray-500">at vehicle</span>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </main>
    );
}
