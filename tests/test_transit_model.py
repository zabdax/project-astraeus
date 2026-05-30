"""Regression tests for geometric transit light curves."""

from __future__ import annotations

import unittest

import numpy as np
from astropy import units as u

from astraeus.core import (
    calculate_circle_overlap_area,
    calculate_sky_separation,
    generate_geometric_transit,
)


class TransitGeometryTests(unittest.TestCase):
    """Tests for projected sky-plane geometry."""

    def test_sky_separation_projects_onto_xy_plane(self) -> None:
        """Projected separation should ignore line-of-sight displacement."""

        separation = calculate_sky_separation(
            3.0 * u.R_sun,
            4.0 * u.R_sun,
            12.0 * u.R_sun,
        )

        self.assertAlmostEqual(separation.to_value(u.R_sun), 5.0)

    def test_sky_separation_requires_quantities(self) -> None:
        """Bare numeric coordinates should fail the unit contract."""

        with self.assertRaises(TypeError):
            calculate_sky_separation(3.0, 4.0 * u.R_sun, 0.0 * u.R_sun)

    def test_circle_overlap_area_returns_area_quantity(self) -> None:
        """Generic disk overlap should preserve squared length units."""

        area = calculate_circle_overlap_area(
            0.0 * u.R_sun,
            1.0 * u.R_sun,
            0.1 * u.R_sun,
        )

        self.assertAlmostEqual(area.to_value(u.R_sun**2), np.pi * 0.1**2)

    def test_circle_overlap_area_rejects_negative_separation(self) -> None:
        """Generic center separation is a non-negative distance."""

        with self.assertRaises(ValueError):
            calculate_circle_overlap_area(
                -0.1 * u.R_sun,
                1.0 * u.R_sun,
                0.1 * u.R_sun,
            )


class GeometricTransitTests(unittest.TestCase):
    """Tests for uniform-disk occultation depths."""

    def test_full_transit_depth_equals_radius_ratio_squared(self) -> None:
        """A fully superimposed small planet should block its area ratio."""

        flux_drop = generate_geometric_transit(
            0.5 * u.R_sun,
            1.0 * u.R_sun,
            0.1 * u.R_sun,
        )

        self.assertAlmostEqual(
            flux_drop.to_value(u.dimensionless_unscaled),
            0.01,
        )

    def test_out_of_transit_depth_is_zero(self) -> None:
        """Separated disks should produce no flux loss."""

        flux_drop = generate_geometric_transit(
            1.2 * u.R_sun,
            1.0 * u.R_sun,
            0.1 * u.R_sun,
        )

        self.assertAlmostEqual(
            flux_drop.to_value(u.dimensionless_unscaled),
            0.0,
        )

    def test_partial_transit_uses_intersection_area(self) -> None:
        """Equal-radius disks separated by one radius have known lens area."""

        flux_drop = generate_geometric_transit(
            1.0 * u.R_sun,
            1.0 * u.R_sun,
            1.0 * u.R_sun,
        )

        expected_flux_drop = (2.0 / 3.0) - (np.sqrt(3.0) / (2.0 * np.pi))

        self.assertAlmostEqual(
            flux_drop.to_value(u.dimensionless_unscaled),
            expected_flux_drop,
        )

    def test_equal_radius_zero_separation_is_full_occultation(self) -> None:
        """Coincident equal disks should block the full stellar disk."""

        flux_drop = generate_geometric_transit(
            0.0 * u.R_sun,
            1.0 * u.R_sun,
            1.0 * u.R_sun,
        )

        self.assertAlmostEqual(
            flux_drop.to_value(u.dimensionless_unscaled),
            1.0,
        )

    def test_negative_separation_is_rejected(self) -> None:
        """Projected center separation is a non-negative physical distance."""

        with self.assertRaises(ValueError):
            generate_geometric_transit(
                -0.1 * u.R_sun,
                1.0 * u.R_sun,
                0.1 * u.R_sun,
            )


if __name__ == "__main__":
    unittest.main()
