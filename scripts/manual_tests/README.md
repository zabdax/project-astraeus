# scripts/manual_tests/

Manual test scripts relocated from the repo root by **bucket 7** (chore/root-hygiene). These are **standalone drivers, not pytest tests** — they print to stdout and exit when done. **Bucket 5 is responsible for converting them into proper pytest tests under `tests/`.**

## What's here

| File | Origin | Purpose |
|---|---|---|
| `run_test.py` | root | Kepler-90 (KIC 11442793) multi-planet full-pipeline driver. Phases 1–4: load → search → vet → report. |
| `test_engine.py` | root | N-body core engine diagnostic. Three scenarios: Earth-Sun analog, Kepler-90b high-res, Kepler-90b oversized-Δt (forced blowup). |
| `test_orchestrator.py` | root | Kepler-90 multi-planet search via `run_multi_planet_search`. Writes the consolidated discovery payload to stdout. |
| `test_ingest.py` | root | 14-line `RemoteDiscoveryEngine` print-out. |
| `test_fetch.py` | root | 13-line one-shot NASA TAP query. |
| `test_nasa.py` | root | 8-line `NASAExoplanetArchive` fetch test. |

## Why they're here (not in `tests/`)

These files all live at the root and have names matching pytest's `test_*.py` discovery pattern, but they are **not** pytest functions — they are top-level `print` / `main()` scripts that run as `python <file>.py`. Putting them in `tests/` would cause pytest to attempt to collect them and fail.

## How to run (for now)

```bash
# From the repo root:
python scripts/manual_tests/run_test.py
python scripts/manual_tests/test_engine.py
# etc.
```

Some scripts depend on network access to NASA archives. They print progress to stdout; capture with `>` if needed (note: pytest_log.txt and friends are no longer the canonical capture targets after bucket 7).

## Bucket 5 handoff

**Action for bucket 5:** convert each of these into a proper pytest test under `tests/`. The current pattern is:
- `test_<name>.py` → `tests/test_<name>.py` with pytest functions (`def test_xxx(): ...`)
- `run_test.py` (which is a full pipeline) → likely becomes `tests/test_pipeline_smoke.py` style or multiple focused tests

When conversion is complete, the originals in `scripts/manual_tests/` should be moved to `deprecated/` (per the global "never delete — deprecate" rule), not deleted.

## See also

- `reports/bucket7_hygiene_audit.md` — full audit, file-by-file rationale, import analysis.
- `reports/bucket7_summary.md` — what changed, what was tested, what remains uncertain.
