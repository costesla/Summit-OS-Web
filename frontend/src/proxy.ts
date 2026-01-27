import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function proxy(request: NextRequest) {
    const { pathname, searchParams } = request.nextUrl;

    // 1. EXCLUDE AZURE INTERNAL ROUTES
    if (
        pathname.startsWith('/_next') ||
        pathname.startsWith('/api') ||
        pathname.startsWith('/static') ||
        pathname.startsWith('/.swa') ||
        pathname.includes('.') // skip files like favicon.ico
    ) {
        return NextResponse.next();
    }

    // 2. YOUR CUSTOM LOGIC: Protect /cabin
    if (pathname.startsWith('/cabin')) {
        const token = searchParams.get('token');

        if (!token) {
            // Redirect to Home if no token
            return NextResponse.redirect(new URL('/', request.url));
        }
    }

    return NextResponse.next();
}

// 3. THE MATCHER (CRITICAL)
export const config = {
    matcher: [
        /*
         * Match all request paths except for the ones starting with:
         * - api (API routes)
         * - _next/static (static files)
         * - _next/image (image optimization files)
         * - favicon.ico (favicon file)
         * - .swa (Azure SWA internal)
         */
        '/((?!api|_next/static|_next/image|favicon.ico|.swa).*)',
    ],
};
