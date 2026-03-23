"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { CheckCircle, XCircle, Loader2 } from "lucide-react";

export default function BookingSuccessPage() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const sessionId = searchParams.get('session_id');

    const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
    const [errorMsg, setErrorMsg] = useState('');

    useEffect(() => {
        if (!sessionId) {
            setStatus('error');
            setErrorMsg('Invalid session identifier.');
            return;
        }

        const finalize = async () => {
            try {
                const res = await fetch('/api/finalize-booking', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId })
                });

                const data = await res.json();
                if (data.success) {
                    setStatus('success');
                } else {
                    setStatus('error');
                    setErrorMsg(data.error || 'Failed to confirm booking.');
                }
            } catch (err: any) {
                setStatus('error');
                setErrorMsg('An unexpected error occurred while finalizing your booking.');
            }
        };

        finalize();
    }, [sessionId]);

    return (
        <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-6 font-sans">
            <div className="max-w-md w-full bg-white/5 border border-white/10 rounded-2xl p-8 text-center shadow-2xl backdrop-blur-md">
                {status === 'loading' && (
                    <div className="flex flex-col items-center animate-in fade-in duration-500">
                        <Loader2 className="w-16 h-16 text-cyan-500 animate-spin mb-6" />
                        <h2 className="text-2xl font-bold tracking-tight mb-2">Confirming Payment...</h2>
                        <p className="text-gray-400 text-sm">Please wait while we finalize your appointment.</p>
                    </div>
                )}

                {status === 'success' && (
                    <div className="flex flex-col items-center animate-in zoom-in-95 fade-in duration-500">
                        <CheckCircle className="w-20 h-20 text-green-500 mb-6" />
                        <h2 className="text-3xl font-bold tracking-tight mb-2 text-white">Booking Confirmed!</h2>
                        <p className="text-gray-300 text-base mb-8">
                            We've successfully received your payment. A confirmation and receipt email have been sent to you.
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
