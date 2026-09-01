---
name: spatial-telemetry-engine
description: >-
  Guide and architectural patterns for joining vehicle CAN bus telemetry (Tessie energy, mileage, duration)
  with commercial rideshare (Uber/Lyft) and private booking ledgers into high-integrity spatial APIs and resilient web map interfaces.
---

# Spatial Telemetry Engine & Commercial Yield Analytics

This skill documents the end-to-end architecture for building, securing, and visualizing real vehicle energy metrics joined with financial trip data.

---

## 1. Data Pipeline & Formula Invariants

### Dynamic Net Yield Formula
Never store static net hourly yields when energy or wear costs may be variable. Compute dynamically:
$$\text{Net Yield (\$/hr)} = \frac{\text{Gross Fare} - (\text{kWh} \times \text{Energy Rate}) - (\text{Miles} \times \text{Wear Rate})}{\text{Engaged Hours}}$$

* `Gross Fare`: Raw platform payout or invoiced private amount.
* `kWh`: Measured battery drain from CAN bus telemetry (`Tessie Drives`).
* `Engaged Hours`: Total active driving time $(\text{minutes} / 60)$.
* `Energy Rate`: Current local blended cost per kWh (e.g., \$0.45/kWh supercharging baseline).
* `Wear Rate`: Depreciated maintenance & tire wear cost per mile (e.g., \$0.13/mi).

---

## 2. Privacy & PII Compliance at API Boundary

* **GeoJSON Properties:** Never pass raw customer residential addresses or client names in GeoJSON properties.
* **Coordinates:** Provide coordinates solely in `geometry.coordinates` `[lng, lat]` format.
* **LineStrings vs Points:**
  * Use `format=points` for discrete pickup clustering and zone analytics.
  * Use `format=corridors` (`LineString`) only when directional origin-destination flows are specifically requested.

---

## 3. Resilient Map Rendering Architecture

To prevent third-party Google Cloud API key referrer restrictions, billing surprises, and React 18 event listener race conditions (`Cannot read properties of undefined (reading '__e3_')`):

1. **Leaflet Vector Engine with Direct Layer Management:**
   * Use Leaflet with native direct layer instances (`L.polygon`, `L.circleMarker`, `L.divIcon`).
   * Clean up with `layerGroup.clearLayers()` on state changes to avoid memory leaks.
2. **Google Tile Layer Integration:**
   * Standard Google Streets: `https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}` (provides 100% full street names, avenue labels, and highway numbers without domain whitelist locks).
   * Google Hybrid (Satellite + Labels): `https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}`.
3. **Custom HTML Floating Badges:**
   * Use `L.divIcon` with CSS pill styling (`padding: 3px 8px; border-radius: 12px; border: 2px solid white; box-shadow: ...`) for readable `$XX/trip` markers over neighborhood centroids.
