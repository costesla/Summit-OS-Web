"use client";

import { useEffect, useState } from "react";
import { Battery, Zap, Moon, AlertCircle } from "lucide-react";

interface CarStatus {
    vin: string;
    name: string;
    battery_level: number;
    battery_range: number;
    is_charging: boolean;
    status: string;
}

export default function BatteryWidget() {
    const [data, setData] = useState<CarStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    useEffect(() => {
        async function fetchStatus() {
            try {
                const res = await fetch("/api/car-status");
                if (!res.ok) throw new Error("Failed");
                const json = await res.json();
                setData(json);
            } catch (e) {
                setError(true);
            } finally {
                setLoading(false);
            }
        }

        fetchStatus();
        // Refresh every 5 minutes (300000ms) to be polite to API limits
        const interval = setInterval(fetchStatus, 300000);
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="bg-black/40 backdrop-blur-md border border-white/10 rounded-2xl p-6 h-full flex flex-col justify-center items-center animate-pulse">
                <Battery className="w-8 h-8 text-gray-600 mb-2" />
                <div className="h-2 w-20 bg-gray-700 rounded full"></div>
            </div>
        );
    }

    if (error || !data) {
        return (
            <div className="bg-black/40 backdrop-blur-md border border-white/10 rounded-2xl p-6 h-full flex flex-col justify-center items-center text-center">
                <AlertCircle className="w-8 h-8 text-red-400 mb-2 opacity-80" />
                <span className="text-xs text-gray-400 uppercase tracking-widest">Connection Lost</span>
            </div>
        );
    }

    const isSleeping = data.status === "Sleeping";
    const batteryColor = data.battery_level > 20 ? "text-green-400" : "text-red-400";
    const progressColor = data.battery_level > 20 ? "bg-green-500" : "bg-red-500";

    return (
        <div className="bg-black/40 backdrop-blur-md border border-white/10 rounded-2xl p-6 h-full flex flex-col justify-between relative overflow-hidden group hover:border-green-500/30 transition-all cursor-default">
            {/* Background Glow */}
            <div className={`absolute top-0 right-0 w-32 h-32 bg-green-500/10 blur-[50px] rounded-full -translate-y-1/2 translate-x-1/2`}></div>

            {/* Header */}
            <div className="flex justify-between items-start z-10">
                <div>
                    <h3 className="text-white font-medium text-lg tracking-tight">{data.name}</h3>
                    <p className="text-xs text-gray-400 uppercase tracking-widest mt-1 flex items-center gap-1">
                        {isSleeping ? <Moon className="w-3 h-3" /> : <Zap className="w-3 h-3 text-yellow-400" />}
                        {isSleeping ? "Asleep" : "Online"}
                    </p>
                </div>
                <div className={`${batteryColor} font-bold text-2xl flex items-center gap-1`}>
                    {isSleeping ? (
                        <span className="text-gray-500 text-lg">--%</span>
                    ) : (
                        <>{data.battery_level}%</>
                    )}
                </div>
            </div>

            {/* Main Stat (Range) */}
            <div className="mt-4 z-10">
                <div className="flex items-baseline gap-1">
                    <span className="text-4xl font-bold text-white">
                        {isSleeping ? "💤" : data.battery_range}
                    </span>
                    {!isSleeping && <span className="text-sm text-gray-400 font-medium">mi</span>}
                </div>
                <p className="text-xs text-gray-500 mt-1">Estimated Range</p>
            </div>

            {/* Progress Bar */}
            <div className="mt-6 w-full h-1.5 bg-gray-800 rounded-full overflow-hidden z-10">
                <div
                    className={`h-full ${progressColor} transition-all duration-1000`}
                    style={{ width: isSleeping ? '0%' : `${data.battery_level}%` }}
                ></div>
            </div>
        </div>
    );
}
