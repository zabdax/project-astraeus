# P4-B Detection-Floor FAP Calibration (measurement-only)

**Status:** advisory calibration — NO gate-behavior change.
The operational floor `DETECTION_CONFIDENCE_FLOOR = 7.0`
(`astraeus/core/constants.py`) is untouched. Any floor change is a
separate decision. Code: `astraeus/analysis/fap_calibration.py`;
tests: `tests/test_p4b_fap_calibration.py` (3 passed, ~30 s).

## 1. Headline numbers (measured)

Calibration run: 20 noise-only + 8 injected-signal BLS runs
(noise master seed 71001, signal master seed 72001; per-trial seeds
derived deterministically — rerunning `summarize_calibration` on the
same seeds reproduces these values exactly).

| Quantity | Value |
|---|---|
| Noise confidence max | **2.895** (min 2.135, median 2.570) |
| Injected-signal confidence min | **9.042** (median 11.119, max 12.888) |
| Recommended floor (gap midpoint) | **5.969** |
| Empirical FAP at recommended floor | 0.000 (0/20 noise runs reach it) |
| Detection efficiency at recommended floor | 1.000 (8/8 signals reach it) |
| Operational floor 7.0 in measured gap? | **Yes** — 2.895 < 7.0 < 9.042 |

## 2. Method

- **Statistic:** `BLSSearchEngine.search` `confidence_score`
  (peak BLS periodogram power / median periodogram power).
- **Noise fixture:** flat flux 1.0 + white Gaussian noise
  (sigma = 1/200), 30 d baseline, 1200 cadences, seeded `numpy`
  `default_rng`; per-trial seeds derived from one master seed.
- **Signal fixture:** `synthetic.py` `generate_synthetic_transit_series`
  — 1%-deep (radius ratio 0.1), 5 d hot Jupiter at SNR 200 on the same
  30 d / 1200-cadence grid (not reinvented; the package generator API).
- **BLS grid:** `frequency_factor=5.0` (coarsened vs the pipeline
  adaptive default) so each search costs ~1 s instead of ~5–8 s;
  spot-checked to preserve the noise/signal gap (noise max 3.08 →
  2.90-class, signal min ~9–10 across pilot seeds).
- **FAP mapping:** `empirical_fap = mean(noise >= threshold)`
  (descriptive sample fraction, not a formal analytic FAP).
- **Efficiency:** `detection_efficiency = mean(signal >= threshold)`.
- **`recommend_floor`:** gap midpoint `(noise_max + signal_min) / 2`
  when separated; explicit overlap warning fallback otherwise.

## 3. Measured FAP / efficiency vs threshold

| Threshold | Empirical FAP (n=20 noise) | Detection efficiency (n=8 signals) |
|---|---|---|
| 2.0 | 1.000 | 1.000 |
| 2.5 | 0.550 | 1.000 |
| 2.6 | 0.450 | 1.000 |
| 2.8 | 0.050 | 1.000 |
| 3.0 | 0.000 | 1.000 |
| 4.0 | 0.000 | 1.000 |
| 5.0 | 0.000 | 1.000 |
| 6.0 (≈ floor 5.969) | 0.000 | 1.000 |
| 7.0 (operational) | 0.000 | 1.000 |
| 8.0 | 0.000 | 1.000 |
| 9.0 | 0.000 | 1.000 |
| 10.0 | 0.000 | 0.750 |
| 11.0 | 0.000 | 0.625 |
| 12.0 | 0.000 | 0.250 |

FAP is non-increasing in threshold and efficiency is non-increasing in
threshold (both locked by tests). The operational floor 7.0 rejects all
20 noise realizations while recovering all 8 injections on these
fixtures — consistent with the bucket 9.1 synthetic sweep
(noise max 5.96, signal floor 9.02) that motivated 7.0.

## 4. Real-curve cross-check (single-slice anecdote)

- 30 d slice of cached `benchmarks/cache/Kepler_4d.npz`
  (1394 cadences, median-normalized, BLS `frequency_factor=5.0`):
  **confidence 80.2**, recovered period 3.212 d vs archive
  `best_period` 3.2136 d.
- A genuine hot Jupiter scores an order of magnitude above both the
  recommended (5.97) and operational (7.0) floors — the expected side
  of the gap. This is one slice, not a distribution; see limitations.

## 5. Limitations (honest)

1. **Synthetic-only distributions.** Noise is white and Gaussian; no
   correlated stellar variability, systematics, detrending residuals,
   or window-function pathologies are modeled. Real-survey FAP at a
   given confidence will be higher.
2. **Small samples.** 20 noise / 8 signal runs: FAP resolution is
   1/20 = 0.05; "FAP 0.0" means "none seen in 20 draws", not a
   10⁻²-level guarantee.
3. **Short baselines, coarsened grid.** 30 d fixtures with
   `frequency_factor=5.0` differ from long-baseline pipeline searches;
   absolute confidence values do not transfer 1:1 to 1000 d curves.
4. **Single-signal archetype.** Efficiency is measured for one
   deep, short-period archetype; shallow/long-period signals will have
   lower efficiency at any threshold (see rows ≥ 10.0 for how fast
   efficiency falls once the threshold approaches the signal bulk).
5. **One real slice.** The Kepler_4d check confirms a real signal
   lands far above the floor but characterizes no real-noise
   distribution.

## 6. Recommendation

Publish as calibration only: the measured gap
[2.90, 9.04] contains both the gap-midpoint recommendation (5.97) and
the operational floor (7.0). No floor change is proposed or made.
