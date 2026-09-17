BUCKET: P05-A
STATUS: COMPLETE

PROVIDES:
- The measured TLS multiprocessing benchmark the Phase 0.5 exit gate requires:
  serial baseline + parallel speedup on real curves, replacing the plan's
  computed Amdahl bound with a measurement.
- `benchmarks/tls_multiprocessing_benchmark.py` -- the reusable, re-runnable
  harness (acquire / bench / nested / report).
- `benchmarks/results/p05a_tls_benchmark.json` -- raw measured data.
- `benchmarks/results/p05a_tls_benchmark.md` -- the written result, with the
  unlock recommendation derived from the numbers.
- A proven nested-pool mechanism verdict: `daemon=True` cannot create the
  `multiprocessing.Pool` TLS parallelism needs; `daemon=False` can. The
  unlock premise is confirmed on the real Kepler-90 call stack, not assumed
  from a comment.
- A correction to a plan figure: the "~149.7 s on Kepler-90 defaults" number
  in PRD v4.1 / `scratch/j2c_tls_profiling_result.json` was measured under
  `A_default_full` with `period_min=200.08, period_max=221.14` -- the
  BLS-narrowed 828-period window, NOT TLS defaults.

CONSUMED BY:
- P1-F (Worker / IPC architecture) -- the redesign is scoped from these
  numbers.
- P4-G (TLS multiprocessing unlock landing) -- the unlock decision and its
  feature flag.

NEW CONTRACTS:
- `tests/characterize/test_tls_call_path_contract.py` gains a P05-A section
  requiring (a) the harness to be committed, (b) the result JSON to carry a
  measured serial baseline and a measured parallel speedup, and (c) the
  nested-pool mechanism verdict to be resolved. The numeric values are
  deliberately NOT pinned; a re-run on other hardware must be able to
  replace them.

FILES OF INTEREST:
- benchmarks/tls_multiprocessing_benchmark.py
- benchmarks/results/p05a_tls_benchmark.json
- benchmarks/results/p05a_tls_benchmark.md
- benchmarks/README.md
- benchmarks/results/P05A_HANDOFF.md
- tests/characterize/test_tls_call_path_contract.py (P05-A section appended)
- astraeus/analysis/detection.py (call-site comment corrected to point at
  the measured benchmark; the `use_threads=1` lock itself is unchanged)
- .gitignore (`/benchmarks/cache/*` -- input curves are regenerable; the
  measured results are the tracked artifact)
- docs/EXECUTION_BUCKETS.md (P05-A marked COMPLETE)

KNOWN CONSTRAINTS:
- The unlock does NOT deliver the projected 6-8x. Measured speedup at
  `use_threads=cpu_count()` (8 cores) on the production BLS-narrowed window
  ranges 1.06x-2.08x across targets (geometric mean 1.53x, i.e. 19% of the
  ideal Amdahl bound), and the 1->2-thread arm on Kepler-11 is *slower* than
  serial (0.82x). Pool startup and uneven period-grid partitioning dominate
  at these grid sizes; scaling is non-monotonic in thread count on several
  targets.
- Numerical equivalence holds: serial and parallel arms return bit-identical
  SDE / FAP / period on all 24 measured arms (max |dSDE| = 0, max |dperiod| =
  0), so the unlock is a performance change, not a scientific one. That
  equivalence must be re-confirmed on the deployment platform before P4-G
  lands.
- Platform scope: this measurement was taken on Windows (spawn start
  method). PRD v4.1 scopes the benchmark to Linux. The nested-pool behaviour
  is start-method dependent, so the definitive production number must be
  re-measured on the Linux deployment target before the unlock ships. The
  workload-level speedup is expected to transfer; the daemon constraint must
  be re-confirmed.
- TLS defaults (no period bounds) is impractical on long baselines: the
  Kepler-90 defaults arm exceeded a 900 s single-threaded budget and was
  terminated. This is why production narrows the window via BLS first; it is
  a finding, not a gap in the measurement.
- The 8 cached input curves are NOT committed (`benchmarks/cache/*` is
  gitignored). They are regenerable via
  `py benchmarks/tls_multiprocessing_benchmark.py acquire`.

NEXT REQUIRED ACTION:
- P1-F may now scope the worker/IPC redesign (`Process`->`Popen`,
  Queue->JSONL) from the measured numbers rather than from the projected
  6-8x. The unlock itself lands only as P4-G, behind a feature flag, after
  the benchmark is re-run on Linux and the numerical equivalence is
  re-confirmed there.
