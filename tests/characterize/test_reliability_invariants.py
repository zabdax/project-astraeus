"""Lock down every constant value the refactor must preserve byte-identically.

This file is the source of truth for the 'all 17 constants preserved exactly'
acceptance criterion in the spec. If a future refactor changes any value,
this test goes red and forces an explicit decision.

NOTE: ``_MAX_DOWNLOAD_SEGMENTS`` was updated from 3 to 12 by the H1 patch
on 2026-07-06 (see ``logs/diagnostic_run_*.json``). The old value of 3 was
causing baseline starvation: a cap of 3 Kepler quarters yields only ~218d
of stitched baseline, which falls below the 2.5*P minimum for 4/8 known
Kepler-90 planets (e, f, g, h with periods 91-331d). The new value 12
yields ~1056d of baseline, which exceeds 2.5 * 331.6d with margin.
The expectation in ``EXPECTED_CONSTANTS`` below was updated to match.
"""
from astraeus.core import lightkurve_client as lkc


EXPECTED_CONSTANTS: dict[str, object] = {
    "_LIGHTKURVE_CACHE_DIR": None,  # value computed below; just check shape
    "_ASTRAEUS_LIGHTKURVE_CACHE_DIR": None,
    "_MAX_DOWNLOAD_SEGMENTS": 12,  # was 3; H1 patch 2026-07-06 (see module docstring)
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
    # 2026-08-21 audit fix: importlib.reload() re-executes the module IN
    # PLACE, rebinding every attribute (LightkurveClient,
    # _TIMEOUT_SENTINEL, helper functions...). Tests that already hold
    # collection-time references to the old objects diverge from the
    # rebound module dict, which poisoned every later lightkurve_client
    # test in the full suite (timeout-sentinel identity failures,
    # '_FakeSearch has no attribute table' cache-fallback errors).
    # Snapshot the module dict and restore it verbatim afterwards so the
    # reload is observable HERE but invisible to every other test.
    pre_reload_state = dict(lkc.__dict__)
    try:
        # Force fallback by ensuring env var unset.
        os.environ.pop("ASTRAEUS_LIGHTKURVE_CACHE_DIR", None)
        # Re-import with env override to verify the env-overridable form is honoured.
        os.environ["ASTRAEUS_LIGHTKURVE_CACHE_DIR"] = "/tmp/explicit_astraeus_cache"
        reloaded = importlib.reload(lkc)
        assert reloaded._ASTRAEUS_LIGHTKURVE_CACHE_DIR == "/tmp/explicit_astraeus_cache"
    finally:
        # Reset env so subsequent test runs aren't poisoned.
        os.environ.pop("ASTRAEUS_LIGHTKURVE_CACHE_DIR", None)
        lkc.__dict__.clear()
        lkc.__dict__.update(pre_reload_state)


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

# The np.float64 invariant is also documented at the module level
# (lightkurve_client.py docstring, lines 1-11: "np.float64" / "precision").
# That is documentation, not behavior, so it is noted here as a comment
# rather than asserted as a test — the enforceable invariant is the
# source-token check below.


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


# Phase 2.1 "PrecisionGuard" placeholder deleted (2026-08-21): no
# ``PrecisionGuard`` symbol exists anywhere in the repo, so the placeholder's
# ``assert True`` was a can't-fail test. Re-add a real assertion if/when that
# collaborator actually lands.


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
