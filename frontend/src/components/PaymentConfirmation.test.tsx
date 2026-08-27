import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import PaymentConfirmation from "./PaymentConfirmation";

/* The passenger's only on-site proof they paid. The cases that matter are the
   ones where Stripe hasn't caught up yet: a paid session whose invoice is still
   finalizing must never render a dead "Download PDF". */

const PAID_BOOKING = {
    status: "paid",
    amountTotal: "$285.00",
    currency: "usd",
    firstName: "Peter",
    invoiceNumber: "INV-PETER-20260801-0930",
    stripeInvoiceNumber: "B12F4A9C-0007",
    hostedInvoiceUrl: "https://invoice.stripe.com/i/example",
    invoicePdf: "https://invoice.stripe.com/i/example/pdf",
    receiptUrl: "https://pay.stripe.com/receipts/example",
    source: "booking",
    pickup: "1200 Cascade Ave, Colorado Springs, CO",
    dropoff: "Denver International Airport (DEN)",
    appointmentStart: "2026-08-01T15:30:00Z",
    fareString: "$285.00",
};

/** Queues one response per call, repeating the last one thereafter. */
function mockFetchSequence(responses: Array<{ status?: number; body: unknown }>) {
    let call = 0;
    const spy = vi.fn(async () => {
        const next = responses[Math.min(call, responses.length - 1)];
        call += 1;
        return {
            status: next.status ?? 200,
            json: async () => next.body,
        } as Response;
    });
    vi.stubGlobal("fetch", spy);
    return spy;
}

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe("PaymentConfirmation", () => {
    it("shows the amount, our invoice number, and all three links when paid", async () => {
        mockFetchSequence([{ body: PAID_BOOKING }]);
        render(<PaymentConfirmation sessionId="cs_test_paid" />);

        expect(await screen.findByText(/Payment received/)).toBeTruthy();
        // Appears twice by design: the headline total and the trip card's fare.
        expect(screen.getAllByText("$285.00").length).toBeGreaterThan(0);
        expect(screen.getByText(/INV-PETER-20260801-0930/)).toBeTruthy();

        const href = (label: RegExp) =>
            screen.getByText(label).closest("a")?.getAttribute("href");
        expect(href(/View invoice/)).toBe(PAID_BOOKING.hostedInvoiceUrl);
        expect(href(/Download PDF/)).toBe(PAID_BOOKING.invoicePdf);
        expect(href(/View receipt/)).toBe(PAID_BOOKING.receiptUrl);
    });

    it("greets by first name only and never exposes a surname", async () => {
        mockFetchSequence([{ body: PAID_BOOKING }]);
        render(<PaymentConfirmation sessionId="cs_test_paid" />);

        expect(await screen.findByText(/thank you, Peter/)).toBeTruthy();
        expect(document.body.textContent).not.toContain("Teehan");
    });

    it("shows the trip card and cabin note for a booking", async () => {
        mockFetchSequence([{ body: PAID_BOOKING }]);
        render(<PaymentConfirmation sessionId="cs_test_paid" />);

        await screen.findByText(/Payment received/);
        expect(screen.getByText("Your trip")).toBeTruthy();
        expect(screen.getByText(/Denver International Airport/)).toBeTruthy();
        expect(screen.getByText(/Cabin access opens/)).toBeTruthy();
    });

    it("omits trip context and cabin note for a post-trip invoice", async () => {
        mockFetchSequence([
            { body: { ...PAID_BOOKING, source: "post_trip_invoice", pickup: undefined, dropoff: undefined } },
        ]);
        render(<PaymentConfirmation sessionId="cs_test_posttrip" />);

        await screen.findByText(/Payment received/);
        expect(screen.queryByText("Your trip")).toBeNull();
        expect(screen.queryByText(/Cabin access opens/)).toBeNull();
    });

    it("renders the receipt without a PDF button while the invoice is still finalizing", async () => {
        mockFetchSequence([
            { body: { ...PAID_BOOKING, hostedInvoiceUrl: null, invoicePdf: null } },
        ]);
        render(<PaymentConfirmation sessionId="cs_test_lag" />);

        await screen.findByText(/Payment received/);
        // This is the whole point: a null PDF must not become a broken button.
        expect(screen.queryByText(/Download PDF/)).toBeNull();
        expect(screen.queryByText(/View invoice/)).toBeNull();
        expect(screen.getByText(/View receipt/)).toBeTruthy();
        expect(screen.getByText(/invoice is being prepared/i)).toBeTruthy();
    });

    it("fills in the invoice links on a later poll without losing the paid state", async () => {
        vi.useFakeTimers();
        mockFetchSequence([
            { body: { ...PAID_BOOKING, hostedInvoiceUrl: null, invoicePdf: null } },
            { body: PAID_BOOKING },
        ]);
        render(<PaymentConfirmation sessionId="cs_test_lag" />);

        // Settle the first fetch. RTL's waitFor doesn't drive vi's fake timers,
        // so the clock is advanced explicitly instead.
        await act(async () => {
            await vi.advanceTimersByTimeAsync(0);
        });
        expect(screen.getByText(/Payment received/)).toBeTruthy();
        expect(screen.queryByText(/Download PDF/)).toBeNull();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(3000);
        });

        expect(screen.getByText(/Download PDF/)).toBeTruthy();
        // The paid confirmation must survive the poll, not flicker back to loading.
        expect(screen.getByText(/Payment received/)).toBeTruthy();
    });

    it("falls back to the pending message after retrying an unpaid session", async () => {
        vi.useFakeTimers();
        const spy = mockFetchSequence([{ body: { status: "pending" } }]);
        render(<PaymentConfirmation sessionId="cs_test_pending" />);

        await act(async () => {
            await vi.advanceTimersByTimeAsync(15000);
        });

        expect(screen.getByText(/still confirming your payment/i)).toBeTruthy();
        // Retries are bounded — it must not poll Stripe forever.
        expect(spy.mock.calls.length).toBeLessThanOrEqual(3);
    });

    it("shows a graceful message for an unknown session, with no stack trace", async () => {
        mockFetchSequence([{ status: 404, body: { status: "not_found" } }]);
        render(<PaymentConfirmation sessionId="cs_test_bogus" />);

        expect(await screen.findByText(/couldn.t find that payment/i)).toBeTruthy();
        expect(document.body.textContent).not.toMatch(/Error:|Traceback|at .*\.tsx/);
    });

    it("treats a missing session id as not-found rather than hanging", async () => {
        mockFetchSequence([{ body: PAID_BOOKING }]);
        render(<PaymentConfirmation sessionId={null} />);

        expect(await screen.findByText(/couldn.t find that payment/i)).toBeTruthy();
    });

    it("only claims an email was sent when finalize confirmed it", async () => {
        mockFetchSequence([{ body: PAID_BOOKING }]);
        const { rerender } = render(
            <PaymentConfirmation sessionId="cs_test_paid" receiptEmailed={null} />
        );
        await screen.findByText(/Payment received/);
        expect(screen.queryByText(/confirmation email is on its way/i)).toBeNull();

        rerender(<PaymentConfirmation sessionId="cs_test_paid" receiptEmailed={true} />);
        await waitFor(() =>
            expect(screen.getByText(/confirmation email is on its way/i)).toBeTruthy()
        );
    });
});
