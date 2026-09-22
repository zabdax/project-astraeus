import numpy as np
from scipy.optimize import curve_fit

from astraeus.core.constants import VETTING_U_VS_V_CHI2_DELTA_THRESHOLD

# P4-C diagnostics: tolerances for the *new* additive helpers below. These
# do not alter any existing default, threshold, or verdict.
ODD_EVEN_CONSISTENCY_REL_TOL = 0.30
EPHEMERIS_HARMONICS = (1.0, 2.0, 0.5, 3.0, 1.0 / 3.0, 4.0, 0.25)


def odd_even_depth_test(time, flux, period, t0, duration, depth) -> dict:
    """Odd/even transit-depth consistency check (eclipsing-binary veto).

    Splits in-transit points by epoch parity (``epoch = round((t - t0) /
    period)``) and compares the median odd depth against the median even
    depth, each measured against the out-of-transit median baseline.

    Returns a dict with ``depth_odd``, ``depth_even``, ``depth_ratio``
    (``depth_odd / depth_even``), ``consistent`` (True when the
    fractional depth difference is below
    ``ODD_EVEN_CONSISTENCY_REL_TOL``), plus ``n_odd``/``n_even`` sample
    counts and an ``expected_depth`` echo of the ``depth`` argument.
    Degenerate inputs (too few points, non-positive period/duration)
    yield zero depths and ``consistent=False`` — never a silent pass.
    """
    try:
        time = np.asarray(time, dtype=float)
        flux = np.asarray(flux, dtype=float)
        if time.shape != flux.shape:
            raise ValueError("time and flux must have the same shape")
        period = float(period)
        t0 = float(t0)
        duration = float(duration)
        expected = float(depth)
    except (TypeError, ValueError):
        return {
            'depth_odd': 0.0,
            'depth_even': 0.0,
            'depth_ratio': 0.0,
            'consistent': False,
            'n_odd': 0,
            'n_even': 0,
            'expected_depth': 0.0,
        }
    if not (np.isfinite(period) and period > 0 and np.isfinite(duration) and duration > 0):
        return {
            'depth_odd': 0.0,
            'depth_even': 0.0,
            'depth_ratio': 0.0,
            'consistent': False,
            'n_odd': 0,
            'n_even': 0,
            'expected_depth': float(expected) if np.isfinite(expected) else 0.0,
        }

    finite = np.isfinite(time) & np.isfinite(flux)
    time = time[finite]
    flux = flux[finite]

    epochs = np.round((time - t0) / period).astype(int)
    phase = (time - t0) - epochs * period
    in_transit = np.abs(phase) < 0.5 * duration
    out_of_transit = ~in_transit

    if np.sum(out_of_transit) > 0:
        baseline = float(np.median(flux[out_of_transit]))
    elif len(flux) > 0:
        baseline = float(np.median(flux))
    else:
        baseline = 1.0

    odd_mask = in_transit & ((epochs % 2) != 0)
    even_mask = in_transit & ((epochs % 2) == 0)
    n_odd = int(np.sum(odd_mask))
    n_even = int(np.sum(even_mask))

    if n_odd < 1 or n_even < 1:
        return {
            'depth_odd': 0.0,
            'depth_even': 0.0,
            'depth_ratio': 0.0,
            'consistent': False,
            'n_odd': n_odd,
            'n_even': n_even,
            'expected_depth': float(expected) if np.isfinite(expected) else 0.0,
        }

    depth_odd = float(baseline - np.median(flux[odd_mask]))
    depth_even = float(baseline - np.median(flux[even_mask]))

    if depth_even != 0.0:
        depth_ratio = float(depth_odd / depth_even)
    else:
        depth_ratio = float('inf') if depth_odd > 0.0 else 0.0

    mean_depth = 0.5 * (depth_odd + depth_even)
    if not np.isfinite(mean_depth) or mean_depth <= 0.0:
        consistent = False
    else:
        rel_diff = abs(depth_odd - depth_even) / mean_depth
        consistent = bool(rel_diff < ODD_EVEN_CONSISTENCY_REL_TOL)

    return {
        'depth_odd': depth_odd,
        'depth_even': depth_even,
        'depth_ratio': depth_ratio,
        'consistent': consistent,
        'n_odd': n_odd,
        'n_even': n_even,
        'expected_depth': float(expected) if np.isfinite(expected) else 0.0,
    }


def ephemeris_match(period, known_periods, tol=0.05) -> dict:
    """Ephemeris cross-match against known periods (harmonic-aware).

    A detected ``period`` matches when ``period / known`` is within
    fractional ``tol`` of one of ``EPHEMERIS_HARMONICS``
    (1x, 2x, 0.5x, 3x, 1/3x, 4x, 0.25x).

    Returns a dict with ``match`` (True/False, or None when the known
    list is empty — explicit, never a silent False), ``matched_period``
    (the best-matching known period, else None), and ``ratio``
    (``period / matched_period``, else None).
    """
    if known_periods is None:
        known_list = []
    else:
        try:
            known_list = list(known_periods)
        except TypeError:
            known_list = [known_periods]

    if len(known_list) == 0:
        return {'match': None, 'matched_period': None, 'ratio': None}

    try:
        period = float(period)
    except (TypeError, ValueError):
        return {'match': False, 'matched_period': None, 'ratio': None}
    if not np.isfinite(period) or period <= 0:
        return {'match': False, 'matched_period': None, 'ratio': None}

    try:
        tol = float(tol)
    except (TypeError, ValueError):
        tol = 0.05

    best = None  # (fractional deviation, known period, ratio)
    for kp in known_list:
        try:
            kp_f = float(kp)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(kp_f) or kp_f <= 0:
            continue
        ratio = period / kp_f
        for harmonic in EPHEMERIS_HARMONICS:
            dev = abs(ratio - harmonic) / harmonic
            if dev <= tol and (best is None or dev < best[0]):
                best = (dev, kp_f, ratio)

    if best is None:
        return {'match': False, 'matched_period': None, 'ratio': None}
    return {'match': True, 'matched_period': float(best[1]), 'ratio': float(best[2])}


class VettingEngine:
    # P4-C additive aliases so the new pure diagnostics are reachable
    # through the engine namespace as well as at module level.
    odd_even_depth_test = staticmethod(odd_even_depth_test)
    ephemeris_match = staticmethod(ephemeris_match)

    @staticmethod
    def vet_transit_shape(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float, depth: float, snr: float = 0.0, threshold: float = VETTING_U_VS_V_CHI2_DELTA_THRESHOLD, flux_err: np.ndarray | None = None) -> dict:
        """
        Statistical Transit Model Fitting engine for vetting planet candidates.
        Performs Bayesian Model Likelihood comparison to differentiate between a planetary transit (U-shape)
        and a grazing/eclipsing binary (V-shape).

        ``threshold`` (default ``VETTING_U_VS_V_CHI2_DELTA_THRESHOLD``) is the minimum
        ``(delta_chi2_u - delta_chi2_v)`` required to label the fit as
        ``"Likely Planet"`` rather than ``"Ambiguous/False Positive"``. See
        ``astraeus/core/constants.py`` and ``reports/bucket10_threshold_audit.md``
        §3 for the empirical derivation. The previous default of 0.0 was a
        category-(c) magic-number flagged in bucket 2 — it required only an
        infinitesimal U-shape advantage over V-shape, with no significance
        floor on the fit itself.

        ``flux_err`` (default None) optionally carries per-point 1-sigma
        flux uncertainties aligned with ``time``/``flux``. When None, the
        legacy unweighted sums are used byte-identically. When provided,
        the chi-squared sums use sigma-weighted residuals
        (``((f - model) / sigma)^2``); weights apply as-given against
        the locally-normalized flux, so uniform unit errors reproduce
        the legacy sums exactly. A shape mismatch raises ValueError;
        non-finite/non-positive sigmas fall back to the median of the
        valid windowed sigmas.
        """
        time = np.asarray(time)
        flux = np.asarray(flux)
        
        # Phase-fold the data
        phase = (time - t0 + 0.5 * period) % period - 0.5 * period
        
        # Local median normalization window = 3x duration
        window_mask = np.abs(phase) < 1.5 * duration
        local_phase = phase[window_mask]
        local_flux = flux[window_mask]
        
        # Data Integrity Guard
        if len(local_flux) < 3:
            return {
                'vetting_status': 'Insufficient Data',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0
            }
            
        in_transit_mask = np.abs(local_phase) < 0.5 * duration
        if np.sum(in_transit_mask) < 3:
            return {
                'vetting_status': 'Insufficient Data',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0
            }
            
        # Normalization Guard
        local_median = float(np.median(local_flux))
        if local_median == 0 or np.isnan(local_median):
            return {
                'vetting_status': 'Inconclusive',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0
            }
            
        normalized_flux = local_flux / local_median
        
        # Sort for proper fitting
        sort_idx = np.argsort(local_phase)
        p_sorted = local_phase[sort_idx]
        f_sorted = normalized_flux[sort_idx]
        
        try:
            # Model A: U-Shape (Planet) using analytical trapezoid template
            def u_model_template(t):
                dur = duration
                ingress = dur * 0.1
                flux_model = np.ones_like(t)
                phase = np.abs(t)
                
                flat_mask = phase <= (dur / 2.0 - ingress)
                flux_model[flat_mask] = 0.0
                
                slope_mask = (phase > (dur / 2.0 - ingress)) & (phase < dur / 2.0)
                if ingress > 0:
                    flux_model[slope_mask] = 1.0 - (dur / 2.0 - phase[slope_mask]) / ingress
                    
                return 1.0 - flux_model # 1 at max depth, 0 out of transit
                
            u_template = u_model_template(p_sorted)
            
            def u_model_fit(t, d):
                return 1.0 - d * u_template
                
            popt_u, _ = curve_fit(u_model_fit, p_sorted, f_sorted, p0=[depth], bounds=([0.0], [1.0]), maxfev=100)
            f_u_fit = u_model_fit(p_sorted, *popt_u)
            
            # Model B: V-Shape (Grazing/Eclipsing Binary) template
            def v_model_template(t):
                dur = duration
                flux_model = np.ones_like(t)
                in_trans = np.abs(t) < dur / 2.0
                if np.any(in_trans):
                    flux_model[in_trans] = 1.0 - (1.0 - 2.0 * np.abs(t[in_trans]) / dur)
                return 1.0 - flux_model
                
            v_template = v_model_template(p_sorted)
            
            def v_model_fit(t, d):
                return 1.0 - d * v_template
                
            popt_v, _ = curve_fit(v_model_fit, p_sorted, f_sorted, p0=[depth], bounds=([0.0], [1.0]), maxfev=100)
            f_v_fit = v_model_fit(p_sorted, *popt_v)
            
            # Null hypothesis (flat line)
            f_flat = np.ones_like(p_sorted)
            
            # Chi-Squared Minimization (legacy unweighted path unless
            # flux_err supplies per-point sigmas for weighted residuals)
            if flux_err is None:
                chi2_flat = np.sum((f_sorted - f_flat)**2)
                chi2_u = np.sum((f_sorted - f_u_fit)**2)
                chi2_v = np.sum((f_sorted - f_v_fit)**2)
            else:
                err = np.asarray(flux_err, dtype=float)
                if err.shape != flux.shape:
                    raise ValueError(
                        f"flux_err shape {err.shape} must match flux shape {flux.shape}"
                    )
                err_window = err[window_mask][sort_idx]
                valid_sigma = np.isfinite(err_window) & (err_window > 0)
                if np.any(valid_sigma):
                    sigma_fill = float(np.median(err_window[valid_sigma]))
                else:
                    sigma_fill = 1.0
                sigma = np.where(valid_sigma, err_window, sigma_fill)
                chi2_flat = np.sum(((f_sorted - f_flat) / sigma)**2)
                chi2_u = np.sum(((f_sorted - f_u_fit) / sigma)**2)
                chi2_v = np.sum(((f_sorted - f_v_fit) / sigma)**2)
            
            delta_chi2_u = chi2_flat - chi2_u
            delta_chi2_v = chi2_flat - chi2_v
            
            # Verdict Logic
            if (delta_chi2_u > delta_chi2_v + threshold) or (snr > 10.0):
                status = "Likely Planet"
                confidence = 1.0 - (chi2_u / chi2_v) if chi2_v > 0 else 1.0
            else:
                status = "Ambiguous/False Positive"
                confidence = chi2_u / chi2_v if chi2_v > 0 else 0.0
                
            confidence = max(0.0, min(1.0, confidence))
                
            return {
                'vetting_status': status,
                'vetting_confidence': float(confidence),
                'u_shape_chi2': float(chi2_u),
                'v_shape_chi2': float(chi2_v),
                'delta_chi2_u': float(delta_chi2_u),
                'delta_chi2_v': float(delta_chi2_v)
            }
            
        except Exception:
            return {
                'vetting_status': 'Indeterminate',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0,
                'delta_chi2_u': 0.0,
                'delta_chi2_v': 0.0
            }
