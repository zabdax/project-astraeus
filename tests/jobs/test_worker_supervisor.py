"""Tests for the worker process and the async supervisor (P1-F/G).

These are the Phase 1 exit-gate tests (PRD v4.1 §21):

* a real job survives a server restart;
* cancel kills the whole process tree within the grace period;
* a hard timeout yields ``FAILED`` + ``error_kind=timeout`` rather than a
  hung run;
* an infrastructure failure yields ``FAILED`` + reason, never ``DONE / 0
  candidates``.

The real pipeline is exercised -- the engine is wrapped, not stubbed.  TLS
has a fixed period-grid cost (P05-A: ~150 s serial on real Kepler data,
~9-60 s on these small test curves), so the real-pipeline tests carry the
``smoke`` marker (sub-minute CI gate) and the long arms are marked
``slow``.
"""

from __future__ import annotations

import asyncio
import io
import json

import numpy as np
import pytest

from astraeus.contracts.analysis_result import JobStage, JobStatus
from astraeus.contracts.dataset import ArtifactStore, Dataset, Mission, TargetRef, TimeUnit
from astraeus.jobs.events import (
    ERROR_KINDS,
    EVENT_TYPES,
    WorkerEvent,
    emit_event,
    parse_event_line,
)
from astraeus.jobs.store import JobRecord, JobStore
from astraeus.jobs.supervisor import JobSupervisor
from astraeus.jobs.worker import EXIT_ERROR, EXIT_OK, WorkerSpec, run_worker

pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# Fixtures: small synthetic light curves (test infrastructure, not data)
# ---------------------------------------------------------------------------


def _noise_curve(n: int = 200, days: float = 10.0, seed: int = 11) -> Dataset:
    rng = np.random.default_rng(seed)
    time = np.linspace(0.0, days, n)
    flux = 1.0 + rng.normal(0, 0.001, n)
    return Dataset.from_arrays(
        time, flux, np.full(n, 0.001),
        target=TargetRef(name="TINY-NOISE", mission=Mission.UNKNOWN),
        time_unit=TimeUnit.BJD,
        source="synthetic-test",
    )


def _injected_curve(seed: int = 42, days: float = 200.0) -> Dataset:
    """A clear single transit -- slow enough to make cancel/timeout tests
    deterministic (the job will not finish within their windows)."""
    rng = np.random.default_rng(seed)
    time = np.arange(0.0, days, 0.0204)
    period, epoch, dur, depth = 12.345, 5.0, 0.12, 0.004
    flux = np.ones_like(time)
    ph = np.mod(time - epoch, period)
    flux[(ph < dur / 2) | (ph > period - dur / 2)] -= depth
    flux += rng.normal(0, 0.0005, time.size)
    return Dataset.from_arrays(
        time, flux, np.full(time.size, 0.0005),
        target=TargetRef(name="TINY-INJECTED", mission=Mission.UNKNOWN),
        time_unit=TimeUnit.BJD,
        source="synthetic-test",
    )


@pytest.fixture
def artifact_store(tmp_path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def job_store(tmp_path) -> JobStore:
    return JobStore(tmp_path / "astraeus.db")


# ---------------------------------------------------------------------------
# Event vocabulary (instant)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestEventVocabulary:
    def test_legacy_types_are_preserved(self):
        from astraeus.jobs.events import LEGACY_EVENT_TYPES

        assert LEGACY_EVENT_TYPES == {"running", "iteration", "candidate", "done", "error"}

    def test_new_types_are_present(self):
        assert {"stage", "progress", "warning", "artifact", "system"} <= EVENT_TYPES

    def test_emit_and_parse_roundtrip(self):
        buf = io.StringIO()
        emit_event("iteration", iteration=3, max_iterations=8, stream=buf)
        event = parse_event_line(buf.getvalue())
        assert event is not None
        assert event.type == "iteration"
        assert event.payload["iteration"] == 3

    def test_emit_is_newline_delimited_and_flushed(self):
        buf = io.StringIO()
        emit_event("running", stream=buf)
        emit_event("done", stream=buf)
        lines = buf.getvalue().splitlines()
        assert len(lines) == 2
        for line in lines:
            assert json.loads(line)["type"] in ("running", "done")

    def test_blank_line_yields_none(self):
        assert parse_event_line("   \n") is None

    def test_malformed_line_raises(self):
        with pytest.raises(Exception):
            parse_event_line("not json at all")

    def test_unknown_type_is_rejected(self):
        with pytest.raises(ValueError, match="unknown worker event type"):
            WorkerEvent("not_a_real_type")

    def test_error_kinds_cover_the_gate_requirements(self):
        # The Phase 1 gate needs a machine-readable reason for the TLS
        # infra failure specifically (PRD §4.3 / §21).
        assert "tls_infrastructure" in ERROR_KINDS
        assert "backend_unavailable" in ERROR_KINDS
        assert "timeout" in ERROR_KINDS


# ---------------------------------------------------------------------------
# The worker, run in-process (fast happy path + error classification)
# ---------------------------------------------------------------------------


class TestWorkerInProcess:
    def test_runs_and_records_everything(self, job_store, artifact_store):
        dataset = _noise_curve()
        artifact_store.save_dataset(dataset)
        job_store.create_job(
            JobRecord(job_id="w-1", target_name="TINY-NOISE", max_iterations=1)
        )
        spec = WorkerSpec(
            job_id="w-1",
            target_name="TINY-NOISE",
            dataset_ref=artifact_store.save_dataset(dataset).model_dump(),
            artifact_root=str(artifact_store.root),
            db_path=str(job_store.db_path),
            max_signals=1,
            snr_floor=7.0,
        )
        buf = io.StringIO()
        code = run_worker(spec, stdout=buf)
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        types = [json.loads(l)["type"] for l in lines]

        assert code == EXIT_OK
        assert types[0] == "running"
        assert types[-1] == "done"
        assert "stage" in types

        # The result and provenance were written by the worker itself.
        record = job_store.require_job("w-1")
        assert record.status is JobStatus.COMPLETED
        assert record.result_id is not None
        assert job_store.get_result("w-1") is not None
        assert job_store.get_provenance("w-1") is not None
        # Events are durable and linked to the job.
        assert len(job_store.list_events("w-1")) >= 3

    def test_survives_a_restart(self, tmp_path, artifact_store):
        """The Phase 1 gate: the record outlives the process."""
        dataset = _noise_curve()
        db_path = tmp_path / "astraeus.db"
        with JobStore(db_path) as store:
            store.create_job(JobRecord(job_id="w-2", target_name="TINY-NOISE"))
            spec = WorkerSpec(
                job_id="w-2",
                target_name="TINY-NOISE",
                dataset_ref=artifact_store.save_dataset(dataset).model_dump(),
                artifact_root=str(artifact_store.root),
                db_path=str(db_path),
                max_signals=1,
                snr_floor=7.0,
            )
            run_worker(spec, stdout=io.StringIO())
        # The worker "died"; a fresh process reopens the database.
        with JobStore(db_path) as reopened:
            assert reopened.require_job("w-2").status is JobStatus.COMPLETED
            assert reopened.get_result("w-2") is not None

    def test_missing_dataset_is_a_structured_error(self, job_store, artifact_store):
        job_store.create_job(JobRecord(job_id="w-3", target_name="NONE"))
        spec = WorkerSpec(
            job_id="w-3",
            target_name="NONE",
            artifact_root=str(artifact_store.root),
            db_path=str(job_store.db_path),
            max_signals=1,
        )
        buf = io.StringIO()
        assert run_worker(spec, stdout=buf) == EXIT_ERROR
        events = [json.loads(l) for l in buf.getvalue().splitlines() if l.strip()]
        assert events[-1]["type"] == "error"
        assert events[-1]["kind"] in ERROR_KINDS


# ---------------------------------------------------------------------------
# The supervisor: real subprocess, process-group kill, hard timeout
# ---------------------------------------------------------------------------


class TestSupervisor:
    @pytest.mark.asyncio
    async def test_subprocess_job_completes(self, job_store, artifact_store):
        dataset = _noise_curve()
        ref = artifact_store.save_dataset(dataset)
        supervisor = JobSupervisor(job_store, artifact_root=artifact_store.root)
        job_id = await supervisor.submit(
            JobRecord(job_id="s-1", target_name="TINY-NOISE", max_iterations=1),
            dataset_ref=ref,
            config={"snr_floor": 7.0, "max_signals": 1},
        )
        record = await supervisor.wait(job_id)
        assert record.status is JobStatus.COMPLETED
        assert job_store.get_result(job_id) is not None
        # Measured progress reached the store, not a fake bar.
        events = job_store.list_events(job_id)
        assert any(e.type == "iteration" for e in events)
        await supervisor.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_within_grace_period(self, job_store, artifact_store):
        """The Phase 1 gate: cancel kills the process tree."""
        dataset = _injected_curve()  # ~60s of work; cancel must land in ~7s
        ref = artifact_store.save_dataset(dataset)
        supervisor = JobSupervisor(
            job_store, artifact_root=artifact_store.root, grace_seconds=5.0
        )
        job_id = await supervisor.submit(
            JobRecord(job_id="s-2", target_name="TINY-INJECTED", max_iterations=2),
            dataset_ref=ref,
            config={"snr_floor": 7.0, "max_signals": 2},
        )
        await asyncio.sleep(2.0)
        record = await asyncio.wait_for(supervisor.cancel(job_id), timeout=30.0)
        assert record.status is JobStatus.CANCELLED
        assert job_store.require_job(job_id).error_kind == "cancelled"
        # The process is actually gone.
        handle = supervisor._handles.get(job_id)
        if handle is not None:
            assert handle.process.poll() is not None
        await supervisor.shutdown()

    @pytest.mark.asyncio
    async def test_hard_timeout_marks_failed(self, job_store, artifact_store):
        dataset = _injected_curve()
        ref = artifact_store.save_dataset(dataset)
        supervisor = JobSupervisor(
            job_store,
            artifact_root=artifact_store.root,
            timeout_seconds=1.0,
            grace_seconds=5.0,
        )
        job_id = await supervisor.submit(
            JobRecord(job_id="s-3", target_name="TINY-INJECTED", max_iterations=2),
            dataset_ref=ref,
            config={"snr_floor": 7.0, "max_signals": 2},
        )
        record = await asyncio.wait_for(supervisor.wait(job_id), timeout=60.0)
        assert record.status is JobStatus.FAILED
        # A hung TLS call can never run forever again (PRD §13.1).
        assert record.error_kind == "timeout"
        await supervisor.shutdown()

    @pytest.mark.asyncio
    async def test_events_stream_replays_then_lives(self, job_store, artifact_store):
        dataset = _noise_curve()
        ref = artifact_store.save_dataset(dataset)
        supervisor = JobSupervisor(job_store, artifact_root=artifact_store.root)
        job_id = await supervisor.submit(
            JobRecord(job_id="s-4", target_name="TINY-NOISE", max_iterations=1),
            dataset_ref=ref,
            config={"snr_floor": 7.0, "max_signals": 1},
        )
        await supervisor.wait(job_id)
        streamed = []
        async for event in supervisor.events(job_id):
            streamed.append(event)
        assert any(e["type"] == "done" for e in streamed)
        await supervisor.shutdown()
