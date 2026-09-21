"""Contract tests for the Phase 1 boundary modules (P1-A/B/C).

Each test below pins a *measured* defect from the PRD v4.1 audit, so a
regression is a test failure rather than a silent scientific change.
Run with the rest of the fast gate: ``pytest tests/contracts/``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from astraeus.contracts import (
    ArtifactRef,
    ArtifactStore,
    Dataset,
    Mission,
    Provenance,
    TargetRef,
    TimeUnit,
)
from astraeus.contracts.analysis_result import (
    ANALYSIS_RESULT_SCHEMA_VERSION,
    LEGACY_ALIASES,
    LEGACY_KEY_TO_CANONICAL,
    LEGACY_KEY_UNIVERSE,
    LEGACY_KEYS_MOVED_OFF_RESULT,
    LEGACY_VERDICT_TO_CANONICAL,
    JobStage,
    JobStatus,
    VettingVerdict,
    from_legacy_result_dict,
)
from astraeus.contracts.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    EffectiveConfig,
    EnvironmentRecord,
    PackageVersions,
    capture_provenance,
    canonical_provenance_json,
    write_provenance_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _lc(n: int = 300, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    time = np.sort(rng.uniform(100.0, 1100.0, n))
    flux = 1.0 + 0.001 * np.sin(2 * np.pi * time / 50.0) + rng.normal(0, 5e-4, n)
    flux_err = np.full(n, 5e-4)
    return time, flux, flux_err


@pytest.fixture
def target() -> TargetRef:
    return TargetRef(name="Kepler-90", mission=Mission.KEPLER, resolved_id="KIC-11442793")


@pytest.fixture
def dataset(target: TargetRef) -> Dataset:
    time, flux, err = _lc()
    return Dataset.from_arrays(time, flux, err, target=target)


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts")


# ===========================================================================
# P1-A -- canonical Dataset contract
# ===========================================================================


class TestDatasetIdentity:
    """PRD §5 / §7: the hash must cover the ARRAYS, not the metadata."""

    def test_hash_is_stable_across_constructions(self, target):
        time, flux, err = _lc()
        a = Dataset.from_arrays(time, flux, err, target=target)
        b = Dataset.from_arrays(time, flux, err, target=target)
        assert a.dataset_id == b.dataset_id
        assert a == b  # equality IS identity
        assert hash(a) == hash(b)

    def test_different_arrays_produce_different_hash(self, target):
        time, flux, err = _lc()
        a = Dataset.from_arrays(time, flux, err, target=target)
        b = Dataset.from_arrays(time, flux * 1.0001, err, target=target)
        assert a.dataset_id != b.dataset_id

    def test_cadence_collision_is_fixed(self, target):
        """The exact measured bug: identical metadata, different cadence
        count, collided under ``sha256(metadata)``."""
        time, flux, err = _lc(n=300)
        full = Dataset.from_arrays(time, flux, err, target=target)
        # Same target/mission/label, FEWER cadences -- metadata-identical.
        trimmed = Dataset.from_arrays(time[:100], flux[:100], err[:100], target=target)
        assert full.dataset_id != trimmed.dataset_id
        assert full.n_cadence == 300
        assert trimmed.n_cadence == 100

    def test_metadata_alone_does_not_change_identity(self, target):
        """``raw_row_dump`` differs, the arrays do not: same dataset."""
        time, flux, err = _lc()
        base = Dataset.from_arrays(time, flux, err, target=target)
        # Only the free-form provenance/source string changes.
        other = base.model_copy(update={"source": "a-different-fetch-site"})
        assert base.dataset_id == other.dataset_id

    def test_flux_err_presence_changes_identity(self, target):
        time, flux, err = _lc()
        with_err = Dataset.from_arrays(time, flux, err, target=target)
        without = Dataset.from_arrays(time, flux, None, target=target)
        assert with_err.dataset_id != without.dataset_id

    def test_unsorted_time_is_rejected(self, target):
        time, flux, err = _lc()
        shuffled = np.random.default_rng(3).permutation(time)
        with pytest.raises(ValueError, match="sorted"):
            Dataset.from_arrays(shuffled, flux, err, target=target)
        # ...and canonicalizable when the caller says so.
        fixed = Dataset.from_arrays(shuffled, flux, err, target=target, sort=True)
        assert fixed.is_time_sorted

    def test_length_mismatch_is_rejected(self, target):
        time, flux, _ = _lc()
        with pytest.raises(ValueError, match="length"):
            Dataset.from_arrays(time, flux[:10], None, target=target)

    def test_non_finite_is_rejected(self, target):
        time, flux, err = _lc()
        flux[5] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            Dataset.from_arrays(time, flux, err, target=target)

    def test_negative_flux_err_is_rejected(self, target):
        time, flux, _ = _lc()
        with pytest.raises(ValueError, match="non-negative"):
            Dataset.from_arrays(time, flux, np.full(len(time), -1e-4), target=target)


class TestDatasetDerivedProperties:
    def test_n_cadence_and_baseline(self, dataset):
        assert dataset.n_cadence == 300
        assert dataset.baseline_days == pytest.approx(dataset.time.max() - dataset.time.min())

    def test_cadence_seconds_is_measured_not_metadata(self, target):
        time = np.arange(0, 1000 * 0.0204, 0.0204)  # ~1764 s Kepler LC
        flux = np.ones_like(time)
        ds = Dataset.from_arrays(time, flux, None, target=target)
        assert ds.cadence_seconds == pytest.approx(0.0204 * 86400, rel=1e-6)

    def test_single_cadence_has_no_baseline(self, target):
        ds = Dataset.from_arrays(np.array([1.0]), np.array([1.0]), None, target=target)
        assert ds.baseline_days == 0.0
        assert ds.cadence_seconds is None


class TestDatasetUnitHandling:
    """PRD §18 item 4: ``time_unit`` must be CARRIED, not dropped."""

    def test_unit_is_carried(self, target):
        ds = Dataset.from_arrays(*_lc(), target=target, time_unit=TimeUnit.BJD)
        assert ds.time_unit is TimeUnit.BJD

    def test_to_bjd_converts_and_labels(self, target):
        time, flux, err = _lc()
        bkjd = Dataset.from_arrays(
            time, flux, err, target=target, time_unit=TimeUnit.BKJD
        )
        bjd = bkjd.to_bjd()
        assert bjd.time_unit is TimeUnit.BJD
        assert bjd.time == pytest.approx(bkjd.time + 2454833.0)
        # Idempotent: converting BJD again is a no-op.
        assert bjd.to_bjd().dataset_id == bjd.dataset_id

    def test_from_dict_restores_the_dropped_unit(self, target):
        """``ingestion.py:242-250`` drops this key; the seam restores it."""
        time, flux, err = _lc()
        ds = Dataset.from_dict(
            {"time": time, "flux": flux, "flux_err": err, "time_unit": "BTJD"},
            target=target,
        )
        assert ds.time_unit is TimeUnit.BTJD


class TestDatasetAdopters:
    """The seven representations all funnel into the one canonical type."""

    def test_from_tuple_three(self, target):
        time, flux, err = _lc()
        ds = Dataset.from_tuple((time, flux, err), target=target)
        assert ds.n_cadence == 300

    def test_from_tuple_two_means_no_error_column(self, target):
        time, flux, _ = _lc()
        ds = Dataset.from_tuple((time, flux), target=target)
        assert ds.flux_err is None

    def test_from_dict_orchestrator_schema(self, target):
        """``ui/pages/detective.py``'s schema: no flux_err at all."""
        time, flux, _ = _lc()
        ds = Dataset.from_dict(
            {"time": time, "flux": flux, "target_name": "Kepler-90"},
            target=target,
        )
        assert ds.flux_err is None
        assert ds.target.name == "Kepler-90"

    def test_from_dict_ingestion_schema(self, target):
        time, flux, err = _lc()
        ds = Dataset.from_dict(
            {
                "status": "success",
                "metadata": {"pl_name": "Kepler-90 b"},
                "time": time,
                "flux": flux,
                "flux_err": err,
                "archive_error": None,
            },
            target=target,
        )
        assert ds.n_cadence == 300

    def test_from_dict_fusion_schema(self, target):
        time, flux, err = _lc()
        ds = Dataset.from_dict(
            {
                "time": time, "flux": flux, "flux_err": err,
                "baseline": "unified", "kepler_segments": 4, "tess_segments": 0,
            },
            target=target,
        )
        assert ds.n_cadence == 300

    def test_from_lightkurve(self, target):
        time, flux, err = _lc()
        lc = SimpleNamespace(
            time=SimpleNamespace(value=time),
            flux=SimpleNamespace(value=flux),
            flux_err=SimpleNamespace(value=err),
        )
        ds = Dataset.from_lightkurve(lc, target=target)
        assert ds.n_cadence == 300

    def test_from_light_curve_data_rejects_invented_zeros(self, target):
        """``dashboard/services/data_ingestion.py:46-48`` fabricates
        ``np.zeros_like(flux)``; the canonical type reads that as ABSENT."""
        time, flux, _ = _lc()
        lcd = SimpleNamespace(time=time, flux=flux, flux_err=np.zeros_like(flux))
        ds = Dataset.from_light_curve_data(lcd, target=target)
        assert ds.flux_err is None

    def test_with_flux_err_from_mad_is_explicit(self, dataset):
        assert dataset.flux_err is not None  # fixture already has errors
        bare = dataset.model_copy(update={"flux_err": None})
        estimated = bare.with_flux_err_from_mad()
        assert estimated.flux_err is not None
        assert np.all(estimated.flux_err > 0)
        assert "mad_estimate" in estimated.source


class TestArtifactStore:
    def test_dataset_roundtrip_preserves_identity(self, store, dataset):
        ref = store.save_dataset(dataset)
        assert ref.checksum == dataset.content_hash
        assert ref.shape == (300, 3)
        reloaded = store.load_dataset(ref)
        assert reloaded == dataset

    def test_array_roundtrip(self, store):
        grid = np.column_stack([np.linspace(1, 100, 1000), np.random.rand(1000)])
        ref = store.save_array(grid, kind="periodogram")
        back = store.load_array(ref)
        assert np.array_equal(back, grid)

    def test_json_roundtrip(self, store):
        ref = store.save_json({"a": 1, "b": [1, 2]}, kind="doc")
        assert store.load_json(ref) == {"a": 1, "b": [1, 2]}

    def test_save_is_idempotent(self, store, dataset):
        a = store.save_dataset(dataset)
        b = store.save_dataset(dataset)
        assert a.path == b.path

    def test_corrupt_artifact_is_detected(self, store, dataset):
        ref = store.save_dataset(dataset)
        path = ArtifactStore.resolve(ref, store.root)
        path.write_bytes(b"not an npz")
        with pytest.raises(Exception):
            store.load_dataset(ref)

    def test_missing_artifact_raises_filenotfound(self, store, dataset):
        ref = store.save_dataset(dataset)
        bogus = ref.model_copy(update={"path": ref.path + ".nope"})
        with pytest.raises(FileNotFoundError):
            store.load_dataset(bogus)


class TestDatasetSerialization:
    def test_metadata_dict_excludes_arrays(self, dataset):
        meta = dataset.to_metadata_dict()
        assert "time" not in meta and "flux" not in meta
        assert meta["dataset_id"] == dataset.dataset_id
        json.dumps(meta)  # must be JSON-safe

    def test_json_roundtrip(self, dataset):
        text = dataset.model_dump_json()
        back = Dataset.model_validate_json(text)
        assert back.dataset_id == dataset.dataset_id

    def test_extra_keys_are_forbidden(self, target):
        with pytest.raises(Exception):
            Dataset(time=[1.0], flux=[1.0], target=target, not_a_field=1)


# ===========================================================================
# P1-C -- provenance
# ===========================================================================


class TestProvenance:
    def test_records_dataset_identity_over_arrays(self, dataset):
        prov = capture_provenance(dataset)
        assert prov.dataset_id == dataset.dataset_id
        assert prov.dataset_content_hash == dataset.content_hash
        assert prov.n_cadence == 300
        assert prov.baseline_days == pytest.approx(dataset.baseline_days)

    def test_effective_config_records_snr_floor(self, dataset):
        """PRD §7: ``snr_floor`` is not in JOB_REGISTRY today; the
        provenance record must state it."""
        prov = capture_provenance(
            dataset, effective_config=EffectiveConfig(snr_floor=7.1, max_signals=5)
        )
        assert prov.effective_config.snr_floor == 7.1
        assert prov.effective_config.max_signals == 5

    def test_package_versions_record_absence_honestly(self):
        pv = PackageVersions.capture()
        # Every field is populated -- None means "not installed", a fact.
        assert pv.numpy is not None
        assert set(pv.model_dump()) == {
            "batman", "wotan", "tls", "emcee", "numpy", "scipy",
            "astropy", "lightkurve", "streamlit",
        }

    def test_environment_records_threads_and_cpu(self):
        env = EnvironmentRecord.capture()
        assert env.cpu_count is not None and env.cpu_count >= 1
        assert env.python_version
        # BLAS threads may be None only if no threadpool and no env var;
        # on a numpy install threadpoolctl reports it.
        assert env.blas_threads is None or env.blas_threads >= 1

    def test_git_capture_never_raises(self, dataset, tmp_path):
        # A directory with no git at all must yield "unknown", not an error.
        prov = capture_provenance(dataset, repo_root=tmp_path)
        assert prov.git_sha == "unknown"

    def test_save_and_load_roundtrip(self, store, dataset):
        prov = capture_provenance(dataset)
        ref = prov.save(store)
        back = Provenance.load(store, ref)
        assert back.provenance_id == prov.provenance_id
        assert back.dataset_id == dataset.dataset_id

    def test_canonical_form_is_stable(self, dataset):
        prov = capture_provenance(dataset)
        assert canonical_provenance_json(prov) == canonical_provenance_json(prov)

    def test_standalone_json_file(self, dataset, tmp_path):
        prov = capture_provenance(dataset)
        out = write_provenance_json(prov, tmp_path / "provenance.json")
        payload = json.loads(out.read_text())
        assert payload["schema_version"] == PROVENANCE_SCHEMA_VERSION
        assert payload["dataset_content_hash"] == dataset.content_hash

    def test_schema_versions_present(self, dataset):
        prov = capture_provenance(dataset)
        assert prov.schema_version == PROVENANCE_SCHEMA_VERSION
        assert prov.pipeline_version


# ===========================================================================
# P1-B -- AnalysisResult v1
# ===========================================================================


def _legacy_full(periodogram=True, ttv=True, vetting="Verified Planet Candidate") -> dict:
    raw: dict = {
        "candidate_found": True,
        "is_candidate": True,
        "period_days": 50.0,
        "period": 50.0,
        "orbital_period": 50.0,
        "depth": 0.0005,
        "transit_depth": 0.0005,
        "duration": 0.15,
        "t0": 120.0,
        "t0_bjd": 120.0,
        "time_unit": "BJD",
        "snr": 15.2,
        "confidence_score": 8.3,
        "vetting_status": vetting,
        "vetting_confidence": 0.92,
        "u_shape_chi2": 100.0,
        "v_shape_chi2": 300.0,
        "delta_chi2_u": 200.0,
        "delta_chi2_v": 5.0,
        "v_shape_metric": 0.08,
        "flat_bottom_fraction": 0.4,
        "secondary_eclipse_depth": 0.0001,
        "secondary_eclipse_snr": 1.2,
        "secondary_eclipse_detected": False,
        "planet_radius_earth": 2.1,
        "equilibrium_temp_k": 450.0,
        "jwst_tsm_score": 0.3,
        "stellar_radius": 1.2,
        "tls_outcome": "ran_pass",
        "tls_valid": True,
        "tls_sde": 12.0,
        "tls_fap": 0.001,
        "tls_period": 50.0,
        "backends_available": {"batman": True, "wotan": True, "tls": True},
        "detrend_method": "wotan:biweight",
        "secondary_eclipse_threshold_ppm": 800.0,
        "secondary_eclipse_threshold_mode": "physical",
    }
    if periodogram:
        raw["periodogram"] = {"periods": list(np.linspace(1, 100, 90_000)),
                              "powers": list(np.random.rand(90_000))}
    if ttv:
        raw["ttv_data"] = [
            {"epoch": 0, "ttv_residual_min": 1.2},
            {"epoch": 1, "ttv_residual_min": -0.8},
        ]
    return raw


class TestAliasMap:
    def test_alias_map_covers_the_measured_legacy_universe(self):
        accounted = set(LEGACY_KEY_TO_CANONICAL) | LEGACY_KEYS_MOVED_OFF_RESULT
        unaccounted = LEGACY_KEY_UNIVERSE - accounted
        assert not unaccounted, f"legacy keys with no canonical home: {sorted(unaccounted)}"

    def test_no_legacy_key_maps_to_two_canonical_fields(self):
        seen: dict[str, str] = {}
        for legacy, canonical in LEGACY_KEY_TO_CANONICAL.items():
            assert legacy not in seen, f"{legacy} mapped twice"
            seen[legacy] = canonical

    def test_period_aliases_are_documented(self):
        assert set(LEGACY_ALIASES["period_days"]) == {
            "period", "period_days", "orbital_period",
        }


class TestVerdictEnum:
    @pytest.mark.parametrize("legacy", sorted(LEGACY_VERDICT_TO_CANONICAL))
    def test_every_legacy_verdict_maps(self, legacy):
        assert LEGACY_VERDICT_TO_CANONICAL[legacy] in VettingVerdict

    def test_is_accepted_replicates_the_prefix_coupling(self):
        """``orchestrator.py:179,409`` accepts on
        ``startswith('Verified Planet Candidate')``; that rule is now a
        property of the enum and cannot drift."""
        accepted = [
            "Verified Planet Candidate",
            "Verified Planet Candidate (Atmospheric Occultation Detected)",
        ]
        for legacy in accepted:
            assert LEGACY_VERDICT_TO_CANONICAL[legacy].is_accepted
        for legacy in LEGACY_VERDICT_TO_CANONICAL:
            expected = legacy.startswith("Verified Planet Candidate")
            assert LEGACY_VERDICT_TO_CANONICAL[legacy].is_accepted is expected

    def test_canonical_round_trips_to_legacy_label(self):
        for legacy, canonical in LEGACY_VERDICT_TO_CANONICAL.items():
            assert canonical.legacy_label == legacy


class TestLegacyBridge:
    def test_resolves_all_period_aliases(self, dataset, store):
        res = from_legacy_result_dict(
            _legacy_full(), job_id="j1", dataset=dataset, store=store
        )
        cand = res.candidates[0]
        assert cand.period_days == 50.0
        assert cand.epoch_bjd == 120.0
        assert cand.duration_hours == pytest.approx(0.15 * 24)

    def test_path_dependent_keys_become_nullables(self, dataset):
        """VettingEngine returns 4 keys on Insufficient Data and 6 on
        success; the canonical schema always has the fields, set to None."""
        raw = _legacy_full(vetting="Insufficient Data")
        del raw["delta_chi2_u"]
        del raw["delta_chi2_v"]
        res = from_legacy_result_dict(raw, job_id="j1", dataset=dataset)
        cand = res.candidates[0]
        assert cand.vetting.delta_chi2_u is None
        assert cand.vetting.delta_chi2_v is None
        assert cand.vetting.verdict is VettingVerdict.INSUFFICIENT_DATA

    def test_sentinel_zero_becomes_none(self, dataset):
        """``physical_properties`` uses ``0.0`` for "not computable";
        the bridge must not report a zero-radius planet."""
        raw = _legacy_full()
        raw["planet_radius_earth"] = 0.0
        raw["equilibrium_temp_k"] = 0.0
        res = from_legacy_result_dict(raw, job_id="j1", dataset=dataset)
        assert res.candidates[0].physical.radius_earth is None
        assert res.candidates[0].physical.equilibrium_temp_k is None

    def test_periodogram_moves_out_of_payload(self, dataset, store):
        raw = _legacy_full()
        res = from_legacy_result_dict(raw, job_id="j1", dataset=dataset, store=store)
        cand = res.candidates[0]
        assert cand.periodogram_ref is not None
        # The ~90k-entry grid is NOT in the serialized result.
        payload = res.to_dict()
        payload_text = json.dumps(payload)
        assert "powers" not in payload_text
        grid = store.load_array(cand.periodogram_ref)
        assert grid.shape == (90_000, 2)

    def test_periodogram_warns_when_no_store(self, dataset):
        res = from_legacy_result_dict(_legacy_full(), job_id="j1", dataset=dataset)
        codes = {w.code for w in res.warnings}
        assert "PERIODOGRAM_NOT_PERSISTED" in codes

    def test_tls_outcome_is_an_enum_never_bool(self, dataset):
        res = from_legacy_result_dict(
            _legacy_full(), job_id="j1", dataset=dataset
        )
        from astraeus.core.capabilities import TlsOutcome

        assert res.candidates[0].tls.outcome is TlsOutcome.RAN_PASS
        # The legacy boolean is DERIVED from the enum, not vice versa.
        assert res.candidates[0].tls.tls_valid is True

    def test_subtraction_provenance_preserved(self, dataset):
        raw = _legacy_full()
        raw["subtraction_backend"] = "trapezoid"
        raw["subtraction_backend_available"] = False
        res = from_legacy_result_dict(raw, job_id="j1", dataset=dataset)
        assert res.candidates[0].subtraction.backend == "trapezoid"
        assert res.candidates[0].subtraction.backend_available is False

    def test_snr_floor_is_stated(self, dataset):
        res = from_legacy_result_dict(
            _legacy_full(), job_id="j1", dataset=dataset, snr_floor=7.1, max_signals=5
        )
        assert res.pipeline_summary.snr_floor == 7.1
        assert res.pipeline_summary.max_signals == 5

    def test_numpy_scalar_types_are_absorbed(self, dataset):
        raw = _legacy_full()
        raw["tls_sde"] = np.float64(12.0)
        raw["period"] = np.float64(50.0)
        res = from_legacy_result_dict(raw, job_id="j1", dataset=dataset)
        assert isinstance(res.candidates[0].tls.sde, float)
        assert res.candidates[0].period_days == 50.0


class TestAnalysisResultContract:
    def _make(self, dataset, store=None, **kw):
        return from_legacy_result_dict(
            _legacy_full(), job_id="j1", dataset=dataset, store=store, **kw
        )

    def test_schema_version_from_day_one(self, dataset):
        res = self._make(dataset)
        assert res.schema_version == ANALYSIS_RESULT_SCHEMA_VERSION

    def test_inference_is_explicitly_null(self, dataset):
        """PRD §6.3: v1 has no inference section in the unified path."""
        res = self._make(dataset)
        assert res.inference is None
        assert "inference" in res.model_dump()

    def test_completed_result_may_not_carry_an_error(self, dataset):
        from pydantic import ValidationError

        from astraeus.contracts.analysis_result import AnalysisResult

        with pytest.raises(ValidationError):
            AnalysisResult(
                result_id="r1", job_id="j1", target_id="t", dataset_id="ds",
                status=JobStatus.COMPLETED, error="oops",
            )

    def test_failed_result_requires_a_reason(self, dataset):
        from pydantic import ValidationError

        from astraeus.contracts.analysis_result import AnalysisResult

        with pytest.raises(ValidationError):
            AnalysisResult(
                result_id="r1", job_id="j1", target_id="t", dataset_id="ds",
                status=JobStatus.FAILED,
            )

    def test_json_is_round_trippable(self, dataset, store):
        res = self._make(dataset, store=store)
        text = res.model_dump_json()
        back = type(res).model_validate_json(text)
        assert back.result_id == res.result_id
        assert back.n_candidates == res.n_candidates

    def test_legacy_dual_emission(self, dataset, store):
        """PRD §6.4: emit BOTH key sets for one release."""
        res = self._make(dataset, store=store, snr_floor=7.1, max_signals=5)
        legacy = res.to_legacy_dict()
        assert legacy["schema_version"] == 1
        assert legacy["candidate_found"] is True
        assert legacy["tls_valid"] is True
        assert legacy["snr_floor"] == 7.1
        assert len(legacy["candidates"]) == 1
        cand_legacy = legacy["candidates"][0]
        assert cand_legacy["period"] == 50.0
        assert cand_legacy["period_days"] == 50.0
        assert cand_legacy["orbital_period"] == 50.0

    def test_stage_enum_names_match_the_real_pipeline(self):
        """PRD §5.1: SEARCHING and VETTING, not DETECTING/CROSS_VALIDATING."""
        names = {stage.value for stage in JobStage}
        assert "SEARCHING" in names
        assert "VETTING" in names
        assert "DETECTING" not in names
        assert "CROSS_VALIDATING" not in names
        assert JobStage.COMPLETED.is_terminal
        assert not JobStage.SEARCHING.is_terminal
