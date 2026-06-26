"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface DatePickerCalendarProps {
    selected: Date | null;
    onSelect: (date: Date) => void;
    isBlocked: (date: Date) => boolean;
    maxDays?: number; // horizon in days from today
    accentColor?: "cyan" | "blue";
}

export default function DatePickerCalendar({
    selected,
    onSelect,
    isBlocked,
    maxDays = 90,
    accentColor = "cyan",
}: DatePickerCalendarProps) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const horizon = new Date(today);
    horizon.setDate(today.getDate() + maxDays);

    const [viewYear, setViewYear] = useState(today.getFullYear());
    const [viewMonth, setViewMonth] = useState(today.getMonth());

    const accent = accentColor === "blue"
        ? { sel: "bg-blue-600 border-blue-600 shadow-blue-500/20", dot: "bg-blue-400" }
        : { sel: "bg-cyan-600 border-cyan-600 shadow-cyan-500/20", dot: "bg-cyan-400" };

    const firstOfMonth = new Date(viewYear, viewMonth, 1);
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const startDow = firstOfMonth.getDay(); // 0=Sun

    const prevMonth = () => {
        if (viewMonth === 0) { setViewMonth(11); setViewYear(y => y - 1); }
        else setViewMonth(m => m - 1);
    };
    const nextMonth = () => {
        if (viewMonth === 11) { setViewMonth(0); setViewYear(y => y + 1); }
        else setViewMonth(m => m + 1);
    };

    // Disable prev if the current month is the same as today's month
    const canGoPrev = viewYear > today.getFullYear() || viewMonth > today.getMonth();
    // Disable next if the entire next month is beyond the horizon
    const firstOfNext = new Date(viewYear, viewMonth + 1, 1);
    const canGoNext = firstOfNext <= horizon;

    const days: (Date | null)[] = [
        ...Array(startDow).fill(null),
        ...Array.from({ length: daysInMonth }, (_, i) => new Date(viewYear, viewMonth, i + 1)),
    ];

    // Pad to full weeks
    while (days.length % 7 !== 0) days.push(null);

    const MONTH_NAMES = ["January","February","March","April","May","June",
        "July","August","September","October","November","December"];
    const DOW = ["Su","Mo","Tu","We","Th","Fr","Sa"];

    return (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 select-none">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <button
                    onClick={prevMonth}
                    disabled={!canGoPrev}
                    className="p-1.5 rounded-lg hover:bg-white/10 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
                >
                    <ChevronLeft size={18} className="text-gray-300" />
                </button>
                <span className="text-white font-semibold text-sm">
                    {MONTH_NAMES[viewMonth]} {viewYear}
                </span>
                <button
                    onClick={nextMonth}
                    disabled={!canGoNext}
                    className="p-1.5 rounded-lg hover:bg-white/10 disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
                >
                    <ChevronRight size={18} className="text-gray-300" />
                </button>
            </div>

            {/* Day-of-week headers */}
            <div className="grid grid-cols-7 mb-1">
                {DOW.map(d => (
                    <div key={d} className="text-center text-[10px] font-bold text-gray-500 uppercase py-1">
                        {d}
                    </div>
                ))}
            </div>

            {/* Day grid */}
            <div className="grid grid-cols-7 gap-y-1">
                {days.map((date, idx) => {
                    if (!date) return <div key={`empty-${idx}`} />;

                    const isPast = date < today;
                    const isBeyond = date > horizon;
                    const blocked = isBlocked(date);
                    const disabled = isPast || isBeyond || blocked;
                    const isSelected = selected?.toDateString() === date.toDateString();
                    const isToday = date.toDateString() === today.toDateString();

                    return (
                        <button
                            key={date.toISOString()}
                            disabled={disabled}
                            onClick={() => onSelect(date)}
                            className={[
                                "relative flex items-center justify-center rounded-lg h-9 text-sm font-medium transition-all border",
                                isSelected
                                    ? `${accent.sel} text-white shadow-lg border-transparent`
                                    : blocked
                                        ? "bg-red-900/10 border-red-900/20 text-red-500/40 cursor-not-allowed"
                                        : disabled
                                            ? "bg-transparent border-transparent text-gray-700 cursor-not-allowed"
                                            : "bg-transparent border-transparent text-gray-300 hover:bg-white/10 hover:border-white/10 cursor-pointer",
                            ].join(" ")}
                        >
                            {date.getDate()}
                            {isToday && !isSelected && (
                                <span className={`absolute bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full ${accent.dot}`} />
                            )}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
