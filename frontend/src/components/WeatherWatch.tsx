"use client";

import { useState, useEffect, useRef } from "react";
import { Search, MapPin, Cloud, Sun, CloudRain, CloudSnow, Wind, Droplets, Gauge } from "lucide-react";

interface WeatherData {
    current: {
        temp_f: number;
        humidity: number;
        wind_mph: number;
        condition: string;
        code: number;
    };
    daily: {
        date: string;
        max_f: number;
        min_f: number;
        condition: string;
    }[];
}

interface SearchResult {
    name: string;
    lat: number;
    lng: number;
}

export default function WeatherWatch() {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<SearchResult[]>([]);
    const [selectedCity, setSelectedCity] = useState<SearchResult | null>(null);
    const [weather, setWeather] = useState<WeatherData | null>(null);
    const [loading, setLoading] = useState(false);
    const [searching, setSearching] = useState(false);
    const componentRef = useRef<HTMLDivElement>(null);

    // Initial load: Colorado Springs
    useEffect(() => {
        const loadDefault = async () => {
            await fetchWeather({ name: "Colorado Springs, CO", lat: 38.8339, lng: -104.8214 });
        };
        loadDefault();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Handle search input debounce
    useEffect(() => {
        const timer = setTimeout(async () => {
            if (query.length > 2) {
                setSearching(true);
                try {
                    const res = await fetch(`https://summitos-api.azurewebsites.net/api/weather/search?q=${encodeURIComponent(query)}`);
                    if (res.ok) {
                        const data = await res.json();
                        setResults(data.results || []);
                    }
                } catch (e) {
                    console.error("Search failed", e);
                } finally {
                    setSearching(false);
                }
            } else {
                setResults([]);
            }
        }, 500);

        return () => clearTimeout(timer);
    }, [query]);

    const fetchWeather = async (city: SearchResult) => {
        setLoading(true);
        setResults([]); // Close dropdown
        setQuery("");   // Clear search
        setSelectedCity(city);

        try {
            const res = await fetch(`https://summitos-api.azurewebsites.net/api/weather/forecast?lat=${city.lat}&lng=${city.lng}`);
            if (res.ok) {
                const data = await res.json();
                setWeather(data);
            }
        } catch (e) {
            console.error("Weather fetch failed", e);
        } finally {
            setLoading(false);
        }
    };

    // Close dropdown on outside click
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (componentRef.current && !componentRef.current.contains(event.target as Node)) {
                setResults([]);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    return (
        <div ref={componentRef} className="bg-[#111] border border-white/10 rounded-3xl p-8 relative overflow-visible group min-h-[300px]">
            {/* Glow Effect */}
            <div className="absolute -top-20 -right-20 w-64 h-64 bg-yellow-500/5 blur-[80px] rounded-full pointer-events-none group-hover:bg-yellow-500/10 transition-colors duration-1000" />

            <div className="relative z-10 space-y-6">
                <div className="flex items-center justify-between">
                    <h3 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <Sun className="text-yellow-500" size={24} />
                        Weather Watch
                    </h3>
                    {selectedCity && (
                        <div className="text-xs font-mono text-gray-500 bg-white/5 px-2 py-1 rounded">
                            {selectedCity.lat.toFixed(2)}, {selectedCity.lng.toFixed(2)}
                        </div>
                    )}
                </div>

                {/* Search Box */}
                <div className="relative">
                    <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none">
                        <Search size={16} className="text-gray-500" />
                    </div>
                    <input
                        type="text"
                        placeholder="Search city (e.g. Denver, Aspen)..."
                        className="w-full bg-white/5 border border-white/10 rounded-xl py-3 pl-10 pr-4 text-sm text-white focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition-all placeholder:text-gray-600"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                    />
                    {searching && (
                        <div className="absolute inset-y-0 right-3 flex items-center">
                            <div className="w-4 h-4 border-2 border-gray-500 border-t-transparent rounded-full animate-spin" />
                        </div>
                    )}

                    {/* Results Dropdown */}
                    {results.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-2 bg-[#1a1a1a] border border-white/10 rounded-xl shadow-2xl z-50 max-h-60 overflow-y-auto">
                            {results.map((r, i) => (
                                <button
                                    key={i}
                                    onClick={() => fetchWeather(r)}
                                    className="w-full text-left px-4 py-3 hover:bg-white/5 border-b border-white/5 last:border-0 flex items-center gap-3 transition-colors"
                                >
                                    <MapPin size={14} className="text-cyan-500" />
                                    <span className="text-sm text-gray-300 truncate">{r.name}</span>
                                </button>
                            ))}
                            <div className="px-4 py-2 bg-black/20 text-[10px] text-gray-600 text-center font-mono uppercase tracking-widest">
                                Powered by Google Maps
                            </div>
                        </div>
                    )}
                </div>

                {/* Weather Display */}
                {weather ? (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                        {/* Current Condition */}
                        <div className="text-center py-4">
                            <h2 className="text-2xl font-light text-white mb-1">
                                {selectedCity?.name.split(",")[0] || "Unknown"}
                            </h2>
                            <div className="text-sm text-gray-500 uppercase tracking-widest mb-6">
                                {weather.current.condition}
                            </div>

                            <div className="text-7xl font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-br from-white to-gray-400">
                                {Math.round(weather.current.temp_f)}°
                            </div>

                            <div className="flex justify-center gap-8 mt-6">
                                <div className="flex flex-col items-center gap-1">
                                    <Wind size={16} className="text-gray-500" />
                                    <span className="text-xs font-mono">{weather.current.wind_mph} mph</span>
                                </div>
                                <div className="flex flex-col items-center gap-1">
                                    <Droplets size={16} className="text-cyan-500/70" />
                                    <span className="text-xs font-mono">{weather.current.humidity}%</span>
                                </div>
                            </div>
                        </div>

                        {/* Forecast Mini-Row */}
                        <div className="grid grid-cols-3 gap-2 border-t border-white/5 pt-4">
                            {weather.daily.map((d, i) => (
                                <div key={i} className="text-center p-2 rounded-lg bg-white/[.02]">
                                    <div className="text-[10px] text-gray-500 font-bold mb-1">
                                        {new Date(d.date).toLocaleDateString('en-US', { weekday: 'short' })}
                                    </div>
                                    <div className="text-lg font-bold">{Math.round(d.max_f)}°</div>
                                    <div className="text-xs text-gray-600">{Math.round(d.min_f)}°</div>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="h-48 flex items-center justify-center text-gray-600 text-sm animate-pulse">
                        {loading ? "Scanning atmosphere..." : "Select a location"}
                    </div>
                )}
            </div>
        </div>
    );
}
