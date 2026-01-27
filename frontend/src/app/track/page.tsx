"use client";

import Navbar from "@/components/Navbar";
import dynamic from "next/dynamic";

const LiveMap = dynamic(() => import("../../components/LiveMap"), {
    ssr: false,
    loading: () => <div className="h-screen flex items-center justify-center text-blue-400">CONNECTING TO TESLA GPS...</div>
});

export default function TrackPage() {
    return (
        <main className="min-h-screen bg-black">
            <Navbar />
            <div className="h-screen w-full relative">
                <LiveMap className="h-full w-full" />

                {/* Overlay Info */}
                <div className="absolute top-24 left-1/2 -translate-x-1/2 bg-black/80 backdrop-blur-md px-6 py-3 rounded-full border border-white/10 z-[1000] text-center">
                    <h1 className="text-white font-bold tracking-widest text-sm mb-1 uppercase">Live Vehicle Telemetry</h1>
                    <p className="text-xs text-gray-400">Real-time GPS tracking via Tessie API</p>
                </div>
            </div>
        </main>
    );
}
