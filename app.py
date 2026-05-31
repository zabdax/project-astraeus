"""Streamlit entry point for the ASTRAEUS dashboard."""

import streamlit as st
from astraeus.dashboard.ui.layout import workbench_layout
from astraeus.dashboard.ui.styles import inject_page_styles
from astraeus.dashboard.ui.components import render_floating_chat

from route import render_route


def main():
    """Render the interactive ASTRAEUS dashboard."""
    
    st.set_page_config(
        page_title="ASTRAEUS Transit Dashboard",
        page_icon=".",
        layout="wide",
    )
    inject_page_styles()
    
    with workbench_layout() as (selected_feature, main_panel, right_panel):
        render_route(selected_feature, main_panel, right_panel)
                
    # Render the persistent floating AI Chat
    render_floating_chat()


if __name__ == "__main__":
    main()
