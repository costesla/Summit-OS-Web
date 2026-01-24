import nodemailer from 'nodemailer';
import path from 'path';

interface ReceiptData {
  customerName: string;
  customerEmail: string;
  pickup: string;
  dropoff: string;
  date: string;
  distance: string; // e.g. "12.5 miles"
  duration: string; // e.g. "25 mins"
  priceCheckdown: {
    base: string; // "$15.00"
    mileage: string; // "$2.50"
    wait: string; // "$0.00"
    total: string; // "$17.50"
  };
  bookingId: string;
}

export const generateReceiptHtml = (data: ReceiptData) => {
  return `
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: 'Arial', sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }
    .container { max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .header { background-color: #000000; color: #ffffff; padding: 30px 20px; text-align: center; }
    .header img { max-width: 150px; height: auto; margin-bottom: 10px; }
    .header p { margin: 5px 0 0; color: #aaaaaa; font-size: 12px; text-transform: uppercase; }
    .content { padding: 30px; color: #333333; }
    .trip-summary { margin-bottom: 25px; border-bottom: 1px solid #eeeeee; padding-bottom: 20px; }
    .row { display: flex; justify-content: space-between; margin-bottom: 10px; }
    .label { color: #666666; font-size: 14px; }
    .value { font-weight: 600; font-size: 14px; text-align: right; }
    .total-row { display: flex; justify-content: space-between; margin-top: 20px; padding-top: 15px; border-top: 2px solid #000000; font-size: 18px; font-weight: bold; }
    .footer { background-color: #eeeeee; padding: 20px; text-align: center; font-size: 12px; color: #888888; }
    .btn { display: inline-block; background-color: #D12630; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 4px; margin-top: 20px; font-size: 14px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <img src="cid:logo" alt="SummitOS" />
      <p>Official Trip Receipt</p>
    </div>
    <div class="content">
      <p>Hello ${data.customerName},</p>
      <p>Thank you for choosing SummitOS. Here is the receipt for your upcoming trip.</p>
      
      <div class="trip-summary">
        <div class="row">
            <span class="label">Date</span>
            <span class="value">${data.date}</span>
        </div>
        <div class="row">
            <span class="label">Booking ID</span>
            <span class="value">#${data.bookingId}</span>
        </div>
        <hr style="border: 0; border-top: 1px dashed #ddd; margin: 15px 0;" />
        <div class="row">
            <span class="label">Pickup</span>
            <span class="value" style="max-width: 60%;">${data.pickup}</span>
        </div>
        <div class="row">
            <span class="label">Dropoff</span>
            <span class="value" style="max-width: 60%;">${data.dropoff}</span>
        </div>
      </div>

      <div class="pricing">
        <div class="row">
            <span class="label">Distance (${data.distance})</span>
            <span class="value">${data.priceCheckdown.mileage}</span>
        </div>
        <div class="row">
            <span class="label">Base Fare</span>
            <span class="value">${data.priceCheckdown.base}</span>
        </div>
         <div class="row">
            <span class="label">Wait Time / Extras</span>
            <span class="value">${data.priceCheckdown.wait}</span>
        </div>
        <div class="total-row">
            <span>TOTAL</span>
            <span>${data.priceCheckdown.total}</span>
        </div>
      </div>

      <div style="text-align: center;">
        <a href="https://costesla.com" class="btn">Book Another Trip</a>
      </div>
    </div>
    <div class="footer">
      <p>SummitOS - Driven by Precision</p>
      <p>Colorado Springs, CO</p>
    </div>
  </div>
</body>
</html>
  `;
};

export const sendReceiptEmail = async (data: ReceiptData) => {
  const transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST || "smtp.office365.com",
    port: parseInt(process.env.SMTP_PORT || "587"),
    secure: false, // true for 465, false for other ports
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
    tls: {
      ciphers: "SSLv3",
      rejectUnauthorized: false
    }
  });

  const html = generateReceiptHtml(data);

  try {
    const info = await transporter.sendMail({
      from: `"SummitOS Reservations" <${process.env.SMTP_USER}>`,
      to: data.customerEmail,
      subject: `Trip Receipt: ${data.date} - ${data.priceCheckdown.total}`,
      html: html,
      attachments: [{
        filename: 'logo.png',
        path: path.join(process.cwd(), 'public', 'logo.png'),
        cid: 'logo' // same cid value as in the html img src
      }]
    });
    console.log("Customer Receipt sent: %s", info.messageId);
    return { success: true, id: info.messageId };
  } catch (error) {
    console.error("Error sending customer email:", error);
    return { success: false, error };
  }
};

export const sendAdminNotification = async (data: ReceiptData) => {
  const transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST || "smtp.office365.com",
    port: parseInt(process.env.SMTP_PORT || "587"),
    secure: false,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
    tls: {
      ciphers: "SSLv3",
      rejectUnauthorized: false
    }
  });

  const html = `
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-top: 5px solid #D12630;">
      <div style="padding: 20px;">
        <h2 style="color: #D12630; margin-top: 0;">🚗 New Trip Request</h2>
        <p><strong>Passenger:</strong> ${data.customerName}</p>
        <p><strong>Email:</strong> ${data.customerEmail}</p>
        
        <div style="background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0;">
          <p style="margin: 5px 0;"><strong>📍 Pickup:</strong> ${data.pickup}</p>
          <p style="margin: 5px 0;"><strong>🏁 Dropoff:</strong> ${data.dropoff}</p>
        </div>

        <div style="display: flex; gap: 20px; font-weight: bold; color: #555;">
          <span>💰 Quote: ${data.priceCheckdown.total}</span>
          <span>🛣️ Distance: ${data.distance}</span>
          <span>⏱️ Time: ${data.duration}</span>
        </div>
        
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #999;">System: SummitOS | Provider: Outlook SMTP</p>
      </div>
    </div>
  `;

  try {
    // Send to Self (Admin)
    const info = await transporter.sendMail({
      from: `"SummitOS System" <${process.env.SMTP_USER}>`,
      to: process.env.SMTP_USER,
      subject: `🚗 New Reservation: ${data.customerName} - ${data.priceCheckdown.total}`,
      html: html,
    });
    console.log("Admin Notification sent: %s", info.messageId);
    return { success: true, id: info.messageId };
  } catch (error) {
    console.error("Error sending admin email:", error);
    return { success: false, error };
  }
};
