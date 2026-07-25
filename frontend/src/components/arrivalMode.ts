/*
 * arrivalMode — the decision logic behind the airport arrival hand-off.
 *
 * Deliberately separate from ArrivalMap.tsx and free of React and the Google
 * Maps SDK, so the rules below can be tested as plain functions. These are the
 * rules a passenger actually feels — when the flight gives way to the driver,
 * and when we stay quiet — and their failure modes are silent: get a comparison
 * backwards and the map either never hands over or hands over instantly, with
 * no error and nothing a typecheck would catch.
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

/** How long the hand-off card stays up before dissolving, in ms. */
export const LANDED_CARD_MS = 5000;

/** How long after touchdown to keep showing the flight before handing over to
 *  the driver. Deplaning plus baggage claim means the passenger isn't looking
 *  for the car yet — switching at the gate is premature, and any ETA quoted
 *  then is stale by the time they actually reach the curb. */
export const ARRIVAL_SWITCH_DELAY_MIN = 15;

export function sameAirport(a?: string | null, b?: string | null): boolean {
    if (!a || !b) return false;
    return a.trim().toUpperCase() === b.trim().toUpperCase();
}

/** Minutes since wheels-down. Measured from the aircraft's real touchdown
 *  timestamp, NOT from page load, so reopening the app can't restart the wait.
 *  Returns Infinity when the timestamp is missing so a landed flight still
 *  hands over rather than getting stuck on the flight view. */
export function minutesSinceLanding(flight?: FlightLike | null, now?: number): number {
    const stamp = flight?.on_ground_since;
    if (!stamp) return Number.POSITIVE_INFINITY;
    const t = Date.parse(stamp);
    if (Number.isNaN(t)) return Number.POSITIVE_INFINITY;
    return ((now ?? Date.now()) - t) / 60000;
}

/** Which view the map should be showing. Pure; `now` is injectable so the
 *  timing can be tested without waiting fifteen real minutes. */
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

        if (!tripBound || diverted) return "FLIGHT";   // landed status, no card/driver

        // Hold the flight view through deplaning and baggage claim. At the gate
        // the passenger is thinking about getting off and finding their bags,
        // not about the car — showing the driver then is noise, and an ETA
        // quoted at that moment is wrong by the time they reach the curb.
        if (minutesSinceLanding(flight, now) < ARRIVAL_SWITCH_DELAY_MIN) return "FLIGHT";

        return cardDone ? "VEHICLE" : "LANDED";
    }

    return tripBound ? "VEHICLE" : "FLIGHT";
}
