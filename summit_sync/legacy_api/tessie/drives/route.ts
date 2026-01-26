import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
    console.log("API ROUTE HIT");
    return NextResponse.json({
        success: true,
        message: "API is working",
        drives: []
    });
}
