import numpy as np
from astropy.timeseries import BoxLeastSquares

class BLSSearchEngine:
    @staticmethod
    def compute_snr_depth(time: np.ndarray, flux: np.ndarray, p: float, t0: float, dur: float) -> tuple[float, float]:
        phase = (time - t0 + 0.5 * p) % p - 0.5 * p
        in_transit = np.abs(phase) < 0.5 * dur
        out_of_transit = ~in_transit
        out_flux = flux[out_of_transit]
        in_flux = flux[in_transit]
        in_count = len(in_flux)
        
        depth = 0.0
        if in_count > 0 and len(out_flux) > 0:
            depth = np.median(out_flux) - np.median(in_flux)
            
        snr = 0.0
        if len(out_flux) > 0 and in_count > 0:
            local_noise_std = np.std(out_flux)
            if local_noise_std > 0:
                snr = (depth / local_noise_std) * np.sqrt(in_count)
        return float(snr), float(depth)

    @staticmethod
    def search(time: np.ndarray, flux: np.ndarray, scan_depth: int = 1, known_periods: list[float] = None) -> dict:
        if known_periods is None:
            known_periods = []
        
        binned_time = time
        binned_flux = flux

        model = BoxLeastSquares(binned_time, binned_flux)
        # Calculate the true observational time span of the active dataset
        T_baseline = float(np.max(time) - np.min(time))
        
        # Dynamically bound the search space (require at least 2 transits within the baseline)
        p_min = 0.5
        if T_baseline > 300.0:
            p_max = 450.0
        else:
            p_max = min(450.0, T_baseline / 2.0)
        
        # J1b: Use rigorous astropy autoperiod instead of linear grid
        periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max)

        durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
        durations = durations[durations < np.min(periods)] # Keep your astropy ValueError shield active
        res = model.power(periods, durations)
        
        # J1c: Window-aware Alias Rejection
        # Compute the sampling window frequencies
        from astropy.timeseries import LombScargle
        ls = LombScargle(binned_time, np.ones_like(binned_time), fit_mean=False, center_data=False)
        freq_window, power_window = ls.autopower(minimum_frequency=1/1000.0, maximum_frequency=1/10.0)
        top_window_indices = np.argsort(power_window)[-5:]
        top_window_freqs = freq_window[top_window_indices]

        # Iterate through best peaks to find the first one that is NOT an alias of a known period
        sorted_indices = np.argsort(res.power)[::-1]
        
        best_period = None
        best_snr = 0.0
        best_depth = 0.0
        best_power = 0.0
        transit_time = 0.0
        duration = 0.0

        for idx in sorted_indices:
            cand_period = res.period[idx]
            cand_freq = 1.0 / cand_period
            is_alias = False
            
            # First, check integer harmonics (e.g. 0.5x, 2.0x, 3.0x) against known periods
            for prev_period in known_periods:
                ratio = cand_period / prev_period
                # Check harmonics (1/4x up to 5x)
                is_harmonic = False
                for h in [0.25, 0.33, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0]:
                    if abs(ratio - h) / h < 0.05:
                        is_harmonic = True
                        break
                if is_harmonic:
                    is_alias = True
                    break
                
                # Check window aliases: f_cand ≈ |f_prev ± k * f_window|
                prev_freq = 1.0 / prev_period
                for w_freq in top_window_freqs:
                    for k in [1, 2, 3, 4, 5]: # Check up to 5th harmonic of the window
                        for m in [1, 2, 3, 4, 5]: # Check subharmonics of the resulting alias
                            # f_alias = (f_prev + k*f_window) / m
                            if abs(cand_freq - (prev_freq + k * w_freq) / m) < 1e-4:
                                is_alias = True
                                break
                            # f_alias = |f_prev - k*f_window| / m
                            if abs(cand_freq - abs(prev_freq - k * w_freq) / m) < 1e-4:
                                is_alias = True
                                break
                        if is_alias:
                            break
                    if is_alias:
                        break
                if is_alias:
                    break
                    
            if not is_alias:
                # We found a valid non-aliased candidate
                best_period = cand_period
                best_power = res.power[idx]
                best_depth = float(res.depth[idx])
                transit_time = res.transit_time[idx]
                duration = res.duration[idx]
                
                best_snr, computed_best_depth = BLSSearchEngine.compute_snr_depth(binned_time, binned_flux, best_period, transit_time, duration)
                best_depth = computed_best_depth if computed_best_depth > 0 else best_depth
                
                break

        # Fallback if everything was rejected
        if best_period is None:
            best_idx = sorted_indices[0]
            best_period = res.period[best_idx]
            best_power = res.power[best_idx]
            best_depth = float(res.depth[best_idx])
            transit_time = res.transit_time[best_idx]
            duration = res.duration[best_idx]
            best_snr, computed_best_depth = BLSSearchEngine.compute_snr_depth(binned_time, binned_flux, best_period, transit_time, duration)
            best_depth = computed_best_depth if computed_best_depth > 0 else best_depth

        confidence_score = float(best_power / np.median(res.power))
        
        return {
            'period': float(best_period),
            'duration': float(duration),
            't0': float(transit_time),
            'snr': float(best_snr),
            'depth': float(best_depth),
            'confidence_score': confidence_score,
            'periodogram': {
                'periods': res.period.tolist(),
                'powers': res.power.tolist()
            }
        }

    @staticmethod
    def mask_transit(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float) -> tuple[np.ndarray, np.ndarray]:
        phase = (time - t0 + 0.5 * period) % period - 0.5 * period
        mask_window = 1.5 * duration
        out_of_transit_mask = np.abs(phase) >= 0.5 * mask_window
        return time[out_of_transit_mask], flux[out_of_transit_mask]
