from typing import Dict, Any, Optional

class PricingEngine:
    """
    SummitOS Pricing Engine v3.0 (Effective September 1, 2026)
    - Base Fare: $25.00
    - Road Mileage: $2.00 per mile (calculated via Google Distance Matrix API from mile 0)
    - Denver Airport (DEN) Corridor Minimum Floor: $225.00
    - Toll Pass-Through (DEN / E-470): $20.00
    - Mountain Surcharge (Teller County): $15.00
    - Intermediate Waypoints: $5.00 / stop
    - Driver Standby / Wait Time: $25.00 / hour
    """
    
    @staticmethod
    def calculate_trip_price(
        distance_miles: float,
        stops_count: int = 0,
        is_teller_county: bool = False,
        is_denver_airport: bool = False,
        wait_time_hours: float = 0.0,
        customer_email: Optional[str] = None,
        is_out_of_county: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate trip price with support for customer-specific pricing and v3.0 standard model.
        
        Args:
            distance_miles: Trip distance in miles
            stops_count: Number of additional stops
            is_teller_county: Whether trip is in Teller County
            is_denver_airport: Whether trip is to/from Denver Airport (DEN)
            wait_time_hours: Wait time in hours
            customer_email: Customer email for pricing lookup
            is_out_of_county: Out-of-county flag
            
        Returns:
            Dictionary with pricing breakdown
        """
        
        # Check for customer-specific pricing
        if customer_email:
            try:
                from services.customer_pricing import CustomerPricingProfile
                custom_pricing = CustomerPricingProfile.get_customer_pricing(customer_email)
                
                if custom_pricing:
                    if "flat_rate" in custom_pricing:
                        flat_rate = custom_pricing["flat_rate"]
                        return {
                            "baseFare": round(flat_rate, 2),
                            "mileageFare": 0.0,
                            "overage": 0.0,
                            "deadheadFee": 0.0,
                            "stopFee": 0.0,
                            "tellerFee": 0.0,
                            "tollFee": 0.0,
                            "waitFee": 0.0,
                            "corridorAdjustment": 0.0,
                            "total": round(flat_rate, 2),
                            "pricing_type": "flat_rate",
                            "customer_tier": custom_pricing.get("description", "Custom pricing")
                        }
            except Exception:
                pass
        
        # Standard v3.0 Pricing Model (Effective September 1, 2026)
        fixed_base = 25.00
        rate_per_mile = 2.00
        den_floor = 225.00

        mileage_charge = round(distance_miles * rate_per_mile, 2)
        stop_fee = stops_count * 5.00
        teller_fee = 15.00 if is_teller_county else 0.0
        toll_fee = 20.00 if is_denver_airport else 0.0
        wait_fee = wait_time_hours * 25.00

        subtotal = fixed_base + mileage_charge + stop_fee + teller_fee + toll_fee + wait_fee

        corridor_adjustment = 0.0
        if is_denver_airport and subtotal < den_floor:
            corridor_adjustment = round(den_floor - subtotal, 2)

        total = subtotal + corridor_adjustment

        return {
            "baseFare": round(fixed_base, 2),
            "mileageFare": round(mileage_charge, 2),
            "overage": round(mileage_charge, 2),  # Backward compatibility for legacy UI hooks
            "deadheadFee": 0.0,
            "stopFee": round(stop_fee, 2),
            "tellerFee": round(teller_fee, 2),
            "tollFee": round(toll_fee, 2),
            "waitFee": round(wait_fee, 2),
            "corridorAdjustment": round(corridor_adjustment, 2),
            "total": round(total, 2),
            "pricing_type": "standard_v3",
            "customer_tier": "SummitOS Standard v3.0 (Effective Sept 1, 2026)"
        }

