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
                    `/api/calendar/availability?date=${selectedDate.toISOString()}`
                );
                const data = await response.json();

                if (data.success) {
                    setAvailableSlots(data.slots);
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
            const bookingResponse = await fetch("/api/calendar/book", {
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
                }),
            });

            const bookingData = await bookingResponse.json();

            if (!bookingData.success) {
                throw new Error(bookingData.error || "Failed to create booking");
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

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-top-4 duration-500">
            <div className="flex items-center gap-3 mb-4">
                <Calendar className="text-red-500" size={24} />
                <h3 className="text-xl font-bold text-white">Select Your Appointment Time</h3>
            </div>

            {/* Date Selection */}
            <div>
                <label className="text-xs font-bold text-gray-400 tracking-widest uppercase mb-3 block">
                    Choose Date
                </label>
                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                    {availableDates.slice(0, 15).map((date) => {
                        const isSelected =
                            selectedDate?.toDateString() === date.toDateString();
                        return (
                            <button
                                key={date.toISOString()}
                                onClick={() => {
                                    setSelectedDate(date);
                                    setSelectedTime(null);
                                }}
                                className={`p-3 rounded-lg border transition-all text-center ${isSelected
                                        ? "bg-red-600 border-red-600 text-white"
                                        : "bg-white/5 border-white/10 text-gray-300 hover:bg-white/10 hover:border-white/20"
                                    }`}
                            >
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
                                                ? "bg-red-600 border-red-600 text-white"
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
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm text-red-100">
                    {error}
                </div>
            )}

            {/* Confirm Button */}
            <button
                onClick={handleBooking}
                disabled={!selectedTime || booking}
                className={`w-full bg-[#D12630] text-white font-bold py-4 rounded-xl hover:bg-[#b01e26] shadow-lg shadow-red-500/20 flex justify-center items-center gap-2 text-lg transition-all ${!selectedTime || booking ? "opacity-50 cursor-not-allowed" : ""
                    }`}
            >
                {booking ? "Confirming Booking..." : "Confirm Appointment"}
            </button>
        </div>
    );
}
