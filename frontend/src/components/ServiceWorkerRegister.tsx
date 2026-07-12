"use client";

import { useEffect } from "react";

export default function ServiceWorkerRegister() {
    useEffect(() => {
        if (process.env.NODE_ENV !== "production") return;
        if (!("serviceWorker" in navigator)) return;
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
            // Registration failure degrades to a plain website — never surface to the user
        });
    }, []);

    return null;
}
