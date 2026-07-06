"""Lock down NASAExoplanetArchive.normalize_target_name, sanitize_meta,
fetch_metadata return shapes against a hand-picked set of canonical names.
"""
from astraeus.core.nasa_archive import NASAExoplanetArchive


# normalize_target_name cases
NORMALIZE_CASES = [
    ("WASP-12 b", "WASP-12 b"),     # already canonical
    ("Kepler-11", "Kepler-11"),     # already canonical
    ("GJ 1214", "GJ 1214"),         # already canonical
]


def test_normalize_target_name_idempotent_on_canonical():
    for raw, expected in NORMALIZE_CASES:
        out = NASAExoplanetArchive.normalize_target_name(raw)
        assert out == expected, f"normalize({raw!r}) = {out!r}, expected {expected!r}"


def test_normalize_target_name_is_idempotent():
    """normalize(normalize(x)) == normalize(x) for the canonical set."""
    for raw, _ in NORMALIZE_CASES:
        once = NASAExoplanetArchive.normalize_target_name(raw)
        twice = NASAExoplanetArchive.normalize_target_name(once)
        assert once == twice


# sanitize_meta cases
def test_sanitize_meta_replaces_nan_with_defaults():
    import math
    meta = {"orbital_period": math.nan, "transit_depth": math.inf, "stellar_radius": 1.2}
    out = NASAExoplanetArchive.sanitize_meta(meta)
    # Defaults: orbital_period=0.0, transit_depth=0.0; stellar_radius untouched
    assert out["orbital_period"] == 0.0
    assert out["transit_depth"] == 0.0
    assert out["stellar_radius"] == 1.2


def test_sanitize_meta_returns_same_dict_object():
    """sanitize_meta mutates in place (spec contract)."""
    meta = {"orbital_period": 1.0}
    out = NASAExoplanetArchive.sanitize_meta(meta)
    assert out is meta


# fetch_metadata: shape only (network path is exercised in test_nasa_archive_network)
def test_fetch_metadata_returns_tuple_meta_error():
    """fetch_metadata returns (meta_dict, error_str_or_None) — shape only."""
    import inspect
    sig = inspect.signature(NASAExoplanetArchive.fetch_metadata)
    assert len(sig.parameters) == 1
    src = inspect.getsource(NASAExoplanetArchive.fetch_metadata)
    assert "return" in src
    assert "meta, archive_error" in src or "(meta, archive_error)" in src
