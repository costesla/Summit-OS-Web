"""
Customer Pricing Profiles for Grandfathered Customers
Allows custom pricing rules per customer email
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import math

class CustomerPricingProfile:
    """
    Defines custom pricing rules for specific customers
    """
    
    # Grandfathered customers with custom pricing
    GRANDFATHERED_CUSTOMERS = {
        # Esmeralda - Flat $20/trip until March 1, 2026
        "esmii.lopez@hotmail.com": {
            "name": "Esmeralda",
            "pricing_tier": "legacy_flat_20",
            "expires": "2026-03-01",
            "notes": "Flat $20/trip - migrates to regular pricing March 1, 2026"
        },
        
        # Jacquelyn Heslep — deferred per-leg billing, capped at 2 legs/day
        # Rule:
        #   Non-AA one-way trip  = 1 leg  = $30, DEFERRED
        #   Non-AA round trip    = 2 legs = $60, DEFERRED (consumes both daily slots)
        #   Legs 3+ in same day  = $0, CREDIT
        #   AA-tagged trips      = $0, CREDIT always (outside leg cap entirely)
        #   Max billable/day     = $60
        "jacquelyn.heslep@playaba.net": {
            "name": "Jacquelyn Heslep",
            "pricing_tier": "jackie_deferred",
            "billing_model": "legs",
            "leg_rate": 30.00,
            "daily_leg_cap": 2,
            "aa_is_always_credit": True,
            "round_trip_threshold_mi": 0.25,
            "payment_status_default": "Deferred",
            "notes": "Non-AA: $30/leg, max 2 legs/day ($60/day cap). Round trip = 2 legs = $60 Deferred. AA trips = $0 Credit always."
        },
    }

    # Clients who pay via Venmo/Zelle/Cash and should NEVER be sent to Stripe
    VENMO_CLIENTS = set()

    @classmethod
    def is_venmo_client(cls, email: str) -> bool:
        """Return True if this customer pays out-of-band (Venmo/Zelle/Cash) and must bypass Stripe."""
        if not email:
            return False
        return email.lower().strip() in cls.VENMO_CLIENTS
    
    # Define pricing tiers
    PRICING_TIERS = {
        "comped": {
            "flat_rate": 0.00,
            "description": "Comped / charity rate (gifted)"
        },
        "jackie_deferred": {
            "leg_rate": 30.00,
            "daily_leg_cap": 2,
            "description": "Jackie per-leg deferred billing — $30/leg, max 2 legs ($60) per day. AA always $0."
        },
        "current": {
            "base_fare": 30.00,
            "rate_per_mile": 0.0,
            "free_miles": 0.0,
            "description": "Standard pricing v3.0 (2026)"
        },
        "flat_30": {
            "flat_rate": 30.00,
            "description": "Legacy flat $30/trip (Grandfathered)"
        },
        "legacy_flat_20": {
            "flat_rate": 20.00,
            "description": "Legacy flat $20/trip (expires March 1, 2026)"
        },
        "legacy_2024": {
            "base_fare": 10.00,
            "tier1_rate": 1.50,
            "tier2_rate": 1.00,
            "description": "Legacy 2024 pricing (grandfathered)"
        },
        "legacy_2025": {
            "base_fare": 12.00,
            "tier1_rate": 1.60,
            "tier2_rate": 1.10,
            "description": "Legacy 2025 pricing (grandfathered)"
        },
        "vip": {
            "base_fare": 15.00,
            "tier1_rate": 1.50,
            "tier2_rate": 1.00,
            "description": "VIP customer discount"
        }
    }
    
    @classmethod
    def is_pricing_expired(cls, expires_date: str) -> bool:
        """
        Check if a pricing tier has expired
        
        Args:
            expires_date: Expiration date in YYYY-MM-DD format
            
        Returns:
            True if expired, False otherwise
        """
        if not expires_date:
            return False
            
        try:
            import datetime
            from services.datetime_utils import normalize_to_utc
            try:
                import pytz
                tz = pytz.utc
            except ImportError:
                tz = datetime.timezone.utc
            
            expiry = normalize_to_utc(expires_date)
            now = datetime.datetime.now(tz)
            
            return now >= expiry
        except Exception as e:
            import logging
            logging.error(f"Pricing expiry check error: {e}")
            return False
    
    @classmethod
    def get_customer_pricing(cls, email: str) -> Optional[Dict[str, Any]]:
        """
        Get custom pricing for a customer by email
        Automatically handles expiration dates
        
        Args:
            email: Customer email address
            
        Returns:
            Customer pricing profile or None if not found or expired
        """
        if not email:
            return None
            
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # Check if customer has custom pricing
        if email in cls.GRANDFATHERED_CUSTOMERS:
            profile = cls.GRANDFATHERED_CUSTOMERS[email]
            
            # Check if pricing has expired
            if "expires" in profile:
                if cls.is_pricing_expired(profile["expires"]):
                    # Pricing expired, return None to use standard pricing
                    return None
            
            # If they reference a tier, merge it
            if "pricing_tier" in profile:
                tier_name = profile["pricing_tier"]
                if tier_name in cls.PRICING_TIERS:
                    tier_pricing = cls.PRICING_TIERS[tier_name].copy()
                    # Override with any custom values in profile
                    tier_pricing.update(profile)
                    return tier_pricing
            
            return profile
        
        return None
    
    @classmethod
    def add_grandfathered_customer(
        cls,
        email: str,
        name: str,
        pricing_tier: str = "legacy_2024",
        expires: Optional[str] = None,
        notes: str = ""
    ) -> bool:
        """
        Add a new grandfathered customer
        
        Args:
            email: Customer email
            name: Customer name
            pricing_tier: Pricing tier to use
            expires: Optional expiration date (YYYY-MM-DD)
            notes: Optional notes
            
        Returns:
            True if added successfully
        """
        email = email.lower().strip()
        
        if pricing_tier not in cls.PRICING_TIERS:
            raise ValueError(f"Invalid pricing tier: {pricing_tier}")
        
        customer_data = {
            "name": name,
            "pricing_tier": pricing_tier,
            "notes": notes
        }
        
        if expires:
            customer_data["expires"] = expires
        
        cls.GRANDFATHERED_CUSTOMERS[email] = customer_data
        
        return True
    
    @classmethod
    def list_grandfathered_customers(cls) -> Dict[str, Any]:
        """
        List all grandfathered customers with their status
        
        Returns:
            Dictionary of grandfathered customers with expiration status
        """
        result = {}
        for email, profile in cls.GRANDFATHERED_CUSTOMERS.items():
            profile_copy = profile.copy()
            
            # Add expiration status
            if "expires" in profile:
                profile_copy["is_expired"] = cls.is_pricing_expired(profile["expires"])
            else:
                profile_copy["is_expired"] = False
                
            result[email] = profile_copy
            
        return result
    
    @classmethod
    def get_pricing_tier(cls, tier_name: str) -> Optional[Dict[str, Any]]:
        """
        Get pricing tier details
        
        Args:
            tier_name: Name of the pricing tier
            
        Returns:
            Pricing tier details or None
        """
        return cls.PRICING_TIERS.get(tier_name)


# ---------------------------------------------------------------------------
# Jackie Billing Engine
# Enforces the per-leg deferred billing rule for Jacquelyn Heslep.
#
# Usage (in cloud_watcher rebuild):
#   result = JackieBillingEngine.classify_invoice(
#       tessie_label=label,
#       pickup_lat=..., pickup_lon=...,
#       dropoff_lat=..., dropoff_lon=...,
#       legs_already_billed_today=N
#   )
#   => {"fare": 60.00, "status": "Deferred", "legs_consumed": 2, "reason": "round_trip"}
# ---------------------------------------------------------------------------

class JackieBillingEngine:
    """
    Enforces Jackie Heslep's billing rules:
      - AA-tagged trip         => $0, Credit, 0 legs consumed
      - Round trip (dropoff within threshold of pickup) => $60, Deferred, 2 legs consumed
      - One-way non-AA         => $30, Deferred, 1 leg consumed
      - Legs beyond daily cap  => $0, Credit, 0 legs consumed
    """

    LEG_RATE       = 30.00
    DAILY_LEG_CAP  = 2
    # Round-trip threshold: dropoff within this many miles of pickup = return to origin
    ROUND_TRIP_THRESHOLD_MI = 0.25

    # Labels / classifications that indicate an AA (Alcoholics Anonymous) trip
    AA_MARKERS = ["aa ", " aa", "aa_", "_aa", "aa-", "-aa", "alcoholics", " aa "]

    @staticmethod
    def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Straight-line distance between two lat/lon points in miles."""
        R = 3958.8  # Earth radius in miles
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @classmethod
    def is_aa_trip(cls, tessie_label: str = "", classification: str = "") -> bool:
        """Return True if this drive is AA-tagged and should always be $0 Credit."""
        combined = f" {(tessie_label or '').lower()} {(classification or '').lower()} "
        return any(marker in combined for marker in cls.AA_MARKERS) or \
               (classification or "").strip().lower() == "aa"

    @classmethod
    def is_round_trip(
        cls,
        pickup_lat: Optional[float], pickup_lon: Optional[float],
        dropoff_lat: Optional[float], dropoff_lon: Optional[float],
        address_pickup: str = "", address_dropoff: str = ""
    ) -> bool:
        """
        Return True if this trip returns near its origin (round trip = 2 legs).

        Uses haversine distance if coordinates are available.
        Falls back to street-number comparison on the same street name.
        """
        if all(v is not None for v in [pickup_lat, pickup_lon, dropoff_lat, dropoff_lon]):
            try:
                dist = cls._haversine_mi(pickup_lat, pickup_lon, dropoff_lat, dropoff_lon)
                return dist <= cls.ROUND_TRIP_THRESHOLD_MI
            except Exception:
                pass

        # Address fallback: same street, house numbers within 10
        if address_pickup and address_dropoff:
            import re
            def parse_addr(addr: str):
                m = re.match(r"(\d+)\s+(.+?)(?:,|$)", addr.strip())
                if m:
                    return int(m.group(1)), m.group(2).lower().strip()
                return None, None

            num1, street1 = parse_addr(address_pickup)
            num2, street2 = parse_addr(address_dropoff)
            if street1 and street1 == street2 and num1 is not None and num2 is not None:
                return abs(num1 - num2) <= 10

        return False

    @classmethod
    def classify_invoice(
        cls,
        tessie_label: str = "",
        classification: str = "",
        pickup_lat: Optional[float] = None,
        pickup_lon: Optional[float] = None,
        dropoff_lat: Optional[float] = None,
        dropoff_lon: Optional[float] = None,
        address_pickup: str = "",
        address_dropoff: str = "",
        legs_already_billed_today: int = 0
    ) -> Dict[str, Any]:
        """
        Classify a Jackie invoice and return fare + status.

        Returns:
            {
                "fare": float,
                "status": str,        # "Deferred" | "Credit"
                "legs_consumed": int, # 0, 1, or 2
                "reason": str         # human-readable explanation
            }
        """
        # Rule 1: AA gate — always $0 Credit regardless of anything else
        if cls.is_aa_trip(tessie_label, classification):
            return {
                "fare": 0.00,
                "status": "Credit",
                "legs_consumed": 0,
                "reason": "aa_trip"
            }

        # Rule 2: Round-trip detection
        round_trip = cls.is_round_trip(
            pickup_lat, pickup_lon, dropoff_lat, dropoff_lon,
            address_pickup, address_dropoff
        )
        legs_needed = 2 if round_trip else 1

        # Rule 3: Daily cap check
        remaining_legs = max(0, cls.DAILY_LEG_CAP - legs_already_billed_today)

        if remaining_legs == 0:
            return {
                "fare": 0.00,
                "status": "Credit",
                "legs_consumed": 0,
                "reason": f"daily_cap_reached ({legs_already_billed_today} legs already billed)"
            }

        if legs_needed > remaining_legs:
            # Partial: would exceed cap — bill only remaining legs
            billable_legs = remaining_legs
            reason = f"partial_cap (needed {legs_needed}, only {remaining_legs} remaining)"
        else:
            billable_legs = legs_needed
            reason = "round_trip" if round_trip else "one_way"

        return {
            "fare": round(billable_legs * cls.LEG_RATE, 2),
            "status": "Deferred",
            "legs_consumed": billable_legs,
            "reason": reason
        }

