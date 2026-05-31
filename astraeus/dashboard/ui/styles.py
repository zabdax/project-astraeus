"""Dashboard page-level Streamlit styling."""

from __future__ import annotations

import streamlit as st


def inject_page_styles() -> None:
    """Apply small layout refinements without changing Streamlit behavior."""

    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1220px;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(148, 163, 184, 0.25);
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            background: rgba(15, 23, 42, 0.025);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
