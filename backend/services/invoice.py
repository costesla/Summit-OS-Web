"""
SummitOS Custom Invoice Service
Generates post-trip invoices with:
  - Venmo / Zelle / Stripe payment options
  - Thor Telemetry: energy used vs equivalent fuel consumption
"""

import os
import logging
import stripe
from datetime import datetime


# ─── Constants ────────────────────────────────────────────────────────────────

VENMO_HANDLE = "@COS-Tesla"
ZELLE_EMAIL  = "peter.teehan@costesla.com"

# Benchmark: Chevrolet Suburban / GMC Yukon XL (20 MPG highway – luxury SUV)
BENCHMARK_MPG  = 20.0
GAS_PRICE_PER_GALLON = 3.50  # USD estimate; update seasonally
CO2_LBS_PER_GALLON   = 19.64  # US EPA: lbs of CO2 per gallon of gasoline
# Tesla Model Y efficiency reference: ~250 Wh/mi (conservative)
TESLA_WH_PER_MILE = 250.0


# ─── Stripe Payment Link ───────────────────────────────────────────────────────

def create_stripe_payment_link(customer_name: str, amount_usd: float, trip_label: str) -> str:
    """
    Creates a one-time Stripe Checkout session and returns the hosted URL.
    Falls back to None if Stripe is unavailable.
    """
    try:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            logging.warning("STRIPE_SECRET_KEY not set – skipping Stripe link generation.")
            return None

        amount_cents = int(round(amount_usd * 100))
        base_url = os.environ.get("SITE_BASE_URL", "https://costesla.com")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=None,  # Customer fills in at checkout
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "SummitOS Private Trip",
                        "description": trip_label,
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{base_url}/booking-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/book",
            metadata={
                "customerName": customer_name,
                "source": "post_trip_invoice",
            }
        )
        return session.url
    except Exception as e:
        logging.error(f"Stripe payment link error: {e}")
        return None


# ─── Thor Telemetry ────────────────────────────────────────────────────────────

def calculate_thor_telemetry(distance_miles: float, energy_used_kwh: float = None) -> dict:
    """
    Given trip distance and optional real kWh from Tessie, calculate:
    - Energy used (kWh) – real or estimated
    - Equivalent SUV fuel consumption
    - Estimated gas cost saved
    - CO2 emissions saved
    """
    # If Tessie data is available, use it; otherwise estimate
    if energy_used_kwh and energy_used_kwh > 0:
        kwh = round(energy_used_kwh, 2)
        data_source = "Tessie Telemetry (Live)"
    else:
        kwh = round((TESLA_WH_PER_MILE * distance_miles) / 1000, 2)
        data_source = "SummitOS Estimate"

    gallons_equivalent = round(distance_miles / BENCHMARK_MPG, 2)
    gas_cost_saved     = round(gallons_equivalent * GAS_PRICE_PER_GALLON, 2)
    co2_lbs_saved      = round(gallons_equivalent * CO2_LBS_PER_GALLON, 1)

    return {
        "distance_miles":       round(distance_miles, 1),
        "energy_used_kwh":      kwh,
        "data_source":          data_source,
        "benchmark_vehicle":    f"20 MPG Luxury SUV (e.g. Chevrolet Suburban)",
        "gallons_equivalent":   gallons_equivalent,
        "gas_cost_saved_usd":   gas_cost_saved,
        "co2_lbs_saved":        co2_lbs_saved,
    }


# ─── HTML Email Template ───────────────────────────────────────────────────────

def build_invoice_html(
    customer_name: str,
    customer_email: str,
    trip_date: str,
    pickup: str,
    dropoff: str,
    amount_usd: float,
    invoice_id: str,
    telemetry: dict,
    stripe_url: str = None,
    notes: str = ""
) -> str:
    """
    Generates a premium, Outlook-safe HTML invoice email.
    """
    amount_display = f"${amount_usd:,.2f}"
    first_name = customer_name.split()[0] if customer_name else "there"

    stripe_section = ""
    if stripe_url:
        stripe_section = f"""
        <tr>
          <td style="padding: 0 0 12px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background:#0a0a0a; border-radius:8px; padding:18px 24px;">
                  <p style="margin:0 0 6px 0; color:#a0a0a0; font-size:12px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Option 3 — Secure Card / Apple Pay</p>
                  <p style="margin:0 0 14px 0; color:#d0d0d0; font-size:13px; font-family:Arial,sans-serif; line-height:1.5;">
                    Prefer to pay by credit card or Apple Pay? Use our encrypted Stripe checkout — your card details are never stored on our servers. A standard processing fee may apply.
                  </p>
                  <a href="{stripe_url}" style="display:inline-block; background:linear-gradient(135deg, #635bff 0%, #8f86ff 100%); color:#ffffff; font-family:Arial,sans-serif; font-size:14px; font-weight:bold; text-decoration:none; padding:12px 28px; border-radius:6px;">⚡ Pay ${amount_usd:,.2f} via Stripe</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    notes_section = ""
    if notes:
        notes_section = f"""
        <tr>
          <td style="padding:0 0 20px 0;">
            <p style="margin:0; color:#a0a0a0; font-size:13px; font-family:Arial,sans-serif; font-style:italic;">
              📝 {notes}
            </p>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SummitOS Invoice {invoice_id}</title>
</head>
<body style="margin:0; padding:0; background:#0d0d0d; font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0d0d0d;">
    <tr>
      <td align="center" style="padding:32px 16px;">

        <!-- Outer Card -->
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px; width:100%; background:#161616; border-radius:16px; overflow:hidden; border:1px solid #2a2a2a;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg, #1a1a2e 0%, #0f3460 60%, #16213e 100%); padding:36px 40px; text-align:center;">
              <p style="margin:0 0 4px 0; color:#ffffff; font-size:24px; font-weight:bold; font-family:Arial,sans-serif; letter-spacing:1px;">COS TESLA LLC</p>
              <p style="margin:0; color:#8ecae6; font-size:12px; font-family:Arial,sans-serif; letter-spacing:2px; text-transform:uppercase;">Powered by: SummitOS</p>
            </td>
          </tr>

          <!-- Invoice Header Row -->
          <tr>
            <td style="padding:28px 40px 0 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <p style="margin:0; color:#a0a0a0; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Invoice</p>
                    <p style="margin:2px 0 0 0; color:#ffffff; font-size:15px; font-family:Arial,sans-serif; font-weight:bold;">{invoice_id}</p>
                  </td>
                  <td align="right">
                    <p style="margin:0; color:#a0a0a0; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Date</p>
                    <p style="margin:2px 0 0 0; color:#ffffff; font-size:15px; font-family:Arial,sans-serif;">{trip_date}</p>
                  </td>
                </tr>
              </table>
              <hr style="border:none; border-top:1px solid #2a2a2a; margin:20px 0;">
            </td>
          </tr>

          <!-- Greeting -->
          <tr>
            <td style="padding:0 40px 20px 40px;">
              <p style="margin:0; color:#e0e0e0; font-size:15px; font-family:Arial,sans-serif; line-height:1.6;">
                Hi {first_name},<br><br>
                Thank you for riding with SummitOS! Please find your trip invoice below. You can pay using whichever method is most convenient for you.
              </p>
            </td>
          </tr>

          <!-- Trip Details -->
          <tr>
            <td style="padding:0 40px 24px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#1f1f1f; border-radius:10px; border:1px solid #2a2a2a; overflow:hidden;">
                <tr>
                  <td style="padding:14px 20px; background:#252525; border-bottom:1px solid #2a2a2a;">
                    <p style="margin:0; color:#8ecae6; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px; font-weight:bold;">🚗 Trip Details</p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:16px 20px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="50%" style="padding-bottom:10px;">
                          <p style="margin:0; color:#707070; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase;">Pickup</p>
                          <p style="margin:4px 0 0 0; color:#e0e0e0; font-size:13px; font-family:Arial,sans-serif;">{pickup}</p>
                        </td>
                        <td width="50%" style="padding-bottom:10px;">
                          <p style="margin:0; color:#707070; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase;">Drop-off</p>
                          <p style="margin:4px 0 0 0; color:#e0e0e0; font-size:13px; font-family:Arial,sans-serif;">{dropoff}</p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%">
                          <p style="margin:0; color:#707070; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase;">Distance</p>
                          <p style="margin:4px 0 0 0; color:#e0e0e0; font-size:13px; font-family:Arial,sans-serif;">{telemetry['distance_miles']} miles</p>
                        </td>
                        <td width="50%">
                          <p style="margin:0; color:#707070; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase;">Billed To</p>
                          <p style="margin:4px 0 0 0; color:#e0e0e0; font-size:13px; font-family:Arial,sans-serif;">{customer_name}</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="background:#1a2a1a; border-top:1px solid #2a2a2a; padding:16px 20px; text-align:center;">
                    <p style="margin:0; color:#a0a0a0; font-size:13px; font-family:Arial,sans-serif;">Amount Due</p>
                    <p style="margin:4px 0 0 0; color:#4ade80; font-size:32px; font-family:Arial,sans-serif; font-weight:bold;">{amount_display}</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Payment Options -->
          <tr>
            <td style="padding:0 40px 8px 40px;">
              <p style="margin:0 0 16px 0; color:#ffffff; font-size:15px; font-family:Arial,sans-serif; font-weight:bold;">💳 Payment Options</p>
              <table width="100%" cellpadding="0" cellspacing="0" border="0">

                <!-- Option 1: Venmo -->
                <tr>
                  <td style="padding:0 0 12px 0;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="background:#1a1f2e; border:1px solid #2a3a5e; border-radius:8px; padding:16px 20px;">
                          <table width="100%" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                              <td>
                                <p style="margin:0; color:#5f86f2; font-size:12px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px; font-weight:bold;">Option 1 — Venmo (Preferred)</p>
                                <p style="margin:6px 0 0 0; color:#ffffff; font-size:20px; font-family:Arial,sans-serif; font-weight:bold;">{VENMO_HANDLE}</p>
                              </td>
                              <td align="right">
                                <p style="margin:0; background:#3d5af1; color:#fff; font-size:13px; font-family:Arial,sans-serif; padding:6px 14px; border-radius:20px; display:inline-block;">@Venmo</p>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <!-- Option 2: Zelle -->
                <tr>
                  <td style="padding:0 0 12px 0;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="background:#1f1a2e; border:1px solid #3a2a5e; border-radius:8px; padding:16px 20px;">
                          <table width="100%" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                              <td>
                                <p style="margin:0; color:#9b72ff; font-size:12px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px; font-weight:bold;">Option 2 — Zelle</p>
                                <p style="margin:6px 0 0 0; color:#ffffff; font-size:16px; font-family:Arial,sans-serif; font-weight:bold;">{ZELLE_EMAIL}</p>
                              </td>
                              <td align="right">
                                <p style="margin:0; background:#6a1fc2; color:#fff; font-size:13px; font-family:Arial,sans-serif; padding:6px 14px; border-radius:20px; display:inline-block;">Zelle</p>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <!-- Option 3: Stripe -->
                {stripe_section}

              </table>
            </td>
          </tr>

          <!-- Notes -->
          {notes_section}

          <!-- Thor Telemetry -->
          <tr>
            <td style="padding:0 40px 32px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0a1a0a; border:1px solid #1a3a1a; border-radius:12px; overflow:hidden;">
                <tr>
                  <td style="background:#0f2a0f; padding:14px 20px; border-bottom:1px solid #1a3a1a;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td>
                          <p style="margin:0; color:#4ade80; font-size:13px; font-family:Arial,sans-serif; font-weight:bold; letter-spacing:1px;">⚡ THOR TRIP TELEMETRY</p>
                          <p style="margin:2px 0 0 0; color:#5a7a5a; font-size:11px; font-family:Arial,sans-serif;">What it cost to move you vs. a traditional vehicle · {telemetry['data_source']}</p>
                        </td>
                        <td align="right">
                          <p style="margin:0; color:#4ade80; font-size:11px; font-family:Arial,sans-serif; background:#1a3a1a; padding:4px 10px; border-radius:20px; display:inline-block;">100% Electric</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:20px;">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="50%" style="padding-bottom:16px;">
                          <p style="margin:0; color:#4a6a4a; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Distance</p>
                          <p style="margin:4px 0 0 0; color:#e0e0e0; font-size:16px; font-family:Arial,sans-serif; font-weight:bold;">{telemetry['distance_miles']} mi</p>
                        </td>
                        <td width="50%" style="padding-bottom:16px;">
                          <p style="margin:0; color:#4a6a4a; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Electric Energy Used</p>
                          <p style="margin:4px 0 0 0; color:#4ade80; font-size:16px; font-family:Arial,sans-serif; font-weight:bold;">{telemetry['energy_used_kwh']} kWh</p>
                        </td>
                      </tr>
                      <tr>
                        <td width="50%" style="padding-bottom:16px;">
                          <p style="margin:0; color:#4a6a4a; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">A {telemetry['benchmark_vehicle']} would've burned</p>
                          <p style="margin:4px 0 0 0; color:#f87171; font-size:16px; font-family:Arial,sans-serif; font-weight:bold;">{telemetry['gallons_equivalent']} gal ⛽</p>
                        </td>
                        <td width="50%" style="padding-bottom:16px;">
                          <p style="margin:0; color:#4a6a4a; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Gas $ You Didn't Burn</p>
                          <p style="margin:4px 0 0 0; color:#fbbf24; font-size:16px; font-family:Arial,sans-serif; font-weight:bold;">${telemetry['gas_cost_saved_usd']:.2f} 💰</p>
                        </td>
                      </tr>
                      <tr>
                        <td colspan="2" style="background:#0a2a0a; border-radius:8px; padding:12px 16px; text-align:center;">
                          <p style="margin:0; color:#4a6a4a; font-size:12px; font-family:Arial,sans-serif;">CO₂ Emissions Avoided</p>
                          <p style="margin:4px 0 0 0; color:#4ade80; font-size:20px; font-family:Arial,sans-serif; font-weight:bold;">{telemetry['co2_lbs_saved']} lbs 🌱</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#111111; padding:24px 40px; text-align:center; border-top:1px solid #2a2a2a;">
              <p style="margin:0 0 6px 0; color:#505050; font-size:12px; font-family:Arial,sans-serif;">Questions? Reply directly to this email or text Peter at (719) 555-0100.</p>
              <p style="margin:0; color:#303030; font-size:11px; font-family:Arial,sans-serif;">COS Tesla LLC · Colorado Springs, CO · {datetime.now().year}</p>
              <p style="margin:8px 0 0 0; color:#303030; font-size:11px; font-family:Arial,sans-serif;">Powered by SummitOS — <span style="color:#4ade80;">⚡ Driving Greener</span></p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_invoice_id(customer_name: str, trip_date: str) -> str:
    """Generates a clean invoice ID."""
    safe_name = customer_name.split()[0].upper() if customer_name else "CLIENT"
    date_clean = trip_date.replace("-", "").replace("/", "").replace(" ", "")[:8]
    ts = datetime.now().strftime("%H%M")
    return f"INV-{safe_name}-{date_clean}-{ts}"
