"""Command-line entry point for ASTRAEUS synthetic validation."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from astraeus.workflows.pipeline import SyntheticValidationPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Run the synthetic hot-Jupiter validation workflow."""
    pipeline = SyntheticValidationPipeline(project_root=PROJECT_ROOT)
    pipeline.execute_full_workflow()


if __name__ == "__main__":
    main()
