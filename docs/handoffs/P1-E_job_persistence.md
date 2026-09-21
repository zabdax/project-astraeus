BUCKET: P1-E
STATUS: COMPLETE

PROVIDES:
- `astraeus/jobs/store.py` — durable job persistence in SQLite (WAL mode):
  the replacement for `JOB_REGISTRY`, the in-memory dict that lost every
  job on restart and forced the app to ship a manual "Clear Stale Job"
  button (PRD §5.1).
- Schema: `jobs` (with `owner_id`, indexed — PRD §13.1's "model users +
  owner_id from day one even with one row"), `job_events`, `results`,
  `provenance_records`, `job_artifacts`.  Idempotent migrations.
- `JobRecord` with the *effective* config on the row (PRD §7).
- Query/transitions: `list_jobs(owner_id=...)` (owner scoping by query, not
  post-hoc filtering), `transition`, `cancel`, `reclaim_stale`
  (stale-job recovery on startup), `append_event` with a monotonic `seq`.

CONSUMED BY:
- P1-H (the API layer's persistence and owner scoping)
- P2-A

NEW CONTRACTS:
- SQLite schema + migrations (owned here; P1-H/P2-A consume read-only)

FILES OF INTEREST:
- astraeus/jobs/store.py
- astraeus/jobs/__init__.py
- tests/jobs/test_store.py

KNOWN CONSTRAINTS:
- `append_event` assigns `seq` via `MAX(seq)+1`; the worker is the single
  authoritative event writer (see the P1-F manifest) so concurrent writers
  cannot collide on the sequence.
- `attach_result` is terminal: writing a result sets the row's status.

NEXT REQUIRED ACTION:
- P1-H may persist and scope jobs.
