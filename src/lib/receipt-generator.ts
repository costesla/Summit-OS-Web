/**
 * Receipt HTML and Text Generator for COS Tesla LLC
 * Generates business-grade passenger receipts with full addresses
 */

import { ReceiptInput } from '@/types/receipt-types';

interface ReceiptTemplateData {
    input: ReceiptInput;
    hasPhoto: boolean;
    photoAttribution?: string;
}

/**
 * Generate HTML email body for receipt
 * Mobile-first, inline CSS, table-based layout for Outlook compatibility
 */
export function generateReceiptHTML(data: ReceiptTemplateData): string {
    const { input, hasPhoto, photoAttribution } = data;
    const { TripData, FareData, PaymentData, PassengerData } = input;

    const greeting = PassengerData.firstName
        ? `Hi ${PassengerData.firstName},`
        : 'Hello,';

    const paymentLine = PaymentData.Last4
        ? `${PaymentData.Method} ending in ${PaymentData.Last4}`
        : PaymentData.Method;

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Private Trip Receipt</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f4f4;">
    <tr>
      <td align="center" style="padding:20px 10px;">
        
        <!-- Main Container -->
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
          
          <!-- Header -->
          <tr>
            <td style="background-color:#000000;color:#ffffff;padding:30px 20px;text-align:center;">
              <h1 style="margin:0;font-size:24px;font-weight:bold;">COS Tesla LLC</h1>
              <p style="margin:5px 0 0;color:#aaaaaa;font-size:14px;text-transform:uppercase;letter-spacing:1px;">Private Trip Receipt</p>
            </td>
          </tr>

          <!-- Content -->
          <tr>
            <td style="padding:30px 20px;">
              
              <!-- Greeting -->
              <p style="margin:0 0 20px;font-size:16px;color:#333333;">${greeting}</p>
              <p style="margin:0 0 25px;font-size:14px;color:#666666;line-height:1.5;">Here is your official receipt for your private trip. This document is suitable for tax deductions and business reimbursement.</p>

              ${hasPhoto ? `
              <!-- Contextual Photo -->
              <div style="margin:0 0 10px;">
                <img src="cid:place_photo_1" alt="Area photo" style="display:block;border:0;max-width:100%;height:auto;border-radius:4px;">
              </div>
              <p style="margin:0 0 25px;font-size:11px;color:#999999;">Photo © Google — ${photoAttribution || 'Google'}</p>
              ` : ''}

              <!-- Trip Summary -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 25px;border-bottom:1px solid #eeeeee;padding-bottom:20px;">
                <tr>
                  <td colspan="2" style="padding:0 0 15px;font-size:18px;font-weight:bold;color:#000000;">Trip Summary</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Trip ID</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;font-weight:600;">${TripData.Id}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Date</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;font-weight:600;">${TripData.DateLocal}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Time</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;font-weight:600;">${TripData.StartTimeLocal} – ${TripData.EndTimeLocal}</td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:15px 0 6px;font-size:14px;color:#666666;">Pickup Address</td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:0 0 6px;font-size:14px;color:#333333;font-weight:600;">${TripData.PickupAddress}</td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:15px 0 6px;font-size:14px;color:#666666;">Dropoff Address</td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:0 0 6px;font-size:14px;color:#333333;font-weight:600;">${TripData.DropoffAddress}</td>
                </tr>
                <tr>
                  <td style="padding:15px 0 6px;font-size:14px;color:#666666;">Distance</td>
                  <td style="padding:15px 0 6px;font-size:14px;color:#333333;text-align:right;font-weight:600;">${TripData.Distance.mi} mi</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Duration</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;font-weight:600;">${TripData.Duration.min} min</td>
                </tr>
              </table>

              <!-- Fare Breakdown -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 25px;">
                <tr>
                  <td colspan="2" style="padding:0 0 15px;font-size:18px;font-weight:bold;color:#000000;">Fare Breakdown</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Base Fare</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;">$${FareData.Base}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Time &amp; Distance</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;">$${FareData.TimeDistance}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Extras (Tolls/Parking)</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;">$${FareData.Extras}</td>
                </tr>
                ${FareData.Discount !== '0.00' ? `
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Discount</td>
                  <td style="padding:6px 0;font-size:14px;color:#00aa00;text-align:right;">-$${FareData.Discount}</td>
                </tr>
                ` : ''}
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Subtotal</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;">$${FareData.Subtotal}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Tax</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;">$${FareData.Tax}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Tip</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;">$${FareData.Tip}</td>
                </tr>
                <tr>
                  <td style="padding:20px 0 0;font-size:18px;font-weight:bold;color:#000000;border-top:2px solid #000000;">Total</td>
                  <td style="padding:20px 0 0;font-size:18px;font-weight:bold;color:#000000;text-align:right;border-top:2px solid #000000;">$${FareData.Total}</td>
                </tr>
              </table>

              <!-- Payment Details -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 25px;border-bottom:1px solid #eeeeee;padding-bottom:20px;">
                <tr>
                  <td colspan="2" style="padding:0 0 15px;font-size:18px;font-weight:bold;color:#000000;">Payment</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Payment Method</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;font-weight:600;">${paymentLine}</td>
                </tr>
                <tr>
                  <td style="padding:6px 0;font-size:14px;color:#666666;">Authorization</td>
                  <td style="padding:6px 0;font-size:14px;color:#333333;text-align:right;font-weight:600;">${PaymentData.AuthCode}</td>
                </tr>
              </table>

              ${TripData.Notes ? `
              <!-- Notes -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 25px;">
                <tr>
                  <td style="padding:0 0 10px;font-size:16px;font-weight:bold;color:#000000;">Notes</td>
                </tr>
                <tr>
                  <td style="padding:0;font-size:14px;color:#666666;line-height:1.5;">${TripData.Notes}</td>
                </tr>
              </table>
              ` : ''}

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color:#f5f5f5;padding:25px 20px;text-align:center;">
              <p style="margin:0 0 5px;font-size:14px;font-weight:bold;color:#333333;">COS Tesla LLC</p>
              <p style="margin:0 0 15px;font-size:12px;color:#888888;">Support: <a href="mailto:peter.teehan@costesla.com" style="color:#D12630;text-decoration:none;">peter.teehan@costesla.com</a></p>
              <p style="margin:0;font-size:11px;color:#999999;line-height:1.5;">Addresses included because this is an official passenger receipt.</p>
            </td>
          </tr>

        </table>
        
      </td>
    </tr>
  </table>
</body>
</html>`;
}

/**
 * Generate plain text email body for receipt
 */
export function generateReceiptText(data: ReceiptTemplateData): string {
    const { input, hasPhoto, photoAttribution } = data;
    const { TripData, FareData, PaymentData, PassengerData } = input;

    const greeting = PassengerData.firstName
        ? `Hi ${PassengerData.firstName},`
        : 'Hello,';

    const paymentLine = PaymentData.Last4
        ? `${PaymentData.Method} ending in ${PaymentData.Last4}`
        : PaymentData.Method;

    let text = `COS TESLA LLC — PRIVATE TRIP RECEIPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${greeting}

Here is your official receipt for your private trip. This document is suitable for tax deductions and business reimbursement.

${hasPhoto ? `[Place photo included]
Photo © Google — ${photoAttribution || 'Google'}

` : ''}TRIP SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Trip ID:           ${TripData.Id}
Date:              ${TripData.DateLocal}
Time:              ${TripData.StartTimeLocal} – ${TripData.EndTimeLocal}

Pickup Address:
${TripData.PickupAddress}

Dropoff Address:
${TripData.DropoffAddress}

Distance:          ${TripData.Distance.mi} mi
Duration:          ${TripData.Duration.min} min


FARE BREAKDOWN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Base Fare:                          $${FareData.Base}
Time & Distance:                    $${FareData.TimeDistance}
Extras (Tolls/Parking):             $${FareData.Extras}`;

    if (FareData.Discount !== '0.00') {
        text += `\nDiscount:                          -$${FareData.Discount}`;
    }

    text += `
Subtotal:                           $${FareData.Subtotal}
Tax:                                $${FareData.Tax}
Tip:                                $${FareData.Tip}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL:                              $${FareData.Total}


PAYMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Payment Method:    ${paymentLine}
Authorization:     ${PaymentData.AuthCode}
`;

    if (TripData.Notes) {
        text += `

NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${TripData.Notes}
`;
    }

    text += `

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COS Tesla LLC
Support: peter.teehan@costesla.com

Addresses included because this is an official passenger receipt.
`;

    return text;
}
