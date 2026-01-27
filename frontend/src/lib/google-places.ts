/**
 * Google Places API (New) Integration for COS Tesla LLC Receipt System
 * Uses Places API v1 to fetch contextual imagery for trip receipts
 */

import { GeoData, PlaceDetails, PlaceSearchResult } from '@/types/receipt-types';

const GOOGLE_PLACES_API_KEY = process.env.GOOGLE_MAPS_API_KEY;
const PLACES_API_BASE = 'https://places.googleapis.com/v1';

/**
 * Fetch place details including photos and attributions
 * @param placeId - Google Place ID
 * @returns Place details with photos and attribution
 */
export async function getPlaceDetails(placeId: string): Promise<PlaceDetails | null> {
    if (!GOOGLE_PLACES_API_KEY) {
        console.warn('Google Places API key not configured');
        return null;
    }

    try {
        const url = `${PLACES_API_BASE}/places/${placeId}`;
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': GOOGLE_PLACES_API_KEY,
                'X-Goog-FieldMask': 'displayName,photos,attributions',
            },
        });

        if (!response.ok) {
            console.error(`Places API error: ${response.status} ${response.statusText}`);
            return null;
        }

        const data: PlaceDetails = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching place details:', error);
        return null;
    }
}

/**
 * Search for a place by text query with optional location bias
 * @param query - Search query (e.g., "Banning Lewis Ranch, Colorado Springs CO, US")
 * @param geo - Optional geographic bias for search
 * @returns First place result with photos, or null
 */
export async function searchPlaceByText(
    query: string,
    geo?: GeoData
): Promise<{ placeId: string; details: PlaceDetails } | null> {
    if (!GOOGLE_PLACES_API_KEY) {
        console.warn('Google Places API key not configured');
        return null;
    }

    try {
        const url = `${PLACES_API_BASE}/places:searchText`;

        const body: any = {
            textQuery: query,
        };

        // Add location bias if geo data provided
        if (geo) {
            body.locationBias = {
                circle: {
                    center: {
                        latitude: geo.lat,
                        longitude: geo.lng,
                    },
                    radius: 15000, // 15km radius
                },
            };
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': GOOGLE_PLACES_API_KEY,
                'X-Goog-FieldMask': 'places.id,places.displayName,places.photos',
            },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            console.error(`Places Text Search error: ${response.status} ${response.statusText}`);
            return null;
        }

        const data: PlaceSearchResult = await response.json();

        // Find first place with photos
        const placeWithPhotos = data.places?.find(place => place.photos && place.photos.length > 0);

        if (!placeWithPhotos || !placeWithPhotos.photos) {
            console.warn('No places with photos found for query:', query);
            return null;
        }

        return {
            placeId: placeWithPhotos.id,
            details: {
                displayName: placeWithPhotos.displayName,
                photos: placeWithPhotos.photos,
            },
        };
    } catch (error) {
        console.error('Error searching place by text:', error);
        return null;
    }
}

/**
 * Retrieve photo media as base64-encoded JPEG
 * @param photoName - Photo resource name (e.g., "places/ChIJ.../photos/...")
 * @returns Base64-encoded JPEG string, or null
 */
export async function getPhotoMedia(photoName: string): Promise<string | null> {
    if (!GOOGLE_PLACES_API_KEY) {
        console.warn('Google Places API key not configured');
        return null;
    }

    try {
        const url = `${PLACES_API_BASE}/${photoName}/media?maxWidthPx=800&key=${GOOGLE_PLACES_API_KEY}`;

        const response = await fetch(url, {
            method: 'GET',
        });

        if (!response.ok) {
            console.error(`Photo Media error: ${response.status} ${response.statusText}`);
            return null;
        }

        // Get binary data
        const arrayBuffer = await response.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);

        // Convert to base64
        const base64 = buffer.toString('base64');

        return base64;
    } catch (error) {
        console.error('Error fetching photo media:', error);
        return null;
    }
}

/**
 * Get contextual place photo for a trip
 * Priority: Dropoff PlaceId > Pickup PlaceId > Text Search (Dropoff) > Text Search (Pickup)
 * @param pickupArea - High-level pickup area
 * @param dropoffArea - High-level dropoff area
 * @param pickupPlaceId - Optional pickup Place ID
 * @param dropoffPlaceId - Optional dropoff Place ID
 * @param geo - Optional geographic bias
 * @returns Photo base64 and attribution, or null
 */
export async function getContextualPhoto(
    pickupArea: string,
    dropoffArea: string,
    pickupPlaceId?: string,
    dropoffPlaceId?: string,
    geo?: GeoData
): Promise<{ base64: string; attribution: string } | null> {
    let placeDetails: PlaceDetails | null = null;
    let searchQuery = '';

    // Priority 1: Dropoff PlaceId
    if (dropoffPlaceId) {
        placeDetails = await getPlaceDetails(dropoffPlaceId);
    }

    // Priority 2: Pickup PlaceId
    if (!placeDetails && pickupPlaceId) {
        placeDetails = await getPlaceDetails(pickupPlaceId);
    }

    // Priority 3: Text Search for Dropoff
    if (!placeDetails) {
        searchQuery = geo
            ? `${dropoffArea}, ${geo.city} ${geo.region}, ${geo.country}`
            : dropoffArea;

        const searchResult = await searchPlaceByText(searchQuery, geo);
        if (searchResult) {
            placeDetails = searchResult.details;
        }
    }

    // Priority 4: Text Search for Pickup
    if (!placeDetails) {
        searchQuery = geo
            ? `${pickupArea}, ${geo.city} ${geo.region}, ${geo.country}`
            : pickupArea;

        const searchResult = await searchPlaceByText(searchQuery, geo);
        if (searchResult) {
            placeDetails = searchResult.details;
        }
    }

    // No place found with photos
    if (!placeDetails || !placeDetails.photos || placeDetails.photos.length === 0) {
        console.warn('No photos available for trip areas');
        return null;
    }

    // Get first photo
    const photo = placeDetails.photos[0];
    const photoBase64 = await getPhotoMedia(photo.name);

    if (!photoBase64) {
        return null;
    }

    // Build attribution text
    const attributions = photo.authorAttributions
        ?.map(attr => attr.displayName)
        .join(', ') || 'Google';

    return {
        base64: photoBase64,
        attribution: attributions,
    };
}
