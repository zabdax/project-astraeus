"""Tests for the durable job store (P1-E).

PRD v4.1 §5.1 / §21 Phase 1 gate: "a real-data job survives a server
restart".  These tests pin that property directly: write a job, drop the
in-memory state entirely, reopen the database, and require the record.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from astraeus.contracts.analysis_result import JobStage, JobStatus
from astraeus.contracts.dataset import ArtifactStore, Dataset, TargetRef, TimeUnit, Mission
from astraeus.contracts.analysis_result import from_legacy_result_dict
from astraeus.jobs.store import DB_SCHEMA_VERSION, JobRecord, JobStore


@pytest.fixture
def store(tmp_path) -> JobStore:
    return JobStore(tmp_path / "astraeus.db")


@pytest.fixture
def dataset() -> Dataset:
    rng = np.random.default_rng(0)
    time = np.sort(rng.uniform(100.0, 1100.0, 300))
    flux = 1.0 + rng.normal(0, 5e-4, 300)
    return Dataset.from_arrays(
        time, flux, np.full(300, 5e-4),
        target=TargetRef(name="Kepler-90", mission=Mission.KEPLER,
                         resolved_id="KIC-11442793"),
        time_unit=TimeUnit.BJD,
    )


def _record(job_id: str = "job-1") -> JobRecord:
    return JobRecord(
        job_id=job_id,
        target_name="Kepler-90",
        resolved_target_id="KIC-11442793",
        mission="Kepler",
        max_iterations=3,
        config={"snr_floor": 7.1, "max_signals": 3},
    )


class TestStoreBasics:
    def test_wal_mode_is_enabled(self, store):
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_schema_version_is_recorded(self, store):
        assert store.schema_version == DB_SCHEMA_VERSION

    def test_migrations_are_idempotent(self, tmp_path):
        path = tmp_path / "astraeus.db"
        JobStore(path).close()
        reopened = JobStore(path)
        assert reopened.schema_version == DB_SCHEMA_VERSION
        reopened.close()

    def test_create_and_get(self, store):
        store.create_job(_record())
        back = store.require_job("job-1")
        assert back.target_name == "Kepler-90"
        assert back.status is JobStatus.QUEUED
        assert back.config == {"snr_floor": 7.1, "max_signals": 3}

    def test_missing_job_raises_keyerror(self, store):
        with pytest.raises(KeyError):
            store.require_job("nope")

    def test_list_jobs_filters_by_status(self, store):
        store.create_job(_record("a"))
        store.create_job(_record("b"))
        store.transition("b", JobStatus.RUNNING)
        assert {r.job_id for r in store.list_jobs(status=JobStatus.QUEUED)} == {"a"}
        assert {r.job_id for r in store.list_jobs(status=JobStatus.RUNNING)} == {"b"}

    def test_update_rejects_unknown_fields(self, store):
        store.create_job(_record())
        with pytest.raises(ValueError, match="unknown"):
            store.update_job("job-1", not_a_column=1)


class TestTransitions:
    def test_running_sets_started_at(self, store):
        store.create_job(_record())
        rec = store.transition("job-1", JobStatus.RUNNING, JobStage.FETCHING)
        assert rec.started_at is not None
        assert rec.stage is JobStage.FETCHING

    def test_terminal_sets_finished_at(self, store):
        store.create_job(_record())
        store.transition("job-1", JobStatus.RUNNING)
        rec = store.transition("job-1", JobStatus.COMPLETED, JobStage.COMPLETED)
        assert rec.finished_at is not None
        assert rec.is_terminal()

    def test_failed_carries_reason_and_kind(self, store):
        store.create_job(_record())
        rec = store.transition(
            "job-1", JobStatus.FAILED, JobStage.FAILED,
            error="TLS gate could not execute", error_kind="tls_infrastructure",
        )
        assert rec.error == "TLS gate could not execute"
        assert rec.error_kind == "tls_infrastructure"

    def test_cancel(self, store):
        store.create_job(_record())
        rec = store.cancel("job-1")
        assert rec.status is JobStatus.CANCELLED
        assert rec.error_kind == "cancelled"


class TestSurvivesRestart:
    """The Phase 1 exit gate, tested directly."""

    def test_job_row_survives_reopen(self, tmp_path):
        path = tmp_path / "astraeus.db"
        with JobStore(path) as store:
            store.create_job(_record())
            store.transition("job-1", JobStatus.RUNNING, JobStage.SEARCHING)
            store.append_event("job-1", "iteration", payload={"iteration": 2})
        # Process "dies": a brand-new connection, no cached state.
        with JobStore(path) as reopened:
            rec = reopened.require_job("job-1")
            assert rec.status is JobStatus.RUNNING
            assert rec.stage is JobStage.SEARCHING
            assert len(reopened.list_events("job-1")) == 1

    def test_events_survive_and_are_ordered(self, tmp_path):
        path = tmp_path / "astraeus.db"
        with JobStore(path) as store:
            store.create_job(_record())
            for i in range(5):
                store.append_event("job-1", "iteration", payload={"iteration": i})
        with JobStore(path) as store:
            events = store.list_events("job-1")
            assert [e.seq for e in events] == list(range(1, 6))
            assert [e.payload["iteration"] for e in events] == list(range(5))


class TestReclaimStale:
    def test_running_rows_are_failed_not_forgotten(self, store):
        store.create_job(_record())
        store.transition("job-1", JobStatus.RUNNING)
        reclaimed = store.reclaim_stale()
        assert len(reclaimed) == 1
        rec = store.require_job("job-1")
        assert rec.status is JobStatus.FAILED
        assert rec.error_kind == "stale_recovery"
        # The recovery itself is an event, so the reason is auditable.
        assert store.list_events("job-1")[-1].type == "system"

    def test_completed_rows_are_not_touched(self, store):
        store.create_job(_record())
        store.transition("job-1", JobStatus.COMPLETED, JobStage.COMPLETED)
        assert store.reclaim_stale() == []


class TestResultsAndProvenance:
    def test_attach_and_get_result(self, store, dataset, tmp_path):
        artifact_store = ArtifactStore(tmp_path / "artifacts")
        raw = {
            "candidate_found": True, "period_days": 50.0, "period": 50.0,
            "orbital_period": 50.0, "depth": 0.0005, "transit_depth": 0.0005,
            "duration": 0.15, "t0": 120.0, "t0_bjd": 120.0, "snr": 15.0,
            "confidence_score": 8.0, "vetting_status": "Verified Planet Candidate",
            "vetting_confidence": 0.9, "u_shape_chi2": 10.0, "v_shape_chi2": 30.0,
            "tls_outcome": "ran_pass", "tls_valid": True,
            "backends_available": {"batman": True, "wotan": True, "tls": True},
        }
        store.create_job(_record())
        result = from_legacy_result_dict(
            raw, job_id="job-1", dataset=dataset, store=artifact_store
        )
        store.attach_result("job-1", result)
        back = store.get_result("job-1")
        assert back is not None
        assert back.result_id == result.result_id
        rec = store.require_job("job-1")
        assert rec.status is JobStatus.COMPLETED

    def test_provenance_roundtrip(self, store, dataset):
        from astraeus.contracts.provenance import capture_provenance, EffectiveConfig

        store.create_job(_record())
        prov = capture_provenance(
            dataset, effective_config=EffectiveConfig(snr_floor=7.1)
        )
        store.attach_provenance("job-1", prov)
        back = store.get_provenance("job-1")
        assert back is not None
        assert back.dataset_id == dataset.dataset_id
        assert back.effective_config.snr_floor == 7.1

    def test_artifacts_are_listed(self, store, dataset, tmp_path):
        artifact_store = ArtifactStore(tmp_path / "artifacts")
        store.create_job(_record())
        ref = artifact_store.save_dataset(dataset)
        store.attach_artifact("job-1", "dataset", ref)
        artifacts = store.list_artifacts("job-1")
        assert artifacts[0][0] == "dataset"
        assert artifacts[0][1].checksum == dataset.content_hash
