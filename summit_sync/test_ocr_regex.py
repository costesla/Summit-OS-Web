import re

# Text from Image 2 (Earnings Breakdown)
# Note: This view does NOT show Rider Payment or Service Fee, so "Platform Cut" is impossible here.
# But we must ensure we capturing the Driver Earnings ($17.09) and not just the Fare ($11.99).
text_earnings_view = """
Trip Details
Duration 8 min 41 sec
Distance 0.61 mi
Oak Pl, Manitou Springs...
Oak Pl, Manitou Springs...
3 points earned
$5.10 tip included

Your earnings
Fare $11.99
Fare $11.50
Additional Time at Stop $0.49
Tip $5.10
Your earnings $17.09
"""

def parse_uber_detailed_test(text):
    data = {"driver_earnings": 0.0, "is_detailed": False}

    # 1. Driver Earnings
    # Regex currently: r"(?:Upfront fare|Your earnings|You earned|Offer).*?[\$]([0-9]+\.[0-9]{2})"
    # with DOTALL.
    # In this text: "Your earnings" appears twice.
    # First time: "Your earnings \n Fare $11.99" -> It will grab $11.99
    # We want the *Total* "Your earnings $17.09" at the bottom? 
    # Or matches "Your earnings" header?
    
    match = re.search(r"(?:Upfront fare|Your earnings|You earned|Offer).*?[\$]([0-9]+\.[0-9]{2})", text, re.IGNORECASE | re.DOTALL)
    if match:
        data["driver_earnings"] = float(match.group(1))
        data["is_detailed"] = True
        
    # Check for "Total" if "Your earnings" grabbed a sub-item?
    # Strategy: If "Your earnings" is followed by "Fare", maybe finding the MAX dollar amount labeled "Your earnings" or "Total"?
    
    return data

print("--- Earnings View Test ---")
print(parse_uber_detailed_test(text_earnings_view))
