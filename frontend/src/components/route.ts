/*
 * route — the trip as an ORDERED sequence of places.
 *
 * The booking engine used to hold `pickup` and `dropoff` as two strings plus a
 * stop COUNT, where stop addresses were optional, never reached the map, and
 * were dropped entirely at the hand-off to the booking step. A "stop" was a $5
 * line item, not a place. That is the defect this module exists to fix: a trip
 * is [pickup, ...stops, finalDropoff], and the order is the trip.
 *
 * Kept free of React and the Maps SDK, like ./arrivalMode, because the failures
 * here are silent. Get an index wrong and the route still renders, still
 * prices, and still books — it just sends the driver to the places in the wrong
 * sequence, which nobody notices until a passenger is standing somewhere
 * unexpected.
 *
 * DELIBERATELY ABSENT: reordering, drag-and-drop, and route optimisation. A
 * passenger enters their stops in the order they intend to travel; letting
 * software rearrange that is a different feature with a different failure mode.
 */

/** Upper bound on intermediate stops.
 *
 *  Matches the cap the previous counter UI enforced, and is what the Stripe
 *  metadata budget assumes: the paid path carries the route as numbered keys
 *  (stop0…stop4) because a single metadata value caps at 500 characters, well
 *  under five autocompleted street addresses. Raising this means checking that
 *  key budget, not just this constant. */
export const MAX_STOPS = 5;

export interface RoutePoint {
    /** Stable across edits so React keys don't collapse two stops into one. */
    id: string;
    address: string;
    /** Google typed this Place as an airport. Drives the arrival workflow. */
    isAirport: boolean;
}

export type RouteRole = "PICKUP" | "STOP" | "DROPOFF";

/** Which airport workflow, if any, this route implies.
 *
 *  ARRIVING — we collect someone off an inbound flight: track it, hand over to
 *  the driver on landing.
 *  DEPARTING — we take someone TO a flight. Worth knowing operationally, but
 *  there is no inbound aircraft to follow and no arrival to hand over from. */
export type AirportDirection = "ARRIVING" | "DEPARTING" | null;

let counter = 0;
function nextId(): string {
    counter += 1;
    return `p${counter}`;
}

export function point(address = "", isAirport = false): RoutePoint {
    return { id: nextId(), address, isAirport };
}

/** A new trip: somewhere to leave from, somewhere to end up. */
export function createRoute(): RoutePoint[] {
    return [point(), point()];
}

export function roleAt(index: number, length: number): RouteRole {
    if (index === 0) return "PICKUP";
    if (index === length - 1) return "DROPOFF";
    return "STOP";
}

export function labelFor(index: number, length: number): string {
    const role = roleAt(index, length);
    if (role === "PICKUP") return "Pickup";
    if (role === "DROPOFF") return "Final Drop-off";
    return `Stop ${index}`;
}

export function stopCount(route: RoutePoint[]): number {
    return Math.max(0, route.length - 2);
}

export function canAddStop(route: RoutePoint[]): boolean {
    return stopCount(route) < MAX_STOPS;
}

/** Insert a stop immediately before the final drop-off.
 *
 *  Always at the end of the stops, never appended to the array — appending
 *  would silently demote the passenger's final destination to a waypoint. */
export function addStop(route: RoutePoint[]): RoutePoint[] {
    if (!canAddStop(route)) return route;
    return [...route.slice(0, -1), point(), route[route.length - 1]];
}

/** Remove a stop by id. The pickup and final drop-off are not removable —
 *  a trip without either isn't a trip. */
export function removeStop(route: RoutePoint[], id: string): RoutePoint[] {
    const index = route.findIndex((p) => p.id === id);
    if (index <= 0 || index >= route.length - 1) return route;
    return route.filter((p) => p.id !== id);
}

export function setPoint(route: RoutePoint[], id: string,
                         patch: Partial<Omit<RoutePoint, "id">>): RoutePoint[] {
    return route.map((p) => (p.id === id ? { ...p, ...patch } : p));
}

/** Every leg has an address. An ordered route cannot contain a blank waypoint:
 *  a gap in the middle isn't a shorter trip, it's an unknown one. */
export function isComplete(route: RoutePoint[]): boolean {
    return route.length >= 2 && route.every((p) => p.address.trim().length > 0);
}

/** The legs still missing an address, for telling the passenger what's left. */
export function missingLabels(route: RoutePoint[]): string[] {
    return route
        .map((p, i) => (p.address.trim() ? null : labelFor(i, route.length)))
        .filter((label): label is string => label !== null);
}

/** Shape the pricing API already accepts.
 *
 *  Endpoints stay named pickup/dropoff on the wire on purpose: every consumer
 *  downstream — Graph, the receipts, the dashboard, the cabin token — reads
 *  those keys, and renaming them to match new UI labels would be a migration
 *  disguised as a rename. Only the ORDERED stops are new. */
export function toQuoteRequest(route: RoutePoint[]): {
    pickup: string; dropoff: string; stops: string[];
} {
    return {
        pickup: route[0]?.address.trim() ?? "",
        dropoff: route[route.length - 1]?.address.trim() ?? "",
        stops: route.slice(1, -1).map((p) => p.address.trim()),
    };
}

/** Which way the airport trip runs, if it is one.
 *
 *  ARRIVING wins when both ends are airports: the inbound flight is the one
 *  that decides when we need to be at the curb, and it's the only one the
 *  arrival hand-off can follow. */
export function airportDirection(route: RoutePoint[]): AirportDirection {
    if (route.length < 2) return null;
    if (route[0].isAirport) return "ARRIVING";
    if (route[route.length - 1].isAirport) return "DEPARTING";
    return null;
}

/* ── fare integrity ──────────────────────────────────────────────────────────
 *
 * A quote that failed to recalculate must never be the number a passenger
 * agrees to. The old engine kept the previous quote on a partial-address error
 * "to prevent map flashing", which meant a stale total could survive a route
 * edit and follow the passenger to checkout. */

export interface QuoteLike {
    total?: number | null;
    baseFare?: number | null;
    overage?: number | null;
    stopFee?: number | null;
    tellerFee?: number | null;
    waitFee?: number | null;
    deadheadFee?: number | null;
}

const FARE_FIELDS: (keyof QuoteLike)[] = [
    "total", "baseFare", "overage", "stopFee", "tellerFee", "waitFee",
    "deadheadFee",
];

/** True only if every fare component is a real, finite number and the total is
 *  positive. Rejects null, undefined, NaN, Infinity and $0 — each of which has
 *  reached a checkout button in some version of this form. */
export function quoteIsBookable(quote: QuoteLike | null | undefined): boolean {
    if (!quote) return false;
    for (const field of FARE_FIELDS) {
        const value = quote[field];
        if (value === undefined || value === null) continue;   // absent is fine
        if (typeof value !== "number" || !Number.isFinite(value)) return false;
    }
    return typeof quote.total === "number"
        && Number.isFinite(quote.total)
        && quote.total > 0;
}
