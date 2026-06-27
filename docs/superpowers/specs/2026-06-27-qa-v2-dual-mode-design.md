# QA v2 — Dual-mode harness (cached + dynamic) — Design

**Date:** 2026-06-27
**Status:** Approved
**Author:** Zubayer Hasan Shaad (via ZCode / brainstorming skill)

## Motivation

The current QA harness (`scripts/qa_runner.py`) was stuck on TRAPPIST-1/TESS for
hours because the Analyze button never rendered. A previous commit (`494c8b4`)
fixed the underlying ingest defect and made the cache-first fallback work, so
the harness now renders the Analyze button for 8/10 targets.

But there are two issues the v1 harness does not address:

1. **The user wants the harness to actually click Analyze and capture the
   Diagnostic Summary Matrix**, not just verify the button appears. v1's
   `matrix_timeout` is 180s; for multi-planet depth=3 BLS runs that
   routinely take 3-7 minutes, v1 only ever captured post-analyze
   snapshots, never matrix screenshots.

2. **The user wants to verify the "dynamic and generalised" data retrieval**
   path — i.e. that `RemoteDiscoveryEngine.fetch_data()` correctly resolves
   arbitrary target names (Kepler-186, K2-18, WASP-121, etc.) and produces a
   valid time-series. The cache fallback short-circuits this path: if a
   target's TIC/KIC files are already on disk, we never exercise the dynamic
   resolver + MAST/S3 download.

The fix is a new dual-mode harness that:

- Runs the full UI flow including matrix capture (10-min timeout per target).
- Has a backend pre-flight that validates the dynamic ingest path.
- Lets us specify fresh-dynamic targets that bypass the cache so the dynamic
  path gets real exercise.
- Keeps the existing v1 harness untouched as a fallback.

## Approach (chosen)

**A. New file `scripts/qa_runner_v2.py` with a YAML target manifest.**

### Why not edit v1
v1 (`scripts/qa_runner.py`) is committed and working for the cached case.
Editing it would mean mixing two concerns (cached vs dynamic) in one file.
v2 lives alongside v1; nothing else changes.

### Why not pytest
`pytest-playwright` is clean but requires pytest fixtures, dependency on
`pytest`, and a larger refactor. For an end-to-end visual QA harness that
produces screenshots and markdown reports, a standalone script is simpler
and more transparent.

## Architecture

```
scripts/qa_runner_v2.py
├── Manifest loader        (reads scripts/qa_targets.yaml)
├── Phase A: Backend pre-flight (per target, before UI)
│   └── Calls RemoteDiscoveryEngine._fetch_data_impl(target, mission)
│       with ASTRAEUS_FORCE_NETWORK=1 in env → exercises the
│       dynamic MAST path (cache bypassed).
│       Asserts: status == 'success' OR returns clear failure reason.
│       Writes: outputs/qa_v2/<target>_backend.json
├── Phase B: UI flow (per target, after backend)
│   └── Launches fresh Playwright browser context.
│       Navigates to http://localhost:8501.
│       Clicks Detective → types target → selects mission route.
│       Clicks Fetch Target Metadata.
│       Waits for Analyze button (default 180s, configurable).
│       Clicks Analyze.
│       Waits for Diagnostic Summary Matrix (default 600s, configurable).
│       Captures three screenshots:
│         qa_<target>_01_post_fetch.png
│         qa_<target>_02_post_analyze.png
│         qa_<target>_03_matrix.png + DOM + exceptions
└── Reporter
    └── Summarises pass/fail per target with exception text.
        Writes: reports/qa_v2_<mode>_<timestamp>.md
```

## Files added / modified

| File | Action | Purpose |
|---|---|---|
| `scripts/qa_runner_v2.py` | **new** | Dual-mode QA harness |
| `scripts/qa_targets.yaml` | **new** | Target manifest (8 cached + 5 dynamic) |
| `astraeus/core/lightkurve_client.py` | edit | Honour `ASTRAEUS_FORCE_NETWORK` env var in `_try_serve_from_cache` |
| `outputs/ui_tests_v2/` | **new (artifacts)** | Per-target screenshots + DOM + JSON |
| `reports/qa_v2_<mode>_<timestamp>.md` | **new (artifacts)** | Per-run markdown report |
| `scripts/qa_runner.py` | unchanged | v1 stays as fallback |
| `astraeus/core/ingestion.py` | unchanged | `_cached_fetch_data` wrapper stays; v2 calls `_fetch_data_impl` directly |

## Manifest format

`scripts/qa_targets.yaml`:

```yaml
defaults:
  fetch_timeout_sec: 180
  matrix_timeout_sec: 600
  post_analyze_settle_sec: 2
  headless: true
  viewport: {width: 1920, height: 1080}

cached:
  - name: TRAPPIST-1
    mission: TESS
    mission_label: "TESS (via Lightkurve)"
    depth: 2
    snr: 5.0
  - name: Kepler-11
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 3
    snr: 6.0
  - name: WASP-12 b
    mission: TESS
    mission_label: "TESS (via Lightkurve)"
    depth: 1
    snr: 10.0
  - name: Kepler-20
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 3
    snr: 4.5
  - name: AU Mic
    mission: TESS
    mission_label: "TESS (via Lightkurve)"
    depth: 2
    snr: 6.0
  - name: HD 80606 b
    mission: TESS
    mission_label: "TESS (via Lightkurve)"
    depth: 1
    snr: 7.0
  - name: Kepler-4d
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 1
    snr: 6.5
  - name: Kepler-90
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 3
    snr: 5.0

dynamic:
  - name: TOI-700
    mission: TESS
    mission_label: "TESS (via Lightkurve)"
    depth: 2
    snr: 4.8
  - name: K2-138
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 3
    snr: 5.5
  - name: Kepler-186
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 2
    snr: 5.0
  - name: K2-18
    mission: Kepler
    mission_label: "Kepler (via Lightkurve)"
    depth: 1
    snr: 5.5
  - name: WASP-121
    mission: TESS
    mission_label: "TESS (via Lightkurve)"
    depth: 1
    snr: 7.0
```

Notes:
- `mission` is the value passed to `RemoteDiscoveryEngine.fetch_data()`.
- `mission_label` is the exact text used by the Streamlit selectbox (must
  match the option label).
- `depth` and `snr` configure the multi-planet toggle and sliders.
- 5 dynamic targets were chosen: TOI-700 (TESS, NASA TESS Object of Interest),
  K2-138 (Kepler multi-planet chain), Kepler-186 (Kepler habitable-zone
  multi-planet), K2-18 (Kepler habitable-zone single-planet), WASP-121
  (TESS, ultra-hot Jupiter with 1.18% transit — clean BLS signal).

## Env var: `ASTRAEUS_FORCE_NETWORK`

In `astraeus/core/lightkurve_client.py::_try_serve_from_cache`:

```python
if os.environ.get("ASTRAEUS_FORCE_NETWORK") == "1":
    # QA mode: bypass the cache entirely so the dynamic MAST path
    # gets exercised on every run.
    return None, None
```

- Default behaviour (env var unset): cache fallback runs as today.
- QA mode (env var = "1"): cache lookup is skipped, every fetch goes
  through `_download_pipeline` → MAST/S3.
- Set via `os.environ["ASTRAEUS_FORCE_NETWORK"] = "1"` at the top of
  `qa_runner_v2.py` before importing `astraeus`.

## Phase A: Backend pre-flight

```python
async def phase_a_backend_preflight(target):
    """Validate the dynamic data path works BEFORE driving the UI."""
    started = time.monotonic()
    try:
        result = RDE._fetch_data_impl(target["name"], target["mission"])
    except Exception as exc:
        return {"status": "backend_crashed", "error": str(exc),
                "elapsed_sec": time.monotonic() - started}

    elapsed = time.monotonic() - started
    out = {
        "target": target["name"],
        "mission": target["mission"],
        "fetch_status": result.get("status"),
        "reason": result.get("reason"),
        "elapsed_sec": elapsed,
        "time_points": (len(result["time"])
                        if result.get("time") is not None else 0),
        "bridged_mission": result.get("bridged_mission"),
        "resolved_target": result.get("resolved_target"),
    }
    if result.get("status") != "success":
        out["mast_error"] = result.get("mast_error")
        out["archive_error"] = result.get("archive_error")
        return {"status": "backend_failed", **out}
    return {"status": "backend_ok", **out}
```

Three exit states:
- `backend_ok` → UI run proceeds.
- `backend_failed` → UI run proceeds but records the failure (UI may still
  work via cache if env var didn't propagate).
- `backend_crashed` → UI run SKIPPED for that target (no point clicking
  buttons if backend crashes).

The pre-flight calls `RDE._fetch_data_impl` directly (bypassing the
`_cached_fetch_data` `@st.cache_data` wrapper) so every pre-flight is a
fresh dynamic fetch — no stale Streamlit cache.

## Phase B: UI flow

Per target:

1. Launch fresh Playwright browser context.
2. Navigate to `http://localhost:8501`.
3. Click `Detective` sidebar tab.
4. Type target name into `stTextInput`.
5. Click `TESS (via Lightkurve)` / `Kepler (via Lightkurve)` in selectbox.
6. Click `Fetch Target Metadata`.
7. Wait for `Analyze Telemetry` button to become visible (timeout
   `fetch_timeout_sec`, default 180s).
8. **Snapshot #1**: `qa_<target>_01_post_fetch.png`.
9. If `depth > 1`: toggle `Multi-Planet Search Deep-Dive` and set the
   `Max Planetary Scan Depth` and `SNR Floor Cutoff` sliders.
10. Click `Analyze Telemetry`.
11. Wait 2s for the click to register.
12. **Snapshot #2**: `qa_<target>_02_post_analyze.png`.
13. Wait for `Diagnostic Summary Matrix` text to appear (timeout
    `matrix_timeout_sec`, default 600s).
14. Wait 3s for full matrix render.
15. **Snapshot #3 + DOM + exceptions**: `qa_<target>_03_matrix.png`,
    `qa_<target>_03_matrix_dom.txt`, `qa_<target>_03_exceptions.txt` (if any).
16. Close browser.

UI run outcome recorded in `stages`:
- `fetch`: ok / timeout (with `elapsed_sec`).
- `matrix`: ok / timeout (with `elapsed_sec`, optional `exceptions`).
- `ui_crashed`: boolean, with `error` string.

## Reporter

Markdown report at `reports/qa_v2_<mode>_<timestamp>.md`:

```markdown
# QA v2 Report — dynamic
_Run started: 2026-06-27 23:14:02_

## Summary

- Targets tested: **5**
- Passed: **2** ✅
- Failed: **3** ❌
- Pass rate: **40.0%**

## Per-target details

### WASP-121 (TESS) — PASS
**Backend**
- status: `backend_ok`
- fetch_status: `success`
- elapsed_sec: `12.4`
- time_points: `28150`

**UI flow**
- fetch: `ok` (3.1s)
- matrix: `ok` (87.4s)

**Artifacts**: `outputs/ui_tests_v2/WASP-121/`

### K2-138 (Kepler) — FAIL
**Backend**
- status: `backend_failed`
- fetch_status: `no_time_series`
- reason: `Target not observed`
- elapsed_sec: `180.0`
...
```

Overall pass/fail per target:
- `pass` ⟺ `backend.status == 'backend_ok'` AND
  `ui.stages.matrix.status == 'ok'`
- `fail` otherwise.

## Error handling

| Failure | Behaviour | Exit code |
|---|---|---|
| Streamlit not running on :8501 | Print error, exit | 2 |
| Manifest missing/malformed | Print YAML parse error, exit | 3 |
| Playwright page crash | Catch, set `ui_crashed=true`, save `crash_state.png`, continue to next target | (continues) |
| Backend crash in Phase A | Set `backend_crashed`, skip Phase B for that target | (continues) |
| Phase A `backend_failed` (status != success) | UI run still attempted (cache may help) | (continues) |
| Phase B `matrix.timeout` | Snapshot #2 saved; matrix stage marked timeout | (continues) |

## Edge cases

- **Target name with spaces** (WASP-12 b): `safe = name.replace(' ', '_')`
  used for paths; UI input gets the original name.
- **TESS targets**: `_resolve_mission_target` prefix regex covers
  `TIC|TOI|WASP-|...` so dynamic resolution stays correct.
- **Multi-planet depth > 1**: slider section gated by
  `if target.get('depth', 1) > 1`.
- **Slow network**: backend pre-flight has its own 180s timeout; UI fetch
  has `fetch_timeout_sec`; matrix has `matrix_timeout_sec`. Default 600s
  matrix is 10 minutes — long enough for heavy multi-planet BLS runs.
- **Cache returns 0 valid files** even with env var bypass: cache lookup
  is skipped entirely, so we always exercise the MAST path. No code
  change needed in `LightkurveClient.download_pipeline`.

## Testing

1. Run `python scripts/qa_runner_v2.py --mode cached`:
   - 8 cached targets.
   - Each should `backend_ok` (cache hit) and produce full matrix.
2. Run `python scripts/qa_runner_v2.py --mode dynamic`:
   - 5 dynamic targets.
   - Some may `backend_failed` (MAST still flaky); UI run still attempted.
3. Manual smoke: open `http://localhost:8501`, type TOI-700, verify UI
   works end-to-end.
4. Inspect `reports/qa_v2_*.md` and `outputs/ui_tests_v2/<target>/`.

## Out of scope

- Pre-existing UI bugs (slider keyboard arrow sequencing, page crashes
  from concurrent Playwright contexts).
- Making the cache write to a different location during QA. Dynamic QA
  runs populate the cache as a side effect; that's intentional.
- New metric types in the report.

## Acceptance criteria

- ✅ `qa_runner_v2.py --mode cached` produces a markdown report for all
  8 cached targets with backend_ok and matrix_ok for at least 6 of 8.
- ✅ `qa_runner_v2.py --mode dynamic` produces a markdown report for all
  5 dynamic targets with at least 1 backend_ok+matrix_ok showing the
  dynamic path works.
- ✅ At least 3 distinct `03_matrix.png` screenshots exist in
  `outputs/ui_tests_v2/`, each showing a fully rendered Diagnostic
  Summary Matrix.
- ✅ No `stException` divs in any matrix DOM (DOM grep check).
- ✅ No regressions in v1 (`scripts/qa_runner.py`) — it still runs and
  still produces per-target post-analyze screenshots.