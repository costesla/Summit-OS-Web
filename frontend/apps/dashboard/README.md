# SummitOS Driver Dashboard

**Live:** [www.dashboardcostesla.com](https://www.dashboardcostesla.com)  
**Stack:** React 19 · TypeScript · Vite 7 · Tailwind CSS · Recharts

---

## Dev → Build → Deploy

### Local Development

```bash
cd frontend/apps/dashboard
npm install
npm run dev          # Vite HMR at http://localhost:5173
```

Copy `.env.template` to `.env.local` and set your values. Never commit `.env.local`.

### Type Checking

```bash
npm run type-check   # tsc --noEmit (no output, just errors)
```

### Lint

```bash
npm run lint         # eslint . (hooks + refresh rules enforced)
```

### CI Gate (runs all three)

```bash
npm run ci           # type-check → lint → build
```

### Production Build

```bash
npm run build        # tsc -b && vite build → dist/
```

> ⚠️ **`dist/` is generated — never commit it.**
> Azure Static Web Apps picks up the build from CI via `app_artifact_location: dist`.
> A failed local build is a red flag; push only after `npm run build` succeeds locally.

### Preview Built Bundle

```bash
npm run preview      # serves dist/ locally at http://localhost:4173
```

---

## Project Structure

```
src/
  components/
    DriverDashboard.tsx   — main dashboard UI (1700+ lines, single component)
    ErrorBoundary.tsx     — React error boundary with telemetry
  lib/
    api/
      client.ts           — centralized fetch wrapper (base URL, retries, telemetry)
      endpoints.ts        — typed wrappers for every backend route
    telemetry/
      index.ts            — structured event logger (EVENTS vocabulary)
  main.tsx                — app entry: mounts ErrorBoundary + global error handlers
  App.tsx                 — root component
```

---

## Environment Variables

See `.env.template` for all supported `VITE_*` variables.

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Backend base URL | Azure prod URL |
| `VITE_TELEMETRY_ENABLED` | Enable console telemetry | `true` |
| `VITE_TELEMETRY_SINK_URL` | Optional remote sink URL | _(blank = console only)_ |
| `VITE_APP_VERSION` | Injected by CI | `1.4.5` |
| `VITE_SOURCEMAP` | Enable sourcemaps | `false` (prod) |

**Never put secrets in `VITE_*` variables** — they are inlined into the JS bundle.  
Use Azure Static Web App managed identity or backend-side secrets only.

---

## Telemetry

The dashboard emits structured operational events to the console (and optionally a sink):

```
[SummitOS:INFO] sync_started { date: "2026-05-18", ... }
[SummitOS:INFO] tessie_drives_loaded { count: 4, ... }
[SummitOS:ERROR] api_failure { endpoint: "/daily-sync", status: 504 }
```

The event vocabulary (`src/lib/telemetry/index.ts → EVENTS`) is the contract with SummitOS Intelligence.

---

## Security

- No secrets in frontend code or `VITE_*` env vars
- Secret scan CI check: `node scripts/scan-secrets.mjs --all`
- Dependency audit: `npm run audit:report`
- `.env` files are gitignored; use `.env.template` to document required vars

---

## Troubleshooting

**Build fails on Azure but works locally?**  
Run `npm run ci` locally — it replicates the CI gate exactly.

**White screen in production?**  
The `ErrorBoundary` now catches render errors and shows a recovery UI.  
Check the browser console for `[SummitOS:ERROR]` events.

**API calls timing out?**  
All calls go through `src/lib/api/client.ts` — adjust `DEFAULT_TIMEOUT_MS` or pass `timeoutMs` per endpoint.
