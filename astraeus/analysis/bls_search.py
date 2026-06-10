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
    def search(time: np.ndarray, flux: np.ndarray) -> dict:
        if len(time) > 1000:
            n_bins = 1000
            points_per_bin = len(time) // n_bins
            truncate_idx = points_per_bin * n_bins
            binned_time = time[:truncate_idx].reshape(n_bins, points_per_bin).mean(axis=1)
            binned_flux = flux[:truncate_idx].reshape(n_bins, points_per_bin).mean(axis=1)
        else:
            binned_time = time
            binned_flux = flux

        model = BoxLeastSquares(binned_time, binned_flux)
        durations = np.array([0.01, 0.03, 0.05, 0.07, 0.1])
        periods = np.linspace(0.5, 20.0, 5000)
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
        mask_window = 2.5 * duration
        out_of_transit_mask = np.abs(phase) >= 0.5 * mask_window
        return time[out_of_transit_mask], flux[out_of_transit_mask]
