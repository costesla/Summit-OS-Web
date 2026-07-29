import { describe, expect, test } from "vitest";
import {
    MAX_STOPS, addStop, airportDirection, canAddStop, createRoute, isComplete,
    labelFor, missingLabels, point, quoteIsBookable, removeStop, roleAt,
    setPoint, stopCount, toQuoteRequest,
} from "./route";
import type { RoutePoint } from "./route";

/*
 * The trip as an ordered sequence.
 *
 * These failures are the quiet kind: get an index wrong and the route still
 * renders, still prices, and still books — it just sends the driver to the
 * places in the wrong sequence, which nobody notices until a passenger is
 * standing somewhere they didn't expect to be.
 *
 * The other half is fare integrity. A quote that failed to recalculate must
 * never be the number a passenger agrees to, and "$0" is a number.
 */

const route = (...addresses: string[]): RoutePoint[] =>
    addresses.map((a) => point(a));

const airport = (address: string) => point(address, true);

describe("shape", () => {
    test("a new trip is somewhere to leave from and somewhere to end up", () => {
        const r = createRoute();
        expect(r).toHaveLength(2);
        expect(stopCount(r)).toBe(0);
    });

    test("roles are positional, not stored", () => {
        const r = route("A", "B", "C", "D");
        expect(roleAt(0, r.length)).toBe("PICKUP");
        expect(roleAt(1, r.length)).toBe("STOP");
        expect(roleAt(2, r.length)).toBe("STOP");
        expect(roleAt(3, r.length)).toBe("DROPOFF");
    });

    test("labels read the way a passenger thinks about the trip", () => {
        const r = route("A", "B", "C");
        expect(labelFor(0, r.length)).toBe("Pickup");
        expect(labelFor(1, r.length)).toBe("Stop 1");
        expect(labelFor(2, r.length)).toBe("Final Drop-off");
    });

    test("every point keeps a stable id", () => {
        // React keys depend on this — reusing an id collapses two stops
        // into one on re-render.
        const r = addStop(addStop(createRoute()));
        expect(new Set(r.map((p) => p.id)).size).toBe(r.length);
    });
});

describe("adding and removing stops", () => {
    test("a stop is inserted BEFORE the final drop-off", () => {
        // Appending would silently demote the passenger's destination to a
        // waypoint — the trip would end somewhere they never chose.
        const r = addStop(route("Home", "Airport"));
        expect(r.map((p) => p.address)).toEqual(["Home", "", "Airport"]);
    });

    test("stops accumulate in the order they were added", () => {
        let r = route("Home", "Airport");
        r = addStop(r);
        r = setPoint(r, r[1].id, { address: "Dry cleaner" });
        r = addStop(r);
        r = setPoint(r, r[2].id, { address: "Bank" });
        expect(r.map((p) => p.address))
            .toEqual(["Home", "Dry cleaner", "Bank", "Airport"]);
    });

    test("the cap is enforced", () => {
        let r = createRoute();
        for (let i = 0; i < MAX_STOPS + 3; i++) r = addStop(r);
        expect(stopCount(r)).toBe(MAX_STOPS);
        expect(canAddStop(r)).toBe(false);
    });

    test("removing a stop preserves the order of the rest", () => {
        const r = route("Home", "A", "B", "C", "Airport");
        const after = removeStop(r, r[2].id);
        expect(after.map((p) => p.address)).toEqual(["Home", "A", "C", "Airport"]);
    });

    test("the pickup and the final drop-off cannot be removed", () => {
        // A trip without either end isn't a shorter trip, it's not a trip.
        const r = route("Home", "A", "Airport");
        expect(removeStop(r, r[0].id)).toEqual(r);
        expect(removeStop(r, r[2].id)).toEqual(r);
    });

    test("removing an unknown id changes nothing", () => {
        const r = route("Home", "A", "Airport");
        expect(removeStop(r, "nope")).toEqual(r);
    });

    test("editing one leg leaves the others alone", () => {
        const r = route("Home", "A", "Airport");
        const after = setPoint(r, r[1].id, { address: "B" });
        expect(after.map((p) => p.address)).toEqual(["Home", "B", "Airport"]);
    });
});

describe("completeness", () => {
    test("a blank leg makes the route incomplete", () => {
        // An ordered route cannot contain a gap: a blank waypoint isn't a
        // shorter trip, it's an unknown one.
        expect(isComplete(route("Home", "", "Airport"))).toBe(false);
        expect(isComplete(route("Home", "A", "Airport"))).toBe(true);
    });

    test("whitespace is not an address", () => {
        expect(isComplete(route("Home", "   ", "Airport"))).toBe(false);
    });

    test("missing legs are named so the passenger knows what's left", () => {
        const r = route("", "A", "");
        expect(missingLabels(r)).toEqual(["Pickup", "Final Drop-off"]);
    });

    test("a complete route reports nothing missing", () => {
        expect(missingLabels(route("Home", "Airport"))).toEqual([]);
    });
});

describe("the pricing request", () => {
    test("endpoints keep their wire names and stops carry the order", () => {
        // pickup/dropoff stay named that way on the wire on purpose: Graph,
        // the receipts, the dashboard and the cabin token all read those keys.
        const r = route("Home", "Dry cleaner", "Bank", "Airport");
        expect(toQuoteRequest(r)).toEqual({
            pickup: "Home",
            dropoff: "Airport",
            stops: ["Dry cleaner", "Bank"],
        });
    });

    test("a two-point trip sends no stops", () => {
        expect(toQuoteRequest(route("Home", "Airport")).stops).toEqual([]);
    });

    test("addresses are trimmed", () => {
        const r = route("  Home ", " A ", " Airport  ");
        expect(toQuoteRequest(r)).toEqual({
            pickup: "Home", dropoff: "Airport", stops: ["A"],
        });
    });

    test("a repeated address is preserved, not de-duplicated", () => {
        // Going back to the same place twice is a real itinerary.
        const r = route("Home", "Bank", "Home", "Airport");
        expect(toQuoteRequest(r).stops).toEqual(["Bank", "Home"]);
    });
});

describe("airport direction", () => {
    test("an airport at the START is an arrival", () => {
        const r = [airport("COS"), point("Home")];
        expect(airportDirection(r)).toBe("ARRIVING");
    });

    test("an airport at the END is a departure", () => {
        const r = [point("Home"), airport("COS")];
        expect(airportDirection(r)).toBe("DEPARTING");
    });

    test("a plain trip has no direction", () => {
        expect(airportDirection(route("Home", "Office"))).toBe(null);
    });

    test("an airport in the MIDDLE is not a flight trip", () => {
        // Driving past the airport, or dropping someone else off, is not a
        // trip we track a flight for.
        const r = [point("Home"), airport("COS"), point("Office")];
        expect(airportDirection(r)).toBe(null);
    });

    test("airport-to-airport counts as an arrival", () => {
        // The inbound flight is the one that decides when we need to be at the
        // curb, and it's the only one the arrival hand-off can follow.
        const r = [airport("DEN"), airport("COS")];
        expect(airportDirection(r)).toBe("ARRIVING");
    });

    test("direction follows the Place type, not the address text", () => {
        // Text matching is the failure mode this exists to avoid: plenty of
        // real addresses contain the word "airport".
        const r = [point("1 Airport Road, Colorado Springs"), point("Home")];
        expect(airportDirection(r)).toBe(null);
    });
});

describe("fare integrity", () => {
    const good = {
        total: 85, baseFare: 30, overage: 40, stopFee: 10, tellerFee: 0,
        waitFee: 5, deadheadFee: 0,
    };

    test("a complete, positive quote is bookable", () => {
        expect(quoteIsBookable(good)).toBe(true);
    });

    test("nothing at all is not bookable", () => {
        expect(quoteIsBookable(null)).toBe(false);
        expect(quoteIsBookable(undefined)).toBe(false);
    });

    test("a $0 total never reaches checkout", () => {
        // "Free" is what a failed calculation looks like.
        expect(quoteIsBookable({ ...good, total: 0 })).toBe(false);
    });

    test("a negative total never reaches checkout", () => {
        expect(quoteIsBookable({ ...good, total: -20 })).toBe(false);
    });

    test("NaN and Infinity never reach checkout", () => {
        expect(quoteIsBookable({ ...good, total: NaN })).toBe(false);
        expect(quoteIsBookable({ ...good, total: Infinity })).toBe(false);
    });

    test("a NaN in any COMPONENT invalidates the whole quote", () => {
        // The total can look fine while a component is broken — that's a
        // partial total, and it's exactly what must not be agreed to.
        expect(quoteIsBookable({ ...good, stopFee: NaN })).toBe(false);
        expect(quoteIsBookable({ ...good, overage: NaN })).toBe(false);
    });

    test("a non-numeric component invalidates the quote", () => {
        expect(quoteIsBookable({ ...good, stopFee: "10" as unknown as number }))
            .toBe(false);
    });

    test("a missing total is not bookable", () => {
        const { total, ...withoutTotal } = good;
        expect(quoteIsBookable(withoutTotal)).toBe(false);
    });

    test("absent optional components are fine", () => {
        // Not every trip has a mountain surcharge; absent is not broken.
        expect(quoteIsBookable({ total: 30, baseFare: 30 })).toBe(true);
    });
});
