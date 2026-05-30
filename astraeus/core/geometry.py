"""Reusable projected geometry utilities for ASTRAEUS physics models."""

from __future__ import annotations

import numpy as np
from astropy import units as u

from astraeus.core.constants import REFERENCE_LENGTH_UNIT
from astraeus.core.validation import (
    require_convertible_unit,
    require_non_negative_quantity,
    require_positive_quantity,
)


def calculate_sky_separation(
    x: u.Quantity,
    y: u.Quantity,
    z: u.Quantity,
) -> u.Quantity:
    """Calculate projected star-planet center separation on the sky plane.

    Physics derivation:
    For a coordinate frame where the star center is the origin and the
    observer's line of sight is the z-axis, the sky plane is spanned by x and
    y. The projected center-to-center separation is therefore
    ``d = sqrt(x**2 + y**2)``. The z coordinate is not part of the projected
    distance, but it is validated so callers keep a complete three-dimensional
    position contract.

    Geometric assumptions:
    The host star is centered at ``(0, 0, 0)``, the planet is represented by
    its center position, and the z-axis points along the line of sight. This
    function does not decide whether the planet is in front of the star.

    Unit expectations:
    ``x``, ``y``, and ``z`` must be Astropy length quantities with compatible
    units. The returned separation has the unit of ``x``.
    """

    require_convertible_unit(x, REFERENCE_LENGTH_UNIT, "x")
    require_convertible_unit(y, x.unit, "y")
    require_convertible_unit(z, x.unit, "z")

    x_value = x.to_value(x.unit)
    y_value = y.to_value(x.unit)

    return np.hypot(x_value, y_value) * x.unit


def calculate_circle_overlap_area(
    separation: u.Quantity,
    first_radius: u.Quantity,
    second_radius: u.Quantity,
) -> u.Quantity:
    """Calculate projected overlap area between two circular disks.

    Physics derivation:
    Two disks with radii ``R1`` and ``R2`` and center separation ``d`` have no
    overlap when ``d >= R1 + R2``. If one disk lies wholly inside the other,
    the overlap is the area of the smaller disk, ``pi min(R1, R2)**2``. In the
    boundary-intersection regime, ``abs(R1 - R2) < d < R1 + R2``, the lens
    area is:
    ``A = R1**2 acos((d**2 + R1**2 - R2**2) / (2 d R1))
    + R2**2 acos((d**2 + R2**2 - R1**2) / (2 d R2))
    - 0.5 sqrt((-d + R1 + R2)(d + R1 - R2)(d - R1 + R2)
    (d + R1 + R2))``.

    Geometric assumptions:
    The disks are perfect circles in a common projection plane. This function
    is purely geometric and does not assign physical brightness, opacity, or
    line-of-sight ordering.

    Unit expectations:
    ``separation``, ``first_radius``, and ``second_radius`` must be Astropy
    length quantities with compatible units. Radii must be strictly positive,
    and separation must be non-negative. The returned area has units of
    ``separation.unit**2``.
    """

    require_convertible_unit(separation, REFERENCE_LENGTH_UNIT, "separation")
    require_convertible_unit(first_radius, separation.unit, "first_radius")
    require_convertible_unit(second_radius, separation.unit, "second_radius")
    require_non_negative_quantity(separation, "separation")
    require_positive_quantity(first_radius, "first_radius")
    require_positive_quantity(second_radius, "second_radius")

    d, radius_1, radius_2 = np.broadcast_arrays(
        separation.to_value(separation.unit),
        first_radius.to_value(separation.unit),
        second_radius.to_value(separation.unit),
    )
    overlap_area = np.zeros_like(d, dtype=float)

    smaller_radius = np.minimum(radius_1, radius_2)
    contained = d <= np.abs(radius_1 - radius_2)
    disjoint = d >= (radius_1 + radius_2)
    intersecting = ~(contained | disjoint)

    overlap_area = np.where(
        contained,
        np.pi * smaller_radius**2,
        overlap_area,
    )

    if np.any(intersecting):
        overlap_area[intersecting] = _calculate_intersecting_circle_area(
            d[intersecting],
            radius_1[intersecting],
            radius_2[intersecting],
        )

    return overlap_area * separation.unit**2


def _calculate_intersecting_circle_area(
    separation: np.ndarray,
    first_radius: np.ndarray,
    second_radius: np.ndarray,
) -> np.ndarray:
    """Return the lens area for two partially intersecting circles."""

    first_argument = (
        separation**2 + first_radius**2 - second_radius**2
    ) / (2.0 * separation * first_radius)
    second_argument = (
        separation**2 + second_radius**2 - first_radius**2
    ) / (2.0 * separation * second_radius)
    lens_root = (
        (-separation + first_radius + second_radius)
        * (separation + first_radius - second_radius)
        * (separation - first_radius + second_radius)
        * (separation + first_radius + second_radius)
    )

    return (
        first_radius**2 * np.arccos(np.clip(first_argument, -1.0, 1.0))
        + second_radius**2 * np.arccos(np.clip(second_argument, -1.0, 1.0))
        - 0.5 * np.sqrt(np.maximum(lens_root, 0.0))
    )
