"use client";

import { useEffect } from "react";
import { APIProvider, Map, AdvancedMarker, useMap } from "@vis.gl/react-google-maps";

/*
 * FlightMap — live aircraft position + flown route for the public FlightTracker.
 *
 * Everything here comes from AeroAPI's GET /flights/{fa_flight_id}/position via
 * the /flight-status response:
 *   last_position -> the marker (rotated to the aircraft's heading)
 *   waypoints     -> `path`, the track actually flown so far
 *   bounding_box  -> `bounds`, used to frame the whole route
 *
 * Only rendered when the flight is airborne; scheduled/arrived flights have no
 * position. Uses the same Google config as HomeMap / the /cabin console
 * (NEXT_PUBLIC_GMAPS_API_KEY + the SummitOS Map ID) so the map loads from the
 * single shared @vis.gl/react-google-maps script. libraries={["places"]}
 * mirrors HomeMap so client-side navigation to /book (which needs Places)
 * doesn't break — see the note in HomeMap.tsx.
 */

export interface LatLng {
    lat: number;
    lng: number;
}

export interface Bounds {
    south: number;
    west: number;
    north: number;
    east: number;
}

const SOLO_ZOOM = 7; // used when there's a fix but no route to frame

/* SummitOS brand cobalt — matches --primary-hsl (221 83% 53%) in globals.css,
   so the route reads as ours rather than as Google's default blue. */
const BRAND_COBALT = "#2563eb";
const BRAND_COBALT_GLOW = "#60a5fa";

/** Draws the flown track. @vis.gl has no Polyline component, so this manages
 *  google.maps.Polylines imperatively and cleans them up on change/unmount.
 *  Two stacked lines: a soft wide glow under a solid brand-cobalt core, so the
 *  route stays legible over both ocean and land. */
function FlightPath({ path }: { path: LatLng[] }) {
    const map = useMap();
    useEffect(() => {
        if (!map || path.length < 2) return;
        const glow = new google.maps.Polyline({
            path, map, geodesic: true,
            strokeColor: BRAND_COBALT_GLOW, strokeOpacity: 0.35, strokeWeight: 8,
            zIndex: 1,
        });
        const core = new google.maps.Polyline({
            path, map, geodesic: true,
            strokeColor: BRAND_COBALT, strokeOpacity: 0.95, strokeWeight: 3,
            zIndex: 2,
        });
        return () => { glow.setMap(null); core.setMap(null); };
    }, [map, path]);
    return null;
}

/** Frames everything we draw, once the map is ready.
 *
 *  Bounds are derived from the route points plus the aircraft, NOT from
 *  AeroAPI's bounding_box: that box covers only the portion already flown, so
 *  fitting to it crops the rest of the route off-screen. The server box is kept
 *  as a fallback for the rare case where we have a fix but no waypoints. */
function FitToRoute({
    path, position, bounds,
}: { path: LatLng[]; position: LatLng; bounds?: Bounds | null }) {
    const map = useMap();
    useEffect(() => {
        if (!map) return;
        if (path.length >= 2) {
            const b = new google.maps.LatLngBounds();
            path.forEach((p) => b.extend(p));
            b.extend(position);
            map.fitBounds(b, 32); // padding so nothing sits flush to the edge
        } else if (bounds) {
            map.fitBounds(
                new google.maps.LatLngBounds(
                    { lat: bounds.south, lng: bounds.west },
                    { lat: bounds.north, lng: bounds.east }
                ),
                32
            );
        } else {
            map.setCenter(position);
            map.setZoom(SOLO_ZOOM);
        }
    }, [map, path, bounds, position.lat, position.lng]); // eslint-disable-line react-hooks/exhaustive-deps
    return null;
}

function AircraftMarker({ position, heading }: { position: LatLng; heading?: number }) {
    return (
        <AdvancedMarker position={position} title="Aircraft position">
            <div className="relative flex h-9 w-9 items-center justify-center">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400/30" />
                <span className="relative flex h-8 w-8 items-center justify-center rounded-full border border-blue-400/60 bg-blue-500/30 shadow backdrop-blur-md">
                    {/* Arrow points north (up); rotate by the track heading
                        (0=N, 90=E) so it faces the direction of travel. */}
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        className="text-blue-300"
                        style={heading != null ? { transform: `rotate(${heading}deg)` } : undefined}
                        aria-hidden="true"
                    >
                        <path d="M12 2L4 20l8-4 8 4z" />
                    </svg>
                </span>
            </div>
        </AdvancedMarker>
    );
}

export default function FlightMap({
    position,
    heading,
    path = [],
    bounds,
}: {
    position: LatLng;
    heading?: number;
    path?: LatLng[];
    bounds?: Bounds | null;
}) {
    const apiKey = process.env.NEXT_PUBLIC_GMAPS_API_KEY;
    const mapId = process.env.NEXT_PUBLIC_GMAPS_MAP_ID;

    // No map config, or no live fix -> render nothing (the tracker still shows
    // the textual telemetry). Never block the rest of the card on the map.
    if (!apiKey || !mapId || !position) return null;

    return (
        <div className="overflow-hidden rounded-2xl border border-blue-200/60 shadow-sm" style={{ height: 260 }}>
            <APIProvider apiKey={apiKey} libraries={["places"]}>
                <Map
                    mapId={mapId}
                    renderingType="VECTOR"
                    /* DARK matches the SummitOS map identity used by HomeMap and
                       the /cabin console, and makes the cobalt route read as ours. */
                    colorScheme="DARK"
                    style={{ width: "100%", height: "100%" }}
                    defaultCenter={position}
                    defaultZoom={SOLO_ZOOM}
                    disableDefaultUI={true}
                    gestureHandling="greedy"
                    clickableIcons={false}
                >
                    <FitToRoute path={path} position={position} bounds={bounds} />
                    <FlightPath path={path} />
                    <AircraftMarker position={position} heading={heading} />
                </Map>
            </APIProvider>
        </div>
    );
}
