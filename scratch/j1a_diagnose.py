import numpy as np
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from astraeus.analysis.bls_search import BLSSearchEngine
from astropy.timeseries import BoxLeastSquares
from astropy.timeseries import LombScargle

def build_syn_longperiod():
    # 1240d baseline
    T_SPAN = 1240.0
    N_SAMPLES = 45000
    time = np.linspace(0, T_SPAN, N_SAMPLES)
    
    # Introduce ~10 day gaps every ~90 days to simulate Kepler quarter rolls
    mask = np.ones(N_SAMPLES, dtype=bool)
    for q in range(1, 14):
        gap_center = q * 90.0
        gap_mask = (time > gap_center - 5.0) & (time < gap_center + 5.0)
        mask[gap_mask] = False
    time = time[mask]
    n_kept = len(time)
    
    # 500 ppm noise
    rng = np.random.default_rng(42)
    flux = 1.0 + rng.normal(0, 5e-4, size=n_kept)
    
    # Inject 2 signals: 210.6d and 331.6d (matching Kepler-90g and Kepler-90h periods)
    # SNR ~ 15 -> depth ~ 15 * 5e-4 / sqrt(n_in_transit)
    # Let's say duration ~ 0.4d. N_in_transit ~ (0.4 / 1240) * 45000 * n_transits
    # For 210d, 5 transits. n_in_transit ~ 15 * 5 = 75. 
    # Depth = 15 * 5e-4 / sqrt(75) ~ 8.6e-4 ~ 860 ppm
    
    INJECTED = [
        ("p1", 210.6, 860, 50.0, 0.4),
        ("p2", 331.6, 1200, 100.0, 0.4)
    ]
    
    for name, period, depth_ppm, t0, dur in INJECTED:
        phase = ((time - t0) % period) - period / 2.0
        in_tr = np.abs(phase) < dur / 2.0
        flux[in_tr] -= depth_ppm / 1e6
        
    return time, flux

time, flux = build_syn_longperiod()

bls = BoxLeastSquares(time, flux)
periods = np.linspace(0.5, 450, 14000)
durations = np.array([0.01, 0.05, 0.1, 0.2, 0.4])
res = bls.power(periods, durations)

# 1. Compute power at true periods vs reported alias periods (from the orchestrator alias: 797.48d, 842.46d)
# We need to compute it directly using BLS
test_periods = [210.6, 331.6, 797.48, 842.46]
print("--- BLS Power at Specific Periods ---")
for p in test_periods:
    test_res = bls.power([p], durations)
    print(f"Period: {p:6.2f}d, Power: {test_res.power[0]:.4f}, Depth: {test_res.depth[0]:.6f}")
    
# 2. Spectral window function of sampling
print("\n--- Sampling Window Function Analysis ---")
ls = LombScargle(time, np.ones_like(time), fit_mean=False, center_data=False)
freq, ls_power = ls.autopower(minimum_frequency=1/1000.0, maximum_frequency=1/10.0)

# Check if aliases line up with sampling window peaks
# Convolution: f_alias = f_true +/- f_window  => 1/P_alias = 1/P_true +/- 1/P_window
for p_true in [210.6, 331.6]:
    for p_alias in [797.48, 842.46]:
        f_true = 1.0 / p_true
        f_alias = 1.0 / p_alias
        f_diff = abs(f_true - f_alias)
        p_window = 1.0 / f_diff
        print(f"To alias {p_true:6.2f}d to {p_alias:6.2f}d requires window period of ~{p_window:6.2f}d")

# Find top peaks in window function
top_idx = np.argsort(ls_power)[-5:]
print("\nTop 5 window function periods:")
for idx in reversed(top_idx):
    print(f"Period: {1.0/freq[idx]:6.2f}d, Power: {ls_power[idx]:.4f}")
