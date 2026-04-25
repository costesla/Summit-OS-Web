import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

/**
 * API Route to trigger the Daily Operations:
 * 1. Create OneDrive folders for the current date.
 * 2. Run the sync_today.py script to pull Tessie and Banking data.
 */
export async function POST() {
    try {
        console.log("Triggering Cloud Daily Sync...");

        // Call the Azure Python Backend directly
        const azureApiUrl = "https://summitos-api.azurewebsites.net/api/daily-sync";
        
        const response = await fetch(azureApiUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `Azure API returned ${response.status}`);
        }

        return NextResponse.json({
            success: true,
            logs: data.logs || ["[INFO] Sync completed via Cloud API"]
        });
    } catch (error: any) {
        console.error('Daily Sync API Error:', error);
        
        return NextResponse.json({
            success: false,
            error: error.message,
            logs: [
                `[ERROR] ${error.message}`,
                ...(error.logs || [])
            ]
        }, { status: 500 });
    }
}
