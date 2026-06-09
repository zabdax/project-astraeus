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
