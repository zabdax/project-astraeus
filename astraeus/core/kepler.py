"""Solvers for Kepler's equation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from astropy import units as u

from astraeus.core.constants import (
    BOUND_ECCENTRICITY_MAXIMUM,
    FULL_TURN_ANGLE,
    HALF_TURN_ANGLE,
    HIGH_ECCENTRICITY_INITIAL_GUESS_THRESHOLD,
    KEPLER_NEWTON_MAX_ITERATIONS,
    KEPLER_NEWTON_TOLERANCE,
)
from astraeus.core.validation import require_bound_eccentricity, require_convertible_unit


class KeplerEquationSolver(Protocol):
    """Protocol for interchangeable Kepler-equation solvers.

    Physics derivation and assumptions:
    Implementations solve the elliptic Kepler equation ``M = E - e sin(E)``
    for the eccentric anomaly ``E``. The protocol keeps downstream orbital
    geometry dependent on a solver contract rather than on a concrete numeric
    method, so future bisection, Halley, or vectorized backends can be added
    without changing coordinate code.
    """

    def solve(self, mean_anomaly: u.Quantity, eccentricity: u.Quantity) -> u.Quantity:
        """Solve ``M = E - e sin(E)`` and return eccentric anomaly in radians."""

        ...


@dataclass(frozen=True)
class NewtonRaphsonKeplerSolver:
    """Newton-Raphson implementation for the elliptic Kepler equation.

    Physics derivation:
    For bound elliptical motion, the mean anomaly ``M`` is proportional to
    swept area, while the eccentric anomaly ``E`` parameterizes the auxiliary
    circle of the ellipse. The two are related by ``M = E - e sin(E)``. This
    class solves ``f(E) = E - e sin(E) - M`` using Newton-Raphson updates
    ``E_next = E - f(E) / f'(E)``, where ``f'(E) = 1 - e cos(E)``.

    Geometric assumptions:
    The orbit is a bound, unperturbed two-body ellipse with ``0 <= e < 1``.
    The anomaly is measured from periapsis, and all input phases are reduced
    to one turn because Keplerian geometry is periodic in ``2 pi``.

    Unit expectations:
    ``mean_anomaly`` must be an Astropy angle quantity convertible to radians.
    ``eccentricity`` must be an Astropy dimensionless quantity. ``solve``
    returns an Astropy angle quantity in radians.
    """

    tolerance: float = KEPLER_NEWTON_TOLERANCE
    max_iterations: int = KEPLER_NEWTON_MAX_ITERATIONS
    high_eccentricity_threshold: float = HIGH_ECCENTRICITY_INITIAL_GUESS_THRESHOLD

    def solve(self, mean_anomaly: u.Quantity, eccentricity: u.Quantity) -> u.Quantity:
        """Solve Kepler's equation for eccentric anomaly.

        Physics derivation:
        The residual ``E - e sin(E) - M`` is iteratively driven to zero with
        Newton-Raphson corrections. The derivative ``1 - e cos(E)`` is the
        local change in mean anomaly per change in eccentric anomaly, making
        each correction a first-order estimate of the remaining angular error.

        Geometric assumptions:
        Inputs describe an elliptic orbit, with phase measured from periapsis.
        The solver normalizes ``M`` into one full turn before iteration.

        Unit expectations:
        ``mean_anomaly`` must be convertible to radians. ``eccentricity`` must
        be dimensionless and satisfy ``0 <= e < 1``. The return value is in
        radians.
        """

        normalized_mean_anomaly = self._normalize_mean_anomaly(mean_anomaly)
        eccentricity_value = require_bound_eccentricity(eccentricity).to_value(
            u.dimensionless_unscaled
        )
        eccentric_anomaly = self._initial_guess(
            normalized_mean_anomaly,
            eccentricity_value,
        )

        for _iteration in range(self.max_iterations):
            residual = (
                eccentric_anomaly
                - eccentricity_value * np.sin(eccentric_anomaly)
                - normalized_mean_anomaly
            )
            derivative = (
                BOUND_ECCENTRICITY_MAXIMUM
                - eccentricity_value * np.cos(eccentric_anomaly)
            )
            correction = residual / derivative
            eccentric_anomaly = eccentric_anomaly - correction

            if np.all(np.abs(correction) <= self.tolerance):
                return eccentric_anomaly * u.rad

        raise RuntimeError(
            "Newton-Raphson solver did not converge for Kepler's equation."
        )

    def _normalize_mean_anomaly(self, mean_anomaly: u.Quantity) -> np.ndarray:
        """Normalize mean anomaly to the periodic interval used by the solver.

        Physics derivation and assumptions:
        Keplerian orbital phase repeats after one full turn, so adding or
        subtracting integer multiples of ``2 pi`` does not change position on
        the ellipse. Normalization improves solver stability without changing
        the physical phase.
        """

        anomaly = require_convertible_unit(
            mean_anomaly,
            u.rad,
            "mean_anomaly",
        )
        return np.mod(
            anomaly.to_value(u.rad),
            FULL_TURN_ANGLE.to_value(u.rad),
        )

    def _initial_guess(
        self,
        normalized_mean_anomaly: np.ndarray,
        eccentricity_value: np.ndarray,
    ) -> np.ndarray:
        """Choose a Newton-Raphson starting point for elliptic motion.

        Physics derivation and assumptions:
        For low eccentricity, ``E`` remains close to ``M``. At higher
        eccentricity, the sinusoidal term becomes stronger, so the initial
        estimate is nudged toward the side of the ellipse implied by the
        current half orbit. This keeps the iteration count stable without
        changing the target equation.
        """

        if np.any(eccentricity_value >= self.high_eccentricity_threshold):
            return np.where(
                normalized_mean_anomaly < HALF_TURN_ANGLE.to_value(u.rad),
                normalized_mean_anomaly + eccentricity_value,
                normalized_mean_anomaly - eccentricity_value,
            )

        return normalized_mean_anomaly


def solve_kepler_equation(
    mean_anomaly: u.Quantity,
    eccentricity: u.Quantity,
    solver: KeplerEquationSolver | None = None,
) -> u.Quantity:
    """Solve Kepler's equation with the configured solver.

    Physics derivation:
    This function is the public functional entry point for solving
    ``M = E - e sin(E)``. It delegates the numeric method to a solver object,
    preserving the same physical contract while allowing the implementation
    to change as ASTRAEUS gains more demanding orbital regimes.

    Geometric assumptions:
    The equation is elliptic and bound: ``0 <= e < 1`` with anomaly measured
    from periapsis. The default solver uses Newton-Raphson iterations.

    Unit expectations:
    ``mean_anomaly`` must be an angle quantity, ``eccentricity`` must be
    dimensionless, and the returned eccentric anomaly is in radians.
    """

    active_solver = solver or NewtonRaphsonKeplerSolver()
    return active_solver.solve(mean_anomaly, eccentricity)


solve_keplers_equation = solve_kepler_equation
