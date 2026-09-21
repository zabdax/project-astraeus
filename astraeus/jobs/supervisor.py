"""The asyncio job supervisor (P1-F).

PRD v4.1 §5.1 / §13.1.  Supplies the three job-system capabilities that
do not exist today and that the Phase 1 exit gate demands (PRD §21):

* **cancellation with process-tree termination** -- ``cancel_job``
  (``orchestrator.py:392``) can only ``terminate()`` the single
  ``multiprocessing.Process``, leaving TLS's own thread pool orphaned;
* **a hard timeout** -- none exists, so a hung TLS call runs forever
  (an accidental DoS, PRD §13.1);
* **stale-job recovery** -- via ``JobStore.reclaim_stale`` at startup.

The supervisor *wraps* the engine: it spawns the worker subprocess of
:mod:`astraeus.jobs.worker`, tails its JSONL stdout, and persists events
to the durable store.  Nothing in ``astraeus/core`` or ``astraeus/analysis``
is rewritten (PRD §16: migration, not rewrite).
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from astraeus.contracts.analysis_result import JobStage, JobStatus
from astraeus.core import paths
from astraeus.core.paths import artifact_path
from astraeus.jobs.events import parse_event_line
from astraeus.jobs.store import JobRecord, JobStore
from astraeus.jobs.worker import EXIT_OK, WorkerSpec

__all__ = ["JobSupervisor", "WorkerHandle"]

#: Default wall-clock budget.  PRD §16.1 / P05-A: the real Kepler-90 serial
#: TLS baseline is ~150 s under a BLS-narrowed window and exceeds a 900 s
#: budget single-threaded on true defaults, so the default must be generous
#: while still finite.  A job may always raise it.
DEFAULT_TIMEOUT_SECONDS = 1800.0

#: Grace period between SIGTERM and SIGKILL so the worker can flush its
#: capture files and emit a final event.
DEFAULT_GRACE_SECONDS = 5.0


class WorkerHandle:
    """A live worker subprocess and its I/O plumbing."""

    def __init__(
        self,
        process: subprocess.Popen,
        spec: WorkerSpec,
        stderr_path: Path,
    ) -> None:
        self.process = process
        self.spec = spec
        self.stderr_path = stderr_path
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self.stdout_task: asyncio.Task | None = None
        self.stderr_task: asyncio.Task | None = None
        self.stdout_lines: list[str] = []
        self.terminated = False

    @property
    def pid(self) -> int:
        return self.process.pid

    def kill_process_tree(self, force: bool = False) -> None:
        """Terminate the whole process group.

        ``start_new_session=True`` puts the worker (and anything it spawns,
        including TLS's ``Pool``) in its own session, so ``killpg`` reaches
        the entire tree -- the thing ``multiprocessing.Process`` could not
        do (no ``start_new_session`` parameter) and the reason this
        redesign exists (PRD §5.1, §17 risk register).

        On Windows there are no process groups: ``start_new_session`` is a
        no-op and ``killpg`` is unavailable.  We fall back to ``taskkill
        /T`` (which does walk the tree) and finally to ``kill()``.  PRD's
        production scope is Linux; the fallback keeps local dev honest.
        """
        if self.terminated:
            return
        self.terminated = True
        proc = self.process
        if proc.poll() is not None:
            return
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL if force else signal.SIGTERM)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        else:  # Windows
            # ``/T`` walks the process tree, reaching the TLS ``Pool``
            # children that ``terminate()`` cannot.  Build argv without a
            # stray empty token -- ``taskkill /PID <pid> /T ""`` is rejected
            # and would silently leave the tree alive -- and only trust it
            # when taskkill actually succeeded.
            argv = ["taskkill", "/PID", str(proc.pid), "/T"]
            if force:
                argv.append("/F")
            try:
                completed = subprocess.run(
                    argv, capture_output=True, check=False, timeout=10.0
                )
                if completed.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            proc.kill() if force else proc.terminate()
        except OSError:
            pass


class JobSupervisor:
    """Owns the worker lifecycle for one process.  Not a global singleton:
    the API layer (P1-H) instantiates one per app and may run several jobs
    concurrently, bounded by a quota (PRD §13.1)."""

    def __init__(
        self,
        store: JobStore,
        *,
        artifact_root: Path | str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        max_concurrent: int = 4,
    ) -> None:
        self.store = store
        self.artifact_root = Path(artifact_root) if artifact_root else artifact_path("artifacts")
        self.timeout_seconds = timeout_seconds
        self.grace_seconds = grace_seconds
        self.max_concurrent = max_concurrent
        self._handles: dict[str, WorkerHandle] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # -- submission -----------------------------------------------------------

    def _spec_path(self, job_id: str) -> Path:
        return artifact_path("jobs", "specs", f"{job_id}.json")

    def _stderr_path(self, job_id: str) -> Path:
        return artifact_path("jobs", "logs", f"{job_id}.stderr")

    async def submit(
        self,
        record: JobRecord,
        *,
        dataset_ref: Any | None = None,
        fetch_real_data: bool = False,
        config: dict | None = None,
    ) -> str:
        """Persist the job row, write the worker spec, and launch the worker."""
        if len(self._handles) >= self.max_concurrent:
            raise RuntimeError(
                f"job quota exhausted ({self.max_concurrent} concurrent); "
                "rejecting submission (PRD §13.1 resource governance)"
            )
        record.stdout_path = str(self._spec_path(record.job_id))
        record.stderr_path = str(self._stderr_path(record.job_id))
        record.config = {
            "max_signals": record.max_iterations or 5,
            "snr_floor": record.config.get("snr_floor") if record.config else None,
            **(config or {}),
        }
        self.store.create_job(record)
        self.store.transition(record.job_id, JobStatus.RUNNING, JobStage.STARTING)

        spec = WorkerSpec(
            job_id=record.job_id,
            target_name=record.target_name,
            mission=record.mission,
            resolved_target_id=record.resolved_target_id,
            dataset_ref=dataset_ref.model_dump() if hasattr(dataset_ref, "model_dump") else dataset_ref,
            artifact_root=str(self.artifact_root),
            db_path=str(self.store.db_path),
            max_signals=record.max_iterations or 5,
            snr_floor=float((record.config or {}).get("snr_floor") or 7.1),
            config=config or {},
            fetch_real_data=fetch_real_data,
        )
        spec_path = spec.save(self._spec_path(record.job_id))
        await self._launch(record.job_id, spec, spec_path)
        return record.job_id

    async def _launch(self, job_id: str, spec: WorkerSpec, spec_path: Path) -> None:
        async with self._semaphore:
            env = dict(os.environ)
            # The worker resolves the same data root as the supervisor, so
            # artifact paths agree regardless of either process's CWD
            # (Phase 0's CWD-independent paths, PRD §4.4).
            env.setdefault("ASTRAEUS_DATA_DIR", str(paths.data_root()))

            popen_kwargs: dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "stdin": subprocess.DEVNULL,
                "env": env,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "cwd": None,
                # PRD §5.1: a fresh session makes the worker's process tree
                # killable as a group.  On Windows this is accepted but inert.
                "start_new_session": os.name == "posix",
            }
            process = subprocess.Popen(
                [sys.executable, "-m", "astraeus.jobs.worker", "--spec", str(spec_path)],
                **popen_kwargs,
            )
            handle = WorkerHandle(process, spec, self._stderr_path(job_id))
            self._handles[job_id] = handle
            handle.stdout_task = asyncio.create_task(
                self._pump_stdout(job_id, handle), name=f"stdout:{job_id}"
            )

    async def _pump_stdout(self, job_id: str, handle: WorkerHandle) -> None:
        """Tail the worker's JSONL stdout: parse, persist, broadcast."""
        loop = asyncio.get_running_loop()
        stream = handle.process.stdout
        deadline = loop.time() + self.timeout_seconds if self.timeout_seconds else None

        while True:
            remaining = None
            if deadline is not None:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    await self._handle_timeout(job_id, handle)
                    return
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, stream.readline),
                    timeout=max(remaining, 0.5) if remaining else None,
                )
            except asyncio.TimeoutError:
                # Stop pumping once the process is gone *or* we have killed
                # the tree ourselves: an orphaned TLS child can keep the
                # inherited stdout pipe open after its parent dies, and
                # waiting on it would pin an executor thread forever.
                if handle.process.poll() is not None or handle.terminated:
                    break
                continue
            except (ValueError, OSError):
                break
            if not line:
                break
            handle.stdout_lines.append(line)
            await self._dispatch_line(job_id, handle, line)

        await self._await_exit(job_id, handle)

    async def _dispatch_line(self, job_id: str, handle: WorkerHandle, line: str) -> None:
        try:
            event = parse_event_line(line)
        except Exception as exc:  # noqa: BLE001 - protocol violations must surface
            # A non-JSON line on the event channel means the engine wrote to
            # our stdout; record it rather than corrupting the stream.
            self.store.append_event(
                job_id, "system", payload={"unparsed_line": line[:512], "error": str(exc)}
            )
            return
        if event is None:
            return
        # The worker persists the durable event trail itself, so the
        # supervisor's copy of the stream feeds live subscribers only --
        # appending here would duplicate every row.  Row-level state
        # updates are still the supervisor's (it owns the lifecycle).
        await handle.events.put(event.to_dict())
        self._apply_event(job_id, event)

    def _apply_event(self, job_id: str, event) -> None:
        """Translate worker events into job row updates."""
        etype = event.type
        payload = event.payload
        if etype == "stage":
            stage = payload.get("stage")
            status = payload.get("status")
            if stage:
                try:
                    self.store.update_job(job_id, stage=JobStage(stage))
                except ValueError:
                    pass
            if status == "failed":
                self.store.transition(job_id, JobStatus.FAILED, JobStage.FAILED,
                                      error=payload.get("message"),
                                      error_kind="pipeline")
        elif etype == "iteration":
            self.store.update_job(
                job_id,
                iteration=payload.get("iteration"),
                max_iterations=payload.get("max_iterations"),
                progress=_fraction(payload),
            )
        elif etype == "progress":
            self.store.update_job(
                job_id,
                iteration=payload.get("iteration"),
                max_iterations=payload.get("max_iterations"),
                progress=float(payload.get("fraction", 0.0)),
            )
        elif etype == "error":
            self.store.transition(
                job_id,
                JobStatus.FAILED,
                JobStage.FAILED,
                error=payload.get("message"),
                error_kind=payload.get("kind", "internal"),
            )
        elif etype == "done":
            self.store.transition(
                job_id, JobStatus.COMPLETED, JobStage.COMPLETED
            )

    async def _await_exit(self, job_id: str, handle: WorkerHandle) -> None:
        loop = asyncio.get_running_loop()
        try:
            code = await loop.run_in_executor(None, handle.process.wait)
        except Exception:  # noqa: BLE001
            code = None
        record = self.store.get_job(job_id)
        if record is not None and not record.is_terminal():
            if code == EXIT_OK:
                self.store.transition(job_id, JobStatus.COMPLETED, JobStage.COMPLETED)
            else:
                self.store.transition(
                    job_id, JobStatus.FAILED, JobStage.FAILED,
                    error=f"worker exited with code {code}",
                    error_kind="internal",
                )

    async def _handle_timeout(self, job_id: str, handle: WorkerHandle) -> None:
        """The hard wall-clock budget expired: kill the tree and mark FAILED."""
        handle.kill_process_tree(force=False)
        try:
            await asyncio.wait_for(_wait_proc(handle.process), timeout=self.grace_seconds)
        except asyncio.TimeoutError:
            handle.kill_process_tree(force=True)
        self.store.append_event(
            job_id, "system", stage=JobStage.FAILED,
            payload={"reason": f"hard timeout after {self.timeout_seconds:.0f}s"},
        )
        self.store.transition(
            job_id, JobStatus.FAILED, JobStage.FAILED,
            error=f"hard timeout after {self.timeout_seconds:.0f}s",
            error_kind="timeout",
        )

    # -- control --------------------------------------------------------------

    async def cancel(self, job_id: str) -> JobRecord:
        handle = self._handles.get(job_id)
        if handle is None:
            # Already gone: just mark the row (idempotent).
            return self.store.cancel(job_id)
        handle.kill_process_tree(force=False)
        try:
            await asyncio.wait_for(_wait_proc(handle.process), timeout=self.grace_seconds)
        except asyncio.TimeoutError:
            handle.kill_process_tree(force=True)
        record = self.store.cancel(job_id)
        return record

    async def wait(self, job_id: str) -> JobRecord:
        handle = self._handles.get(job_id)
        if handle is None:
            return self.store.require_job(job_id)
        if handle.stdout_task is not None:
            await handle.stdout_task
        return self.store.require_job(job_id)

    async def events(self, job_id: str, *, after_seq: int = 0) -> AsyncIterator[dict]:
        """Replay stored events, then stream live ones (SSE source, P1-H)."""
        for event in self.store.list_events(job_id, after_seq=after_seq, limit=10**9):
            yield event.payload | {
                "type": event.type,
                "stage": event.stage.value if event.stage else None,
                "seq": event.seq,
                "ts": event.ts,
            }
        handle = self._handles.get(job_id)
        if handle is None:
            return
        # A job that is already over is fully represented by its stored
        # trail; the pump's buffered queue would only echo it back again.
        record = self.store.get_job(job_id)
        if record is not None and record.is_terminal():
            return
        while True:
            try:
                event = await asyncio.wait_for(handle.events.get(), timeout=0.25)
            except asyncio.TimeoutError:
                record = self.store.get_job(job_id)
                if record is not None and record.is_terminal():
                    return
                continue
            yield event

    # -- teardown -------------------------------------------------------------

    async def shutdown(self) -> None:
        """Cancel everything still running (graceful drain)."""
        for job_id in list(self._handles):
            try:
                await self.cancel(job_id)
            except Exception:  # noqa: BLE001 - best-effort drain
                pass


def _fraction(payload: dict) -> float:
    iteration = payload.get("iteration")
    maximum = payload.get("max_iterations")
    if iteration and maximum:
        try:
            return min(1.0, float(iteration) / float(maximum))
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    return 0.0


async def _wait_proc(process: subprocess.Popen) -> int:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, process.wait)
