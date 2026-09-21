BUCKET: P1-B
STATUS: COMPLETE

PROVIDES:
- `astraeus/contracts/analysis_result.py` — the versioned `AnalysisResult`
  v1 schema replacing the ~42-key untyped dict assembled by sequential
  `.update()` in `detection.py` (PRD §6.1).
- The complete legacy alias map (`from_legacy_result_dict`), so the schema
  can be adopted without rewriting the engine (PRD §16: migration, not
  rewrite).
- The **run-level** bridge `from_legacy_run`: ONE `AnalysisResult` per job
  whose `candidates` list holds 0..N entries.  This is the fix for the
  PRD §21 gate's central concern — the legacy machinery emits nothing at
  all on an empty search, leaving "DONE / 0 candidates" indistinguishable
  from a broken pipeline.  A clean zero-candidate run is now a COMPLETED
  result with an empty list, never a job stuck non-terminal.
- `JobStage` / `JobStatus` state model (PRD §5.1) with `is_terminal` /
  `is_live`; `CapabilitySnapshot` adopted unchanged from Phase 0.

CONSUMED BY:
- P1-C (provenance references the result schema)
- P1-E (the store persists `AnalysisResult` and transitions on its status)
- P1-H (the API serializes `AnalysisResult` + provenance)
- P2-A, P3-B, P3-C, P3-G

NEW CONTRACTS:
- `AnalysisResult`, `CandidateEvidence`, `PipelineSummary`, `TlsSummary`,
  `VettingVerdict`, `StructuredWarning`, `JobStage`, `JobStatus`

FILES OF INTEREST:
- astraeus/contracts/analysis_result.py
- tests/contracts/test_contracts.py

KNOWN CONSTRAINTS:
- Frozen models: the bridge builds a candidate once rather than mutating
  after construction.
- The periodogram/TTV blocks must run BEFORE candidate construction
  (ordering bug found and fixed during implementation).
- Legacy keys `duration` (a unit conversion) and `time_unit` (moved to the
  `Dataset` contract) are documented in the alias map rather than silently
  renamed.
- The worker (P1-F) owns the single call site of `from_legacy_run`.

NEXT REQUIRED ACTION:
- P1-C may now reference the result schema; P1-H may serialize it.
