import { useState, useEffect, useMemo, useCallback } from "react";
import { GoogleMap, useJsApiLoader, InfoWindow, MarkerF, Polyline, CircleF } from "@react-google-maps/api";
import { AlertCircle, RefreshCw, Car, User, Calendar, Navigation, Activity, Flame } from "lucide-react";
import { apiGet } from "../lib/apiClient";

// Colorado Springs Center
const defaultCenter = {
    lat: 38.8339,
    lng: -104.8214
};

const mapContainerStyle = {
    width: "100%",
    height: "100%"
};

// Dark Mode Styling matching Dashboard Void Aesthetic
const darkMapStyles = [
    { elementType: "geometry", stylers: [{ color: "#090d16" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#090d16" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#94a3b8" }] },
    {
        featureType: "administrative.locality",
        elementType: "labels.text.fill",
        stylers: [{ color: "#38bdf8" }],
    },
    {
        featureType: "road",
        elementType: "geometry",
        stylers: [{ color: "#1e293b" }],
    },
    {
        featureType: "road",
        elementType: "geometry.stroke",
        stylers: [{ color: "#0f172a" }],
    },
    {
        featureType: "road",
        elementType: "labels.text.fill",
        stylers: [{ color: "#64748b" }],
    },
    {
        featureType: "road.highway",
        elementType: "geometry",
        stylers: [{ color: "#334155" }],
    },
    {
        featureType: "water",
        elementType: "geometry",
        stylers: [{ color: "#020617" }],
    },
];

export interface TripYieldFeature {
    type: "Feature";
    geometry: {
        type: "Point" | "LineString";
        coordinates: [number, number] | [number, number][]; // [lng, lat] or [[lng, lat], [lng, lat]]
    };
    properties: {
        ride_id: string;
        trip_type: string;
        timestamp_start: string | null;
        gross: number;
        distance_mi: number;
        duration_min: number;
        energy_used_kwh: number | null;
        energy_cost: number;
        wear_cost: number;
        net: number;
        net_per_hour: number;
        is_estimated: boolean;
    };
}

interface FeatureCollectionResponse {
    type: string;
    features: TripYieldFeature[];
    metadata?: Record<string, unknown>;
}

export type TripTypeFilter = "all" | "uber" | "private";
export type ViewMode = "corridors" | "pickups" | "heatmap";

// Continuous Yield Color Scale (Loss = Crimson, Low = Indigo, Med = Blue, High = Cyan/Teal, Peak = Emerald)
function getYieldColor(netPerHour: number): string {
    if (netPerHour <= 0) return "#ef4444"; // Warning Crimson for Loss
    if (netPerHour < 30) return "#6366f1"; // Indigo
    if (netPerHour < 55) return "#3b82f6"; // Blue
    if (netPerHour < 85) return "#06b6d4"; // Cyan
    return "#10b981"; // Emerald for peak yield
}

interface Props {
    className?: string;
}

export default function TripYieldMap({ className = "" }: Props) {
    const [trips, setTrips] = useState<TripYieldFeature[]>([]);
    const [loading, setLoading] = useState<boolean>(true);

    // View & Filter states
    const [viewMode, setViewMode] = useState<ViewMode>("corridors");
    const [tripFilter, setTripFilter] = useState<TripTypeFilter>("all");
    const [dateRange, setDateRange] = useState<string>("all");
    const [selectedTrip, setSelectedTrip] = useState<TripYieldFeature | null>(null);
    const [hoveredTripId, setHoveredTripId] = useState<string | null>(null);

    // Unvalidated rate parameters
    const [energyRate] = useState<number>(0.45);
    const [wearRate] = useState<number>(0.13);

    const googleMapsApiKey = 
        (import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined) ||
        (import.meta.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY as string | undefined) ||
        "";

    const [libraries] = useState<("places" | "geometry" | "drawing")[]>([
        "places"
    ]);

    const { isLoaded, loadError } = useJsApiLoader({
        id: "google-map-trip-yield-dash",
        googleMapsApiKey,
        libraries,
    });

    const fetchTripData = useCallback(async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            params.append("format", viewMode === "corridors" ? "corridors" : "points");
            if (tripFilter !== "all") params.append("trip_type", tripFilter);
            if (energyRate) params.append("energy_rate", energyRate.toString());
            if (wearRate) params.append("wear_rate", wearRate.toString());

            if (dateRange === "7d") {
                const d = new Date();
                d.setDate(d.getDate() - 7);
                params.append("from", d.toISOString().split("T")[0]);
            } else if (dateRange === "30d") {
                const d = new Date();
                d.setDate(d.getDate() - 30);
                params.append("from", d.toISOString().split("T")[0]);
            } else if (dateRange === "90d") {
                const d = new Date();
                d.setDate(d.getDate() - 90);
                params.append("from", d.toISOString().split("T")[0]);
            }

            const data = await apiGet<FeatureCollectionResponse>(`/analytics/trip-yield?${params.toString()}`);
            setTrips(data.features || []);
        } catch (err: unknown) {
            console.error("Failed to fetch trip yield data:", err);
        } finally {
            setLoading(false);
        }
    }, [viewMode, tripFilter, dateRange, energyRate, wearRate]);

    useEffect(() => {
        fetchTripData();
    }, [fetchTripData]);

    const stats = useMemo(() => {
        if (!trips.length) return null;
        let totalGross = 0;
        let totalNet = 0;
        let totalEngagedMinutes = 0;
        let totalDistance = 0;
        let lossCount = 0;
        let estCount = 0;

        trips.forEach((t) => {
            const p = t.properties;
            totalGross += p.gross;
            totalNet += p.net;
            totalEngagedMinutes += p.duration_min;
            totalDistance += p.distance_mi;
            if (p.net_per_hour <= 0) lossCount++;
            if (p.is_estimated) estCount++;
        });

        const avgYield = totalEngagedMinutes > 0 ? (totalNet / (totalEngagedMinutes / 60)) : 0;

        return {
            count: trips.length,
            totalGross,
            totalNet,
            totalDistance,
            avgYield,
            lossCount,
            estCount,
        };
    }, [trips]);

    if (loadError) {
        return (
            <div className="bg-red-950/40 border border-red-800 text-red-300 p-6 rounded-xl text-center">
                <AlertCircle className="w-8 h-8 mx-auto mb-2 text-red-500" />
                <h3 className="font-semibold text-lg">Google Maps Load Error</h3>
                <p className="text-sm mt-1 text-red-400">{loadError.message}</p>
            </div>
        );
    }

    return (
        <div className={`flex flex-col h-full bg-[#030712] text-slate-100 rounded-xl overflow-hidden border border-slate-800 shadow-2xl ${className}`}>
            {/* Header & Controls Panel */}
            <div className="p-4 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 flex flex-wrap items-center justify-between gap-4 z-10">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-cyan-950/80 border border-cyan-700/60 rounded-lg text-cyan-400 shadow-inner">
                        <Navigation className="w-5 h-5" />
                    </div>
                    <div>
                        <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                            Commercial Route & Heatmap Console
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono">
                                Verified Telemetry
                            </span>
                        </h2>
                        <p className="text-xs text-slate-400">
                            {viewMode === "heatmap" ? "Density & yield intensity heatmap" : "Real commercial routes color-coded by net $/engaged hour"}
                        </p>
                    </div>
                </div>

                {/* Filter & Mode Controls */}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                    {/* View Mode Toggle: Corridors vs Pickups vs Heatmap */}
                    <div className="flex items-center bg-slate-950 rounded-lg p-1 border border-slate-800">
                        <button
                            onClick={() => setViewMode("corridors")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1.5 transition-all ${
                                viewMode === "corridors" ? "bg-slate-800 text-cyan-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <Navigation className="w-3.5 h-3.5" />
                            Corridors
                        </button>
                        <button
                            onClick={() => setViewMode("pickups")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1.5 transition-all ${
                                viewMode === "pickups" ? "bg-slate-800 text-cyan-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <Activity className="w-3.5 h-3.5" />
                            Pickups
                        </button>
                        <button
                            onClick={() => setViewMode("heatmap")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1.5 transition-all ${
                                viewMode === "heatmap" ? "bg-slate-800 text-amber-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <Flame className="w-3.5 h-3.5" />
                            Heatmap
                        </button>
                    </div>

                    {/* Trip Type Toggle */}
                    <div className="flex items-center bg-slate-950 rounded-lg p-1 border border-slate-800">
                        <button
                            onClick={() => setTripFilter("all")}
                            className={`px-2.5 py-1 rounded font-medium transition-all ${
                                tripFilter === "all" ? "bg-slate-800 text-cyan-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            All ({trips.length})
                        </button>
                        <button
                            onClick={() => setTripFilter("private")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1 transition-all ${
                                tripFilter === "private" ? "bg-slate-800 text-cyan-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <User className="w-3 h-3" />
                            Private
                        </button>
                        <button
                            onClick={() => setTripFilter("uber")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1 transition-all ${
                                tripFilter === "uber" ? "bg-slate-800 text-cyan-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <Car className="w-3 h-3" />
                            Uber
                        </button>
                    </div>

                    {/* Date Range Selector */}
                    <div className="flex items-center bg-slate-950 rounded-lg p-1 border border-slate-800 text-slate-400">
                        <Calendar className="w-3.5 h-3.5 ml-1.5 mr-1 text-slate-400" />
                        <select
                            value={dateRange}
                            onChange={(e) => setDateRange(e.target.value)}
                            aria-label="Filter trips by date range"
                            className="bg-transparent text-slate-200 border-none outline-none pr-2 py-0.5 cursor-pointer font-medium"
                        >
                            <option value="all" className="bg-slate-900 text-slate-100">All Time</option>
                            <option value="90d" className="bg-slate-900 text-slate-100">Last 90 Days</option>
                            <option value="30d" className="bg-slate-900 text-slate-100">Last 30 Days</option>
                            <option value="7d" className="bg-slate-900 text-slate-100">Last 7 Days</option>
                        </select>
                    </div>

                    {/* Refresh Button */}
                    <button
                        onClick={fetchTripData}
                        disabled={loading}
                        aria-label="Refresh trip yield data"
                        className="p-1.5 bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-lg text-slate-400 hover:text-cyan-400 transition-all disabled:opacity-50"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
                    </button>
                </div>
            </div>

            {/* Unvalidated Parameters Notice Banner */}
            <div className="px-4 py-2 bg-amber-950/25 border-b border-amber-900/40 flex items-center justify-between text-[11px] text-amber-300/90">
                <div className="flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>
                        <strong className="text-amber-300 font-semibold">Cost Parameters (Unvalidated):</strong> Energy at <strong>${energyRate.toFixed(2)}/kWh</strong> | Wear at <strong>${wearRate.toFixed(2)}/mi</strong>
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    {stats && (
                        <span className="font-mono text-slate-300">
                            Avg Net Yield: <strong className="text-cyan-400">${stats.avgYield.toFixed(2)}/hr</strong>
                        </span>
                    )}
                    {stats && stats.estCount > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                            {stats.estCount} Estimated kWh
                        </span>
                    )}
                </div>
            </div>

            {/* Map Canvas */}
            <div className="relative flex-1 min-h-[480px]">
                {isLoaded ? (
                    <GoogleMap
                        mapContainerStyle={mapContainerStyle}
                        center={defaultCenter}
                        zoom={11}
                        options={{
                            styles: darkMapStyles,
                            disableDefaultUI: true,
                            zoomControl: true,
                            clickableIcons: false,
                        }}
                    >
                        {/* 1. CORRIDOR LINES MODE (POLYLINES) */}
                        {viewMode === "corridors" && trips.map((trip) => {
                            const p = trip.properties;
                            if (trip.geometry.type !== "LineString") return null;
                            const coords = trip.geometry.coordinates as [number, number][];
                            if (!coords || coords.length < 2) return null;

                            const path = [
                                { lat: coords[0][1], lng: coords[0][0] },
                                { lat: coords[1][1], lng: coords[1][0] },
                            ];

                            const strokeColor = getYieldColor(p.net_per_hour);
                            const isHovered = hoveredTripId === p.ride_id;
                            const isSelected = selectedTrip?.properties.ride_id === p.ride_id;

                            return (
                                <Polyline
                                    key={p.ride_id}
                                    path={path}
                                    options={{
                                        strokeColor: isSelected ? "#ffffff" : strokeColor,
                                        strokeOpacity: isHovered || isSelected ? 0.95 : (p.is_estimated ? 0.6 : 0.8),
                                        strokeWeight: isSelected ? 5 : (isHovered ? 4 : (p.trip_type === "Private" ? 3.5 : 2.5)),
                                        icons: [
                                            {
                                                icon: {
                                                    path: 1, // google.maps.SymbolPath.FORWARD_CLOSED_ARROW
                                                    scale: 2.5,
                                                    strokeColor: isSelected ? "#ffffff" : strokeColor,
                                                    fillColor: strokeColor,
                                                    fillOpacity: 1,
                                                },
                                                offset: "65%",
                                            },
                                        ],
                                    }}
                                    onClick={() => setSelectedTrip(trip)}
                                    onMouseOver={() => setHoveredTripId(p.ride_id)}
                                    onMouseOut={() => setHoveredTripId(null)}
                                />
                            );
                        })}

                        {/* 2. PICKUPS MODE (MARKERS) */}
                        {viewMode === "pickups" && trips.map((trip) => {
                            const p = trip.properties;
                            const coords = (
                                trip.geometry.type === "Point"
                                    ? (trip.geometry.coordinates as [number, number])
                                    : (trip.geometry.coordinates as [number, number][])[0]
                            );
                            if (!coords) return null;

                            const markerPos = { lat: coords[1], lng: coords[0] };
                            const markerColor = getYieldColor(p.net_per_hour);

                            const markerIcon: google.maps.Symbol = {
                                path: 0, // google.maps.SymbolPath.CIRCLE
                                scale: p.is_estimated ? 5.5 : 6.5,
                                fillColor: markerColor,
                                fillOpacity: p.is_estimated ? 0.6 : 0.9,
                                strokeColor: p.net_per_hour <= 0 ? "#fca5a5" : (p.is_estimated ? "#cbd5e1" : "#ffffff"),
                                strokeOpacity: 1,
                                strokeWeight: p.is_estimated ? 1.5 : 2,
                            };

                            return (
                                <MarkerF
                                    key={p.ride_id}
                                    position={markerPos}
                                    icon={markerIcon}
                                    onClick={() => setSelectedTrip(trip)}
                                />
                            );
                        })}

                        {/* 3. HEATMAP MODE (Density Glow via native Circle overlays) */}
                        {viewMode === "heatmap" && trips.map((trip) => {
                            const p = trip.properties;
                            const coords = (
                                trip.geometry.type === "Point"
                                    ? (trip.geometry.coordinates as [number, number])
                                    : (trip.geometry.coordinates as [number, number][])[0]
                            );
                            if (!coords) return null;

                            const center = { lat: coords[1], lng: coords[0] };
                            const color = getYieldColor(p.net_per_hour);

                            return (
                                <CircleF
                                    key={`heat-${p.ride_id}`}
                                    center={center}
                                    radius={650}
                                    options={{
                                        fillColor: color,
                                        fillOpacity: 0.18,
                                        strokeColor: color,
                                        strokeOpacity: 0.45,
                                        strokeWeight: 1,
                                        clickable: true,
                                    }}
                                    onClick={() => setSelectedTrip(trip)}
                                />
                            );
                        })}

                        {/* Interactive Tooltip Card */}
                        {selectedTrip && (
                            <InfoWindow
                                position={(() => {
                                    if (selectedTrip.geometry.type === "LineString") {
                                        const coords = selectedTrip.geometry.coordinates as [number, number][];
                                        return {
                                            lat: (coords[0][1] + coords[1][1]) / 2,
                                            lng: (coords[0][0] + coords[1][0]) / 2,
                                        };
                                    }
                                    const coords = selectedTrip.geometry.coordinates as [number, number];
                                    return { lat: coords[1], lng: coords[0] };
                                })()}
                                onCloseClick={() => setSelectedTrip(null)}
                            >
                                <div className="p-2 text-slate-900 max-w-[240px] font-sans">
                                    <div className="flex items-center justify-between border-b pb-1 mb-1.5">
                                        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-700">
                                            {selectedTrip.properties.trip_type} Route
                                        </span>
                                        <span className="text-[10px] font-mono text-slate-500">
                                            {selectedTrip.properties.timestamp_start?.split("T")[0]}
                                        </span>
                                    </div>

                                    <div className="flex items-baseline justify-between mb-2">
                                        <div className="text-xl font-extrabold font-mono text-slate-900">
                                            ${selectedTrip.properties.net_per_hour.toFixed(2)}
                                            <span className="text-xs font-normal text-slate-500">/hr</span>
                                        </div>
                                        <span
                                            className={`text-[10px] font-bold px-1.5 py-0.5 rounded font-mono ${
                                                selectedTrip.properties.net_per_hour > 0
                                                    ? "bg-emerald-100 text-emerald-800"
                                                    : "bg-red-100 text-red-800"
                                            }`}
                                        >
                                            Net ${selectedTrip.properties.net.toFixed(2)}
                                        </span>
                                    </div>

                                    <div className="grid grid-cols-2 gap-1 text-[11px] text-slate-600 bg-slate-50 p-1.5 rounded border border-slate-200 mb-1">
                                        <div>Gross: <strong>${selectedTrip.properties.gross.toFixed(2)}</strong></div>
                                        <div>Duration: <strong>{selectedTrip.properties.duration_min}m</strong></div>
                                        <div>Distance: <strong>{selectedTrip.properties.distance_mi.toFixed(1)}mi</strong></div>
                                        <div>Energy: <strong>{selectedTrip.properties.energy_used_kwh ? `${selectedTrip.properties.energy_used_kwh.toFixed(1)} kWh` : "Est"}</strong></div>
                                    </div>

                                    {selectedTrip.properties.is_estimated && (
                                        <p className="text-[9px] text-amber-700 italic mt-1">
                                            * Energy estimated using vehicle averages
                                        </p>
                                    )}
                                </div>
                            </InfoWindow>
                        )}
                    </GoogleMap>
                ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-slate-500">
                        <div className="w-8 h-8 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin mb-3"></div>
                        <span className="text-xs uppercase tracking-widest font-mono text-cyan-400">Loading Map Console...</span>
                    </div>
                )}
            </div>

            {/* Legend & Telemetry Footer */}
            <div className="p-3 bg-slate-950 border-t border-slate-800 flex flex-wrap items-center justify-between text-xs text-slate-400 gap-2">
                <div className="flex items-center gap-4">
                    <span className="font-mono text-[11px] uppercase tracking-wider text-slate-500">Yield Scale:</span>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444]" />
                        <span>Loss (&le;$0)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#6366f1]" />
                        <span>&lt;$30/hr</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#3b82f6]" />
                        <span>$30-$55</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#06b6d4]" />
                        <span>$55-$85</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" />
                        <span>&gt;$85/hr</span>
                    </div>
                </div>

                <div className="flex items-center gap-3 text-[11px]">
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-cyan-400 inline-block" /> Private Route
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-3 h-0.5 bg-indigo-400 inline-block" /> Uber Route
                    </span>
                </div>
            </div>
        </div>
    );
}
