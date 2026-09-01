"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { GoogleMap, useJsApiLoader } from "@react-google-maps/api";
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
    const [map, setMap] = useState<google.maps.Map | null>(null);

    // View & Filter states
    const [viewMode, setViewMode] = useState<ViewMode>("zones");
    const [tripFilter, setTripFilter] = useState<TripTypeFilter>("all");
    const [dateRange, setDateRange] = useState<string>("all");
    const [selectedZone, setSelectedZone] = useState<ZoneAnalytics | null>(null);

    // Unvalidated rate parameters
    const [energyRate] = useState<number>(0.45);
    const [wearRate] = useState<number>(0.13);

    const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);

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

    // Native Google Maps Overlay Manager — avoids React 18 __e3_ listener lifecycle bugs
    useEffect(() => {
        if (!map || typeof google === "undefined" || !google.maps) return;

        const overlays: (google.maps.Polygon | google.maps.Marker | google.maps.Circle)[] = [];

        if (!infoWindowRef.current) {
            infoWindowRef.current = new google.maps.InfoWindow();
        }
        const infoWindow = infoWindowRef.current;

        if (viewMode === "zones") {
            zoneAnalytics.forEach((za) => {
                const isSelected = selectedZone?.zone.id === za.zone.id;
                const zoneColor = za.tier === "premium" ? "#10b981" : (za.tier === "mid" ? "#3b82f6" : "#ef4444");

                // Sector Polygon
                const poly = new google.maps.Polygon({
                    paths: za.zone.paths,
                    fillColor: zoneColor,
                    fillOpacity: isSelected ? 0.35 : (za.tier === "premium" ? 0.20 : 0.12),
                    strokeColor: isSelected ? "#ffffff" : zoneColor,
                    strokeOpacity: isSelected ? 1 : 0.7,
                    strokeWeight: isSelected ? 2.5 : 1.5,
                    map,
                });

                poly.addListener("click", () => {
                    setSelectedZone(za);
                    infoWindow.setContent(`
                        <div style="padding:10px; font-family:sans-serif; color:#0f172a; max-width:240px;">
                            <div style="font-weight:bold; font-size:13px; margin-bottom:4px;">${za.zone.name}</div>
                            <div style="font-size:11px; color:#475569; margin-bottom:8px;">${za.zone.description}</div>
                            <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px;">
                                <div>
                                    <span style="font-size:10px; color:#64748b;">Expected Fare:</span><br/>
                                    <strong style="font-size:18px; font-family:monospace; color:#0f172a;">$${za.avgFare.toFixed(2)}</strong>
                                </div>
                                <div style="text-align:right;">
                                    <span style="font-size:10px; color:#64748b;">Net Yield:</span><br/>
                                    <strong style="font-size:13px; font-family:monospace; color:#059669;">$${za.avgNetPerHour.toFixed(0)}/hr</strong>
                                </div>
                            </div>
                            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px; font-size:10px; color:#334155; margin-bottom:8px;">
                                <div>Historical Trips: <strong>${za.trips}</strong> (${za.privateTrips} Priv, ${za.uberTrips} Uber)</div>
                                <div>Avg Distance: <strong>${za.avgDistance.toFixed(1)} mi</strong></div>
                                <div>Fare Range: <strong>$${za.minFare.toFixed(0)} – $${za.maxFare.toFixed(0)}</strong></div>
                            </div>
                            <div style="padding:4px; text-align:center; border-radius:4px; font-size:10px; font-weight:bold; ${
                                za.tier === "premium" ? "background:#d1fae5; color:#065f46;" : (za.tier === "mid" ? "background:#dbeafe; color:#1e40af;" : "background:#fee2e2; color:#991b1b;")
                            }">
                                ${za.tier === "premium" ? "🟢 Top Priority Staging" : (za.tier === "mid" ? "🟡 Steady Mid-Tier" : "🔴 Low Value Short Hops")}
                            </div>
                        </div>
                    `);
                    infoWindow.setPosition(za.zone.center);
                    infoWindow.open(map);
                });
                overlays.push(poly);

                // Dollar Badge Marker
                const marker = new google.maps.Marker({
                    position: za.zone.center,
                    label: {
                        text: `$${za.avgFare.toFixed(0)}`,
                        color: "#ffffff",
                        fontSize: "12px",
                        fontWeight: "bold",
                    },
                    icon: {
                        path: 0, // SymbolPath.CIRCLE
                        scale: 14,
                        fillColor: zoneColor,
                        fillOpacity: 0.95,
                        strokeColor: "#ffffff",
                        strokeWeight: 2,
                    },
                    map,
                });
                marker.addListener("click", () => {
                    setSelectedZone(za);
                    poly.setOptions({ strokeColor: "#ffffff", fillOpacity: 0.35, strokeWeight: 2.5 });
                });
                overlays.push(marker);
            });
        } else if (viewMode === "pickups") {
            trips.forEach((t) => {
                const p = t.properties;
                const coords = (
                    t.geometry.type === "Point"
                        ? (t.geometry.coordinates as [number, number])
                        : (t.geometry.coordinates as [number, number][])[0]
                );
                if (!coords) return;

                const marker = new google.maps.Marker({
                    position: { lat: coords[1], lng: coords[0] },
                    icon: {
                        path: 0, // SymbolPath.CIRCLE
                        scale: p.is_estimated ? 4.5 : 5.5,
                        fillColor: getYieldColor(p.net_per_hour),
                        fillOpacity: p.is_estimated ? 0.6 : 0.9,
                        strokeColor: p.net_per_hour <= 0 ? "#fca5a5" : (p.is_estimated ? "#cbd5e1" : "#ffffff"),
                        strokeWeight: 1.5,
                    },
                    map,
                });
                marker.addListener("click", () => {
                    infoWindow.setContent(`
                        <div style="padding:8px; font-family:sans-serif; color:#0f172a; max-width:200px;">
                            <div style="font-weight:bold; font-size:11px; text-transform:uppercase; color:#475569;">${p.trip_type} Pickup</div>
                            <div style="display:flex; justify-content:space-between; align-items:baseline; margin:6px 0;">
                                <strong style="font-size:18px; font-family:monospace; color:#0f172a;">$${p.gross.toFixed(2)}</strong>
                                <span style="font-size:11px; font-weight:bold; color:#059669; font-family:monospace;">$${p.net_per_hour.toFixed(0)}/hr</span>
                            </div>
                            <div style="font-size:10px; color:#64748b;">
                                <div>Distance: <strong>${p.distance_mi.toFixed(1)} mi</strong></div>
                                <div>Duration: <strong>${p.duration_min} min</strong></div>
                            </div>
                        </div>
                    `);
                    infoWindow.setPosition({ lat: coords[1], lng: coords[0] });
                    infoWindow.open(map);
                });
                overlays.push(marker);
            });
        } else if (viewMode === "heatmap") {
            trips.forEach((t) => {
                const p = t.properties;
                const coords = (
                    t.geometry.type === "Point"
                        ? (t.geometry.coordinates as [number, number])
                        : (t.geometry.coordinates as [number, number][])[0]
                );
                if (!coords) return;

                const circle = new google.maps.Circle({
                    center: { lat: coords[1], lng: coords[0] },
                    radius: 650,
                    fillColor: getYieldColor(p.net_per_hour),
                    fillOpacity: 0.18,
                    strokeColor: getYieldColor(p.net_per_hour),
                    strokeOpacity: 0.4,
                    strokeWeight: 1,
                    map,
                });
                overlays.push(circle);
            });
        }

        return () => {
            overlays.forEach((o) => o.setMap(null));
        };
    }, [map, viewMode, zoneAnalytics, trips, selectedZone]);

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
                        onLoad={(m) => setMap(m)}
                        onUnmount={() => setMap(null)}
                        options={{
                            styles: darkMapStyles,
                            disableDefaultUI: true,
                            zoomControl: true,
                            clickableIcons: false,
                        }}
                    />
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
