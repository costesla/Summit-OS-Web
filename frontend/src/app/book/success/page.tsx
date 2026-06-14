"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { CheckCircle, XCircle, Loader2, Mail } from "lucide-react";

interface BookingDetails {
    customerEmail: string | null;
    amount: number | null;
    eventId: string | null;
}

function SuccessContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const sessionId = searchParams.get('session_id');

    const [status, setStatus] = useState<'loading' | 'success' | 'pending' | 'error'>('loading');
    const [errorMsg, setErrorMsg] = useState('');
    const [bookingDetails, setBookingDetails] = useState<BookingDetails | null>(null);

    useEffect(() => {
        // Direct booking (Venmo/Zelle) — already confirmed server-side, just show success
        const isDirect = searchParams.get('direct') === 'true';
        if (isDirect) {
            setStatus('success');
            return;
        }

        if (!sessionId) {
            setStatus('error');
            setErrorMsg('Invalid session identifier.');
            return;
        }

        // Stripe only redirects here after the charge succeeds, so confirmation
        // must never hinge on this request: the webhook fulfills server-side.
        // If finalize is slow or unreachable, show "pending" rather than spin forever.
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);

        const finalize = async () => {
            try {
                const res = await fetch('/api/finalize-booking', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId }),
                    signal: controller.signal
                });

                const data = await res.json();
                if (data.success) {
                    setStatus('success');
                    setBookingDetails({
                        customerEmail: data.customerEmail || null,
                        amount: data.amount || null,
                        eventId: data.eventId || null,
                    });
                } else if (data.error === 'Payment not completed') {
                    setStatus('error');
                    setErrorMsg(data.error);
                } else {
                    // Payment is done; only the booking/receipt step misbehaved
                    setStatus('pending');
                }
            } catch (err: any) {
                setStatus('pending');
            } finally {
                clearTimeout(timeout);
            }
        };

        finalize();
        return () => {
            clearTimeout(timeout);
            controller.abort();
        };
    }, [sessionId]);

    return (
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-6 font-sans">
            {/* Confetti animation keyframes */}
            <style>{`
                @keyframes confetti {
                    0% { transform: translateY(0) rotate(0deg) scale(0); opacity: 1; }
                    50% { opacity: 1; }
                    100% { transform: translateY(-200px) rotate(720deg) scale(1); opacity: 0; }
                }
            `}</style>

            <div className="max-w-md w-full bg-white/5 border border-white/10 rounded-2xl p-8 text-center shadow-2xl backdrop-blur-md relative">
                {status === 'loading' && (
                    <div className="flex flex-col items-center animate-in fade-in duration-500">
                        <Loader2 className="w-16 h-16 text-cyan-500 animate-spin mb-6" />
                        <h2 className="text-2xl font-bold tracking-tight mb-2">Confirming Payment...</h2>
                        <p className="text-gray-400 text-sm">Please wait while we finalize your appointment.</p>
                    </div>
                )}

                {status === 'success' && (
                    <div className="flex flex-col items-center animate-in zoom-in-95 fade-in duration-500">
                        {/* Animated checkmark with ring */}
                        <div className="relative mb-6">
                            <div className="w-24 h-24 rounded-full bg-green-500/10 flex items-center justify-center border-2 border-green-500/30">
                                <CheckCircle className="w-14 h-14 text-green-500" />
                            </div>
                            <div className="absolute inset-0 rounded-full border-2 border-green-500/20 animate-ping" />
                        </div>

                        <p className="text-green-400/80 text-xs font-mono uppercase tracking-[0.2em] mb-2">Transaction Complete</p>
                        <h2 className="text-3xl font-bold tracking-tight mb-2 text-white">Booking Confirmed!</h2>

                        {/* Amount display if available */}
                        {bookingDetails?.amount && (
                            <p className="text-2xl font-bold text-green-400 mb-4">${(bookingDetails.amount / 100).toFixed(2)}</p>
                        )}

                        <p className="text-gray-300 text-base mb-2">
                            Your ride has been scheduled and a confirmation has been sent.
                        </p>

                        {/* Receipt notice - only show when email was used */}
                        {bookingDetails?.customerEmail && (
                            <p className="text-gray-400 text-sm mb-6 flex items-center gap-2">
                                <Mail className="w-4 h-4" />
                                A receipt has been sent to {bookingDetails.customerEmail}
                            </p>
                        )}

                        {/* Confetti dots animation */}
                        <div className="absolute inset-0 pointer-events-none overflow-hidden">
                            {Array.from({length: 20}).map((_, i) => (
                                <div
                                    key={i}
                                    className="absolute w-2 h-2 rounded-full"
                                    style={{
                                        left: `${Math.random() * 100}%`,
                                        top: `${Math.random() * 100}%`,
                                        backgroundColor: ['#4ade80', '#60a5fa', '#f472b6', '#facc15', '#a78bfa'][i % 5],
                                        animation: `confetti ${2 + Math.random() * 3}s ease-out ${Math.random() * 0.5}s forwards`,
                                        opacity: 0,
                                    }}
                                />
                            ))}
                        </div>

                        <button
                            onClick={() => router.push('/')}
                            className="w-full bg-cyan-600 text-white font-bold py-3 rounded-lg hover:bg-cyan-700 transition-colors mt-4"
                        >
                            Return Home
                        </button>
                    </div>
                )}

                {status === 'pending' && (
                    <div className="flex flex-col items-center animate-in zoom-in-95 fade-in duration-500">
                        <CheckCircle className="w-20 h-20 text-green-500 mb-6" />
                        <h2 className="text-3xl font-bold tracking-tight mb-2 text-white">Payment Received!</h2>
                        <p className="text-gray-300 text-base mb-8">
                            Your payment was processed successfully. We're finishing up your booking confirmation — your receipt email will arrive shortly. No further action is needed.
                        </p>
                        <button
                            onClick={() => router.push('/')}
                            className="w-full bg-cyan-600 text-white font-bold py-3 rounded-lg hover:bg-cyan-700 transition-colors"
                        >
                            Return Home
                        </button>
                    </div>
                )}

                {status === 'error' && (
                    <div className="flex flex-col items-center animate-in zoom-in-95 fade-in duration-500">
                        <XCircle className="w-20 h-20 text-red-500 mb-6" />
                        <h2 className="text-2xl font-bold tracking-tight mb-2 text-white">Something went wrong</h2>
                        <p className="text-red-300/80 text-sm mb-8 bg-red-500/10 p-4 rounded-xl border border-red-500/20">
                            {errorMsg}. If you see a charge on your account, please contact us immediately.
                        </p>
                        <button
                            onClick={() => router.push('/book')}
                            className="w-full bg-white/10 text-white font-bold py-3 rounded-lg hover:bg-white/20 transition-colors"
                        >
                            Return to Booking Engine
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function BookingSuccessPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-6 font-sans">
                <Loader2 className="w-16 h-16 text-cyan-500 animate-spin mb-6" />
                <h2 className="text-2xl font-bold tracking-tight">Loading Secure Connection...</h2>
            </div>
        }>
            <SuccessContent />
        </Suspense>
    );
}
