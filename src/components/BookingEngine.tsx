"use client";

/// <reference types="@types/google.maps" />

import { useState, useEffect, useRef } from "react";
import { Plus, X, MapPin, Clock, DollarSign, ChevronRight, AlertCircle } from "lucide-react";
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
    const [stops, setStops] = useState<string[]>([]);

    // Toast notification state
    const [toastMessage, setToastMessage] = useState<string | null>(null);

    // Autocomplete refs
    const pickupAutocompleteRef = useRef<google.maps.places.Autocomplete | null>(null);
    const dropoffAutocompleteRef = useRef<google.maps.places.Autocomplete | null>(null);
    const stopAutocompleteRefs = useRef<(google.maps.places.Autocomplete | null)[]>([]);
    const returnStopAutocompleteRefs = useRef<(google.maps.places.Autocomplete | null)[]>([]);

    // Return Leg State
    const [returnStops, setReturnStops] = useState<string[]>([]);
    const [layoverHours, setLayoverHours] = useState(0);

    // Old Wait Time Toggle (Keep for One-Way, disable for Round Trip if Layover used)
    const [waitTime, setWaitTime] = useState(false);

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

    // Auto-Calculate Quote when inputs change
    useEffect(() => {
        if (!pickup || !dropoff) {
            setQuote(null);
            return;
        }

        const fetchQuote = async () => {
            setLoading(true);
            try {




                const res = await fetch('/api/quote', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tripType,
                        pickup: pickup, // Send Raw
                        dropoff: dropoff, // Send Raw
                        stops: stops, // Send Raw
                        returnStops: returnStops, // Send Raw
                        layoverHours,
                        simpleWaitTime: waitTime // For one-way
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
                    setToastMessage(data.error || "Failed to calculate pricing");
                    setQuote(null);
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

    }, [pickup, dropoff, stops, returnStops, tripType, layoverHours, waitTime]);

    const addStop = () => { if (stops.length < 5) setStops([...stops, ""]); };
    const updateStop = (index: number, val: string) => { const newStops = [...stops]; newStops[index] = val; setStops(newStops); };
    const removeStop = (index: number) => { const newStops = stops.filter((_, i) => i !== index); setStops(newStops); };

    const addReturnStop = () => { if (returnStops.length < 5) setReturnStops([...returnStops, ""]); };
    const updateReturnStop = (index: number, val: string) => { const newStops = [...returnStops]; newStops[index] = val; setReturnStops(newStops); };
    const removeReturnStop = (index: number) => { const newStops = returnStops.filter((_, i) => i !== index); setReturnStops(newStops); };

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
                    <p className="text-gray-400 text-sm mt-1 tracking-wide uppercase">SummitOS Engine v2.1</p>
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
                                    className="w-full bg-white/5 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                />
                            </Autocomplete>
                        ) : (
                            <input
                                type="text"
                                value={pickup}
                                onChange={e => setPickup(e.target.value)}
                                placeholder="e.g., 1194 Magnolia St"
                                className="w-full bg-white/5 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                            />
                        )}
                    </div>

                    {stops.map((stop, idx) => (
                        <div key={idx} className="relative flex gap-2 items-end animate-in slide-in-from-left-4 fade-in duration-300">
                            <div className="flex-1">
                                <label className="text-[10px] font-bold text-cyan-400 tracking-widest uppercase mb-1 block">Stop #{idx + 1} (+ $5.00)</label>
                                <input
                                    type="text"
                                    value={stop}
                                    onChange={e => updateStop(idx, e.target.value)}
                                    placeholder="Add Stop..."
                                    className="w-full bg-white/5 border border-cyan-500/30 rounded-xl p-3 text-white focus:outline-none focus:border-cyan-500 transition-colors"
                                />
                            </div>
                            <button onClick={() => removeStop(idx)} className="p-4 bg-white/5 hover:bg-cyan-500/20 rounded-xl border border-white/10 transition-colors text-gray-400 hover:text-cyan-400">
                                <X size={20} />
                            </button>
                        </div>
                    ))}

                    {stops.length < 5 && (
                        <button onClick={addStop} className="text-sm text-gray-400 hover:text-white flex items-center gap-2 transition-colors pl-1">
                            <Plus size={16} /> Add Stop
                        </button>
                    )}

                    <div className="relative group pt-2">
                        <label className="text-xs font-bold text-gray-500 tracking-widest uppercase mb-2 block">Destination</label>
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
                                    className="w-full bg-white/5 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                />
                            </Autocomplete>
                        ) : (
                            <input
                                type="text"
                                value={dropoff}
                                onChange={e => setDropoff(e.target.value)}
                                placeholder="e.g., 1194 Magnolia St"
                                className="w-full bg-white/5 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
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
                                        className="w-20 bg-black/30 border border-blue-500/30 rounded-lg p-2 text-center text-white font-mono text-lg focus:border-blue-500 focus:outline-none"
                                    />
                                    <span className="text-gray-400 text-sm">Hours @ $20/hr</span>
                                </div>
                            </div>
                        ) : (
                            <label className="flex items-center gap-4 cursor-pointer group">
                                <div className={`w-6 h-6 rounded border ${waitTime ? 'bg-cyan-600 border-cyan-600' : 'border-gray-500 group-hover:border-white'} flex items-center justify-center transition-colors`}>
                                    {waitTime && <Clock size={16} className="text-white" />}
                                </div>
                                <input type="checkbox" className="hidden" checked={waitTime} onChange={e => setWaitTime(e.target.checked)} />
                                <div>
                                    <span className={`block font-medium ${waitTime ? 'text-white' : 'text-gray-400'} transition-colors`}>Request Driver Wait Time</span>
                                    <span className="text-xs text-gray-500 block">+ $20.00 / hour</span>
                                </div>
                            </label>
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
                                <div className="opacity-50 pointer-events-none">
                                    <label className="text-[10px] font-bold text-gray-500 tracking-widest uppercase mb-1 block">Return Origin</label>
                                    <input type="text" value={dropoff || "Dropoff Location"} disabled className="w-full bg-transparent border-b border-white/10 py-2 text-gray-400 italic" />
                                </div>

                                {returnStops.map((stop, idx) => (
                                    <div key={idx} className="relative flex gap-2 items-end animate-in slide-in-from-left-4 fade-in duration-300">
                                        <div className="flex-1">
                                            <label className="text-[10px] font-bold text-cyan-400 tracking-widest uppercase mb-1 block">Return Stop #{idx + 1}</label>
                                            <input type="text" value={stop} onChange={e => updateReturnStop(idx, e.target.value)} placeholder="Add Stop on way back..." className="w-full bg-white/5 border border-cyan-500/30 rounded-xl p-3 text-white focus:outline-none focus:border-cyan-500 transition-colors" list="locations" />
                                        </div>
                                        <button onClick={() => removeReturnStop(idx)} className="p-4 bg-white/5 hover:bg-cyan-500/20 rounded-xl border border-white/10 transition-colors text-gray-400 hover:text-cyan-400"><X size={20} /></button>
                                    </div>
                                ))}

                                {returnStops.length < 5 && (
                                    <button onClick={addReturnStop} className="text-sm text-gray-400 hover:text-white flex items-center gap-2 transition-colors mt-2"><Plus size={16} /> Add Return Stop</button>
                                )}

                                <div className="opacity-50 pointer-events-none mt-4">
                                    <label className="text-[10px] font-bold text-gray-500 tracking-widest uppercase mb-1 block">Return Destination</label>
                                    <input type="text" value={pickup || "Pickup Location"} disabled className="w-full bg-transparent border-b border-white/10 py-2 text-gray-400 italic" />
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
                                stops={stops} // RouteMap handles generic stops
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
                                href={`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(pickup)}&destination=${encodeURIComponent(dropoff)}&waypoints=${stops.map(s => encodeURIComponent(s)).join('|')}`}
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
                                            <span>Waypoints ({parseInt(stops.length.toString()) + parseInt(returnStops.length.toString())})</span>
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
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                    />
                                    <input
                                        type="email"
                                        placeholder="Email Address"
                                        value={email}
                                        onChange={e => setEmail(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                    />
                                    <input
                                        type="tel"
                                        placeholder="Phone Number"
                                        value={phone}
                                        onChange={e => setPhone(e.target.value)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                                    />
                                    <input
                                        type="number"
                                        min="1"
                                        max="6"
                                        placeholder="# of Passengers"
                                        value={passengers}
                                        onChange={e => setPassengers(parseInt(e.target.value) || 1)}
                                        className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
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
                                <button
                                    onClick={() => {
                                        if (!quote || !name || !email || !phone) {
                                            alert('Please fill in all contact information');
                                            return;
                                        }
                                        setShowCalendar(true);
                                    }}
                                    disabled={!quote || !name || !email || !phone}
                                    className={`w-full bg-cyan-600 text-white font-bold py-4 rounded-xl hover:bg-cyan-700 shadow-lg shadow-cyan-500/20 flex justify-center items-center gap-2 text-lg transition-all ${(!quote || !name || !email || !phone) ? 'opacity-50 cursor-not-allowed' : ''}`}
                                >
                                    Continue to Calendar <ChevronRight />
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
