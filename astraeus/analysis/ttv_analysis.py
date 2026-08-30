import logging

import numpy as np

logger = logging.getLogger(__name__)

# Audit fix M7 (2026-08-21): a window must dip at least this many robust
# sigma (measured on the full, out-of-window-inclusive flux) to count as a
# transit; otherwise the epoch is gap/noise-only and any "residual" is a
# phantom timing measurement.
_DIP_SIGNIFICANCE_SIGMA = 3.0

# Minimum number of in-window samples for a usable timing measurement.
_MIN_WINDOW_POINTS = 5


class TTVAnalyzer:
    @staticmethod
    def calculate(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float) -> list:
        ttv_data = []
        try:
            if period > 0 and duration > 0:
                # Robust noise scale of the full light curve (MAD-based),
                # computed once outside the epoch windows so gap-covered
                # epochs can be rejected against the global noise level.
                full_median = np.median(flux)
                robust_sigma = 1.4826 * np.median(np.abs(flux - full_median))
                dip_threshold = _DIP_SIGNIFICANCE_SIGMA * robust_sigma

                epoch_t0 = t0 - np.floor((t0 - np.min(time)) / period) * period
                max_epoch = int(np.ceil((np.max(time) - epoch_t0) / period))

                for epoch in range(0, max_epoch + 1):
                    try:
                        t_calc = epoch_t0 + (epoch * period)
                        window_mask = (time >= t_calc - 0.5 * duration) & (time <= t_calc + 0.5 * duration)
                        t_window = time[window_mask]
                        f_window = flux[window_mask]

                        # Audit fix M7 (2026-08-21): reject epochs whose
                        # window holds too few points or fails to actually
                        # dip (gap-covered epochs previously recorded
                        # phantom residuals from pure out-of-transit noise).
                        if len(t_window) < _MIN_WINDOW_POINTS:
                            continue
                        if (np.max(f_window) - np.min(f_window)) < dip_threshold:
                            continue

                        n_lowest = max(1, int(0.10 * len(t_window)))
                        lowest_idx = np.argsort(f_window)[:n_lowest]

                        t_lowest = t_window[lowest_idx]
                        f_lowest = f_window[lowest_idx]

                        depths = np.max(f_window) - f_lowest
                        if np.sum(depths) > 0:
                            t_obs = float(np.average(t_lowest, weights=depths))
                        else:
                            t_obs = float(np.mean(t_lowest))

                        ttv_residual_min = (t_obs - t_calc) * 1440.0

                        ttv_data.append({
                            'epoch': epoch,
                            'ttv_residual_min': float(ttv_residual_min)
                        })
                    except Exception as exc:
                        # Numeric failure on one epoch must not silently
                        # masquerade as "no TTV"; surface it (audit fix M7).
                        logger.warning(
                            "TTV epoch %d failed to reduce (skipped): %s", epoch, exc
                        )
                        continue
        except Exception as exc:
            logger.warning("TTV analysis aborted early: %s", exc)

        return ttv_data
