"""Command-line entry point for ASTRAEUS synthetic validation."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from astraeus.simulation import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)
from astraeus.visualization.plots import plot_synthetic_validation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "synthetic_validation.png"


def main() -> None:
    """Run the synthetic hot-Jupiter validation workflow."""

    scenario = SyntheticTransitScenario.hot_jupiter()
    light_curve = generate_synthetic_transit_series(scenario)
    output_path = plot_synthetic_validation(
        time_days=light_curve.time_days,
        theoretical_flux=light_curve.theoretical_flux,
        observed_flux=light_curve.observed_flux,
        output_path=OUTPUT_PATH,
    )

    print(f"Synthetic validation plot saved to {output_path}")


if __name__ == "__main__":
    main()
