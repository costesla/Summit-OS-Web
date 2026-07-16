import Link from "next/link";
import type { Metadata } from "next";
import { ChevronRight, Receipt, Mail } from "lucide-react";
import FeedbackForm from "@/components/FeedbackForm";
import DriverNotifications from "@/components/DriverNotifications";

export const metadata: Metadata = {
    title: "More | COS Tesla",
    description: "Trips, receipts, feedback, policies, and contact for COS Tesla.",
};

const LINKS = [
    { href: "/services/", label: "Services" },
    { href: "/contact/", label: "Contact" },
    { href: "/privacy/", label: "Privacy Policy" },
    { href: "/terms/", label: "Terms of Service" },
] as const;

export default function MorePage() {
    return (
        <main className="min-h-screen container mx-auto px-6 pt-28 pb-16 max-w-lg">
            <h1 className="text-3xl font-bold mb-8">More</h1>

            {/* Owner-only (renders nothing for customers) */}
            <DriverNotifications />

            {/* ── Trips & Receipts ─────────────────────────────────────
                 Placeholder by design: no receipts API or customer identity
                 exists yet (finding C2). The real endpoint is designed in
                 docs/identity-spec.md alongside customer accounts. */}
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Trips &amp; Receipts</h2>
            <div className="rounded-2xl bg-white border border-slate-200/60 shadow-sm px-5 py-5 mb-8">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                        <Receipt size={20} className="text-[#2563eb]" aria-hidden="true" />
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-slate-800 mb-1">Receipts arrive by email</p>
                        <p className="text-sm text-slate-500 leading-relaxed">
                            A receipt is emailed after every completed trip. In-app trip history
                            arrives with customer accounts — coming soon.
                        </p>
                        <a
                            href="mailto:peter.teehan@costesla.com?subject=Receipt%20copy%20request"
                            className="inline-flex items-center gap-1.5 text-sm font-medium text-[#2563eb] mt-3 hover:underline"
                        >
                            <Mail size={14} aria-hidden="true" />
                            Request a receipt copy
                        </a>
                    </div>
                </div>
            </div>

            {/* ── Feedback ───────────────────────────────────────────── */}
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Feedback</h2>
            <div className="mb-8">
                <FeedbackForm />
            </div>

            {/* ── About ──────────────────────────────────────────────── */}
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">About</h2>
            <div className="rounded-2xl bg-white border border-slate-200/60 shadow-sm px-5 py-5 mb-8">
                <p className="text-sm text-slate-600 leading-relaxed">
                    COS Tesla LLC is the executive standard for private transportation in
                    Colorado Springs and the Pikes Peak region — one vehicle, one driver,
                    every detail handled. Licensed and insured, Colorado PUC 0250.
                </p>
                <p className="text-xs text-slate-400 mt-3">
                    COS Tesla is an independent transportation service and is not affiliated
                    with Tesla, Inc.
                </p>
            </div>

            {/* ── Links ──────────────────────────────────────────────── */}
            <div className="flex flex-col divide-y divide-slate-200/80 rounded-2xl bg-white border border-slate-200/60 shadow-sm overflow-hidden">
                {LINKS.map(({ href, label }) => (
                    <Link
                        key={href}
                        href={href}
                        className="flex items-center justify-between px-5 py-4 text-[color:var(--color-text-main)] hover:bg-slate-50 transition-colors"
                    >
                        <span className="font-medium">{label}</span>
                        <ChevronRight size={18} className="text-slate-400" aria-hidden="true" />
                    </Link>
                ))}
            </div>

            <p className="text-xs text-slate-400 mt-8 text-center font-mono">
                COS Tesla LLC · CO PUC 0250
            </p>
        </main>
    );
}
