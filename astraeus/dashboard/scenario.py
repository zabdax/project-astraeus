"""Dashboard input models and validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardTransitScenario:
    """Primitive UI inputs for an interactive transit simulation."""

    radius_ratio: float
    period_days: float
    eccentricity: float
    inclination_degrees: float
    snr: int
    samples: int = 900

    def validate(self) -> None:
        """Validate slider-level bounds before physics quantities are built."""

        if not 0.0 < self.radius_ratio <= 1.0:
            raise ValueError("radius_ratio must satisfy 0 < radius_ratio <= 1")
        if self.period_days <= 0.0:
            raise ValueError("period_days must be positive")
        if not 0.0 <= self.eccentricity < 1.0:
            raise ValueError("eccentricity must satisfy 0 <= eccentricity < 1")
        if not 0.0 <= self.inclination_degrees <= 180.0:
            raise ValueError("inclination_degrees must be between 0 and 180")
        if self.snr <= 0:
            raise ValueError("snr must be positive")
        if self.samples < 2:
            raise ValueError("samples must be at least 2")

    @property
    def stable_seed(self) -> int:
        """Return a deterministic seed for repeatable slider states."""

        scaled_values = (
            int(round(self.radius_ratio * 10_000.0)),
            int(round(self.period_days * 10_000.0)),
            int(round(self.eccentricity * 10_000.0)),
            int(round(self.inclination_degrees * 10_000.0)),
            int(self.snr),
            int(self.samples),
        )
        seed = 0xA57AEE5
        for value in scaled_values:
            seed = ((seed * 1_664_525) + value + 1_013_904_223) % (2**32)
        return seed
