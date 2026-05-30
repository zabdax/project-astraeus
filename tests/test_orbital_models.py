"""Regression tests for Keplerian orbital models."""

from __future__ import annotations

import unittest

import numpy as np
from astropy import units as u

from astraeus.core import calculate_orbital_position, solve_kepler_equation
from astraeus.core.orbits import KeplerianOrbit


class KeplerSolverTests(unittest.TestCase):
    """Tests for the elliptic Kepler-equation solver."""

    def test_solver_satisfies_kepler_equation(self) -> None:
        """Solver result should make ``E - e sin(E)`` recover ``M``."""

        mean_anomaly = 1.4 * u.rad
        eccentricity = 0.3 * u.dimensionless_unscaled

        eccentric_anomaly = solve_kepler_equation(mean_anomaly, eccentricity)

        residual = (
            eccentric_anomaly.to_value(u.rad)
            - eccentricity.to_value(u.dimensionless_unscaled)
            * np.sin(eccentric_anomaly.to_value(u.rad))
            - mean_anomaly.to_value(u.rad)
        )

        self.assertAlmostEqual(residual, 0.0)


class KeplerianOrbitTests(unittest.TestCase):
    """Tests for focus-centered Keplerian orbit positions."""

    def test_position_at_periapsis(self) -> None:
        """At periapsis, x should equal ``a(1 - e)`` and y/z should vanish."""

        x, y, z = calculate_orbital_position(
            time=0.0 * u.day,
            period=10.0 * u.day,
            semi_major_axis=1.0 * u.AU,
            eccentricity=0.2 * u.dimensionless_unscaled,
            inclination=0.0 * u.rad,
        )

        self.assertAlmostEqual(x.to_value(u.AU), 0.8)
        self.assertAlmostEqual(y.to_value(u.AU), 0.0)
        self.assertAlmostEqual(z.to_value(u.AU), 0.0)

    def test_edge_on_circular_quarter_orbit(self) -> None:
        """A circular edge-on quarter orbit should place y near zero and z at a."""

        orbit = KeplerianOrbit(
            period=4.0 * u.day,
            semi_major_axis=1.0 * u.AU,
            eccentricity=0.0 * u.dimensionless_unscaled,
            inclination=(np.pi / 2.0) * u.rad,
        )

        x, y, z = orbit.position_at(1.0 * u.day)

        self.assertAlmostEqual(x.to_value(u.AU), 0.0)
        self.assertAlmostEqual(y.to_value(u.AU), 0.0)
        self.assertAlmostEqual(z.to_value(u.AU), 1.0)


if __name__ == "__main__":
    unittest.main()
