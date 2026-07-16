import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Fairness Engine | COS Tesla",
    description: "How COS Tesla pricing is calculated — deterministic, no surge, no hidden fees.",
};

/* Promoted from a homepage section to its own route (dark redesign).
   Figures mirror the live pricing engine — update both together. */
interface PriceLine {
    label: string;
    detail: string;
    value: string;
    accent?: boolean;
    mono?: boolean;
    suffix?: string;
}

const LINES: PriceLine[] = [
    { label: "Base Fare", detail: "Every trip starts here", value: "$30.00" },
    { label: "Distance", detail: "Free within El Paso County · $1.75/mi beyond", value: "by route", mono: true },
    { label: "Extra Stops", detail: "Each intermediate stop on your route", value: "$5.00", suffix: "/ stop", accent: true },
    { label: "Driver Wait Time", detail: "On-site wait, per hour", value: "$20.00", suffix: "/ hr" },
    { label: "Teller County", detail: "Woodland Park, Cripple Creek, Divide", value: "$15.00", suffix: "surcharge" },
];

export default function FairnessPage() {
    return (
        <main className="min-h-screen bg-[#0a0a0a] px-6 pb-20 pt-24 lg:pt-12">
            <div className="mx-auto max-w-3xl">
                <header className="mb-10">
                    <span className="font-mono text-xs font-bold uppercase tracking-widest text-cyan-400">SummitOS</span>
                    <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">Fairness Engine v5.0</h1>
                    <p className="mt-3 leading-relaxed text-slate-400">
                        Pricing emerges from your actual route — not a menu. Every dollar is earned by real distance,
                        real time, and real complexity.
                    </p>
                </header>

                <div className="rounded-3xl border border-white/10 bg-[#111318] p-2">
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

                <p className="mt-8 border-t border-white/5 pt-6 font-mono text-[0.65rem] leading-relaxed text-slate-600">
                    ROUTE CALCULATED VIA GOOGLE DISTANCE MATRIX. NO SURGE PRICING. NO HIDDEN FEES. DETERMINISTIC —
                    SAME ROUTE ALWAYS YIELDS SAME PRICE.
                </p>
            </div>
        </main>
    );
}
