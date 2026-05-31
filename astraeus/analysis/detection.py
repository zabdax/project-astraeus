import numpy as np
from astropy.timeseries import BoxLeastSquares

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
