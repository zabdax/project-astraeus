import os
import sys
import time
import json
import traceback
import threading
import _thread
import faulthandler

faulthandler.enable()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from astraeus.core.ingestion import RemoteDiscoveryEngine
from astraeus.analysis.detection import detect_transit_candidate
import numpy as np

class TimeoutEnforcer:
    def __init__(self, timeout: float = 30.0, label: str = "Component"):
        self.timeout = timeout
        self.label = label
        self._timer = None
        self._t0 = 0.0

    def _on_timeout(self):
        print(f"\n[TIMEOUT] {self.label} exceeded {self.timeout}s!", file=sys.stderr)
        faulthandler.dump_traceback(file=sys.stderr)
        _thread.interrupt_main()

    def __enter__(self):
        self._t0 = time.perf_counter()
        self._timer = threading.Timer(self.timeout, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._timer is not None:
            self._timer.cancel()
        if exc_type is KeyboardInterrupt:
            raise TimeoutError(f"[TIMEOUT] {self.label}")
        return False

def run_matrix():
    matrix = [
        # Phase 1
        (1, "WASP-12 b", "NASA Exoplanet Archive", 1.5),
        (1, "Kepler-13 b", "NASA Exoplanet Archive", 1.5),
        (1, "HAT-P-11 b", "NASA Exoplanet Archive", 1.5),
        # Phase 2
        (2, "WASP-12 b", "TESS", 30.0),
        (2, "Kepler-13 b", "TESS", 30.0),
        (2, "HAT-P-11 b", "TESS", 30.0),
        # Phase 3
        (3, "WASP-12 b", "Kepler", 30.0),
        (3, "Kepler-13 b", "Kepler", 30.0),
        (3, "HAT-P-11 b", "Kepler", 30.0),
        # Phase 4
        (4, "Kepler-13 b", "Combined Baseline (Kepler + TESS)", 30.0),
        (4, "HAT-P-11 b", "Combined Baseline (Kepler + TESS)", 30.0)
    ]

    report = []
    
    for phase, target, source, timeout_limit in matrix:
        print(f"\n{'='*50}\nExecuting Phase {phase}: {target} | {source}\n{'='*50}")
        
        test_id = f"{target}_{source}".replace(" ", "_").upper()
        
        block = {
            "test_id": test_id,
            "execution_status": "PENDING",
            "execution_time_seconds": 0.00,
            "error_traceback": None,
            "metadata_synchronization": {
                "archive_stellar_radius": 0.00,
                "pipeline_stellar_radius": 0.00,
                "drift_detected": False
            },
            "analytical_layer_telemetry": {
                "layer_1_arrays_shape": [],
                "layer_2_measured_transit_depth_fraction": 0.00000,
                "layer_3_calculated_period_days": 0.00000,
                "layer_4_v_shape_metric": 0.00,
                "layer_4_vetting_classification": "",
                "layer_5_planet_radius_earth": 0.00,
                "layer_5_jwst_tsm_score": 0.00,
                "layer_6_ttv_datapoints_compiled": 0
            },
            "cross_ai_validation_metrics": {
                "measured_vs_archival_period_delta_pct": 0.00,
                "measured_vs_archival_depth_ratio": 0.00,
                "signal_to_noise_ratio": 0.00
            }
        }
        
        t0 = time.perf_counter()
        try:
            with TimeoutEnforcer(timeout_limit, f"Phase {phase}: {target} - {source}"):
                data = RemoteDiscoveryEngine._fetch_data_impl(target, source)
                
                status = data.get("status", "unknown")
                meta = data.get("metadata", {})
                
                arch_st_rad = meta.get("st_rad", 0.0)
                pipe_st_rad = meta.get("stellar_radius", 0.0)
                
                block["metadata_synchronization"]["archive_stellar_radius"] = float(arch_st_rad)
                block["metadata_synchronization"]["pipeline_stellar_radius"] = float(pipe_st_rad)
                block["metadata_synchronization"]["drift_detected"] = abs(arch_st_rad - pipe_st_rad) > 0.0001
                
                if phase == 1:
                    assert "st_rad" in meta, "Root key 'st_rad' missing"
                    assert "pl_orbper" in meta, "Root key 'pl_orbper' missing"
                    if status == "no_time_series":
                        block["execution_status"] = "SUCCESS"
                    else:
                        block["execution_status"] = "FAILED"
                        block["error_traceback"] = f"Expected 'no_time_series', got '{status}'"
                
                elif phase == 2:
                    if status == "success":
                        t_arr = data["time"]
                        f_arr = data["flux"]
                        block["analytical_layer_telemetry"]["layer_1_arrays_shape"] = list(t_arr.shape)
                        
                        candidates = detect_transit_candidate(t_arr, f_arr, target, source, meta)
                        if candidates:
                            cand = candidates[0].get("candidate_1", {})
                            assert cand.get("planet_radius_earth", 0.0) > 0, "Mandel-Agol output invalid (<=0)"
                            
                            block["analytical_layer_telemetry"].update({
                                "layer_2_measured_transit_depth_fraction": cand.get("transit_depth", 0.0),
                                "layer_3_calculated_period_days": cand.get("period_days", 0.0),
                                "layer_4_v_shape_metric": cand.get("v_shape_metric", 0.0),
                                "layer_4_vetting_classification": cand.get("vetting_status", ""),
                                "layer_5_planet_radius_earth": cand.get("planet_radius_earth", 0.0),
                                "layer_5_jwst_tsm_score": cand.get("jwst_tsm_score", 0.0),
                                "layer_6_ttv_datapoints_compiled": len(cand.get("ttv_data", []))
                            })
                            
                            meas_per = cand.get("period_days", 0.0)
                            arch_per = meta.get("orbital_period", 0.0)
                            if arch_per > 0:
                                delta_pct = abs(meas_per - arch_per) / arch_per * 100
                            else:
                                delta_pct = 0.0
                                
                            meas_depth = cand.get("transit_depth", 0.0)
                            arch_depth = meta.get("transit_depth", 0.0) / 1e6
                            if arch_depth > 0:
                                depth_ratio = meas_depth / arch_depth
                            else:
                                depth_ratio = 0.0
                                
                            block["cross_ai_validation_metrics"].update({
                                "measured_vs_archival_period_delta_pct": delta_pct,
                                "measured_vs_archival_depth_ratio": depth_ratio,
                                "signal_to_noise_ratio": cand.get("snr", 0.0)
                            })
                        block["execution_status"] = "SUCCESS"
                    else:
                        block["execution_status"] = "FAILED"
                        block["error_traceback"] = f"Ingestion returned status: {status}"

                elif phase == 3:
                    if target == "WASP-12 b":
                        if status == "no_time_series":
                            block["execution_status"] = "SUCCESS"
                        else:
                            block["execution_status"] = "FAILED"
                            block["error_traceback"] = f"Expected fallback 'no_time_series', got '{status}'"
                    else:
                        if status == "success":
                            t_arr = data["time"]
                            f_arr = data["flux"]
                            block["analytical_layer_telemetry"]["layer_1_arrays_shape"] = list(t_arr.shape)
                            candidates = detect_transit_candidate(t_arr, f_arr, target, source, meta)
                            if candidates:
                                cand = candidates[0].get("candidate_1", {})
                                assert cand.get("transit_depth", 0.0) > 0, "Signal squashed by detrending"
                                
                                block["analytical_layer_telemetry"].update({
                                    "layer_2_measured_transit_depth_fraction": cand.get("transit_depth", 0.0),
                                    "layer_3_calculated_period_days": cand.get("period_days", 0.0),
                                    "layer_4_v_shape_metric": cand.get("v_shape_metric", 0.0),
                                    "layer_4_vetting_classification": cand.get("vetting_status", ""),
                                    "layer_5_planet_radius_earth": cand.get("planet_radius_earth", 0.0),
                                    "layer_5_jwst_tsm_score": cand.get("jwst_tsm_score", 0.0),
                                    "layer_6_ttv_datapoints_compiled": len(cand.get("ttv_data", []))
                                })
                                
                                meas_per = cand.get("period_days", 0.0)
                                arch_per = meta.get("orbital_period", 0.0)
                                if arch_per > 0:
                                    delta_pct = abs(meas_per - arch_per) / arch_per * 100
                                else:
                                    delta_pct = 0.0
                                    
                                meas_depth = cand.get("transit_depth", 0.0)
                                arch_depth = meta.get("transit_depth", 0.0) / 1e6
                                if arch_depth > 0:
                                    depth_ratio = meas_depth / arch_depth
                                else:
                                    depth_ratio = 0.0
                                    
                                block["cross_ai_validation_metrics"].update({
                                    "measured_vs_archival_period_delta_pct": delta_pct,
                                    "measured_vs_archival_depth_ratio": depth_ratio,
                                    "signal_to_noise_ratio": cand.get("snr", 0.0)
                                })
                            block["execution_status"] = "SUCCESS"
                        else:
                            block["execution_status"] = "FAILED"
                            block["error_traceback"] = f"Ingestion returned status: {status}"
                            
                elif phase == 4:
                    if status == "success":
                        t_arr = data["time"]
                        f_arr = data["flux"]
                        block["analytical_layer_telemetry"]["layer_1_arrays_shape"] = list(t_arr.shape)
                        candidates = detect_transit_candidate(t_arr, f_arr, target, source, meta)
                        if candidates:
                            cand = candidates[0].get("candidate_1", {})
                            assert len(cand.get("ttv_data", [])) > 0, "Layer 6 TTV points not compiled"
                            
                            block["analytical_layer_telemetry"].update({
                                "layer_2_measured_transit_depth_fraction": cand.get("transit_depth", 0.0),
                                "layer_3_calculated_period_days": cand.get("period_days", 0.0),
                                "layer_4_v_shape_metric": cand.get("v_shape_metric", 0.0),
                                "layer_4_vetting_classification": cand.get("vetting_status", ""),
                                "layer_5_planet_radius_earth": cand.get("planet_radius_earth", 0.0),
                                "layer_5_jwst_tsm_score": cand.get("jwst_tsm_score", 0.0),
                                "layer_6_ttv_datapoints_compiled": len(cand.get("ttv_data", []))
                            })
                            
                            meas_per = cand.get("period_days", 0.0)
                            arch_per = meta.get("orbital_period", 0.0)
                            if arch_per > 0:
                                delta_pct = abs(meas_per - arch_per) / arch_per * 100
                            else:
                                delta_pct = 0.0
                                
                            meas_depth = cand.get("transit_depth", 0.0)
                            arch_depth = meta.get("transit_depth", 0.0) / 1e6
                            if arch_depth > 0:
                                depth_ratio = meas_depth / arch_depth
                            else:
                                depth_ratio = 0.0
                                
                            block["cross_ai_validation_metrics"].update({
                                "measured_vs_archival_period_delta_pct": delta_pct,
                                "measured_vs_archival_depth_ratio": depth_ratio,
                                "signal_to_noise_ratio": cand.get("snr", 0.0)
                            })
                        block["execution_status"] = "SUCCESS"
                    else:
                        block["execution_status"] = "FAILED"
                        block["error_traceback"] = f"Ingestion returned status: {status}"
                        
        except TimeoutError as te:
            block["execution_status"] = "TIMEOUT"
            block["error_traceback"] = str(te)
        except Exception as e:
            block["execution_status"] = "FAILED"
            block["error_traceback"] = traceback.format_exc()
        
        block["execution_time_seconds"] = round(time.perf_counter() - t0, 3)
        if phase == 1 and block["execution_time_seconds"] >= 1.5:
            # Note: due to network variability, this might flake, but user requested strict < 1.5s
            # We'll just mark it FAILED and note the time.
            block["execution_status"] = "FAILED"
            block["error_traceback"] = f"Phase 1 execution time {block['execution_time_seconds']}s >= 1.5s limit"

        report.append(block)
        print(f"Status: {block['execution_status']} in {block['execution_time_seconds']}s")

    os.makedirs(os.path.join(os.path.dirname(__file__), 'reports'), exist_ok=True)
    report_path = os.path.join(os.path.dirname(__file__), 'reports', 'ai_audit_payload.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
        
    print(f"\nMatrix completed. Report saved to {report_path}")
    print("\n--- JSON PAYLOAD ---\n")
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    run_matrix()
