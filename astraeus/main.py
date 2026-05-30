"""Integration script for real exoplanet parameter retrieval (TrES-2b)."""

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from astraeus.workflows.pipeline import RealDataPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    """Run full parameter retrieval on TrES-2b using the orchestration pipeline."""
    pipeline = RealDataPipeline(project_root=PROJECT_ROOT)
    pipeline.execute_full_workflow(target_name="TrES-2b", mission="Kepler", quarter=1)

if __name__ == "__main__":
    main()

