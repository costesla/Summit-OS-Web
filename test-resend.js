const { Resend } = require('resend');

async function main() {
    const key = "re_gMmoBq8w_NrKkB97vvA1zx7RQN41nzS83";
    console.log("Testing Resend API Key:", key.substring(0, 5) + "...");

    const resend = new Resend(key);

    try {
        console.log("sending...");
        // Sending from the default 'onboarding' domain to verify API Key validity FIRST.
        // If this works, the key is solid.
        // We send to the user's new email to valid receipt.
        const { data, error } = await resend.emails.send({
            from: 'onboarding@resend.dev',
            to: 'PrivateTrips@costesla.com',
            subject: 'SummitOS Resend Verification',
            html: '<p>Transformation Complete: Resend API is active.</p>'
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
