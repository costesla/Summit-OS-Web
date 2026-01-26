from typing import Dict, Any, Optional

class PricingEngine:
    """
    SummitOS Pricing Engine v2.0
    Python port of the high-precision tiered pricing logic.
    """
    
    @staticmethod
    def calculate_trip_price(
        distance_miles: float,
        stops_count: int = 0,
        is_teller_county: bool = False,
        wait_time_hours: float = 0.0
    ) -> Dict[str, Any]:
        
        # 1. Calculate Base & Distance Fare (Tiered)
        fixed_base = 15.00
        tier1_charge = 0.0
        tier2_charge = 0.0

        if distance_miles <= 5.0:
            # FLAT BASE
            mileage_charge = 0.0
        elif distance_miles <= 20.0:
            # TIER 1 ZONE
            tier1_miles = distance_miles - 5.0
            tier1_charge = tier1_miles * 1.75
            mileage_charge = tier1_charge
        else:
            # TIER 2 ZONE (Long Haul)
            tier1_miles = 15.0  # Full 15 miles of Tier 1 (5.0 to 20.0)
            tier1_charge = tier1_miles * 1.75  # $26.25
            
            tier2_miles = distance_miles - 20.0
            tier2_charge = tier2_miles * 1.25
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
            "total": round(total, 2)
        }
