"""Data Ingestion Lab module for the dashboard."""

import streamlit as st
from astraeus.dashboard.ui.data_ingestion_panel import render_data_ingestion_panel

def render(main_panel, right_panel) -> None:
    """Render the Lab module."""
    with main_panel:
        st.title("Data Ingestion Lab")
        render_data_ingestion_panel()
        
    if right_panel:
        with right_panel:
            st.subheader("Lab Diagnostics")
            st.write("Ready for data ingestion.")
