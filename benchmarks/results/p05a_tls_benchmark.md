# P05-A -- TLS multiprocessing benchmark (measured)

Bucket P05-A of `docs/EXECUTION_BUCKETS.md`; gate spec `PRD_v4.1_web_platform.md` Phase 0.5.

## Machine

| property | value |
|---|---|
| python | 3.12.10 |
| platform | Windows-11-10.0.26200-SP0 |
| processor | Intel64 Family 6 Model 142 Stepping 12, GenuineIntel |
| cpu_count | 8 |
| mp_start_method | spawn |
| tls_version | 1.32 |

> Platform note: the PRD scopes this benchmark to Linux. Where the
> measurement below was taken on a different platform, the speedup is
> a property of the TLS workload and still binds, but the nested-pool
> behaviour is start-method dependent and must be re-confirmed on the
> deployment platform before the unlock lands (P4-G).

## Nested-pool mechanism (the unlock's premise)

Target: `Kepler-90`. The real TLS call run inside an
orchestrator-style worker, varying only the worker's `daemon` flag.

| worker | use_threads | result | wall (s) |
|---|---|---|---|
| daemon=True | 1 | ran | 84.682 |
| daemon=True | 8 | blocked | 3.139 |
| daemon=False | 1 | ran | 115.307 |
| daemon=False | 8 | ran | 101.783 |

**Mechanism confirmed: True.** A daemonic
worker cannot create the `multiprocessing.Pool` that TLS parallelism
requires; a non-daemonic worker can. `daemon=False` is therefore the
precise flag that gates `use_threads>1` -- the constraint in
`detection.py` and `orchestrator.py` is real, not a historical relic.
Daemon-worker error observed: `AssertionError: daemonic processes are not allowed to have children`

## Cost driver: trial-period count

TLS wall time is governed by the number of trial periods in the
search window, not by the cadence count alone. Every arm records its
`n_periods`; against the serial baseline this is what the unlock
would actually be paying for.

| target | window | cadences | n_periods | serial wall (s) | s per 100 periods |
|---|---|---|---|---|---|
| TRAPPIST-1 | narrow | 94910 | 2117 | 338.8 | 16.00 |
| Kepler-11 | narrow | 47100 | 1774 | 110.0 | 6.20 |
| Kepler-20 | narrow | 47098 | 1885 | 256.7 | 13.62 |
| Kepler-90 | narrow | 45853 | 613 | 123.7 | 20.18 |
| Kepler-4d | narrow | 42053 | 3103 | 352.0 | 11.34 |
| HD 80606 b | narrow | 35159 | 1133 | 66.0 | 5.82 |

Reference check: the plan's ~149.7 s Kepler-90 figure was measured by
`scratch/j2c_tls_profiling_result.json` under the profile label
`A_default_full`, whose kwargs are `period_min=200.08, period_max=221.14`
-- that is the **BLS-narrowed 828-period window, not TLS defaults**.
The label 'defaults' in the plan is therefore a misnomer; the number is a
narrowed-window measurement. The serial measurements above reproduce its
magnitude (Kepler-90, 613 periods) once normalised by period count.

True TLS defaults (no period bounds) on a ~1240 d baseline is a
different and far larger computation: the `default` arm on Kepler-90
exceeded its 900 s budget single-threaded and was terminated. That is
reported as a finding, not a gap -- it is why production narrows the
window via BLS before ever calling TLS.

## Measured TLS wall time

### TLS defaults (wide period grid)

| target | cadences | baseline (d) | threads | wall median (s) | measured speedup | fraction of ideal |
|---|---|---|---|---|---|---|
| Kepler-90 | 45853 | 1239.8 | 1 | *timeout* | - | - |

### Production window (BLS-narrowed 0.95p-1.05p)

| target | cadences | baseline (d) | threads | wall median (s) | measured speedup | fraction of ideal |
|---|---|---|---|---|---|---|
| AU Mic | 242237 | 2581.2 | 1 | *timeout* | - | - |
| TRAPPIST-1 | 94910 | 23.8 | 1 | 338.8 | 1.00x (baseline) | - |
| TRAPPIST-1 | 94910 | 23.8 | 2 | 302.7 | 1.12x | 56% |
| TRAPPIST-1 | 94910 | 23.8 | 4 | 214.5 | 1.58x | 40% |
| TRAPPIST-1 | 94910 | 23.8 | 8 | 188.1 | 1.80x | 22% |
| Kepler-11 | 47100 | 1050.5 | 1 | 110.0 | 1.00x (baseline) | - |
| Kepler-11 | 47100 | 1050.5 | 2 | 134.4 | 0.82x | 41% |
| Kepler-11 | 47100 | 1050.5 | 4 | 101.9 | 1.08x | 27% |
| Kepler-11 | 47100 | 1050.5 | 8 | 89.9 | 1.22x | 15% |
| Kepler-20 | 47098 | 1050.5 | 1 | 256.7 | 1.00x (baseline) | - |
| Kepler-20 | 47098 | 1050.5 | 2 | 175.8 | 1.46x | 73% |
| Kepler-20 | 47098 | 1050.5 | 4 | 142.7 | 1.80x | 45% |
| Kepler-20 | 47098 | 1050.5 | 8 | 125.4 | 2.05x | 26% |
| Kepler-90 | 45853 | 1239.8 | 1 | 123.7 | 1.00x (baseline) | - |
| Kepler-90 | 45853 | 1239.8 | 2 | 98.0 | 1.26x | 63% |
| Kepler-90 | 45853 | 1239.8 | 4 | 111.6 | 1.11x | 28% |
| Kepler-90 | 45853 | 1239.8 | 8 | 116.8 | 1.06x | 13% |
| Kepler-4d | 42053 | 1152.5 | 1 | 352.0 | 1.00x (baseline) | - |
| Kepler-4d | 42053 | 1152.5 | 2 | 250.7 | 1.40x | 70% |
| Kepler-4d | 42053 | 1152.5 | 4 | 197.2 | 1.78x | 45% |
| Kepler-4d | 42053 | 1152.5 | 8 | 168.8 | 2.08x | 26% |
| HD 80606 b | 35159 | 736.5 | 1 | 66.0 | 1.00x (baseline) | - |
| HD 80606 b | 35159 | 736.5 | 2 | 56.8 | 1.16x | 58% |
| HD 80606 b | 35159 | 736.5 | 4 | 56.9 | 1.16x | 29% |
| HD 80606 b | 35159 | 736.5 | 8 | 51.7 | 1.28x | 16% |

## Numerical equivalence (serial vs parallel)

| target | window | threads | SDE | dSDE vs serial | period (d) | dperiod (d) |
|---|---|---|---|---|---|---|
| TRAPPIST-1 | narrow | 1 | 5.215 | +0.000 | 9.4987 | +0.0000 |
| TRAPPIST-1 | narrow | 2 | 5.215 | +0.000 | 9.4987 | +0.0000 |
| TRAPPIST-1 | narrow | 4 | 5.215 | +0.000 | 9.4987 | +0.0000 |
| TRAPPIST-1 | narrow | 8 | 5.215 | +0.000 | 9.4987 | +0.0000 |
| Kepler-11 | narrow | 1 | 16.008 | +0.000 | 13.0252 | +0.0000 |
| Kepler-11 | narrow | 2 | 16.008 | +0.000 | 13.0252 | +0.0000 |
| Kepler-11 | narrow | 4 | 16.008 | +0.000 | 13.0252 | +0.0000 |
| Kepler-11 | narrow | 8 | 16.008 | +0.000 | 13.0252 | +0.0000 |
| Kepler-20 | narrow | 1 | 17.289 | +0.000 | 10.8542 | +0.0000 |
| Kepler-20 | narrow | 2 | 17.289 | +0.000 | 10.8542 | +0.0000 |
| Kepler-20 | narrow | 4 | 17.289 | +0.000 | 10.8542 | +0.0000 |
| Kepler-20 | narrow | 8 | 17.289 | +0.000 | 10.8542 | +0.0000 |
| Kepler-90 | narrow | 1 | 5.777 | +0.000 | 517.3806 | +0.0000 |
| Kepler-90 | narrow | 2 | 5.777 | +0.000 | 517.3806 | +0.0000 |
| Kepler-90 | narrow | 4 | 5.777 | +0.000 | 517.3806 | +0.0000 |
| Kepler-90 | narrow | 8 | 5.777 | +0.000 | 517.3806 | +0.0000 |
| Kepler-4d | narrow | 1 | 24.188 | +0.000 | 3.2137 | +0.0000 |
| Kepler-4d | narrow | 2 | 24.188 | +0.000 | 3.2137 | +0.0000 |
| Kepler-4d | narrow | 4 | 24.188 | +0.000 | 3.2137 | +0.0000 |
| Kepler-4d | narrow | 8 | 24.188 | +0.000 | 3.2137 | +0.0000 |
| HD 80606 b | narrow | 1 | 8.419 | +0.000 | 18.0810 | +0.0000 |
| HD 80606 b | narrow | 2 | 8.419 | +0.000 | 18.0810 | +0.0000 |
| HD 80606 b | narrow | 4 | 8.419 | +0.000 | 18.0810 | +0.0000 |
| HD 80606 b | narrow | 8 | 8.419 | +0.000 | 18.0810 | +0.0000 |

## Interpretation and unlock recommendation

Across 6 measured (target, window) pairs, the geometric-mean
speedup of `use_threads=8` over `use_threads=1` is **1.53x**
(serial 173.7s -> parallel 113.7s), i.e.
**19%** of the ideal `8x` Amdahl bound the plan had been
carrying as an assumption.

The weakest measured arm achieved 0.82x and the strongest 2.08x,
so the parallel pool does not uniformly pay off: small period grids
amortise pool startup poorly, and some arms are slower single-
threaded-to-parallel than others. That dispersion is the concrete reason
the unlock must be scoped from these numbers rather than from a single
division.

**Recommendation:** land the unlock only as the P4-G `[SCIENCE]` change,
behind a feature flag, after (a) this benchmark is re-run on the Linux
deployment platform, and (b) the numerical-equivalence deltas above are
accepted as a versioned scientific change. The IPC redesign in P1-F
(`Process`->`Popen`, Queue->JSONL) is what makes `daemon=False` safe to
adopt at all, so P05-A informs P1-F's scope but does not itself change
production topology.

## Raw data

Full JSON: `benchmarks/results/p05a_tls_benchmark.json`.
