import numpy as np
from astropy.timeseries import BoxLeastSquares
from typing import Tuple
import json
import os
import datetime

# --- Wotan Biweight Detrending (primary) with safe fallback ---
try:
    from wotan import flatten as wotan_flatten
    _WOTAN_AVAILABLE = True
except ImportError:
    _WOTAN_AVAILABLE = False

def detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=5.0):
    """
    Detects a transit candidate in a light curve using the Box Least Squares (BLS) method.
    """
    time = np.asarray(time)
    flux = np.asarray(flux)
    
    # 1. COMPUTE LOMB-SCARGLE STELLAR ROTATION ESTIMATION
    from astropy.timeseries import LombScargle
    
    frequency, power = LombScargle(time, flux).autopower(minimum_frequency=0.1, maximum_frequency=10.0)
    stellar_rotation_period_days = float(1.0 / frequency[np.argmax(power)])
    
    # 2. DYNAMICALLY SCALE THE DETRENDING WINDOW
    window_length_days = min(0.5, stellar_rotation_period_days * 0.5)

    # 3. WOTAN BIWEIGHT DETRENDING (primary path)
    if _WOTAN_AVAILABLE:
        try:
            flatten_flux, trend_flux = wotan_flatten(
                time, flux,
                window_length=window_length_days,
                method='biweight',
                return_trend=True
            )
            # Guard against NaN contamination from edge effects
            nan_mask = np.isnan(flatten_flux)
            if nan_mask.any():
                flatten_flux[nan_mask] = 1.0
            flux = flatten_flux
        except Exception:
            # Runtime failure inside wotan — fall back to median filter
            _apply_median_fallback = True
        else:
            _apply_median_fallback = False
    else:
        _apply_median_fallback = True

    # 4. MEDIAN-FILTER FALLBACK (legacy path)
    if _apply_median_fallback:
        from scipy.ndimage import median_filter
        dt = float(np.median(np.diff(time)))
        if dt > 0:
            window_length_points = int(window_length_days / dt)
            if window_length_points % 2 == 0:
                window_length_points += 1
            window_length_points = max(3, window_length_points)
            trend = median_filter(flux, size=window_length_points)
            trend[trend == 0] = 1.0  # Avoid division by zero
            flux = flux / trend

    active_time = time.copy()
    active_flux = flux.copy()
    
    candidates = []

    for iteration in range(1, 4):
        if len(active_time) < 10:
            break

        current_time = active_time.copy()
        current_flux = active_flux.copy()

        # Sub-second Computational Efficiency: Multi-Phase Uniform Data Binning
        if len(current_time) > 1000:
            n_bins = 1000
            points_per_bin = len(current_time) // n_bins
            truncate_idx = points_per_bin * n_bins
            current_time = current_time[:truncate_idx].reshape(n_bins, points_per_bin).mean(axis=1)
            current_flux = current_flux[:truncate_idx].reshape(n_bins, points_per_bin).mean(axis=1)

        model = BoxLeastSquares(current_time, current_flux)
        
        # Restrict Sweep Windows
        durations = np.array([0.01, 0.03, 0.05, 0.07, 0.1])
        
        # Vectorized Frequency Gridding
        periods = model.autoperiod(durations, minimum_period=0.5, maximum_period=20.0, frequency_factor=50.0)
        res = model.power(periods, durations)
        
        best_idx = np.argmax(res.power)
        best_period = res.period[best_idx]
        best_power = res.power[best_idx]
        best_depth = float(res.depth[best_idx])
        transit_time = res.transit_time[best_idx]
        duration = res.duration[best_idx]
        
        def compute_snr_depth(p, t0, dur):
            phase = (current_time - t0 + 0.5 * p) % p - 0.5 * p
            in_transit = np.abs(phase) < 0.5 * dur
            out_of_transit = ~in_transit
            out_flux = current_flux[out_of_transit]
            in_flux = current_flux[in_transit]
            in_count = len(in_flux)
            
            depth = 0.0
            if in_count > 0 and len(out_flux) > 0:
                depth = np.median(out_flux) - np.median(in_flux)
                
            snr = 0.0
            if len(out_flux) > 0 and in_count > 0:
                local_noise_std = np.std(out_flux)
                if local_noise_std > 0:
                    snr = (depth / local_noise_std) * np.sqrt(in_count)
            return snr, depth

        best_snr, computed_best_depth = compute_snr_depth(best_period, transit_time, duration)
        best_depth = computed_best_depth if computed_best_depth > 0 else best_depth
        
        # Advanced Anti-Aliasing Physics Pass
        for harmonic in [0.5, 2.0]:
            node_period = harmonic * best_period
            node_snr, node_depth = compute_snr_depth(node_period, transit_time, duration)
            
            if harmonic == 2.0:
                if node_depth >= best_depth * 0.85 and node_snr > best_snr * 0.85:
                    best_period = node_period
                    best_snr = node_snr
                    best_depth = node_depth
            elif harmonic == 0.5:
                if node_depth >= best_depth * 0.85 and node_snr > best_snr * 0.85:
                    best_period = node_period
                    best_snr = node_snr
                    best_depth = node_depth

        confidence_score = float(best_power / np.median(res.power))
        is_valid = best_snr > snr_threshold
        
        result = {
            'candidate_found': is_valid,
            'is_candidate': is_valid,
            'period_days': float(best_period),
            'period': float(best_period),
            'orbital_period': float(best_period),
            'stellar_rotation_period_days': stellar_rotation_period_days,
            'transit_depth': float(best_depth),
            'stellar_radius': 1.0,
            'vetting_status': 'candidate' if is_valid else 'rejected',
            'confidence_score': confidence_score,
            'snr': float(best_snr),
            'depth': float(best_depth),
            'duration': float(duration),
            't0': float(transit_time),
            'periodogram': {
                'periods': res.period.tolist(),
                'powers': res.power.tolist()
            }
        }

        # ── GEOMETRIC VALIDATION FILTER 1: V-SHAPE METRIC ────────────────
        # Phase-fold the light curve at the best-fit period and isolate the
        # core transit window.  Fit a high-order polynomial to quantify the
        # curvature: a truly box-shaped transit (planet) will have a flat
        # bottom, while a V-shaped profile (grazing binary) will not.
        phase_full = (current_time - transit_time + 0.5 * best_period) % best_period - 0.5 * best_period
        in_transit_mask = np.abs(phase_full) < 0.5 * duration
        in_transit_phase = phase_full[in_transit_mask]
        in_transit_flux_vals = current_flux[in_transit_mask]

        v_shape_metric = 0.0
        flat_bottom_fraction = 0.0

        if len(in_transit_phase) >= 8:
            # Sort by phase for a clean polynomial fit
            sort_idx = np.argsort(in_transit_phase)
            ph_sorted = in_transit_phase[sort_idx]
            fl_sorted = in_transit_flux_vals[sort_idx]

            # 6th-order polynomial captures ingress/egress curvature
            poly_coeffs = np.polyfit(ph_sorted, fl_sorted, min(6, len(ph_sorted) - 1))
            poly_fn = np.poly1d(poly_coeffs)
            fitted = poly_fn(ph_sorted)

            # Second derivative measures concavity across the transit floor
            second_deriv = np.gradient(np.gradient(fitted, ph_sorted), ph_sorted)
            max_abs_curv = float(np.max(np.abs(second_deriv))) if len(second_deriv) > 0 else 0.0

            # Flat-bottom fraction: ratio of points within 10% of minimum
            # depth vs. total in-transit points (T23/T14 proxy)
            depth_threshold = np.min(fl_sorted) + 0.10 * np.abs(best_depth)
            n_flat = int(np.sum(fl_sorted <= depth_threshold))
            flat_bottom_fraction = float(n_flat / len(fl_sorted))

            # Normalize curvature against transit depth to get a 0-1 metric
            if best_depth > 0:
                v_shape_metric = float(np.clip(
                    max_abs_curv * (duration ** 2) / best_depth, 0.0, 1.0
                ))
            else:
                v_shape_metric = 0.0

            # Flag: steep V-shape (high curvature AND negligible flat bottom)
            if v_shape_metric > 0.8 or flat_bottom_fraction < 0.05:
                result['vetting_status'] = "V-Shaped False Positive Risk (Potential Grazing Binary)"

        result['v_shape_metric'] = float(v_shape_metric)
        result['flat_bottom_fraction'] = float(flat_bottom_fraction)

        # ── GEOMETRIC VALIDATION FILTER 2: SECONDARY ECLIPSE SEARCH ──────
        # Scan the phase-folded curve around phase 0.5 (anti-transit) for a
        # shallow secondary dip.  A detectable eclipse at this phase is the
        # hallmark of a self-luminous eclipsing binary system.
        phase_secondary = (current_time - transit_time) / best_period
        phase_secondary = phase_secondary - np.floor(phase_secondary)  # 0..1

        sec_window_mask = np.abs(phase_secondary - 0.5) < 0.05
        sec_baseline_mask = (np.abs(phase_secondary - 0.5) >= 0.05) & (np.abs(phase_secondary - 0.5) < 0.15)

        secondary_eclipse_depth = 0.0
        secondary_eclipse_snr = 0.0
        secondary_eclipse_detected = False

        sec_flux = current_flux[sec_window_mask]
        sec_baseline_flux = current_flux[sec_baseline_mask]

        if len(sec_flux) >= 3 and len(sec_baseline_flux) >= 3:
            sec_median = float(np.median(sec_flux))
            baseline_median = float(np.median(sec_baseline_flux))
            secondary_eclipse_depth = float(baseline_median - sec_median)
            baseline_std = float(np.std(sec_baseline_flux))

            if baseline_std > 0 and secondary_eclipse_depth > 0:
                secondary_eclipse_snr = float(
                    (secondary_eclipse_depth / baseline_std) * np.sqrt(len(sec_flux))
                )

            if secondary_eclipse_snr > 3.0:
                secondary_eclipse_detected = True
                result['vetting_status'] = "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"

        result['secondary_eclipse_depth'] = float(secondary_eclipse_depth)
        result['secondary_eclipse_snr'] = float(secondary_eclipse_snr)
        result['secondary_eclipse_detected'] = secondary_eclipse_detected

        # ── PHYSICAL CHARACTERIZATION LAYER ──────────────────────────────
        # Derive observational follow-up metrics from raw BLS output and
        # host-star metadata pulled from the NASA Exoplanet Archive.
        # All three keys degrade gracefully to 0.0 on missing inputs.

        _meta = metadata or {}
        _stellar_radius_rsun = float(_meta.get('stellar_radius', _meta.get('st_rad', 1.0)))
        _st_teff = float(_meta.get('st_teff', 5778.0))
        _st_mass = float(_meta.get('st_mass', 1.0))
        _sy_jmag = float(_meta.get('sy_jmag', 10.0))

        # 1. PLANETARY RADIUS (R_Earth)
        #    R_p = sqrt(transit_depth_fraction) × R_star × 109.2
        #    where 109.2 = R_sun / R_earth conversion factor
        _transit_depth_frac = best_depth  # BLS depth is already a fraction
        if _transit_depth_frac > 0 and _stellar_radius_rsun > 0:
            planet_radius_earth = float(
                np.sqrt(_transit_depth_frac) * _stellar_radius_rsun * 109.2
            )
        else:
            planet_radius_earth = 0.0

        # 2. EQUILIBRIUM TEMPERATURE (K)
        #    T_eq = T_eff × sqrt(R_star / (2 × a)) × (1 - A_B)^0.25
        #    Semi-major axis from Kepler's third law:
        #    a(AU) = (M_star × P_yr²)^(1/3)
        _bond_albedo = 0.3
        _period_days = float(best_period)
        equilibrium_temp_k = 0.0

        if _period_days > 0 and _st_teff > 0 and _st_mass > 0 and _stellar_radius_rsun > 0:
            _period_yr = _period_days / 365.25
            _semi_major_axis_au = (_st_mass * _period_yr ** 2) ** (1.0 / 3.0)
            # Convert stellar radius to AU: 1 R_sun = 0.00465047 AU
            _stellar_radius_au = _stellar_radius_rsun * 0.00465047
            if _semi_major_axis_au > 0:
                equilibrium_temp_k = float(
                    _st_teff
                    * np.sqrt(_stellar_radius_au / (2.0 * _semi_major_axis_au))
                    * (1.0 - _bond_albedo) ** 0.25
                )

        # 3. TRANSMISSION SPECTROSCOPY METRIC (TSM)
        #    Kempton et al. 2018, PASP, 130, 114401
        #    TSM = Scale × (R_p^3 × T_eq) / (M_p × R_star^2) × 10^(-J/5)
        #    Planet mass estimated via Chen & Kipping 2017 M-R relation:
        #      M_p ≈ R_p^2.06  (for R_p < 14.26 R_Earth)
        #    Scale factor binned by radius:
        #      R_p < 1.5:  0.190    (Terrestrial)
        #      1.5-2.75:   1.26     (Sub-Neptune)
        #      2.75-4.0:   1.28     (Neptune-class)
        #      4.0-10.0:   1.15     (Sub-Jovian)
        jwst_tsm_score = 0.0

        if planet_radius_earth > 0 and equilibrium_temp_k > 0 and _stellar_radius_rsun > 0:
            # Radius-binned scale factor (Kempton+2018 Table 1)
            if planet_radius_earth < 1.5:
                _tsm_scale = 0.190
            elif planet_radius_earth < 2.75:
                _tsm_scale = 1.26
            elif planet_radius_earth < 4.0:
                _tsm_scale = 1.28
            elif planet_radius_earth < 10.0:
                _tsm_scale = 1.15
            else:
                _tsm_scale = 1.15  # Extend Sub-Jovian bin for giants

            # Chen & Kipping 2017 mass estimate (Earth masses)
            _planet_mass_earth = planet_radius_earth ** 2.06
            if _planet_mass_earth > 0:
                jwst_tsm_score = float(
                    _tsm_scale
                    * (planet_radius_earth ** 3 * equilibrium_temp_k)
                    / (_planet_mass_earth * _stellar_radius_rsun ** 2)
                    * 10.0 ** (-_sy_jmag / 5.0)
                )

        result['planet_radius_earth'] = round(planet_radius_earth, 4)
        result['equilibrium_temp_k'] = round(equilibrium_temp_k, 2)
        result['jwst_tsm_score'] = round(jwst_tsm_score, 4)

        candidates.append({f'candidate_{iteration}': result})
        
        # Reproducible Ledger
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "target_name": target_name,
            "period": float(best_period),
            "stellar_rotation_period_days": stellar_rotation_period_days,
            "snr": float(best_snr),
            "data_source": data_source,
            "metadata": metadata or {},
            "is_valid_candidate": bool(is_valid)
        }
        
        experiments_file = "experiments.json"
        experiments = []
        if os.path.exists(experiments_file):
            try:
                with open(experiments_file, "r") as f:
                    experiments = json.load(f)
            except Exception:
                pass
                
        experiments.append(log_entry)
        
        try:
            with open(experiments_file, "w") as f:
                json.dump(experiments, f, indent=4)
        except Exception as e:
            print(f"Failed to write to experiments.json: {e}")

        # Mask out transit data points for the next iteration
        if is_valid and best_snr > 7.0:
            phase = (active_time - transit_time + 0.5 * best_period) % best_period - 0.5 * best_period
            mask_window = 2.5 * duration
            out_of_transit_mask = np.abs(phase) >= 0.5 * mask_window
            
            active_time = active_time[out_of_transit_mask]
            active_flux = active_flux[out_of_transit_mask]
        else:
            break

    return candidates

def validate_bls_candidate(
    transit_depth: float, 
    out_of_transit_flux: np.ndarray, 
    in_transit_count: int, 
    snr_threshold: float = 5.0
) -> Tuple[bool, float]:
    """
    Secondary mathematical validation pass for BLS candidates.
    
    Calculates the specific SNR based on transit depth, the standard deviation
    of out-of-transit local noise arrays, and the square root of the number 
    of in-transit data points.
    """
    if len(out_of_transit_flux) == 0 or in_transit_count <= 0:
        return False, 0.0
        
    local_noise_std = np.std(out_of_transit_flux)
    
    if local_noise_std == 0:
        return False, 0.0
        
    calculated_snr = (transit_depth / local_noise_std) * np.sqrt(in_transit_count)
    is_valid = calculated_snr > snr_threshold
    
    return is_valid, float(calculated_snr)
