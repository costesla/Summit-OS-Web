import os
import sys
import pytest
from datetime import datetime

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.vector_contract import CanonicalVector

def test_valid_canonical_vector():
    data = {
        "vector_id": "test-123",
        "source_type": "FSD",
        "timestamp_utc": datetime.utcnow(),
        "vehicle_id": "VIN123",
        "driver_id": "a" * 64, # 64 char hex string
        "confidence_score": 0.95,
        "embedding_model_version": "test-model",
        "raw_text_hash": "b" * 64,
        "source_pointer": "pointer-1",
        "derivation_reason": "testing",
        "embedding": [0.1] * 1536
    }
    vec = CanonicalVector(**data)
    assert vec.vector_id == "test-123"

def test_invalid_source_type():
    data = {
        "vector_id": "test-123",
        "source_type": "INVALID_TYPE",
        "timestamp_utc": datetime.utcnow(),
        "vehicle_id": "VIN123",
        "driver_id": "a" * 64,
        "confidence_score": 0.95,
        "embedding_model_version": "test-model",
        "raw_text_hash": "b" * 64,
        "source_pointer": "pointer-1",
        "derivation_reason": "testing",
        "embedding": [0.1] * 1536
    }
    with pytest.raises(ValueError, match="Input should be"):
        CanonicalVector(**data)

def test_invalid_hash_length():
    data = {
        "vector_id": "test-123",
        "source_type": "FSD",
        "timestamp_utc": datetime.utcnow(),
        "vehicle_id": "VIN123",
        "driver_id": "short-hash",
        "confidence_score": 0.95,
        "embedding_model_version": "test-model",
        "raw_text_hash": "b" * 64,
        "source_pointer": "pointer-1",
        "derivation_reason": "testing",
        "embedding": [0.1] * 1536
    }
    with pytest.raises(ValueError, match="Value must be a valid 64-character SHA-256 hash"):
        CanonicalVector(**data)
