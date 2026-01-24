const { Resend } = require('resend');

async function main() {
    const key = "re_gMmoBq8w_NrKkB97vvA1zx7RQN41nzS83";
    // ^ Using the key from valid .env.local

    const resend = new Resend(key);

    try {
        console.log("Attempting to send via Resend FROM Custom Domain...");

        const { data, error } = await resend.emails.send({
            from: 'SummitOS <PrivateTrips@costesla.com>', // Unverified domain? We'll see.
            to: 'PrivateTrips@costesla.com', // Sending to self
            subject: 'SummitOS Resend Verification (Custom Domain)',
            html: '<p>Transformation Complete: Resend API IS working.</p>'
        });

        if (error) {
            console.error("❌ Resend Error:", error);
        } else {
            console.log("✅ Success! Email Sent via Resend.");
            console.log("ID:", data.id);
        }
    } catch (e) {
        console.error("❌ Exception:", e);
    }
}

main();
