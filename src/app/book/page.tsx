import BookingEngine from "@/components/BookingEngine";

export default function BookPage() {
    return (
        <main className="pt-24 min-h-screen bg-[var(--background)] text-white">
            <div className="container mx-auto px-6">
                <div className="text-center mb-12">
                    <h1 className="text-4xl font-bold mb-4">Reserve Your Ride</h1>
                    <p className="text-xl text-gray-400">Simple pricing. Instant confirmation. Zero surge.</p>
                </div>

                {/* Booking Engine with Calendar */}
                <div className="max-w-5xl mx-auto">
                    <div className="bg-[#0a0a0a]/80 backdrop-blur-2xl border border-white/10 rounded-[3rem] p-1 shadow-2xl shadow-black/80">
                        <div className="bg-[#111]/50 rounded-[2.8rem] p-8 lg:p-12 border border-white/5">
                            <BookingEngine />
                        </div>
                    </div>
                </div>
            </div>
        </main>
    );
}
