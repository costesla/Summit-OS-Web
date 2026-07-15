"use client";

import FlightTracker from "@/components/FlightTracker";

/* Promoted from a homepage section to its own route (dark redesign).
   Backed by the existing Aviationstack integration (/api/flight-status). */
export default function FlightsPage() {
    return (
        <main className="min-h-screen bg-[#0a0a0a] px-6 pb-20 pt-24 lg:pt-12">
            <div className="mx-auto max-w-3xl">
                <header className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight text-white">Flight Tracker</h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Live flight status for airport pickups. We track the aircraft, not the schedule — so a delay
                        doesn&rsquo;t leave you waiting on a curb.
                    </p>
                </header>
                <FlightTracker />
            </div>
        </main>
    );
}
