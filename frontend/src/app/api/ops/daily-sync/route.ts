/**
 * app/api/ops/daily-sync/route.ts
 *
 * LOCAL DEV PROXY — This route only runs during `next dev`.
 *
 * In PRODUCTION (Azure Static Web Apps static export), this file is NOT executed.
 * The frontend Dashboard calls the Azure Function backend directly via lib/api.ts.
 */
import { NextResponse } from "next/server";

const BACKEND =
  process.env.AZURE_FUNCTION_URL ||
  "https://summitos-api.azurewebsites.net";

const FUNCTION_KEY = process.env.AZURE_FUNCTION_KEY || "";

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));

    const response = await fetch(`${BACKEND}/api/daily-sync`, {
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
        { success: false, error: data.error || "Backend error", logs: data.logs || [] },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("ops/daily-sync proxy error:", message);
    return NextResponse.json(
      { success: false, error: message, logs: [`[ERROR] ${message}`] },
      { status: 500 }
    );
  }
}

export const runtime = "edge";
