BUCKET: P1-C
STATUS: COMPLETE

PROVIDES:
- `astraeus/contracts/provenance.py` — the provenance record that makes a
  run reconstructible from its own record (PRD §7): effective config,
  capability snapshot, dataset identity, and timing, captured BEFORE the
  search so a crash still leaves a record of what was about to run.
- `EffectiveConfig` — `snr_floor` and `max_signals` are reconstructible
  from the record (PRD §7: not possible in `JOB_REGISTRY` today).
- `capture_provenance` + `.save(store)` — content-addressed provenance
  artifacts.

CONSUMED BY:
- P1-H (every API result must carry provenance, PRD §5)
- P2-A, P3-B

NEW CONTRACTS:
- `Provenance`, `EffectiveConfig`

FILES OF INTEREST:
- astraeus/contracts/provenance.py
- tests/contracts/test_contracts.py

KNOWN CONSTRAINTS:
- Provenance is captured pre-search, so the record describes intent as
  well as outcome.
- The worker attaches provenance to the job row before emitting `done`,
  so a supervisor that dies mid-flight still finds a complete record.

NEXT REQUIRED ACTION:
- P1-H may now serialize provenance in the API layer.
