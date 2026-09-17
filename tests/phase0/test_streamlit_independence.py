"""Phase 0: the engine boundary -- scientific ingestion without Streamlit.

PRD v4.1 §4.1 / §19. The desired invariant:

    RemoteDiscoveryEngine.fetch_data() works without Streamlit installed.

Before Phase 0, `astraeus/core/ingestion.py::_cached_fetch_data` did
`import streamlit as st` + `@st.cache_data(ttl=3600)` inside the function
body and bound the result as `RemoteDiscoveryEngine.fetch_data` at import
time. Importing the module succeeded, but CALLING fetch_data raised
ImportError in any environment without Streamlit -- a hard, live-reachable
coupling from the scientific ingestion path to the web framework.

This test forces Streamlit absent the same way PRD §4.1 did: by setting
sys.modules['streamlit'] = None, which makes `import streamlit` raise.
"""

from __future__ import annotations

import sys

import pytest

INGESTION_MODULES = (
    "astraeus.core",
    "astraeus.core.ingestion",
    "astraeus.analysis",
    "astraeus.analysis.detection",
    "astraeus.core.orchestrator",
    "astraeus.data.adapter",
)


@pytest.fixture
def without_streamlit(monkeypatch):
    """Make `import streamlit` raise ModuleNotFoundError for the duration."""
    monkeypatch.setitem(sys.modules, "streamlit", None)


@pytest.fixture
def offline_ingestion(monkeypatch, without_streamlit):
    """Return the ingestion module with a recording fake fetch backend."""
    from astraeus.core import ingestion as ing

    calls = []

    def fake_impl(t, m):
        calls.append((t, m))
        return {"status": "success", "time": [], "flux": [], "flux_err": []}

    monkeypatch.setattr(
        ing.RemoteDiscoveryEngine, "_fetch_data_impl", staticmethod(fake_impl)
    )
    ing._clear_fetch_cache()
    return ing, calls


@pytest.mark.parametrize("module", INGESTION_MODULES)
def test_engine_modules_import_without_streamlit(module, without_streamlit):
    """Every engine module must import with Streamlit unavailable."""
    __import__(module)
    assert sys.modules[module] is not None


def test_fetch_data_executes_without_streamlit(offline_ingestion):
    """THE headline invariant: the real ingestion path must execute."""
    ing, calls = offline_ingestion
    out = ing._cached_fetch_data("Kepler-11", "Kepler")
    assert out["status"] == "success"
    assert calls == [("Kepler-11", "Kepler")]


def test_fetch_data_caches_within_ttl(offline_ingestion):
    """The framework-neutral replacement preserves the original
    st.cache_data(ttl=3600) semantics: a second call within the TTL must
    not re-execute the underlying fetch."""
    ing, calls = offline_ingestion
    ing._cached_fetch_data("Kepler-90", "Kepler")
    ing._cached_fetch_data("Kepler-90", "Kepler")
    assert len(calls) == 1, f"expected one fetch within TTL, got {len(calls)}"


def test_clear_fetch_cache_forces_refetch(offline_ingestion):
    ing, calls = offline_ingestion
    ing._cached_fetch_data("TRAPPIST-1", "TESS")
    ing._clear_fetch_cache()
    ing._cached_fetch_data("TRAPPIST-1", "TESS")
    assert len(calls) == 2


def test_cache_key_distinguishes_missions(offline_ingestion):
    ing, calls = offline_ingestion
    ing._cached_fetch_data("Kepler-90", "Kepler")
    ing._cached_fetch_data("Kepler-90", "TESS")
    assert ("Kepler-90", "Kepler") in calls
    assert ("Kepler-90", "TESS") in calls


def test_no_streamlit_symbol_in_the_hard_ingestion_path():
    """Static guard: the ingestion module must not EXECUTABLY reference
    Streamlit. A future regression that re-introduces
    `import streamlit` at module level (or inside _cached_fetch_data)
    fails here instead of silently re-coupling the engine.

    Uses the AST rather than string matching so docstrings and comments
    may legitimately mention Streamlit (this test's own history note
    does); only real Import / ImportFrom nodes are forbidden.
    """
    import ast

    from astraeus.core import paths

    source = (paths._PACKAGE_DIR / "core" / "ingestion.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any("streamlit" in name for name in names):
            offenders.append((node.lineno, names))
    assert not offenders, (
        "ingestion.py contains executable Streamlit imports at lines "
        f"{offenders}. The engine boundary (PRD §4.1) forbids the "
        "scientific ingestion path from depending on the web framework."
    )
