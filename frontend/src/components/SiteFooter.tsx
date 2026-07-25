"use client";

import { usePathname } from "next/navigation";
import Footer from "./Footer";

/* The home map is full-viewport (h-100dvh); a footer below it would add a
   stray scroll region and break the app feel. /flights is a focused single-
   purpose tool and reads better ending at the result card. Every other route
   keeps the footer — including the Privacy/Terms links and the CO PUC permit
   display — exactly as before. */
const NO_FOOTER_ROUTES = ["/", "/flights"];

export default function SiteFooter() {
    const pathname = usePathname();
    if (NO_FOOTER_ROUTES.includes(pathname?.replace(/\/$/, "") || "/")) return null;
    return <Footer />;
}
