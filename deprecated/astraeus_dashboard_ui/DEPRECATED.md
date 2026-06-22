# DEPRECATED — six `astraeus/dashboard/ui/` panels

**Deprecated:** 2026-06-22 (Bucket 1 — orphan cleanup)
**Moved from:** `astraeus/dashboard/ui/{sidebar,simulation_panel,data_ingestion_panel,mcmc_panel,action_deck,mcmc_form}.py`
**Moved to:** `deprecated/astraeus_dashboard_ui/{sidebar,simulation_panel,data_ingestion_panel,mcmc_panel,action_deck,mcmc_form}.py`

## Why they are dead

These six modules formed a **self-referential dead cluster** with no path to the
live UI. A repo-wide import trace (see
[`reports/bucket1_orphan_investigation.md`](../../reports/bucket1_orphan_investigation.md),
§1 and §4) proved:

| Module | Its only importer(s) | Live replacement |
|---|---|---|
| `sidebar.py` | *(none — zero importers anywhere)* | `astraeus/dashboard/ui/layout.py::render_left_nav` (imported by `app.py`) |
| `simulation_panel.py` | *(none)* | `ui/pages/simulator.py` (via `route.py`) |
| `data_ingestion_panel.py` | *(none — root of the dead cluster)* | ingestion happens via `astraeus/core/ingestion.py::RemoteDiscoveryEngine.fetch_data` in `ui/pages/detective.py` |
| `mcmc_panel.py` | `data_ingestion_panel.py` (also dead) | *(no live MCMC UI exists)* |
| `action_deck.py` | `mcmc_panel.py` (also dead) | *(no live export-deck UI exists)* |
| `mcmc_form.py` | `mcmc_panel.py` (also dead) | *(no live MCMC form exists)*

No live path (`app.py`, `route.py`, `ui/pages/`, or any still-live
`astraeus/dashboard/` module) imported any of these. Their exported symbols
(`render_app_sidebar`, `render_simulation_panel`, `render_data_ingestion_panel`,
`render_mcmc_analysis_panel`, `render_action_deck`, `render_mcmc_config_form`,
etc.) had zero importers outside the cluster itself. The live sidebar nav lives
in `layout.py`; the live simulation / ingestion UIs live in `ui/pages/`.

## What still IS live in `astraeus/dashboard/ui/`

After this deprecation, `astraeus/dashboard/ui/` contains only the **live**
modules:

- `layout.py` — `workbench_layout`, `render_left_nav` (imported by `app.py`)
- `styles.py` — `inject_page_styles` (imported by `app.py`)
- `components.py` — `render_floating_chat` (imported by `app.py`)
- `settings.py` — `render_settings_panel` (imported by `ui/pages/settings.py`)
- `__init__.py`

## Note on internal cross-imports

The moved files still contain `from astraeus.dashboard.ui.<other-panel> import ...`
references to one another. These are **expected and intentional**: the files are
deprecated (not on any import path), so the cross-imports simply mean "if you
un-deprecate and move them back as a set, they will work again." No live import
can reach them, so these references never execute.

## Deferred dependencies (NOT moved in this bucket)

These panels depended on `astraeus/dashboard/services/*`
(`data_ingestion.py`, `mcmc_retrieval.py`, `action_deck.py`). After this
deprecation those services have no live importers either, but they are
**dependencies of** the orphan panels rather than named targets of this bucket,
and the bucket's hard constraints forbid broadening scope. They are flagged in
`reports/bucket1_orphan_investigation.md` §5 for a later explicit cleanup step
and were **not** touched here.

## Not deleted — moved

Per the bucket's hard constraint, dead code is **deprecated, not deleted**, in
this pass. Files are preserved here verbatim (git history intact via `git mv`).
Actual deletion is a separate, explicit decision for a later cleanup step — see
`reports/bucket1_summary.md`.

## To restore

```bash
git checkout <commit-before-deprecation> -- astraeus/dashboard/ui/sidebar.py \
    astraeus/dashboard/ui/simulation_panel.py \
    astraeus/dashboard/ui/data_ingestion_panel.py \
    astraeus/dashboard/ui/mcmc_panel.py \
    astraeus/dashboard/ui/action_deck.py \
    astraeus/dashboard/ui/mcmc_form.py
```
