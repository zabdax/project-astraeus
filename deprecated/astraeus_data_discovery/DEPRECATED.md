# DEPRECATED — `astraeus/data/discovery.py::RemoteDiscoveryEngine`

**Deprecated:** 2026-06-22 (Bucket 1 — RemoteDiscoveryEngine disambiguation)
**Moved from:** `astraeus/data/discovery.py`
**Moved to:** `deprecated/astraeus_data_discovery/discovery.py`
**Also moved:** `tests/test_discovery.py` → `deprecated/astraeus_data_discovery/test_discovery.py` (skip-marked)

## Why it is dead — the headless-context finding

This was the **second** of two classes named `RemoteDiscoveryEngine`. The other,
in `astraeus/core/ingestion.py`, is the **live** survivor. Both implemented
NASA-Exoplanet-Archive + MAST/lightkurve ingestion, so the question was whether
each was specialized for a different runtime context (Streamlit vs headless) —
in which case both would be needed — or whether one was simply redundant.

The Phase 1 headless-context analysis (see
[`reports/bucket1_orphan_investigation.md`](../../reports/bucket1_orphan_investigation.md)
§2) settled it:

- The live `astraeus/core/ingestion.py::RemoteDiscoveryEngine` is deliberately
  designed to serve **both** contexts:
  - `_fetch_data_impl` is a plain `@staticmethod` with **no Streamlit** —
    this is the headless entry point that every stress/diagnostic script calls
    directly (`tests/{pipeline,global,solid}*.py`, `trace_download_deadlock.py`).
  - `fetch_data` (attached dynamically, `ingestion.py:224`) wraps
    `_fetch_data_impl` in `@st.cache_data` **lazily inside a function body**, so
    it is only the cached entry for the Streamlit UI (`ui/pages/detective.py`).
- `astraeus/data/discovery.py::RemoteDiscoveryEngine` had **no live importer at
  all** — only a package re-export (`astraeus/data/__init__.py`) and one mocked
  test file. Its own commit message (`b823181`, 2026-06-02, *"Add
  RemoteDiscoveryEngine and UI integration"*) pointed at UI panels that were
  themselves orphans (deprecated in this same bucket). It had not been touched
  in 3 weeks while `core/ingestion.py` was actively maintained (committed
  2026-06-22).

There is therefore **no Streamlit/headless limitation** in the survivor that
would justify keeping a second class. This class is redundant, not
context-specialized.

## Resolution applied (option (b): deprecate one)

- Moved `astraeus/data/discovery.py` → `deprecated/astraeus_data_discovery/discovery.py`.
- Removed the `from astraeus.data.discovery import RemoteDiscoveryEngine`
  re-export from `astraeus/data/__init__.py` (with an inline note explaining
  why it is not restored, to prevent accidentally resurrecting the name
  collision).
- Relocated `tests/test_discovery.py` alongside the module and added a
  module-level `pytestmark = pytest.mark.skip(...)` so its 3 tests are
  preserved for history but never run.
- Added `--ignore=deprecated` to `pytest.ini` so the whole `deprecated/` tree
  is excluded from collection going forward.
- The survivor's name (`RemoteDiscoveryEngine` in `core/ingestion.py`) is
  **unchanged** — with the duplicate gone there is no collision to rename.

## What replaced it

`astraeus/core/ingestion.py::RemoteDiscoveryEngine` — the single source of
truth for both the Streamlit UI path (`fetch_data`, cached) and the headless
pipeline path (`_fetch_data_impl`).

## Hard-constraint compliance

- **No fetch-logic changes:** neither `core/ingestion.py` nor
  `data/discovery.py` had any fetch logic modified. This bucket only resolved
  *which* path is used and deprecated the dead one.
- **No deletion:** the module and its test are moved, not deleted. Actual
  deletion is a separate, explicit decision for a later cleanup step.

## To restore

```bash
git checkout <commit-before-deprecation> -- astraeus/data/discovery.py tests/test_discovery.py
# and revert the astraeus/data/__init__.py + pytest.ini changes in the same commit
```
