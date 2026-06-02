import numpy as np
from astropy.timeseries import BoxLeastSquares
from typing import Tuple

def detect_transit_candidate(time, flux, threshold=5.0):
    """
    Detects a transit candidate in a light curve using the Box Least Squares (BLS) method.

    Parameters:
    - time (array-like): Time array (e.g., in days).
    - flux (array-like): Flux array (normalized).
    - threshold (float): Minimum confidence score to be considered a valid candidate.

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
    
    # Check for P/2 harmonic
    idx_half = np.argmin(np.abs(res.period - (best_period / 2.0)))
    if res.power[idx_half] > (0.9 * best_power):
        best_period /= 2.0
        
    confidence_score = float(best_power / np.median(res.power))
    
    # The user provided threshold_sigma=5.0 but the original signature had threshold=5.0
    # The return dict returned 'candidate_found' but the original also had 'is_candidate'
    # For compatibility with UI tests:
    return {
        'candidate_found': confidence_score > threshold,
        'is_candidate': confidence_score > threshold,
        'period_days': float(best_period),
        'period': float(best_period),
        'confidence_score': confidence_score,
        'depth': float(res.depth[best_idx]),
        'duration': float(res.duration[best_idx]),
        't0': float(res.transit_time[best_idx]),
        'periodogram': {
            'periods': res.period.tolist(),
            'powers': res.power.tolist()
        }
    }

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
    
    Args:
        transit_depth: The calculated depth of the transit signal.
        out_of_transit_flux: Array of local out-of-transit flux baseline values.
        in_transit_count: The number of data coordinates lying within the transit.
        snr_threshold: Conservative scientific floor limit for SNR (default: 5.0).
        
    Returns:
        is_valid: Boolean indicating if the candidate cleared the SNR threshold.
        snr: The calculated Signal-to-Noise Ratio as a float.
    """
    if len(out_of_transit_flux) == 0 or in_transit_count <= 0:
        return False, 0.0
        
    local_noise_std = np.std(out_of_transit_flux)
    
    if local_noise_std == 0:
        return False, 0.0
        
    calculated_snr = (transit_depth / local_noise_std) * np.sqrt(in_transit_count)
    is_valid = calculated_snr > snr_threshold
    
    return is_valid, float(calculated_snr)
