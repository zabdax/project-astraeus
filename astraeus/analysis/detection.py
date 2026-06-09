import numpy as np
from astropy.timeseries import BoxLeastSquares
from typing import Tuple
import json
import os
from datetime import datetime

def detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=5.0):
    """
    Detects a transit candidate in a light curve using the Box Least Squares (BLS) method.
    """
    time = np.asarray(time)
    flux = np.asarray(flux)
    
    # Sub-second Computational Efficiency: Multi-Phase Uniform Data Binning
    if len(time) > 3000:
        bins = np.linspace(time.min(), time.max(), 1001)
        bin_indices = np.digitize(time, bins)
        time_binned, flux_binned = [], []
        for i in range(1, 1001):
            mask = bin_indices == i
            if np.any(mask):
                time_binned.append(np.median(time[mask]))
                flux_binned.append(np.median(flux[mask]))
        time = np.array(time_binned)
        flux = np.array(flux_binned)

    model = BoxLeastSquares(time, flux)
    
    # Restrict Sweep Windows
    durations = np.array([0.01, 0.03, 0.05, 0.07, 0.1])
    
    # Vectorized Frequency Gridding
    periods = model.autoperiod(durations, minimum_period=0.5, maximum_period=20.0, frequency_factor=3.0)
    res = model.power(periods, durations)
    
    best_idx = np.argmax(res.power)
    best_period = res.period[best_idx]
    best_power = res.power[best_idx]
    best_depth = float(res.depth[best_idx])
    transit_time = res.transit_time[best_idx]
    duration = res.duration[best_idx]
    
    def compute_snr_depth(p, t0, dur):
        phase = (time - t0 + 0.5 * p) % p - 0.5 * p
        in_transit = np.abs(phase) < 0.5 * dur
        out_of_transit = ~in_transit
        out_flux = flux[out_of_transit]
        in_flux = flux[in_transit]
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
            if node_depth >= best_depth * 0.95 and node_snr > best_snr * 1.05:
                best_period = node_period
                best_snr = node_snr
                best_depth = node_depth
        elif harmonic == 0.5:
            if node_depth >= best_depth * 0.95 and node_snr > best_snr * 0.95:
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
    
    # Reproducible Ledger
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "target_name": target_name,
        "period": float(best_period),
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

    return result

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
