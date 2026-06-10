import numpy as np

class GeometricValidator:
    @staticmethod
    def validate(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float, depth_fraction: float) -> dict:
        phase_full = (time - t0 + 0.5 * period) % period - 0.5 * period
        in_transit_mask = np.abs(phase_full) < 0.5 * duration
        in_transit_phase = phase_full[in_transit_mask]
        in_transit_flux_vals = flux[in_transit_mask]

        v_shape_metric = 0.0
        flat_bottom_fraction = 0.0

        if len(in_transit_phase) >= 8:
            sort_idx = np.argsort(in_transit_phase)
            ph_sorted = in_transit_phase[sort_idx]
            fl_sorted = in_transit_flux_vals[sort_idx]

            poly_coeffs = np.polyfit(ph_sorted, fl_sorted, min(6, len(ph_sorted) - 1))
            poly_fn = np.poly1d(poly_coeffs)
            fitted = poly_fn(ph_sorted)

            second_deriv = np.gradient(np.gradient(fitted, ph_sorted), ph_sorted)
            max_abs_curv = float(np.max(np.abs(second_deriv))) if len(second_deriv) > 0 else 0.0

            depth_threshold = np.min(fl_sorted) + 0.10 * np.abs(depth_fraction)
            n_flat = int(np.sum(fl_sorted <= depth_threshold))
            flat_bottom_fraction = float(n_flat / len(fl_sorted))

            if depth_fraction > 0:
                v_shape_metric = float(np.clip(max_abs_curv * (duration ** 2) / depth_fraction, 0.0, 1.0))
        
        # Secondary eclipse search
        phase_secondary = (time - t0) / period
        phase_secondary = phase_secondary - np.floor(phase_secondary)

        sec_window_mask = np.abs(phase_secondary - 0.5) < 0.05
        sec_baseline_mask = (np.abs(phase_secondary - 0.5) >= 0.05) & (np.abs(phase_secondary - 0.5) < 0.15)

        secondary_eclipse_depth = 0.0
        secondary_eclipse_snr = 0.0
        secondary_eclipse_detected = False

        sec_flux = flux[sec_window_mask]
        sec_baseline_flux = flux[sec_baseline_mask]

        if len(sec_flux) >= 3 and len(sec_baseline_flux) >= 3:
            sec_median = float(np.median(sec_flux))
            baseline_median = float(np.median(sec_baseline_flux))
            secondary_eclipse_depth = float(baseline_median - sec_median)
            baseline_std = float(np.std(sec_baseline_flux))

            if baseline_std > 0 and secondary_eclipse_depth > 0:
                secondary_eclipse_snr = float((secondary_eclipse_depth / baseline_std) * np.sqrt(len(sec_flux)))

            if secondary_eclipse_snr > 3.0:
                secondary_eclipse_detected = True

        return {
            'v_shape_metric': v_shape_metric,
            'flat_bottom_fraction': flat_bottom_fraction,
            'secondary_eclipse_depth': secondary_eclipse_depth,
            'secondary_eclipse_snr': secondary_eclipse_snr,
            'secondary_eclipse_detected': secondary_eclipse_detected
        }
