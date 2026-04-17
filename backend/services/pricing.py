from typing import Dict, Any, Optional

class PricingEngine:
    """
    SummitOS Pricing Engine v3.0
    Python port of the high-precision pricing logic.
    $30 base. No mileage rate.
    Supports customer-specific pricing overrides.
    """
    
    @staticmethod
    def calculate_trip_price(
        distance_miles: float,
        stops_count: int = 0,
        is_teller_county: bool = False,
        wait_time_hours: float = 0.0,
        customer_email: Optional[str] = None,
        is_out_of_county: bool = False
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
                    base_fare = custom_pricing.get("base_fare", 30.00)
                    rate_per_mile = custom_pricing.get("rate_per_mile", custom_pricing.get("tier1_rate", 1.75))
                    
                    if is_out_of_county and rate_per_mile == 0.0:
                        rate_per_mile = 1.75
                        
                    free_miles = custom_pricing.get("free_miles", 5.0)
                    
                    # Calculate with custom rates
                    return PricingEngine._calculate_tiered_price(
                        distance_miles=distance_miles,
                        base_fare=base_fare,
                        rate_per_mile=rate_per_mile,
                        free_miles=free_miles,
                        stops_count=stops_count,
                        is_teller_county=is_teller_county,
                        wait_time_hours=wait_time_hours,
                        pricing_type="custom_tiered",
                        customer_tier=custom_pricing.get("description", "Custom pricing")
                    )
        
        # Standard pricing (no custom pricing found or no email provided)
        return PricingEngine._calculate_tiered_price(
            distance_miles=distance_miles,
            base_fare=30.00,
            rate_per_mile=1.50 if is_out_of_county else 0.0,
            free_miles=5.0 if is_out_of_county else 0.0,
            stops_count=stops_count,
            is_teller_county=is_teller_county,
            wait_time_hours=wait_time_hours,
            pricing_type="standard",
            customer_tier="Standard pricing v4.0 (2026)" + (" (Out of County Surcharge)" if is_out_of_county else "")
        )
        
    @staticmethod
    def calculate_bundle_price(
        distance_miles: float,
        is_teller_county: bool = False
    ) -> Dict[str, Any]:
        """
        Daily Exclusivity Bundle logic: Flat $100 up to 50 miles. +$1.75/mi overage.
        """
        bundle_price = 100.00
        free_miles = 50.0
        rate_per_mile = 1.75
        
        billable_miles = max(0.0, distance_miles - free_miles)
        mileage_charge = billable_miles * rate_per_mile
        
        teller_fee = 15.00 if is_teller_county else 0.0
        
        total = bundle_price + mileage_charge + teller_fee
        
        return {
            "baseFare": round(bundle_price, 2),
            "overage": round(mileage_charge, 2),
            "deadheadFee": 0.0,
            "stopFee": 0.0,
            "tellerFee": round(teller_fee, 2),
            "waitFee": 0.0,
            "total": round(total, 2),
            "pricing_type": "bundle",
            "customer_tier": "Daily Exclusivity Bundle"
        }
    
    @staticmethod
    def _calculate_tiered_price(
        distance_miles: float,
        base_fare: float,
        rate_per_mile: float = 1.75,
        free_miles: float = 5.0,
        stops_count: int = 0,
        is_teller_county: bool = False,
        wait_time_hours: float = 0.0,
        pricing_type: str = "standard",
        customer_tier: str = "Standard"
    ) -> Dict[str, Any]:
        """
        Internal method: flat rate after free_miles window.
        """
        fixed_base = base_fare
        billable_miles = max(0.0, distance_miles - free_miles)
        mileage_charge = billable_miles * rate_per_mile

        # Extra Fees
        stop_fee = stops_count * 5.00
        teller_fee = 15.00 if is_teller_county else 0.0
        wait_fee = wait_time_hours * 20.00
        deadhead_fee = 0.0  # Deprecated

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
