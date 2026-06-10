import math
import numpy as np

class PhysicalPropertiesEngine:
    @staticmethod
    def derive(period_days: float, transit_depth_fraction: float, st_rad: float, st_teff: float, st_mass: float, sy_jmag: float) -> dict:
        R_SUN_TO_R_EARTH = 109.2
        planet_radius_earth = 0.0
        
        if transit_depth_fraction > 0 and st_rad > 0:
            planet_radius_earth = float(st_rad * math.sqrt(transit_depth_fraction) * R_SUN_TO_R_EARTH)

        bond_albedo = 0.3
        equilibrium_temp_k = 0.0

        if period_days > 0 and st_teff > 0 and st_mass > 0 and st_rad > 0:
            period_yr = period_days / 365.25
            semi_major_axis_au = (st_mass * period_yr ** 2) ** (1.0 / 3.0)
            stellar_radius_au = st_rad * 0.00465047
            if semi_major_axis_au > 0:
                equilibrium_temp_k = float(
                    st_teff * np.sqrt(stellar_radius_au / (2.0 * semi_major_axis_au)) * (1.0 - bond_albedo) ** 0.25
                )

        jwst_tsm_score = 0.0
        if planet_radius_earth > 0 and equilibrium_temp_k > 0 and st_rad > 0:
            if planet_radius_earth < 1.5:
                tsm_scale = 0.190
            elif planet_radius_earth < 2.75:
                tsm_scale = 1.26
            elif planet_radius_earth < 4.0:
                tsm_scale = 1.28
            else:
                tsm_scale = 1.15
            
            planet_mass_earth = planet_radius_earth ** 2.06
            if planet_mass_earth > 0:
                jwst_tsm_score = float(
                    tsm_scale * (planet_radius_earth ** 3 * equilibrium_temp_k) /
                    (planet_mass_earth * st_rad ** 2) * 10.0 ** (-sy_jmag / 5.0)
                )

        return {
            'planet_radius_earth': round(planet_radius_earth, 4),
            'equilibrium_temp_k': round(equilibrium_temp_k, 2),
            'jwst_tsm_score': round(jwst_tsm_score, 4)
        }
