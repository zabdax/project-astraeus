"""Synthetic light-curve generation workflows."""

from __future__ import annotations

import gc
from dataclasses import dataclass, field

import numpy as np
from astropy import units as u
from astropy.timeseries import BoxLeastSquares

from astraeus.core.geometry import calculate_sky_separation
from astraeus.core.orbital_models import calculate_orbital_position
from astraeus.core.transit_model import generate_geometric_transit, generate_model_flux
from astraeus.data.preprocessing import inject_gaussian_noise
from astraeus.core.orchestrator import subtract_planetary_signal
from astraeus.analysis.bls_search import BLSSearchEngine


@dataclass(frozen=True)
class SyntheticTransitScenario:
    """Configuration for a synthetic exoplanet transit validation run."""

    duration: u.Quantity = field(default_factory=lambda: 10.0 * u.day)
    period: u.Quantity = field(default_factory=lambda: 3.0 * u.day)
    eccentricity: u.Quantity = field(
        default_factory=lambda: 0.0 * u.dimensionless_unscaled
    )
    radius_ratio: float = 0.1
    snr: float = 200.0
    samples: int = 4_000
    seed: int = 42
    stellar_radius: u.Quantity = field(default_factory=lambda: 1.0 * u.R_sun)
    semi_major_axis: u.Quantity = field(default_factory=lambda: 10.0 * u.R_sun)
    inclination: u.Quantity = field(default_factory=lambda: 90.0 * u.deg)

    @classmethod
    def hot_jupiter(cls) -> "SyntheticTransitScenario":
        """Return the default ten-day hot-Jupiter validation scenario."""

        return cls()


@dataclass(frozen=True)
class LightCurveSeries:
    """Container for generated synthetic light-curve arrays."""

    time_days: np.ndarray
    theoretical_flux: np.ndarray
    observed_flux: np.ndarray

    @property
    def residuals(self) -> np.ndarray:
        """Return observed minus theoretical flux."""

        return self.observed_flux - self.theoretical_flux


def generate_synthetic_transit_series(
    scenario: SyntheticTransitScenario,
) -> LightCurveSeries:
    """Generate theoretical and noisy light curves for a transit scenario."""

    _validate_scenario(scenario)

    time_days = _generate_time_grid(scenario.duration, scenario.samples)
    time_quantity = time_days * u.day
    theoretical_flux = _generate_theoretical_flux(time_quantity, scenario)
    observed_flux = inject_gaussian_noise(
        theoretical_flux,
        snr=scenario.snr,
        seed=scenario.seed,
    )

    return LightCurveSeries(
        time_days=time_days,
        theoretical_flux=theoretical_flux,
        observed_flux=observed_flux,
    )


def _generate_time_grid(duration: u.Quantity, samples: int) -> np.ndarray:
    """Return an evenly sampled time grid in days."""

    return np.linspace(
        0.0,
        duration.to_value(u.day),
        samples,
        endpoint=True,
    )


def _generate_theoretical_flux(
    time: u.Quantity,
    scenario: SyntheticTransitScenario,
) -> np.ndarray:
    """Calculate noiseless relative flux from orbital and transit physics."""

    x, y, z = calculate_orbital_position(
        time=time,
        period=scenario.period,
        semi_major_axis=scenario.semi_major_axis,
        eccentricity=scenario.eccentricity,
        inclination=scenario.inclination,
    )
    separation = calculate_sky_separation(x, y, z)
    planet_radius = scenario.radius_ratio * scenario.stellar_radius
    flux_drop = generate_geometric_transit(
        separation=separation,
        R_star=scenario.stellar_radius,
        R_planet=planet_radius,
    ).to_value(u.dimensionless_unscaled)

    planet_in_front = z.to_value(scenario.stellar_radius.unit) > 0.0
    return 1.0 - np.where(planet_in_front, flux_drop, 0.0)


def _validate_scenario(scenario: SyntheticTransitScenario) -> None:
    """Validate scenario fields that are local to synthetic sampling."""

    if scenario.samples < 2:
        raise ValueError("samples must be at least 2")

    if not np.isfinite(scenario.radius_ratio) or scenario.radius_ratio <= 0.0:
        raise ValueError("radius_ratio must be a positive finite value")

    if scenario.radius_ratio > 1.0:
        raise ValueError("radius_ratio must be less than or equal to 1.0")


def run_injection_recovery(
    time: np.ndarray,
    flux: np.ndarray,
    injected_period: float,
    injected_r_ratio: float,
    injected_b: float,
    injected_epoch: float,
    known_planets: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    Run an Injection-Recovery validation test.
    
    Args:
        time: Time array in days.
        flux: Authentic flux array.
        injected_period: Period to inject in days.
        injected_r_ratio: Radius ratio Rp/Rs.
        injected_b: Impact parameter.
        injected_epoch: Transit midpoint epoch in days.
        known_planets: List of dictionaries describing known planets to mask out.
        metadata: Metadata containing limb darkening coefficients etc.
        
    Returns:
        A completeness scoring dictionary containing recovery metrics.
    """
    # 1. Parameter Validation
    if injected_r_ratio >= 1.0:
        raise ValueError("Physical violation: Radius ratio must be < 1.0")
    if injected_b >= 1.0 + injected_r_ratio:
        raise ValueError("Physical violation: Impact parameter does not allow a crossing transit")
    
    baseline = np.max(time) - np.min(time)
    if injected_period >= baseline:
        return {
            "signal_recovered": False,
            "error": "Data baseline insufficient",
            "period_error_delta": 0.0,
            "snr_attenuation": 0.0,
            "recovered_period": 0.0,
            "recovered_snr": 0.0,
            "injected_snr": 0.0
        }
        
    # 2. Deep copy to prevent memory leaks during iterations
    local_time = np.copy(time)
    local_flux = np.copy(flux)
    working_flux = np.copy(flux)
    
    # 3. Anti-Collision Guard
    if known_planets:
        for kp in known_planets:
            # Handle possible keys for transit midpoint
            t0 = kp.get('t0', kp.get('epoch', 0.0))
            depth = kp.get('depth', 0.0)
            
            working_flux = subtract_planetary_signal(
                flux=working_flux,
                time=local_time,
                period=kp['period'],
                epoch=t0,
                duration=kp['duration'],
                depth_ppm=depth * 1e6 if depth < 1.0 else depth,
                metadata=metadata
            )
            
    # 4. Core Signal Injection (using native geometry engine)
    a_rs_val = max(15.0, injected_b + 2.0)
    inclination_rad = np.arccos(injected_b / a_rs_val)

    # Audit fix M14 (2026-08-21): generate_model_flux dips at P/4 after
    # whatever origin it is handed, so a quarter-period lead is required
    # for `injected_epoch` to be the actual transit midpoint (previously
    # the dip landed a quarter period away from injected_epoch). The sign
    # is locked numerically by tests/test_science_audit_fixes.py.
    time_quant = (local_time - injected_epoch + 0.25 * injected_period) * u.day
    period_quant = injected_period * u.day
    a_quant = a_rs_val * u.R_sun
    inc_quant = inclination_rad * u.rad
    R_star_quant = 1.0 * u.R_sun
    R_planet_quant = injected_r_ratio * u.R_sun
    
    u1, u2 = 0.1, 0.3
    if metadata and 'u' in metadata:
        u1, u2 = metadata['u']
        
    transit_model = generate_model_flux(
        time=time_quant,
        period=period_quant,
        semi_major_axis=a_quant,
        eccentricity=0.0 * u.dimensionless_unscaled,
        inclination=inc_quant,
        R_star=R_star_quant,
        R_planet=R_planet_quant,
        u1=u1,
        u2=u2,
    )
    
    working_flux *= transit_model
    
    # 5. Performance Countermeasure (Bounded-Grid Slicing)
    p_min = injected_period * 0.95
    p_max = injected_period * 1.05
    
    periods = np.linspace(p_min, p_max, 1000)
    durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3])
    durations = durations[durations < p_min]
    if len(durations) == 0:
        durations = np.array([p_min / 2.0])
        
    model = BoxLeastSquares(local_time, working_flux)
    res = model.power(periods, durations)
    
    best_idx = np.argmax(res.power)
    recovered_period = float(res.period[best_idx])
    recovered_t0 = float(res.transit_time[best_idx])
    recovered_duration = float(res.duration[best_idx])
    
    # 6. Output Completeness Scoring
    snr, depth = BLSSearchEngine.compute_snr_depth(
        local_time, working_flux, recovered_period, recovered_t0, recovered_duration
    )
    
    period_error_delta = abs(recovered_period - injected_period)
    signal_recovered = bool(period_error_delta / injected_period <= 0.01)
    
    in_transit = transit_model < 1.0
    n_in_transit = np.sum(in_transit)
    noise = np.std(local_flux)
    injected_depth = float(1.0 - np.min(transit_model)) if n_in_transit > 0 else 0.0
    
    injected_theoretical_snr = (injected_depth / noise) * np.sqrt(n_in_transit) if noise > 0 else 0.0
    snr_attenuation = float(snr / injected_theoretical_snr) if injected_theoretical_snr > 0 else 0.0
    
    payload_dict = {
        "signal_recovered": signal_recovered,
        "period_error_delta": period_error_delta,
        "snr_attenuation": snr_attenuation,
        "recovered_period": recovered_period,
        "recovered_snr": snr,
        "recovered_depth": float(depth),
        "injected_snr": injected_theoretical_snr
    }
    
    # 7. Memory Isolation Countermeasure (Anti-OOM)
    del working_flux
    del model
    del res
    gc.collect()
    
    return payload_dict
