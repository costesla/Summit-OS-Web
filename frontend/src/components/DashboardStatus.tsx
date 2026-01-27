"use client";

import { useEffect, useState } from "react";
import { Cloud, Battery, TrendingUp, Navigation } from "lucide-react";

interface DashboardData {
    stats: {
        TotalEarnings: number;
        TotalTips: number;
        TripCount: number;
    };
    weather: {
        Temperature_F: number | string;
        Condition: string;
    };
    telematics: {
        battery_level: number;
        charge_limit_soc: number;
        charging_state: string;
        latitude: number;
        longitude: number;
        speed: number;
    };
}

export default function DashboardStatus() {
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Direct fetch to Azure Function Backend
                const res = await fetch('https://summitos-api.azurewebsites.net/api/dashboard-summary');
                if (res.ok) {
                    const json = await res.json();
                    setData(json);
                }
            } catch (err) {
                console.error("Failed to fetch dashboard summary", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        // Poll every 30 seconds
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div className="text-xs text-gray-500 animate-pulse">Connecting to SummitOS Neural Net...</div>;
    if (!data) return null;

    return (
        <div className="bg-[#111] border border-white/10 rounded-3xl p-6 space-y-6">
            <h3 className="text-xs font-bold uppercase tracking-widest text-cyan-400 flex items-center gap-2">
                <span className="w-2 h-2 bg-cyan-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(6,182,212,0.5)]"></span>
                System Status
            </h3>

            <div className="grid grid-cols-2 gap-4">
                {/* Weather */}
                <div className="bg-white/5 p-4 rounded-2xl">
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                        <Cloud size={16} />
                        <span className="text-xs uppercase">Conditions</span>
                    </div>
                    <div className="text-2xl font-bold">{data.weather.Temperature_F}°F</div>
                    <div className="text-xs text-gray-500">{data.weather.Condition}</div>
                </div>

                {/* Battery */}
                <div className="bg-white/5 p-4 rounded-2xl">
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                        <Battery size={16} />
                        <span className="text-xs uppercase">Energy</span>
                    </div>
                    <div className="text-2xl font-bold">{data.telematics.battery_level}%</div>
                    <div className="text-xs text-gray-500">{data.telematics.charging_state}</div>
                </div>

                {/* Stats */}
                <div className="bg-white/5 p-4 rounded-2xl">
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                        <TrendingUp size={16} />
                        <span className="text-xs uppercase">Activity</span>
                    </div>
                    <div className="text-2xl font-bold">{data.stats.TripCount}</div>
                    <div className="text-xs text-gray-500">Trips Completed</div>
                </div>

                {/* Location */}
                <div className="bg-white/5 p-4 rounded-2xl">
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                        <Navigation size={16} />
                        <span className="text-xs uppercase">Speed</span>
                    </div>
                    <div className="text-2xl font-bold">{data.telematics.speed} MPH</div>
                    <div className="text-xs text-gray-500">
                        {data.telematics.latitude.toFixed(4)}, {data.telematics.longitude.toFixed(4)}
                    </div>
                </div>
            </div>
        </div>
    );
}
