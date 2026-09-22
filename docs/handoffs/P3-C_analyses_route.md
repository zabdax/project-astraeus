BUCKET: P3-C
STATUS: COMPLETE

PROVIDES:
- `web/app/analyses/page.tsx`: owner-scoped job list (store query, via
  `GET /jobs`) → detail (status/stage/iteration, error + kind) →
  candidate summary with TLS labels → provenance drawer → analysis-JSON
  download → cancel for live jobs. Zero-candidate jobs render the
  measured negative explicitly.

CONSUMED BY:
- P3-H (restore/view parity with History)

FILES OF INTEREST:
- web/app/analyses/page.tsx

KNOWN CONSTRAINTS:
- Re-running a job means submitting again from Investigate/Simulate;
  the API exposes no clone, and the UI invents none.
- "Restore" semantics = view the durable record, never mutate it.

NEXT REQUIRED ACTION:
- P3-H compares against History on the same job id.
