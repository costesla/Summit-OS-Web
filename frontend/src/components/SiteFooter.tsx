"use client";

import { usePathname } from "next/navigation";
import Footer from "./Footer";

/* The home map is full-viewport (h-100dvh); a footer below it would add a
   stray scroll region and break the app feel. Every other route keeps the
   footer exactly as before. */
export default function SiteFooter() {
    const pathname = usePathname();
    if (pathname === "/") return null;
    return <Footer />;
}
