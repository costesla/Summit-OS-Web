import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import React from "react";

/* The Maps SDK is replaced with plain divs: these tests are about the hand-off
   card's behaviour, not about Google's renderer. useMap() returns null so the
   polyline/fitBounds effects bail out exactly as they do before a map loads. */
vi.mock("@vis.gl/react-google-maps", () => ({
    APIProvider: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    Map: ({ children }: { children?: React.ReactNode }) => <div data-testid="map">{children}</div>,
    AdvancedMarker: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    useMap: () => null,
}));

import ArrivalMap from "./ArrivalMap";
import { LANDED_CARD_MS } from "./arrivalMode";

const TOUCHDOWN = "2026-07-25T18:00:00Z";
/** 20 minutes after touchdown — past the hold, so the hand-off is due. */
const NOW = Date.parse(TOUCHDOWN) + 20 * 60_000;

const landedFlight = {
    flight_number: "DL4089",
    destination: { code: "COS", city: "Colorado Springs" },
    origin: { code: "MSP", city: "Minneapolis" },
    on_ground: true,
    on_ground_since: TOUCHDOWN,
    landed_at: "COS",
};
const vehicle = { latitude: 38.85, longitude: -104.79, heading: 180 };
const driverEnRoute = { dispatched: true, eta_minutes: 9, heading_to_expected: true, moving: true };

function renderMap(props: Record<string, unknown> = {}) {
    return render(
        <ArrivalMap
            flight={landedFlight}
            vehicle={vehicle}
            driver={driverEnRoute}
            tripBound
            expectedDestination="COS"
            {...props}
        />
    );
}

beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_GMAPS_API_KEY", "test-key");
    vi.stubEnv("NEXT_PUBLIC_GMAPS_MAP_ID", "test-map-id");
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    cleanup();
});

describe("the hand-off card", () => {
    test("states the airport and the driver's real ETA", () => {
        renderMap();
        expect(screen.getByText(/Landed at Colorado Springs/)).toBeTruthy();
        expect(screen.getByText(/about 9 min/)).toBeTruthy();
    });

    test("promises no ETA when the driver is not dispatched", () => {
        // Never invent a number — say what's true instead.
        renderMap({ driver: { dispatched: false, eta_minutes: null } });
        expect(screen.getByText(/being dispatched/)).toBeTruthy();
        expect(screen.queryByText(/about \d+ min/)).toBeNull();
    });

    test("auto-dissolves without the passenger touching anything", () => {
        renderMap();
        const card = screen.getByRole("status");
        expect(card.className).toContain("opacity-100");

        act(() => { vi.advanceTimersByTime(LANDED_CARD_MS); });
        expect(screen.getByRole("status").className).toContain("opacity-0");

        // ...and then gives way to the vehicle view entirely.
        act(() => { vi.advanceTimersByTime(800); });
        expect(screen.queryByRole("status")).toBeNull();
    });

    test("has no dismiss control and never blocks the map", () => {
        renderMap();
        expect(screen.queryByRole("button")).toBeNull();
        expect(screen.getByRole("status").className).toContain("pointer-events-none");
        expect(screen.getByTestId("map")).toBeTruthy();
    });

    test("fires once — a repoll with the same flight does not replay it", () => {
        const { rerender } = renderMap();
        expect(screen.getByRole("status")).toBeTruthy();

        // Let it dissolve.
        act(() => { vi.advanceTimersByTime(LANDED_CARD_MS + 800); });
        expect(screen.queryByRole("status")).toBeNull();

        // Repolls / reconnects deliver the same flight object again.
        for (let i = 0; i < 3; i++) {
            rerender(
                <ArrivalMap flight={landedFlight} vehicle={vehicle} driver={driverEnRoute}
                    tripBound expectedDestination="COS" />
            );
            act(() => { vi.advanceTimersByTime(30_000); });
        }
        expect(screen.queryByRole("status")).toBeNull();
    });
});

describe("suppression", () => {
    test("a diversion shows no card and no driver", () => {
        renderMap({
            flight: { ...landedFlight, landed_at: "DEN", diverted: true },
        });
        expect(screen.queryByRole("status")).toBeNull();
        expect(screen.queryByText(/about 9 min/)).toBeNull();
    });

    test("a bare public lookup shows no card", () => {
        renderMap({ tripBound: false });
        expect(screen.queryByRole("status")).toBeNull();
    });

    test("inside the 15-minute hold there is no card yet", () => {
        vi.setSystemTime(Date.parse(TOUCHDOWN) + 5 * 60_000);
        renderMap();
        expect(screen.queryByRole("status")).toBeNull();
    });
});

describe("degradation", () => {
    test("a cancelled flight shows a status, not a map", () => {
        renderMap({ flight: { ...landedFlight, cancelled: true } });
        expect(screen.getByText(/is cancelled/)).toBeTruthy();
        expect(screen.queryByTestId("map")).toBeNull();
    });

    test("no vehicle position falls back rather than showing a blank map", () => {
        renderMap({ vehicle: null, flight: { ...landedFlight, live: null } });
        expect(screen.getByText(/dispatched/i)).toBeTruthy();
        expect(screen.queryByTestId("map")).toBeNull();
    });
});

/*
 * The passenger's Flight/Driver control. It is off by default — the public
 * flight lookup has no driver to switch to — so every assertion here has to
 * opt in, and the tests above prove the default surface is unchanged.
 */
const airborneFlight = {
    flight_number: "DL4089",
    destination: { code: "COS", city: "Colorado Springs" },
    origin: { code: "MSP", city: "Minneapolis" },
    on_ground: false,
    live: { latitude: 39.1, longitude: -104.2, heading_deg: 200, path: [] },
};

const flightBtn = () => screen.getByRole("button", { name: "Flight" });
const driverBtn = () => screen.getByRole("button", { name: "Driver" });
const autoBtn = () => screen.queryByRole("button", { name: "Auto" });

describe("the passenger view control", () => {
    test("is absent unless the surface asks for it", () => {
        renderMap();
        expect(screen.queryByRole("button", { name: "Flight" })).toBeNull();
    });

    test("shows which view is on screen while still on automatic", () => {
        // Landed and past the hold: automatic is handing over, so the control
        // must read Driver — otherwise both buttons look inert.
        renderMap({ showViewToggle: true });
        expect(driverBtn().getAttribute("aria-pressed")).toBe("true");
        expect(flightBtn().getAttribute("aria-pressed")).toBe("false");
        // Nothing overridden yet, so there is nothing to go back to.
        expect(autoBtn()).toBeNull();
    });

    test("switches view on tap, without a reload", () => {
        renderMap({ showViewToggle: true, flight: airborneFlight });
        expect(flightBtn().getAttribute("aria-pressed")).toBe("true");

        fireEvent.click(driverBtn());
        expect(driverBtn().getAttribute("aria-pressed")).toBe("true");
        expect(flightBtn().getAttribute("aria-pressed")).toBe("false");
    });

    test("a manual choice is not overwritten when the flight lands", () => {
        // Pinned to Flight on a landed flight: automatic wants the car, and
        // must not take it.
        renderMap({ showViewToggle: true });
        fireEvent.click(flightBtn());
        expect(flightBtn().getAttribute("aria-pressed")).toBe("true");

        // Let every timer the hand-off uses run out.
        act(() => { vi.advanceTimersByTime(LANDED_CARD_MS + 60_000); });
        expect(flightBtn().getAttribute("aria-pressed")).toBe("true");
        expect(screen.queryByRole("status")).toBeNull();
    });

    test("offers the driver instead of seizing the view", () => {
        renderMap({ showViewToggle: true });
        fireEvent.click(flightBtn());

        const offer = screen.getByRole("button", { name: /Tap to follow the car/ });
        expect(offer).toBeTruthy();

        // The offer works when taken — but only then.
        fireEvent.click(offer);
        expect(driverBtn().getAttribute("aria-pressed")).toBe("true");
        expect(screen.queryByRole("button", { name: /Tap to follow the car/ })).toBeNull();
    });

    test("no driver offer while the aircraft is still airborne", () => {
        renderMap({ showViewToggle: true, flight: airborneFlight });
        fireEvent.click(flightBtn());
        expect(screen.queryByRole("button", { name: /Tap to follow the car/ })).toBeNull();
    });

    test("automatic mode can be restored", () => {
        renderMap({ showViewToggle: true, flight: airborneFlight });
        fireEvent.click(driverBtn());
        expect(autoBtn()).toBeTruthy();

        fireEvent.click(autoBtn()!);
        // Back under the state machine: airborne means Flight.
        expect(flightBtn().getAttribute("aria-pressed")).toBe("true");
        expect(autoBtn()).toBeNull();
    });

    test("the passenger is never stranded without a way back", () => {
        // Driver view with no vehicle position falls back to a message; the
        // control has to survive that branch or there is no route out.
        renderMap({ showViewToggle: true, vehicle: null, flight: { ...landedFlight, live: null } });
        expect(screen.getByText(/dispatched/i)).toBeTruthy();
        expect(driverBtn()).toBeTruthy();
        expect(flightBtn()).toBeTruthy();
    });
});

describe("live vs final", () => {
    test("an airborne flight is labelled live", () => {
        renderMap({ flight: airborneFlight });
        expect(screen.getByText(/Live · FlightAware/)).toBeTruthy();
    });

    test("a landed flight is labelled final, never live", () => {
        // Polling stops at touchdown, so this view is a frozen snapshot.
        renderMap({ showViewToggle: true });
        fireEvent.click(flightBtn());
        expect(screen.getByText(/Final · FlightAware/)).toBeTruthy();
        expect(screen.queryByText(/Live · FlightAware/)).toBeNull();
    });

    test("the vehicle view stays live", () => {
        renderMap();
        expect(screen.getByText(/Live vehicle/)).toBeTruthy();
    });
});

describe("vehicle telemetry carried over from AirshowMap", () => {
    test("shows speed while the car is moving", () => {
        renderMap({ vehicleSpeed: 43.4 });
        expect(screen.getByText("43 mph")).toBeTruthy();
    });

    test("says nothing rather than printing a zero when parked", () => {
        renderMap({ vehicleSpeed: 0 });
        expect(screen.queryByText(/mph/)).toBeNull();
    });

    test("a sleeping car explains itself instead of showing an empty map", () => {
        renderMap({
            vehicle: null, vehicleStandby: true,
            flight: { ...landedFlight, live: null },
        });
        expect(screen.getByText(/asleep/i)).toBeTruthy();
    });
});
