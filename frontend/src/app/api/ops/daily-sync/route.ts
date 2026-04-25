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
        // --- ENVIRONMENT CHECK ---
        const isWindows = process.platform === 'win32';
        
        if (!isWindows) {
            console.log("Skipping Daily Sync: Not running on Windows (Azure/Cloud Environment).");
            return NextResponse.json({
                success: false,
                error: "Daily Sync can only be triggered when running the dashboard locally on the host machine.",
                logs: ["[INFO] Daily Sync is disabled in the Cloud environment to prevent local path conflicts."]
            });
        }

        // Use the same absolute path logic as the desktop button
        const baseDir = "c:\\Users\\PeterTeehan\\OneDrive - COS Tesla LLC\\COS Tesla - Website";
        
        console.log("Starting Daily Sync API request...");

        // 1. Create Folders (PowerShell)
        const psCommand = `powershell -ExecutionPolicy Bypass -File "${baseDir}\\Scripts\\Sync-UberDriverFolders.ps1"`;
        const { stdout: psOut } = await execAsync(psCommand);
        
        // 2. Run Data Sync (Python)
        const pythonCommand = `cd /d "${baseDir}\\Summit-OS-Web-master" && python sync_today.py`;
        const { stdout: pyOut } = await execAsync(pythonCommand);
        
        const combinedLogs = [
            ...psOut.split('\n').filter(l => l.trim()),
            ...pyOut.split('\n').filter(l => l.trim())
        ];

        return NextResponse.json({
            success: true,
            logs: combinedLogs
        });
    } catch (error: any) {
        console.error('Daily Sync API Error:', error);
        
        // Return details so the dashboard console can show what failed
        return NextResponse.json({
            success: false,
            error: error.message,
            logs: [
                `[ERROR] ${error.message}`,
                ...(error.stdout ? error.stdout.split('\n') : []),
                ...(error.stderr ? error.stderr.split('\n') : [])
            ]
        }, { status: 500 });
    }
}
