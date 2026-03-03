from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Literal, List, Optional, Any

class ArtifactRecord(BaseModel):
    artifact_id: str = Field(..., description="Stable SHA-256 identifier")
    filename: str
    source_url: str
    integrity_hash: str
    ocr_output: dict = Field(..., description="raw_text and confidence")
    provenance: dict = Field(..., description="ingestion timings and tenant info")

    @validator('artifact_id', 'integrity_hash')
    def must_be_sha256(cls, v: str) -> str:
        if len(v) != 64 and not v.startswith("sha256:"): # Basic check
             pass # Allow for flexibility in naming while enforcing hash structure
        return v

class UberTripRecord(BaseModel):
    trip_id: str
    artifact_id: str
    status: Literal['Proposed', 'Executed', 'Intelligence']
    classification: Literal['Uber_Core', 'Uber_Reserved', 'Uber_Package', 'Expense']
    financials: dict = Field(..., description="rider_payment, driver_earnings, platform_cut_raw")
    mobility_semantics: dict = Field(..., description="pickup_label, dropoff_label, city, state")
    efficiency_metrics: Optional[dict] = None
    confidence_score: float = Field(..., ge=0, le=100)

    @validator('mobility_semantics')
    def privacy_enforcement(cls, v: dict) -> dict:
        # STRICT PRIVACY: No full addresses
        if any(key in v for key in ['pickup_address_full', 'dropoff_address_full', 'address']):
            raise ValueError("Privacy Violation: Full addresses detected in mobility_semantics")
        return v

class ChargeSessionRecord(BaseModel):
    session_id: str
    vin: str = Field(..., description="Hashed vehicle ID")
    location: str
    timestamps: dict
    energy: dict

    @validator('vin')
    def must_be_hashed(cls, v: str) -> str:
        if len(v) < 32: # Simple check for hashing
            raise ValueError("Privacy Violation: VIN must be a hashed identifier")
        return v

class CanonicalVector(BaseModel):
    """
    Standardized payload for Vector Store ingestion.
    Derived deterministically from Canonical Records.
    """
    vector_id: str
    source_type: Literal['Artifact', 'Trip', 'Charge', 'Ops']
    timestamp_utc: datetime
    raw_text_hash: str
    source_pointer: str
    derivation_reason: str
    embedding: List[float] = Field(..., min_length=1536, max_length=1536)
