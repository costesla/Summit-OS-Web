import os
import sys
import pytest

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.privacy import PrivacyManager

def test_hash_identity():
    id1 = PrivacyManager.hash_identity("PeterTeehan")
    id2 = PrivacyManager.hash_identity("PeterTeehan")
    assert id1 == id2
    assert len(id1) == 64

def test_abstract_text_phone():
    text = "Call me at 555-123-4567 and my email is john@example.com."
    abstracted = PrivacyManager.abstract_text(text)
    assert "555-123-4567" not in abstracted
    assert "[REDACTED PHONE]" in abstracted
    assert "john@example.com" not in abstracted
    assert "[REDACTED EMAIL]" in abstracted
