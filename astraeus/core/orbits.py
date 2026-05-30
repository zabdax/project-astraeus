"""Keplerian orbit domain objects and coordinate transforms."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from astropy import units as u

from astraeus.core.constants import (
    BOUND_ECCENTRICITY_MAXIMUM,
    FULL_TURN_ANGLE,
    REFERENCE_LENGTH_UNIT,
)
from astraeus.core.kepler import KeplerEquationSolver, NewtonRaphsonKeplerSolver
from astraeus.core.validation import (
    require_bound_eccentricity,
    require_convertible_unit,
    require_positive_quantity,
)

CartesianPosition = tuple[u.Quantity, u.Quantity, u.Quantity]
PlanarPosition = tuple[u.Quantity, u.Quantity]


@dataclass(frozen=True)
class KeplerianOrbit:
    """Bound two-body orbit with injectable anomaly solver.

    Physics derivation:
    A closed Keplerian orbit is described by a period, semi-major axis,
    eccentricity, and plane orientation. Position at a given time follows from
    mean anomaly ``M = (2 pi / period) * time``, eccentric anomaly from
    Kepler's equation, and focus-centered ellipse coordinates
    ``x' = a(cos(E) - e)`` and ``y' = a sqrt(1 - e**2) sin(E)``.

    Geometric assumptions:
    The host star is fixed at the origin, periapsis lies on the positive
    x-axis, longitude of ascending node and argument of periapsis are zero,
    and inclination rotates the orbital plane about the x-axis.

    Unit expectations:
    ``period`` is a time quantity, ``semi_major_axis`` is a length quantity,
    ``eccentricity`` is dimensionless with ``0 <= e < 1``, and
    ``inclination`` is an angle quantity. Returned positions use the same
    length unit as ``semi_major_axis``.
    """

    period: u.Quantity
    semi_major_axis: u.Quantity
    eccentricity: u.Quantity
    inclination: u.Quantity
    solver: KeplerEquationSolver = field(default_factory=NewtonRaphsonKeplerSolver)

    def __post_init__(self) -> None:
        """Validate the units and bounds required by elliptic orbital geometry.

        Physics derivation and assumptions:
        A bound two-body ellipse needs a positive period, a positive orbital
        scale, a dimensionless eccentricity below unity, and an inclination
        angle. These checks keep construction separate from coordinate
        calculation while preserving the model's geometric contract.
        """

        require_convertible_unit(self.period, u.day, "period")
        require_positive_quantity(self.period, "period")
        require_convertible_unit(
            self.semi_major_axis,
            REFERENCE_LENGTH_UNIT,
            "semi_major_axis",
        )
        require_positive_quantity(self.semi_major_axis, "semi_major_axis")
        require_bound_eccentricity(self.eccentricity)
        require_convertible_unit(self.inclination, u.rad, "inclination")

    def position_at(self, time: u.Quantity) -> CartesianPosition:
        """Return the focus-centered Cartesian position at a time from periapsis.

        Physics derivation:
        Time is converted to mean anomaly with ``M = (2 pi / P) t``. The
        injected solver finds the eccentric anomaly ``E``. The orbit is first
        evaluated in its own plane, then rotated by inclination into the
        project coordinate frame.

        Geometric assumptions:
        The coordinate origin is the host star. ``time = 0`` is periapsis.
        Periapsis points along positive x, and inclination is a rotation about
        the x-axis.

        Unit expectations:
        ``time`` must be a time quantity convertible to the orbit period's
        units. The returned ``(x, y, z)`` values use the same length unit as
        ``semi_major_axis``.
        """

        mean_anomaly = calculate_mean_anomaly(time, self.period)
        eccentric_anomaly = self.solver.solve(mean_anomaly, self.eccentricity)
        orbital_x, orbital_y = calculate_orbital_plane_position(
            eccentric_anomaly,
            self.semi_major_axis,
            self.eccentricity,
        )

        return rotate_orbital_plane_by_inclination(
            orbital_x,
            orbital_y,
            self.inclination,
        )


def calculate_mean_anomaly(time: u.Quantity, period: u.Quantity) -> u.Quantity:
    """Calculate mean anomaly from elapsed time and orbital period.

    Physics derivation:
    Mean anomaly is the uniformly advancing orbital phase for a Keplerian
    ellipse. With mean motion ``n = 2 pi / P`` and time measured from
    periapsis, ``M = n t``. This function returns that phase as an Astropy
    angle while leaving periodic normalization to the Kepler solver.

    Geometric assumptions:
    ``time = 0`` corresponds to periapsis passage. The orbit is periodic and
    unperturbed, so elapsed times beyond one period are valid.

    Unit expectations:
    ``time`` and ``period`` must be Astropy time quantities. The result is an
    angle quantity in radians.
    """

    require_convertible_unit(time, period.unit, "time")
    require_positive_quantity(period, "period")
    period_fraction = (time / period).to_value(u.dimensionless_unscaled)

    return period_fraction * FULL_TURN_ANGLE


def calculate_orbital_plane_position(
    eccentric_anomaly: u.Quantity,
    semi_major_axis: u.Quantity,
    eccentricity: u.Quantity,
) -> PlanarPosition:
    """Calculate focus-centered ``(x', y')`` coordinates in the orbital plane.

    Physics derivation:
    The auxiliary-circle parameterization of an ellipse gives
    ``x_centered = a cos(E)`` and ``y = b sin(E)`` with
    ``b = a sqrt(1 - e**2)``. The host star is one focus, offset from the
    ellipse center by ``a e`` along the major axis, so the focus-centered
    coordinate is ``x' = a(cos(E) - e)``.

    Geometric assumptions:
    The major axis lies along x, periapsis is at positive x, and the host star
    is the origin. No inclination or sky projection is applied here.

    Unit expectations:
    ``eccentric_anomaly`` must be an angle quantity, ``semi_major_axis`` a
    length quantity, and ``eccentricity`` dimensionless. Returned coordinates
    use the same length unit as ``semi_major_axis``.
    """

    anomaly = require_convertible_unit(
        eccentric_anomaly,
        u.rad,
        "eccentric_anomaly",
    )
    require_convertible_unit(
        semi_major_axis,
        REFERENCE_LENGTH_UNIT,
        "semi_major_axis",
    )
    eccentricity_value = require_bound_eccentricity(eccentricity).to_value(
        u.dimensionless_unscaled
    )
    anomaly_radians = anomaly.to_value(u.rad)
    semi_minor_scale = np.sqrt(BOUND_ECCENTRICITY_MAXIMUM - eccentricity_value**2)

    orbital_x = semi_major_axis * (np.cos(anomaly_radians) - eccentricity_value)
    orbital_y = semi_major_axis * semi_minor_scale * np.sin(anomaly_radians)

    return orbital_x, orbital_y


def rotate_orbital_plane_by_inclination(
    orbital_x: u.Quantity,
    orbital_y: u.Quantity,
    inclination: u.Quantity,
) -> CartesianPosition:
    """Rotate orbital-plane coordinates into three dimensions.

    Physics derivation:
    With longitude of ascending node and argument of periapsis fixed to zero,
    the only orientation transform is a rotation about the x-axis. The
    rotation matrix gives ``x = x'``, ``y = y' cos(i)``, and
    ``z = y' sin(i)``.

    Geometric assumptions:
    The orbital x-axis is unchanged by inclination. Positive inclination
    lifts positive orbital-plane y into positive z.

    Unit expectations:
    ``orbital_x`` and ``orbital_y`` must be length quantities with compatible
    units. ``inclination`` must be an angle quantity. Returned coordinates use
    the unit of ``orbital_x``.
    """

    require_convertible_unit(orbital_y, orbital_x.unit, "orbital_y")
    inclination_angle = require_convertible_unit(inclination, u.rad, "inclination")
    inclination_radians = inclination_angle.to_value(u.rad)

    x = orbital_x
    y = orbital_y.to(orbital_x.unit) * np.cos(inclination_radians)
    z = orbital_y.to(orbital_x.unit) * np.sin(inclination_radians)

    return x, y, z
