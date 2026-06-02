"""Unit tests for the format-agnostic DataAdapter class."""

import io
import sys
import numpy as np
import pandas as pd
from astropy.io import fits
import pytest

from astraeus.data.adapter import DataAdapter


def test_adapter_csv_happy_path():
    """Verify that DataAdapter parses and maps a typical, clean CSV file correctly."""
    # Construct a CSV with lowercase and mixed case headers
    data = {"Time": [1.0, 2.0, 3.0], "flux": [10.0, 9.9, 10.1], "FLUX_ERR": [0.1, 0.1, 0.1]}
    df = pd.DataFrame(data)

    csv_bytes = df.to_csv(index=False).encode("utf-8")

    adapter = DataAdapter(csv_bytes, "csv")
    result = adapter.parse()

    assert np.allclose(result["time"], [1.0, 2.0, 3.0])
    assert np.allclose(result["flux"], [10.0, 9.9, 10.1])
    assert np.allclose(result["flux_err"], [0.1, 0.1, 0.1])
    assert result["metadata"] == {}


def test_adapter_csv_noise_and_sorting():
    """Verify that DataAdapter cleans out NaNs, Infs, and chronologically sorts CSV arrays."""
    # Data has NaNs, Infs, and out-of-order time coordinates
    data = {
        "bjd_tdb": [3.0, 1.0, np.nan, 2.0, 4.0],
        "pdcsap_flux": [1.0, 1.1, 1.2, np.inf, 1.3],
        "pdcsap_flux_err": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    df = pd.DataFrame(data)
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    adapter = DataAdapter(csv_bytes, "lightcurve.csv")
    result = adapter.parse()

    # Out-of-order timestamps: [3.0, 1.0, nan, 2.0, 4.0]
    # NaNs and Infs filter:
    # Row 0: Time=3.0, Flux=1.0, Err=0.01 -> Valid
    # Row 1: Time=1.0, Flux=1.1, Err=0.02 -> Valid
    # Row 2: Time=NaN -> Invalid
    # Row 3: Flux=Inf -> Invalid
    # Row 4: Time=4.0, Flux=1.3, Err=0.05 -> Valid
    # Valid indices remaining: Row 1 (Time=1.0), Row 0 (Time=3.0), Row 4 (Time=4.0)
    # Sorted chronologically:
    # Time: [1.0, 3.0, 4.0]
    # Flux: [1.1, 1.0, 1.3]
    # Err:  [0.02, 0.01, 0.05]

    assert len(result["time"]) == 3
    assert np.array_equal(result["time"], [1.0, 3.0, 4.0])
    assert np.array_equal(result["flux"], [1.1, 1.0, 1.3])
    assert np.array_equal(result["flux_err"], [0.02, 0.01, 0.05])


def test_adapter_json():
    """Verify that DataAdapter successfully parses JSON data from bytes."""
    data = [
        {"time": 10.0, "flux": 1.0, "flux_err": 0.01},
        {"time": 11.0, "flux": 0.99, "flux_err": 0.01},
    ]
    df = pd.DataFrame(data)
    json_bytes = df.to_json(orient="records").encode("utf-8")

    adapter = DataAdapter(json_bytes, "data.json")
    result = adapter.parse()

    assert np.allclose(result["time"], [10.0, 11.0])
    assert np.allclose(result["flux"], [1.0, 0.99])
    assert np.allclose(result["flux_err"], [0.01, 0.01])


def test_adapter_fits_parsing():
    """Verify that DataAdapter parses in-memory FITS byte streams and extracts metadata."""
    # Dynamically build a FITS file in-memory using astropy
    col_time = fits.Column(name="TIME", format="D", array=np.array([1.5, np.nan, 2.5, 3.5]))
    col_flux = fits.Column(name="SAP_FLUX", format="E", array=np.array([100.0, 101.0, np.inf, 103.0]))
    col_err = fits.Column(name="SAP_FLUX_ERR", format="E", array=np.array([1.0, 1.1, 1.2, 1.3]))

    table_hdu = fits.BinTableHDU.from_columns([col_time, col_flux, col_err])

    primary_hdu = fits.PrimaryHDU()
    primary_hdu.header["OBJECT"] = "HAT-P-11b"
    primary_hdu.header["RA"] = 297.71
    primary_hdu.header["DEC"] = 48.08
    primary_hdu.header["INSTRUME"] = "Kepler"

    hdul = fits.HDUList([primary_hdu, table_hdu])

    buf = io.BytesIO()
    hdul.writeto(buf)
    fits_bytes = buf.getvalue()

    adapter = DataAdapter(fits_bytes, "target_lc.fits")
    result = adapter.parse()

    # Valid mask keeps Row 0 (Time 1.5, Flux 100.0, Err 1.0) and Row 3 (Time 3.5, Flux 103.0, Err 1.3)
    assert len(result["time"]) == 2
    assert np.allclose(result["time"], [1.5, 3.5])
    assert np.allclose(result["flux"], [100.0, 103.0])
    assert np.allclose(result["flux_err"], [1.0, 1.3])

    # Metadata extraction
    assert result["metadata"]["object"] == "HAT-P-11b"
    assert np.isclose(result["metadata"]["ra"], 297.71)
    assert np.isclose(result["metadata"]["dec"], 48.08)
    assert result["metadata"]["instrume"] == "Kepler"


def test_adapter_column_override():
    """Verify that custom column name overrides bypass typical heuristical mappings."""
    data = {"custom_t": [1.0, 2.0], "custom_f": [5.0, 6.0], "custom_e": [0.1, 0.2]}
    df = pd.DataFrame(data)
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    column_map = {"time": "custom_t", "flux": "custom_f", "flux_err": "custom_e"}
    adapter = DataAdapter(csv_bytes, "csv", column_map=column_map)
    result = adapter.parse()

    assert np.allclose(result["time"], [1.0, 2.0])
    assert np.allclose(result["flux"], [5.0, 6.0])
    assert np.allclose(result["flux_err"], [0.1, 0.2])


def test_adapter_unsupported_format():
    """Verify that unsupported formats trigger a ValueError."""
    with pytest.raises(ValueError, match="Unsupported file format"):
        adapter = DataAdapter(b"some data", "unsupported.txt")
        adapter.parse()


def test_adapter_streamlit_integration(monkeypatch):
    """Verify that DataAdapter successfully populates st.session_state.active_data."""
    # Mock streamlit
    class MockSessionState(dict):
        pass

    class MockStreamlit:
        session_state = MockSessionState()

    sys.modules["streamlit"] = MockStreamlit

    # Reset streamlit active_data mock
    MockStreamlit.session_state.clear()

    data = {"time": [1.0, 2.0], "flux": [10.0, 10.0], "flux_err": [0.1, 0.1]}
    df = pd.DataFrame(data)
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    adapter = DataAdapter(csv_bytes, "csv")
    result = adapter.parse()

    # Verify state was saved to mock active_data
    assert "active_data" in MockStreamlit.session_state
    saved_data = MockStreamlit.session_state["active_data"]
    assert np.allclose(saved_data["time"], [1.0, 2.0])
    assert np.allclose(saved_data["flux"], [10.0, 10.0])

    # Clean up mock streamlit
    del sys.modules["streamlit"]
