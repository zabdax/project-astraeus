"""The JSONL worker event vocabulary (P1-F).

PRD v4.1 §5.1: the event schema *supersedes* today's
``{running, iteration, candidate, done, error}`` (emitted onto a
``multiprocessing.Queue`` at ``orchestrator.py:415``) and adds
``warning``, ``stage``, ``progress``, ``artifact`` and a structured
``error{kind}``.

Superset, not replacement (PRD §17 risk register: "keep the event
vocabulary as the JSONL schema so consumers are stable").  The five
legacy ``type`` values are emitted unchanged; a consumer written against
the old vocabulary keeps working, and new consumers get the richer
fields.  Each event is one line of UTF-8 JSON on the worker's stdout --
newline-delimited so a truncated stream still yields complete records up
to the break.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from astraeus.contracts.analysis_result import JobStage

__all__ = [
    "EVENT_TYPES",
    "LEGACY_EVENT_TYPES",
    "ERROR_KINDS",
    "WorkerEvent",
    "emit_event",
    "parse_event_line",
]

#: Every event type the worker may emit.
EVENT_TYPES = frozenset(
    {
        # --- legacy vocabulary (unchanged, for consumer stability) --------
        "running",
        "iteration",
        "candidate",
        "done",
        "error",
        # --- new vocabulary (PRD §5.1) -------------------------------------
        "stage",       # a pipeline stage started / finished
        "progress",    # measured progress, not a fake bar
        "warning",     # a structured warning linked to the job
        "artifact",    # an artifact was written to the store
        "system",      # supervisor / lifecycle, not the engine
    }
)

#: The five pre-existing types, kept byte-identical in shape.
LEGACY_EVENT_TYPES = frozenset({"running", "iteration", "candidate", "done", "error"})

#: Structured error kinds.  ``error`` events carry one of these so a
#: FAILED job's reason is machine-readable -- the PRD §21 Phase 1 gate
#: requires "a TLS infrastructure failure yields FAILED + reason, not
#: DONE / 0 candidates".
ERROR_KINDS = frozenset(
    {
        "backend_unavailable",   # a required scientific backend is missing
        "tls_infrastructure",    # TLS raised its locked infra-failure mode
        "timeout",               # the hard wall-clock budget was exceeded
        "cancelled",             # the process group was killed
        "ingestion",             # fetching / parsing data failed
        "pipeline",              # an engine exception
        "stale_recovery",        # the row was reclaimed at startup
        "internal",              # anything not otherwise classified
    }
)


class WorkerEvent:
    """A single newline-delimited worker event.

    Deliberately not a pydantic model: this is the *wire* format between
    a worker subprocess and the supervisor, and it must parse even when
    the worker is a different astraeus version.  Unknown fields are
    preserved, never rejected.
    """

    __slots__ = ("type", "stage", "payload")

    def __init__(
        self,
        type: str,
        *,
        stage: JobStage | str | None = None,
        **payload: Any,
    ) -> None:
        if type not in EVENT_TYPES:
            raise ValueError(
                f"unknown worker event type {type!r}; expected one of {sorted(EVENT_TYPES)}"
            )
        self.type = type
        self.stage = JobStage(stage) if isinstance(stage, str) else stage
        self.payload = payload

    def to_line(self) -> str:
        record: dict[str, Any] = {"type": self.type}
        if self.stage is not None:
            record["stage"] = (
                self.stage.value if isinstance(self.stage, JobStage) else str(self.stage)
            )
        record.update(self.payload)
        return json.dumps(record, default=str)

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {"type": self.type}
        if self.stage is not None:
            record["stage"] = (
                self.stage.value if isinstance(self.stage, JobStage) else str(self.stage)
            )
        record.update(self.payload)
        return record

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "WorkerEvent":
        record = dict(record)
        event_type = record.pop("type", None)
        stage = record.pop("stage", None)
        if event_type is None:
            raise ValueError("worker event record has no 'type'")
        return cls(event_type, stage=stage, **record)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"WorkerEvent({self.to_dict()})"


def emit_event(
    event_type: str,
    *,
    stage: JobStage | str | None = None,
    stream: Any = None,
    **payload: Any,
) -> str:
    """Serialize one event as a line and write it to ``stream`` (stdout).

    The worker's stdout is its only channel back to the supervisor, so
    the write is flushed immediately and the line terminator is always
    ``\\n``.  Anything the engine prints to stdout directly would
    corrupt the stream, which is why the worker redirects the engine's
    logging to stderr (see :mod:`astraeus.jobs.worker`).
    """
    line = WorkerEvent(event_type, stage=stage, **payload).to_line()
    target = stream if stream is not None else sys.stdout
    target.write(line + "\n")
    try:
        target.flush()
    except (AttributeError, ValueError):  # pragma: no cover - closed stream
        pass
    return line


def parse_event_line(line: str) -> WorkerEvent | None:
    """Parse one stdout line into a :class:`WorkerEvent`.

    Returns ``None`` for a blank line.  A line that is not valid JSON, or
    is valid JSON but not a worker event, raises -- the supervisor treats
    that as a protocol violation rather than silently dropping it, since
    a dropped event is exactly how progress reporting desyncs.
    """
    text = line.strip()
    if not text:
        return None
    record = json.loads(text)  # raises on malformed input, by design
    if not isinstance(record, dict):
        raise ValueError(f"worker event line is not a JSON object: {text[:120]}")
    return WorkerEvent.from_dict(record)
