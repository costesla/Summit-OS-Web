"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarCheck, Navigation, Car, Menu } from "lucide-react";

/*
 * Bottom tab navigation for the installed-app experience.
 *
 * Rendered on every page but visible ONLY under `display-mode: standalone`
 * (see globals.css) — the browser site keeps its current layout untouched.
 * Client-side <Link> navigation keeps tab switches flash-free in the
 * static export.
 */
const TABS = [
    { href: "/book/", label: "Book", icon: CalendarCheck, match: "/book" },
    { href: "/track/", label: "Track", icon: Navigation, match: "/track" },
    { href: "/cabin/", label: "Cabin", icon: Car, match: "/cabin" },
    { href: "/more/", label: "More", icon: Menu, match: "/more" },
] as const;

export default function AppTabBar() {
    const pathname = usePathname() || "/";

    return (
        <nav className="app-tab-bar" aria-label="App navigation">
            {TABS.map(({ href, label, icon: Icon, match }) => {
                const active = pathname.startsWith(match);
                return (
                    <Link
                        key={href}
                        href={href}
                        className={`app-tab${active ? " app-tab-active" : ""}`}
                        aria-current={active ? "page" : undefined}
                    >
                        <Icon size={22} strokeWidth={active ? 2.4 : 1.8} aria-hidden="true" />
                        <span>{label}</span>
                    </Link>
                );
            })}
        </nav>
    );
}
