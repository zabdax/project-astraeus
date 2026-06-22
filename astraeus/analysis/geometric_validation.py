import numpy as np

from astraeus.core.constants import (
    GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK,
    GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES,
    GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES,
    GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER,
    GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER,
    GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW,
    VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD,
)


class GeometricValidator:
    @staticmethod
    def validate(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float, depth_fraction: float) -> dict:
        phase_full = (time - t0 + 0.5 * period) % period - 0.5 * period
        in_transit_mask = np.abs(phase_full) < 0.5 * duration
        in_transit_phase = phase_full[in_transit_mask]
        in_transit_flux_vals = flux[in_transit_mask]

        v_shape_metric = 0.0
        flat_bottom_fraction = 1.0  # Default value

        if len(in_transit_phase) >= GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES:
            sort_idx = np.argsort(in_transit_phase)
            fl_sorted = in_transit_flux_vals[sort_idx]

            depth_threshold = np.min(fl_sorted) + GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK * np.abs(depth_fraction)
            n_flat = int(np.sum(fl_sorted <= depth_threshold))
            flat_bottom_fraction = float(n_flat / len(fl_sorted))

        # Secondary eclipse search
        phase_secondary = (time - t0) / period
        phase_secondary = phase_secondary - np.floor(phase_secondary)

        sec_window_mask = np.abs(phase_secondary - 0.5) < GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW
        sec_baseline_mask = (
            (np.abs(phase_secondary - 0.5) >= GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER)
            & (np.abs(phase_secondary - 0.5) < GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER)
        )

        secondary_eclipse_depth = 0.0
        secondary_eclipse_snr = 0.0
        secondary_eclipse_detected = False

        sec_flux = flux[sec_window_mask]
        sec_baseline_flux = flux[sec_baseline_mask]

        if (
            len(sec_flux) >= GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES
            and len(sec_baseline_flux) >= GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES
        ):
            sec_median = float(np.median(sec_flux))
            baseline_median = float(np.median(sec_baseline_flux))
            secondary_eclipse_depth = float(baseline_median - sec_median)
            baseline_std = float(np.std(sec_baseline_flux))

            if baseline_std > 0 and secondary_eclipse_depth > 0:
                secondary_eclipse_snr = float((secondary_eclipse_depth / baseline_std) * np.sqrt(len(sec_flux)))

            if secondary_eclipse_snr > VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD:
                secondary_eclipse_detected = True

        return {
            'v_shape_metric': v_shape_metric,
            'flat_bottom_fraction': flat_bottom_fraction,
            'secondary_eclipse_depth': secondary_eclipse_depth,
            'secondary_eclipse_snr': secondary_eclipse_snr,
            'secondary_eclipse_detected': secondary_eclipse_detected
        }
