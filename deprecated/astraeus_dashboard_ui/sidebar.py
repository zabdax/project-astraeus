"""Application sidebar controls for dashboard settings and simulations."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.scenario import DashboardTransitScenario


def render_app_sidebar() -> DashboardTransitScenario:
    """Render app-wide sidebar controls and return the selected simulation scenario."""

    with st.sidebar:
        st.title("ASTRAEUS")
        return render_scenario_controls()





def render_scenario_controls() -> DashboardTransitScenario:
    """Render simulation controls and return the selected scenario."""

    st.subheader("Simulation Settings")
    radius_ratio = st.slider(
        "Planetary Radius Ratio (Rp/Rs)",
        0.01,
        0.20,
        0.10,
        0.005,
    )
    period_days = st.slider("Orbital Period (days)", 0.5, 20.0, 3.0, 0.1)
    eccentricity = st.slider("Eccentricity (e)", 0.0, 0.9, 0.0, 0.01)
    inclination_degrees = st.slider(
        "Inclination (degrees)",
        80.0,
        90.0,
        88.5,
        0.1,
    )
    snr = st.slider("Target Signal-to-Noise Ratio (SNR)", 50, 500, 200, 10)

    return DashboardTransitScenario(
        radius_ratio=radius_ratio,
        period_days=period_days,
        eccentricity=eccentricity,
        inclination_degrees=inclination_degrees,
        snr=snr,
    )
