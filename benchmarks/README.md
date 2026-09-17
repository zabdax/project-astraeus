# P05-A — TLS multiprocessing benchmark

Bucket **P05-A** of `docs/EXECUTION_BUCKETS.md`; gate spec `PRD_v4.1_web_platform.md`
Phase 0.5 ("Benchmark before you believe").

## Why this exists

`astraeus/analysis/detection.py` forces `use_threads=1` on every TLS `power()`
call, and `astraeus/core/orchestrator.py` spawns its search worker with
`daemon=True`. Those two settings are **coupled**: a daemonic process cannot
create a `multiprocessing.Pool` child, and TLS parallelises *exactly* by
creating such a pool (`transitleastsquares/main.py:141`).

The migration plan therefore carried a projected **6–8×** speedup for the
`daemon=False` + `use_threads=cpu_count()` unlock. That figure was a
**computed Amdahl bound**, never a measurement — see
`scratch/j2c_tls_profiling_result.json`, key
`A_default_8iter_multi_threaded_lower_bound_min` (a division by the core
count). PRD v4.1 Phase 0.5 forbids acting on it.

This harness replaces the bound with a measurement.

## What it measures

* **Serial baseline** — `power(use_threads=1)` wall time on each target, both
  with TLS defaults (the ≈149.7 s Kepler-90 reference) and with the
  production BLS-narrowed `0.95p–1.05p` window that `detect_transit_candidate`
  actually uses.
* **Parallel speedup** — the same call with `use_threads` swept over
  `{1, 2, 4, cpu_count}`, **measured**, not divided.
* **Numerical equivalence** — SDE / FAP / period returned by the serial and
  parallel arms. TLS distributes trial periods across pool workers, so a
  reduction-order change can perturb the statistic; if the parallel arm moves
  the science, that is a Phase 4 concern and must gate the unlock.
* **Nested-pool mechanism** — the real TLS call inside a worker spawned
  `daemon=True` vs `daemon=False`. This is the direct test of the unlock's
  premise, rather than an assertion inherited from a code comment.

## Reproducing

```bash
# 1. Acquire the 8 cached real targets through the production ingestion
#    path (LightkurveClient.download_pipeline) and freeze them to
#    benchmarks/cache/*.npz. Network-required, run once.
py benchmarks/tls_multiprocessing_benchmark.py acquire

# 2. Measure. Each arm runs isolated in its own non-daemon subprocess with a
#    hard wall-clock budget, so a runaway arm is killed, not hung. Results
#    are written incrementally -- an interrupted run keeps what it measured.
py benchmarks/tls_multiprocessing_benchmark.py bench

# 3. Prove the daemon=False mechanism on the real call stack.
py benchmarks/tls_multiprocessing_benchmark.py nested

# 4. Render the written result the Phase 0.5 exit gate requires.
py benchmarks/tls_multiprocessing_benchmark.py report
```

Useful flags: `bench --arms {default,narrow,both}`, `bench --threads 1,2,4,cpu`,
`bench --repeats N`, `nested --target Kepler-90`. The per-arm budget defaults to
2400 s and is overridable via `ASTRAEUS_BENCH_ARM_TIMEOUT`.

## Outputs

| path | committed | contents |
|---|---|---|
| `benchmarks/tls_multiprocessing_benchmark.py` | yes | the harness (the reusable instrument) |
| `benchmarks/results/p05a_tls_benchmark.json` | yes | raw measured data |
| `benchmarks/results/p05a_tls_benchmark.md` | yes | the written result + unlock recommendation |
| `benchmarks/cache/*.npz` | **no** (gitignored) | downloaded + stitched input curves; regenerable via `acquire` |

The measured **results** are the tracked artifact; the input **data** they were
taken on is not — it is regenerable and large. This matches the Phase 0
gitignore anchoring convention.

## Contract

`tests/characterize/test_tls_call_path_contract.py` locks the harness's presence
and the result's well-formedness (a measured serial baseline, a measured
parallel speedup, and a resolved nested-pool mechanism verdict). The numeric
values are deliberately **not** pinned — a re-run on different hardware must be
able to replace them. What is contractual is that the decision rests on a
measurement.

The existing `use_threads=1` / `daemon=True` locks in that same test file remain
in force: this bucket **measures**, it does not unlock. Landing the unlock is
bucket P4-G, and only after P1-F's IPC redesign makes `daemon=False` safe to
adopt.
