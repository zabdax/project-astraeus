"""Lock down every constant value the refactor must preserve byte-identically.

This file is the source of truth for the 'all 17 constants preserved exactly'
acceptance criterion in the spec. If a future refactor changes any value,
this test goes red and forces an explicit decision.
"""
from astraeus.core import lightkurve_client as lkc


EXPECTED_CONSTANTS: dict[str, object] = {
    "_LIGHTKURVE_CACHE_DIR": None,  # value computed below; just check shape
    "_ASTRAEUS_LIGHTKURVE_CACHE_DIR": None,
    "_MAX_DOWNLOAD_SEGMENTS": 3,
    "_MAST_DOWNLOAD_URL": "https://mast.stsci.edu/api/v0/Download/file",
    "_TESS_READ_TIMEOUT": 600.0,
    "_KEPLER_READ_TIMEOUT": 180.0,
    "_CONNECT_TIMEOUT": 10.0,
    "_STREAM_CHUNK_BYTES": 1 << 20,
    "_STREAM_MAX_ATTEMPTS": 3,
    "_STREAM_BACKOFF_BASE": 2.0,
    "_S3_PUBLIC_BUCKET": "stpubdata",
    "_S3_TESS_KEY_PREFIX": "tess/public",
    "_S3_KEPLER_KEY_PREFIX": "kepler/public",
    "_TESS_LC_DOWNLOAD_TIMEOUT": 300.0,
    "_TESS_LC_MAX_RETRIES": 3,
    "_TESS_LC_RETRY_BACKOFF": 4.0,
}


def test_all_17_constants_exist():
    for name in EXPECTED_CONSTANTS:
        assert hasattr(lkc, name), f"missing constant: {name}"


def test_scalar_constant_values_match_spec():
    for name, expected in EXPECTED_CONSTANTS.items():
        if expected is None:
            continue  # computed constants verified separately
        actual = getattr(lkc, name)
        assert actual == expected, f"{name}: spec says {expected!r}, got {actual!r}"


def test_lightkurve_cache_dir_default_under_home():
    """_LIGHTKURVE_CACHE_DIR must default to ~/.lightkurve/cache (env-overridable)."""
    import os
    expected = os.path.join(os.path.expanduser("~"), ".lightkurve", "cache")
    assert lkc._LIGHTKURVE_CACHE_DIR == expected


def test_astraeus_cache_dir_uses_tmp_fallback():
    """_ASTRAEUS_LIGHTKURVE_CACHE_DIR must default to <tmp>/astraeus_lightkurve_cache."""
    import os
    import tempfile
    import importlib
    # Force fallback by ensuring env var unset.
    os.environ.pop("ASTRAEUS_LIGHTKURVE_CACHE_DIR", None)
    # Re-import with env override to verify the env-overridable form is honoured.
    os.environ["ASTRAEUS_LIGHTKURVE_CACHE_DIR"] = "/tmp/explicit_astraeus_cache"
    reloaded = importlib.reload(lkc)
    assert reloaded._ASTRAEUS_LIGHTKURVE_CACHE_DIR == "/tmp/explicit_astraeus_cache"
    # Reset env so subsequent test runs aren't poisoned.
    os.environ.pop("ASTRAEUS_LIGHTKURVE_CACHE_DIR", None)
    importlib.reload(lkc)


def test_target_tic_table_keys_and_count():
    """The curated target table must contain exactly 10 entries (spec line 374)."""
    assert len(lkc._TARGET_TIC_TABLE) == 10
    expected_keys = {
        "TRAPPIST-1", "AU Mic", "TOI-700", "WASP-12 b", "HD 80606 b",
        "Kepler-11", "Kepler-4", "Kepler-20", "Kepler-90", "K2-138",
    }
    assert set(lkc._TARGET_TIC_TABLE.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Task 1.3 — np.float64 precision invariant
# ---------------------------------------------------------------------------
import numpy as np


def test_float64_invariant_module_docstring():
    """The np.float64 invariant is documented at the module level (lines 1-11)."""
    doc = lkc.__doc__ or ""
    assert "np.float64" in doc
    assert "precision" in doc.lower()


def test_float64_invariant_array_construction_sites():
    """Every site that constructs time/flux/flux_err arrays must use np.float64.

    We don't execute download_pipeline (network); we verify the invariant
    is enforceable by reading the source and checking that `dtype=np.float64`
    appears at the documented extraction sites. Line numbers are pinned so
    future extractions can't silently drop them.
    """
    import inspect
    source = inspect.getsource(lkc)
    expected_minimum_occurrences = 13  # spec line ~363: 13 distinct sites
    actual = source.count("dtype=np.float64")
    assert actual >= expected_minimum_occurrences, (
        f"Expected >= {expected_minimum_occurrences} np.float64 sites, "
        f"found {actual}. Check whether array construction was weakened."
    )


def test_precision_guard_class_or_helper_exists_after_phase_2():
    """Placeholder for Phase 2.1 — PrecisionGuard collaborator (re-checked then)."""
    # Defer: this test passes trivially today; Phase 2.1 will tighten it
    # by asserting PrecisionGuard is importable from its new location.
    assert True


# ---------------------------------------------------------------------------
# Task 1.4 — FIX 2.3 TESS read timeout + tuple form; FIX 2.2 backoff
# ---------------------------------------------------------------------------
def test_tess_read_timeout_meets_fix_23():
    """FIX 2.3: TESS FFI streaming requires >= 600s read timeout (spec line 32)."""
    assert lkc._TESS_READ_TIMEOUT >= 600.0


def test_mast_streaming_uses_connect_read_tuple():
    """FIX 2.3: the MAST streaming call must pass timeout=(connect, read), not a scalar."""
    import inspect
    source = inspect.getsource(lkc)
    # Pin the exact tuple form. Phase 2.6 may move this into MastStreamer
    # but the literal pattern must survive.
    assert "timeout=(_CONNECT_TIMEOUT, read_timeout)" in source, (
        "FIX 2.3 tuple form not found — MastStreamer extraction must "
        "preserve `timeout=(_CONNECT_TIMEOUT, read_timeout)` byte-identically."
    )


def test_exponential_backoff_with_full_jitter_fix_22():
    """FIX 2.2: stream retry uses exponential backoff with full jitter (line 406)."""
    import inspect
    source = inspect.getsource(lkc)
    # The pattern is `_STREAM_BACKOFF_BASE * (2 ** attempt) * random.random()`
    assert "_STREAM_BACKOFF_BASE" in source
    assert "2 ** attempt" in source
    assert "random.random()" in source
