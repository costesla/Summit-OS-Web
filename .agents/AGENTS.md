# SummitOS Project Rules

## PII Compliance — Passenger Data

SummitOS is a **commercial transportation platform**. Any screen visible to a driver, dispatcher, or customer must never expose passenger PII beyond what is operationally necessary. Violations risk regulatory fines — treat these as **hard requirements**.

---

### Names — always use `firstName()`
- Only the first word of a name may be displayed on-screen.
- `"Jacquelyn Heslep"` → `"Jacquelyn"`, `"Emerson Jean Baptiste"` → `"Emerson"`
- Applies to: trip labels, unpaid invoice rows, payment badges, and any other UI element.

### Addresses — always use `scrubAddress()`
- Strip the leading street/building number only. City and state are fine.
- `"8989 North Gate Blvd, Colorado Springs, CO"` → `"North Gate Blvd, Colorado Springs, CO"`
- Applies to: Tessie drive start/end, private trip pickup/dropoff, unpaid invoice address lines, and any new address field added in future.

### Standard helpers — copy into any component that renders passenger data

```typescript
/** Strip surname — only ever show the first word of a name on-screen. */
const firstName = (name: string | null | undefined): string | null => {
    if (!name) return null;
    return name.trim().split(/\s+/)[0];
};

/** Strip leading street number for PII compliance — city and state are kept. */
const scrubAddress = (addr: string | null | undefined): string | null => {
    if (!addr) return null;
    return addr.replace(/^\d+\s+/, '');
};
```

### Never expose in any UI element
- Full legal names (first + last + middle)
- Street or building numbers
- Raw GPS coordinates as visible text

---

## Terminal — PowerShell Chaining

The project runs on Windows PowerShell. Use `pwsh` (PowerShell 7+) for any chained git or deploy commands so that `&&` fail-fast chaining works natively:

```powershell
# Correct — fails fast if commit fails, push never fires
git add . && git commit -m "msg" && git pull --rebase && git push
```

Legacy `powershell.exe` (5.1) does not support `&&`. Use `;` only when you explicitly want unconditional chaining. Never use `;` for deploy pipelines.

---

## Cabin Console — Error Copy Voice

The cabin console is **passenger-facing**. Error states must be written for passengers, not engineers:

- ✅ "Map temporarily unavailable" — passenger voice, technical detail in `console.error`
- ❌ "Check deploy config — see console for details" — developer voice on a customer screen

Rule: anything visible in the cabin UI must make sense to someone who has never opened DevTools. Technical detail belongs exclusively in the console log.

---

## Analytics & Operational Inference Guardrails

SummitOS data is used to drive physical vehicle positioning ("staging") and financial decisions. Agents must adhere to strict statistical honesty:

1. **No False Predictive "Verdicts":**
   - Never present raw, unshrinked sample means as authoritative "AI Staging Instructions" (e.g., "Top Priority Staging: $85/hr").
   - If an area has low trip volume ($N < 30$), the average is noise. Always report sample sizes ($N$) alongside metrics.
   - When computing zone-level averages, implement **Empirical Bayes shrinkage** pulling low-sample buckets toward the citywide prior before making operational comparisons.

2. **Strict Cohort Separation:**
   - **Never mix scheduled private bookings with on-demand rideshare trips** when calculating staging or positioning advice.
   - Advance private bookings represent pre-arranged dispatches, not street-hail or on-demand demand density.

3. **Explicit Parameter Labeling:**
   - Energy ($/kWh) and vehicle wear ($/mi) rates must be clearly labeled as user-configurable assumptions or estimates, not measured constants, until backed by empirical billing reconciliations.

