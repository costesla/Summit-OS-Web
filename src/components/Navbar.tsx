import Link from "next/link";
import { Car, Calendar, Phone } from "lucide-react";

export default function Navbar() {
    // Minimal Header
    return (
        <nav className="fixed w-full z-50 top-0 start-0 border-b border-white/5 bg-black/50 backdrop-blur-md">
            <div className="container mx-auto px-6 h-20 flex items-center justify-between">
                <Link href="/" className="flex items-center gap-3 group">
                    <div className="relative w-10 h-10 overflow-hidden rounded-xl border border-white/10 group-hover:border-cyan-500/50 transition-all">
                        <img src="/logo.png" alt="SummitOS" className="object-cover w-full h-full" />
                    </div>
                    <span className="text-xl font-bold tracking-tighter text-white group-hover:text-cyan-400 transition-colors">SUMMITOS</span>
                </Link>
                <Link href="/contact" className="text-sm uppercase tracking-widest text-gray-300 hover:text-white transition-colors">
                    Contact
                </Link>
            </div>
        </nav>
    );
}
