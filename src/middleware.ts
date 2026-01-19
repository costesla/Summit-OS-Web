
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Note: In Vercel Edge Middleware, we cannot access the Node.js global 'sessions' map easily 
// because Middleware runs in a separate V8 isolate (Edge Runtime).
// 
// STRATEGY: 
// For this MVP, we will allow the "Client Side" check in page.tsx (useEffect) to handle the soft-auth/UX.
// The Middleware here will just ensure a token *exists* in the URL to prevent casual browsing.
// If we wanted hard security, we'd use Signed Cookies (JWT) or an external store (Redis/KV).
// 
// Current Logic:
// 1. If path starts with /cabin
// 2. Check searchParams for 'token'
// 3. If missing -> Redirect to /

export function middleware(request: NextRequest) {
    const { pathname, searchParams } = request.nextUrl;

    // Protect /cabin
    if (pathname.startsWith('/cabin')) {
        const token = searchParams.get('token');

        if (!token) {
            // Redirect to Home if no token
            return NextResponse.redirect(new URL('/', request.url));
        }

        // (Optional) Verify JWT signature here if we upgraded logic
    }

    return NextResponse.next();
}

export const config = {
    matcher: '/cabin/:path*',
};
