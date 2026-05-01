'use client';

import dynamic from 'next/dynamic';

const DriverDashboard = dynamic(
    () => import('./DriverDashboard'),
    { ssr: false, loading: () => <div style={{ minHeight: '100vh', background: '#05080a' }} /> }
);

export default function ClientDashboardWrapper() {
    return <DriverDashboard />;
}
