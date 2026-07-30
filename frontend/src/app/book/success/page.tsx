"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2 } from "lucide-react";
import PaymentConfirmation, { ConfirmationShell } from "../../../components/PaymentConfirmation";

/**
 * Where a booking Checkout Session lands the passenger.
 *
 * Two jobs, deliberately decoupled:
 *
 *  1. Fulfillment — POST /api/finalize-booking creates the calendar event, logs
 *     the trip, and sends the receipt. This must keep running; it is the only
 *     thing that books the ride. It is fired here and never blocks the UI.
 *  2. Confirmation — rendered from GET /api/payments/confirm, the same source
 *     /invoice/success uses, so the passenger sees one confirmation design with
 *     a real invoice and receipt behind it.
 *
 * Finalize is idempotent server-side (SQL claim), so a reload can't double-book.
 */

function BookingSuccessContent() {
    const searchParams = useSearchParams();
    const sessionId = searchParams.get("session_id");
    const isDirect = searchParams.get("direct") === "true";

    // null = finalize hasn't answered yet, so we claim nothing about email.
    const [receiptEmailed, setReceiptEmailed] = useState<boolean | null>(null);

    useEffect(() => {
        if (isDirect || !sessionId) return;

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);

        (async () => {
            try {
                const res = await fetch("/api/finalize-booking", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ session_id: sessionId }),
                    signal: controller.signal,
                });
                const data = await res.json();
                // Only an explicit true means the passenger's receipt actually
                // sent. Anything else stays unknown and the page stays quiet
                // rather than promising an email that never arrived.
                setReceiptEmailed(data?.receiptEmailed === true ? true : null);
            } catch {
                // Fulfillment also runs from the Stripe webhook, and the
                // confirmation comes from Stripe directly, so a failure here
                // must not degrade what the passenger sees.
            } finally {
                clearTimeout(timeout);
            }
        })();

        return () => {
            clearTimeout(timeout);
            controller.abort();
        };
    }, [sessionId, isDirect]);

    // Venmo/Zelle bookings are confirmed server-side before redirect and have no
    // Stripe session to look up — so there is no payment to confirm here.
    if (isDirect) {
        return (
            <ConfirmationShell>
                <div className="flex flex-col items-center text-center py-2">
                    <div className="w-14 h-14 rounded-full bg-emerald-50 flex items-center justify-center mb-5">
                        <CheckCircle2 className="w-8 h-8 text-emerald-600" />
                    </div>
                    <h1 className="text-2xl font-semibold tracking-tight">Booking confirmed</h1>
                    <p className="text-slate-600 text-sm mt-3 leading-relaxed">
                        Your ride is scheduled and a confirmation is on its way by email.
                        Payment instructions are included in that message.
                    </p>
                    <p className="text-slate-600 text-sm mt-4">
                        Cabin access opens shortly before your pickup time.
                    </p>
                </div>
            </ConfirmationShell>
        );
    }

    return <PaymentConfirmation sessionId={sessionId} receiptEmailed={receiptEmailed} />;
}

export default function BookingSuccessPage() {
    return (
        <Suspense
            fallback={
                <ConfirmationShell>
                    <div className="flex flex-col items-center text-center py-4">
                        <Loader2 className="w-10 h-10 text-[#2563eb] animate-spin mb-5" />
                        <h1 className="text-xl font-semibold">Confirming your payment…</h1>
                    </div>
                </ConfirmationShell>
            }
        >
            <BookingSuccessContent />
        </Suspense>
    );
}
