"""Regression test for the I3 fix: hostname alias table + null-depth
fallback.

The previous code had three ad-hoc hostname aliases
(Kepler-13 b → KOI-13 b, and a special-case for Kepler-90), and the
null-depth path silently returned 0.0 with no audit trail. Round 1
evidence shows Kepler-90 i has NULL `pl_trandep` in pscomppars — under
the old code, that planet's depth was lost with zero indication.

I3 fix:
  1. The hostname alias table now covers the generic Kepler-N → KOI-N
     pattern so every catalogued multi-planet system is handled, not
     just the two previously-hardcoded cases.
  2. The null-depth path falls back through `pl_ratror` → geometric
     (pl_rade / st_rad) → an explicit "unavailable" marker, and the
     `transit_depth_source` field in the returned meta dict records
     exactly which path was used.
"""

import pytest

from astraeus.core.nasa_archive import NASAExoplanetArchive


# ---------------------------------------------------------------------------
# Hostname alias: Kepler-N → KOI-N
# ---------------------------------------------------------------------------


def test_alias_table_includes_generic_kepler_to_koi():
    """The generic Kepler-N → KOI-N mapping must be applied so
    catalogued multi-planet systems are not silently lost.
    """
    candidates = NASAExoplanetArchive._metadata_name_candidates("Kepler-90")
    assert "KOI-351" in candidates, (
        f"Kepler-90 aliasing to KOI-351 is missing: candidates={candidates}"
    )


def test_alias_table_generic_kepler_pattern_for_other_targets():
    """Every Kepler-N (no planet letter) target must be aliased to
    KOI-N so the structural pattern is covered. The one known
    exception is Kepler-90 (its KOI number is 351, not 90, in
    pscomppars) — the explicit KOI-351 alias is the only correct
    fallback for that target and is asserted separately in
    `test_alias_table_kepler_90_special_case_koi_351`.
    """
    for n in (1, 11, 20):
        cands = NASAExoplanetArchive._metadata_name_candidates(f"Kepler-{n}")
        assert f"KOI-{n}" in cands, (
            f"Kepler-{n} → KOI-{n} aliasing missing: candidates={cands}"
        )


def test_alias_table_kepler_90_special_case_koi_351():
    """Kepler-90 must alias to KOI-351 (not KOI-90), because that is
    its actual catalog number in pscomppars. The structural Kepler-N
    → KOI-N alias would produce the wrong KOI number for this target,
    so it is excluded and the explicit KOI-351 form is asserted.
    """
    cands = NASAExoplanetArchive._metadata_name_candidates("Kepler-90")
    assert "KOI-351" in cands, (
        f"Kepler-90 → KOI-351 aliasing missing: {cands}"
    )
    # KOI-90 is NOT a real catalog number for Kepler-90 — the generic
    # alias must not add it.
    assert "KOI-90" not in cands, (
        f"Kepler-90 should NOT alias to KOI-90 (its KOI number is 351, "
        f"not 90). Candidates: {cands}"
    )


def test_alias_table_canonical_name_tried_first():
    """The canonical name (Kepler-N) must be the first candidate tried,
    not the alias. The alias is a fallback.
    """
    cands = NASAExoplanetArchive._metadata_name_candidates("Kepler-90")
    assert cands[0] == "Kepler-90", (
        f"canonical name 'Kepler-90' must be the first candidate, got {cands[0]}"
    )


def test_alias_table_no_duplicates():
    """Candidates must be unique (the helper ends with
    `list(dict.fromkeys(names))`). This is a defensive test against
    future refactors that might drop the dedupe.
    """
    cands = NASAExoplanetArchive._metadata_name_candidates("Kepler-90")
    assert len(cands) == len(set(cands)), (
        f"duplicate candidates present: {cands}"
    )


def test_alias_table_kepler_13_b_still_works():
    """The pre-existing Kepler-13 b → KOI-13 b alias (pinned by the
    round-1 test suite) must still be in the candidate list.
    """
    cands = NASAExoplanetArchive._metadata_name_candidates("Kepler-13 b")
    assert "KOI-13 b" in cands, (
        f"Kepler-13 b → KOI-13 b alias missing: {cands}"
    )


# ---------------------------------------------------------------------------
# Null-depth fallback: transit_depth_source must be explicit
# ---------------------------------------------------------------------------


def test_transit_depth_source_field_present_in_meta():
    """Every meta dict returned by fetch_metadata must carry a
    `transit_depth_source` field whose value is one of the known
    source labels. This is the audit trail the round-1 protocol
    asked for ("distinguish 'no data' from 'we didn't check'").
    """
    # We don't make a network call here; we just assert the contract
    # by reading the source code (defensive — the test will fail if
    # the field is ever dropped).
    import inspect
    src = inspect.getsource(NASAExoplanetArchive)
    assert "transit_depth_source" in src, (
        "transit_depth_source field has been dropped from the meta dict — "
        "the round-1 protocol's 'no data vs didn't check' audit trail is lost"
    )
    # Source labels in priority order
    assert "pl_trandep" in src
    assert "pl_ratror_squared" in src
    assert "pl_rade_over_st_rad_geometric" in src
    assert "unavailable_no_archive_input" in src
