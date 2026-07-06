"""Lock down DataAdapter(bytes, name).parse() for each format."""
from __future__ import annotations

import io
import json as _json

import numpy as np
import pytest

from astraeus.data.adapter import DataAdapter


def test_parse_csv_returns_time_flux_err_arrays():
    csv_bytes = b"time,flux,flux_err\n0.0,1.0,0.01\n1.0,0.99,0.01\n2.0,1.0,0.01\n"
    adapter = DataAdapter(csv_bytes, "test.csv")
    out = adapter.parse()
    assert "time" in out
    assert "flux" in out
    assert "flux_err" in out
    assert out["time"].dtype == np.float64
    assert out["flux"].dtype == np.float64
    assert out["flux_err"].dtype == np.float64


def test_parse_json_returns_time_flux_err_arrays():
    payload = [{"time": 0.0, "flux": 1.0, "flux_err": 0.01},
               {"time": 1.0, "flux": 0.99, "flux_err": 0.01}]
    adapter = DataAdapter(_json.dumps(payload).encode(), "test.json")
    out = adapter.parse()
    assert out["time"].dtype == np.float64
    assert len(out["time"]) == 2


def test_parse_fits_returns_arrays_and_metadata():
    """Use a minimal in-memory FITS file."""
    from astropy.io import fits

    cols = fits.ColDefs([
        fits.Column(name="TIME", format="D", array=np.array([0.0, 1.0, 2.0])),
        fits.Column(name="PDCSAP_FLUX", format="D", array=np.array([1.0, 0.99, 1.0])),
        fits.Column(name="PDCSAP_FLUX_ERR", format="D", array=np.array([0.01, 0.01, 0.01])),
    ])
    hdu = fits.BinTableHDU.from_columns(cols)
    hdul = fits.HDUList([fits.PrimaryHDU(), hdu])
    buf = io.BytesIO()
    hdul.writeto(buf)
    hdul.close()

    adapter = DataAdapter(buf.getvalue(), "test.fits")
    out = adapter.parse()
    assert "time" in out
    assert "flux" in out
    assert "flux_err" in out
    assert "metadata" in out
    assert out["time"].dtype == np.float64


def test_parse_unsupported_extension_raises_value_error():
    adapter = DataAdapter(b"junk", "test.parquet")
    with pytest.raises(ValueError) as exc_info:
        adapter.parse()
    assert "parquet" in str(exc_info.value).lower()
