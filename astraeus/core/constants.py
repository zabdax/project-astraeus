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
# Empirical distribution (Phase 1.3 / Phase 1.4 of bucket 9.1):
#   noise SNR          : min=2.75, median=5.38, max=10.67 (50 realizations)
#   real-signal SNR    : floor=16.42 (pipeline_smoke), 61.59 (test_signal_recovery),
#                        ~1630 (hot_jupiter_clean), etc.
# A threshold of 12.0 sits cleanly inside the gap (noise max 10.67,
# real floor 16.42) with ~6 SNR units of headroom on each side.
# Callers may still pass an explicit ``snr_threshold`` to override this
# default, but the confidence_score floor below is unconditional.
DETECTION_SNR_THRESHOLD_DEFAULT = 12.0

# Minimum confidence_score (best BLS periodogram power divided by the
# median periodogram power) for emitting a candidate.
#
# Empirical distribution (Phase 1.3 / Phase 1.4 of bucket 9.1):
#   noise confidence_score      : min=1.79, median=2.87, max=5.96
#   real-signal confidence_score: floor=9.02 (pipeline_smoke), 13.32 (test_signal_recovery),
#                                 ~21.65 (hot_jupiter_clean), etc.
# A floor of 7.0 sits cleanly inside the gap (noise max 5.96, real
# floor 9.02) with ~3 units of headroom on each side. This is a
# false-alarm-probability analogue in the sense of Horne & Baliunas
# (1986) / Schwarzenberg-Czerny (1997): a high peak-to-median ratio
# means the peak stands well above the noise floor and is unlikely to
# be a random fluctuation. Applied unconditionally (not bypassable by
# caller-provided snr_threshold) so that the noise test, which passes
# snr_threshold=5.0 explicitly, is still rejected.
DETECTION_CONFIDENCE_FLOOR = 7.0
