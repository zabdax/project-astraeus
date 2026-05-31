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

        /* Sticky Header logic using :has() */
        div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div.element-container:has(.sidebar-header-wrapper) {
            position: sticky;
            top: 0;
            z-index: 999;
            background-color: #0F172A;
            margin-top: -6rem; 
            padding-top: 6rem;
            margin-left: -1.5rem;
            margin-right: -1.5rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid #1E293B;
        }

        /* Sticky Footer logic using :has() */
        div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div.element-container:has(.astro-footer) {
            position: sticky;
            bottom: 0;
            z-index: 999;
            background-color: #0F172A;
            margin-bottom: -6rem; 
            padding-bottom: 6rem;
            margin-left: -1.5rem;
            margin-right: -1.5rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid #1E293B;
        }

        .astro-footer {
            color: #64748B;
            font-size: 0.8rem;
            text-align: center;
        }

        /* Customize Sidebar Toggle Icon (SVG Dashboard Icon) */
        [data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"], button[kind="headerNoPadding"], button[aria-label="Expand sidebar"] {
            position: relative;
        }

        [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg, button[kind="headerNoPadding"] svg, button[aria-label="Expand sidebar"] svg {
            opacity: 0 !important; /* Keep original dimensions intact */
        }
        
        [data-testid="stSidebarCollapseButton"]::after, [data-testid="collapsedControl"]::after, button[kind="headerNoPadding"]::after, button[aria-label="Expand sidebar"]::after {
            content: "";
            position: absolute;
            top: 50%;
            left: 50%;
            width: 20px;
            height: 20px;
            transform: translate(-50%, -50%); /* Perfectly center it inside the button */
            background-image: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='18' height='18' rx='2' ry='2'/%3E%3Cline x1='9' y1='3' x2='9' y2='21'/%3E%3C/svg%3E");
            background-size: contain;
            background-repeat: no-repeat;
            transition: all 0.2s ease-in-out;
            pointer-events: none; /* Do not block clicks */
        }
        
        [data-testid="stSidebarCollapseButton"]:hover::after, [data-testid="collapsedControl"]:hover::after, button[kind="headerNoPadding"]:hover::after, button[aria-label="Expand sidebar"]:hover::after {
            background-image: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%23F8FAFC' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='18' height='18' rx='2' ry='2'/%3E%3Cline x1='9' y1='3' x2='9' y2='21'/%3E%3C/svg%3E");
        }

        /* Sidebar Navigation Button Styling */
        [data-testid="stSidebar"] div[data-testid="stButton"] > button {
            width: 100% !important;
            text-align: left !important;
            display: flex !important;
            justify-content: flex-start !important;
            padding: 0.5rem 1rem !important;
            background-color: transparent !important;
            border: none !important;
            color: #94A3B8 !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
            background-color: rgba(255, 255, 255, 0.05) !important;
            color: #F8FAFC !important;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
            background-color: rgba(167, 139, 250, 0.15) !important;
            color: #A78BFA !important;
            border-left: 3px solid #A78BFA !important;
            border-radius: 4px 8px 8px 4px !important;
        }
        
        [data-testid="stSidebar"] div[data-testid="stButton"] > button p {
            font-size: 1rem !important;
            margin: 0 !important;
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
        # Sticky Header
        st.markdown(
            """
            <div class='sidebar-header-wrapper'>
                <h2 style='margin:0; color:#A78BFA; font-family:"Fira Code", monospace; font-size: 1.5rem;'>🚀 ASTRAEUS</h2>
                <span style='color: #64748B; font-size: 0.8rem;'>Professional Workbench</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        # Add some vertical space to push buttons down
        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
        
        if "current_route" not in st.session_state:
            st.session_state.current_route = "Simulation"
            
        # Navigation Options with Professional Icons
        options = [
            ("Simulation", ":material/rocket_launch:"),
            ("Lab", ":material/science:"),
            ("Detective", ":material/manage_search:"),
            ("History", ":material/history:"),
            ("Settings", ":material/settings:")
        ]
        
        for feature, icon in options:
            # Highlight the currently selected button
            btn_type = "primary" if st.session_state.current_route == feature else "secondary"
            if st.button(feature, icon=icon, use_container_width=True, type=btn_type):
                st.session_state.current_route = feature
                st.rerun()
                
        selected_feature = st.session_state.current_route
        
        # Push footer down dynamically 
        st.markdown("<div style='flex-grow: 1; min-height: 15rem;'></div>", unsafe_allow_html=True)
        
        # Sticky Footer
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
