"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import Image from "next/image";
import WeatherWidget from "../components/WeatherWidget";
import FlightTracker from "../components/FlightTracker";
import BookingEngine from "../components/BookingEngine";

const LiveMap = dynamic(() => import("../components/LiveMap"), {
  ssr: false,
  loading: () => <div className="h-[200px] flex items-center justify-center text-gray-500 font-mono text-xs">INITIALIZING GPS...</div>
});

export default function Home() {
  return (
    <main className="min-h-screen bg-[var(--background)] text-white overflow-hidden">

      {/* 1. HERO SECTION */}
      <section className="relative min-h-screen flex items-center pt-20 lg:pt-0">
        <div className="container mx-auto px-6 relative z-10 grid lg:grid-cols-2 gap-12 items-center">

          {/* Left: Copy */}
          <div className="space-y-8 animate-in fade-in slide-in-from-left duration-1000">
            <div>
              <h2 className="text-sm font-bold tracking-[0.3em] text-[var(--tesla-red)] mb-4 uppercase">
                El Paso County • Colorado
              </h2>
              <h1 className="text-5xl lg:text-7xl font-bold leading-tight tracking-tight">
                Executive <br />
                <span className="text-gray-500">Tesla Transport.</span>
              </h1>
            </div>

            <p className="text-xl text-gray-400 font-light max-w-lg leading-relaxed">
              Experience 'Ohana service in <strong>"Thor"</strong>—a 2024 Model Y.
              Precision pricing. Zero surge. Professional reliability.
            </p>

            <div className="flex flex-wrap gap-4">
              <Link href="/book" className="px-8 py-4 bg-white text-black font-bold rounded-full hover:bg-gray-200 transition-colors">
                Book Now
              </Link>
              <Link href="/cabin" className="px-8 py-4 border border-white/20 text-white font-medium rounded-full hover:bg-white/10 transition-colors backdrop-blur-md">
                Passenger Cabin
              </Link>
            </div>
          </div>

          {/* Right: Car Image */}
          <div className="relative h-[400px] lg:h-[600px] w-full animate-in fade-in scale-in duration-1000 delay-200">
            <Image
              src="/hero-car.png"
              alt="2024 Tesla Model Y Stealth Grey"
              fill
              className="object-contain drop-shadow-2xl"
              priority
            />
          </div>
        </div>

        {/* Background Gradients */}
        <div className="absolute top-0 right-0 w-[50%] h-full bg-gradient-to-l from-[#1a1a1a] to-transparent pointer-events-none -z-10" />
      </section>

      {/* 2. BOOKING ENGINE WIDGET */}
      <section className="container mx-auto px-6 -mt-20 lg:-mt-32 relative z-20 mb-20">
        <div className="max-w-4xl mx-auto bg-[#0f0f0f]/90 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl shadow-black/50">
          <h3 className="text-center text-sm font-mono text-gray-500 mb-6 uppercase tracking-widest">
            Real-Time Precision Quote
          </h3>
          <BookingEngine />
        </div>
      </section>

      {/* 3. CONTENT BLOCKS */}
      <section className="container mx-auto px-6 py-20 space-y-20">

        {/* Block A: Why COS Tesla? */}
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="order-2 lg:order-1 relative h-[300px] rounded-3xl overflow-hidden border border-white/10 bg-gray-900">
            {/* Live Map as visual proof of tech */}
            <LiveMap className="h-full w-full opacity-60 grayscale hover:grayscale-0 transition-all duration-700" />
            <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent" />
            <div className="absolute bottom-6 left-6">
              <div className="flex items-center gap-2">
                <span className="animate-pulse w-2 h-2 bg-green-500 rounded-full" />
                <span className="text-xs font-mono text-green-500">LIVE GPS TELEMETRY</span>
              </div>
            </div>
          </div>
          <div className="order-1 lg:order-2 space-y-6">
            <h3 className="text-3xl font-bold">20 Years of IT Expertise.</h3>
            <p className="text-gray-400 leading-relaxed">
              This isn't just a ride; it's a managed operation. Driven by Peter Teehan, an IT professional with 20+ years of experience.
              Safety is paramount, leveraged by Tesla's FSD (Supervised) suite and local knowledge of El Paso County's unique terrain.
            </p>
          </div>
        </div>

        {/* Block B: The Cabin */}
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <h3 className="text-3xl font-bold">Your Private Command Center.</h3>
            <p className="text-gray-400 leading-relaxed">
              Take control of your journey. Adjust rear seat heating, vent windows for fresh air, and track your route with "down to the inch" precision dashboard.
            </p>
            <Link href="/cabin" className="inline-flex items-center text-[var(--tesla-red)] hover:text-white transition-colors font-medium">
              Enter Cabin Dashboard &rarr;
            </Link>
          </div>
          <div className="relative h-[300px] rounded-3xl overflow-hidden border border-white/10 bg-gray-900 flex items-center justify-center group cursor-pointer">
            {/* Visual Representation of Dashboard */}
            <div className="text-center group-hover:scale-105 transition-transform duration-500">
              <div className="text-6xl mb-4">📱</div>
              <div className="text-sm font-mono text-gray-500">interactive.passenger.ui</div>
            </div>
          </div>
        </div>

        {/* Block C: Fairness */}
        <div className="bg-[#111] border border-white/10 rounded-3xl p-12 text-center">
          <h3 className="text-2xl font-bold mb-4">The SummitOS Fair Price Promise</h3>
          <div className="grid md:grid-cols-3 gap-8 mt-12">
            <div>
              <div className="text-4xl font-bold text-white mb-2">$15</div>
              <div className="text-sm text-gray-500 uppercase tracking-widest">Flat Base</div>
              <p className="text-xs text-gray-600 mt-2">First 5 Miles Included</p>
            </div>
            <div>
              <div className="text-4xl font-bold text-white mb-2">$1.75</div>
              <div className="text-sm text-gray-500 uppercase tracking-widest">Local Tier</div>
              <p className="text-xs text-gray-600 mt-2">Miles 5 - 20</p>
            </div>
            <div>
              <div className="text-4xl font-bold text-white mb-2">$1.25</div>
              <div className="text-sm text-gray-500 uppercase tracking-widest">Long Haul</div>
              <p className="text-xs text-gray-600 mt-2">Miles 20+</p>
            </div>
          </div>
        </div>
      </section>

      {/* 4. PRESERVED WIDGETS */}
      <section className="container mx-auto px-6 pb-20">
        <div className="flex flex-col md:flex-row gap-8 justify-center w-full opacity-60 hover:opacity-100 transition-opacity duration-500">
          <div className="flex-1 max-w-sm mx-auto md:mx-0">
            <WeatherWidget />
          </div>
          <div className="flex-1 max-w-sm mx-auto md:mx-0">
            <FlightTracker />
          </div>
        </div>
      </section>

      {/* 5. FOOTER */}
      <footer className="border-t border-white/10 bg-black py-12">
        <div className="container mx-auto px-6 text-center">
          <p className="text-sm text-gray-600 mb-4">
            &copy; {new Date().getFullYear()} COS Tesla LLC. All rights reserved.
          </p>
          <div className="flex justify-center gap-6 text-xs text-gray-500 font-mono">
            <Link href="#" className="hover:text-white transition-colors">PRIVACY</Link>
            <span>•</span>
            <Link href="#" className="hover:text-white transition-colors">TERMS</Link>
            <span>•</span>
            <Link href="#" className="hover:text-white transition-colors">CONTACT</Link>
          </div>
          <div className="mt-8 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10">
            <div className="w-2 h-2 rounded-full bg-[var(--tesla-red)]"></div>
            <span className="text-[10px] text-gray-400 font-bold tracking-widest uppercase">Powered by SummitOS</span>
          </div>
        </div>
      </footer>
    </main>
  );
}
