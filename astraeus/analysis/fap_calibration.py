"""Empirical false-alarm calibration for the BLS confidence floor (P4-B).

Measurement-only helper. It characterizes the noise-only distribution of
the ``BLSSearchEngine`` confidence statistic (peak BLS periodogram power
divided by the median periodogram power), maps confidence -> empirical
false-alarm probability (FAP), measures detection efficiency versus
threshold on injected synthetic signals, and recommends a floor inside
the observed noise/signal gap.

This module changes NO pipeline behavior: the operational gate
``DETECTION_CONFIDENCE_FLOOR = 7.0`` (see ``astraeus/core/constants.py``)
is untouched, and nothing here is wired into ``detection.py`` or the
orchestrator. Any floor change is a separate decision. All fixtures are
synthetic (white Gaussian noise + ``synthetic.py`` transit injections)
unless a caller explicitly passes real curves in.

Fixtures are deliberately small (30 d baseline, 1200 cadences, coarsened
BLS grid via ``frequency_factor=5.0``) so the calibration suite stays
fast (~1 s per BLS run instead of ~5-8 s on the default dense grid).
"""

from __future__ import annotations

import numpy as np
from astropy import units as u

from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.simulation.synthetic import (
    SyntheticTransitScenario,
    generate_synthetic_transit_series,
)

# ---------------------------------------------------------------------------
# Fixture defaults (shared by the tests and the calibration report script).
# ---------------------------------------------------------------------------

#: Length of each synthetic light curve in days. Short on purpose: the
#: default adaptive BLS grid scales steeply with baseline, and 30 d keeps
#: each search at ~1 s with the coarsened grid below.
BASELINE_DAYS = 30.0

#: Cadence count per synthetic light curve.
N_POINTS = 1200

#: Target SNR of the white-noise fixtures (sigma ~= 1 / SNR on a
#: unity-normalized light curve).
NOISE_SNR = 200.0

#: BLS grid coarseness forwarded to ``BLSSearchEngine.search``. The
#: pipeline default (None -> adaptive ~90k periods) costs ~5-8 s per
#: 30 d curve; 5.0 keeps the noise/signal gap intact at ~1 s per run.
FREQUENCY_FACTOR = 5.0

#: Injected-signal period / depth / noise for the efficiency fixture:
#: a 1%-deep (radius ratio 0.1) 5 d hot Jupiter at SNR 200.
SIGNAL_PERIOD_DAYS = 5.0
SIGNAL_RADIUS_RATIO = 0.1
SIGNAL_SNR = 200.0


# ---------------------------------------------------------------------------
# Fixture builders (seeded, deterministic).
# ---------------------------------------------------------------------------


def _trial_seeds(master_seed: int, n_trials: int) -> list[int]:
    """Derive deterministic per-trial seeds from one master seed."""

    rng = np.random.default_rng(master_seed)
    return [int(s) for s in rng.integers(0, 2**31 - 1, size=n_trials)]


def make_noise_lightcurve(
    seed: int,
    n_points: int = N_POINTS,
    baseline_days: float = BASELINE_DAYS,
    noise_snr: float = NOISE_SNR,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a pure white-noise light curve (flat flux of 1.0 + Gaussian)."""

    rng = np.random.default_rng(seed)
    time = np.linspace(0.0, float(baseline_days), int(n_points))
    flux = 1.0 + rng.normal(loc=0.0, scale=1.0 / float(noise_snr), size=time.shape)
    return time, flux


def make_signal_lightcurve(
    seed: int,
    n_points: int = N_POINTS,
    baseline_days: float = BASELINE_DAYS,
    period_days: float = SIGNAL_PERIOD_DAYS,
    radius_ratio: float = SIGNAL_RADIUS_RATIO,
    noise_snr: float = SIGNAL_SNR,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a synthetic injected-transit light curve via ``synthetic.py``."""

    scenario = SyntheticTransitScenario(
        duration=float(baseline_days) * u.day,
        period=float(period_days) * u.day,
        radius_ratio=float(radius_ratio),
        snr=float(noise_snr),
        samples=int(n_points),
        seed=int(seed),
    )
    series = generate_synthetic_transit_series(scenario)
    return np.asarray(series.time_days), np.asarray(series.observed_flux)


def bls_confidence(
    time: np.ndarray,
    flux: np.ndarray,
    frequency_factor: float = FREQUENCY_FACTOR,
) -> float:
    """Return the BLS confidence score (peak power / median power)."""

    return float(BLSSearchEngine.search(time, flux, frequency_factor=frequency_factor)["confidence_score"])


# ---------------------------------------------------------------------------
# Distribution runners.
# ---------------------------------------------------------------------------


def run_noise_confidences(
    n_trials: int,
    seed: int,
    **fixture_kwargs,
) -> np.ndarray:
    """Run the noise-only BLS confidence distribution (seeded).

    Parameters
    ----------
    n_trials : int
        Number of independent noise realizations.
    seed : int
        Master seed; per-trial seeds are derived deterministically.
    **fixture_kwargs
        Forwarded to :func:`make_noise_lightcurve` (and the BLS grid via
        ``frequency_factor``).
    """

    frequency_factor = fixture_kwargs.pop("frequency_factor", FREQUENCY_FACTOR)
    confidences = np.empty(int(n_trials), dtype=float)
    for i, trial_seed in enumerate(_trial_seeds(seed, int(n_trials))):
        time, flux = make_noise_lightcurve(trial_seed, **fixture_kwargs)
        confidences[i] = bls_confidence(time, flux, frequency_factor=frequency_factor)
    return confidences


def run_signal_confidences(
    n_trials: int,
    seed: int,
    **fixture_kwargs,
) -> np.ndarray:
    """Run BLS confidence on injected-signal fixtures (seeded)."""

    frequency_factor = fixture_kwargs.pop("frequency_factor", FREQUENCY_FACTOR)
    confidences = np.empty(int(n_trials), dtype=float)
    for i, trial_seed in enumerate(_trial_seeds(seed, int(n_trials))):
        time, flux = make_signal_lightcurve(trial_seed, **fixture_kwargs)
        confidences[i] = bls_confidence(time, flux, frequency_factor=frequency_factor)
    return confidences


# ---------------------------------------------------------------------------
# Empirical FAP mapping and detection efficiency.
# ---------------------------------------------------------------------------


def _as_finite_1d(values: np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError(f"{name} must contain at least one value")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain only finite values")
    return arr


def empirical_fap(noise_confidences: np.ndarray, threshold: float) -> float:
    """Return the empirical FAP at ``threshold``: fraction of noise runs >= it."""

    noise = _as_finite_1d(noise_confidences, "noise_confidences")
    threshold = float(threshold)
    if not np.isfinite(threshold):
        raise ValueError("threshold must be finite")
    return float(np.mean(noise >= threshold))


def fap_curve(noise_confidences: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """Map each threshold in ``thresholds`` to its empirical FAP."""

    return np.array([empirical_fap(noise_confidences, t) for t in np.asarray(thresholds, dtype=float)])


def confidence_at_fap(noise_confidences: np.ndarray, target_fap: float) -> float:
    """Return the threshold whose empirical FAP is approximately ``target_fap``.

    Defined via the ``(1 - target_fap)`` quantile of the measured noise
    distribution (``target_fap=0`` returns the noise maximum). This is a
    descriptive quantile of a small synthetic sample, not a formal
    false-alarm probability.
    """

    noise = _as_finite_1d(noise_confidences, "noise_confidences")
    target_fap = float(target_fap)
    if not 0.0 <= target_fap <= 1.0:
        raise ValueError("target_fap must be in [0, 1]")
    return float(np.quantile(noise, 1.0 - target_fap))


def detection_efficiency(signal_confidences: np.ndarray, threshold: float) -> float:
    """Return the fraction of injected signals with confidence >= threshold."""

    signal = _as_finite_1d(signal_confidences, "signal_confidences")
    threshold = float(threshold)
    if not np.isfinite(threshold):
        raise ValueError("threshold must be finite")
    return float(np.mean(signal >= threshold))


def efficiency_vs_threshold(signal_confidences: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """Map each threshold in ``thresholds`` to its detection efficiency."""

    return np.array(
        [detection_efficiency(signal_confidences, t) for t in np.asarray(thresholds, dtype=float)]
    )


# ---------------------------------------------------------------------------
# Floor recommendation (advisory only — not wired into any gate).
# ---------------------------------------------------------------------------


def recommend_floor(
    noise_confidences: np.ndarray,
    signal_confidences: np.ndarray,
) -> tuple[float, str]:
    """Recommend a confidence floor inside the measured noise/signal gap.

    Returns ``(value, rationale)``. When the distributions are separated
    (noise max < signal min) the recommendation is the gap midpoint, at
    which the empirical FAP is 0.0 and the detection efficiency is 1.0
    on the measured samples. When they overlap, the recommendation falls
    back to just above the noise maximum and the rationale says so
    explicitly. Advisory only: the operational floor stays 7.0.
    """

    noise = _as_finite_1d(noise_confidences, "noise_confidences")
    signal = _as_finite_1d(signal_confidences, "signal_confidences")
    noise_max = float(np.max(noise))
    signal_min = float(np.min(signal))

    if noise_max < signal_min:
        value = 0.5 * (noise_max + signal_min)
        rationale = (
            f"Gap midpoint of the measured synthetic distributions "
            f"({noise.size} noise-only runs, {signal.size} injected-signal runs, "
            f"30 d / 1200-cadence fixtures, BLS frequency_factor=5.0): "
            f"noise max {noise_max:.3f} < recommended floor {value:.3f} "
            f"< signal min {signal_min:.3f}. Empirical FAP at the floor is "
            f"{empirical_fap(noise, value):.3f} and detection efficiency is "
            f"{detection_efficiency(signal, value):.3f} on these samples. "
            f"Advisory only: the operational DETECTION_CONFIDENCE_FLOOR (7.0) "
            f"is unchanged by this calibration."
        )
    else:
        value = noise_max + 1e-6
        rationale = (
            f"WARNING: measured noise and signal distributions OVERLAP "
            f"(noise max {noise_max:.3f} >= signal min {signal_min:.3f}); "
            f"no separating floor exists for these fixtures. Returning just "
            f"above the noise maximum ({value:.3f}) as a zero-FAP fallback "
            f"with reduced efficiency "
            f"({detection_efficiency(signal, value):.3f}). Do not use as a gate."
        )
    return float(value), rationale


def summarize_calibration(
    noise_confidences: np.ndarray,
    signal_confidences: np.ndarray,
    thresholds: np.ndarray | None = None,
) -> dict:
    """Return a JSON-friendly summary dict of the calibration measurement."""

    noise = _as_finite_1d(noise_confidences, "noise_confidences")
    signal = _as_finite_1d(signal_confidences, "signal_confidences")
    if thresholds is None:
        thresholds = np.array([3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    thresholds = np.asarray(thresholds, dtype=float)
    floor, rationale = recommend_floor(noise, signal)
    return {
        "n_noise": int(noise.size),
        "n_signal": int(signal.size),
        "noise_min": float(np.min(noise)),
        "noise_median": float(np.median(noise)),
        "noise_max": float(np.max(noise)),
        "signal_min": float(np.min(signal)),
        "signal_median": float(np.median(signal)),
        "signal_max": float(np.max(signal)),
        "thresholds": [float(t) for t in thresholds],
        "fap": [float(v) for v in fap_curve(noise, thresholds)],
        "efficiency": [float(v) for v in efficiency_vs_threshold(signal, thresholds)],
        "recommended_floor": float(floor),
        "rationale": rationale,
        "fixture": {
            "baseline_days": BASELINE_DAYS,
            "n_points": N_POINTS,
            "noise_snr": NOISE_SNR,
            "frequency_factor": FREQUENCY_FACTOR,
            "signal_period_days": SIGNAL_PERIOD_DAYS,
            "signal_radius_ratio": SIGNAL_RADIUS_RATIO,
            "signal_snr": SIGNAL_SNR,
        },
    }
