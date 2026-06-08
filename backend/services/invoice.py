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

def create_stripe_payment_link(customer_name: str, customer_email: str, amount_usd: float, trip_label: str) -> str:
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
            customer_email=customer_email if customer_email else None,
            payment_intent_data={
                "receipt_email": customer_email if customer_email else None,
            },
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
            success_url=f"{base_url}/book/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/book",
            metadata={
                "customerName": customer_name,
                "customerEmail": customer_email,
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


# ─── Tessie Route Visuals & FSD Math ───────────────────────────────────────────

def calculate_fsd_percentage(drive: dict, path_points: list = None) -> float:
    """
    Calculates the percentage of the trip driven using Full Self-Driving (FSD) / Autopilot.
    Checks 'autopilot_distance' and 'distance' first, then falls back to path_points.
    """
    if not drive:
        return None

    autopilot_distance = drive.get("autopilot_distance")
    
    # Check if we can calculate it from the drive summary fields
    total_distance = drive.get("distance")
    if total_distance is None:
        start_odo = drive.get("starting_odometer")
        end_odo = drive.get("ending_odometer")
        if start_odo is not None and end_odo is not None:
            total_distance = end_odo - start_odo

    if autopilot_distance is not None and total_distance and total_distance > 0:
        pct = (autopilot_distance / total_distance) * 100
        return min(max(pct, 0.0), 100.0)

    # Fallback to checking the details path points
    if path_points:
        total_pts = len(path_points)
        if total_pts > 0:
            fsd_pts = sum(1 for pt in path_points if pt.get("autopilot") is True)
            pct = (fsd_pts / total_pts) * 100
            return min(max(pct, 0.0), 100.0)

    return None


def generate_static_map_url(path_points: list, api_key: str) -> str:
    """
    Constructs a styled Google Static Maps URL showing the driving route path,
    optimized with coordinate simplification/sampling to fit standard limits.
    """
    if not path_points or not api_key:
        return None

    coords = []
    for pt in path_points:
        lat = pt.get("latitude")
        lon = pt.get("longitude")
        if lat is not None and lon is not None:
            coords.append((lat, lon))

    if not coords:
        return None

    # Sample points to keep the URL concise and avoid client/server URL limits
    max_points = 40
    if len(coords) > max_points:
        indices = [int(i * (len(coords) - 1) / (max_points - 1)) for i in range(max_points)]
        sampled_coords = [coords[i] for i in indices]
    else:
        sampled_coords = coords

    path_str = "|".join(f"{lat:.5f},{lon:.5f}" for lat, lon in sampled_coords)
    
    start_lat, start_lon = coords[0]
    end_lat, end_lon = coords[-1]

    # Minimal dark styled parameters for high-end dark aesthetic map
    styles = (
        "&style=feature:all|element:geometry|color:0x1b1b1b"
        "&style=feature:water|element:geometry|color:0x0f0f1b"
        "&style=feature:road|element:geometry|color:0x333333"
        "&style=feature:road|element:labels.text.fill|color:0x888888"
        "&style=feature:all|element:labels.text.stroke|visibility:off"
    )

    url = (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?size=600x300&scale=2&maptype=roadmap"
        f"{styles}"
        f"&path=color:0x06b6d4|weight:5|{path_str}"
        f"&markers=color:0x34c759|label:S|{start_lat:.5f},{start_lon:.5f}"
        f"&markers=color:0xff3b30|label:E|{end_lat:.5f},{end_lon:.5f}"
        f"&key={api_key}"
    )
    return url


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
    notes: str = "",
    map_url: str = None,
    fsd_percentage: float = None
) -> str:
    """
    Generates a premium, Outlook-safe HTML invoice email.
    """
    amount_display = f"${amount_usd:,.2f}"
    first_name = customer_name.split()[0] if customer_name else "there"
    site_url = os.environ.get("SITE_URL") or os.environ.get("SITE_BASE_URL") or "https://www.costesla.com"

    fsd_badge = ""
    if fsd_percentage is not None:
        fsd_display = f"{fsd_percentage:.0f}%" if fsd_percentage.is_integer() else f"{fsd_percentage:.1f}%"
        star_char = " ⭐" if fsd_percentage > 95 else ""
        fsd_badge = f"""
        <div style="margin-top: 4px;">
          <p style="margin:0; color:#06b6d4; font-size:11px; font-family:Arial,sans-serif; background:#082f49; padding:4px 10px; border-radius:20px; display:inline-block; border: 1px solid #0e7490; white-space: nowrap;">🤖 {fsd_display} FSD{star_char}</p>
        </div>
        """

    map_section = ""
    if map_url:
        map_section = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px; border-top:1px solid #1a3a1a; padding-top:16px;">
          <tr>
            <td>
              <p style="margin:0 0 8px 0; color:#4a6a4a; font-size:11px; font-family:Arial,sans-serif; text-transform:uppercase; letter-spacing:1px;">Route Visual Map</p>
              <div style="border-radius:8px; overflow:hidden; border:1px solid #1a3a1a;">
                <img src="{map_url}" alt="Route Map" width="480" style="display:block; width:100%; height:auto; max-width:100%; border:0;" />
              </div>
            </td>
          </tr>
        </table>
        """

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
              <img src="{site_url}/logo.png" alt="COS Tesla Logo" style="display: block; margin: 0 auto 15px; height: 60px; width: auto;" />
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
                        <td align="right" style="white-space:nowrap; vertical-align:top;">
                          <p style="margin:0; color:#4ade80; font-size:11px; font-family:Arial,sans-serif; background:#1a3a1a; padding:4px 10px; border-radius:20px; display:inline-block;">100% Electric</p>
                          {fsd_badge}
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
                    {map_section}
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
