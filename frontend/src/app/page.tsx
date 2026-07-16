"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { BatteryCharging, Battery, Gauge, MoonStar, CalendarCheck } from "lucide-react";
import type { LatLng } from "@/components/HomeMap";

/*
 * Home — the live map.
 *
 * Two operational states, decided ENTIRELY by the backend privacy gate
 * (services/trip_window.py -> get_public_state):
 *
 *   privacy: true   -> Driver offline. Regional overview, zero coordinates.
 *   privacy absent  -> A trip is running. Live map + telemetry.
 *
 * Do not add a client-side "guess" at the state. When a trip IS active the
 * API omits `privacy` and returns coordinates, so treating "missing" as
 * private would break live tracking — and treating it as public is exactly
 * what the backend gate exists to prevent. Trust the payload; the gate is
 * the control.
 */

const HomeMap = dynamic(() => import("@/components/HomeMap"), {
    ssr: false,
    loading: () => <div className="h-full w-full bg-sos-dark" />,
});

const API = "https://summitos-api.azurewebsites.net/api";
const LOCATION_POLL_MS = 20_000;
const CHARGE_POLL_MS = 60_000;

/** Shape returned by get_public_state (backend/services/tessie.py). */
interface PublicState {
    privacy?: boolean;
    status?: string;
    lat?: number;
    long?: number;
    speed?: number;
    heading?: number;
    ignition?: boolean;
    updatedAt?: string;
}

interface ChargeState {
    soc: number | null;
    isCharging: boolean;
    rangeMi: number | null;
    asleep: boolean;
}

export default function Home() {
    const [state, setState] = useState<PublicState | null>(null);
    const [charge, setCharge] = useState<ChargeState | null>(null);
    const [reachable, setReachable] = useState(true);
    const isLive = useRef(false);

    // ── Location poll — the source of truth for which state we render ──
    useEffect(() => {
        let cancelled = false;
        const fetchState = async () => {
            try {
                const res = await fetch(`${API}/vehicle-location`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data: PublicState = await res.json();
                if (cancelled) return;
                setState(data);
                isLive.current = data?.privacy !== true && typeof data?.lat === "number";
                setReachable(true);
            } catch {
                // Backend unreachable: show the offline state. Never fall back
                // to a stale/last-known position — that would leak a location
                // the gate may since have closed.
                if (!cancelled) {
                    setReachable(false);
                    setState({ privacy: true, status: "Driver offline" });
                    isLive.current = false;
                }
            }
        };
        fetchState();
        const iv = setInterval(fetchState, LOCATION_POLL_MS);
        return () => { cancelled = true; clearInterval(iv); };
    }, []);

    // ── Charge poll — only while a trip is live (no need otherwise) ──
    useEffect(() => {
        let cancelled = false;
        const fetchCharge = async () => {
            if (!isLive.current) return;
            try {
                const res = await fetch(`${API}/copilot/charging/live`);
                if (!res.ok) return;
                const j = await res.json();
                if (cancelled) return;
                setCharge({
                    soc: j.current_soc ?? null,
                    isCharging: !!j.is_charging,
                    rangeMi: j.battery_range_mi ?? null,
                    asleep: !!j.vehicle_asleep,
                });
            } catch {
                /* telemetry is a nicety — never let it break the map */
            }
        };
        const first = setTimeout(fetchCharge, 1_500);
        const iv = setInterval(fetchCharge, CHARGE_POLL_MS);
        return () => { cancelled = true; clearTimeout(first); clearInterval(iv); };
    }, []);

    const priv = state?.privacy === true || state === null;
    const position: LatLng | null =
        !priv && typeof state?.lat === "number" && typeof state?.long === "number"
            ? { lat: state.lat, lng: state.long }
            : null;
    const live = !!position;

    return (
        <main className="relative h-[100dvh] w-full overflow-hidden bg-sos-dark">
            {/* Map fills the viewport beside/below the AppShell nav */}
            <div className="sos-map absolute inset-0">
                <HomeMap mode={live ? "live" : "offline"} position={position} heading={state?.heading} />
            </div>

            {/* Subtle vignette so overlay cards stay legible over the map */}
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/40"
            />

            {live ? (
                /* ── State B: active trip — telemetry, thumb-reachable ── */
                <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center p-4 sm:justify-end sm:p-6">
                    <div
                        className="sos-touch pointer-events-auto w-full max-w-sm rounded-2xl border border-sos-border bg-black/75 p-5 backdrop-blur-xl sm:max-w-xs"
                        style={{ marginBottom: "env(safe-area-inset-bottom, 0px)" }}
                    >
                        <div className="mb-4 flex items-center justify-between gap-4">
                            <div>
                                <p className="text-sm font-bold text-sos-main">Model Y</p>
                            </div>
                            <span className="flex items-center gap-1.5 text-[0.65rem] font-bold uppercase tracking-wider text-sos-accent">
                                <span className="relative flex h-2 w-2">
                                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400/70" />
                                    <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400" />
                                </span>
                                Live
                            </span>
                        </div>

                        <div className="grid grid-cols-3 gap-3">
                            <Metric
                                icon={<Gauge size={15} className="text-sos-accent" />}
                                label="Speed"
                                value={`${Math.round(state?.speed ?? 0)}`}
                                unit="mph"
                            />
                            <Metric
                                icon={
                                    charge?.isCharging ? (
                                        <BatteryCharging size={15} className="text-green-400" />
                                    ) : (
                                        <Battery size={15} className="text-sos-accent" />
                                    )
                                }
                                label="Charge"
                                value={charge?.soc != null ? `${Math.round(charge.soc)}` : "—"}
                                unit="%"
                            />
                            <Metric
                                icon={
                                    charge?.asleep ? (
                                        <MoonStar size={15} className="text-slate-400" />
                                    ) : charge?.isCharging ? (
                                        <BatteryCharging size={15} className="text-green-400" />
                                    ) : (
                                        <Gauge size={15} className="text-sos-accent" />
                                    )
                                }
                                label="Status"
                                value={charge?.isCharging ? "Charging" : (state?.speed ?? 0) > 0 ? "Driving" : "Stopped"}
                            />
                        </div>
                    </div>
                </div>
            ) : (
                /* ── State A: privacy active — no coordinates rendered ── */
                <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center p-6">
                    <div className="sos-touch pointer-events-auto w-full max-w-md rounded-3xl border border-sos-border bg-black/70 p-8 text-center backdrop-blur-xl">
                        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                            <MoonStar size={26} className="text-sos-dim" aria-hidden="true" />
                        </div>
                        <h1 className="text-xl font-bold tracking-tight text-sos-main">Driver Offline</h1>
                        <p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-sos-dim">
                            Next-trip dispatch tracking will appear here.
                        </p>
                        {!reachable && (
                            <p className="mt-3 font-mono text-[0.6rem] uppercase tracking-widest text-slate-600">
                                Reconnecting…
                            </p>
                        )}
                        <Link
                            href="/book/"
                            className="sos-touch mt-7 inline-flex items-center gap-2 rounded-xl bg-sos-accent px-7 py-3 text-sm font-bold text-black transition-colors hover:bg-cyan-300"
                        >
                            <CalendarCheck size={16} aria-hidden="true" />
                            Book a Ride
                        </Link>
                    </div>
                </div>
            )}
        </main>
    );
}

function Metric({
    icon,
    label,
    value,
    unit,
}: {
    icon: React.ReactNode;
    label: string;
    value: string;
    unit?: string;
}) {
    return (
        <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
            <div className="mb-1.5 flex items-center gap-1.5">
                {icon}
                <span className="font-mono text-[0.55rem] uppercase tracking-widest text-sos-dim">{label}</span>
            </div>
            <p className="text-base font-bold leading-none text-sos-main">
                {value}
                {unit && <span className="ml-0.5 text-[0.65rem] font-normal text-sos-dim">{unit}</span>}
            </p>
        </div>
    );
}
