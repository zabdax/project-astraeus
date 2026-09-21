"""Durable job persistence (P1-E).

PRD v4.1 §5.1 / §13.1 / decision register.  Today ``JOB_REGISTRY`` is an
in-memory dict (``orchestrator.py:371``): jobs are lost on restart, the
app ships a manual **"Clear Stale Job"** button because stale rows cannot
be distinguished from live ones, no timeout exists, and stdout/stderr are
inherited and unlinked to ``job_id``.

This module is the durable replacement: a SQLite database in WAL mode
holding entity metadata and job state (PRD §8.3 -- the database holds
``artifact_ref`` + dtype/shape, **never arrays**), plus the event stream
the worker emits (P1-F) and the results/provenance records the contracts
produce.

Scope discipline (PRD §16 decision register): SQLite + WAL now, Postgres
only when scale actually requires it.  The arq/Redis migration trigger is
recorded in PRD §5.1: the dispatcher changes, the engine does not.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from pydantic import BaseModel, ConfigDict, Field

from astraeus.contracts.analysis_result import (
    ANALYSIS_RESULT_SCHEMA_VERSION,
    AnalysisResult,
    JobStage,
    JobStatus,
    StageOutcome,
)
from astraeus.contracts.dataset import ArtifactRef, utc_now_iso
from astraeus.core.paths import artifact_path
from astraeus.contracts.provenance import PROVENANCE_SCHEMA_VERSION, Provenance

__all__ = [
    "JobRecord",
    "JobEvent",
    "JobStore",
    "DB_SCHEMA_VERSION",
    "DEFAULT_DB_PATH",
]

#: Bumped when the on-disk schema changes; migrations are applied in
#: order and tracked via ``PRAGMA user_version``.
DB_SCHEMA_VERSION = 1

DEFAULT_OWNER = "single-user"

DEFAULT_DB_PATH = "astraeus.db"

#: Jobs in these states are live; anything else found at startup was
#: orphaned by a crash and is reclaimed (PRD §5.1 "stale-job recovery").
_LIVE_STATES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id              TEXT PRIMARY KEY,
        owner_id            TEXT NOT NULL DEFAULT 'single-user',
        target_name         TEXT NOT NULL,
        resolved_target_id  TEXT,
        mission             TEXT,
        dataset_id          TEXT,
        dataset_ref         TEXT,
        status              TEXT NOT NULL DEFAULT 'QUEUED',
        stage               TEXT NOT NULL DEFAULT 'QUEUED',
        progress            REAL NOT NULL DEFAULT 0.0,
        iteration           INTEGER,
        max_iterations      INTEGER,
        config_json         TEXT,
        provenance_id       TEXT,
        result_id           TEXT,
        error               TEXT,
        error_kind          TEXT,
        stdout_path         TEXT,
        stderr_path         TEXT,
        created_at          TEXT NOT NULL,
        started_at          TEXT,
        finished_at         TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, updated_at);
    CREATE INDEX IF NOT EXISTS jobs_owner_idx   ON jobs(owner_id, updated_at);

    CREATE TABLE IF NOT EXISTS job_events (
        event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id       TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
        seq          INTEGER NOT NULL,
        type         TEXT NOT NULL,
        stage        TEXT,
        payload_json TEXT NOT NULL,
        ts           TEXT NOT NULL,
        UNIQUE(job_id, seq)
    );
    CREATE INDEX IF NOT EXISTS job_events_job_idx ON job_events(job_id, seq);

    CREATE TABLE IF NOT EXISTS results (
        result_id      TEXT PRIMARY KEY,
        job_id         TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
        dataset_id     TEXT,
        schema_version TEXT NOT NULL,
        payload_json   TEXT NOT NULL,
        created_at     TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS results_job_idx ON results(job_id);

    CREATE TABLE IF NOT EXISTS provenance_records (
        provenance_id  TEXT PRIMARY KEY,
        job_id         TEXT REFERENCES jobs(job_id) ON DELETE CASCADE,
        schema_version TEXT NOT NULL,
        payload_json   TEXT NOT NULL,
        created_at     TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS job_artifacts (
        job_id      TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
        kind        TEXT NOT NULL,
        ref_json    TEXT NOT NULL,
        attached_at TEXT NOT NULL,
        UNIQUE(job_id, kind, ref_json)
    );
    CREATE INDEX IF NOT EXISTS job_artifacts_job_idx ON job_artifacts(job_id);
    """,
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


class JobRecord(BaseModel):
    """The durable job row.  One Job consumes one Dataset and produces one
    ``AnalysisResult`` (PRD §5).  ``config_json`` is the *effective*
    configuration (PRD §7: ``snr_floor`` must be reconstructible from the
    record -- it is not in ``JOB_REGISTRY`` today)."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    owner_id: str = DEFAULT_OWNER
    target_name: str
    resolved_target_id: str | None = None
    mission: str | None = None
    dataset_id: str | None = None
    dataset_ref: ArtifactRef | None = None
    status: JobStatus = JobStatus.QUEUED
    stage: JobStage = JobStage.QUEUED
    progress: float = 0.0
    iteration: int | None = None
    max_iterations: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    provenance_id: str | None = None
    result_id: str | None = None
    error: str | None = None
    error_kind: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    finished_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def is_live(self) -> bool:
        return self.status.is_live

    def is_terminal(self) -> bool:
        return self.status.is_terminal


class JobEvent(BaseModel):
    """One JSONL event from the worker, persisted and linked to its job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    seq: int
    type: str
    stage: JobStage | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=utc_now_iso)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


class JobStore:
    """Thread-safe SQLite/WAL persistence for jobs, events and results.

    Connections are opened with ``check_same_thread=False`` and guarded by
    a re-entrant lock: the supervisor (asyncio, one thread) and the SSE
    reader (another thread) both touch the store, and SQLite objects must
    not cross threads unsynchronized.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = artifact_path(DEFAULT_DB_PATH)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    # -- setup ----------------------------------------------------------------

    def _configure(self) -> None:
        # WAL: readers never block the writer, and a crash leaves a
        # recoverable journal rather than a torn page.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def _migrate(self) -> None:
        applied = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for index, migration in enumerate(_MIGRATIONS, start=1):
            if index <= applied:
                continue
            self._conn.executescript(migration)
            self._conn.execute(f"PRAGMA user_version = {index}")
        if self._conn.execute("PRAGMA user_version").fetchone()[0] != DB_SCHEMA_VERSION:
            raise RuntimeError(
                f"job database at {self.db_path} is at an unexpected schema version"
            )

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "JobStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- queries --------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            owner_id=row["owner_id"],
            target_name=row["target_name"],
            resolved_target_id=row["resolved_target_id"],
            mission=row["mission"],
            dataset_id=row["dataset_id"],
            dataset_ref=ArtifactRef.model_validate_json(row["dataset_ref"])
            if row["dataset_ref"]
            else None,
            status=JobStatus(row["status"]),
            stage=JobStage(row["stage"]),
            progress=float(row["progress"] or 0.0),
            iteration=row["iteration"],
            max_iterations=row["max_iterations"],
            config=json.loads(row["config_json"]) if row["config_json"] else {},
            provenance_id=row["provenance_id"],
            result_id=row["result_id"],
            error=row["error"],
            error_kind=row["error_kind"],
            stdout_path=row["stdout_path"],
            stderr_path=row["stderr_path"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
        )

    def create_job(self, record: JobRecord) -> JobRecord:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    job_id, owner_id, target_name, resolved_target_id, mission,
                    dataset_id, dataset_ref, status, stage, progress, iteration,
                    max_iterations, config_json, provenance_id, result_id, error,
                    error_kind, stdout_path, stderr_path, created_at, started_at,
                    finished_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.job_id, record.owner_id, record.target_name,
                    record.resolved_target_id, record.mission, record.dataset_id,
                    record.dataset_ref.model_dump_json() if record.dataset_ref else None,
                    record.status.value, record.stage.value, record.progress,
                    record.iteration, record.max_iterations,
                    json.dumps(record.config) if record.config else None,
                    record.provenance_id, record.result_id, record.error,
                    record.error_kind, record.stdout_path, record.stderr_path,
                    record.created_at, record.started_at, record.finished_at,
                    record.updated_at,
                ),
            )
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def require_job(self, job_id: str) -> JobRecord:
        record = self.get_job(job_id)
        if record is None:
            raise KeyError(f"no such job: {job_id}")
        return record

    def list_jobs(
        self,
        *,
        owner_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        query = "SELECT * FROM jobs"
        clauses: list[str] = []
        params: list[Any] = []
        if owner_id is not None:
            clauses.append("owner_id = ?")
            params.append(owner_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    # -- transitions ----------------------------------------------------------

    def update_job(self, job_id: str, **fields: Any) -> JobRecord:
        """Update job columns.  ``status``/``stage`` may be str or enum."""
        allowed = {
            "status", "stage", "progress", "iteration", "max_iterations",
            "config", "provenance_id", "result_id", "error", "error_kind",
            "stdout_path", "stderr_path", "started_at", "finished_at",
            "dataset_id", "dataset_ref",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown JobRecord fields: {sorted(unknown)}")

        normalized: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "status" and not isinstance(value, JobStatus):
                value = JobStatus(value)
            if key == "stage" and not isinstance(value, JobStage):
                value = JobStage(value)
            if key == "config":
                normalized["config_json"] = json.dumps(value)
                continue
            if key == "dataset_ref" and value is not None:
                value = (
                    value.model_dump_json()
                    if isinstance(value, ArtifactRef)
                    else value
                )
            normalized[key] = value
        normalized["updated_at"] = utc_now_iso()

        if "status" in normalized:
            status = normalized["status"]
            if isinstance(status, JobStatus) and status.is_terminal:
                normalized.setdefault("finished_at", utc_now_iso())
            elif isinstance(status, JobStatus) and status is JobStatus.RUNNING:
                normalized.setdefault("started_at", utc_now_iso())

        assignments = ", ".join(f"{col} = ?" for col in normalized)
        params = list(normalized.values()) + [job_id]
        with self._lock:
            self._conn.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?", params
            )
        return self.require_job(job_id)

    def transition(
        self,
        job_id: str,
        status: JobStatus,
        stage: JobStage | None = None,
        *,
        error: str | None = None,
        error_kind: str | None = None,
    ) -> JobRecord:
        fields: dict[str, Any] = {"status": status}
        if stage is not None:
            fields["stage"] = stage
        if error is not None:
            fields["error"] = error
        if error_kind is not None:
            fields["error_kind"] = error_kind
        return self.update_job(job_id, **fields)

    # -- events ---------------------------------------------------------------

    def append_event(
        self,
        job_id: str,
        event_type: str,
        *,
        stage: JobStage | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> JobEvent:
        stage_enum = JobStage(stage) if isinstance(stage, str) else stage
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            seq = int(row[0])
            event = JobEvent(
                job_id=job_id,
                seq=seq,
                type=event_type,
                stage=stage_enum,
                payload=payload or {},
            )
            self._conn.execute(
                """
                INSERT INTO job_events (job_id, seq, type, stage, payload_json, ts)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    event.job_id, event.seq, event.type,
                    event.stage.value if event.stage else None,
                    json.dumps(event.payload, default=str), event.ts,
                ),
            )
            # An event is also a liveness signal: keep the row's mtime fresh.
            self._conn.execute(
                "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
                (event.ts, job_id),
            )
        return event

    def list_events(
        self, job_id: str, *, after_seq: int = 0, limit: int = 1000
    ) -> list[JobEvent]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM job_events
                WHERE job_id = ? AND seq > ?
                ORDER BY seq ASC LIMIT ?
                """,
                (job_id, after_seq, limit),
            ).fetchall()
        return [
            JobEvent(
                job_id=row["job_id"],
                seq=row["seq"],
                type=row["type"],
                stage=JobStage(row["stage"]) if row["stage"] else None,
                payload=json.loads(row["payload_json"]),
                ts=row["ts"],
            )
            for row in rows
        ]

    def iter_events(self, job_id: str) -> Iterator[JobEvent]:
        yield from self.list_events(job_id, limit=10**9)

    # -- results / provenance --------------------------------------------------

    def attach_result(self, job_id: str, result: AnalysisResult) -> AnalysisResult:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO results
                    (result_id, job_id, dataset_id, schema_version, payload_json, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    result.result_id, result.job_id, result.dataset_id,
                    result.schema_version, result.model_dump_json(), result.created_at_iso,
                ),
            )
            self.update_job(
                job_id,
                result_id=result.result_id,
                status=result.status,
                stage=JobStage.COMPLETED
                if result.status is JobStatus.COMPLETED
                else JobStage.FAILED,
                error=result.error,
                error_kind=result.error_kind,
            )
        return result

    def get_result(self, job_id: str) -> AnalysisResult | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM results WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return AnalysisResult.model_validate_json(row["payload_json"])

    def attach_provenance(self, job_id: str, provenance: Provenance) -> Provenance:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO provenance_records
                    (provenance_id, job_id, schema_version, payload_json, created_at)
                VALUES (?,?,?,?,?)
                """,
                (
                    provenance.provenance_id, job_id, provenance.schema_version,
                    provenance.model_dump_json(), provenance.created_at_iso,
                ),
            )
            self.update_job(job_id, provenance_id=provenance.provenance_id)
        return provenance

    def get_provenance(self, job_id: str) -> Provenance | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM provenance_records WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return Provenance.model_validate_json(row["payload_json"])

    def attach_artifact(self, job_id: str, kind: str, ref: ArtifactRef) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO job_artifacts (job_id, kind, ref_json, attached_at)
                VALUES (?,?,?,?)
                """,
                (job_id, kind, ref.model_dump_json(), utc_now_iso()),
            )

    def list_artifacts(self, job_id: str) -> list[tuple[str, ArtifactRef]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind, ref_json FROM job_artifacts WHERE job_id = ?",
                (job_id,),
            ).fetchall()
        return [
            (row["kind"], ArtifactRef.model_validate_json(row["ref_json"]))
            for row in rows
        ]

    # -- recovery --------------------------------------------------------------

    def reclaim_stale(self, *, reason: str = "recovered as stale on startup") -> list[JobRecord]:
        """Reclaim rows left RUNNING by a crash (PRD §5.1).

        A job in a live state with no live process is *failed*, not
        silently forgotten: this is what removes the need for the manual
        "Clear Stale Job" button.
        """
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT * FROM jobs
                WHERE status IN ({",".join("?" * len(_LIVE_STATES))})
                """,
                tuple(_LIVE_STATES),
            ).fetchall()
        reclaimed: list[JobRecord] = []
        for row in rows:
            record = self._row_to_record(row)
            self.transition(
                record.job_id,
                JobStatus.FAILED,
                JobStage.FAILED,
                error=reason,
                error_kind="stale_recovery",
            )
            self.append_event(
                record.job_id,
                "system",
                stage=JobStage.FAILED,
                payload={"reason": reason},
            )
            reclaimed.append(record)
        return reclaimed

    def cancel(self, job_id: str, reason: str = "cancelled by request") -> JobRecord:
        record = self.transition(
            job_id, JobStatus.CANCELLED, JobStage.CANCELLED, error=reason,
            error_kind="cancelled",
        )
        self.append_event(
            job_id, "system", stage=JobStage.CANCELLED, payload={"reason": reason}
        )
        return record
