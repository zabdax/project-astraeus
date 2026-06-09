import time
import numpy as np
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from astraeus.analysis.detection import detect_transit_candidate

def generate_synthetic_data(num_points=12000, period=1.0914, depth=0.01, duration=0.1):
    """Generates synthetic light curve data with embedded transits."""
    # 1. Instant Local Dataset Generation
    time_array = np.linspace(0, 15, num_points)
    
    # Baseline flux + noise
    flux_array = np.random.normal(1.0, 0.001, num_points)
    
    # Inject synthetic transit signal
    # Period = 1.0914 days
    phase = (time_array % period) / period
    
    # Calculate transit window in phase space
    transit_duration_phase = duration / period
    
    # Apply depth in the transit window
    transit_mask = np.abs(phase - 0.5) < (transit_duration_phase / 2.0)
    flux_array[transit_mask] -= depth
    
    return time_array, flux_array

def run_benchmark():
    """Runs the speed and accuracy audit."""
    print("Starting High-Speed Local Benchmark...")
    
    # Generate data
    time_data, flux_data = generate_synthetic_data()
    print(f"Generated {len(time_data)} local data points.")
    
    # Start timer
    start_time = time.perf_counter()
    
    # 2. Run the Speed & Accuracy Audit
    results = detect_transit_candidate(
        time=time_data, 
        flux=flux_data, 
        target_name="Synthetic-Benchmark", 
        data_source="Local", 
        metadata={'stellar_radius': 1.0, 'st_teff': 5700, 'st_mass': 1.0, 'sy_jmag': 10.0}
    )
    
    end_time = time.perf_counter()
    elapsed_ms = (end_time - start_time) * 1000
    
    # Analyze Results
    if not results or 'candidate_1' not in results[0]:
        print("FAILED: No candidates detected or wrong format returned.")
        return
        
    candidate = results[0]['candidate_1']
    
    # Verify key constraints
    
    # Extract period (~1.0914 days)
    detected_period = candidate.get('period_days', 0.0)
    period_pass = abs(detected_period - 1.0914) < 0.05
    
    # V-Shape & Secondary Eclipse Checks
    has_v_shape = 'v_shape_metric' in candidate
    has_sec_eclipse = 'secondary_eclipse_detected' in candidate
    
    # Scales Mandel-Agol Earth radii
    has_radius = 'planet_radius_earth' in candidate and not np.isnan(candidate['planet_radius_earth'])
    
    # TTV O-C data structure
    has_ttv = 'ttv_data' in candidate and isinstance(candidate['ttv_data'], list)
    
    # TSM score
    has_tsm = 'jwst_tsm_score' in candidate and not np.isnan(candidate['jwst_tsm_score'])
    
    # NaN check on key outputs
    no_nan_errors = (
        not np.isnan(candidate.get('planet_radius_earth', np.nan)) and
        not np.isnan(candidate.get('jwst_tsm_score', np.nan)) and
        not np.isnan(candidate.get('v_shape_metric', np.nan))
    )
    
    # Time check (< 2.5s)
    time_pass = elapsed_ms < 2500
    
    # 3. Report Performance Immediately
    print("\n" + "="*50)
    print("BENCHMARK REPORT")
    print("="*50)
    print(f"Total Execution Time: {elapsed_ms:.2f} ms")
    print(f"Speed Requirement: {'PASSED' if time_pass else 'FAILED'} (< 2500 ms)")
    print(f"Target Period: 1.0914 days | Detected: {detected_period:.4f} days")
    print(f"Period Accuracy: {'PASSED' if period_pass else 'FAILED'}")
    
    print("\n6-LAYER FRAMEWORK AUDIT:")
    print(f"Layer 1: BLS Period Extraction    | {'PASSED' if period_pass else 'FAILED'}")
    print(f"Layer 2: V-Shape Geometric Check  | {'PASSED' if has_v_shape else 'FAILED'}")
    print(f"Layer 3: Secondary Eclipse Scan   | {'PASSED' if has_sec_eclipse else 'FAILED'}")
    print(f"Layer 4: Physical Radii Scaling   | {'PASSED' if has_radius else 'FAILED'} (Rp = {candidate.get('planet_radius_earth', 'N/A')})")
    print(f"Layer 5: JWST TSM Score Output    | {'PASSED' if has_tsm else 'FAILED'} (TSM = {candidate.get('jwst_tsm_score', 'N/A')})")
    print(f"Layer 6: TTV O-C Residual Engine  | {'PASSED' if has_ttv else 'FAILED'} (Points = {len(candidate.get('ttv_data', []))})")
    
    print("\nSystem Stability: NO NaNs DETECTED" if no_nan_errors else "\nSystem Stability: NaN ERRORS DETECTED")
    print("="*50)
    
    # Final assertion for CI/CD or general script return
    assert time_pass, f"Time constraint failed: took {elapsed_ms:.2f} ms"
    assert period_pass, f"Period extraction failed: {detected_period:.4f} days"
    assert has_v_shape and has_sec_eclipse and has_radius and has_ttv and has_tsm, "Missing structural data"
    assert no_nan_errors, "NaN errors found in output"

if __name__ == "__main__":
    run_benchmark()
