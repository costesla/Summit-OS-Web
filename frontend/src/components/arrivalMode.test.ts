import { describe, expect, test } from "vitest";
import {
    ARRIVAL_SWITCH_DELAY_MIN, deriveMode, minutesSinceLanding, resolveView,
} from "./arrivalMode";
import type { FlightLike } from "./arrivalMode";

/*
 * The arrival hand-off rules — when the flight gives way to the driver.
 *
 * These failures are silent by nature: a reversed comparison means the map
 * either never hands over or hands over the instant the wheels touch, with no
 * error and nothing a typecheck catches. The first a passenger knows is
 * standing at the curb looking at the wrong screen.
 */

const TOUCHDOWN = "2026-07-25T18:00:00Z";
const at = (minsAfterTouchdown: number) =>
    Date.parse(TOUCHDOWN) + minsAfterTouchdown * 60_000;

function flight(over: Partial<FlightLike> = {}): FlightLike {
    return {
        flight_number: "DL4089",
        destination: { code: "COS", city: "Colorado Springs" },
        origin: { code: "MSP", city: "Minneapolis" },
        on_ground: false,
        cancelled: false,
        diverted: false,
        live: { latitude: 39.1, longitude: -104.2, heading_deg: 200, path: [] },
        ...over,
    };
}

const landed = (over: Partial<FlightLike> = {}) =>
    flight({ on_ground: true, on_ground_since: TOUCHDOWN, landed_at: "COS", ...over });

describe("in the air", () => {
    test("shows the flight for the whole time airborne", () => {
        expect(deriveMode({ flight: flight(), tripBound: true, cardDone: false }))
            .toBe("FLIGHT");
    });

    test("still the flight on final approach", () => {
        const almost = flight({ status: "En Route / On Time" });
        expect(deriveMode({ flight: almost, tripBound: true, cardDone: false }))
            .toBe("FLIGHT");
    });
});

describe("the 15-minute hold after touchdown", () => {
    test("wheels-down does NOT hand over — they are still deplaning", () => {
        expect(deriveMode({
            flight: landed(), tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(0),
        })).toBe("FLIGHT");
    });

    test("still the flight at the baggage carousel", () => {
        expect(deriveMode({
            flight: landed(), tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(10),
        })).toBe("FLIGHT");
    });

    test("hands over once they are heading for the curb", () => {
        expect(deriveMode({
            flight: landed(), tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(ARRIVAL_SWITCH_DELAY_MIN),
        })).toBe("LANDED");
    });

    test("goes to the vehicle once the card has run", () => {
        expect(deriveMode({
            flight: landed(), tripBound: true, expectedDestination: "COS",
            cardDone: true, now: at(20),
        })).toBe("VEHICLE");
    });

    test("wait is measured from touchdown, not from opening the app", () => {
        // Passenger closed the app at the gate and reopens it 25 min later:
        // they must NOT be made to wait another 15 minutes.
        expect(deriveMode({
            flight: landed(), tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(25),
        })).toBe("LANDED");
    });

    test("a missing touchdown timestamp still hands over", () => {
        // Never strand the passenger on the flight view because a field is absent.
        expect(deriveMode({
            flight: landed({ on_ground_since: null }), tripBound: true,
            expectedDestination: "COS", cardDone: false, now: at(0),
        })).toBe("LANDED");
        expect(minutesSinceLanding(landed({ on_ground_since: "not-a-date" })))
            .toBe(Number.POSITIVE_INFINITY);
    });
});

describe("suppression", () => {
    test("a diversion never announces the driver", () => {
        // Landed at Denver when Colorado Springs was expected.
        const diverted = landed({ landed_at: "DEN", diverted: true });
        expect(deriveMode({
            flight: diverted, tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(60),
        })).toBe("FLIGHT");
    });

    test("wrong airport counts as a diversion even without the flag", () => {
        const elsewhere = landed({ landed_at: "DEN", diverted: false });
        expect(deriveMode({
            flight: elsewhere, tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(60),
        })).toBe("FLIGHT");
    });

    test("a bare public lookup never shows the card or the driver", () => {
        expect(deriveMode({
            flight: landed(), tripBound: false, expectedDestination: "COS",
            cardDone: false, now: at(60),
        })).toBe("FLIGHT");
    });

    test("airport codes match case- and whitespace-insensitively", () => {
        expect(deriveMode({
            flight: landed({ landed_at: " cos " }), tripBound: true,
            expectedDestination: "COS", cardDone: false, now: at(20),
        })).toBe("LANDED");
    });
});

describe("vehicle-only surface", () => {
    test("no flight on a trip-bound surface shows the vehicle", () => {
        expect(deriveMode({ flight: null, tripBound: true, cardDone: false }))
            .toBe("VEHICLE");
    });
});

/*
 * The passenger override. The rule worth protecting: the state machine may
 * OFFER the driver view, never seize it. Someone who deliberately pinned the
 * flight and then had the screen change under them learns not to trust the
 * control — and that costs more than a stale flight view ever does.
 */
describe("passenger override", () => {
    test("AUTO defers to the state machine, whatever it decided", () => {
        for (const auto of ["FLIGHT", "LANDED", "VEHICLE"] as const) {
            expect(resolveView({ auto, choice: "AUTO" }))
                .toEqual({ mode: auto, driverSuggested: false, overridden: false });
        }
    });

    test("picking Flight holds the flight view even once auto wants the car", () => {
        const r = resolveView({ auto: "VEHICLE", choice: "FLIGHT" });
        expect(r.mode).toBe("FLIGHT");
        expect(r.overridden).toBe(true);
    });

    test("...and offers the driver rather than switching to it", () => {
        expect(resolveView({ auto: "VEHICLE", choice: "FLIGHT" }).driverSuggested).toBe(true);
        // LANDED is the hand-off card — auto is already on its way to the car.
        expect(resolveView({ auto: "LANDED", choice: "FLIGHT" }).driverSuggested).toBe(true);
    });

    test("no driver offer while the plane is still in the air", () => {
        // Nothing to offer yet: suggesting the car mid-flight is noise.
        expect(resolveView({ auto: "FLIGHT", choice: "FLIGHT" }).driverSuggested).toBe(false);
    });

    test("picking Driver goes straight to the car, even mid-flight", () => {
        const r = resolveView({ auto: "FLIGHT", choice: "VEHICLE" });
        expect(r.mode).toBe("VEHICLE");
        expect(r.overridden).toBe(true);
        // Already on the car — there is nothing left to suggest.
        expect(r.driverSuggested).toBe(false);
    });

    test("returning to AUTO gives control back to the state machine", () => {
        // The way back must actually restore automatic behaviour, not freeze
        // whatever was last shown.
        expect(resolveView({ auto: "VEHICLE", choice: "AUTO" }).mode).toBe("VEHICLE");
        expect(resolveView({ auto: "FLIGHT", choice: "AUTO" }).mode).toBe("FLIGHT");
        expect(resolveView({ auto: "VEHICLE", choice: "AUTO" }).overridden).toBe(false);
    });

    test("an override cannot resurrect a suppressed hand-off", () => {
        // A diversion makes deriveMode return FLIGHT. Choosing Driver shows the
        // car's own map, which is honest — but nothing here may turn a
        // suppressed arrival into a LANDED hand-off card.
        const diverted = landed({ landed_at: "DEN", diverted: true });
        const auto = deriveMode({
            flight: diverted, tripBound: true, expectedDestination: "COS",
            cardDone: false, now: at(60),
        });
        expect(auto).toBe("FLIGHT");
        expect(resolveView({ auto, choice: "VEHICLE" }).mode).toBe("VEHICLE");
        expect(resolveView({ auto, choice: "AUTO" }).mode).toBe("FLIGHT");
    });
});
