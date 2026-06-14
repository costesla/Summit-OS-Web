"use client";

import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import {
    Navigation,
    Zap,
    Shield,
    ShieldOff,
    Wifi,
    WifiOff,
    Gauge,
    Thermometer,
    Battery,
    Play,
    Square,
    RefreshCw
} from "lucide-react";

const LiveMap = dynamic(() => import("@/components/LiveMap"), {
    ssr: false,
    loading: () => <div className="h-[600px] flex items-center justify-center bg-slate-900 text-blue-500 font-mono">INITIALIZING EMULATOR ENGINE...</div>
});

// Colorado Springs Bounds
const COS_LAT = 38.8339;
const COS_LONG = -104.8214;

export default function EmulatorPage() {
    const [lat, setLat] = useState(COS_LAT);
    const [lng, setLng] = useState(COS_LONG);
    const [speed, setSpeed] = useState(0);
    const [heading, setHeading] = useState(0);
    const [battery, setBattery] = useState(85);
    const [tempInt, setTempInt] = useState(72);
    const [tempExt, setTempExt] = useState(45);
    const [privacy, setPrivacy] = useState(false);
    const [status, setStatus] = useState("Active");
    const [isBroadcasting, setIsBroadcasting] = useState(false);
    const [isSimulating, setIsSimulating] = useState(false);

    // Broadcast Channel
    const [channel, setChannel] = useState<BroadcastChannel | null>(null);

    useEffect(() => {
        const bc = new BroadcastChannel('live_map_sync');
        setChannel(bc);
        return () => bc.close();
    }, []);

    const broadcast = useCallback(() => {
        if (!channel) return;

        const payload = {
            lat,
            long: lng,
            speed,
            heading,
            privacy,
            status,
            current_soc: battery,
            inside_temp: (tempInt - 32) * 5/9, // Convert back to C for backend-like consistency
            outside_temp: (tempExt - 32) * 5/9,
            updatedAt: new Date().toISOString()
        };

        channel.postMessage({ type: 'SYNC', payload });
    }, [channel, lat, lng, speed, heading, privacy, status, battery, tempInt, tempExt]);

    // Auto-broadcast if enabled
    useEffect(() => {
        if (isBroadcasting) {
            const iv = setInterval(broadcast, 1000);
            return () => clearInterval(iv);
        }
    }, [isBroadcasting, broadcast]);

    // Simple Simulation Logic: Drive in a circle
    useEffect(() => {
        if (isSimulating) {
            const iv = setInterval(() => {
                setHeading(h => (h + 5) % 360);
                setSpeed(45);
                setLat(l => l + 0.0001 * Math.cos(heading * Math.PI / 180));
                setLng(l => l + 0.0001 * Math.sin(heading * Math.PI / 180));
            }, 100);
            return () => clearInterval(iv);
        } else {
            setSpeed(0);
        }
    }, [isSimulating, heading]);

    return (
        <main className="min-h-screen bg-[#05080a] text-slate-300 p-4 md:p-8 font-sans">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/50 border border-white/10 p-6 rounded-3xl backdrop-blur-xl">
                    <div>
                        <div className="flex items-center gap-3 text-blue-500 mb-1">
                            <Navigation size={20} className="animate-pulse" />
                            <h1 className="text-xl font-black tracking-tighter uppercase">SummitOS System Emulator</h1>
                        </div>
                        <p className="text-xs font-mono text-slate-500">VERSION 2.1.0 • SIMULATION LAYER ACTIVE</p>
                    </div>

                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => setIsBroadcasting(!isBroadcasting)}
                            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl font-bold text-xs uppercase tracking-widest transition-all ${
                                isBroadcasting
                                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                                : 'bg-slate-800 text-slate-400 hover:text-white border border-white/5'
                            }`}
                        >
                            {isBroadcasting ? <Wifi size={14} /> : <WifiOff size={14} />}
                            {isBroadcasting ? 'Broadcasting' : 'Start Broadcast'}
                        </button>

                        <button
                            onClick={() => setIsSimulating(!isSimulating)}
                            className={`flex items-center gap-2 px-6 py-2.5 rounded-xl font-bold text-xs uppercase tracking-widest transition-all ${
                                isSimulating
                                ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-500/20'
                                : 'bg-slate-800 text-slate-400 hover:text-white border border-white/5'
                            }`}
                        >
                            {isSimulating ? <Square size={14} /> : <Play size={14} />}
                            {isSimulating ? 'Stop Simulation' : 'Run Scenario'}
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                    {/* LEFT: Map Panel */}
                    <div className="lg:col-span-8 space-y-6">
                        <div className="relative group">
                            <LiveMap
                                className="h-[600px] w-full rounded-3xl border border-white/10 overflow-hidden shadow-2xl"
                                overridePos={{
                                    lat,
                                    long: lng,
                                    speed,
                                    heading,
                                    privacy,
                                    status
                                }}
                            />

                            {/* Map Overlays */}
                            <div className="absolute top-6 left-6 z-10 flex flex-col gap-2">
                                <div className="bg-black/60 backdrop-blur-md border border-white/10 px-4 py-2 rounded-xl text-[10px] font-mono">
                                    <span className="text-blue-500 font-bold">LAT:</span> {lat.toFixed(6)}<br/>
                                    <span className="text-blue-500 font-bold">LNG:</span> {lng.toFixed(6)}
                                </div>
                            </div>
                        </div>

                        {/* Telemetry Cards */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div className="bg-slate-900/40 border border-white/10 p-4 rounded-2xl flex items-center gap-4">
                                <div className="p-2 bg-blue-500/10 rounded-lg text-blue-500"><Gauge size={20}/></div>
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 uppercase">Speed</p>
                                    <p className="text-xl font-black text-white">{Math.round(speed)} <span className="text-[10px] font-normal text-slate-500">MPH</span></p>
                                </div>
                            </div>
                            <div className="bg-slate-900/40 border border-white/10 p-4 rounded-2xl flex items-center gap-4">
                                <div className="p-2 bg-amber-500/10 rounded-lg text-amber-500"><Battery size={20}/></div>
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 uppercase">Battery</p>
                                    <p className="text-xl font-black text-white">{battery}<span className="text-[10px] font-normal text-slate-500">%</span></p>
                                </div>
                            </div>
                            <div className="bg-slate-900/40 border border-white/10 p-4 rounded-2xl flex items-center gap-4">
                                <div className="p-2 bg-rose-500/10 rounded-lg text-rose-500"><Thermometer size={20}/></div>
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 uppercase">Internal</p>
                                    <p className="text-xl font-black text-white">{tempInt}<span className="text-[10px] font-normal text-slate-500">°F</span></p>
                                </div>
                            </div>
                            <div className="bg-slate-900/40 border border-white/10 p-4 rounded-2xl flex items-center gap-4">
                                <div className={`p-2 rounded-lg ${privacy ? 'bg-rose-500/10 text-rose-500' : 'bg-emerald-500/10 text-emerald-500'}`}>
                                    {privacy ? <Shield size={20}/> : <ShieldOff size={20}/>}
                                </div>
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 uppercase">Privacy</p>
                                    <p className="text-xl font-black text-white uppercase">{privacy ? 'ON' : 'OFF'}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* RIGHT: Controls Panel */}
                    <div className="lg:col-span-4 space-y-6">
                        <div className="bg-slate-900/50 border border-white/10 p-6 rounded-3xl backdrop-blur-xl h-full space-y-8">

                            <div>
                                <h3 className="text-xs font-bold text-blue-500 uppercase tracking-widest mb-6">Navigation Controls</h3>
                                <div className="space-y-6">
                                    <div>
                                        <div className="flex justify-between text-[10px] mb-2">
                                            <span>Latitude</span>
                                            <span className="text-blue-400 font-mono">{lat.toFixed(6)}</span>
                                        </div>
                                        <input
                                            type="range" min={COS_LAT - 0.2} max={COS_LAT + 0.2} step={0.0001}
                                            value={lat} onChange={e => setLat(parseFloat(e.target.value))}
                                            className="w-full accent-blue-600 bg-slate-800 rounded-lg h-1.5"
                                        />
                                    </div>
                                    <div>
                                        <div className="flex justify-between text-[10px] mb-2">
                                            <span>Longitude</span>
                                            <span className="text-blue-400 font-mono">{lng.toFixed(6)}</span>
                                        </div>
                                        <input
                                            type="range" min={COS_LONG - 0.2} max={COS_LONG + 0.2} step={0.0001}
                                            value={lng} onChange={e => setLng(parseFloat(e.target.value))}
                                            className="w-full accent-blue-600 bg-slate-800 rounded-lg h-1.5"
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <div className="flex justify-between text-[10px] mb-2">
                                                <span>Heading</span>
                                                <span className="text-blue-400 font-mono">{heading}°</span>
                                            </div>
                                            <input
                                                type="range" min={0} max={359} step={1}
                                                value={heading} onChange={e => setHeading(parseInt(e.target.value))}
                                                className="w-full accent-blue-600 bg-slate-800 rounded-lg h-1.5"
                                            />
                                        </div>
                                        <div>
                                            <div className="flex justify-between text-[10px] mb-2">
                                                <span>Speed</span>
                                                <span className="text-blue-400 font-mono">{speed} MPH</span>
                                            </div>
                                            <input
                                                type="range" min={0} max={100} step={1}
                                                value={speed} onChange={e => setSpeed(parseInt(e.target.value))}
                                                className="w-full accent-blue-600 bg-slate-800 rounded-lg h-1.5"
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="pt-8 border-t border-white/5">
                                <h3 className="text-xs font-bold text-amber-500 uppercase tracking-widest mb-6">System Status</h3>
                                <div className="space-y-6">
                                    <div className="grid grid-cols-2 gap-4">
                                        <button
                                            onClick={() => setPrivacy(!privacy)}
                                            className={`p-4 rounded-2xl border transition-all text-center ${
                                                privacy
                                                ? 'bg-rose-500/10 border-rose-500/30 text-rose-500'
                                                : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'
                                            }`}
                                        >
                                            <Shield className="mx-auto mb-2" size={24} />
                                            <p className="text-[10px] font-bold uppercase">{privacy ? 'Privacy On' : 'Public GPS'}</p>
                                        </button>
                                        <button
                                            onClick={() => setStatus(status === 'Active' ? 'Charging' : 'Active')}
                                            className={`p-4 rounded-2xl border transition-all text-center ${
                                                status === 'Charging'
                                                ? 'bg-amber-500/10 border-amber-500/30 text-amber-500'
                                                : 'bg-blue-500/10 border-blue-500/30 text-blue-500'
                                            }`}
                                        >
                                            <Zap className="mx-auto mb-2" size={24} />
                                            <p className="text-[10px] font-bold uppercase">{status}</p>
                                        </button>
                                    </div>

                                    <div>
                                        <div className="flex justify-between text-[10px] mb-2">
                                            <span>Battery Level</span>
                                            <span className="text-amber-400 font-mono">{battery}%</span>
                                        </div>
                                        <input
                                            type="range" min={0} max={100} step={1}
                                            value={battery} onChange={e => setBattery(parseInt(e.target.value))}
                                            className="w-full accent-amber-500 bg-slate-800 rounded-lg h-1.5"
                                        />
                                    </div>

                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <div className="flex justify-between text-[10px] mb-2">
                                                <span>Int Temp</span>
                                                <span className="text-rose-400 font-mono">{tempInt}°F</span>
                                            </div>
                                            <input
                                                type="range" min={32} max={100} step={1}
                                                value={tempInt} onChange={e => setTempInt(parseInt(e.target.value))}
                                                className="w-full accent-rose-600 bg-slate-800 rounded-lg h-1.5"
                                            />
                                        </div>
                                        <div>
                                            <div className="flex justify-between text-[10px] mb-2">
                                                <span>Ext Temp</span>
                                                <span className="text-slate-400 font-mono">{tempExt}°F</span>
                                            </div>
                                            <input
                                                type="range" min={-10} max={110} step={1}
                                                value={tempExt} onChange={e => setTempExt(parseInt(e.target.value))}
                                                className="w-full accent-slate-600 bg-slate-800 rounded-lg h-1.5"
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="pt-8 border-t border-white/5">
                                <button
                                    onClick={() => {
                                        setLat(COS_LAT);
                                        setLng(COS_LONG);
                                        setSpeed(0);
                                        setHeading(0);
                                        setStatus("Active");
                                        setPrivacy(false);
                                    }}
                                    className="w-full py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-xs font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-2"
                                >
                                    <RefreshCw size={14} />
                                    Reset Emulator
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer Info */}
                <div className="text-center py-6">
                    <p className="text-[10px] font-mono text-slate-600 tracking-[0.4em] uppercase">
                        SummitOS Governed Simulation Environment • Access Restricted
                    </p>
                </div>
            </div>
        </main>
    );
}
