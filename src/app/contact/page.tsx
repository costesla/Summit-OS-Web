import { Phone, Mail, MapPin } from "lucide-react";

export default function ContactPage() {
    return (
        <main className="pt-24 min-h-screen container mx-auto px-6">
            <div className="max-w-2xl mx-auto glass-panel p-10 text-center">
                <h1 className="text-3xl font-bold mb-8">Get in Touch</h1>

                <div className="space-y-8">
                    <div className="flex flex-col items-center">
                        <div className="p-4 bg-white/5 rounded-full mb-4 text-[var(--color-primary)]">
                            <Phone size={32} />
                        </div>
                        <h3 className="text-xl font-bold">Phone</h3>
                        <p className="text-gray-400 mt-2">Call or Text anytime.</p>
                        <a href="tel:7194334851" className="text-xl font-bold mt-2 hover:text-[var(--color-primary)] transition-colors">
                            719.433.4851
                        </a>
                    </div>

                    <div className="flex flex-col items-center">
                        <div className="p-4 bg-white/5 rounded-full mb-4 text-[var(--color-primary)]">
                            <Mail size={32} />
                        </div>
                        <div className="flex flex-col items-center">
                            <h2 className="text-sm font-bold tracking-[0.3em] text-cyan-400 mb-2 uppercase">Official Support</h2>
                            <a href="mailto:peter.teehan@costesla.com" className="text-xl font-bold mt-2 hover:text-cyan-400 transition-colors">
                                peter.teehan@costesla.com
                            </a>
                        </div>
                    </div>

                    <div className="flex flex-col items-center">
                        <div className="p-4 bg-white/5 rounded-full mb-4 text-[var(--color-primary)]">
                            <MapPin size={32} />
                        </div>
                        <h3 className="text-xl font-bold">Service Area</h3>
                        <p className="text-gray-400 mt-2">
                            Based in Colorado Springs <br />
                            Serving El Paso County, DEN, and beyond.
                        </p>
                    </div>
                </div>
            </div>
        </main>
    );
}
