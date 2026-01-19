
const TESSIE_API_URL = 'https://api.tessie.com';

interface TessieState {
    drive_state: {
        speed: number;
        elevation: number;
        latitude: number;
        longitude: number;
    };
    vehicle_state: {
        odometer: number;
        locked: boolean;
        fd_window: number; // Front Driver Window
        fp_window: number; // Front Passenger
        rd_window: number; // Rear Driver
        rp_window: number; // Rear Passenger
        seat_heater_left: number;
        seat_heater_right: number;
        seat_heater_rear_left: number;
        seat_heater_rear_right: number;
        seat_heater_rear_center: number;
    };
    climate_state: {
        inside_temp: number;
        outside_temp: number;
        is_climate_on: boolean;
    };
}

export class TessieClient {
    private apiKey: string;
    private vin: string;

    constructor() {
        this.apiKey = process.env.TESSIE_API_KEY || "";
        this.vin = "5YJ3E1EA9NF288034"; // Thor

        if (!this.apiKey) {
            console.error("TESSIE_API_KEY is missing");
        }
    }

    private async request(endpoint: string, method: 'GET' | 'POST' = 'GET', body?: any) {
        if (!this.apiKey) return null;

        const url = `${TESSIE_API_URL}/${this.vin}/${endpoint}`;
        const headers = { 'Authorization': `Bearer ${this.apiKey}` };

        try {
            const res = await fetch(url, {
                method,
                headers,
                body: body ? JSON.stringify(body) : undefined
            });
            return await res.json();
        } catch (e) {
            console.error(`Tessie Error [${endpoint}]:`, e);
            throw e;
        }
    }

    async getState(): Promise<TessieState | null> {
        // use_cache=true is cheaper/faster if we just want recent data
        const data = await this.request('state?use_cache=true');
        return data?.results?.[0] || null;
    }

    // --- CONTROLS ---

    async setSeatHeater(seat: 'front_left' | 'front_right' | 'rear_left' | 'rear_right' | 'rear_center', level: 0 | 1 | 2 | 3) {
        // Map readable names to Tessie API params if needed, or pass directly.
        // Tessie usually accepts 'seat_heater_rear_left' etc as end points or command args.
        // Command: command/seat_heater?seat=0&level=3

        // Mapping seats to integers (common Tesla API pattern):
        // 0=Front Left, 1=Front Right, 2=Rear Left, 4=Rear Right, 5=Rear Center
        const seatMap: Record<string, number> = {
            'front_left': 0,
            'front_right': 1,
            'rear_left': 2,
            'rear_center': 5,
            'rear_right': 4
        };

        return this.request(`command/remote_seat_heater_request?heater=${seatMap[seat]}&level=${level}`, 'GET');
        // Note: Tessie commands are often GETs with params
    }

    async setVentWindows(action: 'vent' | 'close') {
        const cmd = action === 'vent' ? 'vent_windows' : 'close_windows';
        return this.request(`command/${cmd}`, 'GET');
    }

    // Volume is tricky, might not be exposed in standard API, usually Media Control.
    // Fallback: Just focus on Climate/Seats for now.
}
