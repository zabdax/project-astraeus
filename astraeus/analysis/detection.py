import numpy as np
from astropy.timeseries import BoxLeastSquares
from typing import Tuple
import json
import os
from datetime import datetime

def detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=5.0):
    """
    Detects a transit candidate in a light curve using the Box Least Squares (BLS) method.

    Parameters:
    - time (array-like): Time array (e.g., in days).
    - flux (array-like): Flux array (normalized).
    - target_name (str): Target designation.
    - data_source (str): Data source used.
    - metadata (dict): Metadata traits.
    - snr_threshold (float): Minimum SNR score to be considered a valid candidate.

    Returns:
    - dict: A dictionary containing the candidate metrics and a confidence_score.
    """
    time = np.asarray(time)
    flux = np.asarray(flux)

    model = BoxLeastSquares(time, flux)
    res = model.autopower(np.linspace(0.01, 0.2, 20), frequency_factor=20.0)
    best_idx = np.argmax(res.power)
    best_period = res.period[best_idx]
    best_power = res.power[best_idx]
    best_depth = float(res.depth[best_idx])
    
    # Check for P/2 harmonic (anti-aliasing)
    idx_half = np.argmin(np.abs(res.period - (best_period / 2.0)))
    if res.power[idx_half] > (0.9 * best_power):
        best_period /= 2.0
        
    confidence_score = float(best_power / np.median(res.power))
    
    # Secondary mathematical validation pass: Calculate SNR
    # Find points in transit
    transit_time = res.transit_time[best_idx]
    duration = res.duration[best_idx]
    
    # Phase fold
    phase = (time - transit_time + 0.5 * best_period) % best_period - 0.5 * best_period
    in_transit = np.abs(phase) < 0.5 * duration
    out_of_transit = ~in_transit
    
    out_of_transit_flux = flux[out_of_transit]
    in_transit_count = np.sum(in_transit)
    
    calculated_snr = 0.0
    if len(out_of_transit_flux) > 0 and in_transit_count > 0:
        local_noise_std = np.std(out_of_transit_flux)
        if local_noise_std > 0:
            calculated_snr = (best_depth / local_noise_std) * np.sqrt(in_transit_count)
            
    is_valid = calculated_snr > snr_threshold
    
    result = {
        'candidate_found': is_valid,
        'is_candidate': is_valid,
        'period_days': float(best_period),
        'period': float(best_period),
        'confidence_score': confidence_score,
        'snr': float(calculated_snr),
        'depth': best_depth,
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
        "snr": float(calculated_snr),
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
