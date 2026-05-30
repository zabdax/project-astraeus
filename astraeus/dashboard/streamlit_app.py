"""Streamlit composition layer for the ASTRAEUS dashboard."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.figures import (
    make_light_curve_figure,
    make_orbit_figure,
    make_residuals_figure,
)
from astraeus.dashboard.scenario import DashboardTransitScenario
from astraeus.dashboard.simulation import (
    DashboardSimulation,
    generate_dashboard_simulation,
)


def render_dashboard() -> None:
    """Render the interactive ASTRAEUS dashboard."""

    st.set_page_config(
        page_title="ASTRAEUS Transit Dashboard",
        page_icon=".",
        layout="wide",
    )
    _inject_page_styles()
    scenario = _render_sidebar()
    simulation = _cached_simulation(scenario)
    _render_main_panel(simulation)


@st.cache_data(show_spinner=False)
def _cached_simulation(scenario: DashboardTransitScenario) -> DashboardSimulation:
    """Cache deterministic dashboard calculations by scenario."""

    return generate_dashboard_simulation(scenario)


def _render_sidebar() -> DashboardTransitScenario:
    """Render controls and return the selected scenario."""

    with st.sidebar:
        st.title("ASTRAEUS")
        radius_ratio = st.slider(
            "Planetary Radius Ratio (Rp/Rs)",
            0.01,
            0.20,
            0.10,
            0.005,
        )
        period_days = st.slider("Orbital Period (days)", 0.5, 20.0, 3.0, 0.1)
        eccentricity = st.slider("Eccentricity (e)", 0.0, 0.9, 0.0, 0.01)
        inclination_degrees = st.slider(
            "Inclination (degrees)",
            80.0,
            90.0,
            88.5,
            0.1,
        )
        snr = st.slider("Target Signal-to-Noise Ratio (SNR)", 50, 500, 200, 10)

    return DashboardTransitScenario(
        radius_ratio=radius_ratio,
        period_days=period_days,
        eccentricity=eccentricity,
        inclination_degrees=inclination_degrees,
        snr=snr,
    )


def _render_main_panel(simulation: DashboardSimulation) -> None:
    """Render metrics and sequential Plotly outputs."""

    st.title("ASTRAEUS Transit Dashboard")

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Semi-major Axis",
        f"{simulation.semi_major_axis_rsun:.2f} R_sun",
    )
    metric_columns[1].metric("Transit Depth", f"{simulation.max_depth_ppm:.0f} ppm")
    metric_columns[2].metric("Noise Sigma", f"{simulation.noise_sigma:.5f}")
    metric_columns[3].metric("Samples", f"{len(simulation.time_days):,}")

    st.subheader("Orbit View")
    st.plotly_chart(make_orbit_figure(simulation), use_container_width=True)

    st.subheader("Light Curve")
    st.plotly_chart(make_light_curve_figure(simulation), use_container_width=True)

    st.subheader("Residuals")
    st.plotly_chart(make_residuals_figure(simulation), use_container_width=True)


def _inject_page_styles() -> None:
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
