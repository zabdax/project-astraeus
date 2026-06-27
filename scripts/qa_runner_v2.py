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

        # Phase B (UI) is implemented in Task 4. Until then, stub it.
        ui: dict = {
            "target": target["name"],
            "stages": {},
            "ui_crashed": False,
        }

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