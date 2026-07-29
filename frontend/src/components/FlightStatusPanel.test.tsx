import { afterEach, describe, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import FlightStatusPanel, { isFinal, statusBadge } from "./FlightStatusPanel";
import type { FlightPanelData } from "./FlightStatusPanel";

/*
 * The flight read-out.
 *
 * Two properties matter more than the layout:
 *
 *   1. It must never throw. This panel renders third-party provider data and
 *      sits inside the cabin console — the surface a passenger uses to open the
 *      trunk. A missing airline or a null delay taking that down would lock
 *      someone out of their luggage over a cosmetic field.
 *
 *   2. A landed flight must not read as live. Polling stops at touchdown, so
 *      what's on screen is frozen. Calling it "Live" is the kind of small lie
 *      that gets found out while someone stands at a carousel.
 */

const base: FlightPanelData = {
    flight_number: "DL4089",
    airline: "Delta Air Lines",
    origin: { code: "MSP", city: "Minneapolis" },
    destination: { code: "COS", city: "Colorado Springs" },
    scheduled_arrival_mt: "4:35 PM",
    estimated_arrival_mt: "4:35 PM",
    delay_minutes: 0,
    aircraft_type: "B738",
};

afterEach(cleanup);

describe("the basics", () => {
    test("shows the airline, ident, route and arrival", () => {
        render(<FlightStatusPanel flight={base} />);
        expect(screen.getByText("Delta Air Lines")).toBeTruthy();
        expect(screen.getByText(/DL4089/)).toBeTruthy();
        expect(screen.getByText("MSP")).toBeTruthy();
        expect(screen.getByText("COS")).toBeTruthy();
        expect(screen.getByText("4:35 PM")).toBeTruthy();
        expect(screen.getByText(/B738/)).toBeTruthy();
    });

    test("a delay shows the new time, the old one, and the gap", () => {
        render(<FlightStatusPanel flight={{
            ...base, estimated_arrival_mt: "5:15 PM", delay_minutes: 40,
        }} />);
        expect(screen.getByText("5:15 PM")).toBeTruthy();
        expect(screen.getByText("4:35 PM")).toBeTruthy();  // struck through
        expect(screen.getByText(/40 min behind schedule/)).toBeTruthy();
        expect(screen.getByText(/Delayed 40 min/)).toBeTruthy();
    });

    test("running early is said plainly, not as a negative delay", () => {
        render(<FlightStatusPanel flight={{
            ...base, estimated_arrival_mt: "4:10 PM", delay_minutes: -25,
        }} />);
        expect(screen.getByText(/25 min early/)).toBeTruthy();
        expect(screen.queryByText(/-25/)).toBeNull();
    });

    test("a couple of minutes either way is on time, not a delay", () => {
        render(<FlightStatusPanel flight={{ ...base, delay_minutes: 3 }} />);
        expect(screen.getByText("On time")).toBeTruthy();
        expect(screen.queryByText(/behind schedule/)).toBeNull();
    });
});

describe("progress", () => {
    test("shows how far along an airborne flight is", () => {
        render(<FlightStatusPanel flight={{
            ...base, progress_percent: 62, live: { altitude_ft: 35000 },
        }} />);
        const bar = screen.getByRole("progressbar");
        expect(bar.getAttribute("aria-valuenow")).toBe("62");
        expect(screen.getByText(/62% of the way/)).toBeTruthy();
    });

    test("is hidden once down — the badge says it better", () => {
        render(<FlightStatusPanel flight={{
            ...base, progress_percent: 100, on_ground: true, landed_at: "COS",
        }} />);
        expect(screen.queryByRole("progressbar")).toBeNull();
    });

    test("an out-of-range percentage is clamped, not rendered raw", () => {
        render(<FlightStatusPanel flight={{ ...base, progress_percent: 140 }} />);
        expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
    });
});

describe("live vs final", () => {
    test("airborne shows live telemetry", () => {
        render(<FlightStatusPanel flight={{
            ...base, live: { altitude_ft: 35000, ground_speed_kts: 450 },
        }} />);
        expect(screen.getByText("Live")).toBeTruthy();
        expect(screen.getByText(/35,000 ft/)).toBeTruthy();
        expect(screen.getByText(/450 kts/)).toBeTruthy();
    });

    test("landed says it has stopped updating, and drops the live block", () => {
        render(<FlightStatusPanel flight={{
            ...base, on_ground: true, landed_at: "COS",
            live: { altitude_ft: 0, ground_speed_kts: 0 },
        }} />);
        expect(screen.getByText(/no longer updating/)).toBeTruthy();
        expect(screen.getByText(/Landed · COS/)).toBeTruthy();
        expect(screen.queryByText("Live")).toBeNull();
    });

    test("the arrival heading switches to past tense once down", () => {
        render(<FlightStatusPanel flight={{ ...base, on_ground: true }} />);
        expect(screen.getByText(/Arrived \(Mountain Time\)/)).toBeTruthy();
    });

    test("isFinal covers both ways a flight stops changing", () => {
        expect(isFinal({ on_ground: true })).toBe(true);
        expect(isFinal({ cancelled: true })).toBe(true);
        expect(isFinal(base)).toBe(false);
        expect(isFinal(null)).toBe(false);
    });
});

describe("disruption", () => {
    test("a cancellation outranks everything else", () => {
        render(<FlightStatusPanel flight={{
            ...base, cancelled: true, delay_minutes: 90,
        }} />);
        expect(screen.getByText("Cancelled")).toBeTruthy();
        expect(screen.queryByText(/Delayed 90/)).toBeNull();
    });

    test("a diversion is spelled out, not left as a badge", () => {
        // Landing at the wrong airport changes where the passenger physically
        // is — burying that in a chip would be negligent.
        render(<FlightStatusPanel flight={{
            ...base, diverted: true, on_ground: true, landed_at: "DEN",
        }} />);
        expect(screen.getByText("Diverted")).toBeTruthy();
        expect(screen.getByText(/diverted to DEN/)).toBeTruthy();
        expect(screen.getByText(/contact us/i)).toBeTruthy();
    });

    test("a diversion outranks a delay in the badge", () => {
        const b = statusBadge({ ...base, diverted: true, delay_minutes: 60 }, "light");
        expect(b.label).toBe("Diverted");
    });
});

describe("missing and malformed data", () => {
    test("renders from an empty object without throwing", () => {
        expect(() => render(<FlightStatusPanel flight={{}} />)).not.toThrow();
        expect(screen.getByText("Flight")).toBeTruthy();     // airline fallback
        expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    });

    test("nulls in every optional field are survivable", () => {
        const nulled: FlightPanelData = {
            flight_number: "XX1",
            airline: null, airline_code: null, status: null,
            origin: undefined, destination: undefined,
            scheduled_arrival_mt: null, estimated_arrival_mt: null,
            delay_minutes: null, aircraft_type: null, progress_percent: null,
            live: null, sources: undefined,
        };
        expect(() => render(<FlightStatusPanel flight={nulled} />)).not.toThrow();
        expect(screen.getByText("Scheduled")).toBeTruthy();  // status fallback
        // No delay line invented from a null.
        expect(screen.queryByText("On time")).toBeNull();
    });

    test("falls back to the airline code when the name is missing", () => {
        render(<FlightStatusPanel flight={{ ...base, airline: null, airline_code: "DAL" }} />);
        expect(screen.getByText("DAL")).toBeTruthy();
    });

    test("does not strike out a scheduled time identical to the estimate", () => {
        // A 40-minute delay whose two timestamps happen to match would
        // otherwise print the same time twice, one struck through.
        render(<FlightStatusPanel flight={{
            ...base, delay_minutes: 40,
            scheduled_arrival_mt: "4:35 PM", estimated_arrival_mt: "4:35 PM",
        }} />);
        expect(screen.getAllByText("4:35 PM").length).toBe(1);
    });
});

describe("both palettes", () => {
    test("dark variant renders the same facts", () => {
        render(<FlightStatusPanel flight={base} variant="dark" compact />);
        expect(screen.getByText("Delta Air Lines")).toBeTruthy();
        expect(screen.getByText("COS")).toBeTruthy();
    });

    test("badges differ by variant so contrast holds on either background", () => {
        const light = statusBadge({ ...base, cancelled: true }, "light");
        const dark = statusBadge({ ...base, cancelled: true }, "dark");
        expect(light.label).toBe(dark.label);
        expect(light.cls).not.toBe(dark.cls);
    });
});
