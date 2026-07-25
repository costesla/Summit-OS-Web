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

export interface LatLng { lat: number; lng: number }

export interface FlightLike {
    flight_number?: string;
    status?: string | null;
    destination?: { code?: string | null; city?: string | null };
    origin?: { code?: string | null; city?: string | null };
    cancelled?: boolean;
    diverted?: boolean;
    on_ground?: boolean;
    /** ISO touchdown timestamp — the hand-off is timed from this, not page load. */
    on_ground_since?: string | null;
    landed_at?: string | null;
    estimated_arrival_mt?: string | null;
    live?: {
        latitude?: number; longitude?: number; heading_deg?: number;
        path?: LatLng[];
    } | null;
}

/** Privacy-safe driver summary from /api/cabin/state. Minutes and booleans
 *  only — the car's nav destination never reaches the client. */
export interface DriverLike {
    dispatched?: boolean;
    eta_minutes?: number | null;
    heading_to_expected?: boolean | null;
    moving?: boolean;
}

export interface VehicleLike {
    latitude?: number | null;
    longitude?: number | null;
    heading?: number | null;
}

export type ArrivalMode = "FLIGHT" | "LANDED" | "VEHICLE";

const BRAND_COBALT = "#2563eb";
const BRAND_COBALT_GLOW = "#60a5fa";
const SOLO_ZOOM = 9;
/** How long the hand-off card stays up before dissolving, in ms. */
export const LANDED_CARD_MS = 5000;

/** How long after touchdown to keep showing the flight before handing over to
 *  the driver. Deplaning plus baggage claim means the passenger isn't looking
 *  for the car yet — switching at the gate is premature, and any ETA quoted
 *  then is stale by the time they actually reach the curb. */
export const ARRIVAL_SWITCH_DELAY_MIN = 15;

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

/* ── mode derivation ────────────────────────────────────────────────────── */

function sameAirport(a?: string | null, b?: string | null) {
    if (!a || !b) return false;
    return a.trim().toUpperCase() === b.trim().toUpperCase();
}

/** Pure so it can be unit-tested without a map. Exported for tests.
 *
 *  `now` is injectable so the timing can be tested deterministically. */
export function deriveMode({ flight, tripBound, expectedDestination, cardDone, now }: {
    flight?: FlightLike | null;
    tripBound?: boolean;
    expectedDestination?: string | null;
    cardDone: boolean;
    now?: number;
}): ArrivalMode {
    const onGround = !!flight?.on_ground;

    // Still flying (or no flight at all on a vehicle-only surface).
    if (flight && !onGround && !flight.cancelled) return "FLIGHT";

    if (onGround) {
        // A diversion must never trigger the driver hand-off: the passenger is
        // at a different airport and the pickup no longer holds.
        const expected = expectedDestination || null;
        const arrivedWhereExpected = expected
            ? sameAirport(flight?.landed_at, expected)
            : true;
        const diverted = !!flight?.diverted || (expected ? !arrivedWhereExpected : false);

        if (!tripBound || diverted) return "FLIGHT";   // show landed status, no card/driver

        // Hold the flight view through deplaning and baggage claim. At the gate
        // the passenger is thinking about getting off and finding their bags,
        // not about the car — showing the driver then is noise, and an ETA
        // quoted at that moment is wrong by the time they reach the curb.
        if (minutesSinceLanding(flight, now) < ARRIVAL_SWITCH_DELAY_MIN) return "FLIGHT";

        return cardDone ? "VEHICLE" : "LANDED";
    }

    return tripBound ? "VEHICLE" : "FLIGHT";
}

/** Minutes since wheels-down. Measured from the aircraft's real touchdown
 *  timestamp, NOT from page load, so reopening the app can't restart the wait.
 *  Returns Infinity when the timestamp is missing so a landed flight without
 *  one still hands over rather than getting stuck on the flight view. */
export function minutesSinceLanding(flight?: FlightLike | null, now?: number): number {
    const stamp = flight?.on_ground_since;
    if (!stamp) return Number.POSITIVE_INFINITY;
    const t = Date.parse(stamp);
    if (Number.isNaN(t)) return Number.POSITIVE_INFINITY;
    return ((now ?? Date.now()) - t) / 60000;
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
                style={{ height: 260 }}>
                <p className="px-6 text-center text-xs font-medium uppercase tracking-widest text-slate-400">
                    {mode === "FLIGHT" ? "Awaiting live flight position…" : "Driver being dispatched…"}
                </p>
            </div>
        );
    }

    return (
        <div className={`relative overflow-hidden rounded-2xl border border-blue-200/60 shadow-sm ${className || ""}`}
            style={{ height: 260 }}>
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
