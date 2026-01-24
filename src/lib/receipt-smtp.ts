/**
 * SMTP Email Sender for Private Trip Receipts
 * Handles actual email delivery via nodemailer with Microsoft 365
 */

import nodemailer from 'nodemailer';
import { SMTPSendBlock } from '@/types/receipt-types';

/**
 * Send receipt email via SMTP
 * @param sendBlock - Complete SMTP configuration and email content
 * @returns Success with message ID, or error
 */
export async function sendReceiptEmail(
    sendBlock: SMTPSendBlock
): Promise<{ success: true; messageId: string } | { success: false; error: string }> {
    try {
        // Create transporter
        const transporter = nodemailer.createTransport({
            host: sendBlock.smtp_host,
            port: sendBlock.smtp_port,
            secure: false, // STARTTLS
            auth: {
                user: sendBlock.smtp_username,
                pass: sendBlock.smtp_password,
            },
            tls: {
                ciphers: 'SSLv3',
                rejectUnauthorized: false,
            },
        });

        // Build email options
        const mailOptions: any = {
            from: sendBlock.from,
            replyTo: sendBlock.reply_to,
            to: sendBlock.to,
            subject: sendBlock.subject,
            html: sendBlock.html_body,
            text: sendBlock.text_body,
            headers: sendBlock.headers,
        };

        // Add inline attachments if present
        if (sendBlock.attachments_inline && sendBlock.attachments_inline.length > 0) {
            mailOptions.attachments = sendBlock.attachments_inline.map(att => ({
                filename: att.filename,
                content: Buffer.from(att.content_base64, 'base64'),
                cid: att.content_id,
                contentType: att.mime_type,
            }));
        }

        // Send email
        const info = await transporter.sendMail(mailOptions);

        console.log('Receipt email sent successfully:', info.messageId);

        return {
            success: true,
            messageId: info.messageId,
        };
    } catch (error) {
        console.error('SMTP send failure:', error);

        const errorMessage = error instanceof Error ? error.message : 'Unknown SMTP error';

        return {
            success: false,
            error: errorMessage,
        };
    }
}
