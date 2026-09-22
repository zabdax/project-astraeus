"""The dedicated worker subprocess (P1-F).

PRD v4.1 §5.1 / §16 decision register.  The previous mechanism --
``multiprocessing.Process(target=_subprocess_search_worker, daemon=True)``
with a ``multiprocessing.Queue`` for events -- **cannot** be flag-flipped
to the target architecture: ``Process.__init__`` has no ``start_new_session``
parameter (verified), and a daemon process cannot create the ``Pool`` that
TLS needs (P05-A's measured nested-pool constraint).  This module is the
*replacement*, not an enhancement: a standalone process launched with
``subprocess.Popen(start_new_session=True)`` that runs the real pipeline
and emits newline-delimited JSON events on stdout.

Channel discipline (why stdout is sacred here):

* **stdout** is the JSONL event channel, and nothing else may write to it.
  The engine's logger ships a ``_StdoutHandler``
  (``core/capabilities.py:66``) precisely because the *old* consumer was
  the orchestrator's stdout event channel; inside this worker that handler
  is rebound to the job's stderr capture file so a scientific warning can
  never corrupt the event stream.
* **stderr** is captured to a file linked to ``job_id`` (PRD §5.1:
  "stdout/stderr capture linked to job_id -- today: inherited,
  unlinked").
* **results and provenance** are written by the worker itself -- to the
  content-addressed artifact store and the durable SQLite store -- *before*
  the ``done`` event is emitted.  So a supervisor that dies mid-flight
  still finds a complete record: the Phase 1 gate is "a real-data job
  survives a server restart".

The engine is wrapped, never rewritten (PRD §16): this process calls
``run_multi_planet_search`` with the P1-F ``on_event`` hook.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from astraeus.contracts.analysis_result import JobStage, JobStatus
from astraeus.contracts.dataset import ArtifactRef, ArtifactStore, Dataset
from astraeus.contracts.provenance import EffectiveConfig, capture_provenance
from astraeus.contracts.analysis_result import from_legacy_run
from astraeus.jobs.events import emit_event
from astraeus.jobs.store import JobStore

__all__ = [
    "WorkerSpec",
    "run_worker",
    "configure_worker_logging",
    "main",
]

#: Exit codes distinguish "the search ran to completion" from "the worker
#: itself failed", so the supervisor can tell a scientific negative apart
#: from a broken pipeline.
EXIT_OK = 0
EXIT_ERROR = 1


class WorkerSpec:
    """The job description the supervisor hands the worker (JSON on disk).

    Carrying the spec as a file (not argv) keeps secrets and large
    payloads out of the process table, and makes a hung job's intent
    inspectable after the fact.
    """

    def __init__(
        self,
        *,
        job_id: str,
        target_name: str,
        mission: str | None = None,
        resolved_target_id: str | None = None,
        dataset_ref: dict | None = None,
        artifact_root: str | None = None,
        db_path: str | None = None,
        max_signals: int = 5,
        snr_floor: float = 7.1,
        config: dict | None = None,
        fetch_real_data: bool = False,
        tls_threads: int | None = None,
    ) -> None:
        self.job_id = job_id
        self.target_name = target_name
        self.mission = mission
        self.resolved_target_id = resolved_target_id
        self.dataset_ref = dataset_ref
        self.artifact_root = artifact_root
        self.db_path = db_path
        self.max_signals = max_signals
        self.snr_floor = snr_floor
        self.config = dict(config or {})
        self.fetch_real_data = fetch_real_data
        # P4-G unlock: forwarded to the TLS gate (None = resolver default,
        # i.e. serial unless ASTRAEUS_TLS_THREADS opts in).
        self.tls_threads = tls_threads

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "target_name": self.target_name,
            "mission": self.mission,
            "resolved_target_id": self.resolved_target_id,
            "dataset_ref": self.dataset_ref,
            "artifact_root": self.artifact_root,
            "db_path": self.db_path,
            "max_signals": self.max_signals,
            "snr_floor": self.snr_floor,
            "config": self.config,
            "fetch_real_data": self.fetch_real_data,
            "tls_threads": self.tls_threads,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "WorkerSpec":
        return cls(**payload)

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return path

    @classmethod
    def load(cls, path: Path | str) -> "WorkerSpec":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Logging: keep stdout pure
# ---------------------------------------------------------------------------


def configure_worker_logging(stderr_path: Path | str | None) -> None:
    """Rebind the ``astraeus`` logger's stdout handler to the job's capture file.

    ``core/capabilities.py`` installs a ``_StdoutHandler`` that resolves
    ``sys.stdout`` at emit time.  In this worker, ``sys.stdout`` IS the
    JSONL event channel, so an un-rebound handler would inject free text
    into a stream a parser expects to be line-delimited JSON.  The TLS
    infra-failure sentinel (``[TLS-INFRA-ERROR]``) is preserved -- it now
    lands in the job's linked stderr capture instead of an anonymous pipe.
    """
    root = logging.getLogger("astraeus")
    from astraeus.core.capabilities import _StdoutHandler

    for handler in list(root.handlers):
        if isinstance(handler, _StdoutHandler):
            root.removeHandler(handler)
    if stderr_path is not None:
        path = Path(stderr_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


def _stage(stage: JobStage) -> str:
    return stage.value


def _load_or_fetch_dataset(spec: WorkerSpec, store: ArtifactStore) -> Dataset:
    """Resolve the dataset: from a stored reference, or by fetching real data.

    P1-G's deliverable is the second branch -- real data has never crossed
    the async subprocess boundary before (PRD §18 item 1).  The fetch lives
    in :mod:`astraeus.jobs.ingestion_bridge` so the engine's ingestion
    stack is imported lazily and only on this path.
    """
    if spec.dataset_ref is not None:
        ref = ArtifactRef.model_validate(spec.dataset_ref)
        return store.load_dataset(ref)
    if not spec.fetch_real_data:
        raise ValueError(
            "worker spec has neither a dataset_ref nor fetch_real_data; "
            "nothing to analyse"
        )
    from astraeus.jobs.ingestion_bridge import fetch_real_dataset

    dataset = fetch_real_dataset(
        spec.target_name, mission=spec.mission or "Kepler", store=store
    )
    return dataset


def run_worker(spec: WorkerSpec, *, stdout: Any = None) -> int:
    """Execute one job.  Returns a process exit code.

    Every failure path emits a structured ``error`` event with a
    ``kind`` before returning -- the PRD §21 Phase 1 gate: "a TLS
    infrastructure failure yields FAILED + reason, not DONE / 0
    candidates".
    """
    from astraeus.core.capabilities import BackendId, BackendUnavailable

    # ``out`` is the event channel and is resolved *before* any stdout
    # redirection below: emit() must keep writing to the real stream even
    # while the engine's own print() output is being redirected.
    out = stdout if stdout is not None else sys.stdout
    store = ArtifactStore(spec.artifact_root)
    db: JobStore | None = (
        JobStore(spec.db_path) if spec.db_path else None
    )
    stderr_path = None
    if db is not None:
        record = db.require_job(spec.job_id)
        stderr_path = record.stderr_path
    configure_worker_logging(stderr_path)

    def emit(event_type: str, **payload: Any) -> None:
        emit_event(event_type, stream=out, **payload)
        # The worker is the authoritative writer of the durable event
        # trail, not the supervisor's stdout parser: an in-process run has
        # no such parser at all, and a supervisor that dies mid-flight
        # must still find the full history linked to the job (PRD §5.1).
        if db is not None:
            try:
                db.append_event(
                    spec.job_id,
                    event_type,
                    stage=payload.get("stage"),
                    payload=payload,
                )
            except Exception:  # pragma: no cover - telemetry must never break a run
                pass

    emit("running", job_id=spec.job_id, target_name=spec.target_name)

    try:
        emit("stage", stage=_stage(JobStage.FETCHING), status="ok")
        dataset = _load_or_fetch_dataset(spec, store)
        emit("artifact", kind="dataset", ref=store.save_dataset(dataset).model_dump())
        if db is not None:
            db.update_job(
                spec.job_id,
                dataset_id=dataset.dataset_id,
                dataset_ref=store.save_dataset(dataset),
            )

        # --- provenance: captured BEFORE the search so a crash still -----
        # leaves a record of what was about to run and on which data.
        emit("stage", stage=_stage(JobStage.PREPROCESSING), status="ok")
        effective = EffectiveConfig(
            snr_floor=spec.snr_floor,
            max_signals=spec.max_signals,
            **{
                k: v
                for k, v in spec.config.items()
                if k in EffectiveConfig.model_fields and k not in ("snr_floor", "max_signals")
            },
        )
        provenance = capture_provenance(
            dataset, effective_config=effective, started_at_iso=_now_iso()
        )
        provenance_ref = provenance.save(store)
        emit("artifact", kind="provenance", ref=provenance_ref.model_dump())
        if db is not None:
            db.attach_provenance(spec.job_id, provenance)

        emit("stage", stage=_stage(JobStage.SEARCHING), status="running")
        from astraeus.core.orchestrator import run_multi_planet_search

        raw_lightcurve = {
            "time": dataset.time,
            "flux": dataset.flux,
            "flux_err": dataset.flux_err if dataset.flux_err is not None else [],
            "target_name": spec.target_name,
            "data_source": f"artifact:{dataset.dataset_id}",
            "metadata": {},
        }
        # The orchestrator reports *measured* progress; remember the last
        # iteration count so the run-level summary is honest rather than
        # inferred from the candidate list (PRD §5.1, §18).  P2-A: also
        # accumulate every examined peak's TLS outcome (accepted or
        # rejected) so the run-level TlsSummary states truthfully whether
        # the gate ran -- rejected peaks never reach the candidate list.
        run_state: dict[str, Any] = {"iteration": 0, "examined_tls": []}

        def _on_event(event_type: str, **payload: Any) -> None:
            if event_type == "iteration" and payload.get("iteration"):
                run_state["iteration"] = payload["iteration"]
            if event_type == "progress" and "tls_outcome" in payload:
                run_state["examined_tls"].append(payload["tls_outcome"])
            # The worker owns the lifecycle vocabulary on the wire: its own
            # "running"/"done" events carry the job id, result ids and
            # dataset id, which the loop cannot know.  Forwarding the
            # loop's copies would duplicate them on the channel and in the
            # store.  The loop's contribution is *measured* progress --
            # iteration, candidate and warning -- which is all we forward.
            if event_type in ("running", "done"):
                return
            emit(event_type, **payload)

        # Channel discipline: the engine's progress output is emitted with
        # print(), which writes to sys.stdout -- the very stream a parser
        # expects to be line-delimited JSON.  Rebinding the *logger* is not
        # enough (print() bypasses logging entirely).  For the duration of
        # the pipeline call, redirect sys.stdout to the job's capture file
        # so a scientific warning or progress line can never corrupt the
        # event channel.  emit() still writes to the real stream captured
        # above, so events are unaffected (PRD §5.1 stdout discipline).
        with _stdout_capture(stderr_path) as capture:
            candidates = run_multi_planet_search(
                raw_lightcurve,
                max_signals=spec.max_signals,
                snr_floor=spec.snr_floor,
                on_event=_on_event,
                tls_threads=spec.tls_threads,
            )
        emit("stage", stage=_stage(JobStage.SEARCHING), status="ok")

        # --- ONE result for the whole run (PRD §5 / §6): 0..N candidates --
        # The legacy machinery yields one dict per accepted candidate and
        # nothing at all when the search comes up empty.  The run-level
        # bridge always produces exactly one AnalysisResult, so "DONE / 0
        # candidates" is a COMPLETED run with an empty list -- which is what
        # makes it distinguishable from a broken pipeline (PRD §21).
        emit("stage", stage=_stage(JobStage.VETTING), status="ok")
        result = from_legacy_run(
            candidates,
            job_id=spec.job_id,
            target_id=spec.resolved_target_id or spec.target_name,
            dataset=dataset,
            store=store,
            max_signals=spec.max_signals,
            snr_floor=spec.snr_floor,
            n_iterations=run_state["iteration"] or None,
            examined_tls_outcomes=run_state["examined_tls"] or None,
            status=JobStatus.COMPLETED,
        )
        provenance = provenance.model_copy(
            update={"result_id": result.result_id}
        )
        ref = store.save_json(result.to_dict(), kind="result")
        emit("artifact", kind="result", ref=ref.model_dump())
        if db is not None:
            db.attach_artifact(spec.job_id, "result", ref)
            db.attach_result(spec.job_id, result)

        emit(
            "stage",
            stage=_stage(JobStage.COMPLETED),
            status="ok",
        )
        emit(
            "done",
            n_candidates=result.n_candidates,
            result_ids=[result.result_id],
            dataset_id=dataset.dataset_id,
        )
        return EXIT_OK

    except BackendUnavailable as exc:
        # The fail-closed gate (PRD §4.2): a missing required backend is a
        # FAILED run with a named reason, never a silent degradation.
        emit(
            "error",
            kind="backend_unavailable",
            stage=_stage(JobStage.SEARCHING),
            message=str(exc),
            backend=str(getattr(exc, "backend", "")),
        )
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - the worker must always report
        kind = "tls_infrastructure" if "TLS" in type(exc).__name__ else "pipeline"
        emit(
            "error",
            kind=kind,
            message=f"{type(exc).__name__}: {exc}",
        )
        return EXIT_ERROR
    finally:
        if db is not None:
            db.close()


def _now_iso() -> str:
    from astraeus.contracts.dataset import utc_now_iso

    return utc_now_iso()


@contextlib.contextmanager
def _stdout_capture(stderr_path: str | None):
    """Redirect ``sys.stdout`` to the job's capture file for the duration of
    a pipeline call.

    The engine reports progress with ``print()`` rather than the logger, and
    in this worker ``sys.stdout`` *is* the JSONL event channel.  Sending
    those lines to the capture file keeps them inspectable (linked to the
    job, PRD §5.1) and keeps the event channel parseable.  If the capture
    path is unknown, fall back to devnull so the channel is still protected.
    """
    handle = None
    if stderr_path is not None:
        try:
            path = Path(stderr_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(path, "a", encoding="utf-8", errors="replace")
        except OSError:
            handle = None
    if handle is None:
        handle = open(os.devnull, "w", encoding="utf-8", errors="replace")
    try:
        with contextlib.redirect_stdout(handle):
            yield handle
    finally:
        try:
            handle.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# CLI entry:  python -m astraeus.jobs.worker --spec path/to/spec.json
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="astraeus.jobs.worker",
        description="Run one ASTRAEUS search job as a dedicated subprocess.",
    )
    parser.add_argument("--spec", required=True, help="path to the WorkerSpec JSON file")
    args = parser.parse_args(argv)

    spec = WorkerSpec.load(args.spec)
    return run_worker(spec)


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
