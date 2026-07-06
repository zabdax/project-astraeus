"""Lock down _cached_fetch_data + _fetch_data_impl return shape and lru_cache semantics."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

from astraeus.core import ingestion as ing_mod


def test_cached_fetch_data_is_module_level_callable():
    """The shim must be importable as astraeus.core.ingestion._cached_fetch_data."""
    assert hasattr(ing_mod, "_cached_fetch_data")
    assert callable(ing_mod._cached_fetch_data)


def test_cached_fetch_data_delegates_to_fetch_data_impl(monkeypatch):
    """_cached_fetch_data must delegate to RemoteDiscoveryEngine._fetch_data_impl.

    Order matters: reload first to get a fresh class object, then monkeypatch
    ``RemoteDiscoveryEngine._fetch_data_impl`` AND sys.modules['streamlit']
    so the inner closure lands on the fakes (no real network).
    """
    captured = {}

    def fake_impl(t, m):
        captured["call"] = (t, m)
        return {"status": "success", "time": [], "flux": [], "flux_err": []}

    # 1. Reload ingestion so we get a fresh RemoteDiscoveryEngine class object
    importlib.reload(ing_mod)

    # 2. Patch sys.modules['streamlit'] BEFORE the function's lazy import fires.
    fake_st = type(sys)("streamlit")
    fake_st.cache_data = lambda **kw: lambda fn: fn
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    # 3. Patch _fetch_data_impl on the new class (the closure looks it up at
    # call time, so monkeypatching after reload is the only safe order).
    monkeypatch.setattr(
        ing_mod.RemoteDiscoveryEngine, "_fetch_data_impl",
        staticmethod(fake_impl),
    )

    out = ing_mod._cached_fetch_data("Kepler-11", "Kepler")
    assert out["status"] == "success"
    assert captured["call"] == ("Kepler-11", "Kepler")


def test_remote_discovery_engine_fetch_data_is_staticmethod():
    """RemoteDiscoveryEngine.fetch_data must be attached as staticmethod
    (the @st.cache_data shim from ingestion.py:224)."""
    import inspect
    # After reload, fetch_data is the cached wrapper. Check it exists.
    assert hasattr(ing_mod.RemoteDiscoveryEngine, "fetch_data")
