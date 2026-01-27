export function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 3959; // Radius of Earth in miles
    const dLat = (lat2 - lat1) * (Math.PI / 180);
    const dLon = (lon2 - lon1) * (Math.PI / 180);
    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * (Math.PI / 180)) *
        Math.cos(lat2 * (Math.PI / 180)) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

export async function getCoordinates(address: string): Promise<{ lat: number; lon: number } | null> {
    try {
        // Strategy: 
        // 1. Try Local Context first ("Address, Colorado Springs, CO")
        // 2. If no result, try Exact/Global search ("DEN Airport", "Denver", etc.)

        const isLocalContext = address.toLowerCase().includes("colorado") || address.toLowerCase().includes(", co");
        const specialLocations = ["den", "airport", "dia"]; // Locations likely outside CS limits
        const shouldBiasLocal = !isLocalContext && !specialLocations.some(l => address.toLowerCase().includes(l));

        // Attempt 1: Local Context (Priority)
        if (shouldBiasLocal) {
            const query = `${address}, Colorado Springs, CO`;
            const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&email=peter.teehan@costesla.com`);
            const data = await res.json();

            if (data && data.length > 0) {
                return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
            }
        }

        // Attempt 2: Exact/Global (Fallback or if "Airport" specified)
        const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(address)}&email=peter.teehan@costesla.com`);
        const data = await res.json();

        if (data && data.length > 0) {
            return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
        }

        return null;
    } catch (error) {
        console.error("Geocoding failed", error);
        return null;
    }
}
