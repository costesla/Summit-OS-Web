import logging
import azure.functions as func
import json
import os
from dateutil import parser
from datetime import datetime, timedelta, timezone
import pytz
from services.graph import GraphClient

bp = func.Blueprint()

# Configuration
STAFF_ID = os.environ.get("MS_BOOKINGS_STAFF_ID", "b9c4204d-bd20-43cc-aa50-2add4602d316")
BUSINESS_TIMEZONE = "America/Denver"

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }

def normalize_to_denver(dt_str):
    """Parses a datetime string from Graph (UTC) and converts to Denver time."""
    try:
        dt = parser.parse(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc) # Assume UTC if naive
        return dt.astimezone(pytz.timezone(BUSINESS_TIMEZONE))
    except Exception as e:
        logging.error(f"Date Parse Error: {e}")
        return datetime.now(pytz.timezone(BUSINESS_TIMEZONE))

@bp.route(route="hop", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def hop(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns normalized Hours of Operation (HOP) from Microsoft Graph Bookings.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    try:
        graph = GraphClient()
        business_hours = graph.get_booking_business_hours()
        
        # Normalize to weekday map
        hop_map = {}
        day_map = {
            "sunday": "0", "monday": "1", "tuesday": "2", "wednesday": "3",
            "thursday": "4", "friday": "5", "saturday": "6"
        }
        
        for entry in business_hours:
            day_name = entry.get("day", "").lower()
            day_idx = day_map.get(day_name)
            
            if day_idx:
                slots = entry.get("timeSlots", [])
                if slots:
                    # Take the first slot for now (assuming contiguous or main block)
                    first_slot = slots[0]
                    # Graph returns wall-clock time for business hours (e.g. "08:00:00.0000000")
                    start_time = first_slot.get("startTime", "08:00")[:5] 
                    end_time = first_slot.get("endTime", "17:00")[:5]
                    
                    # Midnight bleed protection for Friday/Saturday late nights
                    if (day_idx == "5" or day_idx == "6") and (end_time == "00:00" or end_time < "04:00"):
                         end_time = "23:30"
                    
                    hop_map[day_idx] = {
                        "start": start_time,
                        "end": end_time
                    }

        response_data = {
            "timeZone": "(UTC-07:00) Mountain Time (US & Canada)", 
            "ianaTimeZone": BUSINESS_TIMEZONE,
            "increments": 30,
            "hop": hop_map
        }

        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"HOP Error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            headers=_cors_headers(),
            mimetype="application/json"
        )

@bp.route(route="status", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def status(req: func.HttpRequest) -> func.HttpResponse:
    """
    Returns current Time-Off status & upcoming outages.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_cors_headers())

    try:
        graph = GraphClient()
        
        # Timezone aware "now"
        tz = pytz.timezone(BUSINESS_TIMEZONE)
        now = datetime.now(tz)
        
        # Look ahead 45 days for upcoming outages
        start_dt = now - timedelta(days=1) 
        end_dt = now + timedelta(days=45)
        
        calendar_view = graph.get_staff_time_off(STAFF_ID, start_dt, end_dt)
        
        out_today = False
        status_message = ""
        return_date = None
        upcoming_outages = []
        
        for event in calendar_view:
            # Filter logic: Check if it looks like "Time Off"
            # Explicit filtering: if serviceId is present, it's a booking. Skip it.
            # If not present, it's likely time off or manual block.
            if event.get("serviceId"):
                continue
                
            # Parse times to Denver
            # Graph 'dateTime' is UTC usually like "2026-02-14T17:00:00.0000000"
            start_str = event.get("start", {}).get("dateTime")
            end_str = event.get("end", {}).get("dateTime")
            
            if not start_str or not end_str:
                continue

            evt_start = normalize_to_denver(start_str)
            evt_end = normalize_to_denver(end_str)
            
            # Subject
            subject = event.get("subject", "Unavailable")
            
            # Check if "Now" is inside this event
            if evt_start <= now <= evt_end:
                out_today = True
                status_message = f"Peter is {subject} today. Returning {evt_end.strftime('%b %d')}."
                return_date = evt_end.strftime("%Y-%m-%d")
                
            # Check for upcoming (future start)
            elif now < evt_start:
                upcoming_outages.append({
                    "date": evt_start.strftime("%Y-%m-%d"),
                    "reason": subject,
                    "returnDate": evt_end.strftime("%b %d")
                })
        
        response_data = {
            "outToday": out_today,
            "message": status_message,
            "returnDate": return_date,
            "upcoming": upcoming_outages
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            headers=_cors_headers(),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Status Error: {str(e)}")
        # Return generic OK structure to not break frontend, but with error log
        return func.HttpResponse(
            json.dumps({"error": str(e), "outToday": False}),
            status_code=500,
            headers=_cors_headers(),
            mimetype="application/json"
        )
