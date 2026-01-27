
import { randomUUID } from 'crypto';

/**
 * SummitOS Session Manager (In-Memory MVP)
 * 
 * In a serverless environment (Vercel), "In-Memory" resets on cold boot.
 * Ideally, we use Vercel KV (Redis). 
 * 
 * FOR THIS MVP: We will assume "Hot" lambdas or accept that resets log users out.
 * 
 * TODO: Upgrade to Redis/KV when persistence is required across deployments.
 */

// Global Map outside function scope to persist across hot-reloads in Dev
// In Prod Vercel, this is unreliable, but fine for a demo/MVP.
declare global {
    var _summitSessions: Map<string, SessionData> | undefined;
}

interface SessionData {
    tripId: string;
    passengerName: string;
    createdAt: number;
    expiresAt: number;
}

if (!global._summitSessions) {
    global._summitSessions = new Map();
}

const sessions = global._summitSessions!;

export class SessionManager {

    static createSession(tripId: string, passengerName: string): string {
        const token = randomUUID();
        const now = Date.now();

        sessions.set(token, {
            tripId,
            passengerName,
            createdAt: now,
            expiresAt: now + (1000 * 60 * 60 * 4) // 4 Hours Expiry (Typical Trip Max)
        });

        return token;
    }

    static validateSession(token: string): SessionData | null {
        const session = sessions.get(token);
        if (!session) return null;

        if (Date.now() > session.expiresAt) {
            sessions.delete(token);
            return null;
        }

        return session;
    }

    static invalidateSession(token: string) {
        sessions.delete(token);
    }
}
