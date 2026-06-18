import numpy as np
import json
from astraeus.analysis.detection import detect_transit_candidate
from astraeus.analysis.bls_search import BLSSearchEngine

def subtract_planetary_signal(flux, time, period, epoch, duration, depth_ppm, metadata=None):
    """
    Subtracts the transit signal of a planet from the flux timeline without altering noise.
    Uses a hybrid approach: attempts batman-package high-precision subtraction first, 
    and falls back to a custom Trapezoidal model if batman fails or is unavailable.
    
    Args:
        flux (np.ndarray): The flux array.
        time (np.ndarray): The time array.
        period (float): The orbital period of the planet.
        epoch (float): The transit midpoint (t0).
        duration (float): The transit duration.
        depth_ppm (float): The transit depth in parts-per-million.
        metadata (dict, optional): Target metadata (stellar parameters, etc.).
        
    Returns:
        np.ndarray: The new flux array with the transit signal subtracted.
    """
    cleaned_flux = flux.copy()
    
    try:
        import batman
        
        # Initialize batman parameters
        params = batman.TransitParams()
        params.t0 = epoch
        params.per = period
        params.rp = np.sqrt(depth_ppm / 1e6)
        
        # Estimate semi-major axis 'a' from duration and period
        # Using small angle approximation: a = period / (pi * duration)
        params.a = max(1.0, period / (np.pi * duration))
        params.inc = 90.
        params.ecc = 0.
        params.w = 90.
        
        # Attempt to get limb darkening from metadata, else default
        if metadata and 'u' in metadata:
            params.u = metadata['u']
        else:
            params.u = [0.1, 0.3]
            
        params.limb_dark = "quadratic"
        
        # Generate model
        m = batman.TransitModel(params, time)
        transit_model = m.light_curve(params)
        
        # batman returns relative flux where out of transit is 1.0.
        # We need to add the dip (1.0 - transit_model) to our flux to flatten it.
        cleaned_flux += (1.0 - transit_model)
        
    except Exception:
        # Fallback Countermeasure (Trapezoidal Engine)
        # Shift time by epoch to center the transit at phase 0
        phase = (time - epoch + 0.5 * period) % period - 0.5 * period
        abs_phase = np.abs(phase)
        
        # Compute linear ingress and egress ramps (defaulting to 10% of total transit duration)
        ramp_duration = 0.1 * duration
        flat_duration = duration - 2 * ramp_duration
        
        transit_dip = depth_ppm / 1e6
        trapezoid_model = np.zeros_like(flux)
        
        # Flat bottom
        in_flat = abs_phase <= (flat_duration / 2.0)
        trapezoid_model[in_flat] = transit_dip
        
        # Ingress / Egress ramps
        in_ramp = (abs_phase > (flat_duration / 2.0)) & (abs_phase <= (duration / 2.0))
        ramp_x = abs_phase[in_ramp] - (flat_duration / 2.0)
        trapezoid_model[in_ramp] = transit_dip * (1.0 - (ramp_x / ramp_duration))
        
        # Add the trapezoidal dip to flatten the transit
        cleaned_flux += trapezoid_model
        
    return cleaned_flux

def run_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=7.1):
    """
    Orchestrator wrapper to perform a multi-planet search on a given lightcurve.
    This tracks the iteration count and maintains the 'current_working_flux' state.
    
    Args:
        raw_lightcurve (dict or object): Contains at least 'time' and 'flux' arrays.
        max_signals (int): Maximum number of planets/signals to search for.
        snr_floor (float): The minimum SNR threshold for considering a candidate valid.
        
    Returns:
        list: A list of discovered planetary properties (dictionaries).
    """
    # Extract time and flux from raw_lightcurve
    if isinstance(raw_lightcurve, dict):
        time = np.asarray(raw_lightcurve.get('time', []))
        flux = np.asarray(raw_lightcurve.get('flux', []))
        target_name = raw_lightcurve.get('target_name', 'Unknown')
        data_source = raw_lightcurve.get('data_source', 'Unknown')
        metadata = raw_lightcurve.get('metadata', {})
    else:
        # Fallback assuming object notation
        time = np.asarray(getattr(raw_lightcurve, 'time', []))
        flux = np.asarray(getattr(raw_lightcurve, 'flux', []))
        target_name = getattr(raw_lightcurve, 'target_name', 'Unknown')
        data_source = getattr(raw_lightcurve, 'data_source', 'Unknown')
        metadata = getattr(raw_lightcurve, 'metadata', {})
        
    discovered_planetary_properties = []
    
    # State tracking
    active_time = time.copy()
    current_working_flux = flux.copy()
    
    for iteration in range(1, max_signals + 1):
        if len(active_time) < 10:
            break
            
        # We wrap the existing main pipeline execution function
        # detect_transit_candidate returns a dictionary with candidate information
        result = detect_transit_candidate(
            time=active_time,
            flux=current_working_flux,
            target_name=target_name,
            data_source=data_source,
            metadata=metadata,
            snr_threshold=snr_floor
        )
        
        # Read the returned dictionary from the run. Extract the calculated SNR and vetting status.
        snr = result.get('snr', 0.0)
        vetting_status = result.get('vetting_status', '')
        
        # GUARDRAIL 1 (The Break)
        if snr < snr_floor or vetting_status != "Verified Planet Candidate":
            print("Signal significance floor reached. Halting iterative search.")
            break
            
        # GUARDRAIL 2 (The Counter)
        discovered_planetary_properties.append(result)
        
        # Subtract the transit out of the current_working_flux for the next iteration
        best_period = result.get('period')
        transit_time = result.get('t0')
        duration = result.get('duration')
        depth = result.get('depth')
        
        if best_period is not None and transit_time is not None and duration is not None and depth is not None:
            depth_ppm = depth * 1e6
            current_working_flux = subtract_planetary_signal(
                flux=current_working_flux, 
                time=active_time, 
                period=best_period, 
                epoch=transit_time, 
                duration=duration,
                depth_ppm=depth_ppm,
                metadata=metadata
            )
        else:
            # If we don't have enough info to mask, we must break to prevent infinite loops finding the same signal
            break
    else:
        print(json.dumps(discovered_planetary_properties, indent=2))
            
    return discovered_planetary_properties
