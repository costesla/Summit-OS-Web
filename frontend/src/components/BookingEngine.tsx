"use client";

/// <reference types="@types/google.maps" />

import { useState, useEffect, useRef, useMemo } from "react";
import { Plus, Trash2, Clock, ChevronRight, AlertCircle, X, MapPin } from "lucide-react";
import { PriceBreakdown } from "../utils/pricing";
import dynamic from "next/dynamic";
import { useJsApiLoader, Autocomplete } from "@react-google-maps/api";
import CalendarBooking from "./CalendarBooking";
import {
    MAX_STOPS, addStop, airportDirection, canAddStop, createRoute, isComplete,
    labelFor, missingLabels, quoteIsBookable, removeStop, roleAt, setPoint,
    stopCount, toQuoteRequest,
} from "./route";
import type { RoutePoint } from "./route";

const RouteMap = dynamic(() => import("./RouteMap"), {
    ssr: false,
    loading: () => <div className="w-full h-full bg-gray-900 animate-pulse" />
});

// Libraries for Google Maps - MUST be defined outside component to prevent re-initialization
const libraries: ("places" | "geometry" | "drawing" | "visualization")[] = ["places"];

/* Google Directions is billed per request. The old form fired one every 500ms
   of typing, so a single address could cost a dozen calls. Quotes now run off
   COMMITTED addresses only — a Place chosen from autocomplete, or a field the
   passenger has finished with — and this short debounce just coalesces the
   burst when several legs commit at once (paste, tab-through). */
const QUOTE_COALESCE_MS = 350;

export default function BookingEngine() {
    // Load Google Maps with Places library
    const { isLoaded } = useJsApiLoader({
        id: 'google-map-script',
        googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
        libraries
    });

    /* The trip, in travel order: [pickup, ...stops, finalDropoff]. Replaces the
       old pickup/dropoff pair plus a stop COUNT, where stop addresses were
       optional, never reached the map, and were dropped before booking. */
    const [route, setRoute] = useState<RoutePoint[]>(createRoute);

    /* Addresses the passenger has actually committed to. Typing changes `route`
       and nothing else; only a commit moves this, and only this triggers a
       priced lookup. */
    const [committed, setCommitted] = useState<string[]>([]);
    const committedKey = committed.join("");

    // One Autocomplete instance per leg, keyed by point id so adding or
    // removing a stop can't leave a ref pointing at the wrong field.
    const autocompleteRefs = useRef<Record<string, google.maps.places.Autocomplete>>({});

    // ── Flight (optional) ────────────────────────────────────────────────
    // Which airport workflow applies is derived from the ROUTE, not stored:
    // an airport at the start means we're collecting someone off an inbound
    // flight; an airport at the end means we're delivering them to one.
    const direction = airportDirection(route);
    const [flightOverride, setFlightOverride] = useState(false);
    const [flightNumber, setFlightNumber] = useState("");
    const [arrivalAirport, setArrivalAirport] = useState("");
    // Shown whenever the route implies a flight, or the passenger asks for it —
    // an FBO or private terminal often isn't typed as an airport by Google.
    const showFlightSection = direction !== null || flightOverride;

    // Toast notification state
    const [toastMessage, setToastMessage] = useState<string | null>(null);

    // Driver Wait Time
    const [waitTimeHours, setWaitTimeHours] = useState(0);

    const [quote, setQuote] = useState<PriceBreakdown | null>(null);
    const [loading, setLoading] = useState(false);
    /* Set when a recalculation fails. A quote that could not be recomputed
       must never be the number a passenger agrees to, so this blocks the
       continue button rather than leaving a stale total on screen. */
    const [quoteError, setQuoteError] = useState<string | null>(null);

    // Contact Form State (Visible after Quote)
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [phone, setPhone] = useState("");
    const [passengers, setPassengers] = useState(1);
    const [showCalendar, setShowCalendar] = useState(false);
    const [bookingComplete, setBookingComplete] = useState(false);

    const routeComplete = isComplete(route);
    const stops = stopCount(route);

    /* Any edit invalidates the current price immediately. The old form kept the
       previous quote through a failed recalculation "to prevent map flashing",
       which meant a stale total could survive a route change and follow the
       passenger to checkout. A blank price is honest; a wrong one is not. */
    const routeSignature = route.map((p) => p.address.trim()).join("");
    useEffect(() => {
        setQuote(null);
        setQuoteError(null);
    }, [routeSignature, waitTimeHours]);

    // Commit a leg: this is what actually costs a Directions call.
    const commitRoute = (next: RoutePoint[]) => {
        setCommitted(next.map((p) => p.address.trim()));
    };

    const handlePlaceChanged = (id: string) => {
        const auto = autocompleteRefs.current[id];
        if (!auto) return;
        const place = auto.getPlace();
        const address = place.formatted_address || place.name || "";
        const next = setPoint(route, id, {
            address,
            isAirport: !!place.types?.includes("airport"),
        });
        setRoute(next);
        commitRoute(next);
        validateLocation(address);
    };

    // Typing alone never prices. Leaving a field with something in it does —
    // it covers the passenger who types an address and tabs on without
    // choosing from the dropdown.
    const handleBlur = () => {
        if (route.some((p) => p.address.trim())) commitRoute(route);
    };

    useEffect(() => {
        const addresses = committed;
        if (addresses.length < 2 || addresses.some((a) => !a)) return;

        const fetchQuote = async () => {
            setLoading(true);
            setToastMessage(null);
            try {
                // Route through SWA linked backend proxy (function key stays in Azure)
                const res = await fetch('/api/quote', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        // Round trips were removed from the UI; always price as one-way.
                        tripType: 'one-way',
                        // Waypoint ORDER is the trip. The backend passes these to
                        // Google Directions without optimize_waypoints, so the
                        // sequence sent is the sequence priced and driven.
                        ...toQuoteRequest(route),
                        returnStops: [],
                        layoverHours: 0,
                        waitTimeHours: parseFloat(waitTimeHours.toString()) || 0
                    })
                });
                if (!res.ok) {
                    console.error("Quote API Error:", res.status, res.statusText);
                    setQuote(null);
                    setQuoteError(res.status === 404
                        ? "Pricing is temporarily unavailable. Please try again in a moment."
                        : `Pricing is unavailable right now (${res.status}).`);
                    return;
                }

                const data = await res.json();
                if (data.success && quoteIsBookable(data.quote)) {
                    setQuote(data.quote);
                    setQuoteError(null);
                } else {
                    // Either the engine reported a problem, or it returned a
                    // total we will not put in front of a customer ($0, NaN,
                    // a missing component). Both are a failure to price.
                    console.error("Quote rejected:", data.error || data.quote);
                    setQuote(null);
                    setQuoteError(data.error === "NOT_FOUND"
                        ? "We couldn't find a driving route between those addresses. Check each stop."
                        : (data.error || "We couldn't calculate a price for this route."));
                }
            } catch (e: unknown) {
                console.error("Fetch Error:", e);
                setQuote(null);
                setQuoteError("We couldn't reach the pricing service. Please try again.");
            } finally {
                setLoading(false);
            }
        };

        const timeout = setTimeout(fetchQuote, QUOTE_COALESCE_MS);
        return () => clearTimeout(timeout);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [committedKey, waitTimeHours]);

    // ── Route editing ────────────────────────────────────────────────────
    const handleAddStop = () => setRoute((r) => addStop(r));
    const handleRemoveStop = (id: string) => {
        setRoute((r) => {
            const next = removeStop(r, id);
            delete autocompleteRefs.current[id];
            // Removing a leg changes the route, so re-price against what's left
            // rather than leaving the old total up.
            if (next.every((p) => p.address.trim())) {
                setCommitted(next.map((p) => p.address.trim()));
            }
            return next;
        });
    };

    // Validation: Check if address is outside Colorado
    const validateLocation = (address: string) => {
        const lower = address.toLowerCase();
        const isColorado = lower.includes('colorado') || lower.includes(', co');
        if (!isColorado) {
            setToastMessage('Note: You are booking a trip outside of our primary service area');
            setTimeout(() => setToastMessage(null), 5000);
        }
    };

    // Autocomplete configuration options
    const autocompleteOptions = {
        componentRestrictions: { country: "us" },
        // `types` is what tells us a leg is an airport — without it the flight
        // section could only ever be opened by hand.
        fields: ["formatted_address", "geometry", "name", "types"],
        // Soft bias toward Colorado Springs (not strict bounds)
        locationBias: {
            center: { lat: 38.8339, lng: -104.8214 }, // Colorado Springs
            radius: 50000 // 50km radius for soft bias
        }
    };

    const quoteRequest = useMemo(() => toQuoteRequest(route), [routeSignature]); // eslint-disable-line react-hooks/exhaustive-deps
    const bookable = quoteIsBookable(quote);
    const contactComplete = !!(name && email && phone);
    const canContinue = routeComplete && bookable && contactComplete;

    /* Only an ARRIVING flight gets an expected arrival airport. That single
       field is what switches the cabin console into the arrival workflow, so a
       departure deliberately sends the flight number WITHOUT one: dispatch can
       still see the flight, but there is no inbound aircraft to track and no
       landing to hand over from. No extra column, no direction flag. */
    const flightForBooking = showFlightSection && flightNumber.trim()
        ? flightNumber.trim() : undefined;
    const arrivalForBooking = direction === "ARRIVING" && arrivalAirport.trim()
        ? arrivalAirport.trim() : undefined;

    return (
        <div className="w-full text-left font-sans">
            {/* 1. Header */}
            <div className="flex justify-between items-center mb-8 border-b border-white/10 pb-6">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Trip Configuration</h2>
                    <p className="text-gray-400 text-sm mt-1 tracking-wide uppercase">COS Tesla LLC | Powered by: SummitOS</p>
                </div>
            </div>

            {/* Disclaimer Messaging */}
            <div className="mb-6 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-center">
                <p className="text-blue-200 text-xs font-medium tracking-wide">
                    Standardized rates for State Regulation compliance. No surge pricing. Ever.
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">

                {/* LEFT: the route, in travel order */}
                <div className="space-y-6">
                    <div className="space-y-3">
                        {route.map((leg, index) => {
                            const role = roleAt(index, route.length);
                            const label = labelFor(index, route.length);
                            const accent = role === "STOP" ? "text-cyan-500/70" : "text-gray-500";
                            return (
                                <div key={leg.id} className="relative group">
                                    <div className="flex items-center justify-between mb-2">
                                        <label className={`text-xs font-bold tracking-widest uppercase flex items-center gap-2 ${accent}`}>
                                            <MapPin size={12} />
                                            {label}
                                        </label>
                                        {role === "STOP" && (
                                            <button
                                                type="button"
                                                onClick={() => handleRemoveStop(leg.id)}
                                                aria-label={`Remove ${label}`}
                                                className="text-gray-500 hover:text-red-400 transition-colors p-1"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        )}
                                    </div>
                                    {isLoaded ? (
                                        <Autocomplete
                                            onLoad={(a: google.maps.places.Autocomplete) => {
                                                autocompleteRefs.current[leg.id] = a;
                                            }}
                                            onPlaceChanged={() => handlePlaceChanged(leg.id)}
                                            options={autocompleteOptions}
                                        >
                                            <input
                                                type="text"
                                                value={leg.address}
                                                onChange={e => setRoute(r => setPoint(r, leg.id, { address: e.target.value }))}
                                                onBlur={handleBlur}
                                                placeholder={role === "STOP"
                                                    ? "Where should we stop?"
                                                    : "e.g., 1 Lake Ave, Colorado Springs"}
                                                aria-label={label}
                                                className="w-full bg-white/5 border border-white/10 rounded-xl p-4 !text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                                style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                            />
                                        </Autocomplete>
                                    ) : (
                                        <input
                                            type="text"
                                            value={leg.address}
                                            onChange={e => setRoute(r => setPoint(r, leg.id, { address: e.target.value }))}
                                            onBlur={handleBlur}
                                            placeholder="e.g., 1194 Magnolia St"
                                            aria-label={label}
                                            className="w-full bg-white/5 border border-white/10 rounded-xl p-4 !text-white focus:outline-none focus:border-cyan-500 transition-colors text-lg"
                                            style={{ color: '#ffffff', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                                        />
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* Add Stop — inserts before the final drop-off, never after. */}
                    <div className="flex items-center justify-between bg-white/[0.03] border border-white/10 rounded-2xl p-4">
                        <div>
                            <button
                                type="button"
                                onClick={handleAddStop}
                                disabled={!canAddStop(route)}
                                className="flex items-center gap-2 text-sm font-bold text-cyan-400 hover:text-cyan-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            >
                                <Plus size={16} /> Add a stop
                            </button>
                            <p className="text-[11px] text-gray-500 mt-1">
                                $5.00 per stop · up to {MAX_STOPS}
                            </p>
                        </div>
                        {stops > 0 && (
                            <span className="text-xs font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-1 rounded-lg">
                                {stops} {stops === 1 ? 'stop' : 'stops'} · +${(stops * 5).toFixed(2)}
                            </span>
                        )}
                    </div>

                    {/* --- FLIGHT (optional) --- */}
                    <div className="pt-2">
                        {direction === null && (
                            <label className="flex items-center gap-3 cursor-pointer select-none">
                                <input
                                    type="checkbox"
                                    checked={flightOverride}
                                    onChange={e => {
                                        setFlightOverride(e.target.checked);
                                        if (!e.target.checked) {
                                            setFlightNumber("");
                                            setArrivalAirport("");
                                        }
                                    }}
                                    className="w-4 h-4 rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500/50 focus:ring-offset-0"
                                />
                                <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                                    This trip involves a flight
                                </span>
                            </label>
                        )}

                        {showFlightSection && (
                            <div className="mt-4 bg-white/[0.03] border border-white/10 rounded-2xl p-4 space-y-3 animate-in fade-in slide-in-from-top-2 duration-300">
                                <p className="text-[11px] text-gray-500 leading-relaxed">
                                    {direction === "ARRIVING" && (
                                        <>Looks like an airport pickup. Add your flight and we&apos;ll
                                            track it — your cabin console follows the plane in, then
                                            switches to your driver.</>
                                    )}
                                    {direction === "DEPARTING" && (
                                        <>Heading to the airport. Your flight number helps us plan
                                            your pickup time — we don&apos;t track outbound flights.</>
                                    )}
                                    {direction === null && (
                                        <>Add your flight number so we can plan around it.</>
                                    )}
                                    {" "}Optional, and never blocks your booking.
                                </p>
                                <div className="flex gap-2">
                                    <div className="flex-1">
                                        <label className="text-[10px] text-gray-500 uppercase tracking-widest font-bold mb-1 block">
                                            Flight Number
                                        </label>
                                        <input
                                            type="text"
                                            value={flightNumber}
                                            onChange={e => setFlightNumber(e.target.value.toUpperCase())}
                                            placeholder="e.g. UA1234"
                                            maxLength={16}
                                            className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm !text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors"
                                            style={{ color: '#ffffff', backgroundColor: 'rgba(0,0,0,0.2)' }}
                                        />
                                    </div>
                                    {/* Only an arrival has an airport we wait at. */}
                                    {direction === "ARRIVING" && (
                                        <div className="w-28">
                                            <label className="text-[10px] text-gray-500 uppercase tracking-widest font-bold mb-1 block">
                                                Arriving At
                                            </label>
                                            <input
                                                type="text"
                                                value={arrivalAirport}
                                                onChange={e => setArrivalAirport(e.target.value.toUpperCase())}
                                                placeholder="COS"
                                                maxLength={8}
                                                className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm !text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 transition-colors"
                                                style={{ color: '#ffffff', backgroundColor: 'rgba(0,0,0,0.2)' }}
                                            />
                                        </div>
                                    )}
                                </div>
                                {direction === "ARRIVING" && (
                                    <p className="text-[10px] text-gray-600">
                                        The same flight number can fly several routes a day —
                                        the arrival airport pins the right one.
                                    </p>
                                )}
                            </div>
                        )}
                    </div>

                    {/* --- WAIT TIME --- */}
                    <div className="pt-6 border-t border-white/10">
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
                    </div>
                </div>

                {/* RIGHT: Visuals & Quote */}
                <div className="flex flex-col h-full">
                    {/* LIVE MAP INTEGRATION */}
                    <div className="w-full h-48 rounded-2xl border border-white/10 mb-6 overflow-hidden shadow-2xl relative z-0">
                        {(quoteRequest.pickup || quoteRequest.dropoff) ? (
                            <RouteMap
                                pickupAddress={quote?.debug?.origin || quoteRequest.pickup}
                                dropoffAddress={quote?.debug?.destination || quoteRequest.dropoff}
                                /* The stops finally reach the map, in order. */
                                stops={quoteRequest.stops}
                            />
                        ) : (
                            <div className="w-full h-full bg-gradient-to-br from-gray-900 to-black flex items-center justify-center">
                                <span className="text-gray-500 text-sm">Enter locations to see route</span>
                            </div>
                        )}

                        {/* Open in Google Maps — waypoints in travel order. */}
                        {(quoteRequest.pickup || quoteRequest.dropoff) && (
                            <a
                                href={`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(quoteRequest.pickup)}&destination=${encodeURIComponent(quoteRequest.dropoff)}${quoteRequest.stops.filter(Boolean).length ? `&waypoints=${quoteRequest.stops.filter(Boolean).map(encodeURIComponent).join('%7C')}` : ''}`}
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
                                            <span>Stops ({stops}×)</span>
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
                            ) : quoteError ? (
                                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                                    {quoteError}
                                </div>
                            ) : !routeComplete ? (
                                <div className="text-center text-gray-500 py-8 italic">
                                    {missingLabels(route).length
                                        ? `Add an address for: ${missingLabels(route).join(', ')}`
                                        : 'Enter route to calculate...'}
                                </div>
                            ) : (
                                <div className="text-center text-gray-500 py-8 italic">
                                    Calculating...
                                </div>
                            )}
                        </div>

                        <div className="mt-6 pt-6 border-t border-white/10">
                            <div className="flex justify-between items-end mb-6">
                                <span className="text-gray-400">Total Estimate</span>
                                <span className="text-4xl font-bold text-white">
                                    {loading
                                        ? <span className="animate-pulse">...</span>
                                        : (bookable ? `$${quote!.total.toFixed(2)}` : "—")}
                                </span>
                            </div>

                            {/* Contact Form — only once there is a real price. */}
                            {bookable && (
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
                                    pickup={quote?.debug?.origin || quoteRequest.pickup}
                                    dropoff={quote?.debug?.destination || quoteRequest.dropoff}
                                    stops={quoteRequest.stops}
                                    price={quote ? `$${quote.total.toFixed(2)}` : '$0.00'}
                                    tripDistance={quote?.distance?.toFixed(1) || undefined}
                                    tripDuration={quote?.time?.toString() || undefined}
                                    flightNumber={flightForBooking}
                                    arrivalAirport={arrivalForBooking}
                                    onBookingComplete={() => setBookingComplete(true)}
                                />
                            ) : bookingComplete ? (
                                <div className="text-center py-8 bg-green-500/10 rounded-xl border border-green-500/30">
                                    <div className="text-4xl mb-2">✅</div>
                                    <h4 className="text-xl font-bold text-white mb-2">Booking Confirmed!</h4>
                                    <p className="text-sm text-gray-300">You&apos;ll receive a confirmation email shortly.</p>
                                </div>
                            ) : (
                                <>
                                    <button
                                        onClick={() => setShowCalendar(true)}
                                        disabled={!canContinue}
                                        className={`w-full bg-cyan-600 text-white font-bold py-4 rounded-xl hover:bg-cyan-700 shadow-lg shadow-cyan-500/20 flex justify-center items-center gap-2 text-lg transition-all ${!canContinue ? 'opacity-50 cursor-not-allowed' : ''}`}
                                    >
                                        Continue to Date Selection <ChevronRight />
                                    </button>
                                    {/* Say WHY it's disabled. A dead button with no
                                        explanation is how a booking gets abandoned. */}
                                    {!canContinue && (
                                        <p className="mt-3 text-center text-xs text-gray-500">
                                            {!routeComplete
                                                ? `Add an address for: ${missingLabels(route).join(', ')}`
                                                : !bookable
                                                    ? "We need a valid price before you can continue."
                                                    : "Add your contact details to continue."}
                                        </p>
                                    )}
                                </>
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
