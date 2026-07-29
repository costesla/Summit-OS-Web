"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { APIProvider, Map, AdvancedMarker, useMap } from "@vis.gl/react-google-maps";

/*
 * ArrivalMap — one map that follows an airport pickup from the air to the curb.
 *
 *   FLIGHT   inbound aircraft: live position, flown route, origin/destination
 *   LANDED   brief hand-off card, then auto-dissolves (never blocks the map)
 *   VEHICLE  the car on its way to collect the passenger
 *
 * Built on @vis.gl/react-google-maps — the same stack as AirshowMap (the cabin
 * console vehicle map) and FlightMap, so this adds no map library and reuses
 * the SummitOS Map ID styling.
 *
 * The LANDED card is deliberately calm: a repeat client sees it on every trip,
 * so it states facts and leaves. No confetti, no dismiss button, one short
 * fade. It only ever claims a driver ETA the vehicle feed actually reports.
 *
 * `showViewToggle` adds a Flight/Driver control for the passenger. It is OFF by
 * default, because the public flight lookup has no driver to switch to — only
 * the cabin console, which is scoped to one passenger's own trip, turns it on.
 */

/* The mode rules live in ./arrivalMode so they can be tested as plain
   functions, without React or the Maps SDK. Re-exported here so existing
   imports of this component keep working. */
import {
    ARRIVAL_SWITCH_DELAY_MIN, LANDED_CARD_MS, deriveMode, minutesSinceLanding,
    resolveView,
} from "./arrivalMode";
import type {
    ArrivalMode, DriverLike, FlightLike, LatLng, VehicleLike, ViewChoice,
} from "./arrivalMode";

export {
    ARRIVAL_SWITCH_DELAY_MIN, LANDED_CARD_MS, deriveMode, minutesSinceLanding,
    resolveView,
};
export type { ArrivalMode, DriverLike, FlightLike, LatLng, VehicleLike, ViewChoice };

const BRAND_COBALT = "#2563eb";
const BRAND_COBALT_GLOW = "#60a5fa";
/** Zoom used when there is a single point to show rather than a route to frame. */
const SOLO_ZOOM = 9;

/* ── shared map pieces ──────────────────────────────────────────────────── */

function RoutePath({ path }: { path: LatLng[] }) {
    const map = useMap();
    useEffect(() => {
        if (!map || path.length < 2) return;
        const glow = new google.maps.Polyline({
            path, map, geodesic: true, zIndex: 1,
            strokeColor: BRAND_COBALT_GLOW, strokeOpacity: 0.35, strokeWeight: 8,
        });
        const core = new google.maps.Polyline({
            path, map, geodesic: true, zIndex: 2,
            strokeColor: BRAND_COBALT, strokeOpacity: 0.95, strokeWeight: 3,
        });
        return () => { glow.setMap(null); core.setMap(null); };
    }, [map, path]);
    return null;
}

function FitTo({ points }: { points: LatLng[] }) {
    const map = useMap();
    useEffect(() => {
        if (!map || !points.length) return;
        if (points.length === 1) {
            map.setCenter(points[0]);
            map.setZoom(SOLO_ZOOM);
            return;
        }
        const b = new google.maps.LatLngBounds();
        points.forEach((p) => b.extend(p));
        map.fitBounds(b, 32);
    }, [map, points]);
    return null;
}

function Puck({ position, heading, label }: { position: LatLng; heading?: number; label: string }) {
    return (
        <AdvancedMarker position={position} title={label}>
            <div className="relative flex h-9 w-9 items-center justify-center">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400/30" />
                <span className="relative flex h-8 w-8 items-center justify-center rounded-full border border-blue-400/60 bg-blue-500/30 shadow backdrop-blur-md">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"
                        className="text-blue-300"
                        style={heading != null ? { transform: `rotate(${heading}deg)` } : undefined}
                        aria-hidden="true">
                        <path d="M12 2L4 20l8-4 8 4z" />
                    </svg>
                </span>
            </div>
        </AdvancedMarker>
    );
}

/* ── the hand-off card ──────────────────────────────────────────────────── */

function LandedCard({ visible, headline, detail }: {
    visible: boolean; headline: string; detail: string;
}) {
    return (
        <div
            role="status"
            aria-live="polite"
            className={`pointer-events-none absolute inset-x-3 bottom-3 z-10 rounded-xl border border-white/15
                        bg-slate-900/85 px-4 py-3 text-white shadow-lg backdrop-blur-md
                        transition-opacity duration-700 ${visible ? "opacity-100" : "opacity-0"}`}
        >
            <p className="text-sm font-semibold">{headline}</p>
            <p className="mt-0.5 text-xs text-slate-300">{detail}</p>
        </div>
    );
}

/* ── passenger view control ─────────────────────────────────────────────── */

function ViewToggle({ choice, effective, onChoose }: {
    choice: ViewChoice;
    effective: ArrivalMode;
    onChoose: (c: ViewChoice) => void;
}) {
    // While on AUTO nothing is "selected" by the passenger, but the control
    // still has to show what they're looking at — otherwise the buttons read as
    // dead. So highlight the effective view and mark AUTO separately.
    const active = (c: "FLIGHT" | "VEHICLE") =>
        choice === "AUTO" ? viewOf(effective) === c : choice === c;

    const btn = (c: "FLIGHT" | "VEHICLE", label: string) => (
        <button
            type="button"
            onClick={() => onChoose(c)}
            aria-pressed={active(c)}
            className={`rounded-lg px-3 py-1 text-[11px] font-semibold transition-colors ${active(c)
                ? "bg-white/90 text-slate-900"
                : "text-slate-200 hover:bg-white/10"}`}
        >
            {label}
        </button>
    );

    return (
        <div className="absolute left-2 top-2 z-10 flex items-center gap-1 rounded-xl border border-white/15 bg-slate-900/75 p-1 backdrop-blur-md">
            {btn("FLIGHT", "Flight")}
            {btn("VEHICLE", "Driver")}
            {choice !== "AUTO" && (
                <button
                    type="button"
                    onClick={() => onChoose("AUTO")}
                    className="rounded-lg px-2 py-1 text-[11px] font-medium text-cyan-300 hover:bg-white/10"
                    title="Follow the trip automatically"
                >
                    Auto
                </button>
            )}
        </div>
    );
}

/** Which toggle position a rendered mode corresponds to. LANDED is the
 *  hand-off card drawn over the vehicle layer, so it reads as Driver. */
function viewOf(mode: ArrivalMode): "FLIGHT" | "VEHICLE" {
    return mode === "FLIGHT" ? "FLIGHT" : "VEHICLE";
}

/* ── component ──────────────────────────────────────────────────────────── */

export default function ArrivalMap({
    flight, vehicle, driver, tripBound = false, expectedDestination, className,
    showViewToggle = false, vehicleSpeed, vehicleStandby = false, onViewChange,
}: {
    flight?: FlightLike | null;
    vehicle?: VehicleLike | null;
    driver?: DriverLike | null;
    tripBound?: boolean;
    expectedDestination?: string | null;
    className?: string;
    /** Show the passenger's Flight/Driver control. Cabin console only. */
    showViewToggle?: boolean;
    /** Vehicle speed for the driver view's telemetry chip (mph). */
    vehicleSpeed?: number | null;
    /** No vehicle position has ever been received — the car is asleep. */
    vehicleStandby?: boolean;
    /** Reports the rendered mode so a parent can show matching detail. */
    onViewChange?: (mode: ArrivalMode) => void;
}) {
    const apiKey = process.env.NEXT_PUBLIC_GMAPS_API_KEY;
    const mapId = process.env.NEXT_PUBLIC_GMAPS_MAP_ID;

    // The card fires once per trip. Keyed on the flight so a repoll, reconnect
    // or re-render can't replay it; a genuinely new flight starts fresh.
    const tripKey = flight?.flight_number || "none";
    const firedFor = useRef<string | null>(null);
    const [cardDone, setCardDone] = useState(false);
    const [cardVisible, setCardVisible] = useState(false);

    // The passenger's own choice. Sticky for the life of the console session —
    // deliberately not persisted, because a choice made on one trip shouldn't
    // silently govern the next one.
    const [choice, setChoice] = useState<ViewChoice>("AUTO");

    // Ticks only while a landed flight is still inside the hand-off delay, so
    // the switch happens on time even if the surface isn't polling just then.
    const [, setTick] = useState(0);
    const waiting = !!flight?.on_ground && tripBound
        && minutesSinceLanding(flight) < ARRIVAL_SWITCH_DELAY_MIN;
    useEffect(() => {
        if (!waiting) return;
        const id = setInterval(() => setTick((n) => n + 1), 30000);
        return () => clearInterval(id);
    }, [waiting]);

    const auto = deriveMode({ flight, tripBound, expectedDestination, cardDone });
    // Without the toggle there is no passenger choice to honour, so the derived
    // mode governs exactly as it did before this control existed.
    const { mode, driverSuggested } = showViewToggle
        ? resolveView({ auto, choice })
        : { mode: auto, driverSuggested: false };

    useEffect(() => {
        onViewChange?.(mode);
    }, [mode, onViewChange]);

    useEffect(() => {
        if (mode !== "LANDED" || firedFor.current === tripKey) return;
        firedFor.current = tripKey;
        setCardVisible(true);
        // Auto-dissolve — never a modal the passenger has to dismiss.
        const fade = setTimeout(() => setCardVisible(false), LANDED_CARD_MS);
        const done = setTimeout(() => setCardDone(true), LANDED_CARD_MS + 700);
        return () => { clearTimeout(fade); clearTimeout(done); };
    }, [mode, tripKey]);

    const flightPos = flight?.live?.latitude != null && flight?.live?.longitude != null
        ? { lat: flight.live.latitude, lng: flight.live.longitude } : null;
    const vehiclePos = vehicle?.latitude != null && vehicle?.longitude != null
        ? { lat: vehicle.latitude, lng: vehicle.longitude } : null;

    const showVehicleLayer = mode === "VEHICLE" || mode === "LANDED";
    const path = (mode === "FLIGHT" && flight?.live?.path) || [];
    const points = useMemo(() => {
        const pts: LatLng[] = [];
        if (showVehicleLayer && vehiclePos) pts.push(vehiclePos);
        if (mode === "FLIGHT") {
            if (path.length) pts.push(...path);
            if (flightPos) pts.push(flightPos);
        }
        return pts;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mode, showVehicleLayer, vehiclePos?.lat, vehiclePos?.lng, flightPos?.lat, flightPos?.lng, path.length]);

    // Card copy — only promises what the feed actually reports.
    const airport = flight?.destination?.city || flight?.landed_at || "the airport";
    const headline = `Landed at ${airport}`;
    const detail = driver?.dispatched && typeof driver.eta_minutes === "number"
        ? `Your driver is on the way — about ${driver.eta_minutes} min.`
        : "Your driver is being dispatched.";

    /* Polling stops the moment the aircraft is down, so a landed flight is a
       frozen snapshot. Saying "Live" over it would be untrue. */
    const flightIsFinal = !!flight?.on_ground;
    const cornerLabel = mode === "FLIGHT"
        ? (flightIsFinal ? "Final · FlightAware" : "Live · FlightAware")
        : "Live vehicle";
    /* Rendered in BOTH branches. A landed flight often has no position left to
       plot, which drops us into the fallback — and that is precisely the view
       that most needs to say it has stopped updating. */
    const cornerChip = (
        <p className="absolute right-2 top-2 z-10 rounded bg-slate-900/70 px-1.5 py-0.5 text-[9px] text-slate-300">
            {cornerLabel}
        </p>
    );

    const toggle = showViewToggle
        ? <ViewToggle choice={choice} effective={mode} onChoose={setChoice} />
        : null;

    /* The offer, not the takeover: auto wants the driver but the passenger
       pinned the flight. One tap moves them; ignoring it changes nothing. */
    const driverOffer = driverSuggested ? (
        <button
            type="button"
            onClick={() => setChoice("VEHICLE")}
            className="absolute inset-x-3 bottom-3 z-10 rounded-xl border border-cyan-400/30 bg-slate-900/85
                       px-4 py-2.5 text-left text-white shadow-lg backdrop-blur-md transition-colors
                       hover:bg-slate-800/85"
        >
            <span className="block text-sm font-semibold">Your driver is on the way</span>
            <span className="mt-0.5 block text-xs text-cyan-300">Tap to follow the car →</span>
        </button>
    ) : null;

    // A cancelled flight is a status message, not a map.
    if (flight?.cancelled) {
        return (
            <div className={`rounded-2xl border border-amber-200/60 bg-amber-50/70 px-5 py-4 ${className || ""}`}>
                <p className="text-sm font-semibold text-amber-800">
                    {flight.flight_number} is cancelled
                </p>
                <p className="mt-0.5 text-xs text-amber-700">
                    No live tracking for this flight. Contact us to rearrange your pickup.
                </p>
            </div>
        );
    }

    if (!apiKey || !mapId) return null;

    // Nothing to plot yet — say so rather than showing an empty map. The toggle
    // stays mounted so a passenger who switched here isn't stranded with no way
    // back to the other view.
    if (!points.length) {
        const emptyCopy = mode === "FLIGHT"
            ? (flightIsFinal ? "This flight has landed." : "Awaiting live flight position…")
            : vehicleStandby
                ? "Your driver's car is asleep — it'll appear here once it wakes."
                : "Driver being dispatched…";
        return (
            <div className={`relative flex items-center justify-center rounded-2xl border border-blue-200/60 bg-slate-900/90 ${className || ""}`}
                /* Callers that size their own container (the cabin console wraps
               this in a fixed-height panel) pass className and own the height. */
                style={className ? undefined : { height: 260 }}>
                {toggle}
                {cornerChip}
                <p className="px-6 text-center text-xs font-medium uppercase tracking-widest text-slate-400">
                    {emptyCopy}
                </p>
                {/* The offer belongs here too: a landed flight often has no
                    live position left to plot, which is exactly when the
                    passenger most needs the way over to the car. */}
                {driverOffer}
            </div>
        );
    }

    return (
        <div className={`relative overflow-hidden rounded-2xl border border-blue-200/60 shadow-sm ${className || ""}`}
            /* Callers that size their own container (the cabin console wraps
               this in a fixed-height panel) pass className and own the height. */
            style={className ? undefined : { height: 260 }}>
            <APIProvider apiKey={apiKey} libraries={["places"]}>
                <Map
                    mapId={mapId}
                    renderingType="VECTOR"
                    colorScheme="DARK"
                    style={{ width: "100%", height: "100%" }}
                    defaultCenter={points[0]}
                    defaultZoom={SOLO_ZOOM}
                    disableDefaultUI={true}
                    gestureHandling="greedy"
                    clickableIcons={false}
                >
                    <FitTo points={points} />
                    {mode === "FLIGHT" && path.length >= 2 && <RoutePath path={path} />}
                    {mode === "FLIGHT" && flightPos && (
                        <Puck position={flightPos} heading={flight?.live?.heading_deg} label="Aircraft" />
                    )}
                    {showVehicleLayer && vehiclePos && (
                        <Puck position={vehiclePos} heading={vehicle?.heading ?? undefined} label="Your driver" />
                    )}
                </Map>
            </APIProvider>

            {toggle}

            {/* Vehicle telemetry, carried over from the AirshowMap view so
                switching to Driver doesn't quietly lose the speed read-out. */}
            {showVehicleLayer && typeof vehicleSpeed === "number" && vehicleSpeed > 0 && (
                <p className="absolute bottom-2 left-2 z-10 rounded bg-slate-900/70 px-2 py-0.5 text-[10px] font-medium text-slate-200">
                    {Math.round(vehicleSpeed)} mph
                </p>
            )}

            {mode === "LANDED" && (
                <LandedCard visible={cardVisible} headline={headline} detail={detail} />
            )}

            {driverOffer}

            {cornerChip}
        </div>
    );
}
