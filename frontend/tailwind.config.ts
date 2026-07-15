import type { Config } from "tailwindcss";

const config: Config = {
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                background: "var(--background)",
                foreground: "var(--foreground)",
                /* SummitOS night-sky palette (see globals.css :root --sos-*).
                   Purely additive — legacy light pages never reference these,
                   so nothing restyles until a page opts in.
                   Usage: bg-sos-dark, text-sos-main, text-sos-accent, … */
                sos: {
                    dark: "var(--sos-bg)",
                    surface: "var(--sos-surface)",
                    surface2: "var(--sos-surface-2)",
                    border: "var(--sos-border)",
                    main: "var(--sos-text)",
                    dim: "var(--sos-text-dim)",
                    accent: "var(--sos-accent)",
                },
            },
            boxShadow: {
                "sos-glow": "0 0 24px var(--sos-accent-glow)",
            },
        },
    },
    plugins: [],
};
export default config;
