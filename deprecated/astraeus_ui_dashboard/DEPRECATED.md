# DEPRECATED — `astraeus/ui/dashboard.py`

**Deprecated:** 2026-06-22 (Bucket 1 — orphan cleanup)
**Moved from:** `astraeus/ui/dashboard.py` (the entire `astraeus/ui/` package)
**Moved to:** `deprecated/astraeus_ui_dashboard/dashboard.py`

## Why it is dead

`astraeus/ui/dashboard.py` was an **older parallel copy** of what `app.py` now
does inline. Both define the same symbols — `BASELINE_PAYLOAD`,
`_build_adapted_metrics_payload`, `_check_headless_prerequisites`,
`_initialize_session_state`, `main` — with functionally identical bodies. The
live Streamlit application is launched via:

```
streamlit run app.py
```

and its "Discover" tab (rendered inline in `app.py:192-292`) supersedes
`astraeus/ui/dashboard.py`'s `main()` wholesale.

A repo-wide import trace (see
[`reports/bucket1_orphan_investigation.md`](../../reports/bucket1_orphan_investigation.md),
§1 and §4) found that `astraeus.ui.dashboard` was imported by **exactly one**
file — `tests/test_chaos_integration_suite.py` — and that file is a standalone
script (0 pytest-collectable `def test_` functions), so it was never part of the
pytest run. No live path (`app.py`, `route.py`, `ui/pages/`, or any still-live
`astraeus/dashboard/` module) imported `astraeus.ui.*` at all.

## What replaced it

`app.py` (project root). The two symbols the one remaining importer actually
needed — `BASELINE_PAYLOAD` and `_build_adapted_metrics_payload` — exist
identically in `app.py` (lines 26 and 153 respectively), so the importer was
re-pointed at `app` rather than losing test history.

## Not deleted — moved

Per the bucket's hard constraint, dead code is **deprecated, not deleted**, in
this pass. The file is preserved here verbatim (git history intact via
`git mv`). Actual deletion is a separate, explicit decision for a later cleanup
step — see `reports/bucket1_summary.md`.

## To restore

```bash
git checkout <commit-before-deprecation> -- astraeus/ui/dashboard.py astraeus/ui/__init__.py
```
