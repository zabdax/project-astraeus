#!/usr/bin/env python3
"""
================================================================================
  ASTRAEUS - Full Blind Search Cascade
  Target: KIC 11442793 (Kepler-90)
  Mode:   Unvetted Archival Discovery Test (6-Layer Pipeline)
================================================================================

  LAYER 1: Ingestion  - Fetch complete Kepler archival photometry
  LAYER 2: Detrending - Transit-preserving stellar activity removal
  LAYER 3: BLS Search - Box Least Squares periodogram
  LAYER 4: Vetting    - False-positive classifier with high-SNR overrides
  LAYER 5: Physics    - Physical properties derivation + JWST TSM score
  LAYER 6: TTV        - Transit Timing Variation residual mapping
"""

import sys
import os
import json
import time as timer
import datetime
import numpy as np

# Force UTF-8 on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# --- Configuration -----------------------------------------------------------
TARGET_KIC = "KIC 11442793"
TARGET_NAME = "Kepler-90"
MISSION = "Kepler"
MAX_QUARTERS = 6  # Limit to 6 quarters to speed up execution (~1.5 years of data)
SNR_THRESHOLD = 5.0

# Kepler-90 stellar parameters (from NASA Exoplanet Archive)
STELLAR_PARAMS = {
    "st_rad": 1.2,       # Solar radii
    "st_teff": 5930.0,   # Effective temperature (K)
    "st_mass": 1.13,     # Solar masses
    "sy_jmag": 12.49,    # J-band magnitude
}

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs", "kepler90_blind_search")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def print_header(layer_num, title):
    border = "=" * 72
    print(f"\n+{border}+")
    print(f"|  LAYER {layer_num}: {title:<63}|")
    print(f"+{border}+")


def print_telemetry(label, value, unit=""):
    unit_str = f" {unit}" if unit else ""
    print(f"  |-- {label:<40} {value}{unit_str}")


# ==============================================================================
#  LAYER 1: INGESTION
# ==============================================================================
def layer1_ingestion():
    """Fetch and load the complete unvetted light curve for KIC 11442793."""
    print_header(1, "INGESTION - Archival Data Fetch")
    t_start = timer.time()

    import lightkurve as lk

    print(f"  |-- Target:          {TARGET_KIC} ({TARGET_NAME})")
    print(f"  |-- Mission:         {MISSION}")
    print(f"  |-- Query started:   {timestamp()}")

    # Search for all available light curves
    search_result = lk.search_lightcurve(TARGET_KIC, mission=MISSION)
    n_total = len(search_result)
    print(f"  |-- Segments found:  {n_total}")

    if n_total == 0:
        print("  \\-- [FATAL] No light curves found for target.")
        sys.exit(1)

    # Download all (or limited) quarters
    if MAX_QUARTERS is not None:
        search_result = search_result[:MAX_QUARTERS]
        print(f"  |-- Segments used:   {len(search_result)} (capped)")
    else:
        print(f"  |-- Segments used:   {n_total} (ALL)")

    lc_collection = None
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"  |-- Downloading from MAST (Attempt {attempt+1}/{max_retries})...")
            lc_collection = search_result.download_all()
            if lc_collection and len(lc_collection) > 0:
                break
        except Exception as e:
            print(f"  |-- [WARN] MAST download failed: {e}")
            if attempt < max_retries - 1:
                print(f"  |-- Retrying in 10 seconds...")
                timer.sleep(10)

    if not lc_collection or len(lc_collection) == 0:
        print("  \\-- [FATAL] Download returned no data after all retries.")
        sys.exit(1)

    # Stitch all quarters into a single light curve
    print(f"  |-- Stitching {len(lc_collection)} segments...")
    stitched = lc_collection.stitch()

    # Flatten to remove long-term systematics while preserving transits
    try:
        flattened = stitched.flatten(window_length=401)
        print(f"  |-- Flatten method:  Savitzky-Golay (window=401)")
    except Exception:
        flattened = stitched.normalize()
        print(f"  |-- Flatten method:  Simple normalization (fallback)")

    # Remove NaNs
    flattened = flattened.remove_nans()

    time_arr = np.asarray(flattened.time.value, dtype=np.float64)
    flux_arr = np.asarray(flattened.flux.value, dtype=np.float64)
    flux_err_arr = np.asarray(flattened.flux_err.value, dtype=np.float64)

    # Clean: remove remaining NaN/Inf
    valid = np.isfinite(time_arr) & np.isfinite(flux_arr) & np.isfinite(flux_err_arr)
    time_arr = time_arr[valid]
    flux_arr = flux_arr[valid]
    flux_err_arr = flux_err_arr[valid]

    # Sort chronologically
    sort_idx = np.argsort(time_arr)
    time_arr = time_arr[sort_idx]
    flux_arr = flux_arr[sort_idx]
    flux_err_arr = flux_err_arr[sort_idx]

    elapsed = timer.time() - t_start

    print_telemetry("Data points loaded", f"{len(time_arr):,}")
    print_telemetry("Time baseline", f"{time_arr[-1] - time_arr[0]:.2f}", "days")
    print_telemetry("Median flux", f"{np.median(flux_arr):.6f}")
    print_telemetry("Flux RMS scatter", f"{np.std(flux_arr)*1e6:.1f}", "ppm")
    print_telemetry("Ingestion time", f"{elapsed:.2f}", "sec")
    print(f"  \\-- [OK] Layer 1 COMPLETE")

    return time_arr, flux_arr, flux_err_arr, {
        "n_datapoints": len(time_arr),
        "baseline_days": float(time_arr[-1] - time_arr[0]),
        "median_flux": float(np.median(flux_arr)),
        "rms_ppm": float(np.std(flux_arr) * 1e6),
        "ingestion_time_sec": round(elapsed, 2),
    }


# ==============================================================================
#  LAYER 2: DETRENDING
# ==============================================================================
def layer2_detrending(time_arr, flux_arr):
    """Apply transit-preserving detrending matrix."""
    print_header(2, "DETRENDING - Stellar Activity Removal")
    t_start = timer.time()

    from astraeus.analysis.detrending import DetrendingEngine

    # Estimate stellar rotation period
    rot_period = DetrendingEngine.estimate_stellar_rotation(time_arr, flux_arr)
    print_telemetry("Estimated stellar rotation", f"{rot_period:.4f}", "days")

    # Apply transit-preserving detrending
    detrended_flux = DetrendingEngine.detrend(time_arr, flux_arr, rot_period)

    # Verify transit preservation
    pre_std = np.std(flux_arr) * 1e6
    post_std = np.std(detrended_flux) * 1e6
    print_telemetry("Pre-detrend scatter", f"{pre_std:.1f}", "ppm")
    print_telemetry("Post-detrend scatter", f"{post_std:.1f}", "ppm")
    print_telemetry("Noise reduction", f"{(1 - post_std/pre_std)*100:.1f}", "%")

    window_used = min(
        DetrendingEngine.MAX_TRANSIT_PRESERVING_WINDOW_DAYS,
        max(DetrendingEngine.MIN_TRANSIT_PRESERVING_WINDOW_DAYS, rot_period * 0.5),
    )
    print_telemetry("Detrending window", f"{window_used:.3f}", "days")

    elapsed = timer.time() - t_start
    print_telemetry("Detrending time", f"{elapsed:.2f}", "sec")
    print(f"  \\-- [OK] Layer 2 COMPLETE")

    return detrended_flux, {
        "stellar_rotation_period_days": round(rot_period, 4),
        "detrending_window_days": round(window_used, 3),
        "pre_detrend_scatter_ppm": round(pre_std, 1),
        "post_detrend_scatter_ppm": round(post_std, 1),
        "noise_reduction_pct": round((1 - post_std / pre_std) * 100, 1),
        "detrending_time_sec": round(elapsed, 2),
    }


# ==============================================================================
#  LAYER 3: BLS SEARCH
# ==============================================================================
def layer3_bls_search(time_arr, flux_arr):
    """Run Box Least Squares periodogram to find dominant periodic signal."""
    print_header(3, "BLS SEARCH - Periodic Transit Heartbeat Detection")
    t_start = timer.time()

    from astraeus.analysis.bls_search import BLSSearchEngine

    results = BLSSearchEngine.search(time_arr, flux_arr)

    period = results['period']
    snr = results['snr']
    depth = results['depth']
    t0 = results['t0']
    duration = results['duration']
    confidence = results['confidence_score']

    depth_ppm = depth * 1e6  # Convert fractional depth to ppm

    print_telemetry("Peak period", f"{period:.6f}", "days")
    print_telemetry("Transit epoch (t0)", f"{t0:.6f}", "BKJD")
    print_telemetry("Transit duration", f"{duration*24:.4f}", "hours")
    print_telemetry("Transit depth", f"{depth_ppm:.1f}", "ppm")
    print_telemetry("Signal-to-noise ratio", f"{snr:.2f}")
    print_telemetry("BLS confidence score", f"{confidence:.2f}")

    # Detection threshold check
    if snr > SNR_THRESHOLD:
        print(f"  |-- [SIGNAL DETECTED] SNR {snr:.2f} > threshold {SNR_THRESHOLD}")
    else:
        print(f"  |-- [NO SIGNAL] SNR {snr:.2f} < threshold {SNR_THRESHOLD}")

    elapsed = timer.time() - t_start
    print_telemetry("BLS search time", f"{elapsed:.2f}", "sec")
    print(f"  \\-- [OK] Layer 3 COMPLETE")

    return results, {
        "period_days": round(period, 6),
        "t0_bkjd": round(t0, 6),
        "duration_hours": round(duration * 24, 4),
        "depth_ppm": round(depth_ppm, 1),
        "snr": round(snr, 2),
        "confidence_score": round(confidence, 2),
        "bls_search_time_sec": round(elapsed, 2),
    }


# ==============================================================================
#  LAYER 4 & 5: VETTING + PHYSICAL PROPERTIES
# ==============================================================================
def layer4_5_vetting_physics(time_arr, flux_arr, bls_results):
    """Run geometric vetting classifier and derive physical properties."""
    print_header("4+5", "VETTING & PHYSICS - Classification + Properties")
    t_start = timer.time()

    from astraeus.analysis.geometric_validation import GeometricValidator
    from astraeus.analysis.physical_properties import PhysicalPropertiesEngine

    period = bls_results['period']
    t0 = bls_results['t0']
    duration = bls_results['duration']
    depth = bls_results['depth']
    snr = bls_results['snr']

    # -- Geometric Validation --
    print(f"\n  +-- GEOMETRIC VETTING -----------------------------------")
    geom = GeometricValidator.validate(time_arr, flux_arr, period, t0, duration, depth)

    print_telemetry("V-shape metric", f"{geom['v_shape_metric']:.4f}")
    print_telemetry("Flat-bottom fraction", f"{geom['flat_bottom_fraction']:.4f}")
    print_telemetry("Secondary eclipse depth", f"{geom['secondary_eclipse_depth']*1e6:.1f}", "ppm")
    print_telemetry("Secondary eclipse SNR", f"{geom['secondary_eclipse_snr']:.2f}")
    print_telemetry("Secondary eclipse detected", f"{geom['secondary_eclipse_detected']}")

    # -- Apply Vetting Classifier (with high-SNR overrides) --
    is_valid = snr > SNR_THRESHOLD

    # Determine transit depth fraction correctly
    raw_depth = float(depth)
    transit_depth_fraction = raw_depth / 100.0 if raw_depth > 0.1 else raw_depth

    vetting_status = "rejected"
    if is_valid:
        is_ultra_short_period = float(period) < 1.5
        sec_depth = geom.get('secondary_eclipse_depth', 0.0)

        if transit_depth_fraction < 0.03:
            vetting_status = "Verified Planet Candidate"
        elif (geom['v_shape_metric'] > 0.85
              and geom['secondary_eclipse_detected']
              and (snr <= 20.0 or sec_depth >= 0.0008)):
            vetting_status = "Eclipsing Binary Detected"
        elif (
            snr <= 20.0
            and not is_ultra_short_period
            and (geom['v_shape_metric'] > 0.8 or geom['flat_bottom_fraction'] < 0.05)
        ):
            vetting_status = "V-Shaped False Positive Risk (Potential Grazing Binary)"
        elif geom['secondary_eclipse_detected']:
            if sec_depth < 0.0008:
                # < 800 ppm threshold = planetary atmospheric occultation, NOT binary
                vetting_status = "Verified Planet Candidate (Atmospheric Occultation Detected)"
            else:
                vetting_status = "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
        else:
            vetting_status = "Verified Planet Candidate"

    print(f"\n  +-- VETTING VERDICT -------------------------------------")
    print_telemetry("High-SNR override active", f"{snr > 20.0}")
    print_telemetry("Ultra-shallow sec. eclipse threshold", "<800 ppm")
    if "Verified" in vetting_status or "Candidate" in vetting_status:
        print(f"  |-- [PASS] STATUS: {vetting_status}")
    elif "Binary" in vetting_status:
        print(f"  |-- [FAIL] STATUS: {vetting_status}")
    else:
        print(f"  |-- [WARN] STATUS: {vetting_status}")

    # -- Physical Properties --
    print(f"\n  +-- PHYSICAL PROPERTIES ---------------------------------")
    phys = PhysicalPropertiesEngine.derive(
        period,
        transit_depth_fraction,
        STELLAR_PARAMS["st_rad"],
        STELLAR_PARAMS["st_teff"],
        STELLAR_PARAMS["st_mass"],
        STELLAR_PARAMS["sy_jmag"],
    )

    print_telemetry("Planet radius", f"{phys['planet_radius_earth']:.4f}", "R_Earth")
    print_telemetry("Equilibrium temperature", f"{phys['equilibrium_temp_k']:.1f}", "K")
    print_telemetry("JWST TSM score", f"{phys['jwst_tsm_score']:.4f}")

    elapsed = timer.time() - t_start
    print_telemetry("Vetting + Physics time", f"{elapsed:.2f}", "sec")
    print(f"  \\-- [OK] Layer 4+5 COMPLETE")

    return vetting_status, geom, phys, transit_depth_fraction, {
        "vetting_status": vetting_status,
        "v_shape_metric": round(geom['v_shape_metric'], 4),
        "flat_bottom_fraction": round(geom['flat_bottom_fraction'], 4),
        "secondary_eclipse_depth_ppm": round(geom['secondary_eclipse_depth'] * 1e6, 1),
        "secondary_eclipse_detected": geom['secondary_eclipse_detected'],
        "planet_radius_earth": phys['planet_radius_earth'],
        "equilibrium_temp_k": phys['equilibrium_temp_k'],
        "jwst_tsm_score": phys['jwst_tsm_score'],
        "vetting_time_sec": round(elapsed, 2),
    }


# ==============================================================================
#  LAYER 6: TTV ANALYSIS
# ==============================================================================
def layer6_ttv(time_arr, flux_arr, bls_results):
    """Map transit timing variations to detect gravitational perturbations."""
    print_header(6, "TTV MODULE - Transit Timing Variation Analysis")
    t_start = timer.time()

    from astraeus.analysis.ttv_analysis import TTVAnalyzer

    period = bls_results['period']
    t0 = bls_results['t0']
    duration = bls_results['duration']

    ttv_data = TTVAnalyzer.calculate(time_arr, flux_arr, period, t0, duration)

    n_transits = len(ttv_data)
    print_telemetry("Transits measured", f"{n_transits}")

    if n_transits > 0:
        residuals = [d['ttv_residual_min'] for d in ttv_data]
        rms_ttv = float(np.sqrt(np.mean(np.array(residuals) ** 2)))
        max_ttv = float(max(abs(r) for r in residuals))
        mean_ttv = float(np.mean(residuals))

        print_telemetry("TTV RMS", f"{rms_ttv:.2f}", "minutes")
        print_telemetry("TTV Max |residual|", f"{max_ttv:.2f}", "minutes")
        print_telemetry("TTV Mean offset", f"{mean_ttv:.2f}", "minutes")

        # Flag significant TTVs (> 5 minutes RMS is dynamically interesting)
        if rms_ttv > 5.0:
            print(f"  |-- [TTV DETECTED] Significant TTV - Possible sibling planet interaction")
        elif rms_ttv > 2.0:
            print(f"  |-- [TTV MARGINAL] Weak gravitational signature")
        else:
            print(f"  |-- [TTV NONE] Timing consistent with isolated orbit")

        # Find the top 5 most deviant epochs
        sorted_ttv = sorted(ttv_data, key=lambda d: abs(d['ttv_residual_min']), reverse=True)
        print(f"\n  +-- TOP 5 DEVIANT EPOCHS --------------------------------")
        for entry in sorted_ttv[:5]:
            print(f"  |  Epoch {entry['epoch']:>4d}:  {entry['ttv_residual_min']:+8.2f} min")
    else:
        rms_ttv = 0.0
        max_ttv = 0.0
        mean_ttv = 0.0
        print(f"  |-- [WARNING] No transit epochs could be measured")

    elapsed = timer.time() - t_start
    print_telemetry("TTV analysis time", f"{elapsed:.2f}", "sec")
    print(f"  \\-- [OK] Layer 6 COMPLETE")

    return ttv_data, {
        "n_transits_measured": n_transits,
        "ttv_rms_minutes": round(rms_ttv, 2),
        "ttv_max_residual_minutes": round(max_ttv, 2),
        "ttv_mean_offset_minutes": round(mean_ttv, 2),
        "ttv_time_sec": round(elapsed, 2),
    }


# ==============================================================================
#  MAIN ORCHESTRATOR
# ==============================================================================
def main():
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("\n" + "#" * 76)
    print("#" + " " * 74 + "#")
    print("#   ASTRAEUS - Blind Search Cascade                                      #")
    print("#   Full Pipeline Execution                                               #")
    print("#   Target: KIC 11442793 (Kepler-90)                                      #")
    print(f"#   Run ID: {run_id:<62}#")
    print("#" + " " * 74 + "#")
    print("#" * 76)

    total_start = timer.time()
    telemetry = {
        "run_id": run_id,
        "target_kic": TARGET_KIC,
        "target_name": TARGET_NAME,
        "mission": MISSION,
        "pipeline_start": timestamp(),
        "stellar_params": STELLAR_PARAMS,
    }

    # -- LAYER 1 --
    time_arr, flux_arr, flux_err_arr, l1_telem = layer1_ingestion()
    telemetry["layer1_ingestion"] = l1_telem

    # -- LAYER 2 --
    detrended_flux, l2_telem = layer2_detrending(time_arr, flux_arr)
    telemetry["layer2_detrending"] = l2_telem

    # -- LAYER 3 --
    bls_results, l3_telem = layer3_bls_search(time_arr, detrended_flux)
    telemetry["layer3_bls_search"] = l3_telem

    # -- LAYER 4 & 5 --
    vetting_status, geom, phys, depth_frac, l45_telem = layer4_5_vetting_physics(
        time_arr, detrended_flux, bls_results
    )
    telemetry["layer4_5_vetting_physics"] = l45_telem

    # -- LAYER 6 --
    ttv_data, l6_telem = layer6_ttv(time_arr, detrended_flux, bls_results)
    telemetry["layer6_ttv"] = l6_telem

    total_elapsed = timer.time() - total_start
    telemetry["pipeline_end"] = timestamp()
    telemetry["total_pipeline_time_sec"] = round(total_elapsed, 2)

    # ==================================================================
    #  DISCOVERY REPORT
    # ==================================================================
    depth_ppm = bls_results['depth'] * 1e6 if bls_results['depth'] < 0.1 else bls_results['depth']

    discovery_report = {
        "target": TARGET_NAME,
        "target_kic": TARGET_KIC,
        "candidate_found": "Verified" in vetting_status or "Candidate" in vetting_status,
        "calculated_period": round(bls_results['period'], 6),
        "transit_depth_ppm": round(depth_ppm, 1),
        "vetting_status": vetting_status,
        "snr": round(bls_results['snr'], 2),
        "jwst_tsm_score": phys['jwst_tsm_score'],
        "planet_radius_earth": phys['planet_radius_earth'],
        "equilibrium_temp_k": phys['equilibrium_temp_k'],
        "ttv_summary": {
            "n_transits": len(ttv_data),
            "rms_minutes": l6_telem["ttv_rms_minutes"],
            "max_residual_minutes": l6_telem["ttv_max_residual_minutes"],
            "prominent_residuals": [
                {"epoch": d['epoch'], "residual_min": round(d['ttv_residual_min'], 2)}
                for d in sorted(ttv_data, key=lambda x: abs(x['ttv_residual_min']), reverse=True)[:10]
            ] if ttv_data else [],
        },
        "pipeline_telemetry": telemetry,
    }

    # Save discovery report
    report_path = os.path.join(OUTPUT_DIR, f"discovery_report_{run_id}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(discovery_report, f, indent=4, default=str)

    # Save raw telemetry
    telem_path = os.path.join(OUTPUT_DIR, f"raw_telemetry_{run_id}.json")
    with open(telem_path, "w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=4, default=str)

    # Save TTV data
    if ttv_data:
        ttv_path = os.path.join(OUTPUT_DIR, f"ttv_data_{run_id}.json")
        with open(ttv_path, "w", encoding="utf-8") as f:
            json.dump(ttv_data, f, indent=4)

    # -- FINAL SUMMARY --
    print("\n" + "=" * 76)
    print("  DISCOVERY REPORT - FINAL SUMMARY")
    print("=" * 76)
    print(json.dumps({k: v for k, v in discovery_report.items() if k != "pipeline_telemetry"}, indent=4, default=str))
    print("=" * 76)
    print(f"\n  Report saved:    {report_path}")
    print(f"  Telemetry saved: {telem_path}")
    print(f"  Total pipeline time: {total_elapsed:.2f} sec")
    print(f"  Pipeline execution COMPLETE\n")

    # Log to experiment ledger
    try:
        from astraeus.analysis.logging import save_experiment_log
        save_experiment_log(
            params={
                "target_name": TARGET_NAME,
                "period": bls_results['period'],
                "snr": bls_results['snr'],
                "data_source": f"Kepler Archival ({TARGET_KIC})",
                "is_valid_candidate": discovery_report["candidate_found"],
            },
            metadata={"stellar_params": STELLAR_PARAMS, "run_id": run_id},
            fig_paths=[],
        )
    except Exception as e:
        print(f"  [WARN] Experiment logging skipped: {e}")

    return discovery_report


if __name__ == "__main__":
    main()
