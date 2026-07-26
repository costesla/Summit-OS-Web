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
 */

/* The mode rules live in ./arrivalMode so they can be tested as plain
   functions, without React or the Maps SDK. Re-exported here so existing
   imports of this component keep working. */
import {
    ARRIVAL_SWITCH_DELAY_MIN, LANDED_CARD_MS, deriveMode, minutesSinceLanding,
} from "./arrivalMode";
import type {
    ArrivalMode, DriverLike, FlightLike, LatLng, VehicleLike,
} from "./arrivalMode";

export {
    ARRIVAL_SWITCH_DELAY_MIN, LANDED_CARD_MS, deriveMode, minutesSinceLanding,
};
export type { ArrivalMode, DriverLike, FlightLike, LatLng, VehicleLike };

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

/* ── component ──────────────────────────────────────────────────────────── */

export default function ArrivalMap({
    flight, vehicle, driver, tripBound = false, expectedDestination, className,
}: {
    flight?: FlightLike | null;
    vehicle?: VehicleLike | null;
    driver?: DriverLike | null;
    tripBound?: boolean;
    expectedDestination?: string | null;
    className?: string;
}) {
    const apiKey = process.env.NEXT_PUBLIC_GMAPS_API_KEY;
    const mapId = process.env.NEXT_PUBLIC_GMAPS_MAP_ID;

    // The card fires once per trip. Keyed on the flight so a repoll, reconnect
    // or re-render can't replay it; a genuinely new flight starts fresh.
    const tripKey = flight?.flight_number || "none";
    const firedFor = useRef<string | null>(null);
    const [cardDone, setCardDone] = useState(false);
    const [cardVisible, setCardVisible] = useState(false);

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

    const mode = deriveMode({ flight, tripBound, expectedDestination, cardDone });

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

    // Nothing to plot yet — say so rather than showing an empty map.
    if (!points.length) {
        return (
            <div className={`flex items-center justify-center rounded-2xl border border-blue-200/60 bg-slate-900/90 ${className || ""}`}
                /* Callers that size their own container (the cabin console wraps
               this in a fixed-height panel) pass className and own the height. */
            style={className ? undefined : { height: 260 }}>
                <p className="px-6 text-center text-xs font-medium uppercase tracking-widest text-slate-400">
                    {mode === "FLIGHT" ? "Awaiting live flight position…" : "Driver being dispatched…"}
                </p>
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

            {mode === "LANDED" && (
                <LandedCard visible={cardVisible} headline={headline} detail={detail} />
            )}

            <p className="absolute right-2 top-2 z-10 rounded bg-slate-900/70 px-1.5 py-0.5 text-[9px] text-slate-300">
                {mode === "FLIGHT" ? "Powered by FlightAware" : "Live vehicle"}
            </p>
        </div>
    );
}
