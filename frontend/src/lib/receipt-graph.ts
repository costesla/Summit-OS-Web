/**
 * Microsoft Graph API Email Sender for Private Trip Receipts
 * Uses Graph sendMail instead of SMTP for better Microsoft 365 integration
 */

import { SMTPSendBlock } from '@/types/receipt-types';

interface GraphEmailResult {
    success: boolean;
    messageId?: string;
    error?: string;
}

/**
 * Acquire Microsoft Graph access token using client credentials flow
 */
async function getGraphToken(): Promise<string | null> {
    const TENANT = process.env.OAUTH_TENANT_ID;
    const CLIENT = process.env.OAUTH_CLIENT_ID;
    const SECRET = process.env.OAUTH_CLIENT_SECRET;

    if (!TENANT || !CLIENT || !SECRET) {
        console.error('Missing Graph API credentials');
        return null;
    }

    try {
        const url = `https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token`;
        const body = new URLSearchParams({
            client_id: CLIENT,
            client_secret: SECRET,
            scope: 'https://graph.microsoft.com/.default',
            grant_type: 'client_credentials',
        });

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'content-type': 'application/x-www-form-urlencoded' },
            body,
        });

        if (!response.ok) {
            const error = await response.text();
            console.error('Graph token acquisition failed:', error);
            return null;
        }

        const data = await response.json();
        return data.access_token;
    } catch (error) {
        console.error('Error acquiring Graph token:', error);
        return null;
    }
}

/**
 * Send receipt email via Microsoft Graph sendMail API
 * Superior to SMTP for Microsoft 365 integration
 */
export async function sendReceiptEmailGraph(
    sendBlock: SMTPSendBlock
): Promise<GraphEmailResult> {
    try {
        // Get Graph access token
        const token = await getGraphToken();
        if (!token) {
            return {
                success: false,
                error: 'Failed to acquire Graph API token',
            };
        }

        // Build Graph message object
        const message: any = {
            subject: sendBlock.subject,
            from: {
                emailAddress: {
                    address: sendBlock.smtp_username, // PrivateTrips@costesla.com
                },
            },
            toRecipients: [
                {
                    emailAddress: {
                        address: sendBlock.to,
                    },
                },
            ],
            internetMessageHeaders: [
                { name: 'Reply-To', value: sendBlock.reply_to },
                { name: 'List-Unsubscribe', value: sendBlock.headers['List-Unsubscribe'] },
                { name: 'List-Unsubscribe-Post', value: sendBlock.headers['List-Unsubscribe-Post'] },
                { name: 'X-Mailer', value: sendBlock.headers['X-Mailer'] },
                { name: 'X-Sent-By', value: sendBlock.headers['X-Sent-By'] },
            ],
            body: {
                contentType: 'HTML',
                content: sendBlock.html_body,
            },
        };

        // Add inline attachments if present
        if (sendBlock.attachments_inline && sendBlock.attachments_inline.length > 0) {
            message.attachments = sendBlock.attachments_inline.map(att => ({
                '@odata.type': '#microsoft.graph.fileAttachment',
                name: att.filename,
                contentType: att.mime_type,
                isInline: true,
                contentId: att.content_id,
                contentBytes: att.content_base64,
            }));
        }

        // Send via Graph API
        const sendUrl = `https://graph.microsoft.com/v1.0/users/${encodeURIComponent(
            sendBlock.smtp_username
        )}/sendMail`;

        const response = await fetch(sendUrl, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message,
                saveToSentItems: true,
            }),
        });

        if (!response.ok) {
            const error = await response.text();
            console.error('Graph sendMail failed:', error);
            return {
                success: false,
                error: `Graph API error: ${response.status} ${error}`,
            };
        }

        // Graph sendMail returns 202 Accepted with no body
        const messageId = `graph-${Date.now()}`;
        console.log('Receipt email sent via Graph API:', messageId);

        return {
            success: true,
            messageId,
        };
    } catch (error) {
        console.error('Error sending email via Graph:', error);
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        return {
            success: false,
            error: errorMessage,
        };
    }
}
