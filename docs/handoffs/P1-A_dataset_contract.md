BUCKET: P1-A
STATUS: COMPLETE

PROVIDES:
- `astraeus/contracts/dataset.py` — the canonical `Dataset` contract: one
  authoritative typed boundary for light-curve arrays across both ingestion
  stacks and both search pipelines (PRD §8.1: previously seven
  representations, no canonical type).
- Content-addressed identity: the hash covers the ARRAYS, not metadata
  (PRD §5), which is what makes `dataset_id` a safe foreign key.
- `ArtifactStore` — content-addressed persistence for arrays and JSON
  documents, atomic (tmp + `os.replace`), self-describing; copies the
  `simulation/completeness.py` pattern verbatim in spirit.
- `from_arrays` / `from_dict` / `from_light_curve_data` constructors; a
  zero-only error column is read as ABSENT, never trusted (PRD §5).

CONSUMED BY:
- P1-B (AnalysisResult carries `dataset_id`)
- P1-C (provenance references the dataset)
- P1-G (real data canonicalized onto the seam)
- P1-H (the API layer builds a `Dataset` at the boundary)
- P2-A (vertical slice backend)

NEW CONTRACTS:
- `Dataset`, `TargetRef`, `Mission`, `TimeUnit`, `ArtifactRef`, `ArtifactStore`

FILES OF INTEREST:
- astraeus/contracts/dataset.py
- astraeus/contracts/__init__.py
- tests/contracts/test_contracts.py

KNOWN CONSTRAINTS:
- Hashes must cover arrays, not metadata (PRD §5) — the array-hash
  collision was the defect this contract exists to fix.
- Atomic writes follow the completeness-subsystem pattern.
- `from_arrays(sort=True)` validates only after sorting, so the
  canonicalize escape hatch is usable (fixed during implementation: the
  original ordering validated before sorting).

NEXT REQUIRED ACTION:
- P1-B may now reference `dataset_id`.
