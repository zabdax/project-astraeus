# QA v2 — Dual-mode Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new dual-mode QA harness that drives the Detective tab end-to-end (Fetch → Analyze → wait for Diagnostic Summary Matrix), validates the dynamic data-retrieval path via a backend pre-flight, and produces a markdown report per run.

**Architecture:** Two-phase harness per target. Phase A calls `RemoteDiscoveryEngine._fetch_data_impl` directly with `ASTRAEUS_FORCE_NETWORK=1` to bypass the cache and exercise the dynamic MAST/S3 path. Phase B drives the Streamlit UI via Playwright with 3 mandatory snapshots (post-fetch, post-analyze, matrix). v1 stays untouched as a fallback.

**Tech Stack:** Python 3.12, Playwright (async), `lightkurve`, `astraeus.core.ingestion`, `pyyaml`, Streamlit (running externally).

**Reference spec:** `docs/superpowers/specs/2026-06-27-qa-v2-dual-mode-design.md`

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `astraeus/core/lightkurve_client.py` | Edit | Honour `ASTRAEUS_FORCE_NETWORK=1` env var in `_try_serve_from_cache` |
| `scripts/qa_targets.yaml` | Create | Target manifest (8 cached + 5 dynamic) |
| `scripts/qa_runner_v2.py` | Create | Dual-mode QA harness (Phase A backend + Phase B UI) |
| `reports/` | (artifacts) | Markdown reports written by harness |
| `outputs/ui_tests_v2/` | (artifacts) | Per-target screenshots + DOM + JSON |

---

## Task 1: Add `ASTRAEUS_FORCE_NETWORK` env-var bypass to `_try_serve_from_cache`

**Files:**
- Modify: `astraeus/core/lightkurve_client.py:572-595` (the early-return block in `_try_serve_from_cache`)

- [ ] **Step 1: Locate the `_try_serve_from_cache` early-return block**

Open `astraeus/core/lightkurve_client.py`. The function starts at the comment:
```python
@staticmethod
def _try_serve_from_cache(t_name: str, mission_type: str, download_dir: str) -> tuple[dict | None, str | None]:
```
The current early-return block looks like:
```python
        try:
            mission_subdir = "TESS" if mission_type == "TESS" else "Kepler"
            mast_root = os.path.join(download_dir, "mastDownload", mission_subdir)
            if not os.path.isdir(mast_root):
                return None, None

            target_digits = "".join(ch for ch in t_name if ch.isdigit())
```

- [ ] **Step 2: Insert env-var bypass**

Immediately after `        try:`, add a new block:

```python
        try:
            # QA mode: honour ASTRAEUS_FORCE_NETWORK=1 by skipping the cache
            # lookup entirely. This lets the QA harness exercise the dynamic
            # MAST/S3 path on every run, even for targets that already have
            # files on disk. Default behaviour (env var unset) is unchanged.
            if os.environ.get("ASTRAEUS_FORCE_NETWORK") == "1":
                print(
                    f"[LightkurveClient] cache bypass: ASTRAEUS_FORCE_NETWORK=1; "
                    f"skipping cache lookup for {t_name}",
                    file=sys.stderr,
                )
                return None, None

            mission_subdir = "TESS" if mission_type == "TESS" else "Kepler"
            mast_root = os.path.join(download_dir, "mastDownload", mission_subdir)
            if not os.path.isdir(mast_root):
                return None, None

            target_digits = "".join(ch for ch in t_name if ch.isdigit())
```

- [ ] **Step 3: Verify env-var integration with a quick Python check**

Run:
```bash
python -c "
import os
os.environ['ASTRAEUS_FORCE_NETWORK'] = '1'
from astraeus.core.lightkurve_client import LightkurveClient
dl = LightkurveClient._download_cache_dir()
# TRAPPIST-1 is cached, but env var should bypass.
res, _ = LightkurveClient._try_serve_from_cache('TRAPPIST-1', 'TESS', dl)
print('result with env var set:', res is None)  # should be True (miss)
"
```

Then unset the env var and run again:
```bash
python -c "
import os
from astraeus.core.lightkurve_client import LightkurveClient
dl = LightkurveClient._download_cache_dir()
res, _ = LightkurveClient._try_serve_from_cache('TRAPPIST-1', 'TESS', dl)
print('result without env var:', res is not None)  # should be True (hit)
"
```

Expected: First run prints `result with env var set: True`. Second run prints `result without env var: True`.

- [ ] **Step 4: Commit**

```bash
git add astraeus/core/lightkurve_client.py
git commit -m "feat(ingest): honour ASTRAEUS_FORCE_NETWORK env var to bypass cache"
```

---

## Task 2: Create the target manifest

**Files:**
- Create: `scripts/qa_targets.yaml`

- [ ] **Step 1: Write the manifest file**

Create `scripts/qa_targets.yaml` with this content:

```yaml
# scripts/qa_targets.yaml
# Two sections so the manifest stays readable as targets grow.
# `cached` runs against the local cache (fast, deterministic).
# `dynamic` runs with ASTRAEUS_FORCE_NETWORK=1 so the cache
# fallback is bypassed — exercises the full MAST/S3 path.

defaults:
  fetch_timeout_sec: 180
  matrix_timeout_sec: 600
  post_analyze_settle_sec: 2
  headless: true
  viewport:
    width: 1920
    height: 1080

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

- [ ] **Step 2: Verify YAML parses cleanly**

Run:
```bash
python -c "
import yaml
m = yaml.safe_load(open('scripts/qa_targets.yaml', encoding='utf-8'))
print('cached:', len(m['cached']))
print('dynamic:', len(m['dynamic']))
print('first cached:', m['cached'][0]['name'])
print('first dynamic:', m['dynamic'][0]['name'])
print('defaults:', m['defaults'])
"
```

Expected output:
```
cached: 8
dynamic: 5
first cached: TRAPPIST-1
first dynamic: TOI-700
defaults: {'fetch_timeout_sec': 180, 'matrix_timeout_sec': 600, 'post_analyze_settle_sec': 2, 'headless': True, 'viewport': {'width': 1920, 'height': 1080}}
```

- [ ] **Step 3: Commit**

```bash
git add scripts/qa_targets.yaml
git commit -m "feat(qa): add dual-mode target manifest (8 cached + 5 dynamic)"
```

---

## Task 3: Create `scripts/qa_runner_v2.py` — manifest loader + Phase A backend pre-flight

**Files:**
- Create: `scripts/qa_runner_v2.py`

- [ ] **Step 1: Create the file with imports + manifest loader + Phase A**

Create `scripts/qa_runner_v2.py` with the following content:

```python
"""QA v2 — Dual-mode harness.

Modes:
  --mode cached    Run against the local cache (fast, deterministic).
                    Uses ASTRAEUS_FORCE_NETWORK unset.
  --mode dynamic   Bypass the cache via ASTRAEUS_FORCE_NETWORK=1
                    so the dynamic MAST/S3 path gets exercised.

Each target runs two phases:
  Phase A: Backend pre-flight — calls RemoteDiscoveryEngine
           ._fetch_data_impl() directly with the env var set so the
           cache is bypassed. Validates that the dynamic data path
           works before we drive the UI.
  Phase B: UI flow — Playwright drives the Detective tab end-to-end,
           captures three snapshots per target.

Usage:
  python scripts/qa_runner_v2.py --mode cached
  python scripts/qa_runner_v2.py --mode dynamic
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Set the env var BEFORE importing astraeus so the @st.cache_data wrapper
# (if Streamlit is loaded) and our cache fallback both see the bypass.
if "--mode" in sys.argv and "dynamic" in sys.argv:
    os.environ.setdefault("ASTRAEUS_FORCE_NETWORK", "1")

import yaml  # noqa: E402

from astraeus.core.ingestion import RemoteDiscoveryEngine  # noqa: E402

ARTIFACTS_DIR = Path("outputs/ui_tests_v2")
REPORTS_DIR = Path("reports")
MANIFEST_PATH = Path("scripts/qa_targets.yaml")


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"ERROR: manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(3)
    try:
        return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"ERROR: manifest YAML parse failed: {exc}", file=sys.stderr)
        sys.exit(3)


async def phase_a_backend_preflight(target: dict) -> dict:
    """Validate the dynamic data path works BEFORE driving the UI.

    Three exit states:
      backend_ok        UI run proceeds.
      backend_failed    UI run still attempted (cache may help).
      backend_crashed   UI run SKIPPED for that target.
    """
    started = time.monotonic()
    try:
        # Bypass the @st.cache_data wrapper so every pre-flight is a fresh
        # dynamic fetch (no 1-hour TTL cache masking real failures).
        result = RemoteDiscoveryEngine._fetch_data_impl(
            target["name"], target["mission"]
        )
    except Exception as exc:
        return {
            "status": "backend_crashed",
            "target": target["name"],
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_sec": round(time.monotonic() - started, 2),
        }

    elapsed = time.monotonic() - started
    out = {
        "target": target["name"],
        "mission": target["mission"],
        "fetch_status": result.get("status"),
        "reason": result.get("reason"),
        "elapsed_sec": round(elapsed, 2),
        "time_points": (
            len(result["time"]) if result.get("time") is not None else 0
        ),
        "bridged_mission": result.get("bridged_mission"),
        "resolved_target": result.get("resolved_target"),
    }
    if result.get("status") != "success":
        out["mast_error"] = result.get("mast_error")
        out["archive_error"] = result.get("archive_error")
        return {"status": "backend_failed", **out}
    return {"status": "backend_ok", **out}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--mode",
        choices=["cached", "dynamic"],
        required=True,
        help="Run against cache (fast) or bypass cache to exercise dynamic path.",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help=f"Path to qa_targets.yaml (default: {MANIFEST_PATH})",
    )
    return p.parse_args()


async def main() -> int:
    args = parse_args()

    # Pre-flight: confirm Streamlit is reachable.
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8501", timeout=5).read(1)
    except Exception as exc:
        print(
            f"ERROR: cannot reach Streamlit at http://localhost:8501: {exc}",
            file=sys.stderr,
        )
        print(
            "Start it with: python -m streamlit run app.py --server.port 8501",
            file=sys.stderr,
        )
        return 2

    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    targets = manifest[args.mode]
    defaults = manifest.get("defaults", {})

    if args.mode == "dynamic":
        print(
            "[qa_runner_v2] running in DYNAMIC mode (cache bypassed "
            "via ASTRAEUS_FORCE_NETWORK=1)"
        )
    else:
        print("[qa_runner_v2] running in CACHED mode (uses local cache)")

    print(f"[qa_runner_v2] {len(targets)} targets to test\n")

    started_at = datetime.now()
    results: list[dict] = []

    for t in targets:
        target = {**defaults, **t}
        print(f"\n=== {args.mode}: {target['name']} ({target['mission']}) ===")

        backend = await phase_a_backend_preflight(target)
        print(
            f"  backend: {backend.get('status')} "
            f"({backend.get('elapsed_sec', 0)}s, "
            f"{backend.get('time_points', 0)} points)"
        )
        if backend.get("reason"):
            print(f"    reason: {backend['reason']}")
        if backend.get("error"):
            print(f"    error: {backend['error']}")

        # Phase B (UI) is implemented in Task 4. Until then, stub it.
        ui: dict = {"target": target["name"], "stages": {}, "ui_crashed": False}

        overall = (
            "pass"
            if (
                backend.get("status") == "backend_ok"
                and ui.get("stages", {}).get("matrix", {}).get("status") == "ok"
            )
            else "fail"
        )
        results.append(
            {
                "target": target["name"],
                "mission": target["mission"],
                "mode": args.mode,
                "overall": overall,
                "backend": backend,
                "ui": ui,
            }
        )

    # Reporter is implemented in Task 5. For now, write a stub.
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"qa_v2_{args.mode}_phase_a_only.md"
    out_path.write_text(
        f"# QA v2 ({args.mode}) — Phase A only stub\n"
        f"Run started: {started_at:%Y-%m-%d %H:%M:%S}\n"
        f"Targets tested: {len(results)}\n",
        encoding="utf-8",
    )
    print(f"\n[qa_runner_v2] stub report written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Verify Phase A runs end-to-end with the dynamic env var set**

Run:
```bash
python scripts/qa_runner_v2.py --mode dynamic
```

Expected: 
- Script prints "running in DYNAMIC mode" header.
- For each dynamic target, prints `backend: backend_ok` or `backend: backend_failed` with elapsed_sec.
- Script exits 0.
- `reports/qa_v2_dynamic_phase_a_only.md` is created.

If you see `backend_failed` with reason `Network Timeout` or `Target not observed`, that's expected — MAST is flaky. The point of the test is to confirm the harness runs.

- [ ] **Step 3: Verify Phase A also runs in cached mode without bypassing cache**

Run:
```bash
python scripts/qa_runner_v2.py --mode cached
```

Expected:
- Script prints "running in CACHED mode" header.
- For TRAPPIST-1 and Kepler-11 (which have files on disk), `backend: backend_ok` with `time_points > 0`.
- Script exits 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/qa_runner_v2.py
git commit -m "feat(qa): v2 harness with manifest loader and Phase A backend pre-flight"
```

---

## Task 4: Add Phase B (UI flow) to `scripts/qa_runner_v2.py`

**Files:**
- Modify: `scripts/qa_runner_v2.py` (replace the Phase B stub with the real implementation)

- [ ] **Step 1: Add Playwright import + helper at the top of the file**

After the existing imports, add:

```python
from playwright.async_api import async_playwright  # noqa: E402
```

- [ ] **Step 2: Add the `_set_slider` helper**

Add this function after `phase_a_backend_preflight`:

```python
async def _set_slider(page, label_text: str, target_val: float,
                     min_val: float, max_val: float, step: float = 1.0) -> None:
    """Drive a Streamlit slider via keyboard arrows.

    Streamlit sliders are focusable role='slider' elements; once focused,
    ArrowRight / ArrowLeft change the value by `step`.
    """
    try:
        slider = (
            page.locator(f"div:has-text('{label_text}')")
            .locator("div[role='slider']")
            .first
        )
        await slider.focus()
        await page.keyboard.press("Home")
        await page.wait_for_timeout(200)
        steps = int(round((target_val - min_val) / step))
        for _ in range(max(steps, 0)):
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(50)
    except Exception as exc:
        print(f"    ! slider '{label_text}' set failed: {exc}", file=sys.stderr)
```

- [ ] **Step 3: Add the `phase_b_ui_flow` function**

Add this function right after `_set_slider`:

```python
async def phase_b_ui_flow(
    target: dict, page_timeout: int, matrix_timeout: int, headless: bool
) -> dict:
    """Drive the Detective tab exactly like a user would.

    Captures three snapshots:
      01_post_fetch.png  — after Fetch returns, Analyze button visible.
      02_post_analyze.png — immediately after Analyze click.
      03_matrix.png      — Diagnostic Summary Matrix fully rendered.

    Returns a dict with:
      stages.fetch  : {status, elapsed_sec, error?}
      stages.matrix : {status, elapsed_sec, exceptions?, error?}
      ui_crashed    : bool
      error         : str (if ui_crashed)
    """
    safe = target["name"].replace(" ", "_").replace("/", "_")
    out_dir = ARTIFACTS_DIR / safe
    out_dir.mkdir(parents=True, exist_ok=True)

    ui: dict = {
        "target": target["name"],
        "stages": {},
        "ui_crashed": False,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page(
            viewport={
                "width": target.get("viewport", {}).get("width", 1920),
                "height": target.get("viewport", {}).get("height", 1080),
            }
        )

        try:
            # Stage 1: navigate to Streamlit + click Detective tab
            await page.goto("http://localhost:8501", timeout=30000)
            await page.wait_for_selector(".stApp", state="attached")
            await page.wait_for_timeout(3000)
            await page.locator("text=Detective").first.click()
            await page.wait_for_timeout(2000)

            # Stage 2: type target + select mission route
            target_input = (
                page.locator('div[data-testid="stTextInput"] input').first
            )
            await target_input.wait_for(state="visible", timeout=15000)
            await target_input.fill("")
            await target_input.fill(target["name"])
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1000)
            await page.locator('div[data-baseweb="select"]').first.click()
            await page.wait_for_timeout(500)
            await page.locator(
                f"li:has-text('{target['mission_label']}')"
            ).first.click()
            await page.wait_for_timeout(500)

            # Stage 3: click Fetch + wait for Analyze button
            fetch_btn = page.locator(
                "button:has-text('Fetch Target Metadata')"
            ).first
            await fetch_btn.click()
            t0 = time.monotonic()
            try:
                await page.locator(
                    "button:has-text('Analyze Telemetry')"
                ).first.wait_for(
                    state="visible", timeout=page_timeout * 1000
                )
                ui["stages"]["fetch"] = {
                    "status": "ok",
                    "elapsed_sec": round(time.monotonic() - t0, 2),
                }
            except Exception as exc:
                ui["stages"]["fetch"] = {
                    "status": "timeout",
                    "elapsed_sec": round(time.monotonic() - t0, 2),
                    "error": str(exc),
                }
                # No Analyze button — record the failure and bail out of UI.
                await page.screenshot(
                    path=out_dir / "fetch_timeout.png", full_page=True
                )
                return ui

            # Snapshot #1: post-fetch
            await page.screenshot(
                path=out_dir / "01_post_fetch.png", full_page=True
            )

            # Stage 4: multi-planet toggle (if depth > 1)
            depth = target.get("depth", 1)
            if depth > 1:
                try:
                    await page.locator(
                        "text=Multi-Planet Search Deep-Dive"
                    ).first.click()
                    await page.wait_for_timeout(500)
                    await _set_slider(
                        page, "Max Planetary Scan Depth",
                        depth, 1, 5, 1,
                    )
                    await _set_slider(
                        page, "Signal-to-Noise (SNR) Floor Cutoff",
                        target.get("snr", 5.0), 3.0, 12.0, 0.1,
                    )
                except Exception as exc:
                    print(
                        f"    ! multi-planet toggle failed: {exc}",
                        file=sys.stderr,
                    )

            # Stage 5: click Analyze
            analyze_btn = page.locator(
                "button:has-text('Analyze Telemetry')"
            ).first
            await analyze_btn.click()
            await page.wait_for_timeout(target.get("post_analyze_settle_sec", 2) * 1000)

            # Snapshot #2: post-analyze
            await page.screenshot(
                path=out_dir / "02_post_analyze.png", full_page=True
            )

            # Stage 6: wait for Diagnostic Summary Matrix
            t0 = time.monotonic()
            try:
                await page.wait_for_selector(
                    "text=Diagnostic Summary Matrix",
                    timeout=matrix_timeout * 1000,
                )
                # Wait a bit for the matrix to fully render.
                await page.wait_for_timeout(3000)
                ui["stages"]["matrix"] = {
                    "status": "ok",
                    "elapsed_sec": round(time.monotonic() - t0, 2),
                }

                # Snapshot #3 + DOM + exceptions
                await page.screenshot(
                    path=out_dir / "03_matrix.png", full_page=True
                )
                body_text = await page.locator("body").inner_text()
                (out_dir / "03_matrix_dom.txt").write_text(
                    body_text, encoding="utf-8"
                )
                exceptions = await page.locator(
                    "div[data-testid='stException']"
                ).all_inner_texts()
                if exceptions:
                    (out_dir / "03_exceptions.txt").write_text(
                        "\n\n".join(exceptions), encoding="utf-8"
                    )
                    ui["stages"]["matrix"]["exceptions"] = exceptions
            except Exception as exc:
                ui["stages"]["matrix"] = {
                    "status": "timeout",
                    "elapsed_sec": round(time.monotonic() - t0, 2),
                    "error": str(exc),
                }
        except Exception as exc:
            ui["ui_crashed"] = True
            ui["error"] = f"{type(exc).__name__}: {exc}"
            try:
                await page.screenshot(
                    path=out_dir / "crash_state.png", full_page=True
                )
            except Exception:
                pass
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    return ui
```

- [ ] **Step 4: Wire Phase B into `main()`**

In `main()`, replace the `ui: dict = {...}` stub with:

```python
        ui = await phase_b_ui_flow(
            target,
            page_timeout=target.get("fetch_timeout_sec", 180),
            matrix_timeout=target.get("matrix_timeout_sec", 600),
            headless=target.get("headless", True),
        )
```

And update the `print` summary to include UI stages:

```python
        for stage_name, stage in ui.get("stages", {}).items():
            print(
                f"    ui {stage_name}: {stage.get('status')} "
                f"({stage.get('elapsed_sec', 0)}s)"
            )
        if ui.get("ui_crashed"):
            print(f"    ! UI crashed: {ui.get('error')}")
```

- [ ] **Step 5: Smoke-test on a single cached target**

Run:
```bash
mkdir -p outputs/ui_tests_v2
python scripts/qa_runner_v2.py --mode cached 2>&1 | head -50
```

Expected: First few lines print the manifest load + mode header, then iterate over cached targets. For TRAPPIST-1 you should see `backend: backend_ok` and `ui fetch: ok` and `ui matrix: ok` (or matrix timeout if it's slow).

- [ ] **Step 6: Commit**

```bash
git add scripts/qa_runner_v2.py
git commit -m "feat(qa): v2 harness Phase B UI flow with three snapshots per target"
```

---

## Task 5: Add the markdown reporter to `scripts/qa_runner_v2.py`

**Files:**
- Modify: `scripts/qa_runner_v2.py` (replace the stub report with the real writer)

- [ ] **Step 1: Add the `write_report` function**

Add this function right before `parse_args`:

```python
def write_report(results: list[dict], mode: str, started_at: datetime) -> Path:
    """Write a markdown summary to reports/qa_v2_<mode>_<timestamp>.md."""
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / (
        f"qa_v2_{mode}_{started_at:%Y%m%d_%H%M%S}.md"
    )

    n_total = len(results)
    n_pass = sum(1 for r in results if r["overall"] == "pass")
    n_fail = n_total - n_pass
    pass_rate = 100 * n_pass / max(n_total, 1)

    lines: list[str] = [
        f"# QA v2 Report — {mode}",
        "",
        f"_Run started: {started_at:%Y-%m-%d %H:%M:%S}_",
        "",
        "## Summary",
        "",
        f"- Targets tested: **{n_total}**",
        f"- Passed: **{n_pass}** ✅",
        f"- Failed: **{n_fail}** ❌",
        f"- Pass rate: **{pass_rate:.1f}%**",
        "",
        "## Per-target details",
        "",
    ]

    for r in results:
        b = r["backend"]
        u = r["ui"]
        lines.append(
            f"### {r['target']} ({r['mission']}) — "
            f"{r['overall'].upper()}"
        )
        lines.append("")
        lines.append("**Backend**")
        lines.append(f"- status: `{b.get('status')}`")
        if b.get("fetch_status"):
            lines.append(f"- fetch_status: `{b['fetch_status']}`")
        if b.get("reason"):
            lines.append(f"- reason: `{b['reason']}`")
        lines.append(
            f"- elapsed_sec: `{b.get('elapsed_sec', 0):.1f}`"
        )
        lines.append(
            f"- time_points: `{b.get('time_points', 0)}`"
        )
        if b.get("bridged_mission"):
            lines.append(
                f"- bridged_mission: `{b['bridged_mission']}`"
            )
        if b.get("resolved_target"):
            lines.append(
                f"- resolved_target: `{b['resolved_target']}`"
            )
        if b.get("mast_error"):
            lines.append(f"- mast_error: `{b['mast_error']}`")
        lines.append("")

        lines.append("**UI flow**")
        if not u.get("stages"):
            lines.append("- (skipped)")
        else:
            for stage_name, stage in u["stages"].items():
                lines.append(
                    f"- {stage_name}: `{stage.get('status')}` "
                    f"({stage.get('elapsed_sec', 0):.1f}s)"
                )
                if stage.get("exceptions"):
                    lines.append(
                        f"  - exceptions: {len(stage['exceptions'])} "
                        f"(see artifacts)"
                    )
        if u.get("ui_crashed"):
            lines.append(f"- ⚠️ **UI crashed**: `{u.get('error')}`")
        lines.append("")

        lines.append(
            f"**Artifacts**: `outputs/ui_tests_v2/"
            f"{r['target'].replace(' ', '_')}/`"
        )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
```

- [ ] **Step 2: Replace the stub report write in `main()`**

In `main()`, replace the final block (after the `for t in targets` loop) with:

```python
    report_path = write_report(results, args.mode, started_at)
    n_pass = sum(1 for r in results if r["overall"] == "pass")
    print(
        f"\n[qa_runner_v2] report written: {report_path} "
        f"({n_pass}/{len(results)} passed)"
    )
    return 0
```

- [ ] **Step 3: Verify the report renders**

Run:
```bash
python scripts/qa_runner_v2.py --mode cached 2>&1 | tail -10
```

Expected: Output ends with `[qa_runner_v2] report written: reports/qa_v2_cached_<timestamp>.md (N/8 passed)`.

Then read the report:
```bash
ls reports/qa_v2_*.md | tail -1 | xargs head -30
```

Expected: Markdown with the Summary section showing `Targets tested: 8`, `Passed: N`, `Failed: 8-N`, `Pass rate: N*12.5%`, followed by per-target sections.

- [ ] **Step 4: Commit**

```bash
git add scripts/qa_runner_v2.py
git commit -m "feat(qa): v2 harness markdown reporter"
```

---

## Task 6: Run the cached suite and verify acceptance criteria

- [ ] **Step 1: Ensure Streamlit is running on :8501**

Run:
```bash
netstat -ano | grep ":8501.*LISTENING"
```

If nothing is listening:
```bash
cd "$(git rev-parse --show-toplevel)"
python -m streamlit run app.py --server.port 8501 --server.headless=true \
  > logs/streamlit_qav2_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

Wait ~10s, then re-check:
```bash
sleep 10 && netstat -ano | grep ":8501.*LISTENING"
```

- [ ] **Step 2: Run the cached suite (foreground, with output)**

Run:
```bash
python scripts/qa_runner_v2.py --mode cached 2>&1 | tee logs/qa_v2_cached_run.log
```

Expected: 8 targets processed, each with `backend` and `ui` stage results. Some matrix timeouts are OK; at least 6/8 should produce a `03_matrix.png`.

- [ ] **Step 3: Verify at least 6 matrix screenshots exist**

Run:
```bash
ls outputs/ui_tests_v2/*/03_matrix.png | wc -l
```

Expected: `6` or higher.

- [ ] **Step 4: Verify no `stException` divs in matrix DOMs**

Run:
```bash
grep -l "stException" outputs/ui_tests_v2/*/03_matrix_dom.txt 2>/dev/null
```

Expected: empty output (no matches).

- [ ] **Step 5: Inspect one matrix screenshot**

Open `outputs/ui_tests_v2/WASP-12_b/03_matrix.png` (or whichever target has the cleanest run). The Diagnostic Summary Matrix should be fully rendered.

- [ ] **Step 6: Read the final report**

Run:
```bash
ls reports/qa_v2_cached_*.md | tail -1 | xargs cat
```

Expected: A summary section with `Passed: ≥6`, followed by per-target details.

- [ ] **Step 7: Commit (no source changes; just confirm the run) **

```bash
git add outputs/ui_tests_v2/ reports/qa_v2_*.md
git commit -m "test(qa): run v2 cached suite (8 targets, 6+ matrix captures)"
```

---

## Task 7: Run the dynamic suite and verify the dynamic path

- [ ] **Step 1: Run the dynamic suite**

Run:
```bash
python scripts/qa_runner_v2.py --mode dynamic 2>&1 | tee logs/qa_v2_dynamic_run.log
```

Expected: 5 targets processed. Some will fail with `backend_failed` (MAST is flaky); some may succeed. The harness should NOT crash; each target's failure should be recorded cleanly.

- [ ] **Step 2: Verify at least 1 dynamic target had `backend_ok`**

Run:
```bash
python -c "
import yaml, json
import glob
report_files = sorted(glob.glob('reports/qa_v2_dynamic_*.md'))
if not report_files:
    print('no dynamic report yet')
    raise SystemExit
latest = report_files[-1]
print('latest report:', latest)
"
```

Then read the latest dynamic report's Summary section:
```bash
grep -A 5 "## Summary" reports/qa_v2_dynamic_*.md | tail -5
```

Expected: Some passes; some fails; total = 5.

- [ ] **Step 3: Commit (artifacts only)**

```bash
git add outputs/ui_tests_v2/ reports/qa_v2_*.md logs/qa_v2_*.log
git commit -m "test(qa): run v2 dynamic suite (5 fresh-dynamic targets, cache bypassed)"
```

---

## Task 8: Final integration check — confirm v1 still works

- [ ] **Step 1: Run v1 once and confirm no regressions**

Run:
```bash
python scripts/qa_runner.py 2>&1 | tail -20
```

Expected: v1 starts processing targets. (You can stop it after the first target with Ctrl+C; the goal is just to confirm v1 still imports + runs without ImportError.)

- [ ] **Step 2: Confirm v1 and v2 coexist in scripts/**

Run:
```bash
ls scripts/qa_runner*.py scripts/qa_targets.yaml
```

Expected:
```
scripts/qa_runner.py
scripts/qa_runner_v2.py
scripts/qa_targets.yaml
```

- [ ] **Step 3: Commit any remaining artifacts**

```bash
git status
```

If there are uncommitted artifacts (logs, screenshots, reports) that should be tracked:
```bash
git add -A outputs/ reports/ logs/qa_v2_*.log 2>/dev/null || true
git status
```

(Decide case-by-case whether to commit; the screenshots and reports are useful evidence, the logs are optional.)

---

## Acceptance criteria (final check)

- [ ] `scripts/qa_runner_v2.py --mode cached` runs end-to-end and writes `reports/qa_v2_cached_*.md`.
- [ ] `scripts/qa_runner_v2.py --mode dynamic` runs end-to-end and writes `reports/qa_v2_dynamic_*.md`.
- [ ] At least 6 cached targets produced a `03_matrix.png` (Diagnostic Summary Matrix rendered).
- [ ] At least 1 dynamic target had `backend_ok` AND `matrix.ok`.
- [ ] No `stException` divs in any matrix DOM.
- [ ] v1 (`scripts/qa_runner.py`) still imports and runs without ImportError.
- [ ] Both scripts co-exist in `scripts/`.