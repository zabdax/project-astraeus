"""N-Body Gravitational Stability Solver for multi-planet architectures.

Uses a Symplectic Velocity Verlet (Störmer-Verlet / Leapfrog) integrator
to evolve multi-planet systems forward in time and diagnose gravitational
stability.  All calculations use pure numpy vector operations — no external
astronomy packages.

Internal unit system (natural gravitational units):
    Length : AU
    Mass   : M_sun
    Time   : years   (so that G = 4π² AU³ M_sun⁻¹ yr⁻²)

Physics references:
    - Velocity Verlet: Swope et al. 1982, J. Chem. Phys. 76, 637
    - Hill radius: Hamilton & Burns 1992, Icarus 96, 43
    - Weiss-Marcy mass-radius: Weiss & Marcy 2014, ApJL 783, L6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Physical constants in natural gravitational units (AU, M_sun, yr)
# ---------------------------------------------------------------------------
G_AU3_MSUN_YR2: float = 4.0 * np.pi**2
"""Gravitational constant G = 4π² in AU³ M_sun⁻¹ yr⁻²."""

AU_TO_RSUN: float = 215.032
"""1 AU ≈ 215 R_sun."""

YR_TO_DAYS: float = 365.25
"""1 Julian year in days."""

M_EARTH_IN_MSUN: float = 3.003e-6
"""Earth mass in solar masses."""

R_EARTH_IN_RSUN: float = 0.00917
"""Earth radius in solar radii."""

# Gravitational softening parameter (ε² in AU²) to prevent singularities
# during close encounters.  Value ≈ 10⁻⁴ AU² as specified.
SOFTENING_SQ: float = 1.0e-4

# Energy drift threshold for numerical early-exit
ENERGY_DRIFT_THRESHOLD: float = 1.0e-4

# Velocity sanity cap — if any body exceeds this, physics has broken down.
# 10 AU/yr ≈ 47 km/s, a generous cap for bound planetary orbits.
VELOCITY_SANITY_CAP: float = 100.0  # AU/yr


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PlanetParams:
    """Orbital parameters for a single planet.

    All values are in the internal unit system (AU, M_sun, yr, radians).
    ``mass_msun`` is the planet mass in solar masses.
    ``semi_major_axis_au`` is the initial semi-major axis in AU.
    ``eccentricity`` is the initial orbital eccentricity (0 ≤ e < 1).
    ``initial_phase_rad`` is the initial true anomaly in radians.
    """

    mass_msun: float
    semi_major_axis_au: float
    eccentricity: float = 0.0
    initial_phase_rad: float = 0.0


@dataclass
class StabilityResult:
    """Diagnostic payload returned by the stability solver.

    Provides a complete summary of the integration outcome including
    stability verdict, failure diagnostics, per-planet eccentricity drift,
    and integration quality metrics.
    """

    is_stable: bool
    survival_time_years: float
    max_eccentricity_drift: float
    termination_reason: str  # "completed" | "collision" | "ejection" | "energy_divergence"
    colliding_pair: Optional[tuple] = None
    ejected_body: Optional[int] = None
    final_eccentricities: list = field(default_factory=list)
    energy_relative_error: float = 0.0


# ---------------------------------------------------------------------------
# Keplerian → Cartesian state vector converter
# ---------------------------------------------------------------------------
def _keplerian_to_cartesian(
    star_mass: float,
    planet: PlanetParams,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert Keplerian orbital elements to Cartesian position and velocity.

    Physics derivation:
        The radial distance is r = a(1 − e²) / (1 + e cos(ν)) where ν is the
        true anomaly.  The position in the orbital plane is (r cos ν, r sin ν).
        The velocity components follow from the vis-viva equation and angular
        momentum conservation:
            v_r   = √(μ / p) · e sin(ν)
            v_ν   = √(μ / p) · (1 + e cos(ν))
        where p = a(1 − e²) is the semi-latus rectum and μ = G(M★ + m_p).

    Geometric assumptions:
        The orbit is confined to the x-y plane with periapsis on the +x axis.
        Longitude of ascending node and argument of periapsis are zero (i.e.
        all orbits are coplanar and aligned).

    Returns:
        (pos_3d, vel_3d) — position [AU] and velocity [AU/yr] arrays of shape
        (3,).
    """
    a = planet.semi_major_axis_au
    e = planet.eccentricity
    nu = planet.initial_phase_rad
    mu = G_AU3_MSUN_YR2 * (star_mass + planet.mass_msun)

    # Semi-latus rectum
    p = a * (1.0 - e**2)

    # Radial distance
    r = p / (1.0 + e * np.cos(nu))

    # Position in orbital plane
    pos = np.array([r * np.cos(nu), r * np.sin(nu), 0.0])

    # Velocity components in radial/tangential frame
    h = np.sqrt(mu * p)  # specific angular momentum magnitude
    v_r = (mu / h) * e * np.sin(nu)
    v_t = (mu / h) * (1.0 + e * np.cos(nu))

    # Convert to Cartesian
    cos_nu = np.cos(nu)
    sin_nu = np.sin(nu)
    vx = v_r * cos_nu - v_t * sin_nu
    vy = v_r * sin_nu + v_t * cos_nu
    vel = np.array([vx, vy, 0.0])

    return pos, vel


# ---------------------------------------------------------------------------
# Hill radius
# ---------------------------------------------------------------------------
def _hill_radius(m_planet: float, m_star: float, semi_major_axis: float) -> float:
    """Compute the Hill radius for a planet.

    R_H = a · (m_p / (3 M★))^(1/3)

    This defines the gravitational sphere of influence of the planet.
    Two bodies are flagged as colliding if their separation falls below the
    sum of their mutual Hill radii.
    """
    if m_planet <= 0.0 or m_star <= 0.0 or semi_major_axis <= 0.0:
        return 0.0
    return semi_major_axis * (m_planet / (3.0 * m_star)) ** (1.0 / 3.0)


# ---------------------------------------------------------------------------
# Vectorized gravitational acceleration with softening
# ---------------------------------------------------------------------------
def _compute_accelerations(
    positions: np.ndarray,
    masses: np.ndarray,
) -> np.ndarray:
    """Compute gravitational accelerations on all bodies.

    Uses pairwise Newton's law with a softening parameter to prevent
    singularities:  F ∝ 1 / (r² + ε²).

    Parameters:
        positions : (N, 3) array of body positions [AU].
        masses    : (N,) array of body masses [M_sun].

    Returns:
        (N, 3) array of accelerations [AU/yr²].
    """
    n = len(masses)
    acc = np.zeros_like(positions)

    for i in range(n):
        # Displacement vectors from body i to all other bodies
        # Shape: (N, 3) but we mask out self-interaction
        dx = positions - positions[i]  # (N, 3)
        r_sq = np.sum(dx**2, axis=1) + SOFTENING_SQ  # (N,)

        # Gravitational acceleration magnitude: G * m_j / (r² + ε²)^(3/2)
        inv_r3 = 1.0 / (r_sq * np.sqrt(r_sq))  # (N,)
        inv_r3[i] = 0.0  # zero self-interaction

        # Weighted sum: a_i = G * Σ_j m_j * (r_j - r_i) / |r_ij|³
        acc[i] = G_AU3_MSUN_YR2 * np.sum(
            (masses * inv_r3)[:, np.newaxis] * dx, axis=0
        )

    return acc


# ---------------------------------------------------------------------------
# Osculating eccentricity from state vectors
# ---------------------------------------------------------------------------
def _compute_osculating_eccentricity(
    pos: np.ndarray,
    vel: np.ndarray,
    mu: float,
) -> float:
    """Compute the instantaneous (osculating) orbital eccentricity.

    Physics derivation:
        The eccentricity vector is e⃗ = (v⃗ × h⃗) / μ − r̂, where h⃗ = r⃗ × v⃗
        is the specific angular momentum.  The scalar eccentricity is |e⃗|.
        An eccentricity ≥ 1 indicates an unbound (ejected) orbit.

    Parameters:
        pos : (3,) position vector relative to the central body [AU].
        vel : (3,) velocity vector [AU/yr].
        mu  : gravitational parameter G(M★ + m_p) [AU³/yr²].

    Returns:
        Scalar eccentricity (dimensionless, ≥ 0).
    """
    r = np.linalg.norm(pos)
    if r < 1.0e-15:
        return 0.0

    h = np.cross(pos, vel)
    e_vec = np.cross(vel, h) / mu - pos / r
    return float(np.linalg.norm(e_vec))


# ---------------------------------------------------------------------------
# Total mechanical energy of the system
# ---------------------------------------------------------------------------
def _compute_total_energy(
    positions: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
) -> float:
    """Compute the total mechanical energy (kinetic + potential).

    E = Σ_i ½ m_i v_i² − G Σ_{i<j} m_i m_j / r_ij

    Used to monitor numerical integration quality.  A symplectic integrator
    should keep |ΔE/E₀| bounded over the entire run.
    """
    n = len(masses)

    # Kinetic energy
    ke = 0.5 * np.sum(masses * np.sum(velocities**2, axis=1))

    # Potential energy
    pe = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            dx = positions[j] - positions[i]
            r = np.sqrt(np.sum(dx**2) + SOFTENING_SQ)
            pe -= G_AU3_MSUN_YR2 * masses[i] * masses[j] / r

    return float(ke + pe)


# ---------------------------------------------------------------------------
# Main stability analysis
# ---------------------------------------------------------------------------
def run_stability_analysis(
    stellar_mass_msun: float,
    planets: list[PlanetParams],
    n_steps: int = 50_000,
    dt_years: float | None = None,
) -> StabilityResult:
    """Run an N-body gravitational stability simulation.

    Integrates the positions and velocities of a central star plus N planets
    using the Symplectic Velocity Verlet algorithm and monitors for:
        1. Close encounters / collisions (separation < mutual Hill radii sum)
        2. Ejections (osculating eccentricity ≥ 1)
        3. Energy divergence (|ΔE/E₀| > 10⁻⁴)
        4. Velocity blowup (|v| > sanity cap)

    Parameters:
        stellar_mass_msun : Mass of the central star [M_sun].
        planets           : List of PlanetParams describing each planet.
        n_steps           : Total integration steps (default 50,000).
        dt_years          : Timestep in years.  If None, auto-set to
                            min_orbital_period / 100.

    Returns:
        StabilityResult with full diagnostics.
    """
    n_planets = len(planets)
    if n_planets == 0:
        return StabilityResult(
            is_stable=True,
            survival_time_years=0.0,
            max_eccentricity_drift=0.0,
            termination_reason="completed",
            final_eccentricities=[],
            energy_relative_error=0.0,
        )

    # Total bodies = star + planets
    n_bodies = 1 + n_planets

    # --- Initialize state arrays ---
    masses = np.zeros(n_bodies)
    positions = np.zeros((n_bodies, 3))
    velocities = np.zeros((n_bodies, 3))

    # Body 0 = star (at origin, stationary in the barycentric approximation)
    masses[0] = stellar_mass_msun

    for i, planet in enumerate(planets):
        idx = i + 1
        masses[idx] = planet.mass_msun
        pos, vel = _keplerian_to_cartesian(stellar_mass_msun, planet)
        positions[idx] = pos
        velocities[idx] = vel

    # Shift to centre-of-mass frame for better energy conservation
    total_mass = np.sum(masses)
    com_pos = np.sum(masses[:, np.newaxis] * positions, axis=0) / total_mass
    com_vel = np.sum(masses[:, np.newaxis] * velocities, axis=0) / total_mass
    positions -= com_pos
    velocities -= com_vel

    # --- Compute timestep ---
    if dt_years is None:
        # Kepler's third law: P² = (4π²/G·M★) a³ → P = 2π √(a³ / (G·M★))
        periods = [
            2.0 * np.pi * np.sqrt(p.semi_major_axis_au**3 / (G_AU3_MSUN_YR2 * stellar_mass_msun))
            for p in planets
        ]
        min_period = min(periods)
        dt_years = min_period / 100.0  # 100 steps per shortest orbit
    dt = dt_years

    # --- Pre-compute Hill radii for collision detection ---
    hill_radii = np.zeros(n_bodies)
    for i, planet in enumerate(planets):
        hill_radii[i + 1] = _hill_radius(
            planet.mass_msun, stellar_mass_msun, planet.semi_major_axis_au
        )

    # --- Track eccentricity history ---
    initial_eccentricities = np.zeros(n_planets)
    for i, planet in enumerate(planets):
        mu = G_AU3_MSUN_YR2 * (stellar_mass_msun + planet.mass_msun)
        rel_pos = positions[i + 1] - positions[0]
        rel_vel = velocities[i + 1] - velocities[0]
        initial_eccentricities[i] = _compute_osculating_eccentricity(rel_pos, rel_vel, mu)

    max_eccentricity_drift = 0.0
    current_eccentricities = initial_eccentricities.copy()

    # --- Initial energy ---
    E0 = _compute_total_energy(positions, velocities, masses)
    if abs(E0) < 1.0e-30:
        E0 = 1.0e-30  # prevent division by zero for degenerate systems

    # --- Velocity Verlet integration loop ---
    acc = _compute_accelerations(positions, masses)

    termination_reason = "completed"
    colliding_pair = None
    ejected_body = None
    survival_step = n_steps

    for step in range(n_steps):
        # --- Verlet step 1: update positions ---
        positions += velocities * dt + 0.5 * acc * dt**2

        # --- Verlet step 2: compute new accelerations ---
        acc_new = _compute_accelerations(positions, masses)

        # --- Verlet step 3: update velocities ---
        velocities += 0.5 * (acc + acc_new) * dt
        acc = acc_new

        # ===== DIAGNOSTIC CHECKS (every step) =====

        # --- Check 1: Velocity sanity ---
        v_magnitudes = np.sqrt(np.sum(velocities[1:]**2, axis=1))
        if np.any(v_magnitudes > VELOCITY_SANITY_CAP):
            blown_idx = int(np.argmax(v_magnitudes)) + 1  # +1 for planet index
            survival_step = step + 1
            termination_reason = "ejection"
            ejected_body = blown_idx - 1  # 0-indexed planet
            break

        # --- Check 2: Close encounters / Collisions ---
        for i in range(1, n_bodies):
            for j in range(i + 1, n_bodies):
                dx = positions[j] - positions[i]
                dist = np.sqrt(np.sum(dx**2))
                mutual_hill = hill_radii[i] + hill_radii[j]
                if mutual_hill > 0.0 and dist < mutual_hill:
                    survival_step = step + 1
                    termination_reason = "collision"
                    colliding_pair = (i - 1, j - 1)  # 0-indexed planets
                    break
            if termination_reason == "collision":
                break

        if termination_reason != "completed":
            break

        # --- Check 3: Osculating eccentricity / ejection ---
        for i in range(n_planets):
            mu = G_AU3_MSUN_YR2 * (stellar_mass_msun + planets[i].mass_msun)
            rel_pos = positions[i + 1] - positions[0]
            rel_vel = velocities[i + 1] - velocities[0]
            ecc = _compute_osculating_eccentricity(rel_pos, rel_vel, mu)
            current_eccentricities[i] = ecc

            drift = abs(ecc - initial_eccentricities[i])
            if drift > max_eccentricity_drift:
                max_eccentricity_drift = drift

            if ecc >= 1.0:
                survival_step = step + 1
                termination_reason = "ejection"
                ejected_body = i  # 0-indexed planet
                break

        if termination_reason != "completed":
            break

        # --- Check 4: Energy drift early-exit ---
        if (step + 1) % 100 == 0:  # check every 100 steps to save compute
            E_now = _compute_total_energy(positions, velocities, masses)
            rel_error = abs((E_now - E0) / E0)
            if rel_error > ENERGY_DRIFT_THRESHOLD:
                survival_step = step + 1
                termination_reason = "energy_divergence"
                break

    # --- Final diagnostics ---
    survival_time = survival_step * dt
    E_final = _compute_total_energy(positions, velocities, masses)
    energy_rel_error = abs((E_final - E0) / E0)

    is_stable = termination_reason == "completed"

    return StabilityResult(
        is_stable=is_stable,
        survival_time_years=float(survival_time),
        max_eccentricity_drift=float(max_eccentricity_drift),
        termination_reason=termination_reason,
        colliding_pair=colliding_pair,
        ejected_body=ejected_body,
        final_eccentricities=[float(e) for e in current_eccentricities],
        energy_relative_error=float(energy_rel_error),
    )


# ---------------------------------------------------------------------------
# Convenience wrapper: dict-based API for frontend / orchestrator
# ---------------------------------------------------------------------------
def check_system_stability(
    stellar_mass_msun: float,
    planet_dicts: list[dict],
    n_steps: int = 50_000,
    dt_years: float | None = None,
) -> dict:
    """Run gravitational stability analysis from raw dictionaries.

    Accepts the same parameter format produced by the frontend dashboard and
    the multi-planet orchestrator:

        planet_dicts = [
            {
                "mass_msun": 3.0e-6,
                "semi_major_axis_au": 0.05,
                "eccentricity": 0.01,
                "initial_phase_rad": 0.0,
            },
            ...
        ]

    Returns a JSON-serializable dictionary matching the StabilityResult
    fields.
    """
    planets = [
        PlanetParams(
            mass_msun=float(d.get("mass_msun", 0.0)),
            semi_major_axis_au=float(d.get("semi_major_axis_au", 1.0)),
            eccentricity=float(d.get("eccentricity", 0.0)),
            initial_phase_rad=float(d.get("initial_phase_rad", 0.0)),
        )
        for d in planet_dicts
    ]

    result = run_stability_analysis(
        stellar_mass_msun=stellar_mass_msun,
        planets=planets,
        n_steps=n_steps,
        dt_years=dt_years,
    )

    return {
        "is_stable": result.is_stable,
        "survival_time_years": result.survival_time_years,
        "max_eccentricity_drift": result.max_eccentricity_drift,
        "termination_reason": result.termination_reason,
        "colliding_pair": result.colliding_pair,
        "ejected_body": result.ejected_body,
        "final_eccentricities": result.final_eccentricities,
        "energy_relative_error": result.energy_relative_error,
    }


# ---------------------------------------------------------------------------
# Mass estimation helper (Weiss-Marcy 2014 power-law)
# ---------------------------------------------------------------------------
def estimate_mass_from_radius(radius_earth: float) -> float:
    """Estimate planet mass in solar masses from radius in Earth radii.

    Uses the Weiss & Marcy 2014 empirical relation for sub-Neptunes:
        M_p ≈ (R_p / R⊕)^2.06 M⊕

    This is valid for R < 4 R⊕.  For larger radii, a simple cubic scaling
    (density ≈ Jupiter) is used as a rough approximation.

    Returns mass in solar masses.
    """
    if radius_earth <= 0.0:
        return 0.0

    if radius_earth <= 4.0:
        mass_earth = radius_earth ** 2.06
    else:
        # Gas giant regime: scale with volume (constant density ≈ Jupiter)
        mass_earth = (radius_earth / 11.2) ** 3 * 317.8  # M_jup ≈ 317.8 M_earth

    return mass_earth * M_EARTH_IN_MSUN
