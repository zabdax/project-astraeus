BUCKET: P1-F
STATUS: COMPLETE

PROVIDES:
- The worker/IPC replacement (PRD §5.1).  `multiprocessing.Process(daemon=True)`
  + `multiprocessing.Queue` is replaced by `subprocess.Popen` running a
  dedicated worker that emits newline-delimited JSON events on stdout.  The
  old mechanism could not be flag-flipped: `Process.__init__` has no
  `start_new_session`, and a daemon cannot create the `Pool` TLS needs
  (P05-A's measured nested-pool constraint).
- `astraeus/jobs/worker.py` — the worker process.  Runs the REAL pipeline
    (the engine is wrapped, never rewritten), writes results + provenance
    itself before emitting `done`, and rebinds both the logger AND the
    engine's `print()` output to the job's stderr capture so nothing can
    corrupt the JSONL event channel.
- `astraeus/jobs/supervisor.py` — the asyncio supervisor: process-tree
  termination (`killpg` on POSIX, `taskkill /T` on Windows), a hard
  wall-clock timeout, stale-job recovery, and the replay-then-live event
  seam for SSE.
- `astraeus/jobs/events.py` — the stable wire vocabulary
  (`running/iteration/candidate/warning/done/error` plus `stage/progress/
  artifact/system` and error `kind`s incl. `tls_infrastructure`,
  `backend_unavailable`, `timeout`).
- Cancellation, hard timeout, and restart-survival are all demonstrated by
  real-pipeline tests, not stubs.

CONSUMED BY:
- P1-G (real data crosses this boundary)
- P1-H (the API layer drives the supervisor and streams its events)
- P1-I (search-loop unification depends on the final worker topology)

NEW CONTRACTS:
- JSONL worker event vocabulary (owned here; P1-G/P1-H/P3-B consume it)

FILES OF INTEREST:
- astraeus/jobs/worker.py
- astraeus/jobs/supervisor.py
- astraeus/jobs/events.py
- astraeus/core/orchestrator.py   (the additive `on_event` hook)
- tests/jobs/test_worker_supervisor.py

KNOWN CONSTRAINTS (all found by failing tests, then fixed):
- The worker is the SOLE writer of the durable event trail.  The supervisor
  feeds live subscribers only; appending from both sides races on
  `(job_id, seq)`.
- The worker emits the authoritative `running`/`done`; the orchestrator's
  own copies of those are NOT forwarded (they would duplicate).
- Windows `taskkill` must be called WITHOUT a stray empty argv token, and
  the supervisor must only trust a zero return code — otherwise the kill
  silently fails, the tree survives, and orphaned TLS children hold the
  stdout pipe open, pinning an executor thread (the pump must also stop
  once the handle is `terminated`).
- TLS has a fixed ~9 s floor, so real-pipeline worker tests carry the
  `smoke` marker; the full supervisor suite runs in ~43 s, down from ~428 s
  before the cancel-path fix.

NEXT REQUIRED ACTION:
- P1-G and P1-H may build on the worker + supervisor.
