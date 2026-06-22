# Bucket 1 — Summary Report

**Branch:** `refactor/orphan-cleanup-and-rde-rename`
**Date:** 2026-06-22

---

## What was found

Phase 1 discovery (`reports/bucket1_orphan_investigation.md`) confirmed all
targets by reading import statements directly across the whole repo:

### Orphaned modules

| Module | Verdict | Confidence | Only importer(s) |
|---|---|---|---|
| `astraeus/ui/dashboard.py` (+ entire `astraeus/ui/` package) | CONFIRMED DEAD | High | `tests/test_chaos_integration_suite.py` (standalone, non-pytest script) |
| `astraeus/dashboard/ui/sidebar.py` | CONFIRMED DEAD | High | *(none)* |
| `astraeus/dashboard/ui/simulation_panel.py` | CONFIRMED DEAD | High | *(none)* |
| `astraeus/dashboard/ui/data_ingestion_panel.py` | CONFIRMED DEAD | High | *(none)* — root of dead cluster |
| `astraeus/dashboard/ui/mcmc_panel.py` | CONFIRMED DEAD (transitive) | High | only by dead `data_ingestion_panel.py` |
| `astraeus/dashboard/ui/action_deck.py` | CONFIRMED DEAD (transitive) | High | only by dead `mcmc_panel.py` |
| `astraeus/dashboard/ui/mcmc_form.py` | CONFIRMED DEAD (transitive) | High | only by dead `mcmc_panel.py` |

### NOT orphans (still live)

- `astraeus/dashboard/ui/{layout,styles,components}.py` — imported by `app.py`
- `astraeus/dashboard/ui/settings.py` — imported by `ui/pages/settings.py`
- `astraeus/dashboard/{figures,simulation,scenario,validation}.py` — shared libs imported by live pages

### RemoteDiscoveryEngine collision

Two classes shared the name `RemoteDiscoveryEngine`:

| | RDE #1 (`core/ingestion.py:24`) | RDE #2 (`data/discovery.py:8`) |
|---|---|---|
| Role | NASA Archive + MAST facade (Streamlit-aware) | astroquery + lightkurve direct |
| Caching | `fetch_data` wraps `_fetch_data_impl` in `@st.cache_data` (lazy, `ingestion.py:217`) | none |
| Headless support | `_fetch_data_impl` is Streamlit-free staticmethod (`ingestion.py:158`) — all stress scripts call this directly | all methods are Streamlit-free, but no headless importer existed |
| Live importer | `ui/pages/detective.py:10`, 4 stress scripts, `test_ingest.py` | `astraeus/data/__init__.py` re-export only, `tests/test_discovery.py` |
| Last commit | 2026-06-22 (today — actively maintained) | 2026-06-02 (3 weeks stale) |

**Resolution:** Option (b) — deprecate RDE #2. The headless-context analysis
proved RDE #1 already covers both UI (cached `fetch_data`) and headless
(uncached `_fetch_data_impl`) contexts, so no second class is needed. RDE #2
had zero live importers and was redundant.

---

## What was changed

### Commit A — `56800d0` — Deprecate `astraeus/ui/dashboard.py`

| Before | After |
|---|---|
| `astraeus/ui/__init__.py` | `deprecated/astraeus_ui_dashboard/__init__.py` |
| `astraeus/ui/dashboard.py` | `deprecated/astraeus_ui_dashboard/dashboard.py` |
| *(new)* | `deprecated/astraeus_ui_dashboard/DEPRECATED.md` |
| `tests/test_chaos_integration_suite.py` — imported `astraeus.ui.dashboard` | Re-pointed to `app` (identical `BASELINE_PAYLOAD` + `_build_adapted_metrics_payload`) |

### Commit B — `314aa4a` — Deprecate 6 dead dashboard/ui panels

| Before | After |
|---|---|
| `astraeus/dashboard/ui/sidebar.py` | `deprecated/astraeus_dashboard_ui/sidebar.py` |
| `astraeus/dashboard/ui/simulation_panel.py` | `deprecated/astraeus_dashboard_ui/simulation_panel.py` |
| `astraeus/dashboard/ui/data_ingestion_panel.py` | `deprecated/astraeus_dashboard_ui/data_ingestion_panel.py` |
| `astraeus/dashboard/ui/mcmc_panel.py` | `deprecated/astraeus_dashboard_ui/mcmc_panel.py` |
| `astraeus/dashboard/ui/action_deck.py` | `deprecated/astraeus_dashboard_ui/action_deck.py` |
| `astraeus/dashboard/ui/mcmc_form.py` | `deprecated/astraeus_dashboard_ui/mcmc_form.py` |
| *(new)* | `deprecated/astraeus_dashboard_ui/DEPRECATED.md` |

`astraeus/dashboard/ui/` now contains only the 4 live modules + `__init__.py`.

### Commit C — `e08004e` — Deprecate RDE #2 and resolve name collision

| Before | After |
|---|---|
| `astraeus/data/discovery.py` | `deprecated/astraeus_data_discovery/discovery.py` |
| `tests/test_discovery.py` | `deprecated/astraeus_data_discovery/test_discovery.py` (skip-marked) |
| `astraeus/data/__init__.py` — re-exported RDE #2 | RDE re-export removed (with inline note) |
| `pytest.ini` — no addopts | `addopts = --ignore=deprecated` |
| *(new)* | `deprecated/astraeus_data_discovery/DEPRECATED.md` |

The survivor (`core/ingestion.py::RemoteDiscoveryEngine`) kept its name unchanged.

### Commit D — `4b9f4bc` — Add architecture doc

| New file | Content |
|---|---|
| `docs/ARCHITECTURE.md` | Live launch path diagram, shared library inventory, data layer (one engine, two call styles), analysis pipeline call order with file:line refs, quick-reference table, verification commands |

---

## What was tested and how

| Gate | Command | Result |
|---|---|---|
| Phase 0 baseline | `python -m pytest tests/ -v > reports/bucket1_pretest_baseline.txt` | 53 passed, 10 failed (all pre-existing) |
| Commit A regression | `python -m pytest tests/ -v` | 53 passed, 10 failed — failure set diff vs baseline: **EMPTY** |
| Commit B regression | `python -m pytest tests/ -v` | 53 passed, 10 failed — failure set diff vs baseline: **EMPTY** |
| Commit C regression | `python -m pytest tests/ -v` | 50 passed, 10 failed — failure set diff vs baseline: **EMPTY**. The 3-pass decrease is exactly the 3 relocated `test_discovery.py` tests (now SKIPPED in `deprecated/`, not counted in `tests/` gate). No previously-passing test regressed. |
| Phase 4 post-test | `python -m pytest tests/ -v > reports/bucket1_posttest.txt` | 50 passed, 10 failed — identical to Commit C result |
| Relocated test skip | `python -m pytest deprecated/astraeus_data_discovery/test_discovery.py -v` | 3 skipped (collection-safe, no import error) |
| Static import check | `python -c "from astraeus.core.ingestion import RemoteDiscoveryEngine, DataAdapter"` | OK |
| Static no-collision | `python -c "from astraeus.data import RemoteDiscoveryEngine"` | ImportError (expected — RDE re-export removed) |
| Interactive launch | `streamlit run app.py` | **Cannot verify in this sandbox** (stated explicitly per Phase 4.2) |

All 10 failures are pre-existing (7 Streamlit `DeltaGeneratorSingleton` test-isolation errors, 3 unrelated benchmark/detector assertion failures). They have not changed across any commit.

---

## What remains uncertain or deferred

| Item | Status | Notes |
|---|---|---|
| `astraeus/dashboard/services/*` (`data_ingestion.py`, `mcmc_retrieval.py`, `action_deck.py`) | **DEFERRED** | After Phase 2, these have no live importers (they were imported only by the deprecated panels and by the deprecated RDE #2). They are dependencies *of* deprecated code, not named targets of this bucket, and the hard constraints forbid broadening scope. Flagged for a later explicit cleanup. See `reports/bucket1_orphan_investigation.md` §5. |
| `MODULE_REFERENCE.md` stale entry points | **DEFERRED** | `MODULE_REFERENCE.md:636,851` still claim `streamlit run astraeus/ui/dashboard.py` as the entry. `docs/ARCHITECTURE.md` documents the truth; correcting `MODULE_REFERENCE.md` itself is a doc-only follow-up. |
| `deprecated/` actual deletion | **DEFERRED** | Per the bucket's hard constraint, nothing is deleted — only moved + documented. Actual deletion of the `deprecated/` tree is a separate, explicit decision for the user after reviewing this report. |
| Interactive Streamlit launch verification | **NOT POSSIBLE** | `streamlit run app.py` cannot be executed in this sandbox. The static verification (AST parse + import chain) passed. The user should run it manually to confirm. |

---

## Exact commands to verify the result

```bash
# 1. Switch to the bucket branch
git checkout refactor/orphan-cleanup-and-rde-rename

# 2. Run the test suite (should show 50 passed, 10 failed — identical to posttest)
python -m pytest tests/ -v

# 3. Confirm the 10 failures are the same pre-existing set
diff <(grep "^FAILED" reports/bucket1_pretest_baseline.txt) <(grep "^FAILED" reports/bucket1_posttest.txt)
# Expected output: empty (no differences)

# 4. Confirm the relocated tests skip cleanly
python -m pytest deprecated/astraeus_data_discovery/test_discovery.py -v --override-ini="addopts="
# Expected: 3 skipped

# 5. Confirm the live entry point parses and imports resolve
python -c "
from astraeus.core.ingestion import RemoteDiscoveryEngine, DataAdapter
from astraeus.data import DataAdapter
from app import BASELINE_PAYLOAD, _build_adapted_metrics_payload
print('All live imports OK')
"

# 6. Confirm the deprecated RDE is no longer importable from its old path
python -c "from astraeus.data import RemoteDiscoveryEngine" 2>&1
# Expected: ImportError (by design)

# 7. Interactive verification (requires a Streamlit-capable terminal)
streamlit run app.py
# Expected: launches the 6-tab dashboard with sidebar navigation
```

---

## Git log of bucket commits (newest first)

```
4b9f4bc docs(bucket1): add docs/ARCHITECTURE.md (Phase 3)
e08004e refactor(bucket1): deprecate RDE #2 data/discovery.py, resolve name collision
314aa4a refactor(bucket1): deprecate 6 dead dashboard/ui panels (orphans 2-7)
56800d0 refactor(bucket1): deprecate astraeus/ui/dashboard.py (orphan 1)
5622a5d docs(bucket1): add pretest baseline and Phase 1 orphan investigation
```
