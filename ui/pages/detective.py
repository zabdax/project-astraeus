"""Detective module for the dashboard."""

import streamlit as st

def render(main_panel, right_panel) -> None:
    """Render the Detective module."""
    with main_panel:
        st.title("Detective - Coming Soon")
        st.write("Feature under construction.")
        
    if right_panel:
        with right_panel:
            st.subheader("Detective Log")
            st.write("Awaiting inputs...")
