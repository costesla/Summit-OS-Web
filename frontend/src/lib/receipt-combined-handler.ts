/**
 * COS Tesla LLC — SummitOS + Antigravity
 * Private Trip Receipt Engine (Graph sendMail + Google Places NEW)
 * TYPE-SAFE, NATIVE TYPESCRIPT VERSION — OPTION A1
 */

////////////////////////////////
// 1. TYPE DEFINITIONS
////////////////////////////////

interface TripData {
    Id: string;
    DateLocal: string;
    StartTimeLocal: string;
    EndTimeLocal: string;
    PickupArea: string;
    DropoffArea: string;
    PickupAddress: string;
    DropoffAddress: string;
    Distance: { mi: number };
    Duration: { min: number };
    Pickup?: { PlaceId?: string };
    Dropoff?: { PlaceId?: string };
}

interface FareData {
    Base: string;
    TimeDistance: string;
    Extras: string;
    Discount: string;
    Subtotal: string;
    Tax: string;
    Tip: string;
    Total: string;
}

interface PaymentData {
    Method: string;
    Last4?: string;
    AuthCode: string;
}

interface PassengerData {
    firstName?: string;
    email: string;
}

interface GeoData {
    lat?: number;
    lng?: number;
    city?: string;
    region?: string;
    country?: string;
}

interface ReceiptInput {
    TripData: TripData;
    FareData: FareData;
    PaymentData: PaymentData;
    PassengerData: PassengerData;
    GeoData?: GeoData;
    Now?: { Year: number };
}

interface ReceiptOutput {
    html: string;
    text: string;
    send: {
        status: "sent";
        transport: "graph";
        timestamp: number;
    };
}

////////////////////////////////
// 2. ENV HELPERS
////////////////////////////////

function getEnvVar(name: string): string {
    const value = process.env[name];
    if (!value) {
        throw new Error(`Missing required environment variable: ${name}`);
    }
    return value;
}

////////////////////////////////
// 3. GOOGLE PLACES HELPERS
////////////////////////////////

async function getPlaceDetails(placeId: string) {
    const GOOGLE_KEY = getEnvVar('GOOGLE_PLACES_API_KEY');
    const url =
        `https://places.googleapis.com/v1/places/${placeId}?fields=displayName,photos,attributions&key=${GOOGLE_KEY}`;
    const r = await fetch(url);
    if (!r.ok) return null;
    return r.json();
}

async function searchPlaceByText(area: string, geo?: GeoData) {
    const GOOGLE_KEY = getEnvVar('GOOGLE_PLACES_API_KEY');
    const body: any = {
        textQuery: area,
    };
    if (geo?.lat && geo?.lng) {
        body.locationBias = {
            circle: {
                center: { latitude: geo.lat, longitude: geo.lng },
                radius: 15000
            }
        };
    }
    const r = await fetch(
        `https://places.googleapis.com/v1/places:searchText?key=${GOOGLE_KEY}`,
        {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body)
        }
    );
    if (!r.ok) return null;
    const js = await r.json();
    if (!js.places?.length) return null;
    return js.places[0];
}

async function getPlacePhoto(photoName: string): Promise<string | null> {
    const GOOGLE_KEY = getEnvVar('GOOGLE_PLACES_API_KEY');
    const url =
        `https://places.googleapis.com/v1/${photoName}/media?maxWidthPx=800&key=${GOOGLE_KEY}`;
    const r = await fetch(url);
    if (!r.ok) return null;
    const buf = await r.arrayBuffer();
    return Buffer.from(buf).toString("base64");
}

////////////////////////////////
// 4. GRAPH TOKEN HELPER
////////////////////////////////

async function getGraphToken(): Promise<string> {
    const TENANT = getEnvVar('OAUTH_TENANT_ID');
    const CLIENT = getEnvVar('OAUTH_CLIENT_ID');
    const SECRET = getEnvVar('OAUTH_CLIENT_SECRET');
    const url = `https://login.microsoftonline.com/${TENANT}/oauth2/v2.0/token`;
    const body = new URLSearchParams({
        client_id: CLIENT,
        client_secret: SECRET,
        scope: "https://graph.microsoft.com/.default",
        grant_type: "client_credentials"
    });
    const r = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body
    });
    if (!r.ok)
        throw new Error(
            "Graph token request failed: " + (await r.text())
        );
    const js = await r.json();
    return js.access_token;
}

////////////////////////////////
// 5. MAIN HANDLER
////////////////////////////////

export default async function handler(input: ReceiptInput): Promise<ReceiptOutput | { error: any }> {
    const { TripData, FareData, PaymentData, PassengerData, GeoData } = input;

    if (!TripData || !FareData || !PaymentData || !PassengerData)
        return { error: { code: 400, message: "Missing required fields." } };

    ///////////////////////////////////////////////
    // 5.1 RESOLVE GOOGLE PLACE PHOTO
    ///////////////////////////////////////////////

    let place: any = null;

    // Priority order: DropoffId → PickupId → Text search
    if (TripData.Dropoff?.PlaceId) {
        place = await getPlaceDetails(TripData.Dropoff.PlaceId);
    }
    if (!place && TripData.Pickup?.PlaceId) {
        place = await getPlaceDetails(TripData.Pickup.PlaceId);
    }
    if (!place) {
        const textQuery =
            TripData.DropoffArea ??
            TripData.PickupArea ??
            `${GeoData?.city ?? ""} ${GeoData?.region ?? ""}`;
        const p = await searchPlaceByText(textQuery, GeoData);
        if (p?.id) place = await getPlaceDetails(p.id);
    }

    let photoBase64: string | null = null;
    let attribution: string | null = null;

    if (place?.photos?.[0]) {
        photoBase64 = await getPlacePhoto(place.photos[0].name);
        attribution =
            place.attributions?.providerDisplayName ??
            place.photos[0].authorAttributions?.[0]?.displayName ??
            null;
    }

    ///////////////////////////////////////////////
    // 5.2 BUILD HTML RECEIPT
    ///////////////////////////////////////////////

    const firstName = PassengerData.firstName
        ? `Hi ${PassengerData.firstName},`
        : "Hello,";

    const placeFigure = photoBase64
        ? `
      <figure style="margin:0;">
        <img src="cid:place_photo_1" style="max-width:100%; display:block; border-radius:8px;" alt="Place photo" />
        <figcaption style="font-size:12px; color:#667085;">
          Photo © Google ${attribution ? "— " + attribution : ""}
        </figcaption>
      </figure>
      `
        : "";

    const html = `<!DOCTYPE html>
<html>
  <body style="font-family:Segoe UI, Arial, sans-serif; background:#f6f8fb; padding:24px;">
    <div style="max-width:600px; margin:0 auto; background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:20px;">
      <h2 style="margin-top:0;">SummitOS LLC — Private Trip Receipt</h2>
      <p>${firstName}</p>
      ${placeFigure}
      <h3>Trip Summary</h3>
      <p>
        <b>Trip ID:</b> ${TripData.Id}<br>
        <b>Date:</b> ${TripData.DateLocal}<br>
        <b>Time:</b> ${TripData.StartTimeLocal} – ${TripData.EndTimeLocal}<br>
        <b>Pickup:</b> ${TripData.PickupAddress}<br>
        <b>Drop-off:</b> ${TripData.DropoffAddress}<br>
        <b>Distance:</b> ${TripData.Distance.mi} mi<br>
        <b>Duration:</b> ${TripData.Duration.min} min
      </p>
      <h3>Fare Breakdown</h3>
      <table style="width:100%; border-collapse:collapse;">
        <tr><td>Base fare</td><td style="text-align:right;">$${FareData.Base}</td></tr>
        <tr><td>Time &amp; distance</td><td style="text-align:right;">$${FareData.TimeDistance}</td></tr>
        <tr><td>Extras</td><td style="text-align:right;">$${FareData.Extras}</td></tr>
        <tr><td>Discount</td><td style="text-align:right;">-$${FareData.Discount}</td></tr>
        <tr><td>Subtotal</td><td style="text-align:right;">$${FareData.Subtotal}</td></tr>
        <tr><td>Tax</td><td style="text-align:right;">$${FareData.Tax}</td></tr>
        <tr><td>Tip</td><td style="text-align:right;">$${FareData.Tip}</td></tr>
        <tr><td><b>Total charged</b></td><td style="text-align:right;"><b>$${FareData.Total}</b></td></tr>
      </table>
      <h3>Payment</h3>
      <p>
        Method: ${PaymentData.Method}${PaymentData.Last4 ? " ending in " + PaymentData.Last4 : ""
        }<br>
        Authorization: ${PaymentData.AuthCode}
      </p>
      <p style="font-size:12px; color:#667085;">
        Addresses included because this is an official passenger receipt.
      </p>
      <p style="font-size:12px; color:#667085;">
        Questions? Reply to this email or contact peter.teehan@costesla.com
      </p>
    </div>
  </body>
</html>`;

    ///////////////////////////////////////////////
    // 5.3 TEXT RECEIPT
    ///////////////////////////////////////////////

    const text = `SummitOS LLC — Private Trip Receipt

${firstName}

Trip ID: ${TripData.Id}
Date: ${TripData.DateLocal}
Time: ${TripData.StartTimeLocal} – ${TripData.EndTimeLocal}
Pickup: ${TripData.PickupAddress}
Drop-off: ${TripData.DropoffAddress}
Distance: ${TripData.Distance.mi} mi
Duration: ${TripData.Duration.min} min

Fare Breakdown:
  Base: $${FareData.Base}
  Time & distance: $${FareData.TimeDistance}
  Extras: $${FareData.Extras}
  Discount: -$${FareData.Discount}
  Subtotal: $${FareData.Subtotal}
  Tax: $${FareData.Tax}
  Tip: $${FareData.Tip}
TOTAL: $${FareData.Total}

Payment:
  Method: ${PaymentData.Method}${PaymentData.Last4 ? " ending in " + PaymentData.Last4 : ""
        }
  Authorization: ${PaymentData.AuthCode}

${photoBase64 ? "[Inline Google Places photo included]" : ""}

Addresses included because this is an official passenger receipt.
Questions? Contact peter.teehan@costesla.com`;

    ///////////////////////////////////////////////
    // 5.4 GRAPH SENDMAIL
    ///////////////////////////////////////////////

    const token = await getGraphToken();

    const message: any = {
        subject: `Your Private Trip Receipt — ${TripData.DateLocal}`,
        from: { emailAddress: { address: "PrivateTrips@costesla.com" } },
        toRecipients: [
            { emailAddress: { address: PassengerData.email } }
        ],
        internetMessageHeaders: [
            { name: "Reply-To", value: "peter.teehan@costesla.com" },
            {
                name: "List-Unsubscribe",
                value: "<mailto:peter.teehan@costesla.com?subject=unsubscribe>"
            },
            { name: "List-Unsubscribe-Post", value: "List-Unsubscribe=One-Click" },
            { name: "X-Mailer", value: "SummitOS Receipt Engine" },
            { name: "X-Sent-By", value: "SummitOS LLC" }
        ],
        body: { contentType: "HTML", content: html }
    };

    if (photoBase64) {
        message.attachments = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                name: "place.jpg",
                contentType: "image/jpeg",
                isInline: true,
                contentId: "place_photo_1",
                contentBytes: photoBase64
            }
        ];
    }

    const mailBody = {
        message,
        saveToSentItems: true
    };

    const mailRes = await fetch(
        `https://graph.microsoft.com/v1.0/users/${encodeURIComponent(
            "PrivateTrips@costesla.com"
        )}/sendMail`,
        {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`,
                "content-type": "application/json"
            },
            body: JSON.stringify(mailBody)
        }
    );

    if (!mailRes.ok) {
        return {
            error: {
                code: mailRes.status,
                message: await mailRes.text()
            }
        };
    }

    ///////////////////////////////////////////////
    // 5.5 RETURN OUTPUT CONTRACT
    ///////////////////////////////////////////////

    return {
        html,
        text,
        send: {
            status: "sent",
            transport: "graph",
            timestamp: Date.now()
        }
    };
}
