import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy | COS Tesla LLC",
  description:
    "Privacy Policy for COS Tesla LLC. Learn how we collect, use, and protect your personal information.",
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="container mx-auto px-6 py-24 max-w-3xl">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-cyan-400 text-sm mb-12 hover:text-cyan-300 transition-colors"
        >
          ← Back to Home
        </Link>

        <h1 className="text-4xl font-bold mb-2">Privacy Policy</h1>
        <p className="text-gray-500 text-sm mb-12 font-mono">
          Effective Date: January 1, 2025 · Last updated: May 2026
        </p>

        <div className="space-y-10 text-gray-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">1. Who We Are</h2>
            <p>
              COS Tesla LLC ("Company," "we," "us," or "our") is a private transportation
              company based in Colorado Springs, Colorado. We operate the website
              costesla.com and the SummitOS booking platform.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">2. Information We Collect</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>Name, email address, and phone number when you make a booking</li>
              <li>Pickup and drop-off location addresses</li>
              <li>Payment information (processed securely by Stripe — we do not store card data)</li>
              <li>Trip history and booking metadata</li>
              <li>Device and browser information for service improvement</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">3. How We Use Your Information</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>To process and confirm your booking</li>
              <li>To send booking confirmations and receipts via email</li>
              <li>To facilitate payment processing</li>
              <li>To improve our service and pricing algorithms</li>
              <li>To communicate service updates (you may opt out at any time)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">4. Data Sharing</h2>
            <p>
              We do not sell your personal information. We share data only with trusted
              third-party services necessary to operate our platform:
            </p>
            <ul className="list-disc list-inside space-y-2 mt-3">
              <li>
                <strong className="text-white">Stripe</strong> — payment processing
              </li>
              <li>
                <strong className="text-white">Microsoft Azure</strong> — cloud infrastructure
              </li>
              <li>
                <strong className="text-white">Google Maps</strong> — route calculation
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">5. Data Retention</h2>
            <p>
              Booking records are retained for up to 7 years for accounting and tax purposes.
              You may request deletion of your personal data (subject to legal retention
              obligations) by contacting us at the address below.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">6. Your Rights</h2>
            <p>
              If you are a Colorado resident, you have rights under the Colorado Privacy Act
              (CPA), including the right to access, correct, delete, and opt out of the sale
              of your personal data. To exercise these rights, email us.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">7. Contact</h2>
            <p>
              For privacy-related inquiries:
              <br />
              <a
                href="mailto:peter.teehan@costesla.com"
                className="text-cyan-400 hover:text-cyan-300"
              >
                peter.teehan@costesla.com
              </a>
              <br />
              COS Tesla LLC · Colorado Springs, CO
            </p>
          </section>
        </div>

        <div className="mt-16 pt-8 border-t border-white/10 flex gap-6 text-sm text-gray-600">
          <Link href="/terms" className="hover:text-gray-400 transition-colors">
            Terms of Service
          </Link>
          <Link href="/contact" className="hover:text-gray-400 transition-colors">
            Contact
          </Link>
          <Link href="/" className="hover:text-gray-400 transition-colors">
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}
