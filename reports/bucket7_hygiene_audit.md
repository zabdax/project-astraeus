# Bucket 7 — Repo Root Hygiene Audit

**Date:** 2026-06-22
**Branch:** `chore/root-hygiene` (off `v.0.0.2`)
**Bucket scope:** relocate orphan files from the repo root to clearly-named folders; untrack regenerable artifacts via `.gitignore`. **Nothing is deleted** — every file is either `git mv`'d (preserves history) or `git rm --cached`'d (untracked, working copy left on disk).

---

## 1. Repo root inventory

### The real product (untouched)
Every entry below is part of the live product and is **out of scope** for this bucket. Verified present.

| Path | Bytes | Note |
|---|---|---|
| `app.py` | 13 126 | Streamlit entry point. Imported by `tests/test_chaos_integration_suite.py` (`BASELINE_PAYLOAD`, `_build_adapted_metrics_payload`). |
| `route.py` | 825 | Streamlit route dispatcher. Imported by `app.py:15` (`from route import render_route`). |
| `astraeus/` | (dir) | Production package. Untouched. |
| `astraeus.md` | 1 150 | ASCII banner; referenced by `PRD.md`. |
| `ui/` | (dir) | Live Streamlit pages. Untouched. |
| `tests/` | (dir) | Pytest test suite. Untouched. |
| `runs/` | (dir) | Reproducible run scripts (`kepler90_blind_search.py`). Untouched. |
| `config.json` | 177 | LLM provider config. Untouched. |
| `requirements.txt` | 161 | 9 pinned runtime deps, including `streamlit==1.41.1`. |
| `pytest.ini` | 350 | Pytest config; registers `smoke` marker; `--ignore=deprecated`. **Preserved.** |
| `README.md` | 16 608 | Project README. |
| `PRD.md` | 8 048 | v1 PRD. |
| `prd_v2.md` | 7 997 | v2 PRD ("Master PRD"). |
| `AGENTS.md` | 2 174 | CodeGenome MCP instructions for AI agents. |
| `LICENSE` | 1 097 | MIT. |
| `.gitignore` | 899 | Existing ignore rules. Will be appended-to, not replaced. |
| `.github/` | (dir) | Only `copilot-instructions.md`; no `workflows/` (no CI). |
| `docs/` | (dir) | `ARCHITECTURE.md` + `astraeus_agent_implementation_briefs.md`. |
| `logs/` | (dir) | Runtime logs (`experiments.json`, `research_log.md`). |
| `outputs/` | (dir) | Runtime artifacts (plots, discovery JSONs). |
| `reports/` | (dir) | Bucket diagnostic reports. |
| `deprecated/` | (dir) | Bucket 1 dead-code archive. Has `--ignore=deprecated` rule. |
| `dev-knowledge-base/` | (dir) | Empty, already ignored. |
| `.windsurfrules` | 2 323 | Windsurf agent rules. |

### Hidden dirs (already correctly ignored / untracked)
`.git/`, `.cursor/`, `.genome/`, `.pytest_cache/`, `__pycache__/` — all correctly excluded via existing rules.

### Orphan files in scope (26 total)

For each file: **size** (bytes), **tracked in git?**, **inbound refs from live product tree?** (per grep across `app.py`, `route.py`, `config.json`, `astraeus/`, `ui/`, `tests/`, `runs/`), **disposition**.

#### Group A — relocate to `scratch/` (7 files)
Ad-hoc / one-shot / wrong-path scripts and their data outputs. All confirmed to be regenerable.

| File | Bytes | Tracked? | Inbound refs | Disposition |
|---|---:|---|---|---|
| `extract.py` | 1 081 | yes | 0 | `git mv` → `scratch/` |
| `extracted_output.txt` | 3 270 128 | yes | 0 | `git mv` → `scratch/` (regenerable; produced by `extract.py`) |
| `extracted_utf8.txt` | 1 635 061 | yes | 0 | `git mv` → `scratch/` (regenerable; produced by `extract.py`) |
| `final_payload.json` | 1 689 | yes | 0 | `git mv` → `scratch/` (regenerable; output of `extract.py`) |
| `find_cycles.py` | 2 915 | yes | 0 | `git mv` → `scratch/` (hard-codes `d:\GITHUB\OP\project-astraeus` — wrong-path dev tool) |
| `init_project.py` | 2 963 | yes | 0 | `git mv` → `scratch/` (original scaffold; superseded by real tree) |
| `scratch_batman.py` | 640 | yes | 0 | `git mv` → `scratch/` (batman-package smoke test; prints at import time) |

#### Group B — relocate to `tools/diagnostics/` (4 files)
Reusable diagnostic scripts and pytest wrappers.

| File | Bytes | Tracked? | Inbound refs | Disposition |
|---|---:|---|---|---|
| `test_exoplanet_ui_debug.py` | 8 955 | yes | 0 | `git mv` → `tools/diagnostics/` (Streamlit AppTest harness) |
| `ultimate_stress_test.py` | 72 677 | yes | 0 | `git mv` → `tools/diagnostics/` (71 KB full-platform verification suite) |
| `run_my_tests.py` | 127 | yes | 0 | `git mv` → `tools/diagnostics/` (`pytest.main(['-v'])` wrapper) |
| `run_pipeline_test.py` | 165 | yes | 0 | `git mv` → `tools/diagnostics/` (`tests/pipeline_stress_test.py` wrapper) |

#### Group C — relocate to `scripts/manual_tests/` (6 files)
Manual test scripts whose pytest conversion is **Bucket 5's job**. **Relocated only, NOT converted in this bucket.**

| File | Bytes | Tracked? | Inbound refs | Disposition |
|---|---:|---|---|---|
| `run_test.py` | 2 490 | yes | 0 | `git mv` → `scripts/manual_tests/` (Kepler-90 multi-planet end-to-end driver) |
| `test_engine.py` | 7 900 | yes | 0 | `git mv` → `scripts/manual_tests/` (N-body engine standalone diagnostic) |
| `test_orchestrator.py` | 1 653 | yes | 0 | `git mv` → `scripts/manual_tests/` (Kepler-90 pipeline) |
| `test_ingest.py` | 425 | yes | 0 | `git mv` → `scripts/manual_tests/` (RemoteDiscoveryEngine print-out) |
| `test_fetch.py` | 238 | yes | 0 | `git mv` → `scripts/manual_tests/` (NASA TAP query) |
| `test_nasa.py` | 383 | yes | 0 | `git mv` → `scripts/manual_tests/` (NASAExoplanetArchive fetch test) |

**→ Bucket 5 handoff:** all 6 files above should be picked up from `scripts/manual_tests/` and converted into proper pytest tests under `tests/`.

#### Group D — untrack via `.gitignore` + `git rm --cached` (5 files)
Regenerable artifacts that should never have been committed. Working copies are left on disk; no deletions.

| File | Bytes | Tracked? | Inbound refs | Disposition |
|---|---:|---|---|---|
| `experiments.json` | 29 774 | yes | 0 (only `logs/experiments.json` referenced by `astraeus/analysis/logging.py:8,67`, `tests/test_experiment_history.py:7`) | `git rm --cached` (stale duplicate of `logs/experiments.json`; regenerable from live logs + scripts) |
| `test_orchestrator_log.txt` | 20 550 | yes | 0 | `git rm --cached` (stderr dump from `test_orchestrator.py`; regenerable) |
| `pytest_log.txt` | 304 | yes | 0 | `git rm --cached` (regenerable pytest output) |
| `pytest_output.txt` | 0 | yes | 0 | `git rm --cached` (empty regenerable pytest output) |
| `test3d.html` | 8 743 | yes | 0 | `git rm --cached` (Plotly debug export; sibling of already-ignored `test.html`) |

#### Group E — already correctly handled (no action)
| File | Bytes | Tracked? | Why no action |
|---|---:|---|---|
| `err.log` | 5 245 | no | Covered by existing `*.log` rule. |
| `err2.log` | 5 867 | no | Covered by existing `*.log` rule. |
| `pytest_pipeline.log` | 430 | no | Covered by existing `*.log` rule. |
| `test.html` | 8 633 | no | Covered by existing `test.html` rule. |

---

## 2. Import analysis methodology

Combined regex used against every live-tree target:

```
extract\.py|extracted_output|extracted_utf8|final_payload|find_cycles|init_project|scratch_batman|test_exoplanet_ui_debug|ultimate_stress_test|run_my_tests|run_pipeline_test|run_test|test_engine|test_orchestrator|test_ingest|test_fetch|test_nasa|experiments\.json|test\.html|test3d\.html|pytest_log|pytest_output|pytest_pipeline|err\.log|err2\.log|test_orchestrator_log
```

Targets searched: `app.py`, `route.py`, `config.json`, `astraeus/`, `ui/`, `tests/`, `runs/`.

**Result: ZERO inbound references to any of the 26 orphan files.** The only "hits" are:
- The string `experiments.json` in source code, but always as `logs/experiments.json` (never the root file). See `astraeus/analysis/logging.py:8,67`, `tests/test_experiment_history.py:7`.
- Prose mentions of orphan file names in `docs/ARCHITECTURE.md`, `docs/astraeus_agent_implementation_briefs.md`, `reports/bucket1_*.md` — these document the cleanup task, not actual code references.

**Conclusion:** every move is safe. No downstream import resolution depends on any orphan file's current location.

---

## 3. `.gitignore` gaps identified

Current rules in `F:\solo_leveling_assistant\project-astraeus\.gitignore`:

| Rule | What it catches | Gap |
|---|---|---|
| `*.log` | `err.log`, `err2.log`, `pytest_pipeline.log` | Does not match `*.txt` log dumps |
| `test.html` | `test.html` | Does not match `test3d.html` (sibling) |
| — | — | No rule for root-level `experiments.json` (without affecting `logs/experiments.json`) |
| — | — | No rule for `pytest_log.txt`, `pytest_output.txt`, `test_orchestrator_log.txt` |

### Additions (appended in this bucket)

```gitignore
# --- Bucket 7: untracked regenerable artifacts (root-only) ---
test3d.html
/experiments.json
pytest_log.txt
pytest_output.txt
test_orchestrator_log.txt
```

Notes:
- `/experiments.json` is anchored to the repo root, so it does **not** ignore `logs/experiments.json`.
- Explicit names are preferred over `*_log.txt` globs for clarity of intent. New contributors will see exactly which files were tracked in error.

---

## 4. Out-of-scope observations (flagged, not addressed in this bucket)

These were noticed during discovery but are **explicitly out of scope** for bucket 7. Surfacing them so they aren't forgotten.

1. **`MODULE_REFERENCE.md` is missing.**
   - Referenced by name in `ultimate_stress_test.py:5` ("module reference manual (MODULE_REFERENCE.md)") and in `docs/astraeus_agent_implementation_briefs.md`.
   - Glob `**/MODULE_REFERENCE.md` returns zero matches in the repo.
   - Likely candidates: deleted; never committed; or lives in `dev-knowledge-base/` (which is empty and ignored).
   - **Suggested next step:** separate bucket or one-line user clarification.

2. **`scripts/manual_tests/*.py` lifecycle after Bucket 5.**
   - Once Bucket 5 converts the 6 manual scripts into proper pytest tests, the originals may be deletable.
   - Per the global ground rule ("never delete code — deprecate it"), they should move to `deprecated/` or be marked with a dated note at that point.

3. **No CI workflows.**
   - `.github/` contains only `copilot-instructions.md`; no `workflows/`.
   - Documented as "no CI" in `docs/astraeus_agent_implementation_briefs.md:990`.
   - Not addressed here — separate concern.

4. **`prd_v2.md` is a separate document from `PRD.md`.**
   - Both are tracked. The v2 is the "Master PRD" but v1 is also retained.
   - Not addressed here — they may serve different audiences or historical purposes.

---

## 5. Bucket 7 commit plan (final)

| # | Commit message | Action |
|---|---|---|
| 1 | `docs(bucket7): add Phase 1 hygiene audit` | Add this file. |
| 2 | `chore(bucket7): relocate ad-hoc scripts to scratch/` | `git mv` 7 files + create `scratch/README.md`. |
| 3 | `chore(bucket7): relocate reusable diagnostics to tools/diagnostics/` | `git mv` 4 files + create `tools/README.md` + `tools/diagnostics/README.md`. |
| 4 | `chore(bucket7): relocate manual test scripts to scripts/manual_tests/ for bucket5 pickup` | `git mv` 6 files + create `scripts/README.md` + `scripts/manual_tests/README.md`. |
| 5 | `chore(bucket7): untrack regenerable artifacts via .gitignore` | Append `.gitignore` section + `git rm --cached` 5 files. |
| 6 | `docs(bucket7): add Phase 3 posttest and summary report` | Capture `reports/bucket7_posttest.txt`, write `reports/bucket7_summary.md`, update this audit with verification results. |

---

## 6. Files-affected tally (final)

- 17 files `git mv`'d (preserving history)
- 5 files `git rm --cached` (untracked, left on disk)
- 1 file edited (`.gitignore`)
- 5 README.md files created (`scratch/`, `tools/`, `tools/diagnostics/`, `scripts/`, `scripts/manual_tests/`)
- 3 reports/*.md files created (`bucket7_hygiene_audit.md`, `bucket7_summary.md`, audit update)
- 2 reports/*.txt files created (`bucket7_pretest_baseline.txt`, `bucket7_posttest.txt`)
- 1 branch created (`chore/root-hygiene`)
- 6 commits total
- **0 deletions**

---

## 7. Hard constraints — reasserted

- ✅ **NOTHING deleted.** Only `git mv` (preserves history) or `git rm --cached` (untracks, leaves on disk).
- ✅ **Real product untouched.** All entries in §1.1 left exactly where they were.
- ✅ **`astraeus/ui/` NOT touched** (Bucket 1's orphan).
- ✅ **Manual tests NOT converted** (Bucket 5's job — relocated with handoff README).
- ✅ **Each commit is small and revertible.**
- ✅ **Reports follow bucket naming convention.**
- ✅ **No silent fallbacks.** Every deferred item in §4 explicitly flagged.

---

## 8. Verification commands

```bash
# Clean tree
git status

# Tests still pass at baseline
python -m pytest tests/ -v

# App entry point still resolves
python -c "from app import BASELINE_PAYLOAD, _build_adapted_metrics_payload; from route import render_route; print('imports ok')"

# Streamlit launches (static check at minimum)
streamlit run app.py --server.headless true

# Compare pretest vs posttest failure sets (must be byte-identical)
diff <(grep -E "FAILED|PASSED" reports/bucket7_pretest_baseline.txt | sort) \
     <(grep -E "FAILED|PASSED" reports/bucket7_posttest.txt | sort)
```