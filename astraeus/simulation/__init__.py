"""Synthetic simulation workflows for ASTRAEUS."""

from astraeus.simulation.synthetic import (
    LightCurveSeries,
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)

# Completeness-sweep symbols are added incrementally across the bucket's
# commits. We re-export each one defensively so callers can introspect
# the public surface without import-time errors during intermediate
# commits where one symbol exists but another does not.
__all__ = [
    "CompletenessSweepConfig",
    "CompletenessSweepResult",
    "LightCurveSeries",
    "SyntheticTransitScenario",
    "generate_synthetic_transit_series",
    "run_completeness_sweep",
]


def _try_export(name: str) -> None:
    """Attempt to import `name` from astraeus.simulation.completeness and
    bind it as a module-level attribute. Silently skips if the symbol
    does not yet exist (intermediate commits of the bucket)."""
    try:
        value = getattr(__import__("astraeus.simulation.completeness", fromlist=[name]), name)
    except (ImportError, AttributeError):
        return
    globals()[name] = value


for _name in ("CompletenessSweepConfig", "CompletenessSweepResult", "run_completeness_sweep"):
    _try_export(_name)
del _name, _try_export