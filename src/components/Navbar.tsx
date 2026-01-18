import Link from "next/link";
import { Car, Calendar, Phone } from "lucide-react";

export default function Navbar() {
    // Minimal Header
    return (
        <nav className="fixed w-full z-50 top-0 start-0 border-b border-white/5 bg-black/50 backdrop-blur-md">
            <div className="container mx-auto px-6 h-20 flex items-center justify-center">
                <Link href="/contact" className="text-sm uppercase tracking-widest text-gray-300 hover:text-white transition-colors">
                    Contact
                </Link>
            </div>
        </nav>
    );
}
