"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    Menu,
    X,
    Navigation,
    CalendarCheck,
    Car,
    Scale,
    CloudSun,
    Plane,
    FileText,
    LifeBuoy,
    Sparkles,
} from "lucide-react";

/*
 * SummitOS app shell — the primary navigation for the dark redesign.
 *
 * Desktop (lg+): persistent left sidebar.
 * Mobile / TWA:  hamburger button -> slide-out drawer with backdrop.
 *
 * Visual reference is the /cabin console (night-sky palette, cyan glow).
 * Touch-feel classes (.sos-nav) come from globals.css: touch-action
 * manipulation + no tap flash + no text selection, so it reads native.
 */

const PRIMARY = [
    { href: "/", label: "Home", icon: Navigation },
    { href: "/book/", label: "Booking", icon: CalendarCheck },
    { href: "/cabin/", label: "Cabin Control", icon: Car },
    { href: "/fairness/", label: "Fairness Engine", icon: Scale },
    { href: "/weather/", label: "Weather", icon: CloudSun },
    { href: "/flights/", label: "Flight Tracker", icon: Plane },
] as const;

const SECONDARY = [
    { href: "/experience/", label: "The Experience", icon: Sparkles },
    { href: "/privacy/", label: "Legal", icon: FileText },
    { href: "/contact/", label: "Support", icon: LifeBuoy },
] as const;

function isActive(pathname: string, href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href.replace(/\/$/, ""));
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
    const pathname = usePathname() || "/";

    const row = (href: string, label: string, Icon: React.ComponentType<{ size?: number; strokeWidth?: number }>) => {
        const active = isActive(pathname, href);
        return (
            <Link
                key={href}
                href={href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors ${
                    active
                        ? "bg-cyan-500/10 text-cyan-300 shadow-[inset_0_0_0_1px_rgba(34,211,238,0.25)]"
                        : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
                }`}
            >
                <Icon size={18} strokeWidth={active ? 2.4 : 1.8} />
                <span>{label}</span>
            </Link>
        );
    };

    return (
        <nav className="sos-nav flex h-full flex-col gap-1 p-4" aria-label="Main navigation">
            <Link href="/" onClick={onNavigate} className="mb-6 flex items-center gap-3 px-2 pt-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/logo.png" alt="" className="h-9 w-9 rounded-xl" />
                <span className="flex flex-col leading-tight">
                    <span className="text-sm font-bold italic tracking-tighter text-white">COS TESLA</span>
                    <span className="font-mono text-[0.55rem] uppercase tracking-[0.2em] text-slate-500">
                        Powered by SummitOS
                    </span>
                </span>
            </Link>

            {PRIMARY.map((i) => row(i.href, i.label, i.icon))}

            <div className="my-3 h-px bg-white/5" />

            {SECONDARY.map((i) => row(i.href, i.label, i.icon))}

            <p className="mt-auto px-4 pb-1 font-mono text-[0.6rem] uppercase tracking-widest text-slate-600">
                CO PUC 0250
            </p>
        </nav>
    );
}

export default function AppShell() {
    const [open, setOpen] = useState(false);
    const pathname = usePathname();

    // Close the drawer on navigation and on Escape
    useEffect(() => setOpen(false), [pathname]);
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);

    // Lock body scroll while the drawer is open
    useEffect(() => {
        document.body.style.overflow = open ? "hidden" : "";
        return () => { document.body.style.overflow = ""; };
    }, [open]);

    return (
        <>
            {/* Desktop: persistent sidebar */}
            <aside className="fixed inset-y-0 left-0 z-40 hidden w-[var(--sos-nav-w)] border-r border-white/5 bg-[#0a0a0a]/95 backdrop-blur-xl lg:block">
                <NavList />
            </aside>

            {/* Mobile: floating hamburger */}
            <button
                type="button"
                onClick={() => setOpen(true)}
                aria-label="Open navigation"
                aria-expanded={open}
                className="sos-touch fixed left-4 top-4 z-40 flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-black/70 text-white shadow-lg backdrop-blur-md lg:hidden"
            >
                <Menu size={20} />
            </button>

            {/* Mobile: backdrop */}
            <div
                onClick={() => setOpen(false)}
                aria-hidden="true"
                className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-300 lg:hidden ${
                    open ? "opacity-100" : "pointer-events-none opacity-0"
                }`}
            />

            {/* Mobile: slide-out drawer */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-[var(--sos-nav-w)] max-w-[82vw] border-r border-white/5 bg-[#0a0a0a] shadow-2xl transition-transform duration-300 ease-out lg:hidden ${
                    open ? "translate-x-0" : "-translate-x-full"
                }`}
                style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
            >
                <button
                    type="button"
                    onClick={() => setOpen(false)}
                    aria-label="Close navigation"
                    className="sos-touch absolute right-3 top-4 flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 hover:bg-white/5 hover:text-white"
                >
                    <X size={18} />
                </button>
                <NavList onNavigate={() => setOpen(false)} />
            </aside>
        </>
    );
}
