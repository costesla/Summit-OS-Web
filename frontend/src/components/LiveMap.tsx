"use client";

import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, useMap, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Custom Car Icon (or standard if failed, but let's try to style it distinct)
const carIcon = L.icon({
    iconUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png",
    shadowSize: [41, 41]
});

function MapRecenter({ lat, lng }: { lat: number, lng: number }) {
    const map = useMap();
    useEffect(() => {
        map.setView([lat, lng], map.getZoom());
    }, [lat, lng, map]);
    return null;
}

// Type for the Position Data
export interface PosData {
    lat: number;
    long: number;
    speed: number;
    heading: number;
    privacy?: boolean;
    status?: string;
}

export default function LiveMap({ className = "h-[600px]", overridePos }: { className?: string, overridePos?: PosData }) {
    const [pos, setPos] = useState<PosData | null>(null);
    const [error, setError] = useState("");

    // Broadcast Channel Ref
    const channelRef = useState(() => typeof window !== 'undefined' ? new BroadcastChannel('live_map_sync') : null)[0];

    // Popout Handler
    const handlePopout = () => {
        window.open('/live-map-popout', 'LiveMapPopout', 'width=600,height=600,menubar=no,toolbar=no,location=no,status=no');
    };

    const fetchLocation = async () => {
        if (overridePos) return; // Don't fetch if controlled

        try {
            // Direct fetch to Azure Function Backend
            const res = await fetch('https://summitos-api.azurewebsites.net/api/vehicle-location');
            if (res.ok) {
                const data = await res.json();
                setPos(data);
                setError("");

                // BROADCAST STATE
                if (channelRef) {
                    channelRef.postMessage({ type: 'SYNC', payload: data });
                }
            } else {
                console.log("Tracking update failed");
            }
        } catch (e) {
            console.error(e);
            setError("Connection lost");
        }
    };

    useEffect(() => {
        // If controlled, sync state immediately
        if (overridePos) {
            setPos(overridePos);
            return;
        }

        fetchLocation(); // Initial
        const interval = setInterval(fetchLocation, 20000); // 20s poll
        return () => clearInterval(interval);
    }, [overridePos]); // Dependency on overridePos

    // Clean up channel on unmount
    useEffect(() => {
        return () => {
            if (channelRef) channelRef.close();
        };
    }, []);

    if (error && !pos) return <div className="text-red-400 text-center p-10">Tracker Offline</div>;
    if (!pos) return <div className="text-cyan-400 text-center p-10 animate-pulse">Connecting to COS Tesla Fleet GPS...</div>;

    // Privacy Shield Mode
    if (pos.privacy) {
        return (
            <div className={`${className} w-full rounded-xl overflow-hidden shadow-2xl border border-white/10 relative z-0 bg-black flex flex-col items-center justify-center text-center p-6`}>
                <div className="relative">
                    <div className="absolute inset-0 bg-blue-500 blur-xl opacity-20 rounded-full animate-pulse"></div>
                    <div className="relative text-6xl mb-4">🛡️</div>
                </div>
                <h3 className="text-2xl font-bold text-white mb-2">PRIVACY MODE</h3>
                <p className="text-gray-400 max-w-xs mx-auto">
                    {pos.status || "Vehicle is currently docked."}
                </p>
                <div className="mt-6 flex items-center gap-2 text-xs text-blue-500 font-mono">
                    <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                    </span>
                    SYSTEM READY • WAITING FOR TRIP
                </div>

                {/* Popout Button (Only show if NOT overridden/popout itself) */}
                {!overridePos && (
                    <button
                        onClick={handlePopout}
                        className="absolute top-4 right-4 text-xs text-gray-500 hover:text-white transition-colors border border-white/10 p-2 rounded bg-black/50 backdrop-blur"
                    >
                        ⬈ Popout
                    </button>
                )}
            </div>
        );
    }

    // Active Map Mode
    return (
        <div className={`${className} w-full rounded-xl overflow-hidden shadow-2xl border border-blue-500/30 relative z-0`}>
            {/* Popout Button (Active Mode) */}
            {!overridePos && (
                <button
                    onClick={handlePopout}
                    className="absolute top-20 right-4 z-[9999] text-[10px] uppercase font-bold text-cyan-500 hover:text-white transition-colors border border-cyan-500/30 p-1.5 rounded bg-black/80 backdrop-blur shadow-lg"
                >
                    ⬈ Popout
                </button>
            )}

            <div className="absolute top-4 right-4 z-[9999] bg-black/80 text-white px-4 py-2 rounded-lg backdrop-blur-md border border-white/10">
                <p className="text-sm font-bold text-blue-400">⚡ THOR LIVE</p>
                <div className="flex gap-4 text-xs mt-1">
                    <span>🚀 {pos.speed ? Math.round(pos.speed) : 0} mph</span>
                    <span>🧭 {pos.heading}°</span>
                </div>
            </div>

            <MapContainer
                center={[pos.lat, pos.long]}
                zoom={14}
                style={{ height: "100%", width: "100%" }}
                zoomControl={false}
            >
                <TileLayer
                    attribution='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                />
                <Marker position={[pos.lat, pos.long]} icon={carIcon}>
                    <Popup>
                        Current Location
                    </Popup>
                </Marker>
                <MapRecenter lat={pos.lat} lng={pos.long} />
            </MapContainer>
        </div>
    );
}
