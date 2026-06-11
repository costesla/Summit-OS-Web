import React, { useState, useEffect, useCallback } from 'react';
import { Receipt, RefreshCw, CheckCircle2, Loader2 } from 'lucide-react';

const AZURE_BASE = import.meta.env.VITE_PUBLIC_API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'https://summitos-api.azurewebsites.net/api';

interface UnpaidTrip {
    rideId: string;
    start: string | null;
    fare: number;
    classification: string | null;
    pickup: string | null;
    dropoff: string | null;
    customerName: string | null;
    paymentMethod: string | null;
}

// Payment-channel hints for repeat clients (third-party payers etc.)
const CLIENT_PAYMENT_HINTS: Record<string, string> = {
    terrance: 'Cash App — often paid by sister Monique',
};

const paymentHint = (name: string | null): string | null => {
    if (!name) return null;
    const lower = name.toLowerCase();
    for (const key of Object.keys(CLIENT_PAYMENT_HINTS)) {
        if (lower.includes(key)) return CLIENT_PAYMENT_HINTS[key];
    }
    return null;
};

const UnpaidInvoicesPanel: React.FC = () => {
    const [trips, setTrips] = useState<UnpaidTrip[]>([]);
    const [loading, setLoading] = useState(true);
    const [marking, setMarking] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const fetchUnpaid = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`${AZURE_BASE}/unpaid-trips`);
            const data = await res.json();
            if (data.success) {
                setTrips(data.trips || []);
            } else {
                setError(data.error || 'Failed to load unpaid trips');
            }
        } catch (e: any) {
            setError(e.message || 'Connection error');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchUnpaid(); }, [fetchUnpaid]);

    const markPaid = async (rideId: string) => {
        setMarking(rideId);
        try {
            const res = await fetch(`${AZURE_BASE}/mark-paid`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rideId }),
            });
            const data = await res.json();
            if (data.success) {
                setTrips(prev => prev.filter(t => t.rideId !== rideId));
            } else {
                setError(data.error || `Failed to mark ${rideId} paid`);
            }
        } catch (e: any) {
            setError(e.message || 'Connection error');
        } finally {
            setMarking(null);
        }
    };

    const total = trips.reduce((s, t) => s + t.fare, 0);

    const fmtDate = (iso: string | null) => {
        if (!iso) return 'unscheduled';
        try {
            return new Date(iso).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
            });
        } catch {
            return iso;
        }
    };

    return (
        <div className="p-6 rounded-2xl border border-rose-200/80 bg-rose-50/40 shadow-sm backdrop-blur-md relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-rose-500/5 blur-3xl rounded-full pointer-events-none" />
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-base font-bold text-slate-800 flex items-center gap-2">
                        <Receipt className="w-4 h-4 text-rose-600" /> Unpaid Invoices
                    </h2>
                    <p className="text-xs font-semibold text-slate-500 tracking-wide">Invoice · Cash · P2P — awaiting payment</p>
                </div>
                <div className="flex items-center gap-3">
                    {trips.length > 0 && (
                        <span className="text-xl font-black text-rose-700">${total.toFixed(2)}</span>
                    )}
                    <button onClick={fetchUnpaid} disabled={loading}
                        className="text-slate-400 hover:text-rose-600 transition-colors border-none bg-transparent">
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {error && (
                <p className="text-xs text-rose-600 bg-rose-100/60 rounded-lg p-2 mb-3">{error}</p>
            )}

            <div className="space-y-2 max-h-[260px] overflow-y-auto">
                {loading && trips.length === 0 ? (
                    <p className="text-center text-xs text-slate-400 italic py-3">loading…</p>
                ) : trips.length === 0 ? (
                    <p className="text-center text-xs text-slate-400 italic py-3">// all bookings settled 🎉</p>
                ) : trips.map(t => {
                    const hint = paymentHint(t.customerName) || paymentHint(t.rideId);
                    return (
                        <div key={t.rideId} className="p-3 rounded-xl bg-white/70 border border-slate-200/80 hover:bg-slate-50 transition-colors shadow-sm">
                            <div className="flex items-center justify-between gap-2">
                                <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-black text-slate-800">${t.fare.toFixed(2)}</span>
                                        <span className="text-xs font-semibold text-slate-600 truncate">{t.customerName || t.rideId}</span>
                                        {t.paymentMethod && (
                                            <span className="text-[9px] uppercase font-bold text-slate-400 border border-slate-200 rounded px-1">{t.paymentMethod}</span>
                                        )}
                                    </div>
                                    <p className="text-[10px] text-slate-500 truncate">{fmtDate(t.start)} · {t.pickup || '?'} → {t.dropoff || '?'}</p>
                                    {hint && <p className="text-[10px] text-violet-600 font-semibold">{hint}</p>}
                                </div>
                                <button onClick={() => markPaid(t.rideId)} disabled={marking === t.rideId}
                                    className="shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wide bg-emerald-500 text-white hover:bg-emerald-600 transition-all shadow-sm border-none disabled:opacity-60">
                                    {marking === t.rideId
                                        ? <Loader2 className="w-3 h-3 animate-spin" />
                                        : <CheckCircle2 className="w-3 h-3" />}
                                    Mark Paid
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default UnpaidInvoicesPanel;
