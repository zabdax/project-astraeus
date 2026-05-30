"""Public orbital-model facade for ASTRAEUS."""

from __future__ import annotations

from astropy import units as u

from astraeus.core.kepler import (
    NewtonRaphsonKeplerSolver,
    solve_kepler_equation,
    solve_keplers_equation,
)
from astraeus.core.orbits import CartesianPosition, KeplerianOrbit

__all__ = [
    "CartesianPosition",
    "KeplerianOrbit",
    "NewtonRaphsonKeplerSolver",
    "calculate_orbital_position",
    "solve_kepler_equation",
    "solve_keplers_equation",
]


def calculate_orbital_position(
    time: u.Quantity,
    period: u.Quantity,
    semi_major_axis: u.Quantity,
    eccentricity: u.Quantity,
    inclination: u.Quantity,
) -> CartesianPosition:
    """Calculate a planet's Cartesian position in a two-body Keplerian orbit.

    Physics derivation:
    This compatibility facade builds a ``KeplerianOrbit`` and asks it for the
    position at ``time``. Internally, mean anomaly is computed as
    ``M = (2 pi / period) * time``, eccentric anomaly is found from
    ``M = E - e sin(E)``, and focus-centered ellipse coordinates are rotated
    by inclination into ``(x, y, z)``.

    Geometric assumptions:
    The host star sits at the coordinate origin, ``time = 0`` is periapsis,
    periapsis points along the positive x-axis, longitude of ascending node
    and argument of periapsis are zero, and inclination rotates the orbit
    about the x-axis.

    Unit expectations:
    ``time`` and ``period`` must be Astropy time quantities. ``semi_major_axis``
    must be a length quantity, ``eccentricity`` a dimensionless quantity with
    ``0 <= e < 1``, and ``inclination`` an angle quantity. Returned coordinates
    use the same length unit as ``semi_major_axis``.
    """

    orbit = KeplerianOrbit(
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=eccentricity,
        inclination=inclination,
    )

    return orbit.position_at(time)
