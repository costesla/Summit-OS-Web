import BookingForm from "@/components/BookingForm";

export default function BookPage() {
    return (
        <main className="pt-24 min-h-screen container mx-auto px-6">
            <div className="text-center mb-12">
                <h1 className="text-3xl font-bold mb-2">Reserve Your Ride</h1>
                <p className="text-gray-400">Simple pricing. Instant confirmation.</p>
            </div>
            <BookingForm />
        </main>
    );
}
