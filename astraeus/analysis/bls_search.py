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
    def search(time: np.ndarray, flux: np.ndarray, scan_depth: int = 1) -> dict:
        binned_time = time
        binned_flux = flux

        model = BoxLeastSquares(binned_time, binned_flux)
        # Calculate the true observational time span of the active dataset
        T_baseline = float(np.max(time) - np.min(time))
        
        # Dynamically bound the search space (require at least 2 transits within the baseline)
        # FIX 3: Upper boundary expanded 350.0 -> 450.0d so extreme outer giants
        # (e.g. Kepler-90 h at ~331d) resolve cleanly instead of clipping the edge
        # and aliasing to half-period harmonics (~29.84d half-harmonic trap).
        p_min = 0.5
        if T_baseline > 300.0:
            p_max = 450.0
        else:
            p_max = min(450.0, T_baseline / 2.0)
        
        # Auto-scale BLS grid density for high-density resonance chains
        freq_factor = 2 if scan_depth > 3 else 1

        if p_max <= 20.0:
            # Short baseline dataset (e.g., TESS single sector) - use a clean localized grid
            periods = np.linspace(p_min, p_max, 5000 * freq_factor)
        else:
            # Long baseline dataset (e.g., Kepler/PLATO) - use a balanced dual-zone layout
            # Zone 1: High-density linear tracking for rapid inner planets
            grid_inner = np.linspace(p_min, 20.0, 4000 * freq_factor)
            # Zone 2: Physics-matched resolution for long-period outer giants.
            # narrow, infrequent transit dips of extreme cold giants are not skipped by
            # coarse grid spacing, breaking out of the ~29.84d half-harmonic alias trap.
            grid_outer = np.linspace(20.0, p_max, 10000 * freq_factor)
            
            # Merge and ensure unique, sorted periods
            periods = np.unique(np.concatenate([grid_inner, grid_outer]))

        durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
        durations = durations[durations < p_min] # Keep your astropy ValueError shield active
        res = model.power(periods, durations)
        
        best_idx = np.argmax(res.power)
        best_period = res.period[best_idx]
        best_power = res.power[best_idx]
        best_depth = float(res.depth[best_idx])
        transit_time = res.transit_time[best_idx]
        duration = res.duration[best_idx]
        
        best_snr, computed_best_depth = BLSSearchEngine.compute_snr_depth(binned_time, binned_flux, best_period, transit_time, duration)
        best_depth = computed_best_depth if computed_best_depth > 0 else best_depth
        
        # Anti-aliasing pass
        for harmonic in [0.5, 2.0]:
            node_period = harmonic * best_period
            node_snr, node_depth = BLSSearchEngine.compute_snr_depth(binned_time, binned_flux, node_period, transit_time, duration)
            if node_depth >= best_depth * 0.85 and node_snr > best_snr * 0.85:
                best_period = node_period
                best_snr = node_snr
                best_depth = node_depth

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
