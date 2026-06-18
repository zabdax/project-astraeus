import numpy as np
import json
from astraeus.analysis.detection import detect_transit_candidate
from astraeus.analysis.bls_search import BLSSearchEngine

def subtract_planetary_signal(flux, time, period, epoch, duration, depth_ppm):
    """
    Subtracts the transit signal of a planet from the flux timeline without altering noise.
    
    Args:
        flux (np.ndarray): The flux array.
        time (np.ndarray): The time array.
        period (float): The orbital period of the planet.
        epoch (float): The transit midpoint (t0).
        duration (float): The transit duration.
        depth_ppm (float): The transit depth in parts-per-million.
        
    Returns:
        np.ndarray: The new flux array with the transit signal subtracted.
    """
    cleaned_flux = flux.copy()
    
    # Shift time by epoch to center the transit at phase 0
    phase = (time - epoch + 0.5 * period) % period - 0.5 * period
    
    # Identify indices where the planet is transiting
    in_transit = np.abs(phase) < (duration / 2.0)
    
    # Calculate a baseline model of the transit dip and invert it to flatten the transit
    transit_dip = depth_ppm / 1e6
    cleaned_flux[in_transit] += transit_dip
    
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
                depth_ppm=depth_ppm
            )
        else:
            # If we don't have enough info to mask, we must break to prevent infinite loops finding the same signal
            break
    else:
        print(json.dumps(discovered_planetary_properties, indent=2))
            
    return discovered_planetary_properties
