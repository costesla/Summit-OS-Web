import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

class CardGenerator:
    def __init__(self, root_dir: str = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS_Data"):
        self.root_dir = root_dir

    def generate_outputs(self, normalized_data: Dict[str, Any]) -> str:
        """
        Generates MD cards and JSON sidecar in the canonical folder structure.
        Returns the path to the trip folder.
        """
        # 1. Determine Path Components
        # Year / Month / Week / MM.DD.YY / Block / Trip
        dt = datetime.fromtimestamp(normalized_data.get('timestamp_epoch', datetime.now().timestamp()))
        year = dt.strftime("%Y")
        month = dt.strftime("%B")
        week = f"Week {dt.isocalendar()[1]}"
        date_folder = dt.strftime("%m.%d.%y")
        block = normalized_data.get('block_name', 'Default_Block')
        trip_id = normalized_data.get('trip_id', 'Unknown_Trip')

        trip_path = os.path.join(self.root_dir, year, month, week, date_folder, block, trip_id)
        os.makedirs(trip_path, exist_ok=True)

        # 2. Generate Markdown Cards
        self._write_markdown_report(normalized_data, trip_path)

        # 3. Generate JSON Sidecar
        sidecar_path = os.path.join(trip_path, f"{trip_id}_sidecar.json")
        with open(sidecar_path, "w") as f:
            json.dump(normalized_data, f, indent=4, default=str)
        
        logging.info(f"SummitOS Outputs generated at: {trip_path}")
        return trip_path

    def _write_markdown_report(self, data: Dict[str, Any], folder_path: str):
        md_content = f"""# SummitOS Trip Report: {data.get('trip_id')}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Offer Card
- **Platform**: {data.get('classification', 'Unknown')}
- **Service**: {data.get('service_type', 'Standard')}
- **Estimated Earnings**: ${data.get('driver_total', 0.0):.2f}
- **Airport Trip**: {'Yes' if data.get('airport') else 'No'}

## Pickup Card
- **Address**: {data.get('pickup_address_full', data.get('start_location', 'N/A'))}
- **Elevation**: {data.get('elevation_start', 0.0):.0f} ft
- **SOC**: {data.get('start_soc_perc', 'N/A')}%

## Drop-off Card
- **Address**: {data.get('dropoff_address_full', data.get('end_location', 'N/A'))}
- **Elevation**: {data.get('elevation_end', 0.0):.0f} ft
- **SOC**: {data.get('end_soc_perc', 'N/A')}%

## Detail Card
- **Distance**: {data.get('distance_miles', 0.0):.2f} mi
- **Duration**: {data.get('duration_minutes', 0):.0f} min
- **Earnings**: ${data.get('driver_total', 0.0):.2f}
- **Platform Cut**: ${data.get('platform_cut_raw', 0.0):.2f} ({data.get('platform_cut_percent', 0.0):.1f}%)
- **Margin**: {data.get('margin_percent', 0.0):.1f}%

## EV Metrics
- **Energy Used**: {data.get('energy_used', data.get('energy_used_estimated', 0.0)):.2f} kWh
- **Efficiency**: {data.get('wh_mi', 0.0):.0f} Wh/mi
- **SOC Delta**: {data.get('soc_delta', 0.0):.1f}%

## Elevation Card
- **Trend**: {data.get('elevation_trend', 'N/A')}
- **Total Delta**: {data.get('elevation_delta', 0.0):.0f} ft

## Idle Time Card
- **Idle Since Last Trip**: {data.get('idle_time_min', 0.0):.1f} min

## Audit Trail
- **Source Artifact**: {data.get('source_url', 'N/A')}
- **Processed At**: {datetime.now().isoformat()}
"""
        report_path = os.path.join(folder_path, "Trip_Summary.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md_content)
