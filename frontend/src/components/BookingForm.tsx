"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import styles from "./BookingForm.module.css";
import { calculateDistance, getCoordinates } from "../utils/distance";

export default function BookingForm() {
    const [formData, setFormData] = useState({
        pickup: "",
        dropoff: "",
        name: "",
        email: "",
        phone: "",
        passengers: "1",
        notes: ""
    });

    const [priceQuote, setPriceQuote] = useState<string | null>(null);
    const [isCalculating, setIsCalculating] = useState(false);
    const [tripDetails, setTripDetails] = useState<{ dist: string, time: string } | null>(null);
    const [bookingStep, setBookingStep] = useState<'quote' | 'details' | 'handoff'>('quote');
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const [coords, setCoords] = useState<{ pickup: { lat: number, lon: number } | null, dropoff: { lat: number, lon: number } | null }>({ pickup: null, dropoff: null });

    // Calculate price when pickup or dropoff changes
    useEffect(() => {
        const calculatePrice = async () => {
            if (!formData.pickup || !formData.dropoff) {
                setPriceQuote(null);
                setBookingStep('quote'); // Reset if they clear inputs
                return;
            }

            setIsCalculating(true);
            const pickupCoords = await getCoordinates(formData.pickup);
            const dropoffCoords = await getCoordinates(formData.dropoff);

            setCoords({ pickup: pickupCoords, dropoff: dropoffCoords });

            if (pickupCoords && dropoffCoords) {
                const straightDist = calculateDistance(pickupCoords.lat, pickupCoords.lon, dropoffCoords.lat, dropoffCoords.lon);
                const drivingDist = straightDist * 1.3;
                const estTime = Math.round(drivingDist * 2.5);

                setTripDetails({
                    dist: drivingDist.toFixed(1),
                    time: estTime.toString()
                });

                if (straightDist < 2) setPriceQuote("$10.00");
                else if (straightDist < 5) setPriceQuote("$15.00");
                else if (straightDist < 25) setPriceQuote("$20.00");
                else setPriceQuote("Call for Quote");
            }
            setIsCalculating(false);
        };

        const timeoutId = setTimeout(calculatePrice, 800);
        return () => clearTimeout(timeoutId);
    }, [formData.pickup, formData.dropoff]);

    const handleContinueToDetails = () => {
        if (priceQuote) setBookingStep('details');
    };

    const [bookingId, setBookingId] = useState<string | null>(null);
    const [showZelle, setShowZelle] = useState(false);

    const handleSubmitDetails = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsSubmitting(true);

        try {
            // Send data to our API
            const res = await fetch('/api/book', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...formData,
                    price: priceQuote,
                    tripDetails
                })
            });
            const data = await res.json();
            if (data.success && data.bookingId) {
                setBookingId(data.bookingId);
            }
            setBookingStep('handoff');
        } catch (err) {
            alert("Something went wrong. Please try again.");
        } finally {
            setIsSubmitting(false);
        }
    };

    const handlePaymentSelection = async (method: string) => {
        if (!bookingId) return;

        // Send to backend
        try {
            await fetch('/api/book/payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bookingId,
                    paymentMethod: method,
                    email: formData.email,
                    name: formData.name,
                    amount: priceQuote
                })
            });

            if (method === 'Cash') {
                alert("Thank you! Please check your email for the confirmation link.");
            }
        } catch (e) {
            console.error("Failed to log payment method", e);
        }
    };

    const RouteMap = dynamic(() => import("./RouteMap"), { ssr: false, loading: () => <div className="h-[450px] w-full bg-white/5 animate-pulse rounded-xl mt-6"></div> });

    return (
        <div className={`glass-panel ${styles.container}`}>
            <h3 className={styles.title}>
                {bookingStep === 'quote' && "1. Get a Quote"}
                {bookingStep === 'details' && "2. Passenger Details"}
                {bookingStep === 'handoff' && "3. Select Time"}
            </h3>

            {(bookingStep === 'quote' || bookingStep === 'details') && (
                <div className={styles.form}>
                    <div className={styles.row}>
                        <div className={styles.group}>
                            <label htmlFor="pickup">Pickup Location</label>
                            <input required type="text" id="pickup" name="pickup" value={formData.pickup} onChange={handleChange} placeholder="123 Main St" disabled={bookingStep === 'details'} />
                        </div>
                        <div className={styles.group}>
                            <label htmlFor="dropoff">Dropoff Location</label>
                            <input required type="text" id="dropoff" name="dropoff" value={formData.dropoff} onChange={handleChange} placeholder="DEN Airport" disabled={bookingStep === 'details'} />
                        </div>
                    </div>

                    {/* Pricing Display */}
                    <div style={{
                        padding: '1rem',
                        background: 'rgba(6, 182, 212, 0.1)',
                        borderRadius: '8px',
                        textAlign: 'center',
                        border: '1px solid rgba(6, 182, 212, 0.3)',
                        marginTop: '1rem',
                        transition: 'all 0.3s ease'
                    }}>
                        <small style={{ textTransform: 'uppercase', letterSpacing: '1px', color: '#06b6d4' }}>Estimated Price</small>
                        <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#06b6d4' }}>
                            {isCalculating ? "Calculating..." : (priceQuote || "Enter locations")}
                        </div>
                        {tripDetails && !isCalculating && priceQuote && (
                            <div className="text-sm text-gray-300 mt-1 pb-1 border-t border-white/10 pt-2 flex justify-center gap-4">
                                <span>🚗 ~{tripDetails.dist} mi</span>
                                <span>⏱️ ~{tripDetails.time} mins</span>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Step 1 Button */}
            {bookingStep === 'quote' && priceQuote && !isCalculating && (
                <button
                    onClick={handleContinueToDetails}
                    className="mt-6 w-full bg-white text-black font-bold py-3 rounded-lg hover:bg-gray-200 transition-colors"
                >
                    Continue to Booking →
                </button>
            )}

            {/* Step 2: Details Form */}
            {bookingStep === 'details' && (
                <form onSubmit={handleSubmitDetails} className="mt-6 animate-in slide-in-from-bottom-4 fade-in duration-500">
                    <div className="space-y-4">
                        <div className={styles.group}>
                            <label>Name</label>
                            <input required type="text" name="name" value={formData.name} onChange={handleChange} placeholder="John Doe" className="w-full p-3 rounded bg-white/10 border border-white/20 text-white" />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className={styles.group}>
                                <label>Email</label>
                                <input required type="email" name="email" value={formData.email} onChange={handleChange} placeholder="john@example.com" className="w-full p-3 rounded bg-white/10 border border-white/20 text-white" />
                            </div>
                            <div className={styles.group}>
                                <label>Phone</label>
                                <input required type="tel" name="phone" value={formData.phone} onChange={handleChange} placeholder="(555) 123-4567" className="w-full p-3 rounded bg-white/10 border border-white/20 text-white" />
                            </div>
                        </div>
                        <div className={styles.group}>
                            <label>Passengers</label>
                            <select name="passengers" value={formData.passengers} onChange={handleChange} className="w-full p-3 rounded bg-white/10 border border-white/20 text-white">
                                <option value="1">1 Passenger</option>
                                <option value="2">2 Passengers</option>
                                <option value="3">3 Passengers</option>
                                <option value="4">4 Passengers</option>
                            </select>
                        </div>
                    </div>

                    <div className="flex gap-3 mt-6">
                        <button type="button" onClick={() => setBookingStep('quote')} className="flex-1 bg-transparent border border-white/30 text-white py-3 rounded-lg hover:bg-white/10">
                            ← Back
                        </button>
                        <button type="submit" disabled={isSubmitting} className="flex-[2] bg-cyan-600 text-white font-bold py-3 rounded-lg hover:bg-cyan-700 shadow-lg shadow-cyan-500/20">
                            {isSubmitting ? "Saving..." : "Confirm & Select Time"}
                        </button>
                    </div>
                </form>
            )}

            {/* Step 3: Handoff to Bookings */}
            {bookingStep === 'handoff' && (
                <div className="mt-8 mb-2 p-6 bg-green-500/10 rounded-xl border border-green-500/30 text-center animate-in zoom-in-95 duration-300 relative">
                    <div className="text-4xl mb-2">✅</div>
                    <h4 className="text-xl font-bold text-white mb-2">Details Received!</h4>
                    <p className="text-sm text-gray-300 mb-6">We have your trip info. Now simply choose your time slot.</p>

                    <a
                        href="https://outlook.office.com/book/SummitOS@costesla.com/?ismsaljsauthenabled"
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center justify-center gap-2 bg-cyan-600 text-white px-6 py-4 rounded-lg font-bold hover:bg-cyan-700 transition-colors w-full text-lg shadow-lg hover:shadow-cyan-500/20 mb-6"
                    >
                        📅 Select Time Slot
                    </a>

                    <div className="border-t border-white/10 pt-4">
                        <p className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wider">Payment Options</p>
                        <div className="grid grid-cols-3 gap-3">
                            <a
                                href="https://www.venmo.com/u/costesla"
                                target="_blank"
                                rel="noreferrer"
                                onClick={() => handlePaymentSelection('Venmo')}
                                className="bg-[#008CFF] text-white py-3 px-2 rounded-lg font-bold hover:bg-[#0074D4] transition-colors flex items-center justify-center gap-1 text-sm"
                            >
                                Venmo
                            </a>
                            <button
                                onClick={() => {
                                    handlePaymentSelection('Zelle');
                                    setShowZelle(true);
                                }}
                                className="bg-[#6d1ed4] text-white py-3 px-2 rounded-lg font-bold hover:bg-[#5b19b0] transition-colors flex items-center justify-center gap-1 text-sm"
                            >
                                Zelle
                            </button>
                            <button
                                onClick={() => handlePaymentSelection('Cash')}
                                className="bg-emerald-600 text-white py-3 px-2 rounded-lg font-bold hover:bg-emerald-700 transition-colors flex items-center justify-center gap-1 text-sm"
                            >
                                Cash
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Zelle Modal */}
            {showZelle && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 transition-opacity duration-300" onClick={() => setShowZelle(false)}>
                    <div className="bg-white text-black p-6 rounded-2xl max-w-sm w-full text-center shadow-2xl scale-100 transform transition-transform" onClick={e => e.stopPropagation()}>
                        <h3 className="text-xl font-bold mb-2 text-[#6d1ed4]">Scan to Pay via Zelle</h3>
                        <p className="text-sm text-gray-600 mb-4">COS TESLA LLC</p>

                        <div className="bg-gray-100 p-4 rounded-xl mb-4 inline-block">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src="/assets/zelle-qr.png" alt="Zelle QR Code" className="w-56 h-56 object-contain" />
                        </div>

                        <p className="text-xs text-gray-500 mb-6">Or use: <b>p...n@costesla.com</b></p>

                        <button
                            onClick={() => setShowZelle(false)}
                            className="w-full bg-gray-200 text-gray-800 font-bold py-3 rounded-lg hover:bg-gray-300 transition-colors"
                        >
                            Close
                        </button>
                    </div>
                </div>
            )}

            {/* Map Display (Always show if coords exist) */}
            {coords.pickup && coords.dropoff && (
                <div className="mt-8">
                    <RouteMap pickup={coords.pickup} dropoff={coords.dropoff} />
                </div>
            )}
        </div>
    );
}
