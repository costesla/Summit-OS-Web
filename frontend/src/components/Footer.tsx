export default function Footer() {
    return (
        <footer className="border-t border-white/5 bg-black/80 py-12">
            <div className="container mx-auto px-6 text-center">
                <div className="mb-8">
                    <div className="flex justify-center mb-4">
                        <img src="/logo.png" alt="SummitOS" className="w-12 h-12 rounded-xl" />
                    </div>
                    <h4 className="font-bold text-lg mb-2 text-white italic tracking-tighter">SUMMITOS</h4>
                    <p className="text-gray-500 text-sm">The Executive Standard for Transport.</p>
                </div>

                <div className="flex justify-center gap-8 text-sm text-gray-400 mb-8">
                    <span className="hover:text-white cursor-pointer transition-colors">Privacy Policy</span>
                    <span className="hover:text-white cursor-pointer transition-colors">Terms of Service</span>
                </div>

                <div className="pt-8 border-t border-white/5 text-gray-600 text-xs">
                    © {new Date().getFullYear()} SummitOS LLC. All rights reserved.
                </div>
            </div>
        </footer>
    );
}
