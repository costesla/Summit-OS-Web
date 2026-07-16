"use client";

import { useState } from "react";
import { Star, Send, CheckCircle } from "lucide-react";

/*
 * B4 Feedback form: rating + free text, POSTs to /api/feedback
 * (linked-backend proxy). If delivery fails — endpoint not yet deployed,
 * or transient — degrade to a mailto fallback instead of a dead end.
 */
export default function FeedbackForm() {
    const [rating, setRating] = useState(0);
    const [hover, setHover] = useState(0);
    const [message, setMessage] = useState("");
    const [contact, setContact] = useState("");
    const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!rating || !message.trim()) return;
        setStatus("sending");
        try {
            const res = await fetch("/api/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ rating, message: message.trim(), contact: contact.trim() }),
            });
            const data = await res.json().catch(() => null);
            setStatus(res.ok && data?.success ? "sent" : "error");
        } catch {
            setStatus("error");
        }
    };

    if (status === "sent") {
        return (
            <div className="flex items-center gap-3 rounded-2xl bg-sos-surface border border-sos-border shadow-sm px-5 py-6 text-sos-main">
                <CheckCircle size={22} className="text-green-400 shrink-0" aria-hidden="true" />
                <p className="text-sm font-medium">Thank you — your feedback went straight to the owner.</p>
            </div>
        );
    }

    return (
        <form onSubmit={submit} className="rounded-2xl bg-sos-surface border border-sos-border shadow-sm px-5 py-5 space-y-4">
            <div className="flex items-center gap-1" role="radiogroup" aria-label="Rating">
                {[1, 2, 3, 4, 5].map((n) => (
                    <button
                        key={n}
                        type="button"
                        role="radio"
                        aria-checked={rating === n}
                        aria-label={`${n} star${n > 1 ? "s" : ""}`}
                        onClick={() => setRating(n)}
                        onMouseEnter={() => setHover(n)}
                        onMouseLeave={() => setHover(0)}
                        className="p-1"
                    >
                        <Star
                            size={26}
                            className={(hover || rating) >= n ? "text-amber-400" : "text-sos-dim"}
                            fill={(hover || rating) >= n ? "currentColor" : "none"}
                        />
                    </button>
                ))}
            </div>

            <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value.slice(0, 2000))}
                placeholder="How was your experience?"
                rows={4}
                className="w-full rounded-xl border border-sos-border bg-white/[0.03] px-4 py-3 text-sm text-sos-main placeholder:text-slate-600 focus:outline-none focus:border-sos-accent focus:ring-1 focus:ring-sos-accent transition-all resize-none"
            />

            <input
                type="text"
                value={contact}
                onChange={(e) => setContact(e.target.value.slice(0, 200))}
                placeholder="Email or phone (optional — if you'd like a reply)"
                className="w-full rounded-xl border border-sos-border bg-white/[0.03] px-4 py-3 text-sm text-sos-main placeholder:text-slate-600 focus:outline-none focus:border-sos-accent focus:ring-1 focus:ring-sos-accent transition-all"
            />

            {status === "error" && (
                <p className="text-xs text-red-400">
                    Couldn&rsquo;t send just now — please email{" "}
                    <a href="mailto:peter.teehan@costesla.com" className="underline font-medium">
                        peter.teehan@costesla.com
                    </a>{" "}
                    instead.
                </p>
            )}

            <button
                type="submit"
                disabled={!rating || !message.trim() || status === "sending"}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-sos-accent hover:bg-cyan-300 text-black font-bold py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
                <Send size={16} aria-hidden="true" />
                {status === "sending" ? "Sending…" : "Send Feedback"}
            </button>
        </form>
    );
}
