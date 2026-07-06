"""Time-unit normalization at the ingestion boundary.

Lightkurve returns light-curve time arrays in mission-specific offset
units (BKJD for Kepler = BJD - 2454833, BTJD for TESS = BJD - 2457000).
Every downstream consumer in this codebase — the orchestrator's BLS,
the orchestrator's t0, the NASA archive comparison path, the
reporting layer — was historically handed these arrays in BKJD/BTJD
without unit awareness. Any comparison to a NASA `pl_tranmid` value
(BJD full) was therefore silently offset by ~2454833 days with no
error signal.

This module centralizes the conversion so the fix lives in one place
and the rest of the codebase can rely on `time_bjd()` /
`time_unit_label()` to produce or assert a BJD-full epoch.
"""

from __future__ import annotations

# Mission → BJD offset. (Kepler uses BKJD, TESS uses BTJD, K2 uses BKJD
# the same way Kepler does.)
_MISSION_BJD_OFFSET = {
    "Kepler": 2454833.0,
    "K2": 2454833.0,
    "TESS": 2457000.0,
}


def bjd_offset_for_mission(mission: str) -> float:
    """Return the offset that, when added to a lightkurve time array
    produced from this mission, yields BJD full.
    """
    return _MISSION_BJD_OFFSET.get(mission, 0.0)


def to_bjd(time, mission: str):
    """Convert a lightkurve time array (or scalar) to BJD full.

    Returns a numpy array. If the input is already in BJD (mission
    unknown / not in the table), the value is returned unchanged.
    """
    import numpy as np
    offset = bjd_offset_for_mission(mission)
    arr = np.asarray(time, dtype=np.float64)
    return arr + offset
