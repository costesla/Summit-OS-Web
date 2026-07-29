"use client";

import { ArrowRight, Clock, Navigation, Gauge } from "lucide-react";

/*
 * FlightStatusPanel — the read-out for one flight.
 *
 * Extracted from FlightTracker so the cabin console can show the same
 * information without a second flight-tracking implementation. Both surfaces
 * render the SAME /api/flight-status payload; the only difference is the
 * palette, because the public page is light and the cabin console is dark.
 *
 * Two things here are load-bearing and easy to get wrong:
 *
 *   1. LIVE vs FINAL. Polling stops the moment the aircraft is down (the
 *      schedule can't change after that, and every lookup costs an AeroAPI
 *      query). So a landed flight is a FROZEN SNAPSHOT. Labelling it "Live"
 *      would be a lie that costs a passenger their trust the first time they
 *      watch a stale number not move.
 *
 *   2. Every field is optional. This renders provider data — a missing
 *      airline, a null delay, a malformed arrival string are all normal, not
 *      exceptional. Nothing here may throw on absent data, because this panel
 *      sits inside the cabin console and taking it down would take cabin
 *      access down with it.
 */

export interface FlightPanelData {
    /* Matches FlightLike in ./arrivalMode — the same payload feeds both, and
       the backend always echoes the ident it was asked for, so this is never
       null in practice. Keeping the two in step lets one fetch serve both. */
    flight_number?: string;
    airline?: string | null;
    airline_code?: string | null;
    status?: string | null;
    origin?: { code?: string | null; city?: string | null };
    destination?: { code?: string | null; city?: string | null };
    scheduled_arrival_mt?: string | null;
    estimated_arrival_mt?: string | null;
    delay_minutes?: number | null;
    aircraft_type?: string | null;
    progress_percent?: number | null;
    cancelled?: boolean;
    diverted?: boolean;
    on_ground?: boolean;
    landed_at?: string | null;
    live?: {
        altitude_ft?: number;
        ground_speed_kts?: number;
    } | null;
    sources?: { schedule?: string | null; live?: string | null };
}

export type PanelVariant = "light" | "dark";

/** Delay at or beyond this many minutes is worth colouring. Below it, a couple
 *  of minutes either way is schedule noise and shouldn't alarm anyone. */
const DELAY_THRESHOLD_MIN = 15;
/** Ahead of schedule by at least this much before we call it "early". */
const EARLY_THRESHOLD_MIN = 5;

const THEME = {
    light: {
        title: "text-[var(--color-text-main)]",
        muted: "text-[var(--color-text-muted)]",
        card: "rounded-2xl bg-white/60 border border-white/70",
        destCode: "text-blue-600",
        arrow: "text-blue-500",
        track: "bg-slate-200",
        fill: "bg-blue-500",
        liveCard: "bg-blue-50/70 border border-blue-100",
        liveText: "text-blue-700",
    },
    dark: {
        title: "text-white",
        muted: "text-gray-400",
        card: "rounded-2xl bg-white/[.03] border border-white/[.08]",
        destCode: "text-cyan-300",
        arrow: "text-cyan-400",
        track: "bg-white/10",
        fill: "bg-cyan-400",
        liveCard: "bg-cyan-500/10 border border-cyan-500/20",
        liveText: "text-cyan-300",
    },
} as const;

const BADGE = {
    light: {
        red: "bg-red-100 text-red-700",
        amber: "bg-amber-100 text-amber-700",
        blue: "bg-blue-100 text-blue-700",
        green: "bg-emerald-100 text-emerald-700",
        grey: "bg-slate-100 text-slate-600",
    },
    dark: {
        red: "bg-red-500/15 text-red-300 border border-red-500/25",
        amber: "bg-amber-500/15 text-amber-300 border border-amber-500/25",
        blue: "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25",
        green: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25",
        grey: "bg-white/10 text-gray-300 border border-white/10",
    },
} as const;

export function isAirborne(d?: FlightPanelData | null): boolean {
    return !!d?.live && typeof d.live.altitude_ft === "number" && d.live.altitude_ft > 0;
}

/** True once the aircraft is down. From here the payload never changes again,
 *  because the cabin console stops polling — see the file header. */
export function isFinal(d?: FlightPanelData | null): boolean {
    return !!d?.on_ground || !!d?.cancelled;
}

export function statusBadge(d: FlightPanelData, variant: PanelVariant) {
    const c = BADGE[variant];
    if (d.cancelled) return { label: "Cancelled", cls: c.red };
    // A diversion outranks a delay: landing somewhere else is the headline.
    if (d.diverted) return { label: "Diverted", cls: c.red };
    if (d.on_ground) {
        return {
            label: d.landed_at ? `Landed · ${d.landed_at}` : "Landed",
            cls: c.green,
        };
    }
    if (typeof d.delay_minutes === "number" && d.delay_minutes >= DELAY_THRESHOLD_MIN)
        return { label: `Delayed ${d.delay_minutes} min`, cls: c.amber };
    if (isAirborne(d)) return { label: "In the air", cls: c.blue };
    const s = (d.status || "").toLowerCase();
    if (s.includes("arriv") || s.includes("landed"))
        return { label: d.status || "Arrived", cls: c.green };
    if (s.includes("en route") || s.includes("airborne"))
        return { label: d.status || "En route", cls: c.blue };
    return { label: d.status || "Scheduled", cls: c.grey };
}

export default function FlightStatusPanel({
    flight,
    variant = "light",
    compact = false,
    className,
}: {
    flight: FlightPanelData;
    variant?: PanelVariant;
    /** Tighter spacing and smaller type, for the cabin console's narrow column. */
    compact?: boolean;
    className?: string;
}) {
    const t = THEME[variant];
    const airborne = isAirborne(flight);
    const final = isFinal(flight);
    const badge = statusBadge(flight, variant);

    const delay = typeof flight.delay_minutes === "number" ? flight.delay_minutes : null;
    const delayed = delay !== null && delay >= DELAY_THRESHOLD_MIN;
    const early = delay !== null && delay <= -EARLY_THRESHOLD_MIN;

    // Progress is only meaningful in the air. On the ground it's either 0 (not
    // departed) or 100 (landed), and both are better said by the badge.
    const progress = typeof flight.progress_percent === "number" && !final
        ? Math.max(0, Math.min(100, flight.progress_percent))
        : null;

    const arrivalLabel = final ? "Arrived (Mountain Time)" : "Arrival (Mountain Time)";
    const arrivalValue = flight.estimated_arrival_mt || flight.scheduled_arrival_mt || "—";

    return (
        <div className={`${compact ? "space-y-3" : "space-y-5"} ${className || ""}`}>
            {/* Identity + status */}
            <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                    <p className={`${compact ? "text-base" : "text-lg"} font-bold leading-tight truncate ${t.title}`}>
                        {flight.airline || flight.airline_code || "Flight"}
                    </p>
                    <p className={`text-xs truncate ${t.muted}`}>
                        {flight.flight_number || "—"}
                        {flight.aircraft_type ? ` · ${flight.aircraft_type}` : ""}
                    </p>
                </div>
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full shrink-0 ${badge.cls}`}>
                    {badge.label}
                </span>
            </div>

            {/* A diversion changes where the passenger physically is, so it gets
                its own line rather than living only in a badge. */}
            {flight.diverted && (
                <p className={`text-xs ${variant === "dark" ? "text-red-300" : "text-red-700"}`}>
                    This flight was diverted{flight.landed_at ? ` to ${flight.landed_at}` : ""}.
                    Your pickup may need to change — contact us.
                </p>
            )}

            {/* Route */}
            <div className={`flex items-center justify-between ${t.card} ${compact ? "px-4 py-3" : "px-5 py-4"}`}>
                <div className="text-center min-w-0">
                    <span className={`block ${compact ? "text-xl" : "text-2xl"} font-bold ${t.title}`}>
                        {flight.origin?.code || "—"}
                    </span>
                    <span className={`block text-xs truncate max-w-[9rem] ${t.muted}`}>
                        {flight.origin?.city || "Origin"}
                    </span>
                </div>
                <ArrowRight className={`shrink-0 ${t.arrow}`} size={compact ? 18 : 22} />
                <div className="text-center min-w-0">
                    <span className={`block ${compact ? "text-xl" : "text-2xl"} font-bold ${t.destCode}`}>
                        {flight.destination?.code || "—"}
                    </span>
                    <span className={`block text-xs truncate max-w-[9rem] ${t.muted}`}>
                        {flight.destination?.city || "Destination"}
                    </span>
                </div>
            </div>

            {/* Progress along the route — only while actually flying. */}
            {progress !== null && (
                <div>
                    <div
                        className={`h-1.5 w-full overflow-hidden rounded-full ${t.track}`}
                        role="progressbar"
                        aria-valuenow={Math.round(progress)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label="Flight progress"
                    >
                        <div className={`h-full rounded-full ${t.fill}`} style={{ width: `${progress}%` }} />
                    </div>
                    <p className={`mt-1 text-[10px] ${t.muted}`}>{Math.round(progress)}% of the way</p>
                </div>
            )}

            {/* Arrival timing. Scheduled is shown alongside estimated whenever
                the two differ, so a delay is legible without arithmetic. */}
            <div className={`${t.card} ${compact ? "px-4 py-3" : "px-5 py-4"}`}>
                <div className={`flex items-center gap-1.5 text-xs mb-2 ${t.muted}`}>
                    <Clock size={14} /> <span>{arrivalLabel}</span>
                </div>
                <div className="flex items-baseline gap-3 flex-wrap">
                    <span className={`${compact ? "text-xl" : "text-2xl"} font-bold ${delayed
                        ? (variant === "dark" ? "text-amber-300" : "text-amber-600")
                        : t.title}`}>
                        {arrivalValue}
                    </span>
                    {(delayed || early)
                        && flight.scheduled_arrival_mt
                        && flight.scheduled_arrival_mt !== flight.estimated_arrival_mt && (
                            <span className={`text-sm line-through ${t.muted}`}>
                                {flight.scheduled_arrival_mt}
                            </span>
                        )}
                </div>
                {delay !== null && (
                    <p className={`mt-1 text-xs ${delayed
                        ? (variant === "dark" ? "text-amber-300" : "text-amber-600")
                        : early
                            ? (variant === "dark" ? "text-emerald-300" : "text-emerald-600")
                            : t.muted}`}>
                        {delayed
                            ? `${delay} min behind schedule`
                            : early
                                ? `${Math.abs(delay)} min early`
                                : "On time"}
                    </p>
                )}
            </div>

            {/* Telemetry. Airborne only — on the ground these numbers are zero
                or absent and printing them reads as a broken feed. */}
            {airborne && flight.live && (
                <div className={`flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl ${t.liveCard} ${compact ? "px-4 py-2.5" : "px-5 py-3"} text-sm`}>
                    <span className={`flex items-center gap-1.5 font-medium ${t.liveText}`}>
                        <span className="relative flex h-2 w-2">
                            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${variant === "dark" ? "bg-cyan-400" : "bg-blue-400"}`} />
                            <span className={`relative inline-flex rounded-full h-2 w-2 ${variant === "dark" ? "bg-cyan-400" : "bg-blue-600"}`} />
                        </span>
                        Live
                    </span>
                    {typeof flight.live.altitude_ft === "number" && (
                        <span className={`flex items-center gap-1.5 ${t.muted}`}>
                            <Navigation size={14} /> {flight.live.altitude_ft.toLocaleString()} ft
                        </span>
                    )}
                    {typeof flight.live.ground_speed_kts === "number" && (
                        <span className={`flex items-center gap-1.5 ${t.muted}`}>
                            <Gauge size={14} /> {flight.live.ground_speed_kts} kts
                        </span>
                    )}
                </div>
            )}

            {/* Say plainly that a landed flight has stopped updating. Without
                this the passenger has no way to tell a frozen snapshot from a
                live feed that simply isn't changing. */}
            {final && !flight.cancelled && (
                <p className={`text-[11px] ${t.muted}`}>
                    Final — this flight has landed and is no longer updating.
                </p>
            )}

            {(flight.sources?.schedule || (flight.sources?.live && airborne)) && (
                <p className={`text-[10px] text-right ${t.muted}`}>
                    {flight.sources?.schedule ? `Schedule: ${flight.sources.schedule}` : ""}
                    {flight.sources?.live && airborne ? ` · Live: ${flight.sources.live}` : ""}
                </p>
            )}
        </div>
    );
}
