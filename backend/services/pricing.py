from typing import Dict, Any, Optional

class PricingEngine:
    """
    SummitOS Pricing Engine v2.0
    Python port of the high-precision tiered pricing logic.
    Now supports customer-specific pricing overrides.
    """
    
    @staticmethod
    def calculate_trip_price(
        distance_miles: float,
        stops_count: int = 0,
        is_teller_county: bool = False,
        wait_time_hours: float = 0.0,
        customer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate trip price with support for customer-specific pricing
        
        Args:
            distance_miles: Trip distance in miles
            stops_count: Number of additional stops
            is_teller_county: Whether trip is in Teller County
            wait_time_hours: Wait time in hours
            customer_email: Customer email for pricing lookup
            
        Returns:
            Dictionary with pricing breakdown
        """
        
        # Check for customer-specific pricing
        if customer_email:
            from services.customer_pricing import CustomerPricingProfile
            custom_pricing = CustomerPricingProfile.get_customer_pricing(customer_email)
            
            if custom_pricing:
                # Check if this is a flat rate pricing
                if "flat_rate" in custom_pricing:
                    flat_rate = custom_pricing["flat_rate"]
                    return {
                        "baseFare": round(flat_rate, 2),
                        "overage": 0.0,
                        "deadheadFee": 0.0,
                        "stopFee": 0.0,
                        "tellerFee": 0.0,
                        "waitFee": 0.0,
                        "total": round(flat_rate, 2),
                        "pricing_type": "flat_rate",
                        "customer_tier": custom_pricing.get("description", "Custom pricing")
                    }
                
                # Use custom tiered pricing if available
                if "base_fare" in custom_pricing:
                    base_fare = custom_pricing.get("base_fare", 15.00)
                    tier1_rate = custom_pricing.get("tier1_rate", 1.75)
                    tier2_rate = custom_pricing.get("tier2_rate", 1.25)
                    
                    # Calculate with custom rates
                    return PricingEngine._calculate_tiered_price(
                        distance_miles=distance_miles,
                        base_fare=base_fare,
                        tier1_rate=tier1_rate,
                        tier2_rate=tier2_rate,
                        stops_count=stops_count,
                        is_teller_county=is_teller_county,
                        wait_time_hours=wait_time_hours,
                        pricing_type="custom_tiered",
                        customer_tier=custom_pricing.get("description", "Custom pricing")
                    )
        
        # Standard pricing (no custom pricing found or no email provided)
        return PricingEngine._calculate_tiered_price(
            distance_miles=distance_miles,
            base_fare=15.00,
            tier1_rate=1.75,
            tier2_rate=1.25,
            stops_count=stops_count,
            is_teller_county=is_teller_county,
            wait_time_hours=wait_time_hours,
            pricing_type="standard",
            customer_tier="Standard pricing (2026)"
        )
    
    @staticmethod
    def _calculate_tiered_price(
        distance_miles: float,
        base_fare: float,
        tier1_rate: float,
        tier2_rate: float,
        stops_count: int = 0,
        is_teller_county: bool = False,
        wait_time_hours: float = 0.0,
        pricing_type: str = "standard",
        customer_tier: str = "Standard"
    ) -> Dict[str, Any]:
        """
        Internal method to calculate tiered pricing
        """
        
        # 1. Calculate Base & Distance Fare (Tiered)
        fixed_base = base_fare
        tier1_charge = 0.0
        tier2_charge = 0.0

        if distance_miles <= 5.0:
            # FLAT BASE
            mileage_charge = 0.0
        elif distance_miles <= 20.0:
            # TIER 1 ZONE
            tier1_miles = distance_miles - 5.0
            tier1_charge = tier1_miles * tier1_rate
            mileage_charge = tier1_charge
        else:
            # TIER 2 ZONE (Long Haul)
            tier1_miles = 15.0  # Full 15 miles of Tier 1 (5.0 to 20.0)
            tier1_charge = tier1_miles * tier1_rate
            
            tier2_miles = distance_miles - 20.0
            tier2_charge = tier2_miles * tier2_rate
            mileage_charge = tier1_charge + tier2_charge

        # 2. Extra Fees
        stop_fee = stops_count * 5.00
        teller_fee = 15.00 if is_teller_county else 0.0
        wait_fee = wait_time_hours * 20.00
        
        # Deadhead is deprecated (0.0)
        deadhead_fee = 0.0

        # 3. Total
        total = fixed_base + mileage_charge + deadhead_fee + stop_fee + teller_fee + wait_fee

        return {
            "baseFare": round(fixed_base, 2),
            "overage": round(mileage_charge, 2),
            "deadheadFee": round(deadhead_fee, 2),
            "stopFee": round(stop_fee, 2),
            "tellerFee": round(teller_fee, 2),
            "waitFee": round(wait_fee, 2),
            "total": round(total, 2),
            "pricing_type": pricing_type,
            "customer_tier": customer_tier
        }
