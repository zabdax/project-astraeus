import numpy as np
from astraeus.analysis.detection import detect_transit_candidate
from astraeus.analysis.bls_search import BLSSearchEngine

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
        
        # Check if a valid candidate was found
        is_candidate = result.get('is_candidate', False)
        snr = result.get('snr', 0.0)
        
        if not is_candidate or snr < snr_floor:
            # No more significant signals found
            break
            
        # Store discovered planetary properties
        discovered_planetary_properties.append({
            f'signal_{iteration}': result
        })
        
        # Mask the transit out of the current_working_flux for the next iteration
        best_period = result.get('period')
        transit_time = result.get('t0')
        duration = result.get('duration')
        
        if best_period is not None and transit_time is not None and duration is not None:
            active_time, current_working_flux = BLSSearchEngine.mask_transit(
                active_time, 
                current_working_flux, 
                best_period, 
                transit_time, 
                duration
            )
        else:
            # If we don't have enough info to mask, we must break to prevent infinite loops finding the same signal
            break
            
    return discovered_planetary_properties
