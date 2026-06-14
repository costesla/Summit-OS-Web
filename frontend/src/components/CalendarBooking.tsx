"use client";

import { useState, useEffect } from "react";
import { formatTime, formatDate } from "@/lib/calendar";
import { Calendar, Clock, CheckCircle, ChevronRight, Loader2 } from "lucide-react";

interface CalendarBookingProps {
    customerName: string;
    customerEmail: string;
    customerPhone: string;
    passengers: number;
    pickup: string;
    dropoff: string;
    price: string;
    quoteType?: string;
    tripDistance?: string;
    tripDuration?: string;
    durationMinutes?: number;
    returnScheduled?: boolean;
    onBookingComplete: (eventId: string) => void;
}

interface TimeSlot {
    start: string;
    end: string;
}

// Hours of Operation fetched from API
interface HopData {
    [key: number]: { start: string; end: string }
}

interface Outage {
    date: string;
    reason: string;
    returnDate?: string;
}

interface StatusData {
    outToday: boolean;
    message: string;
    returnDate?: string;
    upcoming: Outage[];
}

// Convert HH:MM to minutes since midnight
function toMinutes(hhmm: string): number {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
}

export default function CalendarBooking({
    customerName,
    customerEmail,
    customerPhone,
    passengers,
    pickup,
    dropoff,
    price,
    quoteType = 'single',
    tripDistance,
    tripDuration,
    durationMinutes = 60,
    returnScheduled = false,
    onBookingComplete,
}: CalendarBookingProps) {
    const [selectedDate, setSelectedDate] = useState<Date | null>(null);
    const [selectedTime, setSelectedTime] = useState<string | null>(null);
    const [availableSlots, setAvailableSlots] = useState<TimeSlot[]>([]);
    const [loadingSlots, setLoadingSlots] = useState(false);
    // Scheduled-return round trips: the return leg's own date/time
    const [returnDate, setReturnDate] = useState<Date | null>(null);
    const [returnTime, setReturnTime] = useState<string | null>(null);
    const [returnSlots, setReturnSlots] = useState<TimeSlot[]>([]);
    const [loadingReturnSlots, setLoadingReturnSlots] = useState(false);
    const [booking, setBooking] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [stripeLoading, setStripeLoading] = useState(false);

    // Dynamic Data
    const [hop, setHop] = useState<HopData | null>(null);
    const [status, setStatus] = useState<StatusData | null>(null);
    const [loadingConfig, setLoadingConfig] = useState(true);

    // Fetch Configuration on Mount
    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const [hopRes, statusRes] = await Promise.all([
                    fetch('https://summitos-api.azurewebsites.net/api/hop').then(r => r.json()),
                    fetch('https://summitos-api.azurewebsites.net/api/status').then(r => r.json())
                ]);

                if (hopRes.hop) setHop(hopRes.hop);
                if (statusRes) setStatus(statusRes);
            } catch (e) {
                console.error("Failed to load business configuration", e);
            } finally {
                setLoadingConfig(false);
            }
        };
        fetchConfig();
    }, []);

    // Reset the "Processing..." state when the page is restored from the
    // back/forward cache (e.g. user hits Back from the Stripe checkout page)
    useEffect(() => {
        const onPageShow = (e: PageTransitionEvent) => {
            if (e.persisted) setBooking(false);
        };
        window.addEventListener('pageshow', onPageShow);
        return () => window.removeEventListener('pageshow', onPageShow);
    }, []);

    // Check if a slot start time is within HOP for its weekday
    const withinHop = (dateObj: Date): boolean => {
        if (!hop) return true;
        const w = dateObj.getDay();
        const dayHop = hop[w];
        if (!dayHop || !dayHop.start || !dayHop.end) return false; // Day is off or malformed
        const mins = dateObj.getHours() * 60 + dateObj.getMinutes();
        return mins >= toMinutes(dayHop.start) && mins <= toMinutes(dayHop.end);
    }

    // Generate next 30 days for date selection
    const availableDates = Array.from({ length: 30 }, (_, i) => {
        const date = new Date();
        date.setDate(date.getDate() + i);
        return date;
    });

    // Fetch available slots when date is selected
    useEffect(() => {
        if (!selectedDate) {
            setAvailableSlots([]);
            return;
        }


        const fetchSlots = async () => {
            setLoadingSlots(true);
            setError(null);
            try {
                const response = await fetch(
                    `https://summitos-api.azurewebsites.net/api/calendar-availability?date=${selectedDate.toLocaleDateString("en-CA")}`
                );
                const data = await response.json();

                if (data.success) {
                    const sortedSlots = data.slots.sort((a: TimeSlot, b: TimeSlot) =>
                        new Date(a.start).getTime() - new Date(b.start).getTime()
                    );
                    const filteredSlots = sortedSlots.filter((slot: TimeSlot) =>
                        withinHop(new Date(slot.start))
                    );
                    setAvailableSlots(filteredSlots);
                } else {
                    setError(`API Error: ${data.error || "Failed to load times"}`);
                }
            } catch (err: any) {
                console.error("Availability Fetch Error:", err);
                setError(`Connectivity Error: ${err.message || "Failed to reach booking server"}`);
            } finally {
                setLoadingSlots(false);
            }
        };

        fetchSlots();
    }, [selectedDate]);

    // Fetch return-leg slots when a return date is selected
    useEffect(() => {
        if (!returnScheduled || !returnDate) {
            setReturnSlots([]);
            return;
        }

        const fetchReturnSlots = async () => {
            setLoadingReturnSlots(true);
            try {
                const response = await fetch(
                    `https://summitos-api.azurewebsites.net/api/calendar-availability?date=${returnDate.toLocaleDateString("en-CA")}`
                );
                const data = await response.json();
                if (data.success) {
                    const sorted = data.slots.sort((a: TimeSlot, b: TimeSlot) =>
                        new Date(a.start).getTime() - new Date(b.start).getTime()
                    );
                    setReturnSlots(sorted.filter((slot: TimeSlot) => withinHop(new Date(slot.start))));
                } else {
                    setError(`API Error: ${data.error || "Failed to load return times"}`);
                }
            } catch (err: any) {
                setError(`Connectivity Error: ${err.message || "Failed to reach booking server"}`);
            } finally {
                setLoadingReturnSlots(false);
            }
        };

        fetchReturnSlots();
    }, [returnScheduled, returnDate]);

    // Return pickup can't start before the outbound leg is done (+30 min buffer)
    const earliestReturnMs = selectedTime
        ? new Date(selectedTime).getTime() + (durationMinutes + 30) * 60000
        : 0;
    const selectableReturnSlots = returnSlots.filter(
        slot => new Date(slot.start).getTime() >= earliestReturnMs
    );

    // Clients who pay via Venmo/Zelle and should bypass Stripe entirely
    const VENMO_CLIENTS = new Set<string>([]);

    const handleBooking = async (method: 'stripe' | 'invoice' | 'cash') => {
        if (!selectedTime) return;
        if (returnScheduled && !returnTime) return;

        setBooking(true);
        setError(null);

        // --- DIRECT INVOICE / PAY LATER ---
        if (method === 'invoice' || method === 'cash' || VENMO_CLIENTS.has(customerEmail.toLowerCase().trim())) {
            try {
                const res = await fetch("https://summitos-api.azurewebsites.net/api/book", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        customerName,
                        customerEmail,
                        customerPhone,
                        pickup,
                        dropoff,
                        appointmentStart: selectedTime,
                        price,
                        passengers,
                        tripDistance,
                        tripDuration,
                        duration: durationMinutes,
                        returnStart: returnScheduled ? returnTime : undefined,
                        quoteType,
                        paymentMethod: method === 'invoice' ? "Invoice" : (method === 'cash' ? "Cash" : "Venmo"),
                    }),
                });
                const data = await res.json();
                if (data.success) {
                    setBooking(false);
                    if (onBookingComplete) onBookingComplete(data.eventId || "manual");
                } else {
                    throw new Error(data.error || "Booking failed.");
                }
            } catch (err: any) {
                setError(err.message);
                console.error("Direct booking error:", err);
                setBooking(false);
            }
            return;
        }

        // --- STANDARD STRIPE CHECKOUT ---
        setStripeLoading(true);
        try {
            const bookingResponse = await fetch("https://summitos-api.azurewebsites.net/api/create-checkout-session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    customerName,
                    customerEmail,
                    customerPhone,
                    pickup,
                    dropoff,
                    appointmentStart: selectedTime,
                    price,
                    passengers,
                    tripDistance,
                    tripDuration,
                    duration: durationMinutes,
                    returnStart: returnScheduled ? returnTime : undefined,
                    quoteType,
                    successUrl: `${window.location.origin}/book/success?session_id={CHECKOUT_SESSION_ID}`,
                    cancelUrl: `${window.location.origin}/book?payment_cancelled=true`
                }),
            });

            const bookingData = await bookingResponse.json();

            if (bookingData.url) {
                window.location.href = bookingData.url;
            } else {
                throw new Error(bookingData.error || "Failed to initialize secure checkout session");
            }
        } catch (err: any) {
            setError(err.message);
            console.error("Checkout redirect error:", err);
            setBooking(false);
        } finally {
            setStripeLoading(false);
        }
    };

    // Check if a date is blocked
    const isDateBlocked = (date: Date) => {
        if (!status) return false;

        // Use local YYYY-MM-DD to match backend return which is YYYY-MM-DD
        const ymd = date.toLocaleDateString("en-CA");

        // Check upcoming (safe access)
        if (status.upcoming?.some(u => u.date === ymd)) return true;

        // Check today
        const today = new Date().toLocaleDateString("en-CA");
        if (status.outToday && ymd === today) return true;

        return false;
    }

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-top-4 duration-500">
            {/* Status Banner */}
            {(status?.outToday || (selectedDate && isDateBlocked(selectedDate))) && (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mb-4">
                    <div className="flex items-start gap-3">
                        <div className="text-amber-500 mt-1">⚠️</div>
                        <div>
                            <h4 className="text-amber-200 font-bold text-sm uppercase tracking-wide">
                                Availability Notice
                            </h4>
                            <p className="text-amber-100/80 text-sm mt-1">
                                {status?.message || "Peter is unavailable on this date."}
                            </p>
                            {status?.returnDate && (
                                <p className="text-amber-100/60 text-xs mt-2">
                                    Returning: {status.returnDate}
                                </p>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <div className="flex items-center gap-3 mb-4">
                <Calendar className="text-cyan-500" size={24} />
                <h3 className="text-xl font-bold text-white">Select Your Appointment Time</h3>
            </div>

            {/* Date Selection */}
            <div>
                <label className="text-xs font-bold text-gray-400 tracking-widest uppercase mb-3 block">
                    Choose Date
                </label>
                {loadingConfig ? (
                    <div className="text-sm text-gray-500 py-4">Checking schedule...</div>
                ) : (
                    <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                        {availableDates.slice(0, 15).map((date) => {
                            const isSelected =
                                selectedDate?.toDateString() === date.toDateString();
                            const blocked = isDateBlocked(date);

                            return (
                                <button
                                    key={date.toISOString()}
                                    disabled={blocked}
                                    onClick={() => {
                                        setSelectedDate(date);
                                        setSelectedTime(null);
                                        setReturnDate(null);
                                        setReturnTime(null);
                                    }}
                                    className={`p-3 rounded-lg border transition-all text-center relative overflow-hidden ${blocked
                                        ? "bg-red-900/10 border-red-900/20 opacity-50 cursor-not-allowed grayscale"
                                        : isSelected
                                            ? "bg-cyan-600 border-cyan-600 text-white shadow-lg shadow-cyan-500/20"
                                            : "bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:border-white/20"
                                        }`}
                                >
                                    {blocked && (
                                        <div className="absolute inset-0 flex items-center justify-center bg-black/40 z-10">
                                            <span className="text-[10px] uppercase font-bold text-red-400 rotate-[-15deg] border-2 border-red-400 px-1 rounded">
                                                OUT
                                            </span>
                                        </div>
                                    )}
                                    <div className="text-xs font-bold">
                                        {date.toLocaleDateString("en-US", { weekday: "short" })}
                                    </div>
                                    <div className="text-lg font-bold">
                                        {date.getDate()}
                                    </div>
                                    <div className="text-[10px] text-gray-500">
                                        {date.toLocaleDateString("en-US", { month: "short" })}
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Time Selection */}
            {selectedDate && (
                <div>
                    <label className="text-xs font-bold text-gray-400 tracking-widest uppercase mb-3 block flex items-center gap-2">
                        <Clock size={14} />
                        Choose Time on {formatDate(selectedDate)}
                    </label>

                    {loadingSlots ? (
                        <div className="text-center py-8 text-gray-500">
                            Loading available times...
                        </div>
                    ) : availableSlots.length === 0 ? (
                        <div className="text-center py-8 text-gray-500 bg-white/5 rounded-lg border border-white/10">
                            No available times for this date. Please select another day.
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 max-h-64 overflow-y-auto">
                            {availableSlots.map((slot) => {
                                const slotStart = new Date(slot.start);
                                const isSelected = selectedTime === slot.start;

                                return (
                                    <button
                                        key={slot.start}
                                        onClick={() => { setSelectedTime(slot.start); setReturnTime(null); }}
                                        className={`p-3 rounded-lg border transition-all ${isSelected
                                            ? "bg-cyan-600 border-cyan-600 text-white shadow-lg shadow-cyan-500/20"
                                            : "bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:border-white/20"
                                            }`}
                                    >
                                        <div className="text-sm font-bold">{formatTime(slotStart)}</div>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* Return Leg Selection (scheduled-return round trips) */}
            {returnScheduled && selectedTime && (
                <div className="pt-4 border-t border-white/10 space-y-4 animate-in fade-in slide-in-from-top-4 duration-300">
                    <div className="flex items-center gap-3">
                        <Calendar className="text-blue-400" size={20} />
                        <h3 className="text-lg font-bold text-white">Select Your Return Pickup Time</h3>
                    </div>

                    <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                        {availableDates.slice(0, 15).map((date) => {
                            // Return can't be before the outbound day
                            const beforeOutbound = selectedDate !== null
                                && new Date(date).setHours(0, 0, 0, 0) < new Date(selectedDate).setHours(0, 0, 0, 0);
                            const blocked = isDateBlocked(date) || beforeOutbound;
                            const isSelected = returnDate?.toDateString() === date.toDateString();
                            return (
                                <button
                                    key={`ret-${date.toISOString()}`}
                                    disabled={blocked}
                                    onClick={() => { setReturnDate(date); setReturnTime(null); }}
                                    className={`p-3 rounded-lg border transition-all text-center ${blocked
                                        ? "bg-white/[0.02] border-white/5 opacity-30 cursor-not-allowed"
                                        : isSelected
                                            ? "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-500/20"
                                            : "bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:border-white/20"
                                        }`}
                                >
                                    <div className="text-xs font-bold">{date.toLocaleDateString("en-US", { weekday: "short" })}</div>
                                    <div className="text-lg font-bold">{date.getDate()}</div>
                                    <div className="text-[10px] text-gray-500">{date.toLocaleDateString("en-US", { month: "short" })}</div>
                                </button>
                            );
                        })}
                    </div>

                    {returnDate && (
                        loadingReturnSlots ? (
                            <div className="text-center py-6 text-gray-500">Loading return times...</div>
                        ) : selectableReturnSlots.length === 0 ? (
                            <div className="text-center py-6 text-gray-500 bg-white/5 rounded-lg border border-white/10">
                                No return times available after your outbound trip on this date. Try another day.
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 max-h-64 overflow-y-auto">
                                {selectableReturnSlots.map((slot) => {
                                    const isSelected = returnTime === slot.start;
                                    return (
                                        <button
                                            key={`retslot-${slot.start}`}
                                            onClick={() => setReturnTime(slot.start)}
                                            className={`p-3 rounded-lg border transition-all ${isSelected
                                                ? "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-500/20"
                                                : "bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:border-white/20"
                                                }`}
                                        >
                                            <div className="text-sm font-bold">{formatTime(new Date(slot.start))}</div>
                                        </button>
                                    );
                                })}
                            </div>
                        )
                    )}
                </div>
            )}

            {/* Buffer Info */}
            {selectedTime && (!returnScheduled || returnTime) && (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 text-sm">
                    <div className="flex items-start gap-2">
                        <CheckCircle className="text-blue-400 flex-shrink-0 mt-0.5" size={16} />
                        <div className="text-blue-100">
                            <strong>{returnScheduled ? "Two appointments will be booked:" : "Appointment includes buffers:"}</strong>
                            <ul className="mt-2 space-y-1 text-xs">
                                {returnScheduled && returnTime && (
                                    <li>• <strong>Outbound:</strong> {formatTime(new Date(selectedTime))} &nbsp;|&nbsp; <strong>Return:</strong> {formatTime(new Date(returnTime))}</li>
                                )}
                                <li>• <strong>30 min before:</strong> Driver travel time to pickup</li>
                                <li>• <strong>{durationMinutes >= 60 ? `${Math.floor(durationMinutes / 60)}h ${durationMinutes % 60 ? `${durationMinutes % 60}m` : ''}`.trim() : `${durationMinutes} min`}:</strong> Your trip{returnScheduled ? " (each leg)" : ""}</li>
                                <li>• <strong>30 min after:</strong> Driver break/reset time</li>
                            </ul>
                        </div>
                    </div>
                </div>
            )}

            {/* Error Message */}
            {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm text-red-200">
                    {error}
                </div>
            )}

            {/* Action Buttons */}
            <div className="space-y-3">
                <button
                    onClick={() => handleBooking('stripe')}
                    disabled={!selectedTime || (returnScheduled && !returnTime) || booking || stripeLoading}
                    className={`w-full bg-gradient-to-r from-[#635bff] to-[#8f86ff] text-white font-bold py-4 rounded-xl shadow-lg hover:shadow-[#635bff]/40 flex justify-center items-center gap-2 text-lg transition-all ${!selectedTime || (returnScheduled && !returnTime) || booking || stripeLoading ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                    {stripeLoading ? (
                        <><Loader2 className="w-5 h-5 animate-spin" /> Redirecting to secure checkout...</>
                    ) : booking ? (
                        <><span className="animate-spin inline-block w-5 h-5 border-2 border-white border-t-transparent rounded-full" /> Processing...</>
                    ) : (
                        <>⚡ Pay Now (Stripe) <ChevronRight /></>
                    )}
                </button>

                <button
                    onClick={() => handleBooking('invoice')}
                    disabled={!selectedTime || (returnScheduled && !returnTime) || booking}
                    className={`w-full bg-white/10 text-white font-bold py-4 rounded-xl border border-white/20 hover:bg-white/20 flex justify-center items-center gap-2 text-lg transition-all ${!selectedTime || (returnScheduled && !returnTime) || booking ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                    ✉️ Pay Later (Post-Trip Invoice)
                </button>

                <button
                    onClick={() => handleBooking('cash')}
                    disabled={!selectedTime || (returnScheduled && !returnTime) || booking}
                    className={`w-full bg-green-500/10 text-green-400 font-bold py-4 rounded-xl border border-green-500/30 hover:bg-green-500/20 flex justify-center items-center gap-2 text-lg transition-all ${!selectedTime || (returnScheduled && !returnTime) || booking ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                    💵 Pay Cash to Driver
                </button>
            </div>
        </div>
    );
}
