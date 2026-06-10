import numpy as np

try:
    from wotan import flatten as wotan_flatten
    _WOTAN_AVAILABLE = True
except ImportError:
    _WOTAN_AVAILABLE = False

class DetrendingEngine:
    MIN_TRANSIT_PRESERVING_WINDOW_DAYS = 0.5
    MAX_TRANSIT_PRESERVING_WINDOW_DAYS = 1.5

    @staticmethod
    def estimate_stellar_rotation(time: np.ndarray, flux: np.ndarray) -> float:
        from astropy.timeseries import LombScargle
        if len(time) > 2000:
            step = len(time) // 2000
            ls_time, ls_flux = time[::step], flux[::step]
        else:
            ls_time, ls_flux = time, flux
        frequency, power = LombScargle(ls_time, ls_flux).autopower(minimum_frequency=0.1, maximum_frequency=10.0)
        return float(1.0 / frequency[np.argmax(power)])

    @staticmethod
    def detrend(time: np.ndarray, flux: np.ndarray, stellar_rotation_period_days: float) -> np.ndarray:
        window_length_days = min(
            DetrendingEngine.MAX_TRANSIT_PRESERVING_WINDOW_DAYS,
            max(
                DetrendingEngine.MIN_TRANSIT_PRESERVING_WINDOW_DAYS,
                stellar_rotation_period_days * 0.5,
            ),
        )

        _apply_median_fallback = True

        if _WOTAN_AVAILABLE:
            try:
                flatten_flux, trend_flux = wotan_flatten(
                    time, flux,
                    window_length=window_length_days,
                    method='biweight',
                    return_trend=True
                )
                nan_mask = np.isnan(flatten_flux)
                if nan_mask.any():
                    flatten_flux[nan_mask] = 1.0
                return flatten_flux
            except Exception:
                pass
        
        if _apply_median_fallback:
            from scipy.ndimage import median_filter
            dt = float(np.median(np.diff(time)))
            if dt > 0:
                window_length_points = int(window_length_days / dt)
                if window_length_points % 2 == 0:
                    window_length_points += 1
                window_length_points = max(3, window_length_points)
                trend = median_filter(flux, size=window_length_points)
                trend[trend == 0] = 1.0
                return flux / trend
        
        return flux
