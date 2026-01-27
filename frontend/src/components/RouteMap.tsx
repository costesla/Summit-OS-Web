"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { GoogleMap, useJsApiLoader, DirectionsService, DirectionsRenderer, TrafficLayer } from "@react-google-maps/api";

const containerStyle = {
    width: '100%',
    height: '100%'
};

// Default center (Colorado Springs)
const defaultCenter = {
    lat: 38.8339,
    lng: -104.8214
};

// Map options for "Dark/Night Mode" feel
const mapOptions = {
    disableDefaultUI: true,
    zoomControl: true,
    styles: [
        { elementType: "geometry", stylers: [{ color: "#242f3e" }] },
        { elementType: "labels.text.stroke", stylers: [{ color: "#242f3e" }] },
        { elementType: "labels.text.fill", stylers: [{ color: "#746855" }] },
        {
            featureType: "administrative.locality",
            elementType: "labels.text.fill",
            stylers: [{ color: "#d59563" }],
        },
        {
            featureType: "road",
            elementType: "geometry",
            stylers: [{ color: "#38414e" }],
        },
        {
            featureType: "road",
            elementType: "geometry.stroke",
            stylers: [{ color: "#212a37" }],
        },
        {
            featureType: "road",
            elementType: "labels.text.fill",
            stylers: [{ color: "#9ca5b3" }],
        },
        {
            featureType: "water",
            elementType: "geometry",
            stylers: [{ color: "#17263c" }],
        },
    ]
};

interface RouteMapProps {
    pickup?: { lat: number; lon: number } | null;
    dropoff?: { lat: number; lon: number } | null;
    pickupAddress?: string;
    dropoffAddress?: string;
    stops?: string[]; // New Prop
    // Controlled Props for Popout/Mirror Mode
    showTraffic?: boolean;
    showWeather?: boolean;
    onToggleTraffic?: () => void;
    onToggleWeather?: () => void;
    onPopout?: () => void;
}

export default function RouteMap({
    pickup,
    dropoff,
    pickupAddress,
    dropoffAddress,
    stops = [],
    showTraffic: controlledTraffic,
    showWeather: controlledWeather,
    onToggleTraffic,
    onToggleWeather,
    onPopout
}: RouteMapProps) {
    const [directionsResponse, setDirectionsResponse] = useState<google.maps.DirectionsResult | null>(null);

    // Explicitly grab the key
    const googleMapsApiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "";

    // Libraries must match parent to prevent reload errors
    const [libraries] = useState<("places" | "geometry" | "drawing" | "visualization")[]>(["places"]);

    const { isLoaded, loadError } = useJsApiLoader({
        id: 'google-map-script',
        googleMapsApiKey: googleMapsApiKey,
        libraries
    });

    const origin = pickupAddress || (pickup ? { lat: pickup.lat, lng: pickup.lon } : null);
    const destination = dropoffAddress || (dropoff ? { lat: dropoff.lat, lng: dropoff.lon } : null);

    // Convert stops to Google Maps Waypoints
    const waypoints = useMemo(() => {
        return stops.filter(s => s.trim() !== "").map(stop => ({
            location: stop,
            stopover: true
        }));
    }, [stops]);

    // Callback must be memoized
    const directionsCallback = useCallback((
        response: google.maps.DirectionsResult | null,
        status: google.maps.DirectionsStatus
    ) => {
        if (status === 'OK' && response) {
            setDirectionsResponse(response);
        } else {
            console.warn("Directions request failed:", status);
        }
    }, []);

    // Effect to reset directions if inputs change significantly
    useEffect(() => {
        if (!origin || !destination) {
            setDirectionsResponse(null);
        }
    }, [origin, destination, waypoints]);

    // Memoize options at TOP LEVEL (Rules of Hooks)
    const directionOptions = useMemo(() => {
        // Prevent premature API calls
        if (!origin || !destination) return null;

        // Ensure string inputs are long enough to be valid addresses
        const originStr = typeof origin === 'string' ? origin : '';
        const destStr = typeof destination === 'string' ? destination : '';

        // If using object literals (lat/lng), we skip this check. 
        // But if using strings, we need at least 3 chars to avoid "NOT_FOUND" spam.
        if (typeof origin === 'string' && origin.length < 3) return null;
        if (typeof destination === 'string' && destination.length < 3) return null;

        return {
            destination: destination,
            origin: origin,
            waypoints: waypoints,
            travelMode: 'DRIVING' as google.maps.TravelMode,
            drivingOptions: {
                departureTime: new Date()
            }
        };
    }, [origin, destination, waypoints]);

    // Layer Toggles (Local State)
    const [localShowTraffic, setLocalShowTraffic] = useState(true);
    const [localShowWeather, setLocalShowWeather] = useState(false);

    // Derived State (Controlled vs Local)
    const isTrafficControlled = controlledTraffic !== undefined;
    const isWeatherControlled = controlledWeather !== undefined;

    const showTraffic = isTrafficControlled ? controlledTraffic : localShowTraffic;
    const showWeather = isWeatherControlled ? controlledWeather : localShowWeather;

    const handleToggleTraffic = () => {
        if (onToggleTraffic) onToggleTraffic();
        if (!isTrafficControlled) setLocalShowTraffic(!showTraffic);
    };

    const handleToggleWeather = () => {
        if (onToggleWeather) onToggleWeather();
        if (!isWeatherControlled) setLocalShowWeather(!showWeather);
    };

    // Weather Tile Layer (IEM NEXRAD)
    const weatherFn = useCallback((coord: google.maps.Point, zoom: number) => {
        return `https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/${zoom}/${coord.x}/${coord.y}.png`;
    }, []);

    // Refs for Map Instance and Weather Layer
    const mapRef = useRef<google.maps.Map | null>(null);
    const weatherLayerRef = useRef<google.maps.ImageMapType | null>(null);

    // Capture Map Instance
    const onMapLoad = useCallback((map: google.maps.Map) => {
        mapRef.current = map;
    }, []);

    // Toggle Weather Layer
    useEffect(() => {
        if (!mapRef.current) return;

        if (showWeather) {
            // Create NEXRAD Layer
            const layer = new google.maps.ImageMapType({
                getTileUrl: (coord, zoom) => {
                    return `https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/${zoom}/${coord.x}/${coord.y}.png`;
                },
                tileSize: new google.maps.Size(256, 256),
                opacity: 0.60,
                name: 'NEXRAD'
            });

            // Push to overlay stack
            mapRef.current.overlayMapTypes.push(layer);
            weatherLayerRef.current = layer;
        } else {
            // Remove Layer
            if (weatherLayerRef.current) {
                const arr = mapRef.current.overlayMapTypes;
                for (let i = 0; i < arr.getLength(); i++) {
                    if (arr.getAt(i) === weatherLayerRef.current) {
                        arr.removeAt(i);
                        break;
                    }
                }
                weatherLayerRef.current = null;
            }
        }
    }, [showWeather]);

    if (loadError) {
        return <div className="h-full w-full flex items-center justify-center text-red-500">Map Load Error: {loadError.message}</div>;
    }

    if (!isLoaded) {
        return <div className="h-full w-full flex items-center justify-center text-blue-400">Loading Map...</div>;
    }

    return (
        <div className="h-full w-full relative">
            <GoogleMap
                mapContainerStyle={containerStyle}
                center={defaultCenter}
                zoom={10}
                options={mapOptions}
                onLoad={onMapLoad}
            >
                {/* Directions Service - Fetches Route */}
                {directionOptions && (
                    <DirectionsService
                        options={directionOptions}
                        callback={directionsCallback}
                    />
                )}

                {/* Render text Route */}
                {directionsResponse && (
                    <DirectionsRenderer
                        options={{
                            directions: directionsResponse,
                            polylineOptions: {
                                strokeColor: "#00ffff", // Cyberpunk Blue
                                strokeWeight: 6,
                                strokeOpacity: 0.8
                            }
                        }}
                    />
                )}

                {/* LIVE LAYERS */}
                {showTraffic && <TrafficLayer />}

                {showWeather && (
                    <div className="hidden">
                        {/* 
                            Note: We can't use a simple JSX component for ImageMapType in @react-google-maps/api easily without a custom component wrapper.
                            However, we can shim it or just use a simpler OverlayView if needed.
                            Actually, simpler approach: Use the GoogleMap 'onLoad' to push the layer.
                            But for now, let's try pushing a TrafficLayer as a placeholder or see if we can use a KML/Image layer.
                            
                            Re-thinking: The library doesn't export <ImageMapType> directly.
                            Let's use a simpler approach for now:
                            Just "Toggle Traffic" is built-in. 
                            For Weather, we might need a more complex implementation.
                            Let's use the standard "OverlayView" or just stick to Traffic first to ensure stability?
                            User said "give it a go". Let's try to inject the ImageMapType via onLoad.
                        */}
                    </div>
                )}
            </GoogleMap>

            {/* --- MAP CONTROLS --- */}
            <div className="absolute top-2 left-2 flex flex-col gap-2 z-10">
                <button
                    onClick={handleToggleTraffic}
                    className={`p-2 rounded-lg text-[10px] font-bold uppercase tracking-wider backdrop-blur-md border transition-all ${showTraffic ? 'bg-green-500/20 border-green-500 text-green-400' : 'bg-black/60 border-white/10 text-gray-400 hover:text-white'}`}
                >
                    Traffic {showTraffic ? 'ON' : 'OFF'}
                </button>
                <button
                    onClick={handleToggleWeather}
                    className={`p-2 rounded-lg text-[10px] font-bold uppercase tracking-wider backdrop-blur-md border transition-all ${showWeather ? 'bg-blue-500/20 border-blue-500 text-blue-400' : 'bg-black/60 border-white/10 text-gray-400 hover:text-white'}`}
                >
                    Radar {showWeather ? 'ON' : 'OFF'}
                </button>
                {onPopout && (
                    <button
                        onClick={onPopout}
                        className="p-2 rounded-lg text-[10px] font-bold uppercase tracking-wider backdrop-blur-md border bg-black/60 border-white/10 text-cyan-400 hover:text-white hover:border-cyan-500 transition-all mt-2"
                    >
                        Pop Out ⬈
                    </button>
                )}
            </div>
        </div>
    );
}
