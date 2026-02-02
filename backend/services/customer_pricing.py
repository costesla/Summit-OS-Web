"""
Customer Pricing Profiles for Grandfathered Customers
Allows custom pricing rules per customer email
"""

from typing import Dict, Any, Optional
from datetime import datetime

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
        
        # Jacquelyn - Flat $20/trip until March 1, 2026
        "jacquelyn.heslep@playaba.net": {
            "name": "Jacquelyn",
            "pricing_tier": "legacy_flat_20",
            "expires": "2026-03-01",
            "notes": "Flat $20/trip - migrates to regular pricing March 1, 2026"
        },
    }
    
    # Define pricing tiers
    PRICING_TIERS = {
        "current": {
            "base_fare": 15.00,
            "tier1_rate": 1.75,
            "tier2_rate": 1.25,
            "description": "Current standard pricing (2026)"
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
