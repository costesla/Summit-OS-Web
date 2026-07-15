"use client";

import { useEffect } from "react";
import { APIProvider, Map, AdvancedMarker, useMap } from "@vis.gl/react-google-maps";

/*
 * Home map — dual state, driven by the backend privacy gate.
 *
 *   mode="offline"  privacy:true  -> static regional overview, NO coordinates
 *   mode="live"     privacy:false -> interactive map + vehicle marker
 *
 * Uses the same Google config as the /cabin console (VECTOR + DARK + the
 * SummitOS Map ID) so the look is identical.
 *
 * SECURITY: this component only ever renders what it's given. It cannot make
 * the location private — the backend trip gate (services/trip_window.py) is
 * the control. Never derive `mode` from anything but the API's privacy flag.
 */

export interface LatLng {
    lat: number;
    lng: number;
}

/** Regional framing for the offline state — Colorado Springs / Pikes Peak.
 *  Deliberately a fixed landmark, never anything derived from the vehicle. */
const REGION_CENTER: LatLng = { lat: 38.8339, lng: -104.8214 };
const REGION_ZOOM = 10;
const LIVE_ZOOM = 15;

function ConfigErrorOverlay() {
    return (
        <div className="flex h-full w-full items-center justify-center bg-sos-dark px-6 text-center">
            <div>
                <p className="text-xs font-bold uppercase tracking-widest text-amber-400">Map temporarily unavailable</p>
                <p className="mt-1 text-[11px] text-sos-dim">We&rsquo;ll be back shortly</p>
            </div>
        </div>
    );
}

/** Pans to the vehicle as it moves (live mode only). */
function FollowVehicle({ position }: { position: LatLng }) {
    const map = useMap();
    useEffect(() => {
        if (map) map.panTo(position);
    }, [map, position.lat, position.lng]); // eslint-disable-line react-hooks/exhaustive-deps
    return null;
}

function VehicleMarker({ position, heading }: { position: LatLng; heading?: number }) {
    return (
        <AdvancedMarker position={position} title="COS Tesla · Model Y">
            <div className="relative flex h-11 w-11 items-center justify-center">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400/20" />
                <span className="relative flex h-10 w-10 items-center justify-center rounded-full border border-cyan-500/40 bg-cyan-500/20 shadow-sos-glow backdrop-blur-md">
                    <svg
                        width="22"
                        height="22"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        className="text-cyan-300"
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

export default function HomeMap({
    mode,
    position,
    heading,
}: {
    mode: "offline" | "live";
    position?: LatLng | null;
    heading?: number;
}) {
    const apiKey = process.env.NEXT_PUBLIC_GMAPS_API_KEY;
    const mapId = process.env.NEXT_PUBLIC_GMAPS_MAP_ID;

    if (!apiKey || !mapId) {
        console.error(
            "[HomeMap] NEXT_PUBLIC_GMAPS_API_KEY / NEXT_PUBLIC_GMAPS_MAP_ID missing — " +
                "add them to GitHub Actions secrets and redeploy."
        );
        return <ConfigErrorOverlay />;
    }

    const live = mode === "live" && !!position;

    return (
        <APIProvider apiKey={apiKey}>
            {/* key remounts the map when the operational state flips, so the
                camera + gesture settings reset cleanly rather than needing a
                fully controlled camera. State changes are rare (per trip). */}
            <Map
                key={mode}
                mapId={mapId}
                renderingType="VECTOR"
                colorScheme="DARK"
                style={{ width: "100%", height: "100%" }}
                defaultCenter={live ? position! : REGION_CENTER}
                defaultZoom={live ? LIVE_ZOOM : REGION_ZOOM}
                defaultTilt={live ? 45 : 0}
                disableDefaultUI={true}
                /* offline = static poster; live = fully interactive */
                gestureHandling={live ? "greedy" : "none"}
                clickableIcons={false}
            >
                {live && position && (
                    <>
                        <FollowVehicle position={position} />
                        <VehicleMarker position={position} heading={heading} />
                    </>
                )}
            </Map>
        </APIProvider>
    );
}
