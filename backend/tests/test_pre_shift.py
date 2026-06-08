import os
import sys
import json
import time
import pytest
import asyncio
from unittest.mock import MagicMock, patch

# Add root backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from api.pre_shift_check import (
    _normalize,
    _onedrive_count_cache,
    _drive_cache,
    _get_sharepoint_drive_id,
    _graph_count_files,
    _src_onedrive_trip_count,
    _src_onedrive_expense_count,
)

def test_normalize_path_helper():
    """Verify that path/site name normalization strips, lowercases, and decodes properly."""
    assert _normalize("SummitOS%20Intelligence") == "summitos intelligence"
    assert _normalize("SummitOS Intelligence/") == "summitos intelligence"
    assert _normalize("  /sites/SummitOS Intelligence  ") == "sites/summitos intelligence"
    assert _normalize("") == ""
    assert _normalize(None) == ""

@pytest.mark.asyncio
async def test_onedrive_count_caching_and_fast_path():
    """Verify category-level keys and fast-path cache bypass works as expected."""
    _onedrive_count_cache.clear()
    
    date_str = "2026-05-26"
    
    # 1. Populate cache with pre-calculated values
    _onedrive_count_cache[f"{date_str}:trips"] = {
        "value": 21,
        "expires": time.time() + 600
    }
    _onedrive_count_cache[f"{date_str}:expenses"] = {
        "value": 7,
        "expires": time.time() + 600
    }
    
    # 2. Call OneDrive source functions - on hit, these MUST NOT call _get_graph_token at all
    with patch("api.pre_shift_check._get_graph_token") as mock_token:
        trips = await _src_onedrive_trip_count(date_str)
        expenses = await _src_onedrive_expense_count(date_str)
        
        # Verify cache hits return the correct numbers without doing external auth token calls
        assert trips == 21
        assert expenses == 7
        mock_token.assert_not_called()

@pytest.mark.asyncio
async def test_cache_expiration_and_invalidation():
    """Verify that expired cache keys are ignored and trigger a fresh Graph fetch."""
    _onedrive_count_cache.clear()
    
    date_str = "2026-05-26"
    
    # Set expired cache
    _onedrive_count_cache[f"{date_str}:trips"] = {
        "value": 99,
        "expires": time.time() - 1  # Expired
    }
    
    # Mocking external calls for fresh Graph count fetch
    with patch("api.pre_shift_check._get_graph_token", return_value="mock_token"), \
         patch("api.pre_shift_check._get_sharepoint_drive_id", return_value=(None, "mock_drive", "env", 0.0)), \
         patch("requests.get") as mock_get:
        
        # Mock requests returning children list
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"value": [{"name": "trip1.png"}]}
        mock_get.return_value = mock_resp
        
        trips = await _src_onedrive_trip_count(date_str)
        
        # Verify it bypassed the expired cache and fetched fresh count
        assert trips == 1
        assert _onedrive_count_cache[f"{date_str}:trips"]["value"] == 1
        assert _onedrive_count_cache[f"{date_str}:trips"]["expires"] > time.time()

@pytest.mark.asyncio
async def test_get_sharepoint_drive_id_strict_guard():
    """Verify dynamic resolution rejects wrong hostnames and handles fallback documents library."""
    _drive_cache.clear()
    
    # Mocking Graph requests responses
    with patch("requests.get") as mock_get:
        # Step A: direct resolution fails
        # Step B: search returns a site with WRONG hostname (e.g. personal sharepoint or competitor)
        # Step C: fallback Documents matched
        mock_resp_direct = MagicMock()
        mock_resp_direct.ok = False
        
        mock_resp_search = MagicMock()
        mock_resp_search.ok = True
        mock_resp_search.json.return_value = {
            "value": [
                {
                    "id": "site_wrong_host",
                    "name": "SummitOS Intelligence",
                    "displayName": "SummitOS Intelligence",
                    "webUrl": "https://malicious.sharepoint.com/sites/SummitOS%20Intelligence"
                },
                {
                    "id": "site_correct_host",
                    "name": "SummitOS Intelligence",
                    "displayName": "SummitOS Intelligence",
                    "webUrl": "https://costesla.sharepoint.com/sites/SummitOS%20Intelligence"
                }
            ]
        }
        
        mock_resp_drives = MagicMock()
        mock_resp_drives.ok = True
        mock_resp_drives.json.return_value = {
            "value": [
                {
                    "id": "drive_documents",
                    "name": "Documents",
                    "driveType": "documentLibrary"
                }
            ]
        }
        
        mock_get.side_effect = [mock_resp_direct, mock_resp_search, mock_resp_drives]
        
        site_id, drive_id, source, res_ms = await _get_sharepoint_drive_id("mock_token")
        
        # Verify strict guard filtered out site_wrong_host, leaving only site_correct_host
        assert site_id == "site_correct_host"
        assert drive_id == "drive_documents"
        assert source == "dynamic"

@pytest.mark.asyncio
async def test_get_sharepoint_drive_id_ambiguity_rejection():
    """Verify that multiple matching sites with correct hostname raises ValueError (fail-closed)."""
    _drive_cache.clear()
    
    with patch("requests.get") as mock_get:
        mock_resp_direct = MagicMock()
        mock_resp_direct.ok = False
        
        mock_resp_search = MagicMock()
        mock_resp_search.ok = True
        mock_resp_search.json.return_value = {
            "value": [
                {
                    "id": "site_1",
                    "name": "SummitOS Intelligence",
                    "displayName": "SummitOS Intelligence",
                    "webUrl": "https://costesla.sharepoint.com/sites/SummitOS%20Intelligence"
                },
                {
                    "id": "site_2",
                    "name": "SummitOS Intelligence",
                    "displayName": "SummitOS Intelligence",
                    "webUrl": "https://costesla.sharepoint.com/sites/SummitOS%20Intelligence"
                }
            ]
        }
        
        mock_get.side_effect = [mock_resp_direct, mock_resp_search]
        
        with pytest.raises(ValueError) as exc_info:
            await _get_sharepoint_drive_id("mock_token")
            
        assert "Ambiguous SharePoint site search matches" in str(exc_info.value)

@pytest.mark.asyncio
async def test_graph_count_files_paging():
    """Verify that _graph_count_files recursively follows @odata.nextLink to count all files."""
    _onedrive_count_cache.clear()
    
    with patch("api.pre_shift_check._get_sharepoint_drive_id", return_value=("site_1", "drive_1", "env", 0.0)), \
         patch("requests.get") as mock_get:
        
        # Page 1: returns nextLink and 2 files
        resp_p1 = MagicMock()
        resp_p1.status_code = 200
        resp_p1.headers = {}
        resp_p1.json.return_value = {
            "value": [
                {"name": "trip1.png"},
                {"name": "trip2.png"}
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/drives/drive_1/root:/folder:/children?$select=name&$top=999&$skip=2"
        }
        
        # Page 2: returns no nextLink and 1 file
        resp_p2 = MagicMock()
        resp_p2.status_code = 200
        resp_p2.headers = {}
        resp_p2.json.return_value = {
            "value": [
                {"name": "trip3.png"}
            ]
        }
        
        mock_get.side_effect = [resp_p1, resp_p2]
        
        count = await _graph_count_files(
            "mock_token", "folder",
            include_extensions=[".png"],
            exclude_patterns=[]
        )
        
        # Verify paging fetched both pages and summed up the counts
        assert count == 3
        assert mock_get.call_count == 2
