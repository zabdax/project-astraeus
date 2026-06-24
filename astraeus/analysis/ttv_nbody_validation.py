import numpy as np

def estimate_ttv_periodicity(epochs: list[int], ttv_residuals_min: list[float], known_period_days: float) -> float | None:
    """
    Estimates the dominant super-period of Transit Timing Variations using a Lomb-Scargle periodogram.
    Reuses the astropy Lomb-Scargle approach consistent with detrending.py.
    
    Returns the estimated TTV periodicity in days, or None if the signal is indistinguishable from noise.
    """
    if not epochs or not ttv_residuals_min or len(epochs) < 5:
        return None
        
    epochs_arr = np.array(epochs, dtype=float)
    ttv_arr = np.array(ttv_residuals_min, dtype=float)
    
    # If the TTVs are flat/zero, no periodicity
    if np.std(ttv_arr) < 1e-4:
        return None
        
    # Time in days
    time_days = epochs_arr * known_period_days
    
    try:
        from astropy.timeseries import LombScargle
        # TTV periods are typically between 2 * known_period and the full baseline
        baseline = np.max(time_days) - np.min(time_days)
        if baseline <= 0:
            return None
            
        # Frequencies to search (min: 1/baseline, max: Nyquist roughly 1/(2*known_period))
        min_freq = max(1.0 / baseline, 1e-5)
        max_freq = 1.0 / (2.0 * known_period_days)
        
        if min_freq >= max_freq:
            return None
            
        frequency, power = LombScargle(time_days, ttv_arr).autopower(
            minimum_frequency=min_freq, 
            maximum_frequency=max_freq
        )
        
        best_idx = np.argmax(power)
        best_power = power[best_idx]
        best_freq = frequency[best_idx]
        
        # Simple significance threshold: if max power is too low, it's noise
        if best_power < 0.1:
            return None
            
        return float(1.0 / best_freq)
    except Exception:
        return None
