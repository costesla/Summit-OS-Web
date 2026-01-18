import { NextResponse } from 'next/server';

export async function GET(request: Request) {
    console.log("API ROUTE HIT");
    return NextResponse.json({
        success: true,
        message: "API is working",
        drives: []
    });
}
