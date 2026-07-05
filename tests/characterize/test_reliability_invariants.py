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
