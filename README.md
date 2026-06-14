# SummitOS Web Experience (V2)

The central digital command center for SummitOS operations. This Next.js application powers the client-facing booking experience, real-time fleet tracking, and dynamic pricing engine for the transportation service.

## 🚀 Features

### 1. **Dynamic Booking Engine**
- **Smart Route Input**: Auto-contextualizes addresses (e.g., "1194 Magnolia" -> "Colorado Springs").
- **Multi-Leg Support**: Handles one-way, round-trips, and multi-stop itineraries with ease.
- **Dynamic Pricing**: Real-time quote generation based on:
    - Distance (Google Maps Matrix API)
    - Deadhead calculations (Driver dispatch distance)
    - "Teller County" mountain surcharges
    - Flight/Airport detection
    - Wait time & Layover logic

### 2. **Interactive Route Map**
- **Live Visuals**: Displays the exact route, stops, and traffic conditions using Google Maps.
- **"Night Mode" Styling**: Custom dark-themed map to match the premium brand aesthetic.
- **Pop-Out Capability**: Map can be popped out into a separate window for multi-monitor dispatcher setups.

### 3. **Mission Control Integrations**
- **Microsoft Graph**: Seamlessly links with Outlook/Bookings availability.
- **Resend API**: Transactional email notifications for trip confirmations.
- **Tessie API**: (In Progress) Live vehicle telemetry and battery status.

### 4. **System Emulator**
- **Virtual Telemetry**: Manually override vehicle GPS, speed, and battery status for testing.
- **Broadcast Sync**: Updates live maps across all active sessions via BroadcastChannel API.
- **Scenario Testing**: Run automated "driving" simulations to verify map responsiveness.

---

## 🛠️ Tech Stack

- **Framework**: [Next.js 14](https://nextjs.org/) (Static Export)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) + Glassmorphism Design System
- **Maps**: Google Maps JavaScript API + React Google Maps
- **Backend API**: Python Azure Functions (Standalone)
- **Deployment**: Azure Static Web Apps (Frontend) + Azure Functions (Backend)

---

## 📦 Getting Started

### 1. Prerequisites
- Node.js 18+
- npm or yarn

### 2. Installation
```bash
# Install dependencies
npm install
```

### 3. Environment Setup
Create a `.env.local` file in the root directory:
```bash
# Google Maps (Required for Geocoding & Routing)
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY="your_api_key_here"

# Microsoft Graph (Required for Calendar/Bookings)
AZURE_TENANT_ID=""
AZURE_CLIENT_ID=""
AZURE_CLIENT_SECRET=""

# Resend (Required for Emails)
RESEND_API_KEY=""
```

### 4. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to see the result.

---

## 🚢 Deployment

The project is deployed via GitHub Actions to **Azure Static Web Apps**.
1. Push changes to the `master` branch.
2. The GitHub Action in `.github/workflows/azure-static-web-apps-*.yml` will trigger automatically.
3. Secrets (API Keys, etc.) are managed in **GitHub Repository Secrets**.

---

## 📄 License
Proprietary software for SummitOS operations.
