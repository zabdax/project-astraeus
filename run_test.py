"""
Kepler-90 (KIC 11442793) Multi-Planet Search - Full 5-Pass Extraction
Target 1 of the multi-planet discovery roadmap.
Tests dynamic window scaling and duplicate-period prevention.
"""
import sys
import json
import time as time_mod
import numpy as np

print("=" * 70)
print("PROJECT ASTRAEUS - Multi-Planet Discovery Engine")
print("Target: Kepler-90 (KIC 11442793)")
print("Mode: Full 6-Pass Deep Extraction (Expanded Grid)")
print("=" * 70)

# Step 1: Load data
print("\n[Phase 1] Fetching Kepler-90 lightcurve from NASA archive...")
start_time = time_mod.time()

from astraeus.data.loader import load_nasa_lightcurve
t, f, e = load_nasa_lightcurve("KIC 11442793", mission="Kepler")

load_elapsed = time_mod.time() - start_time
print(f"[Phase 1] Data loaded: {len(t)} data points in {load_elapsed:.1f}s")
print(f"[Phase 1] Time span: {t.min():.2f} to {t.max():.2f} BKJD ({t.max() - t.min():.1f} days)")
print(f"[Phase 1] Flux range: [{f.min():.6f}, {f.max():.6f}]")

# Step 2: Build lightcurve payload
raw_lightcurve = {
    'time': t,
    'flux': f,
    'target_name': 'Kepler-90',
    'data_source': 'NASA Kepler Archive',
    'metadata': {}
}

# Step 3: Run multi-planet search
print(f"\n[Phase 2] Starting deep multi-planet search (max_signals=6, snr_floor=5.0)...")
search_start = time_mod.time()

from astraeus.core.orchestrator import run_multi_planet_search
results = run_multi_planet_search(raw_lightcurve, max_signals=6, snr_floor=5.0)

search_elapsed = time_mod.time() - search_start
total_elapsed = time_mod.time() - start_time

print(f"\n[Phase 3] Search completed in {search_elapsed:.1f}s (total runtime: {total_elapsed:.1f}s)")
print(f"[Phase 3] Total unique candidates discovered: {len(results)}")

# Step 4: Verify uniqueness
if results:
    periods = [r.get('period', 0) for r in results]
    print(f"\n[Verification] Discovered periods: {[f'{p:.4f}d' for p in periods]}")
    
    # Check for duplicates
    is_unique = True
    for i in range(len(periods)):
        for j in range(i + 1, len(periods)):
            ratio = periods[i] / periods[j] if periods[j] > 0 else 0
            if abs(ratio - 1.0) < 0.05:
                print(f"  WARNING: Duplicate detected! Candidate {i+1} ({periods[i]:.4f}d) ~ Candidate {j+1} ({periods[j]:.4f}d)")
                is_unique = False
    
    if is_unique:
        print("  [OK] All candidates have UNIQUE orbital periods. No duplicates detected.")
    
print(f"\n{'='*70}")
print("EXECUTION COMPLETE")
print(f"{'='*70}")
