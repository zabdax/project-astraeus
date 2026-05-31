"""Application routing logic."""

import streamlit as st

from ui.pages import simulator, lab, detective, history, settings

def render_route(selected_feature: str, main_panel, right_panel) -> None:
    """Route the selected feature to the corresponding page module."""
    if selected_feature == "Simulation":
        simulator.render(main_panel, right_panel)
    elif selected_feature == "Lab":
        lab.render(main_panel, right_panel)
    elif selected_feature == "Detective":
        detective.render(main_panel, right_panel)
    elif selected_feature == "History":
        history.render(main_panel, right_panel)
    elif selected_feature == "Settings":
        settings.render(main_panel, right_panel)
    else:
        with main_panel:
            st.title(f"{selected_feature} - Coming Soon")
