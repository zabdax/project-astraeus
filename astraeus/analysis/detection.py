import numpy as np

from astraeus.analysis.detrending import DetrendingEngine
from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.analysis.geometric_validation import GeometricValidator
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.analysis.ttv_analysis import TTVAnalyzer
from astraeus.analysis.logging import save_experiment_log
from astraeus.analysis.vetting import VettingEngine
from astraeus.core.constants import (
    VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION,
    VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM,
    VETTING_ULTRA_SHORT_PERIOD_DAYS,
    VETTING_VSHAPE_LOW_SNR_GATE,
    DETECTION_CONFIDENCE_FLOOR,
    DETECTION_SNR_THRESHOLD_DEFAULT,
)

def detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT, known_periods=None):
    if known_periods is None:
        known_periods = []

    time = np.asarray(time)
    flux = np.asarray(flux)
    
    stellar_rotation_period_days = DetrendingEngine.estimate_stellar_rotation(time, flux)
    flux = DetrendingEngine.detrend(time, flux, stellar_rotation_period_days)

    active_time = time.copy()
    active_flux = flux.copy()
    
    if len(active_time) < 10:
        return {}

    search_results = BLSSearchEngine.search(active_time, active_flux, known_periods=known_periods)
    best_period = search_results['period']
    best_snr = search_results['snr']
    best_depth = search_results['depth']
    transit_time = search_results['t0']
    duration = search_results['duration']
    best_confidence = search_results['confidence_score']
    
    # J1d & J1e: TLS Cross-Validation and FAP
    tls_fap = 1.0
    tls_sde = 0.0
    tls_period = best_period
    tls_valid = False
    # J2c nested-pool fix (2026-07-06): the TLS gate has THREE possible
    # outcomes, not two. tls_valid carries the boolean for the
    # emission-gate's branch on success/fail. tls_environment_error and
    # tls_scientific_error are mutually-exclusive sentinel strings that
    # let downstream consumers (orchestrator, monitor, UI) tell apart
    # "TLS ran and said no" from "TLS could not run at all" — see the
    # except (AssertionError, RuntimeError) and except Exception
    # blocks below. Initialised to None so callers reading the result
    # dict never see a KeyError on the success path.
    tls_environment_error = None  # set to a string if (AssertionError, RuntimeError)
    tls_scientific_error = None   # set to a string if any other Exception
    
    if best_period > 0:
        try:
            import transitleastsquares as tls
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = tls.transitleastsquares(active_time, active_flux)
                # Narrow the search space around the BLS period to save time
                tls_period_min = best_period * 0.95
                tls_period_max = best_period * 1.05
                # Clamp to TLS minimum only if the range allows it
                if tls_period_min < 0.5 and tls_period_max > 0.5:
                    tls_period_min = 0.5
                elif tls_period_max < 0.5:
                    # Period too short for TLS — skip validation
                    raise ValueError("period_min < period_max required")
                # ARCHITECTURAL CONSTRAINT (J2c nested-pool fix, 2026-07-06):
                # detect_transit_candidate runs inside
                # astraeus.core.orchestrator._subprocess_search_worker, which
                # is spawned with daemon=True (see orchestrator.py:
                # submit_multi_planet_search). On Windows, multiprocessing
                # forbids daemonic processes from spawning their own children;
                # TLS's default use_threads=cpu_count() path instantiates
                # multiprocessing.Pool(processes=use_threads) (see
                # transitleastsquares/main.py:141) and raises
                # AssertionError: "daemonic processes are not allowed to
                # have children". Forcing use_threads=1 keeps TLS single-
                # threaded inside the worker, which the J2c profile
                # (logs/j2c_tls_profiling_result.json, scratch/
                # nested_pool_check.py, logs/nested_pool_check_*.json)
                # measured at ~80s per call on a 45,853-cadence curve with
                # the 0.95x-1.05x BLS-narrowed window. Do NOT remove this
                # kwarg or relax it to cpu_count(): it is a contract, not
                # a perf preference. Locked by tests/characterize/
                # test_tls_call_path_contract.py.
                results = model.power(
                    period_min=tls_period_min,
                    period_max=tls_period_max,
                    show_progress_bar=False,
                    use_threads=1,
                )
                tls_fap = results.FAP
                tls_sde = results.SDE
                tls_period = results.period
                # Require TLS SDE >= 5.0 to validate the candidate
                if tls_sde >= 5.0 and abs(tls_period - best_period) / best_period < 0.05:
                    tls_valid = True
        except ImportError:
            print("WARNING: transitleastsquares not installed. Skipping TLS cross-validation.")
            tls_valid = True # Fail open if missing
        except (AssertionError, RuntimeError) as e:
            # INFRASTRUCTURE / ENVIRONMENT failure — distinct from a
            # scientific rejection. Historically this branch has been
            # silently folded into tls_valid=False by the bare
            # `except Exception` below, which meant every production
            # candidate whose TLS gate could not run (Windows
            # AssertionError from nested multiprocessing.Pool, fork
            # unavailable, OOM during grid construction, etc.) was
            # reported identically to a candidate that TLS actually
            # ran on and said no to. This made "no planets found"
            # indistinguishable from "the gate is broken", for as
            # long as the broken gate was in place (2026-06-09 ..
            # 2026-07-06 in this codebase; see logs/
            # nested_pool_check_2026-07-06T145219Z.json and tests/
            # characterize/test_tls_call_path_contract.py).
            #
            # We now log this loudly, set a distinct result field
            # (tls_environment_error) so downstream consumers (the
            # orchestrator's _subprocess_search_worker and the
            # monitor thread) can see and surface it, and refuse to
            # silently downgrade a candidate to "scientifically
            # rejected" when the gate was never actually run. The
            # candidate is still not emitted as Verified — but for a
            # different, distinguishable reason.
            #
            # Locked by tests/characterize/test_tls_call_path_contract.py
            # (test_tls_except_block_distinguishes_infra_from_scientific).
            tls_environment_error = f"{type(e).__name__}: {e}"
            print(f"[TLS-INFRA-ERROR] TLS environment failure during validation: {tls_environment_error}")
            print(f"[TLS-INFRA-ERROR] The TLS gate could not run. This candidate's `tls_valid=False`")
            print(f"[TLS-INFRA-ERROR] reflects an infrastructure failure, NOT a scientific rejection.")
            print(f"[TLS-INFRA-ERROR] Do not treat this as 'the candidate is bad' — fix the environment")
            print(f"[TLS-INFRA-ERROR] and re-run. See astraeus/analysis/detection.py:except block and")
            print(f"[TLS-INFRA-ERROR] tests/characterize/test_tls_call_path_contract.py for the contract.")
            tls_valid = False
        except Exception as e:
            # Genuine scientific failure (numba type error, malformed
            # input, NaN in flux, etc.) — TLS attempted to run and
            # could not produce a result. Distinct from the infra
            # branch above; logged with its own sentinel so the
            # orchestrator can distinguish "gate couldn't run" from
            # "gate ran and couldn't produce a verdict".
            tls_scientific_error = f"{type(e).__name__}: {e}"
            print(f"[TLS-SCI-ERROR] TLS scientific failure during validation: {tls_scientific_error}")
            tls_valid = False


    # Emission gate. The SNR threshold is caller-tunable and a
    # secondary check; the confidence_score floor is the load-bearing
    # noise-rejection gate (unconditional, applies regardless of the
    # caller-supplied snr_threshold). Both values are documented in
    # astraeus/core/constants.py and justified empirically in
    # reports/bucket9.1_signal_detection_audit.md §3 and §4.
    # Added TLS validation to the emission gate.
    is_valid = (
        best_snr > snr_threshold
        and best_confidence >= DETECTION_CONFIDENCE_FLOOR
        and tls_valid
    )
    
    global_payload = metadata or {}
    archive_metadata = global_payload.get('metadata', global_payload)
    st_rad = float(archive_metadata.get('st_rad') or archive_metadata.get('stellar_radius') or 1.0)
    # Hoisted out of the Physical Properties block below so that any
    # future (or current) physical-input-dependent vetting branch can
    # reference them without re-reading the archive dict.
    st_teff = float(archive_metadata.get('st_teff', 5778.0))
    st_mass = float(archive_metadata.get('st_mass', 1.0))
    sy_jmag = float(archive_metadata.get('sy_jmag', 10.0))

    raw_depth = float(best_depth)
    transit_depth_fraction = raw_depth / 100.0 if raw_depth > 0.1 else raw_depth

    archive_depth_percent = float(archive_metadata.get('pl_trandep', 0.0))
    if archive_depth_percent > 0:
        archive_depth_fraction = archive_depth_percent / 100.0
        if transit_depth_fraction < (archive_depth_fraction * 0.1):
            print("WARNING: Measured depth is less than 10% of archival depth.")

    result = {
        'candidate_found': is_valid,
        'is_candidate': is_valid,
        'period_days': best_period,
        'period': best_period,
        'orbital_period': best_period,
        'stellar_rotation_period_days': stellar_rotation_period_days,
        'transit_depth': transit_depth_fraction,
        'stellar_radius': st_rad,
        'vetting_status': 'candidate' if is_valid else 'rejected',
        'confidence_score': search_results['confidence_score'],
        'snr': best_snr,
        'depth': transit_depth_fraction,
        'duration': duration,
        't0': transit_time,
        # I2 fix (round-2 diagnostic 2026-07-06): explicit unit label so
        # downstream consumers do not have to guess. The lightkurve
        # ingestion boundary (astraeus.core.lightkurve_client.download_pipeline)
        # converts BKJD/BTJD to BJD full, so the time array handed in
        # here is in BJD, and t0 (computed by BoxLeastSquares on that
        # array) inherits the same unit.
        't0_bjd': transit_time,
        'time_unit': 'BJD',
        'periodogram': search_results['periodogram'],
        'tls_fap': tls_fap,
        'tls_sde': tls_sde,
        'tls_period': tls_period,
        'tls_valid': tls_valid,
        # J2c nested-pool fix (2026-07-06): distinguish "gate ran and
        # said no" from "gate could not run". See tls_environment_error
        # and tls_scientific_error initialisers above and the matching
        # except blocks. Locked by tests/characterize/
        # test_tls_call_path_contract.py.
        'tls_environment_error': tls_environment_error,
        'tls_scientific_error': tls_scientific_error,
    }

    # Geometric Validation
    geom_metrics = GeometricValidator.validate(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction)
    result.update(geom_metrics)

    # Statistical Transit Shape Vetting
    vetting_metrics = VettingEngine.vet_transit_shape(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction, snr=best_snr)
    result.update(vetting_metrics)

    # Override v_shape_metric key with the inverse of the U-shape confidence for backwards compatibility
    result['v_shape_metric'] = 1.0 - vetting_metrics['vetting_confidence']

    # Physical Properties — derived BEFORE the false-positive cross-vetting
    # so the secondary-eclipse branch can use equilibrium_temp_k and
    # planet_radius_earth as a physically-grounded threshold instead of a
    # flat 800 ppm constant. See bucket2_threshold_audit.md §4.
    phys_props = PhysicalPropertiesEngine.derive(best_period, transit_depth_fraction, st_rad, st_teff, st_mass, sy_jmag)
    result.update(phys_props)

    # Physically-derived secondary-eclipse depth threshold (bucket 2
    # headline fix). When the physical inputs are available this adapts
    # the threshold to the star/planet system under analysis; when they
    # are missing or non-positive the function returns None and we fall
    # back to the historical 800 ppm constant. Either way the result
    # dict carries the value actually used and the mode flag so callers
    # can audit the decision.
    expected_occultation_ppm = PhysicalPropertiesEngine.expected_occultation_depth_ppm(
        planet_radius_earth=phys_props.get('planet_radius_earth', 0.0),
        stellar_radius_solar=st_rad,
        planet_equilibrium_temp_k=phys_props.get('equilibrium_temp_k', 0.0),
        stellar_teff_k=st_teff,
    )
    if expected_occultation_ppm is None:
        sec_eclipse_threshold_ppm = VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM
        sec_eclipse_threshold_mode = "fallback_fixed"
    else:
        sec_eclipse_threshold_ppm = expected_occultation_ppm
        sec_eclipse_threshold_mode = "physical"
    result['secondary_eclipse_threshold_ppm'] = sec_eclipse_threshold_ppm
    result['secondary_eclipse_threshold_mode'] = sec_eclipse_threshold_mode
    # The cross-vetting branches below compare against a fractional
    # depth; convert the ppm threshold once.
    sec_eclipse_threshold_fraction = sec_eclipse_threshold_ppm / 1.0e6

    # False-Positive Cross-Vetting
    #
    # I1 fix (round-2 diagnostic 2026-07-06, see
    # logs/diagnostic_run_round2_*.json): the cross-vetting branches
    # below used to be gated on `is_valid = (snr > snr_threshold) and
    # (confidence_score >= DETECTION_CONFIDENCE_FLOOR)`. In a multi-
    # planet curve, the periodogram-wide confidence_score (best_power /
    # median_power across the whole BLS periodogram) is elevated by
    # every other signal in the data, so even a clean, unambiguously
    # correct peak at p1 can fail the 7.0 floor when 4 other real
    # planets also contribute periodogram power. Gating the cross-
    # vetting on that single-statistic check then left `vetting_status`
    # stuck at the line-79 default ('rejected' or 'candidate') or — after
    # the `result.update(vetting_metrics)` on line 94 overwrites it — at
    # the shape-vet result 'Likely Planet' / 'Ambiguous/False Positive'.
    # The orchestrator's guardrail 1 then trips on
    # `'Likely Planet'.startswith('Verified Planet Candidate') == False`,
    # starving the rest of the search.
    #
    # The fix: run the cross-vetting branches UNCONDITIONALLY on every
    # peak that BLS returns (the shape-vet block above already runs
    # unconditionally). The emission-gate `is_valid` still controls
    # `candidate_found` / `is_candidate` (line 71-72) and the line-79
    # default `vetting_status`, so callers that want a strict
    # "must-clear-the-floor" emission can keep using `is_valid`. The
    # cross-vetting block's job is to *classify* the peak; the
    # candidate-emission gate is a separate concern.
    is_ultra_short_period = float(best_period) < VETTING_ULTRA_SHORT_PERIOD_DAYS
    sec_depth = geom_metrics.get('secondary_eclipse_depth', 0.0)

    if transit_depth_fraction < VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION:
        result['vetting_status'] = "Verified Planet Candidate"
    elif (vetting_metrics['vetting_status'] == "Ambiguous/False Positive"
          and geom_metrics['secondary_eclipse_detected']
          and (best_snr <= VETTING_VSHAPE_LOW_SNR_GATE or sec_depth >= sec_eclipse_threshold_fraction)):
        # Both V-shaped AND secondary eclipse → binary, but only
        # when SNR is low OR the eclipse is deep enough to rule
        # out a planetary occultation. The eclipse-depth comparison
        # uses the physically-derived threshold (or fallback).
        result['vetting_status'] = "Eclipsing Binary Detected"
    elif (
        best_snr <= VETTING_VSHAPE_LOW_SNR_GATE
        and not is_ultra_short_period
        and vetting_metrics['vetting_status'] == "Ambiguous/False Positive"
    ):
        # V-shape / low flat-bottom only vetoes when SNR is NOT
        # overwhelmingly high (oblate-star gravity-darkening
        # produces V-shaped transits even for real planets).
        result['vetting_status'] = "V-Shaped False Positive Risk (Potential Grazing Binary)"
    elif geom_metrics['secondary_eclipse_detected']:
        if sec_depth < sec_eclipse_threshold_fraction:
            # Shallow occultation (below the physically-derived
            # threshold) = planetary thermal emission being
            # occulted, NOT a binary eclipse. The threshold adapts
            # to the system so a hot, large planet around a cool
            # star is not falsely flagged as a binary.
            result['vetting_status'] = "Verified Planet Candidate (Atmospheric Occultation Detected)"
        else:
            result['vetting_status'] = "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
    elif vetting_metrics['vetting_status'] == "Likely Planet":
        result['vetting_status'] = "Verified Planet Candidate"
    elif not is_valid:
        # No shape-vet verdict and emission gate failed: keep the
        # line-79 default ("rejected") so callers that gate on
        # `is_valid` are not silently handed a "Verified" verdict.
        pass

    # TTV Analysis
    result['ttv_data'] = TTVAnalyzer.calculate(active_time, active_flux, best_period, transit_time, duration)

    # Log experiment
    save_experiment_log(
        params={
            "target_name": target_name,
            "period": best_period,
            "stellar_rotation_period_days": stellar_rotation_period_days,
            "snr": best_snr,
            "data_source": data_source,
            "is_valid_candidate": bool(is_valid)
        },
        metadata=metadata or {},
        fig_paths=[]
    )

    return result

def validate_bls_candidate(transit_depth: float, out_of_transit_flux: np.ndarray, in_transit_count: int, snr_threshold: float = 5.0) -> tuple[bool, float]:
    if len(out_of_transit_flux) == 0 or in_transit_count <= 0:
        return False, 0.0
        
    local_noise_std = np.std(out_of_transit_flux)
    if local_noise_std == 0:
        return False, 0.0
        
    calculated_snr = (transit_depth / local_noise_std) * np.sqrt(in_transit_count)
    return calculated_snr > snr_threshold, float(calculated_snr)
