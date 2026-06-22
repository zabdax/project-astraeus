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

def detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=DETECTION_SNR_THRESHOLD_DEFAULT):
    time = np.asarray(time)
    flux = np.asarray(flux)
    
    stellar_rotation_period_days = DetrendingEngine.estimate_stellar_rotation(time, flux)
    flux = DetrendingEngine.detrend(time, flux, stellar_rotation_period_days)

    active_time = time.copy()
    active_flux = flux.copy()
    
    candidates = []

    for iteration in range(1, 4):
        if len(active_time) < 10:
            break

        search_results = BLSSearchEngine.search(active_time, active_flux)
        best_period = search_results['period']
        best_snr = search_results['snr']
        best_depth = search_results['depth']
        transit_time = search_results['t0']
        duration = search_results['duration']
        best_confidence = search_results['confidence_score']

        # Emission gate. The SNR threshold is caller-tunable and a
        # secondary check; the confidence_score floor is the load-bearing
        # noise-rejection gate (unconditional, applies regardless of the
        # caller-supplied snr_threshold). Both values are documented in
        # astraeus/core/constants.py and justified empirically in
        # reports/bucket9.1_signal_detection_audit.md §3 and §4.
        is_valid = (
            best_snr > snr_threshold
            and best_confidence >= DETECTION_CONFIDENCE_FLOOR
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
            'periodogram': search_results['periodogram']
        }

        # Geometric Validation
        geom_metrics = GeometricValidator.validate(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction)
        result.update(geom_metrics)

        # Statistical Transit Shape Vetting
        vetting_metrics = VettingEngine.vet_transit_shape(active_time, active_flux, best_period, transit_time, duration, transit_depth_fraction)
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
        if is_valid:
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

        # TTV Analysis
        result['ttv_data'] = TTVAnalyzer.calculate(active_time, active_flux, best_period, transit_time, duration)

        candidates.append({f'candidate_{iteration}': result})
        
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

        if is_valid and best_snr > 7.0:
            active_time, active_flux = BLSSearchEngine.mask_transit(active_time, active_flux, best_period, transit_time, duration)
        else:
            break

    return candidates[0]['candidate_1'] if candidates else {}

def validate_bls_candidate(transit_depth: float, out_of_transit_flux: np.ndarray, in_transit_count: int, snr_threshold: float = 5.0) -> tuple[bool, float]:
    if len(out_of_transit_flux) == 0 or in_transit_count <= 0:
        return False, 0.0
        
    local_noise_std = np.std(out_of_transit_flux)
    if local_noise_std == 0:
        return False, 0.0
        
    calculated_snr = (transit_depth / local_noise_std) * np.sqrt(in_transit_count)
    return calculated_snr > snr_threshold, float(calculated_snr)
