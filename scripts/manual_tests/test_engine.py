#!/usr/bin/env python3
"""
test_engine.py — Standalone N-Body Core Engine Diagnostic
=========================================================

Bypasses the Streamlit frontend to directly exercise
`astraeus.core.nbody_solver.run_stability_integration` against three
controlled scenarios and prints a clean pass/fail diagnostic ledger.

Scenarios
---------
1. Synthetic Earth-Sun analog  (1-year circular orbit, must survive 1000 steps)
2. Kepler-90b high-res         (micro-timestep, must survive 5000 steps)
3. Kepler-90b oversized dt     (forced blowup, must flag boundary breach / ejection)
"""

from __future__ import annotations

import math
import sys
import traceback

import numpy as np

from astraeus.core.nbody_solver import run_stability_integration, StabilityResult


# ── helper ──────────────────────────────────────────────────────────────────
def _survival_steps(result: StabilityResult, dt: float) -> int:
    """Back-calculate the discrete survival step count from survival_time_years."""
    return round(result.survival_time_years / dt)


# ── colour helpers (ANSI) ──────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _tag(passed: bool) -> str:
    return f"{GREEN}PASSED{RESET}" if passed else f"{RED}FAILED{RESET}"


# ======================================================================== #
#                          SCENARIO DEFINITIONS                            #
# ======================================================================== #

results: dict[str, dict] = {}

# ── SCENARIO 1: Synthetic Earth-Sun Analog ──────────────────────────────── #
print(f"\n{CYAN}{BOLD}> Scenario 1:{RESET} Synthetic Earth-Sun (1 AU circular orbit, 1 year)")
try:
    masses_1 = np.array([1.0, 0.000003])                         # M_sun
    positions_1 = np.array([
        [0.0, 0.0, 0.0],   # Star at origin
        [1.0, 0.0, 0.0],   # Planet at 1 AU
    ])
    velocities_1 = np.array([
        [0.0, 0.0, 0.0],                     # Star stationary
        [0.0, 2.0 * math.pi, 0.0],           # v_circ = 2π AU/yr
    ])

    res1 = run_stability_integration(
        positions_1, velocities_1, masses_1,
        n_steps=1_000, dt=0.001,
    )
    steps1 = _survival_steps(res1, 0.001)
    passed1 = res1.is_stable and steps1 == 1_000

    print(f"  is_stable          : {res1.is_stable}")
    print(f"  termination_reason : {res1.termination_reason}")
    print(f"  survival_steps     : {steps1} / 1000")
    print(f"  survival_time_yrs  : {res1.survival_time_years:.6f}")
    print(f"  max_ecc_drift      : {res1.max_eccentricity_drift:.2e}")
    print(f"  energy_rel_error   : {res1.energy_relative_error:.2e}")
    print(f"  final_eccentricities: {res1.final_eccentricities}")
    print(f"  -- Verdict: [{_tag(passed1)}]")

    results["scenario_1"] = {
        "passed": passed1,
        "stable": res1.is_stable,
        "steps": steps1,
        "total": 1_000,
        "reason": res1.termination_reason,
    }

except Exception:
    traceback.print_exc()
    results["scenario_1"] = {
        "passed": False, "stable": None, "steps": "ERR",
        "total": 1_000, "reason": "EXCEPTION",
    }


# ── SCENARIO 2: Kepler-90b High-Res ─────────────────────────────────────── #
print(f"\n{CYAN}{BOLD}> Scenario 2:{RESET} Kepler-90b (a=0.074 AU, dt=0.00001 yr, 5000 steps)")
try:
    masses_2 = np.array([1.2, 0.000009])                         # M_sun
    positions_2 = np.array([
        [0.0, 0.0, 0.0],
        [0.074, 0.0, 0.0],
    ])
    velocities_2 = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 25.32, 0.0],
    ])

    res2 = run_stability_integration(
        positions_2, velocities_2, masses_2,
        n_steps=5_000, dt=0.00001,
    )
    steps2 = _survival_steps(res2, 0.00001)
    passed2 = res2.is_stable and steps2 == 5_000

    print(f"  is_stable          : {res2.is_stable}")
    print(f"  termination_reason : {res2.termination_reason}")
    print(f"  survival_steps     : {steps2} / 5000")
    print(f"  survival_time_yrs  : {res2.survival_time_years:.6f}")
    print(f"  max_ecc_drift      : {res2.max_eccentricity_drift:.2e}")
    print(f"  energy_rel_error   : {res2.energy_relative_error:.2e}")
    print(f"  final_eccentricities: {res2.final_eccentricities}")
    print(f"  -- Verdict: [{_tag(passed2)}]")

    results["scenario_2"] = {
        "passed": passed2,
        "stable": res2.is_stable,
        "steps": steps2,
        "total": 5_000,
        "reason": res2.termination_reason,
    }

except Exception:
    traceback.print_exc()
    results["scenario_2"] = {
        "passed": False, "stable": None, "steps": "ERR",
        "total": 5_000, "reason": "EXCEPTION",
    }


# ── SCENARIO 3: Kepler-90b Oversized Timestep (Forced Explosion) ──────── #
print(f"\n{CYAN}{BOLD}> Scenario 3:{RESET} Kepler-90b OVERSHOT (dt=0.01 yr — deliberate blowup)")
try:
    # Reuse exact same physical arrays as Scenario 2
    masses_3 = np.array([1.2, 0.000009])
    positions_3 = np.array([
        [0.0, 0.0, 0.0],
        [0.074, 0.0, 0.0],
    ])
    velocities_3 = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 25.32, 0.0],
    ])

    res3 = run_stability_integration(
        positions_3, velocities_3, masses_3,
        n_steps=1_000, dt=0.01,
    )
    steps3 = _survival_steps(res3, 0.01)
    passed3 = (
        not res3.is_stable
        and res3.termination_reason in (
            "Physical Boundary Breach", "ejection", "energy_divergence", "collision",
        )
    )

    print(f"  is_stable          : {res3.is_stable}")
    print(f"  termination_reason : {res3.termination_reason}")
    print(f"  survival_steps     : {steps3} / 1000")
    print(f"  survival_time_yrs  : {res3.survival_time_years:.6f}")
    print(f"  max_ecc_drift      : {res3.max_eccentricity_drift:.2e}")
    print(f"  energy_rel_error   : {res3.energy_relative_error:.2e}")
    print(f"  ejected_body       : {res3.ejected_body}")
    print(f"  -- Verdict: [{_tag(passed3)}]")

    results["scenario_3"] = {
        "passed": passed3,
        "stable": res3.is_stable,
        "steps": steps3,
        "total": 1_000,
        "reason": res3.termination_reason,
    }

except Exception:
    traceback.print_exc()
    results["scenario_3"] = {
        "passed": False, "stable": None, "steps": "ERR",
        "total": 1_000, "reason": "EXCEPTION",
    }


# ======================================================================== #
#                        DIAGNOSTIC SUMMARY LEDGER                         #
# ======================================================================== #
sep = "=" * 60
print(f"\n{BOLD}{sep}")
print("        N-BODY CORE ENGINE DIAGNOSTIC REPORT")
print(f"{sep}{RESET}")

s1 = results["scenario_1"]
s2 = results["scenario_2"]
s3 = results["scenario_3"]

print(
    f"  Scenario 1 (Synthetic Earth-Sun) : [{_tag(s1['passed'])}] "
    f"| Stable: {str(s1['stable']):<5} "
    f"| Steps: {s1['steps']}/{s1['total']}"
)
print(
    f"  Scenario 2 (Kepler-90b High-Res) : [{_tag(s2['passed'])}] "
    f"| Stable: {str(s2['stable']):<5} "
    f"| Steps: {s2['steps']}/{s2['total']}"
)
print(
    f"  Scenario 3 (Kepler-90b Overshot) : [{_tag(s3['passed'])}] "
    f"| Stable: {str(s3['stable']):<5} "
    f"| Reason: {s3['reason']}"
)

print(f"{BOLD}{sep}{RESET}\n")

# Exit code: 0 if all passed, 1 otherwise
all_passed = all(r["passed"] for r in results.values())
sys.exit(0 if all_passed else 1)
