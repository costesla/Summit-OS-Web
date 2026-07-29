"use client";

/**
 * Passenger return-trip portal — the destination for the reminder link.
 *
 * This is the only customer-facing surface in the return-trip feature, and the
 * only one reached WITHOUT an account: the link token is the whole credential
 * (there is no passenger account model), so this page is deliberately public
 * and everything it does is scoped by that token server-side.
 *
 * Three things that drove the implementation:
 *
 * 1. The token is a bearer credential, so it does not stay in the address bar.
 *    It is read once and stripped via replaceState. Left in the URL it lands in
 *    browser history, in any screenshot the passenger sends to support, and in
 *    the Referer header of any outbound click.
 *
 * 2. The flight is resolved server-side and referenced by verification id.
 *    This page never sends flight details to `confirm` — it sends the id it was
 *    given. That is what stops a resolved-then-swapped flight.
 *
 * 3. Every resolve costs a billed AeroAPI call, so the button is disabled while
 *    one is in flight and a 429 is rendered as a real message rather than a
 *    retry loop.
 *
 * Read from `window.location.search` rather than `useSearchParams` on purpose:
 * the site is a static export (`output: export`), where `useSearchParams`
 * requires a Suspense boundary and prerenders to empty.
 */

import { useCallback, useEffect, useState } from "react";

const AZURE_BASE =
    process.env.NEXT_PUBLIC_API_BASE_URL || "https://summitos-api.azurewebsites.net/api";

type Candidate = {
    flightNumber: string | null;
    departureAirport: string | null;
    arrivalAirport: string | null;
    isCodeshare?: boolean;
    scheduledArrivalUtc: string | null;
    bestArrivalUtc: string | null;
};

type Phase =
    | "loading"
    | "noToken"
    | "entry"
    | "ambiguous"
    | "confirming"
    | "confirmed"
    | "dead";

const label = "text-xs font-bold tracking-widest uppercase text-gray-400";
const input =
    "w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3 text-white " +
    "placeholder-gray-600 focus:outline-none focus:border-blue-400/60 transition-colors";

function arrivalText(iso: string | null): string {
    if (!iso) return "arrival time to be confirmed";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "arrival time to be confirmed";
    // The passenger's own locale — the flight's timezone is the airport's, and
    // showing that instead is how people miss pickups.
    return d.toLocaleString(undefined, {
        weekday: "short", month: "short", day: "numeric",
        hour: "numeric", minute: "2-digit",
    });
}

export default function ReturnTripPage() {
    const [token, setToken] = useState<string | null>(null);
    const [phase, setPhase] = useState<Phase>("loading");
    const [flightNumber, setFlightNumber] = useState("");
    const [serviceDate, setServiceDate] = useState("");
    const [candidates, setCandidates] = useState<Candidate[]>([]);
    const [chosen, setChosen] = useState<Candidate | null>(null);
    const [verificationId, setVerificationId] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Read the token once, then remove it from the URL. See note 1 above.
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const raw = params.get("t") || params.get("token");
        if (!raw) {
            setPhase("noToken");
            return;
        }
        setToken(raw);
        setPhase("entry");
        params.delete("t");
        params.delete("token");
        const qs = params.toString();
        window.history.replaceState(
            {}, "", window.location.pathname + (qs ? `?${qs}` : ""));
    }, []);

    const post = useCallback(async (path: string, body: Record<string, unknown>) => {
        const res = await fetch(`${AZURE_BASE}/${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(20_000),
        });
        let data: any = null;
        try {
            data = await res.json();
        } catch {
            /* a non-JSON body is a gateway problem, handled below */
        }
        return { res, data };
    }, []);

    const handleResolve = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!token || busy) return;
        setBusy(true);
        setError(null);
        try {
            const { res, data } = await post("return-trips/resolve-flight", {
                token, flightNumber, serviceDate,
            });

            if (res.status === 409 && data?.error?.candidates) {
                setCandidates(data.error.candidates as Candidate[]);
                setPhase("ambiguous");
                return;
            }
            if (!res.ok) {
                // The backend writes these messages to be passenger-safe, so
                // they are shown as-is rather than replaced with a generic one.
                setError(data?.error?.message || "We couldn't check that flight. Please try again.");
                // An unusable link cannot be fixed by retrying — stop offering.
                if (data?.error?.code === "InvalidOrExpiredToken"
                    || data?.error?.code === "ReturnLinkExpired") {
                    setPhase("dead");
                }
                return;
            }
            setVerificationId(data.verificationId);
            setChosen(data.flight);
            setPhase("confirming");
        } catch {
            setError("We couldn't reach our servers. Please check your connection and try again.");
        } finally {
            setBusy(false);
        }
    };

    const handleConfirm = async () => {
        if (!token || !verificationId || busy) return;
        setBusy(true);
        setError(null);
        try {
            const { res, data } = await post("return-trips/confirm", {
                token, verificationId,
            });
            if (!res.ok) {
                setError(data?.error?.message || "We couldn't confirm your return trip.");
                return;
            }
            setPhase("confirmed");
        } catch {
            setError("We couldn't reach our servers. Please check your connection and try again.");
        } finally {
            setBusy(false);
        }
    };

    const pickCandidate = (c: Candidate) => {
        // Narrow by the arrival airport the passenger picked, then re-resolve.
        // The server still decides — this only adds the disambiguating detail.
        setChosen(c);
        setCandidates([]);
        setPhase("entry");
        if (c.flightNumber) setFlightNumber(c.flightNumber);
        setError("Please confirm the date for that flight and check again.");
    };

    return (
        <main className="min-h-screen bg-gray-950 text-white font-sans px-5 py-12">
            <div className="max-w-lg mx-auto">
                <header className="mb-8 border-b border-white/10 pb-6">
                    <h1 className="text-3xl font-bold tracking-tight">Your return trip</h1>
                    <p className="text-gray-400 text-sm mt-1 tracking-wide uppercase">
                        COS Tesla LLC
                    </p>
                </header>

                {phase === "loading" && (
                    <div className="animate-pulse space-y-3" aria-label="Loading">
                        <div className="h-2 w-40 bg-white/10 rounded-full" />
                        <div className="h-2 w-28 bg-white/10 rounded-full" />
                    </div>
                )}

                {phase === "noToken" && (
                    <div className="rounded-xl border border-white/10 bg-white/5 p-6">
                        <h2 className="font-bold text-lg mb-2">This link looks incomplete</h2>
                        <p className="text-gray-400 text-sm leading-relaxed">
                            Please open the link exactly as it appears in your reminder email.
                            If you copied it by hand, part of it may be missing.
                        </p>
                    </div>
                )}

                {phase === "dead" && (
                    <div className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-6">
                        <h2 className="font-bold text-lg mb-2">This link is no longer active</h2>
                        <p className="text-gray-400 text-sm leading-relaxed">
                            {error || "It may have expired, or your return trip may already be booked."}
                            {" "}Reply to your reminder email and we&apos;ll sort it out.
                        </p>
                    </div>
                )}

                {(phase === "entry" || phase === "confirming") && (
                    <>
                        <p className="text-gray-300 text-sm leading-relaxed mb-6">
                            Tell us the flight you&apos;re arriving on and we&apos;ll be there when
                            you land. We track it ourselves — if it&apos;s delayed, we adjust.
                        </p>

                        <form onSubmit={handleResolve} className="space-y-5">
                            <div>
                                <label className={label} htmlFor="flightNumber">Flight number</label>
                                <input
                                    id="flightNumber"
                                    className={`${input} mt-2`}
                                    placeholder="e.g. UA1234"
                                    value={flightNumber}
                                    autoComplete="off"
                                    autoCapitalize="characters"
                                    onChange={(e) => setFlightNumber(e.target.value)}
                                    disabled={busy || phase === "confirming"}
                                />
                            </div>
                            <div>
                                <label className={label} htmlFor="serviceDate">Arrival date</label>
                                <input
                                    id="serviceDate"
                                    type="date"
                                    className={`${input} mt-2`}
                                    value={serviceDate}
                                    onChange={(e) => setServiceDate(e.target.value)}
                                    disabled={busy || phase === "confirming"}
                                />
                            </div>

                            {phase === "entry" && (
                                <button
                                    type="submit"
                                    disabled={busy || !flightNumber.trim() || !serviceDate}
                                    className="w-full rounded-lg bg-blue-500 hover:bg-blue-400 disabled:bg-white/10
                                               disabled:text-gray-500 disabled:cursor-not-allowed
                                               font-bold py-3 transition-colors"
                                >
                                    {busy ? "Checking your flight…" : "Find my flight"}
                                </button>
                            )}
                        </form>

                        {phase === "confirming" && chosen && (
                            <div className="mt-8">
                                <div className="rounded-xl border border-white/10 bg-white/5 p-5">
                                    <p className={label}>We found</p>
                                    <p className="text-xl font-bold mt-2">{chosen.flightNumber}</p>
                                    <p className="text-gray-300 text-sm mt-1">
                                        {chosen.departureAirport} → {chosen.arrivalAirport}
                                    </p>
                                    <p className="text-gray-400 text-sm mt-2">
                                        Arriving {arrivalText(chosen.bestArrivalUtc || chosen.scheduledArrivalUtc)}
                                    </p>
                                    {chosen.isCodeshare && (
                                        <p className="text-gray-500 text-xs mt-3">
                                            This flight is operated by a partner airline.
                                        </p>
                                    )}
                                </div>
                                <button
                                    onClick={handleConfirm}
                                    disabled={busy}
                                    className="w-full mt-4 rounded-lg bg-emerald-500 hover:bg-emerald-400
                                               disabled:bg-white/10 disabled:text-gray-500
                                               disabled:cursor-not-allowed font-bold py-3 transition-colors"
                                >
                                    {busy ? "Booking your return…" : "Yes, book my return trip"}
                                </button>
                                <button
                                    onClick={() => { setPhase("entry"); setChosen(null); setVerificationId(null); }}
                                    disabled={busy}
                                    className="w-full mt-2 text-gray-400 hover:text-white text-sm py-2 transition-colors"
                                >
                                    That&apos;s not my flight
                                </button>
                            </div>
                        )}
                    </>
                )}

                {phase === "ambiguous" && (
                    <div>
                        <h2 className="font-bold text-lg mb-2">Which one is yours?</h2>
                        <p className="text-gray-400 text-sm leading-relaxed mb-5">
                            That flight number runs more than one route that day. We don&apos;t
                            guess — picking the wrong leg means meeting the wrong plane.
                        </p>
                        <div className="space-y-3">
                            {candidates.map((c, i) => (
                                <button
                                    key={`${c.flightNumber}-${c.arrivalAirport}-${i}`}
                                    onClick={() => pickCandidate(c)}
                                    className="w-full text-left rounded-xl border border-white/10 bg-white/5
                                               hover:border-blue-400/50 hover:bg-white/10 p-4 transition-colors"
                                >
                                    <p className="font-bold">
                                        {c.departureAirport} → {c.arrivalAirport}
                                    </p>
                                    <p className="text-gray-400 text-sm mt-1">
                                        Arriving {arrivalText(c.bestArrivalUtc || c.scheduledArrivalUtc)}
                                    </p>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {phase === "confirmed" && (
                    <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/5 p-6">
                        <h2 className="font-bold text-lg mb-2">You&apos;re all set</h2>
                        <p className="text-gray-300 text-sm leading-relaxed">
                            We&apos;ll meet you when you land
                            {chosen?.flightNumber ? ` off ${chosen.flightNumber}` : ""}. We&apos;re
                            tracking the flight, so you don&apos;t need to tell us if it&apos;s
                            delayed — we&apos;ll already know.
                        </p>
                        <p className="text-gray-500 text-xs mt-4">
                            A confirmation is on its way to the email address we have for you.
                        </p>
                    </div>
                )}

                {error && phase !== "dead" && (
                    <p role="alert" className="mt-5 text-sm text-amber-300/90 leading-relaxed">
                        {error}
                    </p>
                )}
            </div>
        </main>
    );
}
