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
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Make the project root importable so `from astraeus...` works when this
# script is launched as `python scripts/qa_runner_v2.py` (Python prepends
# the script's directory, not the cwd, to sys.path).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Set the env var BEFORE importing astraeus so the @st.cache_data wrapper
# (if Streamlit is loaded) and our cache fallback both see the bypass.
if "--mode" in sys.argv and "dynamic" in sys.argv:
    os.environ.setdefault("ASTRAEUS_FORCE_NETWORK", "1")

import yaml  # noqa: E402

from astraeus.core.ingestion import RemoteDiscoveryEngine  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

ARTIFACTS_DIR = Path("outputs/ui_tests_v2")
REPORTS_DIR = Path("reports")
MANIFEST_PATH = Path("scripts/qa_targets.yaml")


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(3)
    try:
        return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
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


async def _set_slider(page, label_text: str, target_val: float,
                      min_val: float, max_val: float,
                      step: float = 1.0) -> None:
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
        print(
            f"    ! slider '{label_text}' set failed: {exc}",
            file=sys.stderr,
        )


async def phase_b_ui_flow(
    target: dict, page_timeout: int, matrix_timeout: int,
    headless: bool,
) -> dict:
    """Drive the Detective tab exactly like a user would.

    Captures three snapshots:
      01_post_fetch.png   after Fetch returns, Analyze button visible.
      02_post_analyze.png immediately after Analyze click.
      03_matrix.png       Diagnostic Summary Matrix fully rendered.

    Returns a dict with stages.fetch / stages.matrix + ui_crashed flag.
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
                    state="visible", timeout=page_timeout * 1000,
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
                await page.screenshot(
                    path=out_dir / "fetch_timeout.png", full_page=True,
                )
                return ui

            # Snapshot #1: post-fetch
            await page.screenshot(
                path=out_dir / "01_post_fetch.png", full_page=True,
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
                        page,
                        "Signal-to-Noise (SNR) Floor Cutoff",
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
            await page.wait_for_timeout(
                target.get("post_analyze_settle_sec", 2) * 1000
            )

            # Snapshot #2: post-analyze
            await page.screenshot(
                path=out_dir / "02_post_analyze.png", full_page=True,
            )

            # Stage 6: wait for Diagnostic Summary Matrix
            t0 = time.monotonic()
            try:
                await page.wait_for_selector(
                    "text=Diagnostic Summary Matrix",
                    timeout=matrix_timeout * 1000,
                )
                await page.wait_for_timeout(3000)
                ui["stages"]["matrix"] = {
                    "status": "ok",
                    "elapsed_sec": round(time.monotonic() - t0, 2),
                }

                # Snapshot #3 + DOM + exceptions
                await page.screenshot(
                    path=out_dir / "03_matrix.png", full_page=True,
                )
                body_text = await page.locator("body").inner_text()
                (out_dir / "03_matrix_dom.txt").write_text(
                    body_text, encoding="utf-8",
                )
                exceptions = await page.locator(
                    "div[data-testid='stException']"
                ).all_inner_texts()
                if exceptions:
                    (out_dir / "03_exceptions.txt").write_text(
                        "\n\n".join(exceptions), encoding="utf-8",
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
                    path=out_dir / "crash_state.png", full_page=True,
                )
            except Exception:
                pass
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    return ui


def write_report(results: list[dict], mode: str,
                 started_at: datetime) -> Path:
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
            lines.append(
                f"- ⚠️ **UI crashed**: `{u.get('error')}`"
            )
        lines.append("")

        lines.append(
            f"**Artifacts**: `outputs/ui_tests_v2/"
            f"{r['target'].replace(' ', '_')}/`"
        )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


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

    manifest = load_manifest(args.manifest)
    targets = manifest[args.mode]
    defaults = manifest.get("defaults", {})

    if args.mode == "dynamic":
        print(
            "[qa_runner_v2] running in DYNAMIC mode "
            "(cache bypassed via ASTRAEUS_FORCE_NETWORK=1)"
        )
    else:
        print("[qa_runner_v2] running in CACHED mode (uses local cache)")

    print(f"[qa_runner_v2] {len(targets)} targets to test\n")

    started_at = datetime.now()
    results: list[dict] = []

    for t in targets:
        target = {**defaults, **t}
        print(
            f"\n=== {args.mode}: {target['name']} "
            f"({target['mission']}) ==="
        )

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

        # Phase B: UI flow
        ui = await phase_b_ui_flow(
            target,
            page_timeout=target.get("fetch_timeout_sec", 180),
            matrix_timeout=target.get("matrix_timeout_sec", 600),
            headless=target.get("headless", True),
        )
        for stage_name, stage in ui.get("stages", {}).items():
            print(
                f"    ui {stage_name}: {stage.get('status')} "
                f"({stage.get('elapsed_sec', 0)}s)"
            )
        if ui.get("ui_crashed"):
            print(f"    ! UI crashed: {ui.get('error')}")

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

    # Reporter
    report_path = write_report(results, args.mode, started_at)
    n_pass = sum(1 for r in results if r["overall"] == "pass")
    print(
        f"\n[qa_runner_v2] report written: {report_path} "
        f"({n_pass}/{len(results)} passed)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))