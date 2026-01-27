"use client";

import { Briefcase, Calendar, MapPin, Shield, Clock, Star } from "lucide-react";

export default function Services() {
    const services = [
        {
            icon: <Briefcase className="w-8 h-8 text-[var(--color-primary)] mb-4" />,
            title: "Business Travel",
            description: "Punctual, discreet, and professional transport for executives and corporate clients. Work on the go in a quiet, premium environment."
        },
        {
            icon: <Calendar className="w-8 h-8 text-[var(--color-primary)] mb-4" />,
            title: "Special Events",
            description: "Arrive in style at weddings, galas, and concerts. We handle the logistics so you can focus on the occasion."
        },
        {
            icon: <MapPin className="w-8 h-8 text-[var(--color-primary)] mb-4" />,
            title: "Airport Transfers",
            description: "Reliable pickup and dropoff at COS and DEN. Flight tracking ensures we are there exactly when you land."
        }
    ];

    return (
        <section id="services" className="py-24 bg-black/40 relative overflow-hidden">
            {/* Background Accent */}
            <div className="absolute top-0 right-0 w-1/3 h-full bg-[var(--color-primary)] opacity-[0.03] blur-3xl pointer-events-none"></div>

            <div className="container mx-auto px-6">
                <div className="text-center mb-16">
                    <h2 className="text-3xl md:text-4xl font-bold mb-4">Executive Standards</h2>
                    <div className="w-20 h-1 bg-[var(--color-primary)] mx-auto rounded-full"></div>
                    <p className="mt-4 text-gray-400 max-w-2xl mx-auto">
                        Experience the difference of a private driver who prioritizes safety, comfort, and reliability above all else.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    {services.map((s, i) => (
                        <div key={i} className="glass-panel p-8 hover:bg-white/5 transition-colors group">
                            <div className="p-3 bg-white/5 w-fit rounded-lg mb-4 group-hover:scale-110 transition-transform duration-300">
                                {s.icon}
                            </div>
                            <h3 className="text-xl font-bold mb-3 text-white">{s.title}</h3>
                            <p className="text-gray-400 text-sm leading-relaxed">{s.description}</p>
                        </div>
                    ))}
                </div>

                {/* Trust Indicators */}
                <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-8 text-center border-t border-white/5 pt-12">
                    <div className="flex flex-col items-center">
                        <Shield className="w-6 h-6 text-gray-500 mb-2" />
                        <span className="text-sm font-medium tracking-wider text-gray-300">SAFETY FIRST</span>
                    </div>
                    <div className="flex flex-col items-center">
                        <Clock className="w-6 h-6 text-gray-500 mb-2" />
                        <span className="text-sm font-medium tracking-wider text-gray-300">ALWAYS ON TIME</span>
                    </div>
                    <div className="flex flex-col items-center">
                        <Star className="w-6 h-6 text-gray-500 mb-2" />
                        <span className="text-sm font-medium tracking-wider text-gray-300">PREMIUM COMFORT</span>
                    </div>
                </div>
            </div>
        </section>
    );
}
