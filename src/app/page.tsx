"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import WeatherWidget from "../components/WeatherWidget";
import FlightTracker from "../components/FlightTracker";

// NEW SummitOS Engine
import BookingEngine from "../components/BookingEngine";

const LiveMap = dynamic(() => import("../components/LiveMap"), {
  ssr: false,
  loading: () => <div className="h-[350px] flex items-center justify-center text-blue-400 text-sm">Connecting to Tesla GPS...</div>
});

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden py-20">
        {/* Abstract Background */}
        <div className="absolute inset-0 z-0">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/80 to-[var(--background)]"></div>
        </div>

        <div className="container mx-auto px-6 relative z-10 pt-20">


          <div className="text-center max-w-4xl mx-auto mt-20 lg:mt-0">
            <h1 className="title-animate text-5xl md:text-7xl font-bold mb-6 tracking-tight">
              COS TESLA
            </h1>
            <p className="text-xl md:text-2xl text-gray-300 mb-8 font-light tracking-wide">
              Make the Night Unforgettable
            </p>

            {/* SummitOS Booking Engine */}
            <div className="w-full mt-10 animate-in fade-in zoom-in duration-700">
              <BookingEngine />
            </div>

            {/* Top Spacing */}
            <div className="h-12 hidden lg:block"></div>

            {/* Mobile Only Tracker - NOW UNIVERSAL */}
            <div className="w-full max-w-sm mx-auto mt-12 mb-8 opacity-90 hover:opacity-100 transition-opacity group cursor-pointer relative">
              <Link href="/track">
                <LiveMap className="h-[200px] rounded-2xl overflow-hidden shadow-2xl border border-white/10 group-hover:border-cyan-500/50 transition-colors" />

                {/* Hover Overlay Hint */}
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl z-[1000]">
                  <span className="text-white font-medium text-xs tracking-widest border border-white/20 bg-black/50 px-3 py-1 rounded-full backdrop-blur-md">
                    CLICK TO EXPAND
                  </span>
                </div>

                <div className="text-[10px] text-gray-500 mt-2 flex justify-center items-center gap-2 bg-black/50 p-1 rounded-full backdrop-blur-sm border border-white/5">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                  </span>
                  TESLA GPS • LIVE
                </div>
              </Link>
            </div>
          </div>

          {/* Widgets Row moved down and with transition */}
          <div className="mt-16 flex flex-col md:flex-row gap-8 justify-center items-stretch w-full opacity-80 hover:opacity-100 transition-opacity">
            <div className="flex-1 max-w-sm w-full mx-auto md:mx-0">
              <WeatherWidget />
            </div>
            <div className="flex-1 max-w-sm w-full mx-auto md:mx-0">
              <FlightTracker />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
