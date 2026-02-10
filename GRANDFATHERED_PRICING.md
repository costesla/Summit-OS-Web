# Grandfathered Customer Pricing System

## Overview

The system now supports customer-specific pricing for grandfathered customers. This allows you to:
- Set flat-rate pricing for specific customers
- Set custom tiered pricing rates
- Automatically expire pricing on a specific date
- Track which customers have special pricing

## Current Grandfathered Customers

### Esmeralda & Jacquelyn
- **Pricing**: Flat $20 per trip (any distance)
- **Expires**: March 1, 2026
- **Status**: Active until expiration
- **After Expiration**: Automatically switches to standard 2026 pricing

**Note**: You need to update their actual email addresses in `backend/services/customer_pricing.py`

## How It Works

### 1. Customer Makes a Booking
- Customer enters their email in the booking form
- System checks if email matches a grandfathered customer
- If match found and not expired → applies special pricing
- If no match or expired → applies standard pricing

### 2. Automatic Expiration
- On March 1, 2026, Esmeralda and Jacquelyn's pricing automatically expires
- They will see standard pricing in quotes
- No manual intervention needed

### 3. Pricing Display
- Customers see their applicable price in real-time
- Receipt shows the pricing tier used
- You can track which pricing was applied

## Configuration

### Adding a Grandfathered Customer

Edit `backend/services/customer_pricing.py`:

```python
GRANDFATHERED_CUSTOMERS = {
    "customer@email.com": {
        "name": "Customer Name",
        "pricing_tier": "legacy_flat_20",  # or other tier
        "expires": "2026-03-01",  # Optional
        "notes": "Reason for special pricing"
    },
}
```

### Available Pricing Tiers

1. **legacy_flat_20** - Flat $20/trip (any distance)
2. **current** - Standard 2026 pricing ($15 base + tiered)
3. **legacy_2024** - Old 2024 pricing ($10 base + lower rates)
4. **legacy_2025** - 2025 pricing ($12 base + medium rates)
5. **vip** - VIP discount pricing

### Creating Custom Tiers

Add to `PRICING_TIERS` in `customer_pricing.py`:

```python
"my_custom_tier": {
    "flat_rate": 25.00,  # For flat rate
    # OR
    "base_fare": 12.00,  # For tiered pricing
    "tier1_rate": 1.50,
    "tier2_rate": 1.00,
    "description": "Description of this tier"
}
```

## Testing

### Test Grandfathered Pricing

Use the test script:

```bash
python backend/scripts/test_grandfathered_pricing.py
```

This will:
- Test Esmeralda's pricing (should be $20 flat)
- Test Jacquelyn's pricing (should be $20 flat)
- Test a regular customer (should be standard pricing)
- Test after March 1, 2026 (should be standard for all)

## Management Commands

### List All Grandfathered Customers

```python
from services.customer_pricing import CustomerPricingProfile

customers = CustomerPricingProfile.list_grandfathered_customers()
for email, profile in customers.items():
    print(f"{profile['name']}: {profile['pricing_tier']}")
    if profile.get('is_expired'):
        print("  ⚠️  EXPIRED")
```

### Add a New Grandfathered Customer

```python
from services.customer_pricing import CustomerPricingProfile

CustomerPricingProfile.add_grandfathered_customer(
    email="newcustomer@email.com",
    name="New Customer",
    pricing_tier="legacy_flat_20",
    expires="2026-06-01",
    notes="Special pricing until June"
)
```

## Important Notes

### ⚠️ Update Email Addresses

The system currently has placeholder emails:
- `esmeralda@example.com` → Replace with Esmeralda's real email
- `jacquelyn@example.com` → Replace with Jacquelyn's real email

Update these in `backend/services/customer_pricing.py`

### Email Matching

- Emails are case-insensitive
- Whitespace is automatically trimmed
- Customer must enter the exact email used in the system

### Pricing Display

When a customer gets a quote, the response includes:
- `pricing_type`: "flat_rate", "custom_tiered", or "standard"
- `customer_tier`: Description of which pricing tier was used

## Deployment

After updating customer emails:

```bash
cd backend
func azure functionapp publish summitos-api
```

## Future Enhancements

Possible improvements:
1. Admin dashboard to manage grandfathered customers
2. Database storage instead of code-based configuration
3. Automatic email notifications before pricing expires
4. Promo codes for temporary pricing
5. Customer-specific discounts (percentage-based)

## Troubleshooting

### Customer Not Getting Special Pricing

1. **Check email match**: Ensure email in system matches exactly
2. **Check expiration**: Verify pricing hasn't expired
3. **Check logs**: Look for pricing tier in API response
4. **Test directly**: Use test script to verify

### Pricing Not Expiring

1. **Check date format**: Must be "YYYY-MM-DD"
2. **Check server time**: Ensure server clock is correct
3. **Test expiration logic**: Use test script with future dates

## Support

For questions or issues:
- Check `backend/services/customer_pricing.py` for configuration
- Review `backend/services/pricing.py` for pricing logic
- Test with `backend/scripts/test_grandfathered_pricing.py`
