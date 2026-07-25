import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

/* Test runner for the frontend. Dev-only: never part of the Next build or the
   shipped bundle. `npm test` runs once; `npm run test:watch` re-runs on save. */
export default defineConfig({
    plugins: [react()],
    resolve: {
        // Mirror the "@/..." alias used across src/ so tests import like the app does.
        alias: { "@": path.resolve(__dirname, "./src") },
    },
    test: {
        environment: "jsdom",
        globals: true,
        include: ["src/**/*.test.{ts,tsx}"],
    },
});
