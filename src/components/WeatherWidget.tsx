"use client";

import { useState } from "react";
import { Search, Cloud, Sun, CloudRain, Snowflake } from "lucide-react";
import { getCoordinates } from "../utils/distance";

export default function WeatherWidget() {
    const [location, setLocation] = useState("");
    const [weather, setWeather] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const getWeather = async () => {
        if (!location) return;
        setLoading(true);
        setError("");
        setWeather(null);

        try {
            const coords = await getCoordinates(location);
            if (!coords) {
                setError("Location not found.");
                setLoading(false);
                return;
            }

            const res = await fetch(
                `https://api.open-meteo.com/v1/forecast?latitude=${coords.lat}&longitude=${coords.lon}&current_weather=true&temperature_unit=fahrenheit`
            );
            const data = await res.json();

            if (data.current_weather) {
                setWeather(data.current_weather);
            } else {
                setError("Weather data unavailable.");
            }
        } catch (err) {
            setError("Failed to fetch weather.");
        } finally {
            setLoading(false);
        }
    };

    const getWeatherIcon = (code: number) => {
        if (code <= 3) return <Sun className="w-10 h-10 text-yellow-400" />;
        if (code <= 48) return <Cloud className="w-10 h-10 text-gray-400" />;
        if (code <= 77) return <Snowflake className="w-10 h-10 text-cyan-200" />;
        return <CloudRain className="w-10 h-10 text-blue-400" />;
    };

    return (
        <div className="glass-panel p-6 w-full h-full border-t border-[var(--color-primary)]/30">
            <h3 className="text-sm font-bold uppercase tracking-widest mb-4 text-gray-400">Destination Weather</h3>
            <div className="flex gap-2 mb-4">
                <input
                    type="text"
                    placeholder="Enter Zip or City..."
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && getWeather()}
                    className="bg-black/40 border border-white/10 rounded px-3 py-2 text-sm flex-1 focus:border-[var(--color-primary)] outline-none text-white transition-colors"
                />
                <button
                    onClick={getWeather}
                    disabled={loading}
                    className="bg-[var(--color-primary)] text-black p-2 rounded hover:opacity-90 transition-opacity"
                >
                    <Search size={18} />
                </button>
            </div>

            {loading && <p className="text-xs text-gray-500 animate-pulse">Scanning satellites...</p>}
            {error && <p className="text-xs text-red-400">{error}</p>}

            {weather && (
                <div className="flex items-center justify-between mt-4 animate-in fade-in slide-in-from-bottom-4">
                    <div>
                        <div className="text-4xl font-bold text-white tracking-tighter">
                            {Math.round(weather.temperature)}°F
                        </div>
                        <div className="text-xs text-[var(--color-primary)] mt-1 uppercase tracking-wider">
                            Current Conditions
                        </div>
                    </div>
                    {getWeatherIcon(weather.weathercode)}
                </div>
            )}
        </div>
    );
}
