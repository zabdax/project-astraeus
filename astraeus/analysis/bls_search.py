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
    def search(
        time: np.ndarray,
        flux: np.ndarray,
        scan_depth: int = 1,
        known_periods: list[float] = None,
        frequency_factor: float = None,
    ) -> dict:
        """BLS period search.

        Parameters
        ----------
        time, flux : np.ndarray
            Input light curve.
        scan_depth : int
            Unused legacy parameter, retained for backward compatibility.
        known_periods : list[float]
            Periods already discovered in earlier iterations; the alias-
            rejection loop uses them to skip peaks that are integer
            harmonics or window aliases of known signals.
        frequency_factor : float or None
            Coarseness knob forwarded to ``astropy.timeseries.BoxLeastSquares
            .autoperiod``. None (default) chooses a curve-size-adaptive
            value targeting ~90,000 trial periods: this is dense enough
            to resolve a 3d signal on a 10d baseline (ff=1.0) and coarse
            enough to keep ``model.power`` under ~10s on a 1500d /
            3000-cadence curve (ff=500, 3.6s wall, 4/5 SYN-5P recovered
            with p_max widened to T_baseline/2). The formula is
            ``max(1.0, T_baseline^2 / 4500)`` capped at 500. Pass an
            explicit value (e.g. 1.0 for the legacy dense astropy grid)
            to override.
        """
        if known_periods is None:
            known_periods = []
        
        binned_time = time
        binned_flux = flux

        model = BoxLeastSquares(binned_time, binned_flux)
        # Calculate the true observational time span of the active dataset
        T_baseline = float(np.max(time) - np.min(time))

        # Dynamically bound the search space (require at least 2 transits
        # within the baseline). p_max is T_baseline/2 with a 450d cap on
        # short baselines; on long baselines we use the full T_baseline/2
        # so that injected long-period planets (e.g. the 600d planet in
        # SYN-5P) are within the search range. The 450d cap was a relic
        # of older Kepler-only expectations and silently cut off the
        # p5=600d signal in round-6 testing.
        p_min = 0.5
        if T_baseline > 300.0:
            p_max = T_baseline / 2.0
        else:
            p_max = min(450.0, T_baseline / 2.0)

        # J1b: Use rigorous astropy autoperiod instead of linear grid.
        # The default astropy grid is uniform in frequency with df = 1/baseline^2,
        # which gives ~795k periods on a 200d curve and ~44.95M on a 1500d curve
        # — way too dense for fast BLS and mostly noise. The J3 review showed
        # the period count scales as n_periods ≈ (1/p_min - 1/p_max) * baseline^2 /
        # (frequency_factor * min_duration), and that a target of ~90,000 periods
        # works across curve sizes: 10d smoke (ff=1.0, 1801p), 200d kepler90d
        # (ff=8.9, 89k p, 7.2s wall), 1500d syn5p 5-planet (ff=500, 90k p, 3.6s
        # wall, 4/5 recovered). The default below is ff = max(1.0, baseline^2 / 4500)
        # capped at 500; the cap prevents over-coarsening on very long baselines.
        if frequency_factor is None:
            frequency_factor = max(1.0, T_baseline ** 2 / 4500.0)
            if frequency_factor > 500.0:
                frequency_factor = 500.0
        periods = model.autoperiod(duration=0.1, minimum_period=p_min, maximum_period=p_max, frequency_factor=frequency_factor)

        durations = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
        durations = durations[durations < np.min(periods)] # Keep your astropy ValueError shield active
        res = model.power(periods, durations)

        # J3 fix: astropy returns one row per period, where power is the MAX
        # across the duration grid and duration records the best-fitting
        # duration. At any period p, that max can be at an unphysical
        # duration (e.g. dur=0.4d, p=0.5d, i.e. duration > period). Such
        # pairs are degenerate (the box is wider than the orbital phase)
        # and must not win np.argmax. We mask them here by setting their
        # power to -inf, which is a root-cause fix: it works at any
        # period, not just at p_min/p_max.
        # The 0.2 duty-cycle cap is the standard physical upper bound for
        # transit + grazing-binary configurations; real transits are
        # well under 5% of the orbit.
        _MAX_DUTY_CYCLE = 0.2
        physical_mask = res.duration < (res.period * _MAX_DUTY_CYCLE)
        power_for_argmax = np.where(physical_mask, res.power, -np.inf)
        
        # J1c: Window-aware Alias Rejection
        # Compute the sampling window frequencies
        from astropy.timeseries import LombScargle
        ls = LombScargle(binned_time, np.ones_like(binned_time), fit_mean=False, center_data=False)
        freq_window, power_window = ls.autopower(minimum_frequency=1/1000.0, maximum_frequency=1/10.0)
        top_window_indices = np.argsort(power_window)[-5:]
        top_window_freqs = freq_window[top_window_indices]

        # Iterate through best peaks to find the first one that is NOT an alias of a known period.
        # Use power_for_argmax (with unphysical (P, dur) pairs set to -inf) so
        # degenerate boundary peaks cannot win argmax. See the J3 fix comment
        # above for the rationale.
        sorted_indices = np.argsort(power_for_argmax)[::-1]
        
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

            # J3 follow-up: skip candidates within 5% of the search bounds
            # (p_min or p_max). The physical-mask in power_for_argmax covers
            # unphysical (period, duration) pairs, but a candidate like
            # (P=0.5002d, dur=0.1d) is at the duty-cycle boundary AND very
            # near p_min=0.5d, where the autoperiod grid concentrates
            # degenerate points. These are noise peaks, not real signals.
            # The 5% margin matches the assertion in
            # test_j3_bls_single_signal_regression.py and
            # test_j3_syn5p_small_recovery.py.
            if abs(cand_period - p_min) / p_min <= 0.05:
                is_alias = True
            elif abs(cand_period - p_max) / p_max <= 0.05:
                is_alias = True

            # First, check integer harmonics (e.g. 0.5x, 2.0x, 3.0x) against known periods
            for prev_period in known_periods:
                if is_alias:
                    break
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
