# How to Fix the Cached Page Issue

## The Problem
Your browser is showing the old cached version of the `/book` page. The code has been updated correctly, but the browser hasn't refreshed.

## Solution - Try these steps in order:

### 1. Hard Refresh (Try this first)
**Windows/Linux**: Press `Ctrl + Shift + R` or `Ctrl + F5`
**Mac**: Press `Cmd + Shift + R`

This forces the browser to reload without using cache.

### 2. Clear Browser Cache for This Site
1. Press `F12` to open Developer Tools
2. Right-click the refresh button (while DevTools is open)
3. Select "Empty Cache and Hard Reload"

### 3. Restart Dev Server
If the above doesn't work, restart your Next.js dev server:

```powershell
# Stop the current dev server (Ctrl+C in the terminal where it's running)
# Then restart it:
npm run dev
```

### 4. Delete Next.js Cache (Nuclear option)
If nothing else works:

```powershell
# Stop dev server first, then:
Remove-Item -Recurse -Force .next
npm run dev
```

## What Changed
The `/book` page now uses `BookingEngine` (with calendar) instead of `BookingForm` (with Microsoft Bookings link).

## Expected Result
After clearing cache, you should see:
- The new booking engine interface
- Red "Continue to Calendar" button
- No white "Book Your Ride" button
- No redirect to Microsoft Bookings
