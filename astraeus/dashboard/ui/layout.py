"""
Base layout structure for the ASTRAEUS 3-panel professional workbench.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import streamlit as st


def apply_astro_theme() -> None:
    """Injects CSS for a Modern Minimal / Astro-vibe theme."""
    st.markdown(
        """
        <style>
        /* Base application background and typography */
        .stApp {
            background-color: #0A0E17 !important; /* Deep space dark blue */
            color: #E2E8F0 !important;
            font-family: 'Fira Code', 'Courier New', monospace !important;
        }

        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background-color: #0F172A !important;
            border-right: 1px solid #1E293B !important;
        }

        /* Headers */
        h1, h2, h3, h4, h5, h6 {
            color: #A78BFA !important; /* Soft purple */
            font-family: 'Fira Code', 'Courier New', monospace !important;
            letter-spacing: -0.02em !important;
        }

        /* Metric widgets and panels */
        div[data-testid="stMetric"] {
            border: 1px solid #1E293B !important;
            border-radius: 8px !important;
            padding: 1rem !important;
            background: #111827 !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
        }

        /* Hide top padding to maximize workbench feel */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 2rem !important;
            max-width: 95% !important;
        }

        /* Main and Right panel columns styling */
        [data-testid="column"] {
            background-color: #0F172A;
            border-radius: 12px;
            padding: 1rem;
            border: 1px solid #1E293B;
            height: calc(100vh - 6rem);
            overflow-y: auto;
        }

        /* Footer in sidebar */
        .astro-footer {
            margin-top: auto;
            padding-top: 2rem;
            color: #64748B;
            font-size: 0.8rem;
            text-align: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_left_nav() -> str:
    """
    Renders the left navigation panel (Nav).
    Returns the currently selected feature.
    """
    with st.sidebar:
        st.markdown("## 🚀 ASTRAEUS")
        st.markdown("<span style='color: #64748B; font-size: 0.9em; margin-bottom: 2rem; display: block;'>Professional Workbench</span>", unsafe_allow_html=True)
        
        # Feature List Navigation
        st.markdown("### Navigation")
        selected_feature = st.radio(
            "Features",
            options=["Simulation", "Lab", "Detective", "History"],
            label_visibility="collapsed",
        )
        
        # Branding / Footer at bottom
        st.markdown(
            """
            <div class='astro-footer'>
                ASTRAEUS OS v1.0<br>
                <span style='color: #8B5CF6;'>● System Online</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        return str(selected_feature)


@contextmanager
def workbench_layout() -> Iterator[tuple[str, Any, Any]]:
    """
    Sets up the 3-panel workbench.
    Yields (selected_feature, main_panel, right_panel)
    
    - Left (Nav): Provided by st.sidebar automatically.
    - Center (Main): The primary workspace for feature UIs.
    - Right (Assets): Panel for displaying outputs, plots, logs.
    """
    apply_astro_theme()
    
    # 1. Left (Nav) Panel
    selected = render_left_nav()
    
    # Top bar for right panel toggle
    col_empty, col_toggle = st.columns([9, 1])
    with col_toggle:
        # Use a checkbox or toggle to collapse the Right Panel
        show_assets = st.checkbox("Assets Panel", value=True)
        
    st.markdown("---")
        
    # 2 & 3. Center (Main) and Right (Assets) Panels
    if show_assets:
        main_panel, right_panel = st.columns([7, 3], gap="large")
    else:
        main_panel = st.columns([1])[0]
        right_panel = None
        
    yield selected, main_panel, right_panel
