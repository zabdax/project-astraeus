"""Sidebar controls for transit simulation scenarios."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.scenario import DashboardTransitScenario


def render_scenario_controls() -> DashboardTransitScenario:
    """Render simulation controls and return the selected scenario."""

    with st.sidebar:
        st.title("ASTRAEUS")

        st.markdown("---")
        st.subheader("Model Settings")
        st.session_state["llm_api_key"] = st.text_input("API Key", type="password")
        st.session_state["llm_provider"] = st.selectbox(
            "Provider",
            ["google", "openai", "anthropic", "ollama"],
            index=0,
        )
        st.session_state["llm_model"] = st.text_input(
            "Model Name",
            value="gemini-1.5-pro-latest",
        )
        st.markdown("---")

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
