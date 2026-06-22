"""Shared constants for ASTRAEUS core physics models."""

from __future__ import annotations

import numpy as np
from astropy import units as u

BOUND_ECCENTRICITY_MINIMUM = 0.0
BOUND_ECCENTRICITY_MAXIMUM = 1.0
HIGH_ECCENTRICITY_INITIAL_GUESS_THRESHOLD = 0.8
POSITIVE_QUANTITY_MINIMUM = 0.0

KEPLER_NEWTON_TOLERANCE = 1.0e-12
KEPLER_NEWTON_MAX_ITERATIONS = 64

HALF_TURN_ANGLE = np.pi * u.rad
HALF_TURNS_PER_FULL_TURN = 2.0
FULL_TURN_ANGLE = HALF_TURNS_PER_FULL_TURN * HALF_TURN_ANGLE

REFERENCE_LENGTH_UNIT = u.AU

# ---------------------------------------------------------------------------
# Vetting decision thresholds (bucket 2 — threshold hardening).
#
# These are domain conventions, NOT free parameters. Do NOT tune them
# without a literature citation. The headline fix for bucket 2 is the
# physically-derived secondary-eclipse threshold (see
# PhysicalPropertiesEngine.expected_occultation_depth_ppm); these named
# constants replace inline magic numbers that previously controlled the
# pipeline's vetting branches.
# ---------------------------------------------------------------------------

# Planet-candidate depth ceiling: a transit deeper than this is treated as
# a stellar-scale event (eclipsing binary, very young self-luminous
# companion, etc.) rather than a planet candidate.
VETTING_PLANET_CANDIDATE_MAX_DEPTH_FRACTION = 0.03

# V-shape (grazing/eclipsing-binary-like) and secondary-eclipse branches
# only override the planet verdict when the BLS signal-to-noise is NOT
# overwhelming. Above this SNR an oblate-star gravity-darkened transit
# can legitimately look V-shaped.
VETTING_VSHAPE_LOW_SNR_GATE = 20.0

# Detection floor for declaring a secondary-eclipse signal present in the
# phase-folded light curve (GeometricValidator).
VETTING_SECONDARY_ECLIPSE_SNR_THRESHOLD = 3.0

# Ultra-short-period cutoff. Periods below this are flagged so that the
# pipeline can apply separate TTV/correctness checks.
VETTING_ULTRA_SHORT_PERIOD_DAYS = 1.5

# Fallback secondary-eclipse depth used ONLY when the physically-derived
# threshold cannot be computed (missing stellar/planet properties). 800 ppm
# is the historical ASTRAEUS default. The physically-derived threshold
# takes precedence whenever possible — see
# PhysicalPropertiesEngine.expected_occultation_depth_ppm.
VETTING_SECONDARY_ECLIPSE_FALLBACK_PPM = 800.0

# ---------------------------------------------------------------------------
# GeometricValidator secondary-eclipse detection parameters (bucket 2).
# ---------------------------------------------------------------------------

# Minimum number of in-transit samples required to evaluate the flat-bottom
# fraction diagnostic.
GEOMETRIC_FLAT_BOTTOM_MIN_INTRANSIT_SAMPLES = 8

# Slack applied (as a fraction of geometric transit depth) when deciding
# whether an in-transit flux sample is "deep enough" to count as flat-bottom.
GEOMETRIC_FLAT_BOTTOM_DEPTH_FRACTION_SLACK = 0.10

# Half-width of the phase window centred on phase 0.5 in which a secondary
# eclipse, if present, must fall.
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_HALF_WINDOW = 0.05

# Inner and outer edges of the local baseline annulus around phase 0.5
# (used to estimate the local scatter / non-eclipse flux level).
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_INNER = 0.05
GEOMETRIC_SECONDARY_ECLIPSE_PHASE_BASELINE_OUTER = 0.15

# Minimum number of samples required in BOTH the eclipse window and the
# baseline annulus before secondary-eclipse statistics are computed.
GEOMETRIC_SECONDARY_ECLIPSE_MIN_SAMPLES = 3

# ---------------------------------------------------------------------------
# Detection emission gates (bucket 9.1 — signal-detection tuning).
#
# These are the candidate-EMISSION thresholds — the gate that decides
# whether a BLS-detected peak becomes a "candidate" or is rejected
# upstream of the VettingEngine. They are distinct from the vetting
# thresholds above (bucket 2), which operate downstream on already-
# emitted candidates.
#
# Both values are derived empirically from
# reports/bucket9.1_signal_detection_audit.md §3 (50 pure-noise
# realizations at the test_noise_injection fixture) and §4 (5 real-
# signal scenarios × 5 repeats from the guardrail test fixtures).
# ---------------------------------------------------------------------------

# Default SNR threshold for emitting a candidate.
#
# Historical default value (5.0). The SNR threshold is a caller-tunable
# secondary check; the load-bearing noise-rejection gate is the
# confidence_score floor below (DETECTION_CONFIDENCE_FLOOR = 7.0).
#
# Bucket 9.1 briefly raised this to 12.0 on the rationale that noise
# SNR maxes at ~10.67 in the bucket-9.1 sweep. Bucket 9.2 reverted
# it to 5.0: the raised SNR was redundant with the confidence floor
# (which alone catches all 50 noise realizations) and only cost
# real-signal sensitivity at the default threshold for callers that
# do not pass an explicit ``snr_threshold``. See
# reports/bucket9.1_signal_detection_audit.md §3 and §4 for the
# underlying data; reports/bucket9.2_summary.md §Item 2 for the
# revert rationale and stop-guard verification.
#
# Callers may still pass an explicit ``snr_threshold`` to override this
# default. The confidence_score floor below is unconditional.
DETECTION_SNR_THRESHOLD_DEFAULT = 5.0

# Minimum confidence_score (best BLS periodogram power divided by the
# median periodogram power) for emitting a candidate.
#
# EMPIRICALLY DERIVED, not a formal false-alarm probability. The value
# was fit to the bucket 9.1 Phase 1.3 sweep (50 pure-noise realizations
# at the test_noise_injection fixture) and Phase 1.4 sweep (5 real-
# signal guardrail scenarios × 5 repeats):
#   noise confidence_score      : min=1.79, median=2.87, max=5.96
#   real-signal confidence_score: floor=9.02 (pipeline_smoke), 13.32
#                                 (test_signal_recovery), ~21.65
#                                 (hot_jupiter_clean), etc.
# The threshold of 7.0 sits inside the observed noise-vs-signal gap
# with ~1 unit of headroom above the noise maximum and ~2 units of
# headroom below the real-signal minimum. Both distributions were
# measured against SYNTHETIC fixtures only; no real Kepler/TESS
# curves were characterized. See reports/bucket9.1_summary.md §6
# ("Known limitation") for what is NOT measured.
#
# The statistic itself — peak BLS power divided by the median
# periodogram power — is analogous to the peak-height statistics
# discussed in Horne & Baliunas (1986) and Schwarzenberg-Czerny
# (1997), but those papers describe how to compute a FORMAL
# false-alarm probability from the periodogram via chi-squared
# statistics; they do NOT bless "peak/median ratio of 7" as a
# threshold. A future maintainer should NOT read the literature
# references as implying that 7.0 is justified by first-principles
# FAP — it is not. It is empirically fit to the synthetic sweep.
#
# Applied unconditionally (not bypassable by caller-provided
# snr_threshold) so that the noise test, which passes
# snr_threshold=5.0 explicitly, is still rejected.
DETECTION_CONFIDENCE_FLOOR = 7.0
