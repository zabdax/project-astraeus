import numpy as np

from astraeus.core.nbody_solver import (
    PlanetParams,
    run_stability_analysis,
    estimate_mass_from_radius,
    M_EARTH_IN_MSUN
)

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

def validate_ttv_with_nbody(
    known_planet: dict,
    ttv_data: list[dict],
    stellar_mass_msun: float,
    max_candidates_to_integrate: int = 5
) -> dict:
    """
    Evaluates detected TTVs for physical plausibility using N-body dynamics.
    Outputs a set of dynamically stable companion configurations consistent with the TTVs.
    """
    epochs = [d.get('epoch') for d in ttv_data if 'epoch' in d and 'ttv_residual_min' in d]
    residuals = [d.get('ttv_residual_min') for d in ttv_data if 'epoch' in d and 'ttv_residual_min' in d]
    
    if not epochs or len(epochs) < 5:
        return {"conclusion": "Insufficient TTV data", "plausible_companions": []}
        
    ttv_arr = np.array(residuals)
    observed_amplitude = (np.max(ttv_arr) - np.min(ttv_arr)) / 2.0
    
    if observed_amplitude < 0.5: # less than 30 seconds TTV is often noise
        return {"conclusion": "TTV consistent with noise, no significant amplitude detected", "plausible_companions": []}
        
    known_period_days = float(known_planet.get('period_days', 0.0))
    if known_period_days <= 0:
        return {"conclusion": "Invalid known planet period", "plausible_companions": []}
        
    known_radius_earth = float(known_planet.get('planet_radius_earth', 2.0))
    known_mass_msun = estimate_mass_from_radius(known_radius_earth)
    
    # Calculate semi-major axis of known planet using Kepler's Third Law
    # P^2 = a^3 / M -> a = (P^2 * M)^(1/3) where P in yr, a in AU, M in M_sun
    known_period_yr = known_period_days / 365.25
    known_a_au = (known_period_yr**2 * stellar_mass_msun)**(1/3)
    
    # 1. Periodicity extraction
    ttv_periodicity = estimate_ttv_periodicity(epochs, residuals, known_period_days)
    
    # 2. Grid Search
    mass_grid_earth = np.logspace(-1, 3.5, 20) # 0.1 Earth to ~3000 Earth (~10 Jupiter)
    period_ratios = np.linspace(0.1, 4.0, 40)
    
    candidates = []
    
    for m_earth in mass_grid_earth:
        m_msun = m_earth * M_EARTH_IN_MSUN
        for pr in period_ratios:
            # Skip crossing orbits/co-orbital for cheap filter
            if 0.9 < pr < 1.1:
                continue
                
            p_comp_days = known_period_days * pr
            analytic_amp = estimate_analytic_ttv_amplitude_min(
                known_period_days, p_comp_days, m_msun, stellar_mass_msun
            )
            
            # Score: ratio of analytic to observed
            if analytic_amp > 0:
                score = abs(np.log10(analytic_amp / observed_amplitude))
                # Keep if it's within a factor of 3 (~0.5 in log10)
                if score < 0.6:
                    candidates.append({
                        "mass_earth": float(m_earth),
                        "mass_msun": float(m_msun),
                        "period_days": float(p_comp_days),
                        "period_ratio": float(pr),
                        "expected_ttv_amplitude_min": float(analytic_amp),
                        "score": score
                    })
                    
    # Sort by score (closest to 0 is best)
    candidates.sort(key=lambda x: x["score"])
    top_candidates = candidates[:max_candidates_to_integrate]
    
    if not top_candidates:
        return {"conclusion": "No plausible companion found analytically matching the TTV amplitude", "plausible_companions": []}
        
    # 3. N-body confirmation
    plausible_stable_companions = []
    
    # Base known planet
    p1 = PlanetParams(
        mass_msun=known_mass_msun,
        semi_major_axis_au=known_a_au,
        eccentricity=0.0,
        initial_phase_rad=0.0
    )
    
    for cand in top_candidates:
        # P_comp^2 = a_comp^3 / M -> a_comp = (P_comp^2 * M)^(1/3)
        p_comp_yr = cand["period_days"] / 365.25
        a_comp_au = (p_comp_yr**2 * stellar_mass_msun)**(1/3)
        
        p2 = PlanetParams(
            mass_msun=cand["mass_msun"],
            semi_major_axis_au=a_comp_au,
            eccentricity=0.05, # slight eccentricity to avoid perfect symmetries
            initial_phase_rad=np.pi # opposite phase
        )
        
        # Sort planets by semi-major axis (inner first) to be safe, though solver doesn't strictly care
        system = [p1, p2] if known_a_au < a_comp_au else [p2, p1]
        
        stability_res = run_stability_analysis(
            stellar_mass_msun=stellar_mass_msun,
            planets=system,
            n_steps=10000 # 10k is sufficient for a quick plausibility check
        )
        
        if stability_res.is_stable:
            cand["stability"] = {
                "is_stable": True,
                "survival_time_years": stability_res.survival_time_years,
                "max_eccentricity_drift": stability_res.max_eccentricity_drift
            }
            plausible_stable_companions.append(cand)
            
    if not plausible_stable_companions:
        return {
            "conclusion": "Analytically plausible companions found, but none were dynamically stable", 
            "ttv_periodicity_days": ttv_periodicity,
            "plausible_companions": []
        }
        
    return {
        "conclusion": "Plausible stable companions found consistent with the observed TTV amplitude.",
        "ttv_periodicity_days": ttv_periodicity,
        "plausible_companions": plausible_stable_companions
    }
