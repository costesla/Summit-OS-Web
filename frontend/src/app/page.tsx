"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import Image from "next/image";
import WeatherWatch from "../components/WeatherWatch";
import FlightTracker from "../components/FlightTracker";
import BookingEngine from "../components/BookingEngine";

const LiveMap = dynamic(() => import("../components/LiveMap"), {
  ssr: false,
  loading: () => <div className="h-[200px] flex items-center justify-center text-gray-500 font-mono text-xs">INITIALIZING GPS...</div>
});

export default function Home() {
  return (
    <main className="min-h-screen bg-[var(--background)] text-white overflow-x-hidden selection:bg-cyan-500 selection:text-white">

      {/* 1. HERO SECTION: PIKES PEAK PARALLAX */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden">

        {/* Background Image (Fixed/Parallax feel) */}
        <div className="absolute inset-0 z-0">
          <Image
            src="/pikes-peak-bg.png"
            alt="Pikes Peak Midnight Silhouette"
            fill
            className="object-cover opacity-80"
            priority
          />
          {/* Gradient Overlay for Text Readability */}
          <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a] via-transparent to-black/40" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-transparent to-transparent" />
        </div>

        <div className="container mx-auto px-6 relative z-10 grid lg:grid-cols-12 gap-12 items-center pt-20">

          {/* Left: Copy */}
          <div className="lg:col-span-6 space-y-10 animate-in fade-in slide-in-from-left duration-1000">
            <div>
              <h2 className="flex items-center gap-3 text-xs font-bold tracking-[0.4em] text-cyan-400 mb-6 uppercase">
                <span className="w-8 h-[1px] bg-cyan-400"></span>
                El Paso County • Colorado
              </h2>
              <h1 className="text-6xl lg:text-8xl font-bold leading-tight tracking-tighter">
                Summit <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-white to-gray-500">OS.</span>
              </h1>
            </div>

            <p className="text-2xl text-gray-300 font-light max-w-lg leading-relaxed border-l-2 border-white/20 pl-6">
              The executive standard for private transport.
              Precision pricing. Zero surge.
              Driven by <strong>Technology</strong>.
            </p>


          </div>

          {/* Right: Car Image (Floating) */}
          {/* Right: Car Image - Removed per request */}
          <div className="lg:col-span-6 hidden lg:block"></div>
        </div>

        {/* Scroll Indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 animate-bounce opacity-50">
          <div className="w-[1px] h-16 bg-gradient-to-b from-white to-transparent"></div>
        </div>
      </section>

      {/* 2. PRECISION QUOTE (Floating Overlay) */}
      <section className="relative z-20 -mt-24 lg:-mt-32 px-4 mb-32">
        <div className="max-w-5xl mx-auto">
          <div className="bg-[#0a0a0a]/80 backdrop-blur-2xl border border-white/10 rounded-[3rem] p-1 shadow-2xl shadow-black/80">
            <div className="bg-[#111]/50 rounded-[2.8rem] p-8 lg:p-12 border border-white/5">
              <div className="flex flex-col lg:flex-row items-center justify-between mb-8 gap-4">
                <h3 className="text-xl font-light tracking-wide text-white">
                  <span className="font-bold text-cyan-400">01.</span> Instant Quote
                </h3>
                <div className="h-[1px] flex-1 bg-white/10 mx-6 hidden lg:block"></div>
                <span className="text-xs font-mono text-gray-500 uppercase tracking-widest">Powered by Google Distance Matrix</span>
              </div>
              <BookingEngine />
            </div>
          </div>
        </div>
      </section>

      {/* 3. FEATURE: GARDEN OF THE GODS */}
      <section className="relative py-32 overflow-hidden">
        {/* Background */}
        <div className="absolute inset-0 bg-white/5 opacity-0 lg:opacity-100 transition-opacity duration-500">
          <Image
            src="/garden-gods-bg.png"
            alt="Garden of the Gods Night"
            fill
            className="object-cover opacity-20 blur-sm"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0a] via-transparent to-[#0a0a0a]" />
        </div>

        <div className="container mx-auto px-6 relative z-10">
          <div className="grid lg:grid-cols-2 gap-20 items-center">

            {/* Visual */}
            <div className="relative h-[600px] w-full rounded-[3rem] overflow-hidden border border-white/10 group">
              <LiveMap className="h-full w-full grayscale opacity-80 group-hover:grayscale-0 group-hover:opacity-100 transition-all duration-1000 scale-105 group-hover:scale-100" />

              {/* Overlay Info */}
              <div className="absolute bottom-0 left-0 w-full p-8 bg-gradient-to-t from-black via-black/80 to-transparent">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-mono text-cyan-400 mb-1">LIVE TELEMETRY</div>
                    <div className="text-2xl font-bold">SummitOS Fleet Location</div>
                  </div>
                  <div className="w-12 h-12 rounded-full border border-white/20 flex items-center justify-center bg-white/5 backdrop-blur-md">
                    <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]"></span>
                  </div>
                </div>
              </div>
            </div>

            {/* Content */}
            <div className="space-y-12">
              <div className="space-y-6">
                <div className="flex items-center gap-4">
                  <span className="text-6xl font-thin text-white/10">02</span>
                  <h2 className="text-4xl font-bold">Local Knowledge.<br />Global Tech.</h2>
                </div>
                <p className="text-lg text-gray-400 font-light leading-relaxed">
                  Driving El Paso County isn't just about GPS; it's about knowing the terrain.
                  From the icy switchbacks of <strong>Broadmoor Bluffs</strong> to the unpaved expanses of <strong>Black Forest</strong>,
                  we combine 20 years of local IT expertise with our advanced AWD fleet.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-8 border-t border-white/10 pt-8">
                <div>
                  <div className="text-3xl font-bold text-white mb-2">20+</div>
                  <div className="text-sm text-gray-500 uppercase tracking-widest">Years IT Exp</div>
                </div>
                <div>
                  <div className="text-3xl font-bold text-white mb-2">100%</div>
                  <div className="text-sm text-gray-500 uppercase tracking-widest">Safety Rating</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. THE CABIN EXPERIENCE */}
      <section className="py-32 bg-[#050505] relative">
        <div className="container mx-auto px-6">
          <div className="max-w-4xl mx-auto text-center mb-20">
            <h2 className="text-4xl lg:text-5xl font-bold mb-6">Your Private <span className="text-cyan-400">Command Center</span>.</h2>
            <p className="text-xl text-gray-400 font-light">
              Control your environment from your phone. No apps to install. Just a secure link.
            </p>
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Card 1 */}
            <div className="bg-[#111] p-8 rounded-3xl border border-white/5 hover:border-cyan-500/30 transition-all group">
              <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 flex items-center justify-center mb-6 text-cyan-400 group-hover:scale-110 transition-transform">
                <span className="text-2xl">🌡️</span>
              </div>
              <h3 className="text-xl font-bold mb-3">Climate Control</h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                Too hot? Too cold? Adjust the rear seat heaters instantly from your personal dashboard.
              </p>
            </div>

            {/* Card 2 */}
            <div className="bg-[#111] p-8 rounded-3xl border border-white/5 hover:border-white/20 transition-all group relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-10 font-bold text-8xl -translate-y-4 translate-x-4">ui</div>
              <div className="w-12 h-12 rounded-2xl bg-blue-500/10 flex items-center justify-center mb-6 text-blue-500 group-hover:scale-110 transition-transform">
                <span className="text-2xl">🧭</span>
              </div>
              <h3 className="text-xl font-bold mb-3">Live Telemetry</h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                Watch your altitude climb as we ascend Ute Pass. Monitor speed and ETA in real-time.
              </p>
            </div>

            {/* Card 3 */}
            <div className="bg-[#111] p-8 rounded-3xl border border-white/5 hover:border-white/20 transition-all group">
              <div className="w-12 h-12 rounded-2xl bg-white/10 flex items-center justify-center mb-6 text-white group-hover:scale-110 transition-transform">
                <span className="text-2xl">🔒</span>
              </div>
              <h3 className="text-xl font-bold mb-3">Secure Access</h3>
              <p className="text-sm text-gray-500 leading-relaxed">
                Each trip generates a unique session token. Your controls expire safely when you drop off.
              </p>
            </div>
          </div>

          <div className="mt-16 text-center">
            <Link href="/cabin" className="inline-flex items-center gap-3 text-lg font-medium border-b border-cyan-500 pb-1 hover:text-cyan-400 transition-colors">
              Access Cabin Dashboard <span className="text-xl">&rarr;</span>
            </Link>
          </div>
        </div>
      </section>

      {/* 5. PRICING & WIDGETS */}
      <section className="py-32 container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-20">

          {/* Pricing Logic */}
          <div className="bg-[#0f0f0f] rounded-[3rem] p-12 border border-white/10 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 blur-[100px] rounded-full pointer-events-none" />

            <h3 className="text-3xl font-bold mb-8">Fairness Engine v2.0</h3>
            <div className="space-y-8">
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <span className="text-gray-400">Base Engagement</span>
                <span className="text-2xl font-bold">$15.00</span>
              </div>
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <span className="text-gray-400">Local Mile (5-20mi)</span>
                <span className="text-2xl font-bold">$1.75<span className="text-sm text-gray-600 font-normal">/mi</span></span>
              </div>
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <span className="text-gray-400">Long Haul (20mi+)</span>
                <span className="text-2xl font-bold">$1.25<span className="text-sm text-gray-600 font-normal">/mi</span></span>
              </div>
            </div>
            <p className="mt-8 text-xs text-gray-500 font-mono">
              *PRICING CALCULATED VIA GOOGLE DISTANCE MATRIX API.
              NO SURGE PRICING. EVER.
            </p>
          </div>

          {/* Widgets */}
          <div className="space-y-8">
            <h3 className="text-3xl font-bold mb-2">Live Status</h3>
            <p className="text-gray-400 mb-8">Monitoring conditions for a smooth ascent.</p>

            <div className="opacity-90 hover:opacity-100 transition-opacity">
              <WeatherWatch />
            </div>

            <div className="opacity-90 hover:opacity-100 transition-opacity">
              <FlightTracker />
            </div>
          </div>
        </div>
      </section>

      {/* 6. FOOTER */}
      <footer className="border-t border-white/10 bg-black pt-20 pb-10">
        <div className="container mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-20">
            <div className="col-span-2">
              <h2 className="text-2xl font-bold tracking-tighter mb-6">SUMMIT OS.</h2>
              <p className="text-gray-500 max-w-sm">
                Executive transport redefined for the modern era.
                Locally owned in Colorado Springs.
              </p>
            </div>
            <div>
              <h4 className="font-bold mb-6">Links</h4>
              <ul className="space-y-4 text-gray-500 text-sm">
                <li><Link href="/book" className="hover:text-white transition-colors">Book a Ride</Link></li>
                <li><Link href="/cabin" className="hover:text-white transition-colors">Passenger Cabin</Link></li>
                <li><Link href="/track" className="hover:text-white transition-colors">Track Vehicle</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold mb-6">Legal</h4>
              <ul className="space-y-4 text-gray-500 text-sm">
                <li><Link href="#" className="hover:text-white transition-colors">Privacy Policy</Link></li>
                <li><Link href="#" className="hover:text-white transition-colors">Terms of Service</Link></li>
                <li><Link href="#" className="hover:text-white transition-colors">Contact Support</Link></li>
              </ul>
            </div>
          </div>

          <div className="border-t border-white/10 pt-10 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-xs text-gray-600">
              &copy; {new Date().getFullYear()} SummitOS LLC.
            </p>

          </div>
        </div>
      </footer>
    </main>
  );
}
