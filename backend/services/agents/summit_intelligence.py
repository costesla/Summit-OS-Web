import os
import json
import logging
import datetime
import re
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from openai import OpenAI
from services.database import DatabaseClient

# Helper: Sanitize address to city and state for Privacy Enforcement
def sanitize_address_to_city_state(address: str) -> str:
    if not address:
        return "Unknown"
    address = address.strip()
    # Check if there is comma splitting
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        # Exclude country tags
        if parts[-1].lower() in ["usa", "united states", "us"]:
            parts = parts[:-1]
        if len(parts) >= 2:
            city = parts[-2]
            state_zip = parts[-1]
            state_parts = state_zip.split()
            state = state_parts[0] if state_parts else state_zip
            return f"{city}, {state}"
        return parts[-1]
    return address

# ─── PYDANTIC SCHEMAS ─────────────────────────────────────────────────────────

class TripModel(BaseModel):
    trip_id: str
    date: str  # YYYY-MM-DD
    type: Literal["uber", "private"]
    distance_mi: float
    duration_min: float
    earnings: float
    energy_cost: float
    profit: float
    profit_margin: float
    dollars_per_mile: float
    dollars_per_min: float

class ChargingModel(BaseModel):
    session_id: str
    date: str  # YYYY-MM-DD
    kwh_added: float
    cost: float
    duration_min: float
    rate_per_kwh: float

class ExpenseModel(BaseModel):
    expense_id: str
    date: str  # YYYY-MM-DD
    category: str
    amount: float

class VehicleModel(BaseModel):
    timestamp: str  # ISO Format
    soc_pct: float
    efficiency_wh_per_mi: float
    odometer_mi: float

class DashboardModel(BaseModel):
    total_earnings: float
    total_charging_cost: float
    total_expenses: float
    total_energy_cost: float
    net_profit: float
    trips: List[TripModel]
    charging_sessions: List[ChargingModel]
    expenses: List[ExpenseModel]
    vehicle_metrics: List[VehicleModel]

# ─── AGENTS IMPLEMENTATION ───────────────────────────────────────────────────

class TripsAgent:
    """
    Trip Intelligence Engine (Isolated).
    Scope: Uber & Private trips, Earnings, Profitability.
    """
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client

    def query(self, date_str: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        logging.info(f"TripsAgent querying trips. Date: {date_str}, Range: [{start_date}, {end_date}]")
        
        # Build SQL Query with absolute isolation (Rides.Rides only)
        sql = """
            SELECT 
                RideID, TripType, Timestamp_Start, Distance_mi, Duration_min, 
                Driver_Earnings, Fare, Tip, Energy_Used_kWh, Start_SOC, End_SOC, Efficiency_Wh_mi
            FROM Rides.Rides
            WHERE 1=1
        """
        params = []
        
        if date_str:
            sql += " AND CAST(Timestamp_Start AS DATE) = ?"
            params.append(date_str)
        elif start_date and end_date:
            sql += " AND CAST(Timestamp_Start AS DATE) >= ? AND CAST(Timestamp_Start AS DATE) <= ?"
            params.extend([start_date, end_date])
            
        sql += " ORDER BY Timestamp_Start DESC"
        
        results = self.db.execute_query_params(sql, params)
        if not results:
            return []
            
        formatted_trips = []
        for r in results:
            ride_id = str(r.get("RideID") or "")
            t_start = r.get("Timestamp_Start")
            date_val = t_start.strftime("%Y-%m-%d") if isinstance(t_start, datetime.datetime) else str(t_start)[:10]
            
            trip_type = str(r.get("TripType") or "private").lower()
            if trip_type not in ["uber", "private"]:
                trip_type = "private"
                
            dist = float(r.get("Distance_mi") or 0.0)
            dur = float(r.get("Duration_min") or 0.0)
            earnings = float(r.get("Driver_Earnings") or r.get("Fare", 0.0) or 0.0)
            
            # Deterministic Energy Cost calculation
            energy_used = float(r.get("Energy_Used_kWh") or 0.0)
            if energy_used <= 0.0:
                s_soc = float(r.get("Start_SOC") or 0.0)
                e_soc = float(r.get("End_SOC") or 0.0)
                soc_delta = s_soc - e_soc
                if soc_delta > 0:
                    energy_used = (soc_delta / 100.0) * 82.0
                else:
                    energy_used = dist * 0.250  # 250 Wh/mi standard
            
            # Standard supercharging rate ($0.35/kWh)
            energy_cost = round(energy_used * 0.35, 2)
            profit = round(earnings - energy_cost, 2)
            profit_margin = round(profit / earnings, 4) if earnings > 0 else 0.0
            
            dollars_per_mile = round(earnings / dist, 2) if dist > 0 else 0.0
            dollars_per_min = round(earnings / dur, 2) if dur > 0 else 0.0
            
            trip_data = {
                "trip_id": ride_id,
                "date": date_val,
                "type": trip_type,
                "distance_mi": dist,
                "duration_min": dur,
                "earnings": earnings,
                "energy_cost": energy_cost,
                "profit": profit,
                "profit_margin": profit_margin,
                "dollars_per_mile": dollars_per_mile,
                "dollars_per_min": dollars_per_min
            }
            # Enforce schema using Pydantic
            validated = TripModel(**trip_data)
            formatted_trips.append(validated.model_dump())
            
        return formatted_trips


class ChargingAgent:
    """
    Charging Intelligence Engine (Isolated).
    Scope: Tesla charging sessions. NEVER computes profit.
    """
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client

    def query(self, date_str: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        logging.info(f"ChargingAgent querying charging. Date: {date_str}, Range: [{start_date}, {end_date}]")
        
        sql = """
            SELECT SessionID, Start_Time, End_Time, Location_Name, Energy_Added_kWh, Cost
            FROM Rides.ChargingSessions
            WHERE 1=1
        """
        params = []
        
        if date_str:
            sql += " AND CAST(Start_Time AS DATE) = ?"
            params.append(date_str)
        elif start_date and end_date:
            sql += " AND CAST(Start_Time AS DATE) >= ? AND CAST(Start_Time AS DATE) <= ?"
            params.extend([start_date, end_date])
            
        sql += " ORDER BY Start_Time DESC"
        
        results = self.db.execute_query_params(sql, params)
        if not results:
            return []
            
        formatted_sessions = []
        for r in results:
            sid = str(r.get("SessionID") or "")
            t_start = r.get("Start_Time")
            date_val = t_start.strftime("%Y-%m-%d") if isinstance(t_start, datetime.datetime) else str(t_start)[:10]
            
            t_end = r.get("End_Time")
            duration = 0.0
            if isinstance(t_start, datetime.datetime) and isinstance(t_end, datetime.datetime):
                duration = round((t_end - t_start).total_seconds() / 60.0, 1)
                
            kwh = float(r.get("Energy_Added_kWh") or 0.0)
            cost = float(r.get("Cost") or 0.0)
            rate = round(cost / kwh, 4) if kwh > 0 else 0.0
            
            session_data = {
                "session_id": sid,
                "date": date_val,
                "kwh_added": kwh,
                "cost": cost,
                "duration_min": duration,
                "rate_per_kwh": rate
            }
            # Enforce schema using Pydantic
            validated = ChargingModel(**session_data)
            formatted_sessions.append(validated.model_dump())
            
        return formatted_sessions


class ExpensesAgent:
    """
    Expense Tracking Engine (Isolated).
    Scope: Dining, supplies, operating costs. NEVER includes supercharging.
    """
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client

    def query(self, date_str: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        logging.info(f"ExpensesAgent querying expenses. Date: {date_str}, Range: [{start_date}, {end_date}]")
        
        sql = """
            SELECT ExpenseID, Category, Amount, Timestamp
            FROM Rides.ManualExpenses
            WHERE 1=1
        """
        params = []
        
        if date_str:
            sql += " AND CAST(Timestamp AS DATE) = ?"
            params.append(date_str)
        elif start_date and end_date:
            sql += " AND CAST(Timestamp AS DATE) >= ? AND CAST(Timestamp AS DATE) <= ?"
            params.extend([start_date, end_date])
            
        sql += " ORDER BY Timestamp DESC"
        
        results = self.db.execute_query_params(sql, params)
        if not results:
            return []
            
        formatted_expenses = []
        for r in results:
            eid = str(r.get("ExpenseID") or "")
            t_stamp = r.get("Timestamp")
            date_val = t_stamp.strftime("%Y-%m-%d") if isinstance(t_stamp, datetime.datetime) else str(t_stamp)[:10]
            
            category = str(r.get("Category") or "General")
            amount = float(r.get("Amount") or 0.0)
            
            expense_data = {
                "expense_id": eid,
                "date": date_val,
                "category": category,
                "amount": amount
            }
            # Enforce schema using Pydantic
            validated = ExpenseModel(**expense_data)
            formatted_expenses.append(validated.model_dump())
            
        return formatted_expenses


class VehicleAgent:
    """
    Vehicle Telemetry Engine (Isolated).
    Scope: SOC, efficiency, odometer. NEVER calculates earnings or costs.
    """
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client

    def query(self, date_str: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        logging.info(f"VehicleAgent querying telemetry. Date: {date_str}, Range: [{start_date}, {end_date}]")
        
        # Determine target date filters
        target_dates = set()
        if date_str:
            target_dates.add(date_str)
        elif start_date and end_date:
            try:
                s_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
                e_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
                delta = e_dt - s_dt
                for i in range(delta.days + 1):
                    target_dates.add((s_dt + datetime.timedelta(days=i)).strftime("%Y-%m-%d"))
            except Exception as e:
                logging.error(f"Error parsing dates in VehicleAgent: {e}")
                
        # Telemetry is stored as raw JSON payloads containing arrays of points in dbo.Drive_Telemetry
        # To avoid pulling all rows from the database, we pre-filter by joining Rides.Rides on target_dates if active
        if target_dates:
            date_list = ", ".join(f"'{d}'" for d in target_dates)
            sql = f"""
                SELECT dt.DriveID, dt.RawJSONPayload, dt.LastUpdated
                FROM dbo.Drive_Telemetry dt
                INNER JOIN Rides.Rides r ON dt.DriveID = r.RideID
                WHERE dt.RawJSONPayload IS NOT NULL
                  AND CAST(r.Timestamp_Start AS DATE) IN ({date_list})
            """
        else:
            sql = """
                SELECT DriveID, RawJSONPayload, LastUpdated
                FROM dbo.Drive_Telemetry
                WHERE RawJSONPayload IS NOT NULL
            """

        # Because the telemetry is inside a blob, we load and parse it
        results = self.db.execute_query_with_results(sql)
        if not results:
            return []
            
        telemetry_points = []
        for r in results:
            try:
                payload = json.loads(r.get("RawJSONPayload") or "{}")
                timestamps = payload.get("timestamps", [])
                battery_levels = payload.get("battery_levels", [])
                odometers = payload.get("odometers", [])
                
                # Check for standard keys
                if not timestamps or not battery_levels or not odometers:
                    continue
                    
                # Iterate and filter points based on mountain time dates
                for idx, ts in enumerate(timestamps):
                    try:
                        # Convert to MDT date
                        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                        # Shift to MDT (UTC-6)
                        mdt_dt = dt - datetime.timedelta(hours=6)
                        # Remove timezone info to prevent dual-timezone offset like +00:00-06:00
                        mdt_naive = mdt_dt.replace(tzinfo=None)
                        mdt_date_str = mdt_naive.strftime("%Y-%m-%d")
                        
                        # Apply date filter
                        if target_dates and mdt_date_str not in target_dates:
                            continue
                            
                        soc = float(battery_levels[idx] if idx < len(battery_levels) else 0.0)
                        odo = float(odometers[idx] if idx < len(odometers) else 0.0)
                        
                        # Calculate dynamic efficiency based on real-time voltage, current, and speed
                        eff = 250.0 # baseline fallback
                        speeds = payload.get("speeds", [])
                        pack_current = payload.get("pack_current", [])
                        pack_voltage = payload.get("pack_voltage", [])
                        
                        if idx < len(speeds) and idx < len(pack_current) and idx < len(pack_voltage):
                            speed = float(speeds[idx] or 0.0)
                            curr = float(pack_current[idx] or 0.0)
                            volt = float(pack_voltage[idx] or 0.0)
                            
                            # Power in Watts (discharging is negative current)
                            power_w = abs(curr) * volt
                            if speed > 2.0:
                                calculated_eff = power_w / speed
                                # Cap it between 100.0 and 800.0 to keep the graph beautifully scaled
                                eff = max(100.0, min(800.0, calculated_eff))
                            else:
                                # When stationary, use standard baseline
                                eff = 250.0
                        
                        point_data = {
                            "timestamp": mdt_naive.isoformat() + "-06:00",
                            "soc_pct": soc,
                            "efficiency_wh_per_mi": round(eff, 1),
                            "odometer_mi": odo
                        }
                        # Enforce schema using Pydantic
                        validated = VehicleModel(**point_data)
                        telemetry_points.append(validated.model_dump())
                    except Exception as ex:
                        continue
            except Exception as err:
                logging.error(f"Error parsing drive telemetry payload: {err}")
                continue
                
        # Sort chronologically
        telemetry_points.sort(key=lambda x: x["timestamp"])
        
        # Limit to prevent large payloads (e.g. max 100 points)
        return telemetry_points[:100]


# ─── MASTER ORCHESTRATOR ─────────────────────────────────────────────────────

class MasterOrchestrator:
    """
    Summit Intelligence Orchestration and Aggregation layer.
    Can query all individual isolated agents and perform secure financial reconciliation.
    """
    def __init__(self, db_client: DatabaseClient):
        self.trips_agent = TripsAgent(db_client)
        self.charging_agent = ChargingAgent(db_client)
        self.expenses_agent = ExpensesAgent(db_client)
        self.vehicle_agent = VehicleAgent(db_client)

    def aggregate_dashboard(self, date_str: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        logging.info(f"MasterOrchestrator aggregating dashboard. Date: {date_str}, Range: [{start_date}, {end_date}]")
        
        # STEP 1: Query Trips Agent
        trips = self.trips_agent.query(date_str, start_date, end_date)
        
        # STEP 2: Query Charging Agent
        charges = self.charging_agent.query(date_str, start_date, end_date)
        
        # STEP 3: Query Expenses Agent
        expenses = self.expenses_agent.query(date_str, start_date, end_date)
        
        # STEP 4: Query Vehicle Agent
        vehicle = self.vehicle_agent.query(date_str, start_date, end_date)
        
        # STEP 5: Compute Aggregations
        total_earnings = round(sum(t["earnings"] for t in trips), 2)
        total_charging = round(sum(c["cost"] for c in charges), 2)
        total_expenses = round(sum(e["amount"] for e in expenses if e.get("category") not in ["Maintenance", "General_Expense"]), 2)
        total_energy_cost = round(sum(t["energy_cost"] for t in trips), 2)
        
        net_profit = round(total_earnings - total_charging - total_expenses, 2)
        
        dashboard_data = {
            "total_earnings": total_earnings,
            "total_charging_cost": total_charging,
            "total_expenses": total_expenses,
            "total_energy_cost": total_energy_cost,
            "net_profit": net_profit,
            "trips": trips,
            "charging_sessions": charges,
            "expenses": expenses,
            "vehicle_metrics": vehicle
        }
        
        # Enforce schema using Pydantic
        validated = DashboardModel(**dashboard_data)
        return validated.model_dump()


# ─── PARSER & ROUTER ─────────────────────────────────────────────────────────

class GovernedQueryRouter:
    """
    Dual-engine intent parser (LLM-first, rule-based fallback).
    Determines targets and extracts filters accurately.
    """
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def parse_query(self, query: str) -> Dict[str, Any]:
        # Calculate dynamic dates in Mountain Time (UTC-6)
        mt_now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=6)
        today_str = mt_now.strftime("%Y-%m-%d")
        yesterday_str = (mt_now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        parsed = None
        if self.client:
            try:
                # LLM-based parsing
                prompt = f"""
                You are the routing and parameter extraction engine for Summit Intelligence.
                Analyze the user query: "{query}"
                Today's date is {today_str}.
                
                Extract:
                1. target_agent: Must be exactly one of: ["trips", "charging", "expenses", "vehicle", "orchestrator"].
                   - Select "orchestrator" ONLY if the query requires aggregations or combination across multiple domains (e.g. net profit, dashboard, total expenses and trips, etc.).
                   - Otherwise, map to the specific isolated domain engine.
                2. date_str: A date string formatted as "YYYY-MM-DD" if a single specific day is referenced (e.g. "today" -> "{today_str}", "yesterday" -> "{yesterday_str}", "May 10" -> "2026-05-10"). Return null if not specific.
                3. start_date: Start of a range formatted as "YYYY-MM-DD" or null.
                4. end_date: End of a range formatted as "YYYY-MM-DD" or null.
                
                Respond ONLY with a valid JSON object. Do not include markdown code block syntax. Example:
                {{"target_agent": "trips", "date_str": "{today_str}", "start_date": null, "end_date": null}}
                """
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                raw_content = response.choices[0].message.content.strip()
                # Clean markdown backticks if returned
                raw_content = re.sub(r"^```json\s*", "", raw_content)
                raw_content = re.sub(r"\s*```$", "", raw_content)
                parsed = json.loads(raw_content)
                logging.info(f"LLM successfully parsed query intent: {parsed}")
            except Exception as e:
                logging.error(f"OpenAI Query Parser failed, falling back to rule-based: {e}")
                
        if not parsed:
            # Rule-based fallback parsing
            parsed = self._rule_based_fallback(query)
            logging.info(f"Rule-based parser extracted: {parsed}")
            
        return parsed

    def _parse_date_from_text(self, text: str, current_year: int) -> Optional[str]:
        # 1. Check for YYYY-MM-DD pattern
        match_iso = re.search(r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", text)
        if match_iso:
            try:
                y = int(match_iso.group(1))
                m = int(match_iso.group(2))
                d = int(match_iso.group(3))
                # Validate date
                datetime.date(y, m, d)
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass

        # 2. Check for M.D.YY or M.D.YYYY pattern (e.g. 5.20.26, 5/20/2026, 05-20-26)
        match_short = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
        if match_short:
            try:
                m = int(match_short.group(1))
                d = int(match_short.group(2))
                y = int(match_short.group(3))
                if y < 100:
                    y += 2000
                # Validate date
                datetime.date(y, m, d)
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass

        # Worded date mapping
        months_map = {
            "january": 1, "jan": 1,
            "february": 2, "feb": 2,
            "march": 3, "mar": 3,
            "april": 4, "apr": 4,
            "may": 5,
            "june": 6, "jun": 6,
            "july": 7, "jul": 7,
            "august": 8, "aug": 8,
            "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10,
            "november": 11, "nov": 11,
            "december": 12, "dec": 12
        }

        # 3. Pattern A: [Month] [Day] [Year] (e.g. may 20, 2026 or may 20 26)
        pattern_a = r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*|\s+)(\d{2,4})\b"
        match_a = re.search(pattern_a, text)
        if match_a:
            try:
                m_str = match_a.group(1)
                m = months_map[m_str]
                d = int(match_a.group(2))
                y = int(match_a.group(3))
                if y < 100:
                    y += 2000
                datetime.date(y, m, d)
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass

        # 4. Pattern A without year: [Month] [Day] (e.g. may 20 or may 20th)
        pattern_a_no_year = r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b"
        match_a_ny = re.search(pattern_a_no_year, text)
        if match_a_ny:
            try:
                m_str = match_a_ny.group(1)
                m = months_map[m_str]
                d = int(match_a_ny.group(2))
                y = current_year
                datetime.date(y, m, d)
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass

        # 5. Pattern B: [Day] [Month] [Year] (e.g. 20th of may 2026 or 20 may 26)
        pattern_b = r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)(?:\s*,\s*|\s+)(\d{2,4})\b"
        match_b = re.search(pattern_b, text)
        if match_b:
            try:
                d = int(match_b.group(1))
                m_str = match_b.group(2)
                m = months_map[m_str]
                y = int(match_b.group(3))
                if y < 100:
                    y += 2000
                datetime.date(y, m, d)
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass

        # 6. Pattern B without year: [Day] [Month] (e.g. 20th of may or 20 may)
        pattern_b_no_year = r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b"
        match_b_ny = re.search(pattern_b_no_year, text)
        if match_b_ny:
            try:
                d = int(match_b_ny.group(1))
                m_str = match_b_ny.group(2)
                m = months_map[m_str]
                y = current_year
                datetime.date(y, m, d)
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass

        return None

    def _rule_based_fallback(self, query: str) -> Dict[str, Any]:
        q = query.lower()
        target = "trips" # default
        
        # Target Agent classification
        if any(w in q for w in ["net profit", "overall", "dashboard", "summary", "combine", "total"]):
            target = "orchestrator"
        elif any(w in q for w in ["charge", "charging", "supercharger", "kwh", "plug"]):
            target = "charging"
        elif any(w in q for w in ["expense", "spend", "cost", "dining", "supplies", "food"]):
            target = "expenses"
        elif any(w in q for w in ["vehicle", "telemetry", "soc", "battery", "efficiency", "odometer"]):
            target = "vehicle"
        elif any(w in q for w in ["trip", "drive", "ride", "uber", "private", "earnings", "fare"]):
            target = "trips"
            
        # Date Extraction
        date_str = None
        start_date = None
        end_date = None
        
        # Calculate dynamic dates in Mountain Time
        mt_now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=6)
        today_str = mt_now.strftime("%Y-%m-%d")
        yesterday_str = (mt_now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        if "today" in q:
            date_str = today_str
        elif "yesterday" in q:
            date_str = yesterday_str
        else:
            date_str = self._parse_date_from_text(q, mt_now.year)
                
        return {
            "target_agent": target,
            "date_str": date_str,
            "start_date": start_date,
            "end_date": end_date
        }
