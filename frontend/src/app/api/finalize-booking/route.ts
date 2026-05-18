/**
 * app/api/finalize-booking/route.ts
 *
 * LOCAL DEV PROXY — This route only runs during `next dev`.
 *
 * In PRODUCTION (Azure Static Web Apps static export), this file is NOT executed.
 * The frontend calls the Azure Function backend directly via lib/api.ts.
 *
 * This proxy forwards Stripe session finalization to the Python Azure Function
 * which handles: Stripe session retrieval, calendar booking, DB log, receipt email.
 */
import { NextResponse } from "next/server";

const BACKEND =
  process.env.AZURE_FUNCTION_URL ||
  "https://summitos-api.azurewebsites.net";

const FUNCTION_KEY = process.env.AZURE_FUNCTION_KEY || "";

export async function POST(req: Request) {
  try {
    const body = await req.json();

    if (!body.session_id) {
      return NextResponse.json({ error: "Missing session_id" }, { status: 400 });
    }

    const response = await fetch(`${BACKEND}/api/finalize-booking`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(FUNCTION_KEY ? { "x-functions-key": FUNCTION_KEY } : {}),
      },
      body: JSON.stringify(body),
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
    console.error("finalize-booking proxy error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export const runtime = "edge";
