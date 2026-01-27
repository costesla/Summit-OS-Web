"use client";

import { useState } from "react";
import styles from "../../components/BookingForm.module.css"; // Reusing form styles

export default function ReceiptPage() {
    const [formData, setFormData] = useState({
        name: "",
        email: "",
        date: new Date().toISOString().split('T')[0], // Default to today
        miles: "",
        price: "",
        paymentMethod: "Venmo",
        pickup: "",
        dropoff: ""
    });

    const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setStatus("loading");

        try {
            const res = await fetch("/api/receipt", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(formData),
            });

            if (res.ok) {
                setStatus("success");
                // Reset form slightly but keep date? No, reset all for next ride.
                setFormData({
                    name: "", email: "", date: new Date().toISOString().split('T')[0],
                    miles: "", price: "", paymentMethod: "Venmo", pickup: "", dropoff: ""
                });
            } else {
                setStatus("error");
            }
        } catch (error) {
            console.error(error);
            setStatus("error");
        }
    };

    return (
        <div className="min-h-screen pt-24 px-4 pb-12 flex justify-center items-center">
            <div className={`glass-panel ${styles.container} max-w-lg w-full`}>
                <h1 className="text-2xl font-bold text-white mb-6 text-center">🧾 Receipt Generator</h1>

                <form onSubmit={handleSubmit} className={styles.form}>
                    <div className={styles.group}>
                        <label>Customer Name</label>
                        <input required name="name" value={formData.name} onChange={handleChange} placeholder="Passenger Name" />
                    </div>

                    <div className={styles.group}>
                        <label>Customer Email</label>
                        <input required type="email" name="email" value={formData.email} onChange={handleChange} placeholder="passenger@email.com" />
                    </div>

                    <div className={styles.row}>
                        <div className={styles.group}>
                            <label>Date</label>
                            <input required type="date" name="date" value={formData.date} onChange={handleChange} />
                        </div>
                        <div className={styles.group}>
                            <label>Miles</label>
                            <input required type="number" step="0.1" name="miles" value={formData.miles} onChange={handleChange} placeholder="12.5" />
                        </div>
                    </div>

                    <div className={styles.row}>
                        <div className={styles.group}>
                            <label>Total Price ($)</label>
                            <input required type="number" step="0.01" name="price" value={formData.price} onChange={handleChange} placeholder="45.00" />
                        </div>
                        <div className={styles.group}>
                            <label>Payment Method</label>
                            <select name="paymentMethod" value={formData.paymentMethod} onChange={handleChange}>
                                <option value="Venmo">Venmo</option>
                                <option value="Zelle">Zelle</option>
                                <option value="Cash">Cash</option>
                                <option value="Card">Card</option>
                            </select>
                        </div>
                    </div>

                    {/* Location Section with PII Note */}
                    <div className="mt-4 mb-2 p-3 bg-blue-900/20 border border-blue-500/30 rounded text-xs text-blue-200">
                        <strong>Privacy Rule:</strong> For residences, enter <u>Street Name Only</u> (e.g. "Prairie Rd"). Do not enter house numbers.
                    </div>

                    <div className={styles.group}>
                        <label>Pickup Location</label>
                        <input required name="pickup" value={formData.pickup} onChange={handleChange} placeholder="e.g. Amazon Fulfullment OR Prairie Rd" />
                    </div>

                    <div className={styles.group}>
                        <label>Dropoff Location</label>
                        <input required name="dropoff" value={formData.dropoff} onChange={handleChange} placeholder="e.g. DEN Airport" />
                    </div>

                    <button
                        type="submit"
                        disabled={status === "loading"}
                        className={`btn-primary ${styles.submitBtn} mt-6`}
                    >
                        {status === "loading" ? "Sending..." : "Send Receipt"}
                    </button>

                    {status === "success" && <p className="text-green-400 text-center mt-4">Receipt Sent Successfully! ✅</p>}
                    {status === "error" && <p className="text-red-400 text-center mt-4">Failed to send.</p>}
                </form>
            </div>
        </div>
    );
}
