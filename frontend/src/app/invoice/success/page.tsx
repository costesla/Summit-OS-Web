"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import PaymentConfirmation, { ConfirmationShell } from "../../../components/PaymentConfirmation";

/**
 * Where a post-trip invoice Payment Link now lands the payer.
 *
 * Before this page existed, after_completion was unset and Stripe dropped them
 * on stripe.com — they never returned to our site and saw no confirmation.
 */

function InvoiceSuccessContent() {
    const sessionId = useSearchParams().get("session_id");
    return <PaymentConfirmation sessionId={sessionId} />;
}

export default function InvoiceSuccessPage() {
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
            <InvoiceSuccessContent />
        </Suspense>
    );
}
