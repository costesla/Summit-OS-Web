"use client";

import { useEffect, useState } from "react";
import { Bell, BellOff, Send } from "lucide-react";

/*
 * B5a: driver-side push notification controls. Renders NOTHING unless the
 * visitor has an Easy Auth session (owner) — customers never see it.
 * Subscription posts to /api/push/subscribe (B5b); the endpoint re-checks
 * the session server-side via the x-ms-client-principal header.
 */

// VAPID public key — public by design (pairs with VAPID_PRIVATE_KEY app setting)
const VAPID_PUBLIC_KEY =
    "BF88VZMS7Jp-jjAWJUKRbW-VjAxC1zhIojVMx4tvPPFAbaAASi9TzuA1sW3Sd2pg7uRqDxkbgLatgI2h9LToKZs";

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
    const padding = "=".repeat((4 - (base64.length % 4)) % 4);
    const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(b64);
    // new Uint8Array(n) owns a plain ArrayBuffer — satisfies BufferSource
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
}

type PushState = "hidden" | "unsupported" | "blocked" | "off" | "on" | "busy";

export default function DriverNotifications() {
    const [state, setState] = useState<PushState>("hidden");
    const [note, setNote] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const me = await fetch("/.auth/me")
                    .then((r) => (r.ok ? r.json() : null))
                    .catch(() => null);
                if (!me?.clientPrincipal) return; // not the owner: stay hidden
                if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
                    if (!cancelled) setState("unsupported");
                    return;
                }
                if (Notification.permission === "denied") {
                    if (!cancelled) setState("blocked");
                    return;
                }
                const reg = await navigator.serviceWorker.getRegistration();
                const sub = await reg?.pushManager.getSubscription();
                if (!cancelled) setState(sub ? "on" : "off");
            } catch {
                /* stay hidden — never surface errors to non-owners */
            }
        })();
        return () => { cancelled = true; };
    }, []);

    const enable = async () => {
        setState("busy");
        setNote(null);
        try {
            const perm = await Notification.requestPermission();
            if (perm !== "granted") { setState("blocked"); return; }
            const reg = await navigator.serviceWorker.ready;
            const sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
            });
            const res = await fetch("/api/push/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ subscription: sub.toJSON() }),
            });
            if (!res.ok) {
                await sub.unsubscribe().catch(() => {});
                setNote("Couldn't register with the server — try again after the next backend deploy.");
                setState("off");
                return;
            }
            setState("on");
        } catch {
            setNote("Subscription failed — check notification permissions.");
            setState("off");
        }
    };

    const disable = async () => {
        setState("busy");
        setNote(null);
        try {
            const reg = await navigator.serviceWorker.getRegistration();
            const sub = await reg?.pushManager.getSubscription();
            if (sub) {
                await fetch("/api/push/unsubscribe", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ endpoint: sub.endpoint }),
                }).catch(() => {});
                await sub.unsubscribe();
            }
            setState("off");
        } catch {
            setState("on");
        }
    };

    const sendTest = async () => {
        setNote(null);
        const res = await fetch("/api/push/test", { method: "POST" }).catch(() => null);
        setNote(res?.ok ? "Test sent — it should appear in a moment." : "Test failed — is VAPID_PRIVATE_KEY configured?");
    };

    if (state === "hidden") return null;

    return (
        <>
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Driver</h2>
            <div className="rounded-2xl bg-white border border-slate-200/60 shadow-sm px-5 py-5 mb-8">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                        {state === "on"
                            ? <Bell size={20} className="text-[#2563eb]" aria-hidden="true" />
                            : <BellOff size={20} className="text-slate-400" aria-hidden="true" />}
                    </div>
                    <div className="flex-1">
                        <p className="text-sm font-semibold text-slate-800 mb-1">New-booking alerts</p>
                        {state === "unsupported" && (
                            <p className="text-sm text-slate-500">This browser doesn&rsquo;t support push notifications.</p>
                        )}
                        {state === "blocked" && (
                            <p className="text-sm text-slate-500">Notifications are blocked for this site — allow them in browser settings, then retry.</p>
                        )}
                        {(state === "off" || state === "on" || state === "busy") && (
                            <p className="text-sm text-slate-500 mb-3">
                                {state === "on"
                                    ? "This device gets a notification whenever a booking lands."
                                    : "Get a notification on this device whenever a booking lands."}
                            </p>
                        )}
                        <div className="flex gap-2">
                            {state === "off" && (
                                <button onClick={enable} className="rounded-xl bg-[#2563eb] hover:bg-blue-700 text-white text-sm font-bold px-4 py-2 transition-colors">
                                    Enable on this device
                                </button>
                            )}
                            {state === "on" && (
                                <>
                                    <button onClick={sendTest} className="flex items-center gap-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold px-4 py-2 transition-colors">
                                        <Send size={14} aria-hidden="true" /> Send test
                                    </button>
                                    <button onClick={disable} className="rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold px-4 py-2 transition-colors">
                                        Disable
                                    </button>
                                </>
                            )}
                            {state === "busy" && <span className="text-sm text-slate-400 py-2">Working…</span>}
                        </div>
                        {note && <p className="text-xs text-slate-500 mt-2">{note}</p>}
                    </div>
                </div>
            </div>
        </>
    );
}
