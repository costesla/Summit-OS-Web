# SummitOS Driver Dashboard

**Live:** [www.dashboardcostesla.com](https://www.dashboardcostesla.com)  
**Stack:** React 19 · TypeScript · Vite 7 · Tailwind CSS · Recharts

---

## Definition of Done (DoD)

These criteria must ALL be true before any push to `master` is accepted.

### A — Repo Hygiene

| Criterion | Verification |
|---|---|
| `npm run build` leaves git status clean | `git status` after build shows no new files |
| `dist/` is untracked | `git ls-files dist/` → empty |
| No `index-*.js` / `index-*.css` outside `dist/` | `npm run check:clean` → exit 0 |
| No `*.tsbuildinfo` committed | `git ls-files "*.tsbuildinfo"` → empty |
| No `.env` / `.env.local` committed | `git ls-files ".env*"` → empty |

```bash
# Run this after every build to prove hygiene:
git ls-files dist/              # must return nothing
git ls-files "*.tsbuildinfo"    # must return nothing
npm run check:clean             # must exit 0
```

### B — Guardrails

| Script | Purpose | Behaviour on violation |
|---|---|---|
| `npm run check` | Full local gate (type-check → lint → clean → secrets) | exit 1 |
| `npm run check:clean` | Fail if bundles / tsbuildinfo exist outside `dist/` | exit 1 |
| `npm run check:secrets` | Fail if secret-like patterns found in source | exit 1 |
| `npm run ci` | Replicates CI: type-check → lint → build | exit 1 |

### C — Observability

| Requirement | Location |
|---|---|
| `ErrorBoundary` at app root | `src/main.tsx` wraps `<App />` |
| `window.onerror` → telemetry | `src/main.tsx` |
| `window.onunhandledrejection` → telemetry | `src/main.tsx` |
| Key workflow actions emit events | `src/lib/telemetry.ts` (EVENTS vocabulary) |
| SummitOS Intelligence contract | See **Telemetry Events** section below |

---


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
| `VITE_PUBLIC_API_BASE_URL` | Backend base URL _(spec-required name)_ | Azure prod URL |
| `VITE_API_BASE_URL` | Backend base URL _(legacy fallback)_ | Azure prod URL |
| `VITE_TELEMETRY_ENABLED` | Enable console telemetry | `true` |
| `VITE_TELEMETRY_SINK_URL` | Optional remote sink URL | _(blank = console only)_ |
| `VITE_APP_VERSION` | Injected by CI | `1.4.5` |
| `VITE_SOURCEMAP` | Enable sourcemaps | `false` (prod) |

**Never put secrets in `VITE_*` variables** — they are inlined into the JS bundle.  
Use Azure Static Web App managed identity or backend-side secrets only.

---

## Telemetry Events

The dashboard emits structured operational events (console + optional sink). These are the **SummitOS Intelligence contract** — the agent reads these to understand driver workflow state.

```
[SummitOS:INFO]  app_init            { version, session }
[SummitOS:INFO]  workflow_ready      { date }
[SummitOS:INFO]  sync_started        { date }
[SummitOS:INFO]  sync_completed      { date, duration_ms }
[SummitOS:ERROR] api_request_failed  { endpoint, status, duration_ms }
```

### Full EVENTS Vocabulary (`src/lib/telemetry.ts`)

| Event name | Trigger | Category |
|---|---|---|
| `app_init` | App mounts | Lifecycle |
| `page_view` | Route renders | Lifecycle |
| `workflow_ready` | Dashboard ready for daily ops | **Agent signal** |
| `sync_started` | Rebuild Day initiated | Sync |
| `sync_completed` | Rebuild Day finished successfully | **Agent signal** |
| `sync_failed` | Rebuild Day error | Sync |
| `sync_requested` | Any sync button clicked | Sync |
| `rebuild_day_clicked` | Rebuild Day button pressed | **Agent signal** |
| `tessie_tags_confirmed` | Tessie drive tags verified | **Agent signal** |
| `tessie_drives_loaded` | Tessie panel data loaded | Tessie |
| `tessie_drive_imported` | Individual drive imported | Tessie |
| `uber_cards_uploaded` | Screenshot batch uploaded | **Agent signal** |
| `screenshot_match_started` | OCR match process begins | OCR |
| `screenshot_match_completed` | OCR match process ends | OCR |
| `screenshot_no_match` | Screenshot had no match | OCR |
| `manual_expense_added` | Expense logged manually | **Agent signal** |
| `expense_deleted` | Expense removed | Expenses |
| `api_request_failed` | Any API call fails | **Agent signal** |
| `api_call_started` | API request begins | API |
| `api_call_completed` | API request succeeds | API |
| `api_failure` | API error (alias) | API |
| `js_error` | Uncaught JS exception | Errors |
| `unhandled_rejection` | Unhandled promise rejection | Errors |

> Events marked **Agent signal** are the primary observability hooks for SummitOS Intelligence.


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
