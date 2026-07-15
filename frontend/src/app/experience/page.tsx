import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
    title: "The Experience | COS Tesla",
    description:
        "The executive standard for private transport in Colorado Springs — local knowledge, premium vehicle, transparent pricing.",
};

/* Relocated marketing content from the old homepage (dark redesign).
   The homepage is now the live map; this is where the story lives. */
const CABIN_FEATURES = [
    { icon: "🌡️", title: "Climate Control", body: "Too hot? Too cold? Adjust the rear seat heaters instantly from your personal dashboard." },
    { icon: "🧭", title: "Live Telemetry", body: "Watch your altitude climb as we ascend Ute Pass. Monitor speed and conditions in real time." },
    { icon: "🔒", title: "Secure Access", body: "Each trip generates a unique session token. Your controls expire safely when you drop off." },
] as const;

export default function ExperiencePage() {
    return (
        <main className="min-h-screen bg-[#0a0a0a] text-slate-200">
            {/* Hero */}
            <section className="px-6 pb-16 pt-24 lg:pt-20">
                <div className="mx-auto max-w-4xl">
                    <h2 className="mb-6 flex items-center gap-3 text-xs font-bold uppercase tracking-[0.4em] text-cyan-400">
                        <span className="h-[1px] w-8 bg-cyan-400" />
                        El Paso County • Colorado
                    </h2>
                    <h1 className="text-5xl font-bold leading-tight tracking-tighter text-white lg:text-7xl">
                        COS <br />
                        <span className="bg-gradient-to-r from-white to-slate-500 bg-clip-text text-transparent">TESLA.</span>
                    </h1>
                    <p className="mt-4 font-mono text-xs uppercase tracking-[0.3em] text-cyan-400">Powered by SummitOS</p>
                    <p className="mt-10 max-w-lg border-l-2 border-white/10 pl-6 text-2xl font-light leading-relaxed text-slate-300">
                        The executive standard for private transport. Precision pricing. Zero surge. Driven by{" "}
                        <strong className="font-semibold text-white">Technology</strong>.
                    </p>
                </div>
            </section>

            {/* Local knowledge */}
            <section className="border-t border-white/5 px-6 py-20">
                <div className="mx-auto max-w-4xl">
                    <div className="flex items-center gap-4">
                        <span className="select-none text-6xl font-thin text-white/10">01</span>
                        <h2 className="text-3xl font-bold text-white lg:text-4xl">
                            Local Knowledge.
                            <br />
                            Global Tech.
                        </h2>
                    </div>
                    <p className="mt-6 max-w-2xl text-lg font-light leading-relaxed text-slate-400">
                        Driving El Paso County isn&rsquo;t just about GPS; it&rsquo;s about knowing the terrain. From the icy
                        switchbacks of <strong className="font-semibold text-white">Broadmoor Bluffs</strong> to the unpaved
                        expanses of <strong className="font-semibold text-white">Black Forest</strong>, we combine 20 years of
                        local IT expertise with our advanced AWD fleet.
                    </p>
                    <div className="mt-10 grid max-w-md grid-cols-2 gap-8 border-t border-white/5 pt-8">
                        <div>
                            <div className="mb-2 text-3xl font-bold text-white">20+</div>
                            <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">Years IT Exp</div>
                        </div>
                        <div>
                            <div className="mb-2 text-3xl font-bold text-white">100%</div>
                            <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">Safety Rating</div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Cabin experience */}
            <section className="border-t border-white/5 px-6 py-20">
                <div className="mx-auto max-w-5xl">
                    <div className="mx-auto mb-14 max-w-2xl text-center">
                        <h2 className="text-3xl font-bold text-white lg:text-4xl">
                            Your Private <span className="text-cyan-400">Command Center</span>.
                        </h2>
                        <p className="mt-4 text-lg font-light text-slate-400">
                            Control your environment from your phone. No apps to install. Just a secure link.
                        </p>
                    </div>

                    <div className="grid gap-6 lg:grid-cols-3">
                        {CABIN_FEATURES.map((f) => (
                            <div
                                key={f.title}
                                className="group rounded-3xl border border-white/10 bg-[#111318] p-8 transition-colors hover:border-cyan-500/30"
                            >
                                <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/10 text-2xl transition-transform group-hover:scale-110">
                                    {f.icon}
                                </div>
                                <h3 className="mb-3 text-xl font-bold text-white">{f.title}</h3>
                                <p className="text-sm leading-relaxed text-slate-400">{f.body}</p>
                            </div>
                        ))}
                    </div>

                    <div className="mt-14 text-center">
                        <Link
                            href="/book/"
                            className="inline-flex items-center gap-3 rounded-xl bg-cyan-500 px-8 py-4 text-lg font-bold text-black transition-colors hover:bg-cyan-400"
                        >
                            Book a Ride <span className="text-xl">&rarr;</span>
                        </Link>
                    </div>
                </div>
            </section>
        </main>
    );
}
