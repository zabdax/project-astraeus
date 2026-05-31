"""Simulation module for the dashboard."""

import streamlit as st

from astraeus.dashboard.scenario import DashboardTransitScenario
from astraeus.dashboard.simulation import (
    DashboardSimulation,
    generate_dashboard_simulation,
)
from astraeus.dashboard.ui.sidebar import render_app_sidebar
from astraeus.dashboard.ui.simulation_panel import render_simulation_panel


@st.cache_data(show_spinner=False)
def _cached_simulation(scenario: DashboardTransitScenario) -> DashboardSimulation:
    """Cache deterministic dashboard calculations by scenario."""
    return generate_dashboard_simulation(scenario)


def render(main_panel, right_panel) -> None:
    """Render the Simulation module."""
    scenario = render_app_sidebar()
    with main_panel:
        st.title("ASTRAEUS Transit Dashboard")
        simulation = _cached_simulation(scenario)
        render_simulation_panel(simulation)
        
    if right_panel:
        with right_panel:
            st.subheader("Simulation Logs")
            st.write("Simulation completed successfully.")
            st.json({
                "radius_ratio": scenario.radius_ratio,
                "period_days": scenario.period_days,
                "eccentricity": scenario.eccentricity,
                "inclination_degrees": scenario.inclination_degrees,
                "snr": scenario.snr
            })
