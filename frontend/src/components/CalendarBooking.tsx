"use client";

import { useState, useEffect } from "react";
import { formatTime, formatDate } from "@/lib/calendar";
import { Calendar, Clock, CheckCircle } from "lucide-react";

interface CalendarBookingProps {
    customerName: string;
    customerEmail: string;
    customerPhone: string;
    passengers: number;
    pickup: string;
    dropoff: string;
    price: string;
    tripDistance?: string;
    tripDuration?: string;
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
    tripDistance,
    tripDuration,
    onBookingComplete,
}: CalendarBookingProps) {
    const [selectedDate, setSelectedDate] = useState<Date | null>(null);
    const [selectedTime, setSelectedTime] = useState<string | null>(null);
    const [availableSlots, setAvailableSlots] = useState<TimeSlot[]>([]);
    const [loadingSlots, setLoadingSlots] = useState(false);
    const [booking, setBooking] = useState(false);
    const [error, setError] = useState<string | null>(null);

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

    // Check if a slot start time is within HOP for its weekday
    const withinHop = (dateObj: Date): boolean => {
        if (!hop) return false;
        const w = dateObj.getDay();
        const dayHop = hop[w];
        if (!dayHop) return false; // Day is off
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
                    `https://summitos-api.azurewebsites.net/api/calendar-availability?date=${selectedDate.toISOString()}`
                );
                const data = await response.json();

                if (data.success) {
                    // Sort slots chronologically
                    const sortedSlots = data.slots.sort((a: TimeSlot, b: TimeSlot) =>
                        new Date(a.start).getTime() - new Date(b.start).getTime()
                    );

                    // Filter out slots outside Hours of Operation
                    const filteredSlots = sortedSlots.filter((slot: TimeSlot) =>
                        withinHop(new Date(slot.start))
                    );

                    setAvailableSlots(filteredSlots);
                } else {
                    setError(data.error || "Failed to load available times");
                }
            } catch (err: any) {
                setError("Failed to load available times");
                console.error(err);
            } finally {
                setLoadingSlots(false);
            }
        };

        fetchSlots();
    }, [selectedDate]);

    const handleBooking = async () => {
        if (!selectedTime) return;

        setBooking(true);
        setError(null);

        try {
            // Create calendar booking
            const bookingResponse = await fetch("https://summitos-api.azurewebsites.net/api/calendar-book", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    customerName,
                    customerEmail,
                    customerPhone,
                    pickup,
                    dropoff,
                    appointmentStart: selectedTime,
                    duration: 60,
                    price,
                    passengers,
                    paymentMethod: 'External' // Default to external for now
                }),
            });

            const bookingData = await bookingResponse.json();

            if (!bookingData.success) {
                throw new Error(bookingData.error || "Failed to create booking");
            }

            // Log to SQL database for unified analytics
            try {
                await fetch("https://summitos-api.azurewebsites.net/api/log-private-trip", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        customerName,
                        customerEmail,
                        customerPhone,
                        pickup,
                        dropoff,
                        fare: parseFloat(price.replace('$', '')),
                        appointmentTime: selectedTime,
                        calendarEventId: bookingData.eventId,
                        passengers,
                    }),
                });
            } catch (dbError) {
                // Don't fail the booking if SQL logging fails
                console.warn("Failed to log to database:", dbError);
            }

            // Send receipt email
            await fetch("/api/book", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: customerName,
                    email: customerEmail,
                    phone: customerPhone,
                    passengers,
                    pickup,
                    dropoff,
                    price,
                    appointmentStart: selectedTime,
                    tripDetails: {
                        dist: tripDistance || "N/A",
                        time: tripDuration || "N/A",
                    },
                }),
            });

            onBookingComplete(bookingData.eventId);
        } catch (err: any) {
            setError(err.message);
            console.error("Booking error:", err);
        } finally {
            setBooking(false);
        }
    };

    // Check if a date is blocked
    const isDateBlocked = (date: Date) => {
        if (!status) return false;

        // Use local YYYY-MM-DD to match backend return which is YYYY-MM-DD
        // This assumes user is browsing in a similar timezone or we just respect strict date matching
        const ymd = date.toLocaleDateString("en-CA");

        // Check upcoming
        if (status.upcoming.some(u => u.date === ymd)) return true;

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
                                        onClick={() => setSelectedTime(slot.start)}
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

            {/* Buffer Info */}
            {selectedTime && (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 text-sm">
                    <div className="flex items-start gap-2">
                        <CheckCircle className="text-blue-400 flex-shrink-0 mt-0.5" size={16} />
                        <div className="text-blue-100">
                            <strong>Appointment includes buffers:</strong>
                            <ul className="mt-2 space-y-1 text-xs">
                                <li>• <strong>30 min before:</strong> Driver travel time to pickup</li>
                                <li>• <strong>1 hour:</strong> Your trip</li>
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

            {/* Confirm Button */}
            <button
                onClick={handleBooking}
                disabled={!selectedTime || booking}
                className={`w-full bg-cyan-600 text-white font-bold py-4 rounded-xl hover:bg-cyan-700 shadow-lg shadow-cyan-500/20 flex justify-center items-center gap-2 text-lg transition-all ${!selectedTime || booking ? "opacity-50 cursor-not-allowed" : ""
                    }`}
            >
                {booking ? "Confirming Booking..." : "Confirm Appointment"}
            </button>
        </div>
    );
}
