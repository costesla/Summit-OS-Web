import { useEffect, useRef } from "react";
import { useMap } from "@vis.gl/react-google-maps";

const MPH_TO_MS = 0.44704;

export function useAirshowMotion(
    rawLat: number | null,
    rawLng: number | null,
    rawHeading: number | undefined,
    rawSpeed: number
) {
    const map = useMap();
    const posRef = useRef<{ lat: number; lng: number } | null>(null);
    const headingRef = useRef<number>(0);
    const headingInitialized = useRef<boolean>(false);
    const rafRef = useRef<number>(0);
    const lastTimeRef = useRef<number>(0);

    // Tessie reports speed in mph — convert before dead-reckoning
    const speedMs = (rawSpeed ?? 0) * MPH_TO_MS;

    useEffect(() => {
        if (!map) return;

        // Initialize heading on first fix, or update if speed is high enough
        if (rawHeading !== undefined) {
            if (!headingInitialized.current || speedMs >= 2.23) { // ~5mph = 2.23m/s
                headingRef.current = rawHeading;
                headingInitialized.current = true;
            }
        }

        // Immediately snap position if posRef is null (initial load)
        if (rawLat !== null && rawLng !== null && posRef.current === null) {
            posRef.current = { lat: rawLat, lng: rawLng };
        }
    }, [map, rawLat, rawLng, rawHeading, speedMs]);

    useEffect(() => {
        if (!map) return;

        const animate = (time: number) => {
            if (lastTimeRef.current === 0) {
                lastTimeRef.current = time;
                rafRef.current = requestAnimationFrame(animate);
                return;
            }

            const dt = (time - lastTimeRef.current) / 1000; // seconds
            lastTimeRef.current = time;

            if (posRef.current) {
                let currentLat = posRef.current.lat;
                let currentLng = posRef.current.lng;

                // 1. Dead-reckoning
                if (speedMs > 0) {
                    const distanceMeters = speedMs * dt;
                    const headingRad = headingRef.current * (Math.PI / 180);
                    
                    // 1 deg lat ≈ 111,320 m
                    const deltaLat = (distanceMeters * Math.cos(headingRad)) / 111320;
                    const deltaLng = (distanceMeters * Math.sin(headingRad)) / (111320 * Math.cos(currentLat * (Math.PI / 180)));
                    
                    currentLat += deltaLat;
                    currentLng += deltaLng;
                }

                // 2. Ease-correct toward true position if we have a new fix
                if (rawLat !== null && rawLng !== null) {
                    // Simple LERP (Linear Interpolation) with alpha ~0.1
                    currentLat += (rawLat - currentLat) * 0.1;
                    currentLng += (rawLng - currentLng) * 0.1;
                }

                posRef.current = { lat: currentLat, lng: currentLng };

                // 3. Low-pass filter heading (only above 5mph)
                if (speedMs >= 2.23 && rawHeading !== undefined) {
                    // Handle wrap-around for heading interpolation (0-360)
                    let diff = rawHeading - headingRef.current;
                    if (diff > 180) diff -= 360;
                    if (diff < -180) diff += 360;
                    
                    headingRef.current += diff * 0.05; // alpha = 0.05 for smooth damping
                    // Keep in 0-360 range
                    headingRef.current = (headingRef.current + 360) % 360;
                }

                // 4. Apply camera
                map.moveCamera({
                    center: posRef.current,
                    heading: headingRef.current,
                    tilt: 60,
                    zoom: 16,
                });
            }

            rafRef.current = requestAnimationFrame(animate);
        };

        rafRef.current = requestAnimationFrame(animate);

        return () => {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
        };
    }, [map, rawLat, rawLng, rawHeading, speedMs]);
}
