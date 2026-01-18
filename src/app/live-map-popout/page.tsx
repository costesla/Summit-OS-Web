"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

// Import LiveMap dynamically to avoid SSR issues with Leaflet
const LiveMap = dynamic(() => import("@/components/LiveMap"), {
    ssr: false,
    loading: () => <div className="text-blue-500 p-10">Loading Map Engine...</div>
});

export default function LiveMapPopoutPage() {
    const [state, setState] = useState<any>(null);

    useEffect(() => {
        const channel = new BroadcastChannel('live_map_sync');

        channel.onmessage = (event) => {
            if (event.data.type === 'SYNC') {
                setState(event.data.payload);
            }
        };

        return () => {
            channel.close();
        };
    }, []);

    if (!state) {
        return (
            <div className="w-screen h-screen bg-black flex flex-col items-center justify-center text-white">
                <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full mb-4"></div>
                <p className="text-xs uppercase tracking-widest text-blue-500">Connecting to Dashboard...</p>
            </div>
        );
    }

    return (
        <div className="w-screen h-screen bg-black overflow-hidden relative">
            {/* 
                We use LiveMap but inject the state we received from the main window.
                overridePos allows us to drive the map from the main window's data.
            */}
            <LiveMap
                className="h-full w-full rounded-none border-none"
                overridePos={state}
            />

            {/* Sync Indicator */}
            <div className="absolute bottom-4 left-4 z-[9999] pointer-events-none">
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_#00ff00]"></div>
                    <span className="text-[10px] font-mono text-green-500 uppercase tracking-widest">Live Mirror Active</span>
                </div>
            </div>
        </div>
    );
}
