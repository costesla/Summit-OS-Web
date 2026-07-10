import { APIProvider, Map } from "@vis.gl/react-google-maps";
import { useAirshowMotion } from "./useAirshowMotion";

interface AirshowMapProps {
    latitude: number | null;
    longitude: number | null;
    heading?: number;
    speed: number;
    isStandby: boolean;
}

function StandbyOverlay() {
    return (
        <div className="absolute inset-0 bg-white/5 flex flex-col items-center justify-center z-10 text-gray-400">
            <div className="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-3 shadow-[0_0_15px_rgba(255,255,255,0.05)]">
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="animate-pulse"
                >
                    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
                    <circle cx="12" cy="10" r="3" />
                </svg>
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-center px-4">
                Awaiting vehicle position…
            </p>
        </div>
    );
}

/** Shown when a required build-time env var is missing — distinct from StandbyOverlay
 *  so a deploy-config failure is never misread as a Tessie position problem. */
function ConfigErrorOverlay() {
    return (
        <div className="absolute inset-0 bg-white/5 flex flex-col items-center justify-center z-10 text-gray-400">
            <div className="w-12 h-12 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-3">
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-amber-400"
                >
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                </svg>
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-center px-4 text-amber-400">
                Map temporarily unavailable
            </p>
            <p className="text-[10px] text-gray-500 text-center px-6 mt-1">
                We&rsquo;ll be back shortly
            </p>
        </div>
    );
}



function VehicleMarker() {
    return (
        <div
            style={{
                position: "absolute",
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                pointerEvents: "none",
                zIndex: 20,
            }}
        >
            <div className="w-10 h-10 rounded-full bg-cyan-500/20 flex items-center justify-center backdrop-blur-md border border-cyan-500/40 shadow-[0_0_20px_rgba(34,211,238,0.4)]">
                {/* A stylized car/navigation arrow pointing UP */}
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    className="text-cyan-400"
                >
                    <path d="M12 2L4 20l8-4 8 4z" />
                </svg>
            </div>
        </div>
    );
}

function MapMotionController({
    latitude,
    longitude,
    heading,
    speed,
}: {
    latitude: number | null;
    longitude: number | null;
    heading?: number;
    speed: number;
}) {
    useAirshowMotion(latitude, longitude, heading, speed);
    return null; // Logic only
}

export function AirshowMap({
    latitude,
    longitude,
    heading,
    speed,
    isStandby,
}: AirshowMapProps) {
    if (isStandby) {
        return <StandbyOverlay />;
    }

    const apiKey = process.env.NEXT_PUBLIC_GMAPS_API_KEY;
    const mapId = process.env.NEXT_PUBLIC_GMAPS_MAP_ID;

    if (!apiKey) {
        console.error(
            "[AirshowMap] FATAL: NEXT_PUBLIC_GMAPS_API_KEY is undefined. " +
            "Map will not load. Add this secret to GitHub Actions and redeploy."
        );
        return <ConfigErrorOverlay />;
    }
    if (!mapId) {
        console.error(
            "[AirshowMap] FATAL: NEXT_PUBLIC_GMAPS_MAP_ID is undefined. " +
            "Map will not load without a Vector Map ID — dark style and tilt require it. " +
            "Add NEXT_PUBLIC_GMAPS_MAP_ID to GitHub Actions secrets and redeploy."
        );
        return <ConfigErrorOverlay />;
    }


    return (
        <APIProvider apiKey={apiKey}>
            <Map
                mapId={mapId}
                renderingType={"VECTOR"}
                colorScheme={"DARK"}
                style={{ width: "100%", height: "100%" }}
                defaultCenter={{ lat: 38.8339, lng: -104.8214 }}
                defaultZoom={16}
                defaultHeading={0}
                defaultTilt={60}
                disableDefaultUI={true}
                gestureHandling="none"
            >
                <MapMotionController
                    latitude={latitude}
                    longitude={longitude}
                    heading={heading}
                    speed={speed}
                />
                <VehicleMarker />
            </Map>
        </APIProvider>
    );
}
