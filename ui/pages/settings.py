"""Settings module for the dashboard."""

import streamlit as st
from astraeus.dashboard.ui.settings import render_settings_panel

def render(main_panel, right_panel) -> None:
    """Render the Settings module."""
    with main_panel:
        render_settings_panel()
        
    if right_panel:
        with right_panel:
            st.subheader("Settings Info")
            st.write("Configuration updates are saved automatically.")
