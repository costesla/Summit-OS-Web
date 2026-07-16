import type { Metadata, Viewport } from 'next'
import { Outfit } from 'next/font/google'
import './globals.css'
import SiteFooter from '../components/SiteFooter'
import ServiceWorkerRegister from '../components/ServiceWorkerRegister'
import AppShell from '../components/AppShell'

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

export const metadata: Metadata = {
  title: 'COS Tesla | Premium Private Transport',
  description: 'The executive standard for private transport in Colorado Springs.',
  manifest: '/manifest.json',
  icons: {
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: '/icons/icon-192.png',
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'COS Tesla',
  },
}

export const viewport: Viewport = {
  themeColor: '#2563eb',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={outfit.variable}>
        <ServiceWorkerRegister />
        <AppShell />
        {/* Sidebar is fixed on lg+, so content is offset to clear it */}
        <div className="lg:pl-[var(--sos-nav-w)]">
          {children}
          <SiteFooter />
        </div>
      </body>
    </html>
  )
}
