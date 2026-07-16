import BookingEngine from "@/components/BookingEngine";

export default function BookPage() {
    return (
        /* sos-form scopes the dark input styling (globals.css) to this subtree,
           so legacy light pages keep their own form look untouched.
           NOTE: this previously used bg-[var(--background)] — a variable that
           is never defined, so it resolved to transparent and let the light
           body show through behind text-white (invisible heading). */
        <main className="sos-form min-h-screen bg-sos-dark pt-24 text-sos-main lg:pt-12">
            <div className="container mx-auto px-6">
                <div className="mb-12 text-center">
                    <h1 className="mb-4 text-4xl font-bold tracking-tight text-sos-main">Reserve Your Ride</h1>
                    <p className="text-xl text-sos-dim">Simple pricing. Instant confirmation. Zero surge.</p>
                </div>

                {/* Booking Engine with Calendar */}
                <div className="mx-auto max-w-5xl">
                    <div className="rounded-[3rem] border border-sos-border bg-sos-dark/80 p-1 shadow-2xl shadow-black/80 backdrop-blur-2xl">
                        <div className="rounded-[2.8rem] border border-white/5 bg-sos-surface/50 p-8 lg:p-12">
                            <BookingEngine />
                        </div>
                    </div>
                </div>
            </div>
        </main>
    );
}
