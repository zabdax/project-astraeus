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

def estimate_analytic_ttv_amplitude_min(
    known_period_days: float,
    companion_period_days: float,
    companion_mass_msun: float,
    stellar_mass_msun: float
) -> float:
    """
    Simplified order-of-magnitude TTV amplitude estimator (in minutes) based on Lithwick et al. 2012.
    This acts as a fast pre-filter to reject companions that are physically incapable of producing the observed TTV.
    """
    if stellar_mass_msun <= 0 or known_period_days <= 0:
        return 0.0
        
    mass_ratio = companion_mass_msun / stellar_mass_msun
    period_ratio = companion_period_days / known_period_days
    
    # Crude approximation of resonant amplification: identify nearest first-order resonance j:j-1
    if period_ratio > 1.0:
        j = round(1.0 / (1.0 - 1.0/period_ratio))
        if j < 2: j = 2
        delta = period_ratio * (j-1)/j - 1.0
    else:
        j = round(1.0 / (1.0 - period_ratio))
        if j < 2: j = 2
        delta = (1.0/period_ratio) * (j-1)/j - 1.0
        
    # Prevent division by zero for exact resonance, limit maximum amplification
    abs_delta = max(abs(delta), 0.01)
    
    # Expected amplitude in minutes
    amplitude_min = known_period_days * 1440.0 * mass_ratio / abs_delta
    return float(amplitude_min)
