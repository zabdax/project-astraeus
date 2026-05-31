"""History module for the dashboard."""

import streamlit as st

def render(main_panel, right_panel) -> None:
    """Render the History module."""
    with main_panel:
        st.title("History - Coming Soon")
        st.write("Feature under construction.")
        
    if right_panel:
        with right_panel:
            st.subheader("History Details")
            st.write("Select an item to view details.")
