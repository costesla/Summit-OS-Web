import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const isProd = mode === 'production'

  return {
    plugins: [react()],

    // ─── Build output ──────────────────────────────────────────────────────────
    build: {
      outDir: 'dist',
      emptyOutDir: true,

      // Sourcemaps: on for staging/preview, off for production
      // Override with VITE_SOURCEMAP=true in your CI environment if needed
      sourcemap: env.VITE_SOURCEMAP === 'true' ? true : !isProd,

      rollupOptions: {
        output: {
          // Vendor splitting: keeps recharts + lucide-react out of the main chunk
          manualChunks: {
            'vendor-react': ['react', 'react-dom'],
            'vendor-recharts': ['recharts'],
            'vendor-lucide': ['lucide-react'],
          },
        },
      },

      // Warn at 500 kB, error at 750 kB
      chunkSizeWarningLimit: 500,
    },

    // ─── Base path ────────────────────────────────────────────────────────────
    // VITE_BASE_PATH lets CI override for sub-directory deploys (e.g. /dashboard/)
    base: env.VITE_BASE_PATH ?? '/',
  }
})
