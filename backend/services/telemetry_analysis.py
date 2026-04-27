import logging

class TelemetryAnalysisService:
    def __init__(self):
        pass

    def analyze_drive(self, telemetry_data):
        """
        Takes raw driving telemetry (arrays of speeds, elevations, temps, etc.)
        and generates a human-readable statistical summary for Vector Context.
        Returns a string summary or an empty string if data is insufficient.
        """
        if not telemetry_data or not isinstance(telemetry_data, dict):
            return ""

        try:
            # Extract arrays
            speeds = telemetry_data.get('speeds', [])
            elevations = telemetry_data.get('elevations', [])
            inside_temps = telemetry_data.get('inside_temps', [])
            outside_temps = telemetry_data.get('outside_temps', [])
            powers = telemetry_data.get('powers', [])

            summary_parts = []

            # Speed Analysis (mph)
            if speeds and len(speeds) > 0:
                valid_speeds = [s for s in speeds if s is not None]
                if valid_speeds:
                    max_spd = max(valid_speeds)
                    avg_spd = sum(valid_speeds) / len(valid_speeds)
                    summary_parts.append(f"Top speed was {max_spd:.1f} mph (avg {avg_spd:.1f} mph).")

            # Elevation Analysis (feet)
            if elevations and len(elevations) > 0:
                valid_elevs = [e for e in elevations if e is not None]
                if valid_elevs:
                    min_elev = min(valid_elevs)
                    max_elev = max(valid_elevs)
                    if max_elev - min_elev > 50:
                        summary_parts.append(f"Elevation varied between {min_elev:.0f} ft and {max_elev:.0f} ft.")

            # Climate Analysis (Celsius -> Fahrenheit)
            if inside_temps and outside_temps:
                valid_in = [t for t in inside_temps if t is not None]
                valid_out = [t for t in outside_temps if t is not None]
                if valid_in and valid_out:
                    avg_in_c = sum(valid_in) / len(valid_in)
                    avg_out_c = sum(valid_out) / len(valid_out)
                    
                    avg_in_f = (avg_in_c * 9/5) + 32
                    avg_out_f = (avg_out_c * 9/5) + 32
                    
                    summary_parts.append(f"Cabin climate averaged {avg_in_f:.0f}°F while outside temps averaged {avg_out_f:.0f}°F.")

            # Power Output (kW)
            if powers and len(powers) > 0:
                valid_powers = [p for p in powers if p is not None]
                if valid_powers:
                    max_power = max(valid_powers)
                    if max_power > 10:
                        summary_parts.append(f"Peak motor exertion hit {max_power:.0f} kW.")

            if summary_parts:
                return " Telemetry Profile: " + " ".join(summary_parts)
            return ""

        except Exception as e:
            logging.error(f"Error analyzing telemetry: {e}")
            return ""
