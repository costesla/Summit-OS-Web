"""
COS Tesla LLC - Centralized Privacy-Safe Location Normalizer
Author: Google Antigravity & Peter Teehan
Ensures zero street addresses, unit numbers, coordinates, or PII appear in reports.
"""

import re
import html

# Precise address/keyword-to-alias dictionary for confirmed Supercharger locations
SUPERCHARGER_ADDRESS_MAP = {
    "23 east tyler street": "Lincoln Center Supercharger",
    "23 e tyler st": "Lincoln Center Supercharger",
    "lincoln center": "Lincoln Center Supercharger",
    "2727 north cascade avenue": "North Cascade Supercharger",
    "2727 n cascade ave": "North Cascade Supercharger",
    "north cascade": "North Cascade Supercharger",
    "8110 interquest pkwy": "Interquest Supercharger",
    "interquest": "Interquest Supercharger",
    "965 diamond dr": "Castle Rock Supercharger",
    "castle rock": "Castle Rock Supercharger",
}

# Approved municipal entities across Colorado operating territory
APPROVED_MUNICIPALITIES = [
    "Colorado Springs", "Peyton", "Falcon", "Palmer Lake", "Monument",
    "Manitou Springs", "Fountain", "Woodland Park", "Black Forest",
    "Castle Rock", "Denver", "Centennial", "Aurora", "Lone Tree"
]

# Approved operational hub & venue aliases
APPROVED_VENUE_ALIASES = {
    "the farm": "The Farm, Colorado Springs",
    "denver international airport": "Denver International Airport (DEN)",
    "colorado springs airport": "Colorado Springs Airport (COS)",
}

# Approved / Known merchant brands
KNOWN_MERCHANTS = [
    "Maverik", "Dairy Queen", "Rocky Mountain Calva", "Starbucks", "McDonald's",
    "Kum & Go", "King Soopers", "Target", "Costco", "Subway", "Wendy's",
    "Loaf 'N Jug", "7-Eleven", "Tesla", "AutoZone", "O'Reilly"
]


def clean_location(raw_text: str, category: str = "") -> str:
    """
    Normalizes location or expense note text to a privacy-safe label.
    Never returns a street name or address number.
    Returns an approved merchant name, supercharger alias, municipality, or general region.
    """
    if not raw_text:
        if category in ("fastfood", "meals"):
            return "Local Road Meal"
        elif category == "charging":
            return "Regional Supercharger"
        return "Regional Operations"

    text = str(raw_text).strip()
    text_norm = text.lower().replace(".", ",")

    # 1. Supercharger aliases (charging category or explicit supercharger reference)
    if category == "charging" or "supercharger" in text_norm:
        # Check explicit address/keyword map
        for key, alias in SUPERCHARGER_ADDRESS_MAP.items():
            if key in text_norm:
                return alias

        # Check for pattern like "Supercharger - [Location]" or "[Location] Supercharger"
        m1 = re.search(r"supercharger\s*[-–:]\s*([a-z\s]+)", text_norm)
        if m1:
            candidate = m1.group(1).strip()
            for key, alias in SUPERCHARGER_ADDRESS_MAP.items():
                if key in candidate:
                    return alias
            for muni in APPROVED_MUNICIPALITIES:
                if muni.lower() in candidate:
                    return f"{muni} Supercharger"

        m2 = re.search(r"([a-z\s]+)\s+supercharger", text_norm)
        if m2:
            candidate = m2.group(1).strip()
            for key, alias in SUPERCHARGER_ADDRESS_MAP.items():
                if key in candidate:
                    return alias
            for muni in APPROVED_MUNICIPALITIES:
                if muni.lower() in candidate:
                    return f"{muni} Supercharger"

        # Check municipal entities for charging
        for muni in APPROVED_MUNICIPALITIES:
            if re.search(rf"\b{re.escape(muni.lower())}\b", text_norm):
                return f"{muni} Supercharger"

        return "Regional Supercharger"

    # 2. Merchant extraction from receipt notes or category
    if "merchant:" in text_norm or category in ("fastfood", "meals", "capital_maintenance", "maintenance", "expense"):
        # Check structured 'Merchant: [Name]'
        if "merchant:" in text_norm:
            m = re.search(r"merchant:\s*([^.,;]+)", text, re.IGNORECASE)
            if m:
                merchant = m.group(1).strip()
                # Clean up punctuation and uppercase
                if merchant.isupper() and len(merchant) > 3:
                    return merchant.title()
                return merchant

        # Check known merchant brands
        for km in KNOWN_MERCHANTS:
            if re.search(rf"\b{re.escape(km.lower())}\b", text_norm):
                return km

        # Check for merchant name before dash or store number: e.g. "Maverik - Store #412"
        m_dash = re.match(r"^([A-Za-z0-9\s'&]+?)\s*[-–]\s*(?:store|fuel|shop|branch|#|\d)", text, re.IGNORECASE)
        if m_dash:
            name = m_dash.group(1).strip()
            if len(name) > 2 and not any(suff in name.lower() for suff in ["ave", "st", "rd", "dr", "pkwy", "blvd", "hwy"]):
                return name.title() if name.isupper() else name

        # If it looks like a clean merchant title without street address indicators
        if not re.search(r"\b\d{1,5}\s+[A-Za-z]", text) and not any(suff in text_norm for suff in ["ave", "street", "st", "road", "rd", "dr", "pkwy", "blvd", "hwy"]):
            # Split off any sub-notes
            clean_name = text.split("-")[0].split("(")[0].strip()
            if clean_name and len(clean_name) <= 35:
                return clean_name.title() if clean_name.isupper() else clean_name

        if category in ("fastfood", "meals"):
            return "Local Road Meal"
        elif category in ("capital_maintenance", "maintenance"):
            return "Fleet Maintenance"

    # 3. Approved venue aliases (trips / operational hubs)
    for v_key, v_alias in APPROVED_VENUE_ALIASES.items():
        if re.search(rf"\b{re.escape(v_key)}\b", text_norm):
            return v_alias

    # 4. Municipality detection (trips / corridors)
    for muni in APPROVED_MUNICIPALITIES:
        if re.search(rf"\b{re.escape(muni.lower())}\b", text_norm):
            return f"{muni}, CO"

    # 5. Fallback without exposing street names, numbers, or personal coordinates
    return "Regional Operations"
