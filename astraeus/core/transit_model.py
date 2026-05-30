"""Analytical geometric transit light-curve models."""

from __future__ import annotations

import numpy as np
from astropy import units as u

from astraeus.core.geometry import (
    calculate_circle_overlap_area,
    calculate_sky_separation,
)
from astraeus.core.validation import (
    require_convertible_unit,
    require_positive_quantity,
)

__all__ = [
    "calculate_sky_separation",
    "generate_geometric_transit",
]


def generate_geometric_transit(
    separation: u.Quantity,
    R_star: u.Quantity,
    R_planet: u.Quantity,
) -> u.Quantity:
    """Calculate relative flux drop for a uniform-disk geometric transit.

    Physics derivation:
    With a uniform stellar surface brightness, the fractional loss of light is
    the occulted stellar area divided by the stellar disk area. If the planet
    disk is fully inside the stellar disk, ``d <= R_star - R_planet`` and the
    blocked fraction is ``delta_F = (R_planet / R_star)**2``. If the disks do
    not overlap, ``d >= R_star + R_planet`` and ``delta_F = 0``. In the
    boundary-intersection regime, ``R_star - R_planet < d < R_star + R_planet``,
    the occulted area is delegated to the analytic circle-overlap equation in
    ``astraeus.core.geometry`` and normalized by ``pi R_star**2``.

    Geometric assumptions:
    The star and planet are circular disks in projection, the stellar disk has
    uniform surface brightness, limb darkening is ignored, and the planet is
    smaller than or equal to the star. The caller is responsible for ensuring
    the planet is between the observer and the star.

    Unit expectations:
    ``separation``, ``R_star``, and ``R_planet`` must be Astropy length
    quantities with compatible units. Radii must be strictly positive. The
    returned relative flux drop is an Astropy dimensionless quantity.
    """

    require_positive_quantity(R_star, "R_star")
    require_positive_quantity(R_planet, "R_planet")
    require_convertible_unit(R_planet, R_star.unit, "R_planet")

    if np.any(R_planet.to_value(R_star.unit) > R_star.to_value(R_star.unit)):
        raise ValueError("R_planet must be less than or equal to R_star.")

    occulted_area = calculate_circle_overlap_area(
        separation=separation,
        first_radius=R_star,
        second_radius=R_planet,
    )
    stellar_disk_area = np.pi * R_star**2

    return (occulted_area.to(stellar_disk_area.unit) / stellar_disk_area).to(
        u.dimensionless_unscaled
    )
