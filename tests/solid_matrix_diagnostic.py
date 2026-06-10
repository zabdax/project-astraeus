import _thread
import faulthandler
import json
import math
import multiprocessing
import os
import sys
import threading
import time
import traceback

import numpy as np

faulthandler.enable()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astraeus.analysis.bls_search import BLSSearchEngine
from astraeus.analysis.detrending import DetrendingEngine
from astraeus.analysis.geometric_validation import GeometricValidator
from astraeus.analysis.physical_properties import PhysicalPropertiesEngine
from astraeus.analysis.ttv_analysis import TTVAnalyzer
from astraeus.core.ingestion import RemoteDiscoveryEngine


R_SUN_TO_R_EARTH = 109.2

TARGETS = ("WASP-12 b", "Kepler-13 b", "HAT-P-11 b")
SOURCES = (
    "NASA Exoplanet Archive",
    "TESS",
    "Kepler",
    "Combined Baseline (Kepler + TESS)",
)

SOURCE_TIMEOUTS = {
    "NASA Exoplanet Archive": 20.0,
    "TESS": 300.0,
    "Kepler": 300.0,
    "Combined Baseline (Kepler + TESS)": 600.0,
}

PIPELINE_KEYS = (
    "layer_2_detrending_status",
    "layer_3_bls_search_status",
    "layer_4_vetting_status",
    "layer_5_physics_status",
    "layer_6_ttv_status",
)


class TimeoutEnforcer:
    def __init__(self, timeout: float = 45.0, label: str = "Pipeline"):
        self.timeout = timeout
        self.label = label
        self._timer = None

    def _on_timeout(self):
        print(f"\n[TIMEOUT] {self.label} exceeded {self.timeout}s", file=sys.stderr, flush=True)
        faulthandler.dump_traceback(file=sys.stderr)
        _thread.interrupt_main()

    def __enter__(self):
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


def _new_report_block(target: str, source: str) -> dict:
    test_id = f"{target}_{source}".replace(" ", "_").replace("+", "PLUS").upper()
    return {
        "test_id": test_id,
        "execution_status": "FAILED",
        "failed_at_layer": "None",
        "execution_time_seconds": 0.0,
        "error_traceback": None,
        "pipeline_flow_trace": {
            "layer_1_ingestion_status": "FAILED",
            "layer_2_detrending_status": "SKIPPED",
            "layer_3_bls_search_status": "SKIPPED",
            "layer_4_vetting_status": "SKIPPED",
            "layer_5_physics_status": "SKIPPED",
            "layer_6_ttv_status": "SKIPPED",
        },
        "scientific_telemetry": {
            "measured_transit_depth_fraction": 0.0,
            "calculated_period_days": 0.0,
            "vetting_classification": "",
            "calculated_planet_radius_earth": 0.0,
        },
    }


def _skip_after_failure(block: dict, failed_key: str) -> None:
    seen_failed = False
    for key in PIPELINE_KEYS:
        if key == failed_key:
            seen_failed = True
            continue
        if seen_failed:
            block["pipeline_flow_trace"][key] = "SKIPPED"


def _record_layer_failure(block: dict, layer_name: str, status_key: str) -> None:
    block["execution_status"] = "FAILED"
    block["failed_at_layer"] = layer_name
    block["pipeline_flow_trace"][status_key] = "FAILED"
    block["error_traceback"] = traceback.format_exc()
    _skip_after_failure(block, status_key)


def _as_valid_array(values, label: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or len(arr) < 10:
        raise ValueError(f"{label} must be a 1D array with at least 10 samples")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{label} contains NaN or infinite values")
    return arr


def _validate_ingestion_payload(payload: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    status = str(payload.get("status", "")).lower()
    if status != "success":
        raise ValueError(f"Layer 1 ingestion did not fetch live arrays; status={payload.get('status')!r}")

    time_arr = _as_valid_array(payload.get("time"), "Layer 1 time")
    flux_arr = _as_valid_array(payload.get("flux"), "Layer 1 flux")
    if len(time_arr) != len(flux_arr):
        raise ValueError("Layer 1 time and flux arrays have different lengths")

    finite_mask = np.isfinite(time_arr) & np.isfinite(flux_arr)
    if np.count_nonzero(finite_mask) < 10:
        raise ValueError("Layer 1 payload has fewer than 10 finite paired samples")

    return time_arr[finite_mask], flux_arr[finite_mask], payload.get("metadata", {}) or {}


def _validate_metadata_payload(payload: dict) -> dict:
    status = str(payload.get("status", "")).lower()
    if status not in {"no_time_series", "metadata_only", "success"}:
        raise ValueError(f"Layer 1 archive metadata fetch failed; status={payload.get('status')!r}")

    meta = payload.get("metadata", {}) or {}
    if not isinstance(meta, dict) or not meta:
        raise ValueError(f"Layer 1 archive metadata payload is empty; archive_error={payload.get('archive_error')!r}")
    for key in ("pl_orbper", "st_rad"):
        if key not in meta:
            raise ValueError(f"Layer 1 archive metadata missing key {key!r}")
    return meta


def _assert_normalized_flux(flux: np.ndarray) -> None:
    if not np.all(np.isfinite(flux)):
        raise ValueError("Layer 2 detrended flux contains NaN or infinite values")
    median_flux = float(np.median(flux))
    if not np.isclose(median_flux, 1.0, rtol=0.02, atol=0.02):
        raise ValueError(f"Layer 2 detrended flux median is {median_flux:.6f}, expected 1.0")


def _normalize_depth(raw_depth: float) -> float:
    depth = float(raw_depth)
    return depth / 100.0 if depth > 0.1 else depth


def _classify_vetting(depth_fraction: float, metrics: dict, orbital_period_days: float | None = None, snr: float = 0.0) -> str:
    is_ultra_short_period = orbital_period_days is not None and orbital_period_days < 1.5
    sec_depth = metrics.get("secondary_eclipse_depth", 0.0)

    if depth_fraction < 0.03:
        return "Verified Planet Candidate"
    if (metrics.get("v_shape_metric", 0.0) > 0.85
            and metrics.get("secondary_eclipse_detected")
            and (snr <= 20.0 or sec_depth >= 0.0008)):
        return "Eclipsing Binary Detected"
    if (
        snr <= 20.0
        and not is_ultra_short_period
        and (metrics.get("v_shape_metric", 0.0) > 0.8 or metrics.get("flat_bottom_fraction", 1.0) < 0.05)
    ):
        return "V-Shaped False Positive Risk (Potential Grazing Binary)"
    if metrics.get("secondary_eclipse_detected"):
        if sec_depth < 0.0008:
            return "Verified Planet Candidate (Atmospheric Occultation Detected)"
        return "Eclipsing Binary Detected (Secondary Eclipse at Phase 0.5)"
    return "Planet Candidate Requires Follow-Up"


def _stellar_radius(meta: dict) -> float:
    return float(meta.get("st_rad") or meta.get("stellar_radius") or 0.0)


def _print_handoff(layer: int, message: str) -> None:
    print(f"[Layer {layer}] {message}", flush=True)


def run_cascade_for_track(target: str, source: str, timeout_limit: float = 45.0) -> dict:
    block = _new_report_block(target, source)
    started = time.perf_counter()
    current_layer = "Layer_1"

    print(f"\n{'=' * 72}", flush=True)
    print(f"Executing cascade: {target} | {source}", flush=True)
    print(f"{'=' * 72}", flush=True)

    try:
        with TimeoutEnforcer(timeout_limit, f"{target} | {source}"):
            _print_handoff(1, f"Fetching live payload from {source}")
            payload = RemoteDiscoveryEngine._fetch_data_impl(target, source)
            if source == "NASA Exoplanet Archive":
                meta = _validate_metadata_payload(payload)
                block["pipeline_flow_trace"]["layer_1_ingestion_status"] = "SUCCESS"
                block["execution_status"] = "SUCCESS"
                _print_handoff(
                    1,
                    "SUCCESS: archive metadata fetched; time-series analysis layers skipped for metadata-only source",
                )
                return block

            if str(payload.get("status", "")).lower() == "no_time_series" and not payload.get("mast_error"):
                block["pipeline_flow_trace"]["layer_1_ingestion_status"] = "NO_TIME_SERIES"
                block["execution_status"] = "SKIPPED"
                _print_handoff(1, f"NO DATA: {source} has no live arrays for {target}; analysis layers skipped")
                return block

            time_arr, flux_arr, meta = _validate_ingestion_payload(payload)
            block["pipeline_flow_trace"]["layer_1_ingestion_status"] = "SUCCESS"
            _print_handoff(1, f"SUCCESS: {len(time_arr)} samples fetched; forwarding raw arrays to Layer 2")

            try:
                current_layer = "Layer_2"
                rotation_period = DetrendingEngine.estimate_stellar_rotation(time_arr, flux_arr)
                clean_flux = DetrendingEngine.detrend(time_arr, flux_arr, rotation_period)
                clean_flux = np.asarray(clean_flux, dtype=float)
                _assert_normalized_flux(clean_flux)
                block["pipeline_flow_trace"]["layer_2_detrending_status"] = "SUCCESS"
                _print_handoff(2, f"SUCCESS: normalized flux median={np.median(clean_flux):.6f}; forwarding to BLS")
            except Exception:
                _record_layer_failure(block, "Layer_2", "layer_2_detrending_status")
                return block

            try:
                current_layer = "Layer_3"
                bls_result = BLSSearchEngine.search(time_arr, clean_flux)
                period_days = float(bls_result.get("period", 0.0))
                if not math.isfinite(period_days) or period_days <= 0:
                    raise ValueError(f"Layer 3 BLS returned invalid period: {period_days!r}")
                depth_fraction = _normalize_depth(bls_result.get("depth", 0.0))
                if not math.isfinite(depth_fraction) or depth_fraction <= 0:
                    raise ValueError(f"Layer 3 BLS returned invalid depth: {depth_fraction!r}")
                block["pipeline_flow_trace"]["layer_3_bls_search_status"] = "SUCCESS"
                block["scientific_telemetry"]["calculated_period_days"] = round(period_days, 5)
                block["scientific_telemetry"]["measured_transit_depth_fraction"] = round(depth_fraction, 5)
                _print_handoff(3, f"SUCCESS: period={period_days:.5f}d depth={depth_fraction:.6f}; forwarding profile to vetting")
            except Exception:
                _record_layer_failure(block, "Layer_3", "layer_3_bls_search_status")
                return block

            try:
                current_layer = "Layer_4"
                duration = float(bls_result.get("duration", 0.0))
                transit_time = float(bls_result.get("t0", 0.0))
                if duration <= 0 or not math.isfinite(duration):
                    raise ValueError(f"Layer 4 received invalid duration: {duration!r}")
                geom_metrics = GeometricValidator.validate(
                    time_arr,
                    clean_flux,
                    period_days,
                    transit_time,
                    duration,
                    depth_fraction,
                )
                classification = _classify_vetting(depth_fraction, geom_metrics, period_days, snr=float(bls_result.get("snr", 0.0)))
                if not isinstance(classification, str) or not classification.strip():
                    raise ValueError("Layer 4 failed to assign a classification string")
                block["pipeline_flow_trace"]["layer_4_vetting_status"] = "SUCCESS"
                block["scientific_telemetry"]["vetting_classification"] = classification
                _print_handoff(4, f"SUCCESS: {classification}; forwarding depth and stellar radius to physics")
            except Exception:
                _record_layer_failure(block, "Layer_4", "layer_4_vetting_status")
                return block

            try:
                current_layer = "Layer_5"
                st_rad = _stellar_radius(meta)
                if st_rad <= 0:
                    raise ValueError(f"Layer 5 missing archival stellar radius in metadata: {meta!r}")
                expected_radius = st_rad * math.sqrt(depth_fraction) * R_SUN_TO_R_EARTH
                phys = PhysicalPropertiesEngine.derive(
                    period_days,
                    depth_fraction,
                    st_rad,
                    float(meta.get("st_teff") or 5778.0),
                    float(meta.get("st_mass") or 1.0),
                    float(meta.get("sy_jmag") or 10.0),
                )
                model_radius = float(phys.get("planet_radius_earth", 0.0))
                if not np.isclose(model_radius, round(expected_radius, 4), rtol=0.0, atol=0.0001):
                    raise ValueError(
                        "Layer 5 radius scaling mismatch: "
                        f"model={model_radius}, expected={expected_radius:.4f}, constant={R_SUN_TO_R_EARTH}"
                    )
                if model_radius <= 0.1:
                    raise ValueError(f"Layer 5 planet radius too small: {model_radius:.4f} R_Earth")
                block["pipeline_flow_trace"]["layer_5_physics_status"] = "SUCCESS"
                block["scientific_telemetry"]["calculated_planet_radius_earth"] = round(model_radius, 2)
                _print_handoff(5, f"SUCCESS: radius={model_radius:.4f} R_Earth; forwarding transit epochs to TTV")
            except Exception:
                _record_layer_failure(block, "Layer_5", "layer_5_physics_status")
                return block

            try:
                current_layer = "Layer_6"
                ttv_data = TTVAnalyzer.calculate(time_arr, clean_flux, period_days, transit_time, duration)
                if not isinstance(ttv_data, list) or len(ttv_data) == 0:
                    raise ValueError("Layer 6 TTV compiler produced no renderable data points")
                if not all("epoch" in point and "ttv_residual_min" in point for point in ttv_data):
                    raise ValueError("Layer 6 TTV points are missing epoch or residual fields")
                block["pipeline_flow_trace"]["layer_6_ttv_status"] = "SUCCESS"
                block["execution_status"] = "SUCCESS"
                block["failed_at_layer"] = "None"
                _print_handoff(6, f"SUCCESS: compiled {len(ttv_data)} TTV residual points for rendering")
            except Exception:
                _record_layer_failure(block, "Layer_6", "layer_6_ttv_status")
                return block

    except TimeoutError as exc:
        block["execution_status"] = "TIMEOUT"
        block["failed_at_layer"] = current_layer
        block["error_traceback"] = str(exc)
        if current_layer == "Layer_1":
            block["pipeline_flow_trace"]["layer_1_ingestion_status"] = "FAILED"
        else:
            layer_key = {
                "Layer_2": "layer_2_detrending_status",
                "Layer_3": "layer_3_bls_search_status",
                "Layer_4": "layer_4_vetting_status",
                "Layer_5": "layer_5_physics_status",
                "Layer_6": "layer_6_ttv_status",
            }.get(current_layer)
            if layer_key:
                block["pipeline_flow_trace"][layer_key] = "FAILED"
                _skip_after_failure(block, layer_key)
    except Exception:
        block["execution_status"] = "FAILED"
        block["failed_at_layer"] = "None"
        block["error_traceback"] = traceback.format_exc()
        block["pipeline_flow_trace"]["layer_1_ingestion_status"] = "FAILED"

    finally:
        block["execution_time_seconds"] = round(time.perf_counter() - started, 3)

    return block


def _track_process_entry(target: str, source: str, timeout_limit: float, queue) -> None:
    queue.put(run_cascade_for_track(target, source, timeout_limit))


def _timeout_report_block(target: str, source: str, timeout_limit: float, elapsed: float) -> dict:
    block = _new_report_block(target, source)
    block["execution_status"] = "TIMEOUT"
    block["failed_at_layer"] = "None"
    block["execution_time_seconds"] = round(elapsed, 3)
    block["error_traceback"] = f"[TIMEOUT] Track exceeded hard process limit of {timeout_limit:.1f}s"
    return block


def run_track_with_hard_timeout(target: str, source: str, timeout_limit: float) -> dict:
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue(maxsize=1)
    started = time.perf_counter()
    process = ctx.Process(
        target=_track_process_entry,
        args=(target, source, timeout_limit, queue),
        daemon=True,
    )
    process.start()
    process.join(timeout_limit + 5.0)

    elapsed = time.perf_counter() - started
    if process.is_alive():
        process.terminate()
        process.join(5.0)
        if process.is_alive():
            process.kill()
            process.join(5.0)
        print(
            f"[TIMEOUT] {target} | {source} exceeded hard process limit; moving to next source",
            flush=True,
        )
        return _timeout_report_block(target, source, timeout_limit, elapsed)

    if not queue.empty():
        return queue.get()

    block = _new_report_block(target, source)
    block["execution_status"] = "FAILED"
    block["failed_at_layer"] = "None"
    block["execution_time_seconds"] = round(elapsed, 3)
    block["error_traceback"] = f"Track process exited without a report block; exit_code={process.exitcode}"
    return block


def run_matrix() -> list[dict]:
    report = []
    for target in TARGETS:
        for source in SOURCES:
            timeout_limit = SOURCE_TIMEOUTS.get(source, 45.0)
            block = run_track_with_hard_timeout(target, source, timeout_limit)
            report.append(block)
            print(
                f"Track result: {block['execution_status']} "
                f"failed_at={block['failed_at_layer']} "
                f"in {block['execution_time_seconds']}s",
                flush=True,
            )

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, "solid_audit_log.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print(f"\nCascading diagnostic completed. Report saved to {report_path}", flush=True)
    print("\n--- SOLID AUDIT LOG JSON ---", flush=True)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    run_matrix()
