import { useState, useEffect, useMemo, useCallback } from "react";
import { GoogleMap, useJsApiLoader, InfoWindow, MarkerF, CircleF, PolygonF } from "@react-google-maps/api";
import { AlertCircle, RefreshCw, Car, User, Calendar, Activity, Flame, DollarSign, MapPin } from "lucide-react";
import { getTripYieldData } from "@/lib/api";

// Colorado Springs Center
const defaultCenter = {
    lat: 38.8650,
    lng: -104.7900
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

interface ZoneConfig {
    id: string;
    name: string;
    shortName: string;
    description: string;
    center: { lat: number; lng: number };
    bounds: { north: number; south: number; east: number; west: number };
    paths: { lat: number; lng: number }[];
}

const CS_ZONES: ZoneConfig[] = [
    {
        id: "northgate_monument",
        name: "Northgate / Flying Horse / Monument",
        shortName: "Northgate / Monument",
        description: "High-ticket residential, airport shuttles, long-haul private & Uber Black",
        center: { lat: 39.015, lng: -104.825 },
        bounds: { north: 39.12, south: 38.98, east: -104.70, west: -104.92 },
        paths: [
            { lat: 39.12, lng: -104.92 },
            { lat: 39.12, lng: -104.70 },
            { lat: 38.98, lng: -104.70 },
            { lat: 38.98, lng: -104.92 },
        ]
    },
    {
        id: "briargate_cordera",
        name: "Briargate / Pine Creek / Cordera",
        shortName: "Briargate / Cordera",
        description: "Affluent suburban corridor, frequent high-ticket business & airport transfers",
        center: { lat: 38.948, lng: -104.775 },
        bounds: { north: 38.98, south: 38.92, east: -104.70, west: -104.85 },
        paths: [
            { lat: 38.98, lng: -104.85 },
            { lat: 38.98, lng: -104.70 },
            { lat: 38.92, lng: -104.70 },
            { lat: 38.92, lng: -104.85 },
        ]
    },
    {
        id: "broadmoor_sw",
        name: "The Broadmoor / Cheyenne Mtn / SW",
        shortName: "The Broadmoor / SW",
        description: "Luxury resort & executive residential; highest fare averages & VIP transfers",
        center: { lat: 38.790, lng: -104.855 },
        bounds: { north: 38.82, south: 38.74, east: -104.80, west: -104.92 },
        paths: [
            { lat: 38.82, lng: -104.92 },
            { lat: 38.82, lng: -104.80 },
            { lat: 38.74, lng: -104.80 },
            { lat: 38.74, lng: -104.92 },
        ]
    },
    {
        id: "north_nevada_gog",
        name: "North Nevada / Garden of Gods / UCCS",
        shortName: "North Nevada / GOG",
        description: "Major commercial spine, tech campuses & hotel clusters; steady mid-to-high ticket",
        center: { lat: 38.895, lng: -104.845 },
        bounds: { north: 38.92, south: 38.87, east: -104.80, west: -104.90 },
        paths: [
            { lat: 38.92, lng: -104.90 },
            { lat: 38.92, lng: -104.80 },
            { lat: 38.87, lng: -104.80 },
            { lat: 38.87, lng: -104.90 },
        ]
    },
    {
        id: "downtown_occ",
        name: "Downtown / Old Colorado City",
        shortName: "Downtown / OCC",
        description: "Dense dining, nightlife & tourist core; high frequency, short turns, moderate fares",
        center: { lat: 38.845, lng: -104.835 },
        bounds: { north: 38.87, south: 38.82, east: -104.80, west: -104.88 },
        paths: [
            { lat: 38.87, lng: -104.88 },
            { lat: 38.87, lng: -104.80 },
            { lat: 38.82, lng: -104.80 },
            { lat: 38.82, lng: -104.88 },
        ]
    },
    {
        id: "powers_corridor",
        name: "Powers Corridor / Stetson Hills / Cimarron",
        shortName: "Powers Corridor",
        description: "Suburban retail corridor, family commutes, mid-distance trips to airport & downtown",
        center: { lat: 38.880, lng: -104.730 },
        bounds: { north: 38.94, south: 38.83, east: -104.68, west: -104.78 },
        paths: [
            { lat: 38.94, lng: -104.78 },
            { lat: 38.94, lng: -104.68 },
            { lat: 38.83, lng: -104.68 },
            { lat: 38.83, lng: -104.78 },
        ]
    },
    {
        id: "airport_peterson",
        name: "COS Airport / Peterson Space Base",
        shortName: "COS Airport / SFB",
        description: "Terminal pickups & military personnel; consistent medium-to-high ticket fares",
        center: { lat: 38.805, lng: -104.705 },
        bounds: { north: 38.84, south: 38.77, east: -104.64, west: -104.75 },
        paths: [
            { lat: 38.84, lng: -104.75 },
            { lat: 38.84, lng: -104.64 },
            { lat: 38.77, lng: -104.64 },
            { lat: 38.77, lng: -104.75 },
        ]
    },
    {
        id: "south_academy_chelton",
        name: "South Academy / Chelton / Fountain / Security",
        shortName: "South Academy / Fountain",
        description: "Low-value local short hops; lower average fares, higher deadhead exposure",
        center: { lat: 38.745, lng: -104.755 },
        bounds: { north: 38.78, south: 38.68, east: -104.68, west: -104.82 },
        paths: [
            { lat: 38.78, lng: -104.82 },
            { lat: 38.78, lng: -104.68 },
            { lat: 38.68, lng: -104.68 },
            { lat: 38.68, lng: -104.82 },
        ]
    },
    {
        id: "manitou_ute_pass",
        name: "Manitou Springs / Ute Pass",
        shortName: "Manitou / Ute Pass",
        description: "Mountain tourist corridor & Cog Railway transfers; high seasonal spikes",
        center: { lat: 38.860, lng: -104.925 },
        bounds: { north: 38.90, south: 38.82, east: -104.88, west: -105.00 },
        paths: [
            { lat: 38.90, lng: -105.00 },
            { lat: 38.90, lng: -104.88 },
            { lat: 38.82, lng: -104.88 },
            { lat: 38.82, lng: -105.00 },
        ]
    }
];

interface TripYieldFeature {
    type: "Feature";
    geometry: {
        type: "Point" | "LineString";
        coordinates: [number, number] | [number, number][]; // [lng, lat]
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

type TripTypeFilter = "all" | "uber" | "private";
type ViewMode = "zones" | "pickups" | "heatmap";

interface ZoneAnalytics {
    zone: ZoneConfig;
    trips: number;
    privateTrips: number;
    uberTrips: number;
    avgFare: number;
    minFare: number;
    maxFare: number;
    avgNetPerHour: number;
    avgDistance: number;
    totalGross: number;
    tier: "premium" | "mid" | "low";
}

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
    const [viewMode, setViewMode] = useState<ViewMode>("zones");
    const [tripFilter, setTripFilter] = useState<TripTypeFilter>("all");
    const [dateRange, setDateRange] = useState<string>("all");
    const [selectedTrip, setSelectedTrip] = useState<TripYieldFeature | null>(null);
    const [selectedZone, setSelectedZone] = useState<ZoneAnalytics | null>(null);

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
            params.append("format", "points");
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

            const data = await getTripYieldData(params);
            setTrips(data.features || []);
        } catch (err: unknown) {
            console.error("Failed to fetch trip yield data:", err);
        } finally {
            setLoading(false);
        }
    }, [tripFilter, dateRange, energyRate, wearRate]);

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
        const avgGrossFare = trips.length > 0 ? (totalGross / trips.length) : 0;

        return {
            count: trips.length,
            totalGross,
            totalNet,
            totalDistance,
            avgGrossFare,
            avgYield,
            lossCount,
            estCount,
        };
    }, [trips]);

    // Calculate Zone-Level Dollar Yields from Empirical Telemetry
    const zoneAnalytics = useMemo<ZoneAnalytics[]>(() => {
        if (!trips.length) return [];

        const results: ZoneAnalytics[] = [];

        CS_ZONES.forEach((z) => {
            const zoneTrips: TripYieldFeature[] = [];
            trips.forEach((t) => {
                const coords = (
                    t.geometry.type === "Point"
                        ? (t.geometry.coordinates as [number, number])
                        : (t.geometry.coordinates as [number, number][])[0]
                );
                if (!coords) return;
                const lng = coords[0];
                const lat = coords[1];

                if (lat >= z.bounds.south && lat <= z.bounds.north && lng >= z.bounds.west && lng <= z.bounds.east) {
                    zoneTrips.push(t);
                }
            });

            if (zoneTrips.length > 0) {
                let totalGross = 0;
                let totalNet = 0;
                let totalMin = 0;
                let totalDist = 0;
                let privateCount = 0;
                let uberCount = 0;
                const fares: number[] = [];

                zoneTrips.forEach((zt) => {
                    const p = zt.properties;
                    totalGross += p.gross;
                    totalNet += p.net;
                    totalMin += p.duration_min;
                    totalDist += p.distance_mi;
                    fares.push(p.gross);
                    if (p.trip_type === "Private") privateCount++;
                    else uberCount++;
                });

                const count = zoneTrips.length;
                const avgFare = totalGross / count;
                const avgDist = totalDist / count;
                const hours = totalMin / 60;
                const avgNetPerHour = hours > 0 ? (totalNet / hours) : 0;
                const minFare = Math.min(...fares);
                const maxFare = Math.max(...fares);

                const tier: "premium" | "mid" | "low" = 
                    avgFare >= 22 ? "premium" : (avgFare >= 14 ? "mid" : "low");

                results.push({
                    zone: z,
                    trips: count,
                    privateTrips: privateCount,
                    uberTrips: uberCount,
                    avgFare,
                    minFare,
                    maxFare,
                    avgNetPerHour,
                    avgDistance: avgDist,
                    totalGross,
                    tier
                });
            }
        });

        // Sort descending by average fare
        return results.sort((a, b) => b.avgFare - a.avgFare);
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
                        <DollarSign className="w-5 h-5" />
                    </div>
                    <div>
                        <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                            Colorado Springs Zone Staging & Yield Console
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono">
                                Verified Yields
                            </span>
                        </h2>
                        <p className="text-xs text-slate-400">
                            Expected dollar earnings per trip and net $/hr by pickup neighborhood
                        </p>
                    </div>
                </div>

                {/* Filter & Mode Controls */}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                    {/* View Mode Toggle */}
                    <div className="flex items-center bg-slate-950 rounded-lg p-1 border border-slate-800">
                        <button
                            onClick={() => setViewMode("zones")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1.5 transition-all ${
                                viewMode === "zones" ? "bg-slate-800 text-emerald-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <DollarSign className="w-3.5 h-3.5" />
                            Zone Staging
                        </button>
                        <button
                            onClick={() => setViewMode("pickups")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1.5 transition-all ${
                                viewMode === "pickups" ? "bg-slate-800 text-cyan-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <Activity className="w-3.5 h-3.5" />
                            All Pickups
                        </button>
                        <button
                            onClick={() => setViewMode("heatmap")}
                            className={`px-2.5 py-1 rounded font-medium flex items-center gap-1.5 transition-all ${
                                viewMode === "heatmap" ? "bg-slate-800 text-amber-400 shadow-sm" : "text-slate-400 hover:text-white"
                            }`}
                        >
                            <Flame className="w-3.5 h-3.5" />
                            Density Heatmap
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

            {/* Zone Quick-Staging Decision Strip */}
            <div className="bg-slate-950/90 border-b border-slate-800 px-4 py-2 flex items-center gap-3 overflow-x-auto text-xs scrollbar-thin">
                <span className="font-mono text-[11px] uppercase tracking-wider text-slate-400 shrink-0 flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5 text-cyan-400" />
                    Staging Guide:
                </span>
                {zoneAnalytics.map((za) => (
                    <button
                        key={za.zone.id}
                        onClick={() => setSelectedZone(za)}
                        className={`flex items-center gap-2 px-2.5 py-1 rounded-lg border text-xs whitespace-nowrap transition-all ${
                            selectedZone?.zone.id === za.zone.id
                                ? "bg-slate-800 border-cyan-400 text-white shadow-md ring-1 ring-cyan-400"
                                : za.tier === "premium"
                                ? "bg-emerald-950/30 border-emerald-800/60 text-emerald-300 hover:bg-emerald-900/40"
                                : za.tier === "mid"
                                ? "bg-blue-950/30 border-blue-800/60 text-blue-300 hover:bg-blue-900/40"
                                : "bg-red-950/30 border-red-800/60 text-red-300 hover:bg-red-900/40"
                        }`}
                    >
                        <span className="font-medium">{za.zone.shortName}</span>
                        <span className="font-mono font-bold">
                            ${za.avgFare.toFixed(1)}/trip
                        </span>
                        <span className="text-[10px] opacity-75 font-mono">
                            (${za.avgNetPerHour.toFixed(0)}/hr)
                        </span>
                    </button>
                ))}
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
                        {/* 1. ZONE STAGING MODE (Polygons & Floating Average $/Trip Labels) */}
                        {viewMode === "zones" && zoneAnalytics.map((za) => {
                            const isSelected = selectedZone?.zone.id === za.zone.id;
                            const zoneColor = za.tier === "premium" ? "#10b981" : (za.tier === "mid" ? "#3b82f6" : "#ef4444");

                            return (
                                <div key={za.zone.id}>
                                    <PolygonF
                                        paths={za.zone.paths}
                                        options={{
                                            fillColor: zoneColor,
                                            fillOpacity: isSelected ? 0.35 : (za.tier === "premium" ? 0.20 : 0.12),
                                            strokeColor: isSelected ? "#ffffff" : zoneColor,
                                            strokeOpacity: isSelected ? 1 : 0.7,
                                            strokeWeight: isSelected ? 2.5 : 1.5,
                                        }}
                                        onClick={() => setSelectedZone(za)}
                                    />
                                    <MarkerF
                                        position={za.zone.center}
                                        label={{
                                            text: `$${za.avgFare.toFixed(0)}/trip`,
                                            color: "#ffffff",
                                            fontSize: "12px",
                                            fontWeight: "bold",
                                            className: "font-mono px-2 py-0.5 rounded bg-slate-900/90 border border-slate-700 shadow-lg"
                                        }}
                                        icon={{
                                            path: 0, // SymbolPath.CIRCLE
                                            scale: 6,
                                            fillColor: zoneColor,
                                            fillOpacity: 1,
                                            strokeColor: "#ffffff",
                                            strokeWeight: 1.5,
                                        }}
                                        onClick={() => setSelectedZone(za)}
                                    />
                                </div>
                            );
                        })}

                        {/* 2. PICKUPS MODE (Individual Trip Dots) */}
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
                                path: 0, // SymbolPath.CIRCLE
                                scale: p.is_estimated ? 5 : 6,
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

                        {/* 3. DENSITY HEATMAP MODE (Compound Overlapping Concentric Circles) */}
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

                        {/* Selected Zone Intelligence Modal */}
                        {selectedZone && (
                            <InfoWindow
                                position={selectedZone.zone.center}
                                onCloseClick={() => setSelectedZone(null)}
                            >
                                <div className="p-2.5 text-slate-900 max-w-[260px] font-sans">
                                    <div className="flex items-center justify-between border-b pb-1 mb-1.5">
                                        <span className="text-[12px] font-bold text-slate-900">
                                            {selectedZone.zone.name}
                                        </span>
                                    </div>
                                    <p className="text-[10px] text-slate-600 mb-2">
                                        {selectedZone.zone.description}
                                    </p>

                                    <div className="flex items-baseline justify-between mb-2">
                                        <div>
                                            <div className="text-xs text-slate-500 font-semibold">Expected Fare:</div>
                                            <div className="text-xl font-extrabold font-mono text-slate-900">
                                                ${selectedZone.avgFare.toFixed(2)}
                                                <span className="text-xs font-normal text-slate-500">/trip</span>
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-xs text-slate-500 font-semibold">Net Yield:</div>
                                            <span className="text-sm font-bold text-emerald-700 font-mono">
                                                ${selectedZone.avgNetPerHour.toFixed(2)}/hr
                                            </span>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-1 text-[11px] text-slate-600 bg-slate-50 p-2 rounded border border-slate-200 mb-2">
                                        <div>Historical Trips: <strong>{selectedZone.trips}</strong></div>
                                        <div>Avg Distance: <strong>{selectedZone.avgDistance.toFixed(1)} mi</strong></div>
                                        <div>Fare Range: <strong>${selectedZone.minFare.toFixed(0)} - ${selectedZone.maxFare.toFixed(0)}</strong></div>
                                        <div>Total Gross: <strong>${selectedZone.totalGross.toFixed(0)}</strong></div>
                                    </div>

                                    <div className={`p-1.5 rounded text-[10px] font-medium text-center ${
                                        selectedZone.tier === "premium" 
                                            ? "bg-emerald-100 text-emerald-900 border border-emerald-300"
                                            : selectedZone.tier === "mid"
                                            ? "bg-blue-100 text-blue-900 border border-blue-300"
                                            : "bg-red-100 text-red-900 border border-red-300"
                                    }`}>
                                        {selectedZone.tier === "premium"
                                            ? "🟢 Top Priority Staging — High-Ticket Yield"
                                            : selectedZone.tier === "mid"
                                            ? "🟡 Steady Staging — Consistent Volume"
                                            : "🔴 Low-Value Warning — High Deadhead Exposure"}
                                    </div>
                                </div>
                            </InfoWindow>
                        )}

                        {/* Selected Individual Trip Tooltip Card */}
                        {selectedTrip && (
                            <InfoWindow
                                position={(() => {
                                    const coords = (
                                        selectedTrip.geometry.type === "Point"
                                            ? (selectedTrip.geometry.coordinates as [number, number])
                                            : (selectedTrip.geometry.coordinates as [number, number][])[0]
                                    );
                                    return { lat: coords[1], lng: coords[0] };
                                })()}
                                onCloseClick={() => setSelectedTrip(null)}
                            >
                                <div className="p-2 text-slate-900 max-w-[240px] font-sans">
                                    <div className="flex items-center justify-between border-b pb-1 mb-1.5">
                                        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-700">
                                            {selectedTrip.properties.trip_type} Pickup
                                        </span>
                                        <span className="text-[10px] font-mono text-slate-500">
                                            {selectedTrip.properties.timestamp_start?.split("T")[0]}
                                        </span>
                                    </div>

                                    <div className="flex items-baseline justify-between mb-2">
                                        <div className="text-xl font-extrabold font-mono text-slate-900">
                                            ${selectedTrip.properties.gross.toFixed(2)}
                                            <span className="text-xs font-normal text-slate-500"> gross</span>
                                        </div>
                                        <span
                                            className={`text-[10px] font-bold px-1.5 py-0.5 rounded font-mono ${
                                                selectedTrip.properties.net_per_hour > 0
                                                    ? "bg-emerald-100 text-emerald-800"
                                                    : "bg-red-100 text-red-800"
                                            }`}
                                        >
                                            ${selectedTrip.properties.net_per_hour.toFixed(0)}/hr
                                        </span>
                                    </div>

                                    <div className="grid grid-cols-2 gap-1 text-[11px] text-slate-600 bg-slate-50 p-1.5 rounded border border-slate-200">
                                        <div>Duration: <strong>{selectedTrip.properties.duration_min}m</strong></div>
                                        <div>Distance: <strong>{selectedTrip.properties.distance_mi.toFixed(1)}mi</strong></div>
                                    </div>
                                </div>
                            </InfoWindow>
                        )}
                    </GoogleMap>
                ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-slate-500">
                        <div className="w-8 h-8 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin mb-3"></div>
                        <span className="text-xs uppercase tracking-widest font-mono text-cyan-400">Loading Staging Console...</span>
                    </div>
                )}
            </div>

            {/* Legend & Staging Decision Footer */}
            <div className="p-3 bg-slate-950 border-t border-slate-800 flex flex-wrap items-center justify-between text-xs text-slate-400 gap-2">
                <div className="flex items-center gap-4">
                    <span className="font-mono text-[11px] uppercase tracking-wider text-slate-500">Zone Verdict:</span>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" />
                        <span className="text-emerald-300 font-medium">Top Yield (&ge;$22/trip)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#3b82f6]" />
                        <span className="text-blue-300 font-medium">Steady Mid ($14-$22)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444]" />
                        <span className="text-red-300 font-medium">Low Value (&lt;$14/trip)</span>
                    </div>
                </div>

                <div className="flex items-center gap-3 text-[11px]">
                    <span className="text-slate-400">
                        Total Analyzed: <strong className="text-white font-mono">{trips.length} trips</strong>
                    </span>
                    {stats && (
                        <span className="text-slate-400">
                            Overall Avg: <strong className="text-cyan-400 font-mono">${stats.avgGrossFare.toFixed(2)}/trip</strong>
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
