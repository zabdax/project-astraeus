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
    def detrend(time: np.ndarray, flux: np.ndarray, stellar_rotation_period_days: float, st_rad: float = None) -> np.ndarray:
        # Preserve float64 precision
        time = np.asarray(time, dtype=np.float64)
        flux = np.asarray(flux, dtype=np.float64)

        # Asymmetric Sigma Clipping: Remove positive anomalies (> +3 sigma)
        median_flux = np.nanmedian(flux)
        std_flux = np.nanstd(flux)
        positive_outliers = flux > (median_flux + 3 * std_flux)
        clean_flux = np.copy(flux)
        clean_flux[positive_outliers] = median_flux

        # Dynamic Window Scaling based on stellar radius
        if st_rad is not None:
            if st_rad < 0.3:
                window_length_days = 0.5
            elif st_rad >= 0.8:
                window_length_days = 2.0
            else:
                window_length_days = 0.5 + ((2.0 - 0.5) / (0.8 - 0.3)) * (st_rad - 0.3)
        else:
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
                    time, clean_flux,
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
                trend = median_filter(clean_flux, size=window_length_points)
                trend[trend == 0] = 1.0
                return clean_flux / trend
        
        return clean_flux
