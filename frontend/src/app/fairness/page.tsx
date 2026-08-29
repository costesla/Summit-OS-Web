import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Fairness Engine | COS Tesla",
    description: "How COS Tesla pricing is calculated — deterministic, no surge, no hidden fees. Effective September 1, 2026.",
};

/* Figures mirror the live pricing engine — updated for September 1, 2026 */
interface PriceLine {
    label: string;
    detail: string;
    value: string;
    accent?: boolean;
    mono?: boolean;
    suffix?: string;
}

const LINES: PriceLine[] = [
    { label: "Base Fare", detail: "Executive vehicle staging & meet-and-greet", value: "$25.00" },
    { label: "Road Mileage", detail: "Turn-by-turn road miles via Google Distance Matrix", value: "$2.00", suffix: "/ mile", accent: true },
    { label: "Denver Airport (DEN)", detail: "Dedicated corridor floor (E-470 tolls included)", value: "$225.00", suffix: "min floor" },
    { label: "Extra Stops", detail: "Each intermediate stop on your route", value: "$5.00", suffix: "/ stop" },
    { label: "Driver Wait Time", detail: "On-site standby, per hour", value: "$25.00", suffix: "/ hr" },
    { label: "Teller County", detail: "Woodland Park, Cripple Creek, Divide (high elevation)", value: "$15.00", suffix: "surcharge" },
];

export default function FairnessPage() {
    return (
        <main className="min-h-screen bg-[#0a0a0a] px-6 pb-20 pt-24 lg:pt-12">
            <div className="mx-auto max-w-3xl">
                <header className="mb-10">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-cyan-500/30 bg-cyan-950/40 text-cyan-400 font-mono text-[0.65rem] uppercase tracking-widest mb-4">
                        Effective September 1, 2026
                    </div>
                    <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white">SummitOS Fairness Engine</h1>
                    <p className="mt-3 leading-relaxed text-slate-400 text-sm md:text-base">
                        Pricing emerges from your actual route — not a menu or surge algorithm. Every dollar is calculated deterministically by real distance, real time, and real complexity.
                    </p>
                </header>

                <div className="rounded-3xl border border-white/10 bg-[#111318] p-2 shadow-2xl">
                    <div className="divide-y divide-white/5">
                        {LINES.map((l) => (
                            <div key={l.label} className="flex items-center justify-between gap-6 px-6 py-5">
                                <div>
                                    <div className="font-semibold text-slate-100">{l.label}</div>
                                    <div className="mt-0.5 text-xs text-slate-500">{l.detail}</div>
                                </div>
                                <span
                                    className={`shrink-0 text-lg font-bold ${
                                        l.accent ? "text-cyan-400" : l.mono ? "font-mono text-sm text-slate-400" : "text-slate-100"
                                    }`}
                                >
                                    {l.value}
                                    {l.suffix ? (
                                        <span className="ml-1 text-sm font-normal text-slate-500">{l.suffix}</span>
                                    ) : null}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="mt-8 rounded-2xl border border-white/5 bg-white/[0.02] p-6 text-xs text-slate-400 leading-relaxed space-y-2">
                    <div className="font-bold text-slate-200 uppercase tracking-wider text-[0.7rem] text-cyan-400">Fairness Guarantee</div>
                    <p>
                        Zero algorithmic surge pricing during blizzards, peak hours, or airport rush. All quotes generated via the Google Maps Distance Matrix API are locked and guaranteed upfront.
                    </p>
                </div>

                <p className="mt-8 border-t border-white/5 pt-6 font-mono text-[0.65rem] leading-relaxed text-slate-600 uppercase">
                    Route calculated via Google Distance Matrix. No surge pricing. No hidden fees. Deterministic — same route always yields same price.
                </p>
            </div>
        </main>
    );
}
