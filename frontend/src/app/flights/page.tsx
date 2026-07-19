"use client";

import FlightTracker from "@/components/FlightTracker";

/* Its own route, styled to match the site (light cobalt-glass theme).
   Backed by the hybrid FlightAware + Flightradar24 integration
   (/api/flight-status): scheduled + estimated arrival, delays, and live
   position once the aircraft is airborne. */
export default function FlightsPage() {
    return (
        <main className="min-h-screen pt-24 pb-24 lg:pt-28">
            <div className="mx-auto max-w-3xl px-6">
                <header className="mb-8 text-center">
                    <h1 className="text-4xl sm:text-5xl">Flight Tracker</h1>
                    <p className="mx-auto mt-3 max-w-xl text-base text-[var(--color-text-muted)]">
                        Check any flight for your airport pickup — scheduled and estimated arrival, delays,
                        and live position once it&rsquo;s in the air, so a late flight doesn&rsquo;t leave
                        you waiting on the curb.
                    </p>
                </header>
                <FlightTracker />
            </div>
        </main>
    );
}
