"""Unit tests for the RemoteDiscoveryEngine module."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from astraeus.data.discovery import RemoteDiscoveryEngine


@patch("astraeus.data.discovery.NasaExoplanetArchive.query_criteria")
def test_query_metadata_pscomppars_success(mock_query):
    """Test metadata query falling back to pscomppars."""
    mock_row = {
        "pl_name": "WASP-12 b",
        "pl_orbper": 1.09,
        "st_rad": 1.5,
        "pl_trandep": 1.4
    }
    
    # Mock return value as a list of dicts
    mock_query.return_value = [mock_row]
    
    res = RemoteDiscoveryEngine.query_metadata("WASP-12 b")
    
    assert res["pl_name"] == "WASP-12 b"
    assert res["pl_orbper"] == 1.09
    assert res["st_rad"] == 1.5
    assert res["pl_trandep"] == 1.4
    assert res["source_table"] == "pscomppars"


@patch("astraeus.data.discovery.lk.search_lightcurve")
def test_fetch_time_series_success(mock_search):
    """Test lightkurve streaming and stitching logic."""
    mock_search_result = MagicMock()
    mock_search_result.__len__.return_value = 5 # Pretend 5 segments found
    
    # Limit to first 3
    mock_limited_search = MagicMock()
    mock_search_result.__getitem__.return_value = mock_limited_search
    
    mock_collection = MagicMock()
    mock_limited_search.download_all.return_value = mock_collection
    
    mock_stitched = MagicMock()
    mock_collection.stitch.return_value = mock_stitched
    
    mock_flattened = MagicMock()
    mock_stitched.flatten.return_value = mock_flattened
    mock_cleaned = MagicMock()
    mock_flattened.remove_nans.return_value = mock_cleaned
    
    mock_cleaned.time.value = [1.0, 2.0, 3.0]
    mock_cleaned.flux.value = [1.0, 0.99, 1.0]
    mock_cleaned.flux_err.value = [0.01, 0.01, 0.01]
    
    mock_search.return_value = mock_search_result
    
    arrays = RemoteDiscoveryEngine.fetch_time_series("WASP-12 b", "Kepler")
    
    assert arrays is not None
    t, f, e = arrays
    assert len(t) == 3
    assert t[1] == 2.0
    assert f[1] == 0.99
    assert e[1] == 0.01


@patch("astraeus.data.discovery.RemoteDiscoveryEngine.query_metadata")
@patch("astraeus.data.discovery.RemoteDiscoveryEngine.fetch_time_series")
def test_discover_and_cache(mock_fetch, mock_query):
    """Test full integration and cache storage."""
    mock_query.return_value = {"pl_name": "WASP-12 b"}
    
    # Return time, flux, flux_err with a NaN inside
    mock_fetch.return_value = (
        np.array([2.0, 1.0, np.nan]), 
        np.array([1.0, 1.0, 1.0]), 
        np.array([0.1, 0.1, 0.1])
    )
    
    res = RemoteDiscoveryEngine.discover_and_cache("WASP-12 b", "Kepler")
    
    assert res["status"] == "success"
    assert res["metadata"]["pl_name"] == "WASP-12 b"
    
    # Should be sorted chronologically and NaN removed
    assert len(res["time"]) == 2
    assert res["time"][0] == 1.0
    assert res["time"][1] == 2.0

