import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'
import telemetry, { EVENTS } from './lib/telemetry'

// ─── Global error handlers ────────────────────────────────────────────────────
// Catches errors that escape React's boundary (e.g. event handlers, async code)
window.onerror = (message, source, lineno, colno, error) => {
  telemetry.error(EVENTS.JS_ERROR, String(message), {
    source,
    lineno,
    colno,
    stack: error?.stack?.slice(0, 500),
  })
}

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  telemetry.error(EVENTS.UNHANDLED_REJECTION, String(reason?.message ?? reason), {
    stack: reason?.stack?.slice(0, 500),
  })
})

// ─── App init telemetry ───────────────────────────────────────────────────────
telemetry.track(EVENTS.APP_INIT, { version: import.meta.env.VITE_APP_VERSION ?? 'unknown' })

// ─── Mount ────────────────────────────────────────────────────────────────────
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
