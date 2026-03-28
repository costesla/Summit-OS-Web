"""
OpenAPI Specification Generator for Copilot Integration
This endpoint generates the OpenAPI spec that Microsoft Copilot uses to understand our API
"""

import json
import azure.functions as func

bp = func.Blueprint()

@bp.route(route="copilot/openapi.json", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def copilot_openapi(req: func.HttpRequest) -> func.HttpResponse:
    """Generate OpenAPI 3.0 specification for Copilot"""
    
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Summit Intelligence API",
            "description": "API for accessing rideshare trip data, earnings metrics, and vehicle status. CRITICAL INSTRUCTION FOR AGENT: All vehicle and trip operations run in Mountain Time (UTC-7). When a user asks about 'today', you MUST calculate today's date by subtracting 7 hours from your current UTC time before passing it to any API parameters.",
            "version": "1.0.0"
        },
        "servers": [
            {
                "url": "https://summitos-api.azurewebsites.net/api",
                "description": "Production API"
            }

        ],
        "paths": {
            "/copilot/trips/latest": {
                "get": {
                    "operationId": "getLatestTrips",
                    "summary": "Get recent trips",
                    "description": "Retrieve the most recent trips within a specified time period. Supports filtering by trip type (Uber or Private).",
                    "parameters": [
                        {
                            "name": "days",
                            "in": "query",
                            "description": "Number of days to look back (max 90)",
                            "required": False,
                            "schema": {"type": "integer", "default": 7, "maximum": 90}
                        },
                        {
                            "name": "type",
                            "in": "query",
                            "description": "Filter by trip type: 'Uber' or 'Private'",
                            "required": False,
                            "schema": {"type": "string", "enum": ["Uber", "Private"]}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of trips",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "count": {"type": "integer"},
                                                    "trips": {
                                                        "type": "array",
                                                        "items": {"$ref": "#/components/schemas/Trip"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/trips/{trip_id}": {
                "get": {
                    "operationId": "getTripDetails",
                    "summary": "Get detailed trip information",
                    "description": "Retrieve complete details for a specific trip by ID",
                    "parameters": [
                        {
                            "name": "trip_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Trip details",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "trip": {"$ref": "#/components/schemas/TripDetail"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/metrics/daily": {
                "get": {
                    "operationId": "getDailyMetrics",
                    "summary": "Get daily earnings metrics",
                    "description": "Retrieve aggregated metrics by day for a date range",
                    "parameters": [
                        {
                            "name": "start_date",
                            "in": "query",
                            "description": "Start date (YYYY-MM-DD)",
                            "schema": {"type": "string", "format": "date"}
                        },
                        {
                            "name": "end_date",
                            "in": "query",
                            "description": "End date (YYYY-MM-DD)",
                            "schema": {"type": "string", "format": "date"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Daily metrics",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "metrics": {
                                                        "type": "array",
                                                        "items": {"$ref": "#/components/schemas/DailyMetric"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/metrics/summary": {
                "get": {
                    "operationId": "getMetricsSummary",
                    "summary": "Get summary metrics",
                    "description": "Get aggregated summary for a time period",
                    "parameters": [
                        {
                            "name": "days",
                            "in": "query",
                            "description": "Number of days to summarize (max 90)",
                            "schema": {"type": "integer", "default": 30, "maximum": 90}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Summary metrics",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "summary": {"$ref": "#/components/schemas/Summary"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/vehicle/status": {
                "get": {
                    "operationId": "getVehicleStatus",
                    "summary": "Get Tesla vehicle status",
                    "description": "Retrieve current vehicle state including battery, location, and charging status",
                    "responses": {
                        "200": {
                            "description": "Vehicle status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "vehicle": {"type": "object"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/search": {
                "get": {
                    "operationId": "searchTripsSemantically",
                    "summary": "Find Verified Receipts and Purchases",
                    "description": "Searches for receipts, expenses, and transaction details (e.g., Starbucks, McDonald's). Use this tool primarily to answer questions about purchases.",
                    "x-ms-operation-label": "receipt_lookup",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "description": "Semantic search query (e.g. 'Charging session on Tuesday')",
                            "required": True,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "keyword",
                            "in": "query",
                            "description": "Hard keyword filter",
                            "required": False,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "classification",
                            "in": "query",
                            "description": "Filter by type (e.g. 'Charging_Session', 'Meal_Receipt')",
                            "required": False,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Number of results to return (max 10)",
                            "required": False,
                            "schema": {"type": "integer", "default": 5, "maximum": 10}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Search results",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "query": {"type": "string"},
                                                    "results": {
                                                        "type": "array",
                                                        "items": {"$ref": "#/components/schemas/SearchResult"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/charging/live": {
                "get": {
                    "operationId": "getLiveChargingStatus",
                    "summary": "Get real-time vehicle charging telemetry",
                    "description": "Fetches current charging state, SOC, power, and location. Use this for questions like 'Am I charging now?' or 'What is my current battery level?'.",
                    "responses": {
                        "200": {
                            "description": "Real-time charging state",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "is_charging": {"type": "boolean"},
                                            "charging_state": {"type": "string"},
                                            "current_soc": {"type": "integer"},
                                            "charge_power_kw": {"type": "number"},
                                            "location": {"type": "string"},
                                            "timestamp": {"type": "string", "format": "date-time"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/agentic-query": {
                "get": {
                    "operationId": "agenticVectorQuery",
                    "summary": "Agentic SQL Vector Query",
                    "description": "Query the Agentic SQL Vector Database directly. Provides Provably True answers based strictly on stored telemetry and operational data. Specify 'evidence' mode for direct factual returns, 'insight' for pattern analysis, or 'narrative' for synthesized investor-grade reports.",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "description": "The exact question or analytical prompt",
                            "required": True,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "mode",
                            "in": "query",
                            "description": "Operational Mode: 'evidence', 'insight', or 'narrative'",
                            "required": False,
                            "schema": {"type": "string", "default": "evidence"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Agentic Query Result",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "query": {"type": "string"},
                                                    "mode": {"type": "string"},
                                                    "agentic_response": {"type": "string"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/artifacts/{artifact_id}/raw": {
                "get": {
                    "operationId": "getArtifactRaw",
                    "summary": "Retrieve Rehydration Evidence Image",
                    "description": "Returns a highly secure, short-lived download link to the original, human-verifiable artifact image in the SharePoint archive via its Canonical Artifact ID. Call this when an auditor, passenger, or human explicitly asks to 'see the receipt' or 'view the original image'.",
                    "parameters": [
                        {
                            "name": "artifact_id",
                            "in": "path",
                            "description": "The Canonical Artifact ID (sha256-...)",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "302": {
                            "description": "Redirects to the temporary download URL for the artifact image."
                        },
                        "404": {
                            "description": "Artifact archived or not found."
                        }
                    }
                }
            },
            "/copilot/tessie/drives": {
                "get": {
                    "operationId": "getTessieDrives",
                    "summary": "Get Tessie vehicle drives",
                    "description": "Retrieve detailed Tesla drive logs including efficiency, Autopilot usage, and locations. Can be filtered by tag (e.g., 'Jackie') and date range.",
                    "parameters": [
                        {
                            "name": "tag",
                            "in": "query",
                            "description": "Filter by Tessie tag (keyword match, e.g. 'Jackie', 'Esmeralda')",
                            "required": False,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "days",
                            "in": "query",
                            "description": "Number of days to look back (default 30, max 365)",
                            "required": False,
                            "schema": {"type": "integer", "default": 30}
                        },
                        {
                            "name": "month",
                            "in": "query",
                            "description": "Specific month filter (YYYY-MM)",
                            "required": False,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of drives",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "tag_filter": {"type": "string"},
                                            "count": {"type": "integer"},
                                            "drives": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/TessieDrive"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/tessie/charges": {
                "get": {
                    "operationId": "getTessieCharges",
                    "summary": "Get Tessie vehicle charges",
                    "description": "Retrieve historical Tesla charging sessions including location, energy added, and battery levels.",
                    "parameters": [
                        {
                            "name": "days",
                            "in": "query",
                            "description": "Number of days to look back (default 30, max 365)",
                            "required": False,
                            "schema": {"type": "integer", "default": 30}
                        },
                        {
                            "name": "month",
                            "in": "query",
                            "description": "Specific month filter (YYYY-MM)",
                            "required": False,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of charging sessions",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "count": {"type": "integer"},
                                            "sessions": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/TessieCharge"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/tessie/summary": {
                "get": {
                    "operationId": "getTessieSummary",
                    "summary": "Get Tessie driving summary",
                    "description": "Get aggregated driving statistics (miles, autopilot, efficiency) for a period.",
                    "parameters": [
                        {
                            "name": "days",
                            "in": "query",
                            "description": "Number of days to summarize (default 30, max 365)",
                            "required": False,
                            "schema": {"type": "integer", "default": 30}
                        },
                        {
                            "name": "month",
                            "in": "query",
                            "description": "Specific month filter (YYYY-MM)",
                            "required": False,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Tessie execution summary",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "period": {"type": "string"},
                                            "total_drives": {"type": "integer"},
                                            "total_miles": {"type": "number"},
                                            "total_energy_used_kwh": {"type": "number"},
                                            "total_energy_charged_kwh": {"type": "number"},
                                            "charge_sessions": {"type": "integer"},
                                            "average_speed_mph": {"type": "number"},
                                            "max_speed_mph": {"type": "number"},
                                            "autopilot_miles": {"type": "number"},
                                            "autopilot_pct": {"type": "number"},
                                            "efficiency_wh_mi": {"type": "number"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/banking/accounts": {
                "get": {
                    "operationId": "getBankAccounts",
                    "summary": "List connected bank accounts",
                    "description": "Returns a list of connected financial accounts (Chase, etc.) via Teller. Use this to identify where operational expenses or earnings are settled.",
                    "responses": {
                        "200": {
                            "description": "List of bank accounts",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "accounts": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/BankAccount"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/banking/transactions": {
                "get": {
                    "operationId": "getBankTransactions",
                    "summary": "Get recent bank transactions",
                    "description": "Retrieve recent financial activities for a specific account. Use this to reconcile driving missions with actual payments (e.g. Starbucks, McDonalds, Maintenance).",
                    "parameters": [
                        {
                            "name": "account_id",
                            "in": "query",
                            "description": "The Teller Account ID (if omitted, uses default)",
                            "required": False,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Number of transactions to return (default 20)",
                            "required": False,
                            "schema": {"type": "integer", "default": 20}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of transactions",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "count": {"type": "integer"},
                                            "transactions": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/BankTransaction"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/copilot/banking/sync": {
                "post": {
                    "operationId": "syncBankTransactions",
                    "summary": "Synchronize and vectorize bank transactions",
                    "description": "Pulls the latest transactions from Teller and ingests them into the Vector Store (System_Vectors). Use this when the user asks to 'reconcile' or 'refresh' their financial context.",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Number of transactions to pull (default 50)",
                            "required": False,
                            "schema": {"type": "integer", "default": 50}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Sync result",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "transactions_processed": {"type": "integer"},
                                            "transactions_vectorized": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "BankAccount": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string"},
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "subtype": {"type": "string"},
                        "currency": {"type": "string"},
                        "institution": {"type": "string"}
                    }
                },
                "BankTransaction": {
                    "type": "object",
                    "properties": {
                        "transaction_id": {"type": "string"},
                        "date": {"type": "string", "format": "date"},
                        "description": {"type": "string"},
                        "counterparty": {"type": "string"},
                        "amount": {"type": "number"},
                        "type": {"type": "string"},
                        "status": {"type": "string"},
                        "category": {"type": "string"}
                    }
                },
                "SearchResult": {
                    "type": "object",
                    "properties": {
                        "confidence": {"type": "number"},
                        "filename": {"type": "string"},
                        "content": {"type": "string"},
                        "metadata": {"type": "object"}
                    }
                },
                "Trip": {
                    "type": "object",
                    "properties": {
                        "trip_id": {"type": "string"},
                        "type": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                        "pickup": {"type": "string"},
                        "dropoff": {"type": "string"},
                        "fare": {"$ref": "#/components/schemas/Currency"},
                        "tip": {"$ref": "#/components/schemas/Currency"},
                        "distance_miles": {"type": "number"},
                        "duration_minutes": {"type": "number"}
                    }
                },
                "TripDetail": {
                    "type": "object",
                    "properties": {
                        "trip_id": {"type": "string"},
                        "type": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                        "classification": {"type": "string"},
                        "pickup": {"type": "string"},
                        "dropoff": {"type": "string"},
                        "fare": {"$ref": "#/components/schemas/Currency"},
                        "tip": {"$ref": "#/components/schemas/Currency"},
                        "driver_earnings": {"$ref": "#/components/schemas/Currency"},
                        "distance_miles": {"type": "number"},
                        "duration_minutes": {"type": "number"},
                        "payment_method": {"type": "string"},
                        "notes": {"type": "string"}
                    }
                },
                "Currency": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number"},
                        "display": {"type": "string"}
                    }
                },
                "DailyMetric": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "earnings": {"$ref": "#/components/schemas/Currency"},
                        "tips": {"$ref": "#/components/schemas/Currency"},
                        "trip_count": {"type": "integer"},
                        "miles": {"type": "number"},
                        "drive_hours": {"type": "number"}
                    }
                },
                "Summary": {
                    "type": "object",
                    "properties": {
                        "period_days": {"type": "integer"},
                        "total_trips": {"type": "integer"},
                        "total_earnings": {"$ref": "#/components/schemas/Currency"},
                        "total_tips": {"$ref": "#/components/schemas/Currency"},
                        "total_distance": {"type": "number"},
                        "average_fare": {"$ref": "#/components/schemas/Currency"}
                    }
                },
                "TessieDrive": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "time_mst": {"type": "string"},
                        "tag": {"type": "string"},
                        "classification": {"type": "string"},
                        "distance_miles": {"type": "number"},
                        "average_speed_mph": {"type": "number"},
                        "max_speed_mph": {"type": "number"},
                        "energy_used_kwh": {"type": "number"},
                        "efficiency_wh_mi": {"type": "number"},
                        "autopilot_miles": {"type": "number"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "starting_battery": {"type": "integer"},
                        "ending_battery": {"type": "integer"},
                        "tessie_drive_id": {"type": "string"}
                    }
                },
                "TessieCharge": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "time_mst": {"type": "string"},
                        "energy_added_kwh": {"type": "number"},
                        "starting_soc": {"type": "integer"},
                        "ending_soc": {"type": "integer"},
                        "duration_minutes": {"type": "number"},
                        "location": {"type": "string"},
                        "charge_type": {"type": "string"},
                        "tessie_charge_id": {"type": "string"}
                    }
                }
            }
        }
    }
    
    return func.HttpResponse(
        json.dumps(spec, indent=2),
        mimetype="application/json"
    )
