"""Streamlit application shell for the ASTRAEUS dashboard."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.scenario import DashboardTransitScenario
from astraeus.dashboard.simulation import (
    DashboardSimulation,
    generate_dashboard_simulation,
)
from astraeus.dashboard.ui.data_ingestion_panel import render_data_ingestion_panel
from astraeus.dashboard.ui.sidebar import render_scenario_controls
from astraeus.dashboard.ui.simulation_panel import render_simulation_panel
from astraeus.dashboard.ui.styles import inject_page_styles


def render_dashboard() -> None:
    """Render the interactive ASTRAEUS dashboard."""

    st.set_page_config(
        page_title="ASTRAEUS Transit Dashboard",
        page_icon=".",
        layout="wide",
    )
    inject_page_styles()

    st.title("ASTRAEUS Transit Dashboard")
    tab_data, tab_sim = st.tabs(["Data Ingestion", "Transit Simulation"])

    with tab_data:
        render_data_ingestion_panel()

    with tab_sim:
        scenario = render_scenario_controls()
        simulation = _cached_simulation(scenario)
        render_simulation_panel(simulation)


@st.cache_data(show_spinner=False)
def _cached_simulation(scenario: DashboardTransitScenario) -> DashboardSimulation:
    """Cache deterministic dashboard calculations by scenario."""

    return generate_dashboard_simulation(scenario)
