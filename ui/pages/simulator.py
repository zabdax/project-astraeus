"""Simulation module for the dashboard."""

import streamlit as st
import numpy as np
from astropy import units as u
from types import SimpleNamespace

from astraeus.dashboard.figures import (
    make_light_curve_figure,
    make_residuals_figure,
)
from astraeus.core.transit_model import generate_multi_planet_transit
from astraeus.dashboard.simulation import semi_major_axis_for_solar_mass
from astraeus.data.preprocessing import inject_gaussian_noise


def render(main_panel, right_panel) -> None:
    """Render the Simulation module."""
    
    if "multi_planets" not in st.session_state:
        st.session_state.multi_planets = [
            {"radius_ratio": 0.10, "period_days": 3.0, "eccentricity": 0.0, "inclination_degrees": 88.5}
        ]
        
    if "snr" not in st.session_state:
        st.session_state.snr = 200

    with main_panel:
        st.title("ASTRAEUS Transit Dashboard - System Builder")
        
        st.session_state.snr = st.slider("Target Signal-to-Noise Ratio (SNR)", 50, 500, st.session_state.snr, 10)
        
        if st.button("Add Planet"):
            st.session_state.multi_planets.append(
                {"radius_ratio": 0.05, "period_days": 5.0, "eccentricity": 0.0, "inclination_degrees": 90.0}
            )
            
        for i, p in enumerate(st.session_state.multi_planets):
            st.markdown(f"### Planet {i+1}")
            cols = st.columns(4)
            p["radius_ratio"] = cols[0].slider("Radius Ratio", 0.01, 0.20, p["radius_ratio"], 0.005, key=f"rr_{i}")
            p["period_days"] = cols[1].slider("Period (days)", 0.5, 20.0, float(p["period_days"]), 0.1, key=f"pd_{i}")
            p["eccentricity"] = cols[2].slider("Eccentricity", 0.0, 0.9, p["eccentricity"], 0.01, key=f"ecc_{i}")
            p["inclination_degrees"] = cols[3].slider("Inclination", 80.0, 90.0, p["inclination_degrees"], 0.1, key=f"inc_{i}")
            
        # Simulation
        samples = 900
        max_period = max([p["period_days"] for p in st.session_state.multi_planets]) if st.session_state.multi_planets else 1.0
        time_days = np.linspace(0.0, max_period, samples)
        time = time_days * u.day
        
        planet_list = []
        for p in st.session_state.multi_planets:
            sma = semi_major_axis_for_solar_mass(p["period_days"]).to(u.R_sun)
            planet_list.append({
                "R_star": 1.0 * u.R_sun,
                "period": p["period_days"] * u.day,
                "semi_major_axis": sma,
                "eccentricity": p["eccentricity"] * u.dimensionless_unscaled,
                "inclination": p["inclination_degrees"] * u.deg,
                "R_planet": p["radius_ratio"] * 1.0 * u.R_sun,
                "u1": 0.0,
                "u2": 0.0,
            })
            
        if planet_list:
            theoretical_flux = generate_multi_planet_transit(time, planet_list)
        else:
            theoretical_flux = np.ones_like(time_days)
            
        observed_flux = inject_gaussian_noise(
            theoretical_flux,
            snr=float(st.session_state.snr),
            seed=42,
        )
        
        noise_sigma = float(np.mean(np.abs(theoretical_flux)) / st.session_state.snr)
        
        # Mock simulation object for figures
        simulation = SimpleNamespace(
            time_days=time_days,
            theoretical_flux=theoretical_flux,
            observed_flux=observed_flux,
            residuals=observed_flux - theoretical_flux,
            noise_sigma=noise_sigma,
        )
        
        st.subheader("Light Curve")
        st.plotly_chart(make_light_curve_figure(simulation), width="stretch")
        
        st.subheader("Residuals")
        st.plotly_chart(make_residuals_figure(simulation), width="stretch")
        
    if right_panel:
        with right_panel:
            st.subheader("Simulation Logs")
            st.write("Multi-planet simulation generated.")
            st.json({
                "snr": st.session_state.snr,
                "planets": st.session_state.multi_planets
            })
