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
