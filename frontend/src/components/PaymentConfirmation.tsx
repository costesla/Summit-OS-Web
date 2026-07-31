"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, FileText, Loader2, Receipt } from "lucide-react";

/**
 * The confirmation a passenger sees after paying — shared by /invoice/success
 * (post-trip Payment Links) and /book/success (booking Checkout Sessions), with
 * the copy switching on the `source` the backend reports.
 *
 * Payload comes from GET /api/payments/confirm, which returns a whitelist and
 * never the raw Stripe session.
 */

const CONTACT_EMAIL = "peter.teehan@costesla.com";
const CONTACT_PHONE_DISPLAY = "(719) 433-4851";
const CONTACT_PHONE_HREF = "tel:7194334851";

/** Stripe finalizes the invoice a few seconds after the session completes, so
 *  the PDF and hosted links are legitimately null on the first call. */
const INVOICE_POLL_ATTEMPTS = 5;
const INVOICE_POLL_MS = 2500;
/** How many times to re-ask before admitting we can't confirm the payment. */
const PENDING_POLL_ATTEMPTS = 3;
const PENDING_POLL_MS = 3000;

export interface ConfirmPayload {
    status: "paid" | "pending" | "not_found";
    amountTotal?: string;
    currency?: string;
    firstName?: string | null;
    invoiceNumber?: string | null;
    stripeInvoiceNumber?: string | null;
    hostedInvoiceUrl?: string | null;
    invoicePdf?: string | null;
    receiptUrl?: string | null;
    source?: string;
    pickup?: string;
    dropoff?: string;
    appointmentStart?: string;
    fareString?: string;
}

type View = "loading" | "paid" | "pending" | "notfound";

interface Props {
    sessionId: string | null;
    /** Booking flow only: whether finalize actually sent the receipt email.
     *  `null` means unknown — in which case we claim nothing. */
    receiptEmailed?: boolean | null;
}

function Logo() {
    return (
        <div className="flex justify-center mb-8">
            {/* logo.png is a fully opaque near-black square (verified: no
                transparent pixels), so on this light background it has to be
                clipped into a tile or it reads as a raw black rectangle. Same
                treatment AppShell, Navbar and Footer already give it. Drop in a
                transparent version later and this still renders correctly — it
                simply stops looking like a tile. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src="/logo.png"
                alt="COS Tesla"
                width={128}
                height={126}
                className="w-32 max-w-[40vw] h-auto rounded-2xl shadow-sm"
            />
        </div>
    );
}

/** Exported so the cash/Venmo booking path can reuse the branded frame without
 *  pretending a Stripe payment happened. */
export function ConfirmationShell({ children }: { children: React.ReactNode }) {
    return (
        <div className="min-h-screen bg-[#f8fafc] text-slate-900 px-5 py-14">
            <div className="mx-auto w-full max-w-lg">
                <Logo />
                <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-8">
                    {children}
                </div>
                <p className="mt-6 text-center text-xs text-slate-500">
                    Questions? {" "}
                    <a href={`mailto:${CONTACT_EMAIL}`} className="text-[#2563eb] hover:underline">
                        {CONTACT_EMAIL}
                    </a>
                    {" · "}
                    <a href={CONTACT_PHONE_HREF} className="text-[#2563eb] hover:underline">
                        {CONTACT_PHONE_DISPLAY}
                    </a>
                </p>
            </div>
        </div>
    );
}

function formatAppointment(raw?: string): string | null {
    if (!raw) return null;
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return raw;
    return parsed.toLocaleString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

export default function PaymentConfirmation({ sessionId, receiptEmailed = null }: Props) {
    const [view, setView] = useState<View>("loading");
    const [data, setData] = useState<ConfirmPayload | null>(null);
    const cancelled = useRef(false);

    const fetchOnce = useCallback(async (id: string): Promise<ConfirmPayload | null> => {
        try {
            const res = await fetch(`/api/payments/confirm?session_id=${encodeURIComponent(id)}`, {
                headers: { Accept: "application/json" },
            });
            // A non-JSON body means something upstream served us a page, not the
            // API. Treat it as "no answer yet" rather than crashing on parse.
            const body = (await res.json()) as ConfirmPayload;
            if (res.status === 404) return { status: "not_found" };
            return body;
        } catch {
            return null;
        }
    }, []);

    useEffect(() => {
        cancelled.current = false;
        if (!sessionId) {
            setView("notfound");
            return;
        }

        const run = async () => {
            let pendingTries = 0;
            let invoiceTries = 0;

            while (!cancelled.current) {
                const body = await fetchOnce(sessionId);
                if (cancelled.current) return;

                if (!body) {
                    // Network hiccup — reuse the pending budget rather than
                    // failing the passenger on one dropped request.
                    pendingTries += 1;
                    if (pendingTries >= PENDING_POLL_ATTEMPTS) {
                        setView("pending");
                        return;
                    }
                    await sleep(PENDING_POLL_MS);
                    continue;
                }

                if (body.status === "not_found") {
                    setView("notfound");
                    return;
                }

                if (body.status === "pending") {
                    pendingTries += 1;
                    if (pendingTries >= PENDING_POLL_ATTEMPTS) {
                        setView("pending");
                        return;
                    }
                    await sleep(PENDING_POLL_MS);
                    continue;
                }

                // Paid. Show it immediately — the receipt link is already live.
                setData(body);
                setView("paid");

                // Then keep quietly polling only until the invoice links appear,
                // so we never render a dead "Download PDF".
                const haveInvoice = Boolean(body.invoicePdf || body.hostedInvoiceUrl);
                invoiceTries += 1;
                if (haveInvoice || invoiceTries >= INVOICE_POLL_ATTEMPTS) return;
                await sleep(INVOICE_POLL_MS);
            }
        };

        run();
        return () => {
            cancelled.current = true;
        };
    }, [sessionId, fetchOnce]);

    if (view === "loading") {
        return (
            <ConfirmationShell>
                <div className="flex flex-col items-center text-center py-4">
                    <Loader2 className="w-10 h-10 text-[#2563eb] animate-spin mb-5" />
                    <h1 className="text-xl font-semibold">Confirming your payment…</h1>
                    <p className="text-slate-500 text-sm mt-2">This only takes a moment.</p>
                </div>
            </ConfirmationShell>
        );
    }

    if (view === "pending") {
        return (
            <ConfirmationShell>
                <div className="flex flex-col items-center text-center py-4">
                    <Loader2 className="w-10 h-10 text-[#2563eb] animate-spin mb-5" />
                    <h1 className="text-xl font-semibold">We&apos;re still confirming your payment…</h1>
                    <p className="text-slate-600 text-sm mt-3 leading-relaxed">
                        If your card was charged, you&apos;re all set — the confirmation is just
                        taking longer than usual to come back. Your receipt will arrive by email.
                    </p>
                    <p className="text-slate-500 text-sm mt-4">
                        If anything looks wrong, contact us and we&apos;ll sort it out right away.
                    </p>
                </div>
            </ConfirmationShell>
        );
    }

    if (view === "notfound" || !data) {
        return (
            <ConfirmationShell>
                <div className="flex flex-col items-center text-center py-4">
                    <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-5">
                        <FileText className="w-6 h-6 text-slate-400" />
                    </div>
                    <h1 className="text-xl font-semibold">We couldn&apos;t find that payment</h1>
                    <p className="text-slate-600 text-sm mt-3 leading-relaxed">
                        This confirmation link may have expired, or the payment was never
                        completed. Nothing has been charged if you didn&apos;t finish checkout.
                    </p>
                    <p className="text-slate-500 text-sm mt-4">
                        If you believe you were charged, get in touch and we&apos;ll confirm it
                        for you.
                    </p>
                </div>
            </ConfirmationShell>
        );
    }

    const isBooking = data.source !== "post_trip_invoice";
    const appointment = formatAppointment(data.appointmentStart);
    const invoicePending = !data.invoicePdf && !data.hostedInvoiceUrl;

    return (
        <ConfirmationShell>
            <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-emerald-50 flex items-center justify-center mb-5">
                    <CheckCircle2 className="w-8 h-8 text-emerald-600" />
                </div>

                <h1 className="text-2xl font-semibold tracking-tight">
                    Payment received — thank you{data.firstName ? `, ${data.firstName}` : ""}
                </h1>

                {data.amountTotal && (
                    <p className="mt-4 text-4xl font-semibold text-slate-900">{data.amountTotal}</p>
                )}

                {data.invoiceNumber && (
                    <p className="mt-2 text-sm text-slate-500">
                        Invoice{" "}
                        <span className="font-medium text-slate-700">{data.invoiceNumber}</span>
                        {data.stripeInvoiceNumber ? ` · Stripe ${data.stripeInvoiceNumber}` : ""}
                    </p>
                )}
            </div>

            {isBooking && (appointment || data.pickup || data.dropoff) && (
                <div className="mt-7 rounded-xl bg-slate-50 border border-slate-200 p-5 text-sm">
                    <h2 className="font-semibold text-slate-900 mb-3">Your trip</h2>
                    <dl className="space-y-2">
                        {appointment && (
                            <Row label="Pickup time" value={appointment} />
                        )}
                        {data.pickup && <Row label="From" value={data.pickup} />}
                        {data.dropoff && <Row label="To" value={data.dropoff} />}
                        {data.fareString && <Row label="Fare" value={data.fareString} />}
                    </dl>
                </div>
            )}

            <div className="mt-7 flex flex-col gap-2.5">
                {data.hostedInvoiceUrl && (
                    <a
                        href={data.hostedInvoiceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 w-full rounded-lg bg-[#2563eb] px-4 py-3 text-sm font-semibold text-white hover:bg-[#1d4ed8] transition-colors"
                    >
                        <FileText className="w-4 h-4" />
                        View invoice
                    </a>
                )}
                {data.invoicePdf && (
                    <a
                        href={data.invoicePdf}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 w-full rounded-lg border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                        <Download className="w-4 h-4" />
                        Download PDF
                    </a>
                )}
                {data.receiptUrl && (
                    <a
                        href={data.receiptUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`flex items-center justify-center gap-2 w-full rounded-lg px-4 py-3 text-sm font-semibold transition-colors ${
                            invoicePending
                                ? "bg-[#2563eb] text-white hover:bg-[#1d4ed8]"
                                : "border border-slate-300 text-slate-700 hover:bg-slate-50"
                        }`}
                    >
                        <Receipt className="w-4 h-4" />
                        View receipt
                    </a>
                )}
            </div>

            {invoicePending && (
                <p className="mt-4 text-center text-xs text-slate-500">
                    Your invoice is being prepared — it will be emailed to you shortly.
                </p>
            )}

            {isBooking && (
                <p className="mt-6 text-center text-sm text-slate-600 leading-relaxed">
                    Cabin access opens shortly before your pickup time.
                </p>
            )}

            {receiptEmailed === true && (
                <p className="mt-3 text-center text-xs text-slate-500">
                    A confirmation email is on its way.
                </p>
            )}
        </ConfirmationShell>
    );
}

function Row({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex justify-between gap-4">
            <dt className="text-slate-500 shrink-0">{label}</dt>
            <dd className="text-slate-900 font-medium text-right">{value}</dd>
        </div>
    );
}

function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
