# Microsoft Bookings Page Creation Guide

## Step-by-Step Instructions

### 1. Navigate to Microsoft Bookings
Go to: [https://outlook.office.com/bookings](https://outlook.office.com/bookings)

### 2. Create New Booking Page
Click **"Create a booking page"** or **"New booking business"**

### 3. Configure Business Details
- **Business Name**: `COS Tesla Private Trips` or `Private Trips`
- **Business Email**: `PrivateTrips@costesla.com`
- **Business Type**: Select "Transportation" or "Professional Services"
- **Time Zone**: Select your local time zone (likely Mountain Time - Denver)

### 4. Set Hours of Operation

Configure the following schedule **exactly**:

| Day | Hours |
|-----|-------|
| **Monday** | 4:00 AM – 10:00 PM |
| **Tuesday** | 4:00 AM – 10:00 PM |
| **Wednesday** | 4:00 AM – 10:00 PM |
| **Thursday** | 4:00 AM – 10:00 PM |
| **Friday** | 4:00 AM – 12:00 AM (midnight) |
| **Saturday** | 8:00 AM – 11:00 AM |
| **Sunday** | 8:00 AM – 6:00 PM |

**Important Notes**:
- For Friday, set end time to "12:00 AM" (next day/midnight)
- Use 12-hour format with AM/PM when entering times in Microsoft Bookings

### 5. Create Service

Click **"Services"** → **"Add a service"**

Configure:
- **Service Name**: `Private Trip Scheduling`
- **Description**: `Book your private Tesla transportation service. Final pricing determined by route.`
- **Duration**: `30 minutes` (default appointment slot)
- **Buffer Time Before**: `15 minutes`
- **Buffer Time After**: `15 minutes`
- **Price**: Leave blank or set to "Custom" (pricing handled by your booking engine)
- **Location**: `Customer Location` or `Flexible`

### 6. Configure Booking Page Settings

Go to **"Booking page"** settings:
- **Public booking page**: Enable ✅
- **Allow customers to book**: Enable ✅
- **Require customer information**: Enable ✅
  - Name (required)
  - Email (required)
  - Phone (required)
- **Send confirmation emails**: Enable ✅

### 7. Publish the Page

Click **"Publish"** or **"Make public"**

### 8. Obtain Public URL

After publishing, you'll see a public booking URL in this format:
```
https://outlook.office.com/book/[YourBookingPageID]@costesla.com/
```

**Copy this URL exactly** - you'll need it for the codebase update.

### 9. Test the Booking Page

1. Open the public URL in an incognito/private browser window
2. Verify hours of operation display correctly
3. Test booking a time slot
4. Confirm you receive the confirmation email

### 10. Provide the Following Information

Once complete, provide:
- ✅ **Public Booking URL**
- ✅ **Booking Page ID** (from the URL)
- ✅ **Confirmation** that the page is live and accessible

---

## Troubleshooting

**If Friday midnight doesn't work**: Some systems require setting Friday to end at "11:59 PM" and Saturday to start at "12:00 AM"

**If hours don't save**: Ensure you're using 24-hour format and clicking "Save" after each day

**If page won't publish**: Verify that at least one service is configured and business email is confirmed

---

## Next Steps After Creation

Once you provide the new booking URL, I will:
1. Update `BookingForm.tsx` line 200
2. Update `BookingEngine.tsx` line 497
3. Verify receipt engine integration
4. Test the complete booking flow
