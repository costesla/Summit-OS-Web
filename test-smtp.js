const nodemailer = require('nodemailer');
const path = require('path');

// Load env using dotenv
// Try to load dotenv, fallback to manual if missing (though it is in package.json)
try {
    require('dotenv').config({ path: path.resolve(__dirname, '.env.test') });
} catch (e) {
    console.error("Failed to load dotenv:", e.message);
}

async function main() {
    console.log("Testing SMTP Connection...");
    console.log("Host:", process.env.SMTP_HOST);
    console.log("User:", process.env.SMTP_USER);

    if (!process.env.SMTP_HOST || !process.env.SMTP_USER || !process.env.SMTP_PASS) {
        console.error("❌ ERROR: Missing SMTP Environment Variables.");
        console.log("Current Env Keys:", Object.keys(process.env).filter(k => k.startsWith('SMTP')));
        return;
    }

    const transporter = nodemailer.createTransport({
        host: process.env.SMTP_HOST,
        port: parseInt(process.env.SMTP_PORT || '587'),
        secure: false,
        auth: {
            user: process.env.SMTP_USER,
            pass: process.env.SMTP_PASS,
        },
        tls: { ciphers: "SSLv3", rejectUnauthorized: false }
    });

    try {
        await transporter.verify();
        console.log("✅ SMTP Connection Successful! Credentials are valid.");

        // Send test
        const info = await transporter.sendMail({
            from: process.env.SMTP_USER,
            to: process.env.SMTP_USER,
            subject: "SummitOS SMTP Verification",
            html: "<h3>Success!</h3><p>The automated receipt system is configured correctly.</p>"
        });
        console.log("✅ Test Email Sent! ID:", info.messageId);
        console.log("Please check your inbox (and spam folder) for 'SummitOS SMTP Verification'.");
    } catch (error) {
        console.error("❌ SMTP Error:", error);
    }
}

main();
