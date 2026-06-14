"use client";

/// <reference types="@types/google.maps" />

import { useState, useEffect, useRef } from "react";
import { Minus, Plus, MapPin, Clock, ChevronRight, AlertCircle, X } from "lucide-react";
import styles from "./BookingForm.module.css"; // Reuse existing clean styles
import { PriceBreakdown } from "../utils/pricing";
import dynamic from "next/dynamic";
import { useJsApiLoader, Autocomplete } from "@react-google-maps/api";
import CalendarBooking from "./CalendarBooking";

const RouteMap = dynamic(() => import("./RouteMap"), {
    ssr: false,
    loading: () => <div className="w-full h-full bg-gray-900 animate-pulse" />
});

// Libraries for Google Maps - MUST be defined outside component to prevent re-initialization
const libraries: ("places" | "geometry" | "drawing" | "visualization")[] = ["places"];

export default function BookingEngine() {
    // Load Google Maps with Places library
    const { isLoaded } = useJsApiLoader({
        id: 'google-map-script',
        googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
        libraries
    });


    const [tripType, setTripType] = useState<'one-way' | 'round-trip'>('one-way');

    const [pickup, setPickup] = useState("");
    const [dropoff, setDropoff] = useState("");
    // Stop counters — $5 per stop per leg
    const [stopCount, setStopCount] = useState(0);
    const [stopAddresses, setStopAddresses] = useState<string[]>([]);
    const [returnStopCount, setReturnStopCount] = useState(0);
    const [returnStopAddresses, setReturnStopAddresses] = useState<string[]>([]);

    // Toast notification state
    const [toastMessage, setToastMessage] = useState<string | null>(null);

    // Autocomplete refs
    const pickupAutocompleteRef = useRef<google.maps.places.Autocomplete | null>(null);
    const dropoffAutocompleteRef = useRef<google.maps.places.Autocomplete | null>(null);
    const [layoverHours, setLayoverHours] = useState(0);

    // Wait Time (Single Trip)
    const [waitTimeHours, setWaitTimeHours] = useState(0);

    const [quote, setQuote] = useState<PriceBreakdown | null>(null);
    const [loading, setLoading] = useState(false);

    // Contact Form State (Visible after Quote)
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [phone, setPhone] = useState("");
    const [passengers, setPassengers] = useState(1);
    const [submitting, setSubmitting] = useState(false);
    const [showCalendar, setShowCalendar] = useState(false);
    const [bookingComplete, setBookingComplete] = useState(false);
    const [checkoutLoading, setCheckoutLoading] = useState(false);
    const [checkoutError, setCheckoutError] = useState('');

    // Auto-Calculate Quote when inputs change
    useEffect(() => {
        if (!pickup || !dropoff || pickup.length < 10 || dropoff.length < 10) {
            setQuote(null);
            return;
        }

        const fetchQuote = async () => {
            setLoading(true);
            setToastMessage(null); // Clear previous errors
            try {

                // Route through SWA linked backend proxy (function key stays in Azure)
                const res = await fetch('/api/quote', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        tripType,
                        pickup,
                        dropoff,
                        stops: stopAddresses.length > 0 ? stopAddresses : Array(stopCount).fill(''),
                        returnStops: returnStopAddresses.length > 0 ? returnStopAddresses : Array(returnStopCount).fill(''),
                        layoverHours: parseFloat(layoverHours.toString()) || 0,
                        waitTimeHours: parseFloat(waitTimeHours.toString()) || 0
                    })
                });
                if (!res.ok) {
                    console.error("Quote API Error:", res.status, res.statusText);
                    // Don't show toast for 404s (API deploying) to avoid spamming user while typing
                    if (res.status !== 404) {
                        setToastMessage(`Pricing Engine Unavailable (${res.status})`);
                    }
                    setQuote(null);
                    return;
                }

                const data = await res.json();
                if (data.success) {
                    setQuote(data.quote);
                } else {
                    console.error("Quote Logic Error:", data.error);

                    // Only show logic error toasts if the address looks like it could be real
                    // (prevents toast spam while typing "2" or "23")
                    const isPartialAddress = (pickup.length < 10 || dropoff.length < 10) && data.error === "NOT_FOUND";

                    if (!isPartialAddress) {
                        setToastMessage(data.error || "Failed to calculate pricing");
                    }

                    // We keep the old quote if it's just a partial address error to prevent map flashing
                    if (!isPartialAddress) {
                        setQuote(null);
                    }
                }
            } catch (e: any) {
                console.error("Fetch Error:", e);
                setToastMessage(`Connection Error: ${e.message}`);
            } finally {
                setLoading(false);
            }
        };

        const timeout = setTimeout(fetchQuote, 500); // Debounce
        return () => clearTimeout(timeout);

    }, [pickup, dropoff, stopCount, returnStopCount, stopAddresses, returnStopAddresses, tripType, layoverHours, waitTimeHours]);

    // Stop address helpers — keep arrays in sync with counts
    const handleStopCountChange = (newCount: number) => {
        const clamped = Math.max(0, Math.min(5, newCount));
        setStopCount(clamped);
        setStopAddresses(prev => {
            const next = [...prev];
            while (next.length < clamped) next.push('');
            return next.slice(0, clamped);
        });
    };
    const handleReturnStopCountChange = (newCount: number) => {
        const clamped = Math.max(0, Math.min(5, newCount));
        setReturnStopCount(clamped);
        setReturnStopAddresses(prev => {
            const next = [...prev];
            while (next.length < clamped) next.push('');
            return next.slice(0, clamped);
        });
    };
    const updateStopAddress = (idx: number, val: string) => {
        setStopAddresses(prev => { const a = [...prev]; a[idx] = val; return a; });
    };
    const updateReturnStopAddress = (idx: number, val: string) => {
        setReturnStopAddresses(prev => { const a = [...prev]; a[idx] = val; return a; });
    };

    // Validation: Check if address is outside Colorado
    const validateLocation = (address: string) => {
        const lower = address.toLowerCase();
        const isColorado = lower.includes('colorado') || lower.includes(', co');

        if (!isColorado) {
            setToastMessage('Note: You are booking a trip outside of our primary service area');
            setTimeout(() => setToastMessage(null), 5000); // Auto-dismiss after 5 seconds
        }
    };

    // Autocomplete configuration options
    const autocompleteOptions = {
        componentRestrictions: { country: "us" },
        fields: ["formatted_address", "geometry", "name"],
        // Soft bias toward Colorado Springs (not strict bounds)
        locationBias: {
            center: { lat: 38.8339, lng: -104.8214 }, // Colorado Springs
            radius: 50000 // 50km radius for soft bias
        }
    };

    return (
        <div className="w-full text-left font-sans">
            {/* Engine Logic */}

            {/* 1. Header */}
            <div className="flex justify-between items-center mb-8 border-b border-white/10 pb-6">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Trip Configuration</h2>
                    <p className="text-gray-400 text-sm mt-1 tracking-wide uppercase">COS Tesla LLC | Powered by: SummitOS</p>
                </div>

                {/* Trip Type Toggle */}
                <div className="bg-white/10 p-1 rounded-xl flex">
                    <button
                        onClick={() => setTripType('one-way')}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${tripType === 'one-way' ? 'bg-white text-black shadow-lg' : 'text-gray-400 hover:text-white'}`}
                    >
                        One Way
                    </button>
                    <button
                        onClick={() => setTripType('round-trip')}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${tripType === 'round-trip' ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-500/20' : 'text-gray-400 hover:text-white'}`}
                    >
                        Round Trip
                    </button>
                </div>
            </div>

            {/* Disclaimer Messaging */}
            <div className="mb-6 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-center">
                <p className="text-blue-200 text-xs font-medium tracking-wide">
                    Standardized rates for State Regulation compliance. No surge pricing. Ever.
                </p>
            </div>



            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">

                {/* LEFT: Inputs */}
                <div className="space-y-6">

                    {/* --- LEG 1 --- */}
                    <div className="relative group">
                        <label className="text-xs font-bold text-gray-500 tracking-widest uppercase mb-2 block">Origin</label>
                        {isLoaded ? (
                            <Autocomplete
                                onLoad={(autocomplete: google.maps.places.Autocomplete) => { pickupAutocompleteRef.current = autocomplete; }}
                                onPlaceChanged={() => {
                                    if (pickupAutocompleteRef.current) {
                                        const place = pickupAutocompleteRef.current.getPlace();
                                        const address = place.formatted_address || place.name || "";
                                        setPickup(address);
                                        validateLocation(address);
                                    }
                                }}
                                options={autocompleteOptions}
                            >
                                <input
                                    type="text"
                                    value={pickup}
                                    onChange={e => setPickup(e.target.value)}
                                    placeholder="e.g., 1 Lake Ave, Colorado Springs"
                                    className="w-full bg-white/5 border border-white/10 rounded-xl p-4 !text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                    style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                />
                            </Autocomplete>
                        ) : (
                            <input
                                type="text"
                                value={pickup}
                                onChange={e => setPickup(e.target.value)}
                                placeholder="e.g., 1194 Magnolia St"
                                className="w-full bg-white/5 border border-white/10 rounded-xl p-4 !text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                            />
                        )}
                    </div>



                    {/* Stop Counter */}
                    <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-4 space-y-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">Extra Stops</p>
                                <p className="text-[11px] text-gray-500 mt-0.5">$5.00 per stop, outbound leg</p>
                            </div>
                            {stopCount > 0 && (
                                <span className="text-xs font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-1 rounded-lg">
                                    +${(stopCount * 5).toFixed(2)}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => handleStopCountChange(stopCount - 1)}
                                disabled={stopCount === 0}
                                className="w-10 h-10 rounded-xl border border-white/10 bg-white/5 flex items-center justify-center text-gray-300 hover:bg-white/10 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                            >
                                <Minus size={16} />
                            </button>
                            <div className="flex-1 text-center">
                                <span className="text-3xl font-bold text-white tabular-nums">{stopCount}</span>
                                <span className="text-gray-500 text-sm ml-2">{stopCount === 1 ? 'stop' : 'stops'}</span>
                            </div>
                            <button
                                onClick={() => handleStopCountChange(stopCount + 1)}
                                disabled={stopCount === 5}
                                className="w-10 h-10 rounded-xl border border-cyan-500/30 bg-cyan-500/10 flex items-center justify-center text-cyan-400 hover:bg-cyan-500/20 hover:text-cyan-300 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                            >
                                <Plus size={16} />
                            </button>
                        </div>
                        {/* Optional address fields — animate in when stops > 0 */}
                        {stopCount > 0 && (
                            <div className="space-y-2 pt-2 border-t border-white/5 animate-in fade-in slide-in-from-top-2 duration-300">
                                <p className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Stop Addresses <span className="normal-case font-normal">(optional)</span></p>
                                {Array.from({ length: stopCount }).map((_, idx) => (
                                    <div key={idx} className="flex items-center gap-2">
                                        <span className="text-[10px] font-bold text-cyan-500/60 w-5 text-center">{idx + 1}</span>
                                        <input
                                            type="text"
                                            value={stopAddresses[idx] || ''}
                                            onChange={e => updateStopAddress(idx, e.target.value)}
                                            placeholder={`Stop ${idx + 1} address (optional)`}
                                            className="flex-1 bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm !text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors"
                                            style={{ color: '#ffffff', backgroundColor: 'rgba(0,0,0,0.2)' }}
                                        />
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="relative group pt-2">
                        <label className="text-xs font-bold text-gray-500 tracking-widest uppercase mb-2 block">
                            Destination
                        </label>
                        {isLoaded ? (
                            <Autocomplete
                                onLoad={(autocomplete: google.maps.places.Autocomplete) => { dropoffAutocompleteRef.current = autocomplete; }}
                                onPlaceChanged={() => {
                                    if (dropoffAutocompleteRef.current) {
                                        const place = dropoffAutocompleteRef.current.getPlace();
                                        const address = place.formatted_address || place.name || "";
                                        setDropoff(address);
                                        validateLocation(address);
                                    }
                                }}
                                options={autocompleteOptions}
                            >
                                <input
                                    type="text"
                                    value={dropoff}
                                    onChange={e => setDropoff(e.target.value)}
                                    placeholder="e.g., 1 Lake Ave, Colorado Springs"
                                    className="w-full bg-white/5 border border-white/10 rounded-xl p-4 !text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                    style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                />
                            </Autocomplete>
                        ) : (
                            <input
                                type="text"
                                value={dropoff}
                                onChange={e => setDropoff(e.target.value)}
                                placeholder="e.g., 1194 Magnolia St"
                                className="w-full bg-white/5 border border-white/10 rounded-xl p-4 !text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                            />
                        )}
                    </div>

                    {/* --- LAYOVER / WAIT TIME --- */}
                    <div className="pt-6 border-t border-white/10">
                        {tripType === 'round-trip' ? (
                            <div className="animate-in fade-in slide-in-from-top-4 duration-300 bg-white/5 p-4 rounded-xl border border-white/10">
                                <label className="flex items-center gap-3 mb-3">
                                    <Clock size={16} className="text-blue-400" />
                                    <span className="text-sm font-bold text-blue-100 uppercase tracking-widest">Layover Duration</span>
                                </label>
                                <div className="flex gap-4 items-center">
                                    <input
                                        type="number"
                                        min="0"
                                        max="24"
                                        step="0.5"
                                        value={layoverHours}
                                        onChange={e => setLayoverHours(parseFloat(e.target.value) || 0)}
                                        className="w-20 bg-black/30 border border-blue-500/30 rounded-lg p-2 text-center !text-white font-mono text-lg focus:border-blue-500 focus:outline-none"
                                        style={{ color: '#ffffff', backgroundColor: 'rgba(0, 0, 0, 0.3)', borderColor: 'rgba(59, 130, 246, 0.3)' }}
                                    />
                                    <span className="text-gray-400 text-sm">Hours @ $20/hr</span>
                                </div>
                            </div>
                        ) : (
                            <div className="animate-in fade-in slide-in-from-top-4 duration-300 bg-white/5 p-4 rounded-xl border border-white/10">
                                <label className="flex items-center gap-3 mb-3">
                                    <Clock size={16} className="text-cyan-400" />
                                    <span className="text-sm font-bold text-cyan-100 uppercase tracking-widest">Driver Wait Time</span>
                                </label>
                                <div className="flex gap-4 items-center">
                                    <input
                                        type="number"
                                        min="0"
                                        max="24"
                                        step="0.5"
                                        value={waitTimeHours}
                                        onChange={e => setWaitTimeHours(parseFloat(e.target.value) || 0)}
                                        className="w-20 bg-black/30 border border-cyan-500/30 rounded-lg p-2 text-center !text-white font-mono text-lg focus:border-cyan-500 focus:outline-none"
                                        style={{ color: '#ffffff', backgroundColor: 'rgba(0, 0, 0, 0.3)', borderColor: 'rgba(6, 182, 212, 0.3)' }}
                                    />
                                    <span className="text-gray-400 text-sm">Hours @ $20/hr</span>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* --- LEG 2 (Round Trip Only) --- */}
                    {tripType === 'round-trip' && (
                        <div className="pt-6 border-t border-white/10 animate-in fade-in slide-in-from-top-10 duration-500">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="h-6 w-1 bg-cyan-600 rounded-full"></div>
                                <h4 className="text-lg font-bold text-white uppercase tracking-tight">Return Journey</h4>
                            </div>

                            <div className="pl-4 border-l-2 border-white/5 space-y-4">
                                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                                        <MapPin size={16} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <label className="text-[10px] font-bold text-cyan-500/70 tracking-widest uppercase mb-0.5 block">Return Origin</label>
                                        <div className="text-sm text-gray-300 truncate font-medium">
                                            {dropoff || <span className="text-gray-500 italic">Enter destination above</span>}
                                        </div>
                                    </div>
                                </div>

                                {/* Return Stop Counter */}
                                <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-4 space-y-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">Return Stops</p>
                                            <p className="text-[11px] text-gray-500 mt-0.5">$5.00 per stop, return leg</p>
                                        </div>
                                        {returnStopCount > 0 && (
                                            <span className="text-xs font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-1 rounded-lg">
                                                +${(returnStopCount * 5).toFixed(2)}
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <button
                                            onClick={() => handleReturnStopCountChange(returnStopCount - 1)}
                                            disabled={returnStopCount === 0}
                                            className="w-10 h-10 rounded-xl border border-white/10 bg-white/5 flex items-center justify-center text-gray-300 hover:bg-white/10 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                                        >
                                            <Minus size={16} />
                                        </button>
                                        <div className="flex-1 text-center">
                                            <span className="text-3xl font-bold text-white tabular-nums">{returnStopCount}</span>
                                            <span className="text-gray-500 text-sm ml-2">{returnStopCount === 1 ? 'stop' : 'stops'}</span>
                                        </div>
                                        <button
                                            onClick={() => handleReturnStopCountChange(returnStopCount + 1)}
                                            disabled={returnStopCount === 5}
                                            className="w-10 h-10 rounded-xl border border-cyan-500/30 bg-cyan-500/10 flex items-center justify-center text-cyan-400 hover:bg-cyan-500/20 hover:text-cyan-300 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                                        >
                                            <Plus size={16} />
                                        </button>
                                    </div>
                                    {/* Optional return address fields */}
                                    {returnStopCount > 0 && (
                                        <div className="space-y-2 pt-2 border-t border-white/5 animate-in fade-in slide-in-from-top-2 duration-300">
                                            <p className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Stop Addresses <span className="normal-case font-normal">(optional)</span></p>
                                            {Array.from({ length: returnStopCount }).map((_, idx) => (
                                                <div key={idx} className="flex items-center gap-2">
                                                    <span className="text-[10px] font-bold text-cyan-500/60 w-5 text-center">{idx + 1}</span>
                                                    <input
                                                        type="text"
                                                        value={returnStopAddresses[idx] || ''}
                                                        onChange={e => updateReturnStopAddress(idx, e.target.value)}
                                                        placeholder={`Return stop ${idx + 1} address (optional)`}
                                                        className="flex-1 bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm !text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors"
                                                        style={{ color: '#ffffff', backgroundColor: 'rgba(0,0,0,0.2)' }}
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                                        <MapPin size={16} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <label className="text-[10px] font-bold text-cyan-500/70 tracking-widest uppercase mb-0.5 block">Return Destination</label>
                                        <div className="text-sm text-gray-300 truncate font-medium">
                                            {pickup || <span className="text-gray-500 italic">Enter origin above</span>}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* RIGHT: Visuals & Quote */}
                <div className="flex flex-col h-full">
                    {/* LIVE MAP INTEGRATION */}
                    <div className="w-full h-48 rounded-2xl border border-white/10 mb-6 overflow-hidden shadow-2xl relative z-0">
                        {/* Only load map if we have inputs */}
                        {(pickup || dropoff) ? (
                            <RouteMap
                                pickupAddress={quote?.debug?.origin || pickup} // Use Validated if available
                                dropoffAddress={quote?.debug?.destination || dropoff} // Use Validated if available
                                stops={[]} // Stops are now count-only; no addresses to display
                            />
                        ) : (
                            <div className="w-full h-full bg-gradient-to-br from-gray-900 to-black flex items-center justify-center">
                                <span className="text-gray-500 text-sm">Enter locations to see route</span>
                            </div>
                        )}

                        {/* Round Trip Badge Overlay */}
                        {tripType === 'round-trip' && (
                            <div className="absolute bottom-2 right-2 bg-cyan-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow-lg uppercase tracking-widest z-10">
                                Round Trip Active
                            </div>
                        )}

                        {/* Open in Google Maps Button */}
                        {(pickup || dropoff) && (
                            <a
                                href={`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(pickup)}&destination=${encodeURIComponent(dropoff)}`}
                                target="_blank"
                                rel="noreferrer"
                                className="absolute top-2 right-2 bg-white/10 hover:bg-white/20 hover:text-white backdrop-blur-md text-gray-300 p-2 rounded-lg transition-all z-10 border border-white/10 shadow-lg"
                                title="Open in Google Maps"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                            </a>
                        )}
                    </div>

                    {/* Quote Card */}
                    <div className="flex-1 bg-white/5 rounded-2xl p-6 border border-white/10 flex flex-col justify-between">
                        <div>
                            <h3 className="text-gray-400 text-xs font-bold tracking-widest uppercase mb-4">Pricing Breakdown</h3>

                            {quote ? (
                                <div className="space-y-3">
                                    <div className="flex justify-between text-sm text-gray-300">
                                        <span>Base Fare</span>
                                        <span>${quote.baseFare.toFixed(2)}</span>
                                    </div>
                                    {quote.overage > 0 && (
                                        <div className="flex justify-between text-sm text-gray-300">
                                            <span>Mileage Overage</span>
                                            <span>${quote.overage.toFixed(2)}</span>
                                        </div>
                                    )}
                                    {quote.deadheadFee > 0 && (
                                        <div className="flex justify-between text-sm text-cyan-300">
                                            <span>Dispatch Fee (Deadhead)</span>
                                            <span>${quote.deadheadFee.toFixed(2)}</span>
                                        </div>
                                    )}
                                    {quote.stopFee > 0 && (
                                        <div className="flex justify-between text-sm text-gray-300">
                                            <span>Extra Stops ({stopCount + returnStopCount}×)</span>
                                            <span>${quote.stopFee.toFixed(2)}</span>
                                        </div>
                                    )}
                                    {quote.tellerFee > 0 && (
                                        <div className="flex justify-between text-sm text-yellow-300">
                                            <span>Mountain Surcharge</span>
                                            <span>${quote.tellerFee.toFixed(2)}</span>
                                        </div>
                                    )}
                                    {quote.waitFee > 0 && (
                                        <div className="flex justify-between text-sm text-blue-300">
                                            <span>Wait Time ({quote.waitFee / 20} hr)</span>
                                            <span>${quote.waitFee.toFixed(2)}</span>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="text-center text-gray-500 py-8 italic">
                                    Enter route to calculate...
                                </div>
                            )}
                        </div>

                        <div className="mt-6 pt-6 border-t border-white/10">
                            <div className="flex justify-between items-end mb-6">
                                <span className="text-gray-400">Total Estimate</span>
                                <span className="text-4xl font-bold text-white">
                                    {loading ? <span className="animate-pulse">...</span> : (quote ? `$${quote.total.toFixed(2)}` : "$0.00")}
                                </span>
                            </div>

                            {/* Contact Form (Visible after Quote) */}
                            {quote && (
                                <div className="space-y-3 mb-6 animate-in fade-in slide-in-from-top-4 duration-300">
                                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Contact Information</h4>
                                    <input
                                        type="text"
                                        placeholder="Full Name"
                                        value={name}
                                        onChange={e => setName(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 !text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                        style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                    />
                                    <input
                                        type="email"
                                        placeholder="Email Address"
                                        value={email}
                                        onChange={e => setEmail(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 !text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                        style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                    />
                                    <input
                                        type="tel"
                                        placeholder="Phone Number"
                                        value={phone}
                                        onChange={e => setPhone(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 !text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                        style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                    />
                                    <input
                                        type="number"
                                        min="1"
                                        max="6"
                                        placeholder="# of Passengers"
                                        value={passengers}
                                        onChange={e => setPassengers(parseInt(e.target.value) || 1)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 !text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                        style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                    />
                                </div>
                            )}

                            {/* Calendar Booking or Checkout Button */}
                            {showCalendar ? (
                                <CalendarBooking
                                    customerName={name}
                                    customerEmail={email}
                                    customerPhone={phone}
                                    passengers={passengers}
                                    pickup={quote?.debug?.origin || pickup}
                                    dropoff={quote?.debug?.destination || dropoff}
                                    price={quote ? `$${quote.total.toFixed(2)}` : '$0.00'}
                                    tripDistance={quote?.distance?.toFixed(1) || undefined}
                                    tripDuration={quote?.time?.toString() || undefined}
                                    onBookingComplete={(eventId) => {
                                        console.log('✅ Booking complete:', eventId);
                                        setBookingComplete(true);
                                    }}
                                />
                            ) : bookingComplete ? (
                                <div className="text-center py-8 bg-green-500/10 rounded-xl border border-green-500/30">
                                    <div className="text-4xl mb-2">✅</div>
                                    <h4 className="text-xl font-bold text-white mb-2">Booking Confirmed!</h4>
                                    <p className="text-sm text-gray-300">You'll receive a confirmation email shortly.</p>
                                </div>
                            ) : (
                                // --- Continue to Calendar ---
                                <button
                                    onClick={() => {
                                        if (!name || !email || !phone) {
                                            alert('Please fill in all contact information');
                                            return;
                                        }
                                        setShowCalendar(true);
                                    }}
                                    disabled={!name || !email || !phone}
                                    className={`w-full bg-cyan-600 text-white font-bold py-4 rounded-xl hover:bg-cyan-700 shadow-lg shadow-cyan-500/20 flex justify-center items-center gap-2 text-lg transition-all ${(!name || !email || !phone) ? 'opacity-50 cursor-not-allowed' : ''}`}
                                >
                                    Continue to Date Selection <ChevronRight />
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>



            {/* Toast Notification */}
            {toastMessage && (
                <div className="fixed bottom-8 right-8 z-50 animate-in slide-in-from-bottom-4 fade-in duration-300">
                    <div className="bg-yellow-500/10 border border-yellow-500/30 backdrop-blur-xl rounded-xl p-4 shadow-2xl max-w-md">
                        <div className="flex items-start gap-3">
                            <AlertCircle className="text-yellow-400 flex-shrink-0 mt-0.5" size={20} />
                            <div className="flex-1">
                                <p className="text-yellow-100 text-sm font-medium">{toastMessage}</p>
                            </div>
                            <button
                                onClick={() => setToastMessage(null)}
                                className="text-yellow-400 hover:text-yellow-300 transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
}
