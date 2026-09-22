BUCKET: P4-G
STATUS: COMPLETE (code; production enablement gated on Linux re-measure)

PROVIDES:
- Flag-gated TLS unlock, default serial: `ASTRAEUS_TLS_THREADS` env /
  `tls_threads` argument, resolved by `_tls_thread_count()` (validated,
  cpu-capped, daemon-forced serial). Daemon legacy path always serial.
- Plumbing: `run_multi_planet_search` + `WorkerSpec` → Popen worker
  (the only Pool-capable path). API unchanged (env-gated only).
- Characterization test evolved to the exact new contract.
- `tests/test_p4g_tls_unlock.py` (resolver/daemon units fast;
  bit-identity equivalence slow) + `reports/p4g_tls_unlock.md`.

MEASURED (Windows spawn, 8 cores, narrow window):
- 6 completed pairs: 1.06x–2.09x, bit-identical SDE/period.
- AU Mic + WASP-12 b: serial infeasible (>40 min); 8-thread completes
  (2382 s / 1529 s). Unlock = answer vs none, same science.
- In-pipeline tiny-curve equivalence: identical SDE/period/outcome.

FILES OF INTEREST:
- astraeus/analysis/detection.py (resolver + two-branch call)
- astraeus/core/orchestrator.py, astraeus/jobs/worker.py (plumbing)
- tests/characterize/test_tls_call_path_contract.py (new contract)
- tests/test_p4g_tls_unlock.py, reports/p4g_tls_unlock.md

KNOWN CONSTRAINTS:
- Default 1 everywhere: zero behavior change unless opted in.
- Linux re-measure + bit-identity required before production use.
- Regression: jobs+characterize+P4-G+fail-closed = 89 passed + 1
  pre-existing order-pollution failure (proven on pristine tree, full
  gate order unaffected). See report.

NEXT REQUIRED ACTION:
- Phase 5. Enable `ASTRAEUS_TLS_THREADS` in prod only after Linux gate.
