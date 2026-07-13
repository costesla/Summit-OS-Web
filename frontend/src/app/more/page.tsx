import Link from "next/link";
import type { Metadata } from "next";
import { ChevronRight } from "lucide-react";

export const metadata: Metadata = {
    title: "More | COS Tesla",
    description: "Services, policies, and contact for COS Tesla.",
};

/*
 * "More" tab destination for the installed-app shell (B1).
 * B4 expands this page with Trips & Receipts, About, and Feedback sections.
 */
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
