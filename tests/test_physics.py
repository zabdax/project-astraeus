import numpy as np
from astropy import units as u

from astraeus.core.transit_model import generate_geometric_transit, generate_model_flux
from astraeus.core.orbits import KeplerianOrbit

def test_transit_depth():
    """Assert that generate_transit_model(time, rp_rstar=0.1) yields exactly 1% depth."""
    
    def generate_transit_model(time: u.Quantity, rp_rstar: float) -> np.ndarray:
        return generate_model_flux(
            time=time,
            period=10.0 * u.day,
            semi_major_axis=20.0 * u.R_sun,
            eccentricity=0.0 * u.dimensionless_unscaled,
            inclination=90.0 * u.deg,
            R_star=1.0 * u.R_sun,
            R_planet=rp_rstar * u.R_sun,
            u1=0.0,
            u2=0.0,
        )

    # For a circular orbit with inc=90, periapsis (t=0) is at (a, 0, 0).
    # Transit (z > 0, x=0, y=0) occurs at t = P/4.
    transit_time = np.array([2.5]) * u.day
    flux = generate_transit_model(transit_time, rp_rstar=0.1)
    
    # Assert depth is exactly (0.1)^2 = 0.01
    assert np.isclose(1.0 - flux[0], 0.01)


def test_limb_darkening_module():
    """Test the limb darkening module: assert flux remains at 1.0 when fully visible, 
    and drops proportionally at the center.
    """
    R_star = 1.0 * u.R_sun
    R_planet = 0.1 * u.R_sun
    u1, u2 = 0.3, 0.1

    # 1. Star is fully visible (separation > R_star + R_planet)
    separation_out = 1.5 * u.R_sun
    drop_out = generate_geometric_transit(separation_out, R_star, R_planet, u1=u1, u2=u2)
    assert np.isclose(drop_out.value, 0.0)

    # 2. Planet traverses the center (separation = 0)
    separation_in = 0.0 * u.R_sun
    drop_in = generate_geometric_transit(separation_in, R_star, R_planet, u1=u1, u2=u2)
    
    # Expected relative depth at center is larger than uniform disk depth
    # I_center = 1.0, I_average = 1 - u1/3 - u2/6
    expected_depth = (0.1**2) / (1 - u1/3 - u2/6)
    assert np.isclose(drop_in.value, expected_depth, rtol=1e-2)


def test_kepler_solver_eccentric_orbits():
    """Verify that Kepler solver correctly maps eccentric orbits at apsides 
    and follows Kepler's Second Law.
    """
    period = 10.0 * u.day
    semi_major_axis = 1.0 * u.AU
    eccentricity = 0.5 * u.dimensionless_unscaled
    inclination = 90.0 * u.deg

    orbit = KeplerianOrbit(
        period=period,
        semi_major_axis=semi_major_axis,
        eccentricity=eccentricity,
        inclination=inclination,
    )

    # 1. Test at periastron (t = 0)
    x_p, y_p, z_p = orbit.position_at(0.0 * u.day)
    # Distance at periastron = a(1 - e) = 0.5 AU
    assert np.isclose(x_p.to_value(u.AU), 0.5)
    assert np.isclose(y_p.to_value(u.AU), 0.0)
    assert np.isclose(z_p.to_value(u.AU), 0.0)

    # 2. Test at apoastron (t = P/2 = 5 days)
    x_a, y_a, z_a = orbit.position_at(5.0 * u.day)
    # Distance at apoastron = a(1 + e) = 1.5 AU (coordinate is negative x in focus-centered)
    assert np.isclose(x_a.to_value(u.AU), -1.5)
    assert np.isclose(y_a.to_value(u.AU), 0.0)
    assert np.isclose(z_a.to_value(u.AU), 0.0)

    # 3. Test Kepler's Second Law numerically at apsides (r_p * v_p = r_a * v_a)
    dt = 0.0001 * u.day
    
    # Velocity at periastron
    x_p1, y_p1, z_p1 = orbit.position_at(dt)
    x_pm1, y_pm1, z_pm1 = orbit.position_at(-dt)
    v_p = np.sqrt((x_p1 - x_pm1)**2 + (y_p1 - y_pm1)**2 + (z_p1 - z_pm1)**2) / (2 * dt)
    
    # Velocity at apoastron
    x_a1, y_a1, z_a1 = orbit.position_at(5.0 * u.day + dt)
    x_am1, y_am1, z_am1 = orbit.position_at(5.0 * u.day - dt)
    v_a = np.sqrt((x_a1 - x_am1)**2 + (y_a1 - y_am1)**2 + (z_a1 - z_am1)**2) / (2 * dt)

    r_p = 0.5 * u.AU
    r_a = 1.5 * u.AU

    angular_momentum_p = r_p * v_p
    angular_momentum_a = r_a * v_a

    # Conserved angular momentum
    assert np.isclose(angular_momentum_p.value, angular_momentum_a.value, rtol=1e-3)
