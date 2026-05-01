import dynamic from 'next/dynamic';

// Force this page to never be statically prerendered.
// The dashboard uses localStorage, authentication, and live API data
// which are all unavailable at build time.
export const dynamicPage = 'force-dynamic';
export const revalidate = 0;

export const metadata = {
    title: 'Driver Dashboard | COS Tesla',
    description: 'Daily driver trip and expense tracking dashboard for COS Tesla.',
};

// Disable SSR entirely for the dashboard component
const DriverDashboard = dynamic(
    () => import('@/components/DriverDashboard'),
    { ssr: false }
);

export default function DriverDashboardPage() {
    return <DriverDashboard />;
}
