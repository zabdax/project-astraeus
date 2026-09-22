# P4-G TLS unlock — Windows measurement + equivalence (2026-09-22)

Bucket P4-G lands the P05-A unlock as code: `ASTRAEUS_TLS_THREADS`
(default serial) with daemon-forced serial, on the unified loop.
Production enablement requires the Linux re-measure — this box is
Windows (spawn), so enablement stays OFF everywhere by default.

## Method

`benchmarks/tls_multiprocessing_benchmark.py bench --arms narrow
--threads 1,8 --repeats 1` on the 8 cached real curves, plus the
slow equivalence test (`tests/test_p4g_tls_unlock.py`, tiny curve,
serial vs 2-thread through `detect_transit_candidate`).

## Results (BLS-narrowed window, 8 cores, Windows spawn)

| Target | serial wall (s) | 8-thread wall (s) | speedup | SDE identical | period identical |
|---|---|---|---|---|---|
| TRAPPIST-1 | 338.8 | 188.1 | 1.80x | yes | yes |
| Kepler-11 | 110.0 | 89.9 | 1.22x | yes | yes |
| Kepler-90 | 123.7 | 116.8 | 1.06x | yes | yes |
| HD 80606 b | 66.0 | 51.7 | 1.28x | yes | yes |
| Kepler-20 | 256.7 | 125.4 | 2.05x | yes | yes |
| Kepler-4d | 352.0 | 168.8 | 2.09x | yes | yes |
| AU Mic | timeout (>2400) | 2381.7 | infeasible→feasible | n/a (no serial) | n/a |
| WASP-12 b | timeout (>2400) | 1529.1 | infeasible→feasible | n/a (no serial) | n/a |

The six completed pairs reproduce the P05-A range (1.06x–2.08x);
SDE and period are bit-identical in every completed pair. The two
largest curves cannot complete serially inside a 40-minute budget at
all — there the unlock is the difference between an answer and none,
with identical science. In-pipeline equivalence (tiny curve, 1 vs 2
threads): identical SDE/period/outcome.

## What shipped

- `detect_transit_candidate(..., tls_threads=None)`: serial literal
  branch (daemon-safe) + resolver-sourced parallel branch.
- `_tls_thread_count()`: env/argument → validated, cpu-capped,
  daemon-forced serial. Default 1 everywhere: zero behavior change
  unless opted in.
- `run_multi_planet_search(tls_threads=...)` + `WorkerSpec.tls_threads`
  plumbed through the Popen worker (the only path that can spawn a
  Pool). Legacy daemon adapter passes nothing → serial always.
- Characterization test evolved to the exact new contract
  (Constant(1) or resolver call — never default/cpu_count/variable).

## Linux gate (production enablement, NOT code)

Re-run this table on the deployment platform and re-confirm
bit-identity there before setting `ASTRAEUS_TLS_THREADS` anywhere
that matters. The nested-pool mechanism is start-method dependent;
Windows spawn numbers do not transfer.

## Regression note (pre-existing order pollution, not P4-G)

`tests/jobs/*` before `test_tls_call_path_contract.py::
test_detect_transit_candidate_surfaces_tls_environment_error` in one
invocation fails the sentinel assertion (in-process `run_worker`
rebinds global logging handlers; the sentinel leaves `captured.out`).
Proven on the pristine tree with P4-G stashed (1 failed, 15 passed),
so it is not this bucket. The full fast gate collects
`characterize` before `jobs` (alphabetical) and is unaffected. Fix
belongs to a test-hygiene bucket (snapshot/restore logger handlers
around in-process worker runs), not here.
