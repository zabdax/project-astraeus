"""Streamlit application shell for the ASTRAEUS dashboard."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.scenario import DashboardTransitScenario
from astraeus.dashboard.simulation import (
    DashboardSimulation,
    generate_dashboard_simulation,
)
from astraeus.dashboard.ui.data_ingestion_panel import render_data_ingestion_panel
from astraeus.dashboard.ui.sidebar import render_app_sidebar
from astraeus.dashboard.ui.simulation_panel import render_simulation_panel
from astraeus.dashboard.ui.styles import inject_page_styles
from astraeus.dashboard.ui.layout import workbench_layout
from astraeus.dashboard.ui.settings import render_settings_panel
from astraeus.dashboard.ui.components import render_floating_chat

def render_dashboard() -> None:
    """Render the interactive ASTRAEUS dashboard."""

    st.set_page_config(
        page_title="ASTRAEUS Transit Dashboard",
        page_icon=".",
        layout="wide",
    )
    inject_page_styles()
    
    with workbench_layout() as (selected_feature, main_panel, right_panel):
        if selected_feature == "Settings":
            with main_panel:
                render_settings_panel()
        elif selected_feature == "Simulation":
            scenario = render_app_sidebar()
            with main_panel:
                st.title("ASTRAEUS Transit Dashboard")
                simulation = _cached_simulation(scenario)
                render_simulation_panel(simulation)
        elif selected_feature == "Lab":
            with main_panel:
                st.title("Data Ingestion Lab")
                render_data_ingestion_panel()
        else:
            with main_panel:
                st.title(f"{selected_feature} - Coming Soon")
                
    # Render the persistent floating AI Chat
    render_floating_chat()

@st.cache_data(show_spinner=False)
def _cached_simulation(scenario: DashboardTransitScenario) -> DashboardSimulation:
    """Cache deterministic dashboard calculations by scenario."""

    return generate_dashboard_simulation(scenario)
