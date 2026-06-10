import numpy as np

from astraeus.analysis.detrending import DetrendingEngine
from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.analysis.geometric_validation import GeometricValidator
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.analysis.ttv_analysis import TTVAnalyzer
from astraeus.analysis.logging import save_experiment_log

def detect_transit_candidate(time, flux, target_name="Unknown", data_source="Unknown", metadata=None, snr_threshold=5.0):
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
        
        is_valid = best_snr > snr_threshold
        
        global_payload = metadata or {}
        archive_metadata = global_payload.get('metadata', global_payload)
        st_rad = float(archive_metadata.get('st_rad') or archive_metadata.get('stellar_radius') or 1.0)
        
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

        # False-Positive Cross-Vetting
        if is_valid:
            is_ultra_short_period = float(best_period) < 1.5
            sec_depth = geom_metrics.get('secondary_eclipse_depth', 0.0)

            if transit_depth_fraction < 0.03:
                result['vetting_status'] = "Verified Planet Candidate"
            elif (geom_metrics['v_shape_metric'] > 0.85
                  and geom_metrics['secondary_eclipse_detected']
                  and (best_snr <= 20.0 or sec_depth >= 0.0008)):
                # Both V-shaped AND secondary eclipse → binary, but only
                # when SNR is low OR the eclipse is deep enough to rule
                # out a planetary occultation.
                result['vetting_status'] = "Eclipsing Binary Detected"
            elif (
                best_snr <= 20.0
                and not is_ultra_short_period
                and (geom_metrics['v_shape_metric'] > 0.8 or geom_metrics['flat_bottom_fraction'] < 0.05)
            ):
                # V-shape / low flat-bottom only vetoes when SNR is NOT
                # overwhelmingly high (oblate-star gravity-darkening
                # produces V-shaped transits even for real planets).
                result['vetting_status'] = "V-Shaped False Positive Risk (Potential Grazing Binary)"
            elif geom_metrics['secondary_eclipse_detected']:
                if sec_depth < 0.0008:
                    # Shallow occultation (<800 ppm) = planetary thermal
                    # emission being occulted, NOT a binary eclipse.
                    result['vetting_status'] = "Verified Planet Candidate (Atmospheric Occultation Detected)"
                else:
                    result['vetting_status'] = "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"

        # Physical Properties
        st_teff = float(archive_metadata.get('st_teff', 5778.0))
        st_mass = float(archive_metadata.get('st_mass', 1.0))
        sy_jmag = float(archive_metadata.get('sy_jmag', 10.0))
        phys_props = PhysicalPropertiesEngine.derive(best_period, transit_depth_fraction, st_rad, st_teff, st_mass, sy_jmag)
        result.update(phys_props)

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
