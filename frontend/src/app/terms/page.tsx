import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service | COS Tesla LLC",
  description:
    "Terms of Service for COS Tesla LLC private transportation services.",
};

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-[#0a0a0a] text-white">
      <div className="container mx-auto px-6 py-24 max-w-3xl">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-cyan-400 text-sm mb-12 hover:text-cyan-300 transition-colors"
        >
          ← Back to Home
        </Link>

        <h1 className="text-4xl font-bold mb-2">Terms of Service</h1>
        <p className="text-gray-500 text-sm mb-12 font-mono">
          Effective Date: January 1, 2025 · Last updated: May 2026
        </p>

        <div className="space-y-10 text-gray-300 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">1. Acceptance</h2>
            <p>
              By using costesla.com or the SummitOS booking platform you agree to these
              Terms of Service. If you do not agree, do not use our services.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">2. Service Description</h2>
            <p className="mb-4">
              COS Tesla LLC provides private passenger transportation services in El Paso
              County, Colorado and surrounding areas. Service is subject to driver
              availability and geographic coverage.
            </p>
            <p className="text-sm text-gray-400">
              COS Tesla LLC operates as a prearranged luxury transportation service under Colorado Department of Regulatory Agencies (DORA) Public Utilities Commission Permit No. <span className="text-cyan-400 font-mono">0250</span> (issued in 2026).
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">3. Booking & Payment</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>Bookings are confirmed upon payment or explicit driver acceptance.</li>
              <li>
                The base fare is $30 flat within El Paso County. Trips beyond county
                boundaries are charged at $1.75/mile beyond the county border.
              </li>
              <li>Pricing is calculated via Google Distance Matrix API at booking time.</li>
              <li>No surge pricing is applied at any time.</li>
              <li>Accepted payment: Stripe (card/Apple Pay), Venmo, Zelle, Cash App, Cash.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">4. Cancellation Policy</h2>
            <p>
              Cancellations made more than 2 hours before the scheduled pickup time are
              eligible for a full refund. Cancellations within 2 hours of pickup are
              non-refundable. No-shows are charged the full fare.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">5. Cabin Controls</h2>
            <p>
              Access to in-vehicle cabin controls (climate, seat heaters, trunk) is granted
              via a time-limited, single-use token provided in the booking confirmation.
              Misuse of cabin controls may result in loss of access.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">6. Limitation of Liability</h2>
            <p>
              COS Tesla LLC is not liable for delays caused by weather, traffic, road
              conditions, or events outside our control. Our maximum liability for any claim
              related to a single trip is limited to the fare paid for that trip.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">7. Governing Law & Regulatory Oversight</h2>
            <p className="mb-4">
              These terms are governed by the laws of the State of Colorado. Any disputes
              will be resolved in El Paso County, Colorado courts.
            </p>
            <p className="text-sm text-gray-400">
              As a Limited Regulation Carrier, our operations are subject to safety and insurance oversight by the Colorado Public Utilities Commission (PUC). For inquiries or to file a passenger complaint, you may contact the PUC Consumer Affairs Unit directly at 303-894-2000 or visit their official website.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">8. Contact</h2>
            <p>
              Questions about these terms:
              <br />
              <a
                href="mailto:peter.teehan@costesla.com"
                className="text-cyan-400 hover:text-cyan-300"
              >
                peter.teehan@costesla.com
              </a>
            </p>
          </section>
        </div>

        <div className="mt-16 pt-8 border-t border-white/10 flex gap-6 text-sm text-gray-600">
          <Link href="/privacy" className="hover:text-gray-400 transition-colors">
            Privacy Policy
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
