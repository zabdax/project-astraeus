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

    # Initialize the BLS model
    model = BoxLeastSquares(time, flux)
    
    # Define a range of durations to search (e.g., 0.01 to 0.2 days is typical for short transits)
    # Adjusting based on time baseline to be safe
    baseline = np.max(time) - np.min(time)
    durations = np.linspace(0.01 * baseline, 0.1 * baseline, 20)
    
    # Compute the periodogram using autopower (automatically determines period grid)
    try:
        results = model.autopower(durations)
    except ValueError:
        # Fallback if autopower fails (e.g., baseline too short)
        periods = np.linspace(0.1, max(0.2, baseline / 2.0), 1000)
        results = model.power(periods, durations)

    # Find the peak of the periodogram
    best_idx = np.argmax(results.power)
    best_power = results.power[best_idx]
    best_period = results.period[best_idx]
    best_depth = results.depth[best_idx]
    best_duration = results.duration[best_idx]
    best_t0 = results.transit_time[best_idx]
    
    # Calculate noise floor (median of the power spectrum)
    noise_floor = np.median(results.power)
    
    # Calculate confidence score (ratio of power to noise floor)
    if noise_floor > 0:
        confidence_score = float(best_power / noise_floor)
    else:
        confidence_score = float('inf')
        
    return {
        'period': float(best_period),
        'depth': float(best_depth),
        'duration': float(best_duration),
        't0': float(best_t0),
        'confidence_score': confidence_score,
        'is_candidate': confidence_score >= threshold,
        'periodogram': {
            'periods': results.period.tolist(),
            'powers': results.power.tolist()
        }
    }
