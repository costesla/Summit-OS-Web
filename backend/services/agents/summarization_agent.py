import logging
from typing import Dict, Any

class SummarizationAgent:
    def __init__(self):
        pass

    def generate(self, final_data: Dict[str, Any]) -> str:
        """
        Generates the SummitOS Summary Cards (Markdown).
        """
        logging.info("SummarizationAgent: Generating human-readable cards...")
        
        md_content = f"""# SummitOS Trip Report: {final_data.get('trip_id')}
Compliance Verdict: **{final_data.get('compliance_verdict', 'UNKNOWN')}**

## Offer Card
- **Platform**: {final_data.get('classification', 'Unknown')}
- **Service**: {final_data.get('service_type', 'Standard')}
- **Earnings Projection**: ${final_data.get('driver_total', 0.0):.2f}
- **Airport Priority**: {'YES' if final_data.get('airport') else 'NO'}

## Pickup Card
- **Address**: {final_data.get('pickup_address_full', final_data.get('start_location', 'N/A'))}
- **Elevation**: {final_data.get('elevation_start', 0.0):.0f} ft
- **SOC**: {final_data.get('start_soc_perc', 'N/A')}%

## Drop-off Card
- **Address**: {final_data.get('dropoff_address_full', final_data.get('end_location', 'N/A'))}
- **Elevation**: {final_data.get('elevation_end', 0.0):.0f} ft
- **SOC**: {final_data.get('end_soc_perc', 'N/A')}%

## Detail Card
- **Distance**: {final_data.get('distance_miles', 0.0):.2f} mi
- **Duration**: {final_data.get('duration_minutes', 0):.0f} min
- **Earnings**: ${final_data.get('driver_total', 0.0):.2f}
- **Platform Cut**: ${final_data.get('platform_cut_raw', 0.0):.2f} ({final_data.get('platform_cut_percent', 0.0):.1f}%)
- **Margin**: {final_data.get('margin_percent', 0.0):.1f}%

## EV Metrics
- **Energy Used**: {final_data.get('energy_used', final_data.get('energy_used_estimated', 0.0)):.2f} kWh
- **Efficiency**: {final_data.get('wh_mi', 0.0):.0f} Wh/mi
- **SOC Delta**: {final_data.get('soc_delta', 0.0):.1f}%

## Elevation Card
- **Trend**: {final_data.get('elevation_trend', 'N/A')}
- **Total Delta**: {final_data.get('elevation_delta', 0.0):.0f} ft

## Idle Time Card
- **Idle Since Last Trip**: {final_data.get('idle_time_min', 0.0):.1f} min

## Power BI Blueprint
- **KPIs**: {len(final_data.get('powerbi_spec', {}).get('visual_spec', []))} Visuals Generated
- **Model**: {len(final_data.get('powerbi_spec', {}).get('blueprint', {}).get('measures', []))} DAX Measures Ready

## Compliance Audit
{self._format_gates(final_data.get('compliance_gates', {}))}

## Audit Trail
- **Source**: {final_data.get('source_url', 'N/A')}
- **Orchestration Timestamp**: {final_data.get('orchestration_timestamp')}
"""
        return md_content

    def _format_gates(self, gates: Dict[str, bool]) -> str:
        lines = []
        for g, val in gates.items():
            status = "✅ PASS" if val else "❌ FAIL"
            lines.append(f"- **{g.upper()}**: {status}")
        return "\n".join(lines)
