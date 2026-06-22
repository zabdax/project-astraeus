# tools/diagnostics/

Reusable diagnostic scripts and stress-test runners. Moved here by **bucket 7** (chore/root-hygiene) from the repo root, where they were masquerading as project files. None of them is imported by the live product tree (`app.py`, `route.py`, `astraeus/`, `ui/`, `tests/`, `runs/`).

## What's here

| File | Origin | Purpose |
|---|---|---|
| `test_exoplanet_ui_debug.py` | root | Streamlit `AppTest` harness for the UI (telemetry-heavy, prints to stdout). Asserts no unhandled exceptions on app boot, exercises search box, target fetching, and Detective page navigation. |
| `ultimate_stress_test.py` (71 KB) | root | Full-platform end-to-end verification suite. Wraps every module in independent try-except blocks; reports `RECOVERED` on graceful failure, exits 0 on success. References the (missing) `MODULE_REFERENCE.md` in its docstring. |
| `run_my_tests.py` | root | Minimal pytest wrapper: runs `pytest -v` and captures all output to `pytest_log.txt` at the repo root. |
| `run_pipeline_test.py` | root | Minimal pytest wrapper: runs `tests/pipeline_stress_test.py` and captures output to `pytest_pipeline.log` at the repo root. |

## How to use

These are intended for ad-hoc operational verification — running them does not feed back into the live product. They are NOT part of `tests/` and are NOT collected by `python -m pytest tests/`.

If you need to run a stress test, navigate to the repo root first (some scripts hard-code relative paths like `pytest_log.txt`).

## See also

- `reports/bucket7_hygiene_audit.md` — full audit, file-by-file rationale, import analysis.
- `reports/bucket7_summary.md` — what changed, what was tested, what remains uncertain.
