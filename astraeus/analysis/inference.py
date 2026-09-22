"""Candidate -> MCMC inference wiring (P4-F).

The pipeline never ran inference against a real detected candidate:
period and semi-major axis arrived as hardcoded constants or form
input. This module closes the four gaps (PRD §6.3):

1. period/epoch come from the candidate (legacy aliases included);
2. semi-major axis comes from Kepler's third law + stellar mass;
3. radius-ratio guess comes from the measured depth;
4. limb-darkening guesses come from the P4-D source (never literals).

Eccentricity is unmeasured by the search: circular is assumed and
stated. Inclination is unmeasured: near edge-on is assumed and stated.
The sampler runs with the P4-A gates attached; `require_converged`
fails closed per call. `AnalysisResult.inference` stays null (v1
contract frozen) — this returns the retrieval result alongside.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from astraeus.core.limb_darkening import resolve as resolve_ld

#: Days per Julian year (Kepler's third law in AU/Msun/yr units).
_DAYS_PER_YEAR = 365.25

#: Assumed inclination for detected (transiting, near edge-on) candidates.
#: The search does not measure inclination; this is a starting guess for
#: the optimizer/sampler, not a result.
ASSUMED_INCLINATION_DEG = 89.5


def kepler_semi_major_axis_au(period_days: float, stellar_mass_solar: float) -> float:
    """Semi-major axis from Kepler's third law (circular orbit)."""
    period_days = float(period_days)
    stellar_mass_solar = float(stellar_mass_solar)
    if period_days <= 0 or stellar_mass_solar <= 0:
        raise ValueError(
            "period and stellar mass must be positive, got "
            f"period_days={period_days!r}, stellar_mass_solar={stellar_mass_solar!r}"
        )
    return float(
        (stellar_mass_solar * (period_days / _DAYS_PER_YEAR) ** 2) ** (1.0 / 3.0)
    )


def _field(candidate: Any, *names: str) -> Any:
    """Read a value from a legacy dict, a pydantic model, or an object."""
    if isinstance(candidate, Mapping):
        for name in names:
            if candidate.get(name) is not None:
                return candidate[name]
        return None
    for name in names:
        value = getattr(candidate, name, None)
        if value is not None:
            return value
    return None


def candidate_to_mcmc_config(
    candidate: Any,
    stellar: Mapping[str, Any] | None = None,
    *,
    n_steps: int = 2000,
    n_walkers: int = 32,
    seed: int | None = None,
    require_converged: bool = False,
) -> "MCMCConfig":
    """Build a retrieval config from a detected candidate (P4-F bridge)."""
    from astraeus.dashboard.services.mcmc_retrieval import MCMCConfig

    stellar = stellar or {}
    period = _field(candidate, "period_days", "period", "orbital_period")
    if period is None or float(period) <= 0:
        raise ValueError(f"candidate carries no usable period: {candidate!r}")
    epoch = _field(candidate, "epoch_bjd", "t0_bjd", "t0", "epoch")
    if epoch is None:
        raise ValueError(f"candidate carries no usable epoch: {candidate!r}")
    depth = _field(candidate, "depth_fraction", "depth", "transit_depth")
    if depth is None or float(depth) <= 0:
        raise ValueError(f"candidate carries no usable depth: {candidate!r}")

    stellar_radius = _field(candidate, "stellar_radius", "st_rad")
    if stellar_radius is None:
        stellar_radius = stellar.get("st_rad", 1.0)
    stellar_mass = stellar.get("st_mass", 1.0)
    ld = resolve_ld(
        st_teff=stellar.get("st_teff"),
        logg=stellar.get("logg"),
        metallicity=stellar.get("metallicity"),
    )
    return MCMCConfig(
        period_days=float(period),
        transit_epoch=float(epoch),
        stellar_radius_rsun=float(stellar_radius),
        semi_major_axis_au=kepler_semi_major_axis_au(float(period), float(stellar_mass)),
        eccentricity=0.0,
        radius_ratio_guess=float(np.sqrt(float(depth))),
        inclination_degrees_guess=ASSUMED_INCLINATION_DEG,
        u1_guess=ld.u1,
        u2_guess=ld.u2,
        n_steps=n_steps,
        n_walkers=n_walkers,
        seed=seed,
        require_converged=require_converged,
    )


def run_candidate_inference(
    time_raw: np.ndarray,
    flux_raw: np.ndarray,
    candidate: Any,
    stellar: Mapping[str, Any] | None = None,
    *,
    n_steps: int = 2000,
    n_walkers: int = 32,
    seed: int | None = None,
    require_converged: bool = False,
    progress_callback=None,
) -> "MCMCRetrievalResult":
    """Fold the candidate's own light curve and retrieve posteriors."""
    from astraeus.dashboard.services.mcmc_retrieval import run_retrieval

    config = candidate_to_mcmc_config(
        candidate, stellar,
        n_steps=n_steps, n_walkers=n_walkers, seed=seed,
        require_converged=require_converged,
    )
    return run_retrieval(
        np.asarray(time_raw, dtype=float),
        np.asarray(flux_raw, dtype=float),
        config,
        progress_callback=progress_callback,
    )
