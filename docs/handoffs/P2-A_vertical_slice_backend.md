BUCKET: P2-A
STATUS: COMPLETE

PROVIDES:
- The first real-data end-to-end proof of the Phase 1 architecture
  (PRD §21 Phase 2 gate): the cached Kepler-90 curve (45,853 real points,
  1240 d baseline, network-free) driven API → supervisor → worker
  subprocess → engine, reaching COMPLETED with provenance attached.
- `tests/test_p2a_vertical_slice.py` (slow-marked, weekly gate): asserts
  dataset identity, candidate list, provenance with capability snapshot,
  an honest run-level TLS roll-up, and exactly-one-`done` event trail.
- Rejected-peak TLS honesty fix: every examined peak's TLS assessment is
  now a `progress` event (`orchestrator.py`), accumulated by the worker
  and folded into the run-level `TlsSummary` via the new
  `from_legacy_run(..., examined_tls_outcomes=...)` parameter — no
  candidate entries created, fully backwards-compatible.

CONSUMED BY:
- P2-B (minimal honest UI over this slice)

MEASURED (not projected):
- Kepler-90 first peak: BLS P=616.4 d, SNR=16.37 (spurious long-period
  peak, R8 family) → TLS RAN and rejected (`ran_fail`, SDE=4.34 < 5.0)
  → vetting "Likely Planet" correctly gated to `is_candidate=False`
  by the R8 emission rule. Fail-closed chain verified on real data.
- Slice runtime: ~107 s wall (BLS grid + serial TLS, max_signals=1).
- Before the fix the same run recorded `tls.attempted=False` (rejected
  peak's dict discarded); after: `attempted=True, n_ran_fail=1`.

FILES OF INTEREST:
- tests/test_p2a_vertical_slice.py
- astraeus/core/orchestrator.py  (`progress` assessment emit)
- astraeus/jobs/worker.py        (examined-TLS accumulation)
- astraeus/contracts/analysis_result.py  (`examined_tls_outcomes` param)

KNOWN CONSTRAINTS:
- The `progress` event is extended in meaning (peak assessment), not in
  schema; the P1-F vocabulary set is unchanged.
- The legacy Streamlit `_subprocess_search_worker` path drops `progress`
  events (unchanged behaviour, out of scope until P3).
- Zero-candidate COMPLETED runs now state TLS truthfully instead of
  "attempted: False".
- `benchmarks/cache/*.npz` stays the offline real-data source; the API
  `target`-fetch path still needs network and is not exercised here.

NEXT REQUIRED ACTION:
- P2-B may build the minimal honest UI on this slice.
