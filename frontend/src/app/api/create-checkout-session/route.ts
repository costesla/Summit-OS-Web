/**
 * app/api/create-checkout-session/route.ts
 *
 * LOCAL DEV PROXY — This route only runs during `next dev`.
 *
 * In PRODUCTION (Azure Static Web Apps static export), this file is NOT executed.
 * The frontend calls the Azure Function backend directly via lib/api.ts.
 *
 * This proxy forwards the request to the Python Azure Function so that
 * local development works without needing to run the Python backend locally.
 */
import { NextResponse } from "next/server";

const BACKEND =
  process.env.AZURE_FUNCTION_URL ||
  "https://summitos-api.azurewebsites.net";

const FUNCTION_KEY = process.env.AZURE_FUNCTION_KEY || "";

export async function POST(req: Request) {
  try {
    const body = await req.json();

    const response = await fetch(`${BACKEND}/api/create-checkout-session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(FUNCTION_KEY ? { "x-functions-key": FUNCTION_KEY } : {}),
      },
      body: JSON.stringify({
        ...body,
        successUrl:
          body.successUrl ||
          `${req.headers.get("origin")}/book/success?session_id={CHECKOUT_SESSION_ID}`,
        cancelUrl:
          body.cancelUrl ||
          `${req.headers.get("origin")}/book?payment_cancelled=true`,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.error || "Backend error" },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("create-checkout-session proxy error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export const runtime = "edge"; // use edge runtime (compatible with static export dev mode)
