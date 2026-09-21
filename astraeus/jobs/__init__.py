"""Job system: durable persistence, worker IPC and the async supervisor.

Phase 1 (PRD v4.1 §5.1).  Before this package, ``JOB_REGISTRY`` was an
in-memory dict (``orchestrator.py:371``) guarded by a plain lock, jobs
were lost on restart, ``multiprocessing.Process(daemon=True)`` could not
be flag-flipped to ``start_new_session=True`` (the constructor has no
such parameter -- verified), a hung TLS call ran forever with no timeout,
and warnings went to inherited stdout unlinked to ``job_id``.

Layout:

* :mod:`astraeus.jobs.store`      -- SQLite/WAL persistence (P1-E).
* :mod:`astraeus.jobs.events`     -- the JSONL worker event vocabulary (P1-F).
* :mod:`astraeus.jobs.worker`     -- the dedicated worker process (P1-F).
* :mod:`astraeus.jobs.supervisor` -- asyncio + Popen supervisor with
                                     process-group kill and hard timeout (P1-F).

The engine boundary is unchanged: the supervisor *wraps*
``run_multi_planet_search``, it does not rewrite it (PRD §16:
"migration, not rewrite").
"""

from astraeus.jobs.events import (
    WorkerEvent,
    emit_event,
    parse_event_line,
)
from astraeus.jobs.store import JobRecord, JobStore

__all__ = [
    "JobRecord",
    "JobStore",
    "WorkerEvent",
    "emit_event",
    "parse_event_line",
]
