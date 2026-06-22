"""MCMC configuration form rendering."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.services.mcmc_retrieval import MCMCConfig


def render_mcmc_config_form() -> tuple[MCMCConfig, bool]:
    """Render and collect MCMC configuration controls."""

    with st.form("mcmc_config_form"):
        st.write("**Orbital Parameters (Required for phase-folding)**")
        col1, col2 = st.columns(2)
        period = col1.number_input("Orbital Period (days)", value=2.470613, format="%.6f")
        t0 = col2.number_input(
            "Transit Epoch (t0)",
            value=0.0,
            format="%.6f",
            help="Set to 0.0 to auto-estimate from the data.",
        )

        st.write("**Fixed Physical Assumptions**")
        col3, col4, col5 = st.columns(3)
        r_star = col3.number_input("Stellar Radius (R_sun)", value=1.0)
        a_semi = col4.number_input("Semi-major Axis (AU)", value=0.03556, format="%.5f")
        ecc = col5.number_input("Eccentricity", value=0.0)

        st.write("**Initial Parameter Guesses**")
        col6, col7, col8, col9 = st.columns(4)
        rp_rs_guess = col6.number_input("Rp/Rs", value=0.125, format="%.4f")
        inc_guess = col7.number_input("Inclination (deg)", value=83.6)
        u1_guess = col8.number_input("u1", value=0.4)
        u2_guess = col9.number_input("u2", value=0.2)
        n_steps = st.slider("MCMC Steps", min_value=100, max_value=2000, value=500, step=100)

        submitted = st.form_submit_button("Run MCMC Analysis")

    return (
        MCMCConfig(
            period_days=period,
            transit_epoch=t0,
            stellar_radius_rsun=r_star,
            semi_major_axis_au=a_semi,
            eccentricity=ecc,
            radius_ratio_guess=rp_rs_guess,
            inclination_degrees_guess=inc_guess,
            u1_guess=u1_guess,
            u2_guess=u2_guess,
            n_steps=n_steps,
        ),
        submitted,
    )
