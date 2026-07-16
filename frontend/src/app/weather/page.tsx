"use client";

import WeatherWatch from "@/components/WeatherWatch";

/* Promoted from a homepage section to its own route (dark redesign). */
export default function WeatherPage() {
    return (
        <main className="min-h-screen bg-[#0a0a0a] px-6 pb-20 pt-24 lg:pt-12">
            <div className="mx-auto max-w-3xl">
                <header className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight text-white">Weather</h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Conditions along the route. Mountain weather changes fast — we watch it so your pickup doesn&rsquo;t surprise you.
                    </p>
                </header>
                <WeatherWatch />
            </div>
        </main>
    );
}
