"use client";

import { useEffect } from "react";
import { APIProvider, Map, AdvancedMarker, useMap } from "@vis.gl/react-google-maps";

/*
 * FlightMap — live aircraft position for the public FlightTracker.
 *
 * Renders the plane where it is right now (FR24 live position from the
 * /flight-status response) with the icon rotated to its heading. Only shown
 * when the flight is airborne; scheduled/arrived flights have no live position.
 *
 * Uses the same Google config as HomeMap / the /cabin console
 * (NEXT_PUBLIC_GMAPS_API_KEY + the SummitOS Map ID) so the map loads from the
 * single shared @vis.gl/react-google-maps script. libraries={["places"]}
 * mirrors HomeMap so client-side navigation to /book (which needs Places)
 * doesn't break — see the note in HomeMap.tsx.
 */

export interface LatLng {
    lat: number;
    lng: number;
}

const DEFAULT_ZOOM = 7;

/** Keeps the aircraft centred as its position updates between lookups. */
function FollowAircraft({ position }: { position: LatLng }) {
    const map = useMap();
    useEffect(() => {
        if (map) map.panTo(position);
    }, [map, position.lat, position.lng]); // eslint-disable-line react-hooks/exhaustive-deps
    return null;
}

function AircraftMarker({ position, heading }: { position: LatLng; heading?: number }) {
    return (
        <AdvancedMarker position={position} title="Aircraft position">
            <div className="relative flex h-9 w-9 items-center justify-center">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400/20" />
                <span className="relative flex h-8 w-8 items-center justify-center rounded-full border border-blue-500/40 bg-blue-500/20 shadow backdrop-blur-md">
                    {/* Arrow points north (up); rotate by the track heading
                        (0=N, 90=E) so it faces the direction of travel. */}
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        className="text-blue-600"
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
}: {
    position: LatLng;
    heading?: number;
}) {
    const apiKey = process.env.NEXT_PUBLIC_GMAPS_API_KEY;
    const mapId = process.env.NEXT_PUBLIC_GMAPS_MAP_ID;

    // No map config, or no live fix -> render nothing (the tracker still shows
    // the textual telemetry). Never block the rest of the card on the map.
    if (!apiKey || !mapId || !position) return null;

    return (
        <div className="overflow-hidden rounded-2xl border border-white/70" style={{ height: 260 }}>
            <APIProvider apiKey={apiKey} libraries={["places"]}>
                <Map
                    mapId={mapId}
                    renderingType="VECTOR"
                    colorScheme="LIGHT"
                    style={{ width: "100%", height: "100%" }}
                    defaultCenter={position}
                    defaultZoom={DEFAULT_ZOOM}
                    disableDefaultUI={true}
                    gestureHandling="greedy"
                    clickableIcons={false}
                >
                    <FollowAircraft position={position} />
                    <AircraftMarker position={position} heading={heading} />
                </Map>
            </APIProvider>
        </div>
    );
}
