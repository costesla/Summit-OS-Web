/**
 * Calendar Management Utilities
 * Handles Microsoft Graph Calendar integration for booking system
 */

export interface TimeSlot {
    start: Date;
    end: Date;
    available: boolean;
}

export interface BookingDetails {
    customerName: string;
    customerEmail: string;
    customerPhone: string;
    pickup: string;
    dropoff: string;
    appointmentStart: Date;
    duration: number; // in minutes
    price: string;
    passengers: number;
}

export interface CalendarEvent {
    id: string;
    subject: string;
    start: Date;
    end: Date;
    location: string;
}

export interface HoursOfOperation {
    start: string; // "04:00"
    end: string;   // "22:00"
}

const BUFFER_MINUTES = 30;
const DEFAULT_TRIP_DURATION = 60; // minutes

/**
 * Get hours of operation for a given day
 */
export function getHoursForDay(date: Date): HoursOfOperation | null {
    const day = date.getDay(); // 0 = Sunday, 1 = Monday, etc.

    const hours: Record<number, HoursOfOperation> = {
        1: { start: "04:30", end: "22:00" }, // Monday
        2: { start: "04:30", end: "22:00" }, // Tuesday
        3: { start: "04:30", end: "22:00" }, // Wednesday
        4: { start: "04:30", end: "22:00" }, // Thursday
        5: { start: "04:30", end: "00:00" }, // Friday (Midnight)
        6: { start: "08:00", end: "23:00" }, // Saturday
        0: { start: "08:00", end: "18:00" }, // Sunday
    };

    return hours[day] || null;
}

/**
 * Calculate buffer times for a booking
 * Returns: { bufferStart, appointmentStart, appointmentEnd, bufferEnd }
 */
export function calculateBuffers(appointmentStart: Date, durationMinutes: number = DEFAULT_TRIP_DURATION) {
    const bufferStart = new Date(appointmentStart.getTime() - BUFFER_MINUTES * 60000);
    const appointmentEnd = new Date(appointmentStart.getTime() + durationMinutes * 60000);
    const bufferEnd = new Date(appointmentEnd.getTime() + BUFFER_MINUTES * 60000);

    return {
        bufferStart,
        appointmentStart,
        appointmentEnd,
        bufferEnd,
    };
}

/**
 * Check if a time is within hours of operation
 */
export function isWithinHours(date: Date): boolean {
    const hours = getHoursForDay(date);
    if (!hours) return false;

    const timeStr = date.toTimeString().slice(0, 5); // "HH:MM"

    // Handle midnight crossover (Friday)
    if (hours.end === "00:00") {
        return timeStr >= hours.start || timeStr <= "00:00";
    }

    return timeStr >= hours.start && timeStr <= hours.end;
}

/**
 * Generate time slots for a given date
 * Returns array of 30-minute intervals within hours of operation
 */
export function generateTimeSlotsForDay(date: Date): Date[] {
    const hours = getHoursForDay(date);
    if (!hours) return [];

    const slots: Date[] = [];
    const [startHour, startMin] = hours.start.split(":").map(Number);
    const [endHour, endMin] = hours.end.split(":").map(Number);

    const startTime = new Date(date);
    startTime.setHours(startHour, startMin, 0, 0);

    const endTime = new Date(date);
    if (endHour === 0) {
        // Midnight - next day
        endTime.setDate(endTime.getDate() + 1);
        endTime.setHours(0, 0, 0, 0);
    } else {
        endTime.setHours(endHour, endMin, 0, 0);
    }

    let current = new Date(startTime);
    while (current < endTime) {
        slots.push(new Date(current));
        current = new Date(current.getTime() + 30 * 60000); // 30-minute intervals
    }

    return slots;
}

/**
 * Check if two time ranges overlap
 */
export function timeRangesOverlap(
    start1: Date,
    end1: Date,
    start2: Date,
    end2: Date
): boolean {
    return start1 < end2 && start2 < end1;
}

/**
 * Format time for display
 */
export function formatTime(date: Date): string {
    return date.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
    });
}

/**
 * Format date for display
 */
export function formatDate(date: Date): string {
    return date.toLocaleDateString("en-US", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
    });
}
