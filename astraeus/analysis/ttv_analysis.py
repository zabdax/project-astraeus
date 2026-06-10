import numpy as np

class TTVAnalyzer:
    @staticmethod
    def calculate(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float) -> list:
        ttv_data = []
        try:
            if period > 0 and duration > 0:
                epoch_t0 = t0 - np.floor((t0 - np.min(time)) / period) * period
                max_epoch = int(np.ceil((np.max(time) - epoch_t0) / period))
                
                for epoch in range(0, max_epoch + 1):
                    try:
                        t_calc = epoch_t0 + (epoch * period)
                        window_mask = (time >= t_calc - 0.5 * duration) & (time <= t_calc + 0.5 * duration)
                        t_window = time[window_mask]
                        f_window = flux[window_mask]
                        
                        if len(t_window) == 0:
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
                    except Exception:
                        continue
        except Exception:
            pass
            
        return ttv_data
