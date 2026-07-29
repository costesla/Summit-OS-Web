"use client";

import { useState } from "react";
import { Plane, Search, AlertCircle } from "lucide-react";
import ArrivalMap from "./ArrivalMap";
/* The read-out itself lives in FlightStatusPanel so the cabin console renders
   exactly the same fields from exactly the same payload — one implementation,
   two palettes. This page keeps the search box, the errors, and the map. */
import FlightStatusPanel, { isAirborne } from "./FlightStatusPanel";
import type { FlightPanelData } from "./FlightStatusPanel";

const API = "https://summitos-api.azurewebsites.net/api/flight-status";

type FlightData = FlightPanelData & {
    live?: (FlightPanelData["live"] & {
        latitude?: number; longitude?: number; heading_deg?: number;
        /* Route actually flown so far + its bounding box (AeroAPI waypoints). */
        path?: { lat: number; lng: number }[];
        bounds?: { south: number; west: number; north: number; east: number } | null;
    }) | null;
};

export default function FlightTracker() {
    const [flightNum, setFlightNum] = useState("");
    const [dest, setDest] = useState("");
    const [flightData, setFlightData] = useState<FlightData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const checkFlight = async () => {
        if (!flightNum) return;
        setLoading(true);
        setError("");
        setFlightData(null);
        const destCode = dest.trim().toUpperCase();
        try {
            const res = await fetch(API, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                // expectedDestination pins the exact leg when a flight number is
                // reused for several routes in a day (e.g. WN250). Optional.
                body: JSON.stringify({
                    flightNumber: flightNum,
                    ...(destCode ? { expectedDestination: destCode } : {}),
                }),
            });
            const data = await res.json();
            if (res.ok && data.success && data.found) {
                setFlightData(data.data);
            } else if (res.ok && data.success && !data.found) {
                setError(destCode
                    ? `No ${flightNum} flight arriving at ${destCode} right now. Check the flight number and arrival airport, then try again.`
                    : "No flight found for that number right now. Double-check the flight number (e.g. UA123) and try again.");
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

            <input
                type="text"
                placeholder="Arriving at (optional) — e.g. DAL, DEN"
                value={dest}
                onChange={(e) => setDest(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && checkFlight()}
                aria-label="Arrival airport (optional)"
                className="w-full mb-2"
                style={{ marginBottom: "0.5rem" }}
            />

            <p className="mb-2 text-[11px] text-[var(--color-text-muted)]">
                Same flight number can fly several routes a day — add the arrival airport to pin the exact one. Powered by FlightAware
            </p>

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

            {flightData && (
                <div className="mt-6 space-y-5">
                    <FlightStatusPanel flight={flightData} variant="light" />

                    {/* Live map. tripBound={false} because a public lookup has
                        no booking behind it: the map shows the flight and then
                        its landed state, and never advances to the hand-off
                        card or the driver. That branch belongs to the cabin
                        console, which is scoped to a passenger's own trip. */}
                    {isAirborne(flightData) && flightData.live
                        && typeof flightData.live.latitude === "number"
                        && typeof flightData.live.longitude === "number" && (
                        <ArrivalMap flight={flightData} tripBound={false} />
                    )}
                </div>
            )}

            {!flightData && !loading && !error && (
                <p className="mt-4 text-sm text-[var(--color-text-muted)]">
                    Enter a flight number to see its arrival time, delay, and live position.
                </p>
            )}
        </div>
    );
}
