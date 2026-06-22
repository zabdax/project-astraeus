"""Simulation tab rendering for the dashboard."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.figures import (
    make_light_curve_figure,
    make_orbit_figure,
    make_residuals_figure,
)
from astraeus.dashboard.simulation import DashboardSimulation


def render_simulation_panel(simulation: DashboardSimulation) -> None:
    """Render metrics and Plotly outputs for a simulation."""

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Semi-major Axis",
        f"{simulation.semi_major_axis_rsun:.2f} R_sun",
    )
    metric_columns[1].metric("Transit Depth", f"{simulation.max_depth_ppm:.0f} ppm")
    metric_columns[2].metric("Noise Sigma", f"{simulation.noise_sigma:.5f}")
    metric_columns[3].metric("Samples", f"{len(simulation.time_days):,}")

    st.subheader("Orbit View")
    st.plotly_chart(make_orbit_figure(simulation), width="stretch")

    st.subheader("Light Curve")
    st.plotly_chart(make_light_curve_figure(simulation), width="stretch")

    st.subheader("Residuals")
    st.plotly_chart(make_residuals_figure(simulation), width="stretch")
