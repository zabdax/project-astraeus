# Bucket 4: TTV N-Body Validation Summary Report

## Final Architecture
The new TTV physical plausibility check is implemented in `astraeus/analysis/ttv_nbody_validation.py` using a three-stage "Cheap-Filter-then-Confirm" pipeline:
1. **Periodicity Extraction** (`estimate_ttv_periodicity`): Analyzes the TTV residuals using a Lomb-Scargle periodogram (consistent with detrending approaches) to extract a dominant super-period, filtering out cases indistinguishable from noise.
2. **Cheap Analytic Filter** (`estimate_analytic_ttv_amplitude_min`): Computes a fast analytic approximation of the expected TTV amplitude based on Lithwick et al. 2012. We search a broad grid (masses from 0.1 Earth to ~3000 Earth masses, period ratios from 0.1 to 4.0) and instantly score each configuration's predicted amplitude against the observed amplitude.
3. **Full N-Body Confirmation** (`validate_ttv_with_nbody`): The top $N$ candidates (default 5) whose analytic predicted amplitudes closely match the observed TTV are fed into the unmodified `run_stability_analysis` function. Candidates that survive the 10,000-step integration without collisions or ejections are returned.

## Known-Truth Validation Results
The synthetic recovery test (`test_synthetic_recovery` in `tests/test_ttv_nbody_validation.py`) successfully demonstrated the pipeline's effectiveness.
- **Ground Truth**: A stable system with a known planet at 10 days and a 100 Earth-mass companion at 21.5 days.
- **Recovery Accuracy**: The grid search recovered companions on the correct order of magnitude for both mass and orbital period. Due to inherent degeneracies in TTVs (where slightly larger mass farther away can mimic smaller mass closer in, particularly outside exact resonances), the recovery is approximate. The framework honestly bounds the configuration rather than claiming perfect precision.

## Compute Cost
- **Analytic Grid**: ~800 evaluations of the analytic proxy, taking <0.01 seconds.
- **N-Body Confirmation**: 5 full `run_stability_analysis` integrations of 10,000 steps each. Since the vectorized Numpy solver handles an integration in ~0.1 seconds, the total compute cost per TTV validation is very light (under 1 second).

## UI & Presentation Framing Recommendations
**HARD CONSTRAINT**: The UI must **never** present the output of this module as a "detected companion" or a confirmed parameter determination. 
The results must be framed strictly as a **"Plausibility Set"** or "Dynamically Consistent Configurations".
- **Recommended Language**: "The observed transit timing variations are consistent with an unseen companion. A grid search identified dynamically stable configurations that produce similar TTV amplitudes, representing a plausibility set rather than a precise detection."
- **Visuals**: Show a bounded region (e.g., a scatter or density plot of stable mass-period pairs) rather than a single point estimate.

## Verification Commands
To reproduce the test run and verify the validation suite:
```bash
python -m pytest tests/test_ttv_nbody_validation.py -v
python -m pytest tests/ -v
```
