import Link from "next/link";

export default function Footer() {
    return (
        <footer className="border-t border-white/5 bg-black/80 py-12">
            <div className="container mx-auto px-6 text-center">
                <div className="mb-8">
                    <div className="flex justify-center mb-4">
                        <img src="/logo.png" alt="COS Tesla" className="w-12 h-12 rounded-xl" />
                    </div>
                    <h4 className="font-bold text-lg text-white italic tracking-tighter">COS TESLA</h4>
                    <span className="block text-[0.6rem] text-gray-500 font-mono tracking-widest uppercase mb-2">Powered by SummitOS</span>
                    <p className="text-gray-500 text-sm">The Executive Standard for Transport.</p>
                </div>

                <div className="flex justify-center gap-8 text-sm text-gray-400 mb-8">
                    <Link href="/privacy/" className="hover:text-white cursor-pointer transition-colors">Privacy Policy</Link>
                    <Link href="/terms/" className="hover:text-white cursor-pointer transition-colors">Terms of Service</Link>
                </div>

                <div className="pt-8 border-t border-white/5 text-gray-600 text-xs flex flex-col items-center gap-1">
                    <span>© {new Date().getFullYear()} COS Tesla LLC. All rights reserved.</span>
                    <span className="font-mono opacity-80">CO PUC 0250</span>
                </div>
            </div>
        </footer>
    );
}
