"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import Image from "next/image";
import WeatherWatch from "../components/WeatherWatch";
import FlightTracker from "../components/FlightTracker";
import BookingEngine from "../components/BookingEngine";
import { useEffect } from "react";

const LiveMap = dynamic(() => import("../components/LiveMap"), {
  ssr: false,
  loading: () => <div className="h-[200px] flex items-center justify-center text-gray-500 font-mono text-xs">INITIALIZING GPS...</div>
});

export default function Home() {
  useEffect(() => {
    if (typeof window !== "undefined") {
      const host = window.location.hostname.toLowerCase();
      if (
        host.includes("dashboard") ||
        host.includes("driver") ||
        host === "summit-os.com"
      ) {
        window.location.replace("/driver-dashboard");
      }
    }
  }, []);

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 overflow-x-hidden selection:bg-blue-600 selection:text-white">

      {/* 1. HERO SECTION: PIKES PEAK PARALLAX */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden">

        {/* Background Image (Fixed/Parallax feel) */}
        <div className="absolute inset-0 z-0">
          <Image
            src="/pikes-peak-bg.png"
            alt="Pikes Peak Silhouette"
            fill
            className="object-cover opacity-60"
            priority
          />
          {/* Gradient Overlay for Text Readability - Morning/Foggy theme */}
          <div className="absolute inset-0 bg-gradient-to-t from-slate-50 via-transparent to-white/30" />
          <div className="absolute inset-0 bg-gradient-to-r from-white/90 via-transparent to-transparent" />
        </div>

        <div className="container mx-auto px-6 relative z-10 grid lg:grid-cols-12 gap-12 items-center pt-20">

          {/* Left: Copy */}
          <div className="lg:col-span-6 space-y-10 animate-in fade-in slide-in-from-left duration-1000">
            <div>
              <h2 className="flex items-center gap-3 text-xs font-bold tracking-[0.4em] text-blue-600 mb-6 uppercase">
                <span className="w-8 h-[1px] bg-blue-600"></span>
                El Paso County • Colorado
              </h2>
              <h1 className="text-6xl lg:text-8xl font-bold leading-tight tracking-tighter">
                COS <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-slate-900 to-slate-500">TESLA.</span>
              </h1>
              <p className="font-mono text-blue-600 tracking-[0.3em] text-xs mt-4 uppercase">Powered by SummitOS</p>
            </div>

            <p className="text-2xl text-slate-700 font-light max-w-lg leading-relaxed border-l-2 border-slate-300 pl-6">
              The executive standard for private transport.
              Precision pricing. Zero surge.
              Driven by <strong className="font-semibold text-slate-900">Technology</strong>.
            </p>


          </div>

          {/* Right: Car Image (Floating) */}
          {/* Right: Car Image - Removed per request */}
          <div className="lg:col-span-6 hidden lg:block"></div>
        </div>

        {/* Scroll Indicator */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 animate-bounce opacity-50">
          <div className="w-[1px] h-16 bg-gradient-to-b from-slate-900 to-transparent"></div>
        </div>
      </section>

      {/* 2. PRECISION QUOTE (Floating Overlay) */}
      <section className="relative z-20 -mt-24 lg:-mt-32 px-4 mb-32">
        <div className="max-w-5xl mx-auto">
          <div className="bg-white/80 backdrop-blur-2xl border border-slate-200/60 rounded-[3rem] p-1 shadow-2xl shadow-slate-200/40">
            <div className="bg-white/50 rounded-[2.8rem] p-8 lg:p-12 border border-slate-100/50">
              <div className="flex flex-col lg:flex-row items-center justify-between mb-8 gap-4">
                <h3 className="text-xl font-medium tracking-wide text-slate-950">
                  <span className="font-bold text-blue-600">01.</span> Instant Quote
                </h3>
                <div className="h-[1px] flex-1 bg-slate-200/80 mx-6 hidden lg:block"></div>
                <span className="text-xs font-mono text-slate-500 uppercase tracking-widest">Powered by Google Distance Matrix</span>
              </div>
              <BookingEngine />
            </div>
          </div>
        </div>
      </section>

      {/* 3. FEATURE: GARDEN OF THE GODS */}
      <section className="relative py-32 overflow-hidden border-t border-slate-200/50">
        {/* Background */}
        <div className="absolute inset-0 bg-slate-100/50 opacity-0 lg:opacity-100 transition-opacity duration-500">
          <Image
            src="/garden-gods-bg.png"
            alt="Garden of the Gods"
            fill
            className="object-cover opacity-10 blur-sm"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-slate-50 via-transparent to-slate-50" />
        </div>

        <div className="container mx-auto px-6 relative z-10">
          <div className="grid lg:grid-cols-2 gap-20 items-center">

            {/* Visual */}
            <div className="relative h-[600px] w-full rounded-[3rem] overflow-hidden border border-slate-200 shadow-xl group">
              <LiveMap className="h-full w-full grayscale opacity-90 group-hover:grayscale-0 group-hover:opacity-100 transition-all duration-1000 scale-105 group-hover:scale-100" />

              {/* Overlay Info */}
              <div className="absolute bottom-0 left-0 w-full p-8 bg-gradient-to-t from-white via-white/95 to-transparent">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold font-mono text-blue-600 mb-1">LIVE TELEMETRY</div>
                    <div className="text-2xl font-bold text-slate-900">COS Tesla Fleet Location</div>
                  </div>
                  <div className="w-12 h-12 rounded-full border border-slate-200 flex items-center justify-center bg-white/80 backdrop-blur-md shadow-sm">
                    <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]"></span>
                  </div>
                </div>
              </div>
            </div>

            {/* Content */}
            <div className="space-y-12">
              <div className="space-y-6">
                <div className="flex items-center gap-4">
                  <span className="text-6xl font-thin text-slate-200 select-none">02</span>
                  <h2 className="text-4xl font-bold text-slate-900">Local Knowledge.<br />Global Tech.</h2>
                </div>
                <p className="text-lg text-slate-600 font-light leading-relaxed">
                  Driving El Paso County isn't just about GPS; it's about knowing the terrain.
                  From the icy switchbacks of <strong className="font-semibold text-slate-900">Broadmoor Bluffs</strong> to the unpaved expanses of <strong className="font-semibold text-slate-900">Black Forest</strong>,
                  we combine 20 years of local IT expertise with our advanced AWD fleet.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-8 border-t border-slate-200 pt-8">
                <div>
                  <div className="text-3xl font-bold text-slate-900 mb-2">20+</div>
                  <div className="text-sm text-slate-500 uppercase tracking-widest font-semibold">Years IT Exp</div>
                </div>
                <div>
                  <div className="text-3xl font-bold text-slate-900 mb-2">100%</div>
                  <div className="text-sm text-slate-500 uppercase tracking-widest font-semibold">Safety Rating</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. THE CABIN EXPERIENCE */}
      <section className="py-32 bg-slate-50/50 relative border-y border-slate-200/50">
        <div className="container mx-auto px-6">
          <div className="max-w-4xl mx-auto text-center mb-20">
            <h2 className="text-4xl lg:text-5xl font-bold mb-6 text-slate-900">Your Private <span className="text-blue-600">Command Center</span>.</h2>
            <p className="text-xl text-slate-600 font-light">
              Control your environment from your phone. No apps to install. Just a secure link.
            </p>
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Card 1 */}
            <div className="bg-white/90 backdrop-blur-md p-8 rounded-3xl border border-slate-200/60 shadow-sm hover:border-blue-500/40 hover:shadow-md transition-all group">
              <div className="w-12 h-12 rounded-2xl bg-blue-500/10 flex items-center justify-center mb-6 text-blue-600 group-hover:scale-110 transition-transform">
                <span className="text-2xl">🌡️</span>
              </div>
              <h3 className="text-xl font-bold mb-3 text-slate-900">Climate Control</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Too hot? Too cold? Adjust the rear seat heaters instantly from your personal dashboard.
              </p>
            </div>

            {/* Card 2 */}
            <div className="bg-white/90 backdrop-blur-md p-8 rounded-3xl border border-slate-200/60 shadow-sm hover:border-blue-500/40 hover:shadow-md transition-all group relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-5 font-bold text-8xl -translate-y-4 translate-x-4 text-slate-400 select-none">ui</div>
              <div className="w-12 h-12 rounded-2xl bg-blue-500/10 flex items-center justify-center mb-6 text-blue-600 group-hover:scale-110 transition-transform">
                <span className="text-2xl">🧭</span>
              </div>
              <h3 className="text-xl font-bold mb-3 text-slate-900">Live Telemetry</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Watch your altitude climb as we ascend Ute Pass. Monitor speed and ETA in real-time.
              </p>
            </div>

            {/* Card 3 */}
            <div className="bg-white/90 backdrop-blur-md p-8 rounded-3xl border border-slate-200/60 shadow-sm hover:border-blue-500/40 hover:shadow-md transition-all group">
              <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mb-6 text-slate-800 group-hover:scale-110 transition-transform">
                <span className="text-2xl">🔒</span>
              </div>
              <h3 className="text-xl font-bold mb-3 text-slate-900">Secure Access</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Each trip generates a unique session token. Your controls expire safely when you drop off.
              </p>
            </div>
          </div>

          <div className="mt-16 text-center">
            <Link href="/cabin" className="inline-flex items-center gap-3 text-lg font-medium border-b border-blue-600 pb-1 text-blue-600 hover:text-blue-800 transition-colors">
              Access Cabin Dashboard <span className="text-xl">&rarr;</span>
            </Link>
          </div>
        </div>
      </section>

      {/* 5. PRICING & WIDGETS */}
      <section className="py-32 container mx-auto px-6">
        <div className="grid lg:grid-cols-2 gap-20">

          {/* Pricing Logic */}
          <div className="bg-white/95 backdrop-blur-md rounded-[3rem] p-12 border border-slate-200/80 shadow-lg relative overflow-hidden">
            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 blur-[100px] rounded-full pointer-events-none" />

            <h3 className="text-3xl font-bold mb-8 text-slate-900">Fairness Engine v4.0</h3>
            <div className="space-y-8">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <span className="text-slate-600">Base Engagement</span>
                <span className="text-2xl font-bold text-slate-900">$30.00</span>
              </div>
            </div>
            <p className="mt-8 text-xs text-slate-500 font-mono leading-relaxed">
              *$30 FLAT FEE IS VALID ONLY WITHIN EL PASO COUNTY, COLORADO. ANYTHING BEYOND THIS RANGE WILL INCLUDE $1.75/MILE.<br /><br />
              *PRICING CALCULATED VIA GOOGLE DISTANCE MATRIX API. NO SURGE PRICING. EVER.
            </p>
          </div>

          {/* Widgets */}
          <div className="space-y-8">
            <h3 className="text-3xl font-bold mb-2 text-slate-900">Live Status</h3>
            <p className="text-slate-600 mb-8">Monitoring conditions for a smooth ascent.</p>

            <div className="opacity-95 hover:opacity-100 transition-opacity">
              <WeatherWatch />
            </div>

            <div className="opacity-95 hover:opacity-100 transition-opacity">
              <FlightTracker />
            </div>
          </div>
        </div>
      </section>

      {/* 6. FOOTER */}
      <footer className="border-t border-slate-200 bg-slate-50 pt-20 pb-10 text-slate-700">
        <div className="container mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-20">
            <div className="col-span-2">
              <h2 className="text-2xl font-bold tracking-tighter mb-1 text-slate-900">COS TESLA.</h2>
              <p className="font-mono text-blue-600 tracking-[0.2em] text-xs font-semibold uppercase mb-6">Powered by SummitOS</p>
              <p className="text-slate-600 max-w-sm">
                Executive transport redefined for the modern era.
                Locally owned in Colorado Springs.
              </p>
            </div>
            <div>
              <h4 className="font-bold mb-6 text-slate-900">Links</h4>
              <ul className="space-y-4 text-slate-600 text-sm">
                <li><Link href="/book" className="hover:text-blue-600 transition-colors">Book a Ride</Link></li>
                <li><Link href="/cabin" className="hover:text-blue-600 transition-colors">Passenger Cabin</Link></li>
                <li><Link href="/track" className="hover:text-blue-600 transition-colors">Track Vehicle</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold mb-6 text-slate-900">Legal</h4>
              <ul className="space-y-4 text-slate-600 text-sm">
                <li><Link href="/privacy" className="hover:text-blue-600 transition-colors">Privacy Policy</Link></li>
                <li><Link href="/terms" className="hover:text-blue-600 transition-colors">Terms of Service</Link></li>
                <li><Link href="/contact" className="hover:text-blue-600 transition-colors">Contact Support</Link></li>
              </ul>
            </div>
          </div>

          <div className="border-t border-slate-200 pt-10 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-xs text-slate-500">
              &copy; {new Date().getFullYear()} COS Tesla LLC.
            </p>

          </div>
        </div>
      </footer>
    </main>
  );
}
