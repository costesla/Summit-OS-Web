import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
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
