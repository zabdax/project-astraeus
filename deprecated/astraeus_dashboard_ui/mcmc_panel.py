"""MCMC analysis panel rendering for ingested light curves."""

from __future__ import annotations

import time

import numpy as np
import streamlit as st

from astraeus.dashboard.figures import make_retrieval_validation_figure
from astraeus.dashboard.services.data_ingestion import LightCurveData
from astraeus.dashboard.services.action_deck import build_retrieval_summary
from astraeus.dashboard.services.mcmc_retrieval import (
    MCMCConfig,
    run_retrieval,
)
from astraeus.dashboard.ui.action_deck import render_action_deck
from astraeus.dashboard.ui.mcmc_form import render_mcmc_config_form


def render_mcmc_analysis_panel(light_curve: LightCurveData) -> None:
    """Render the MCMC analysis configuration and execution panel."""

    st.markdown("---")
    st.subheader("Run Parameter Retrieval (MCMC)")
    st.warning(
        "Computational warning: MCMC retrieval can take several minutes depending "
        "on the number of steps and walkers. The dashboard is unavailable while "
        "the analysis is running."
    )

    config, submitted = render_mcmc_config_form()
    if submitted:
        _execute_mcmc_retrieval(light_curve, config)

    render_action_deck()


def _execute_mcmc_retrieval(light_curve: LightCurveData, config: MCMCConfig) -> None:
    """Run retrieval and render progress/results."""

    st.info("Starting MCMC analysis workflow...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text("Step 1/4: Detrending and phase folding data...")
    progress_bar.progress(10)

    start_time = time.time()

    def update_mcmc_progress(step: int, total: int) -> None:
        progress = 15 + int((step / total) * 80)
        progress_bar.progress(progress)

        elapsed = time.time() - start_time
        if step > 10:
            time_per_step = elapsed / step
            eta_seconds = (total - step) * time_per_step
            minutes, seconds = divmod(int(eta_seconds), 60)
            status_text.text(
                f"Step 4/4: Running MCMC sampling ({step}/{total}) - "
                f"ETA: {minutes:02d}:{seconds:02d}"
            )
        else:
            status_text.text(
                f"Step 4/4: Running MCMC sampling ({step}/{total}) - ETA: Calculating..."
            )

    try:
        result = run_retrieval(
            time_raw=light_curve.time,
            flux_raw=light_curve.flux,
            config=config,
            progress_callback=update_mcmc_progress,
        )
    except Exception as exc:
        progress_bar.empty()
        status_text.empty()
        st.error(f"MCMC retrieval failed: {exc}")
        return

    progress_bar.progress(100)
    status_text.text("Analysis complete.")
    if result.t0_was_estimated:
        st.write(f"*Auto-estimated t0: {result.t0_used:.4f}*")

    _render_retrieval_results(result.median_params)
    st.markdown("### Phase-Folded Transit Validation")
    st.plotly_chart(make_retrieval_validation_figure(result), width="stretch")
    st.session_state["mcmc_data"] = build_retrieval_summary(result)


def _render_retrieval_results(median_params: np.ndarray) -> None:
    """Render MCMC median parameter metrics."""

    st.success("MCMC retrieval completed successfully.")
    st.subheader("Retrieval Results")
    res_cols = st.columns(4)
    res_cols[0].metric("Radius Ratio (Rp/Rs)", f"{median_params[0]:.4f}")
    res_cols[1].metric("Inclination", f"{median_params[1]:.2f} deg")
    res_cols[2].metric("Limb Darkening u1", f"{median_params[2]:.4f}")
    res_cols[3].metric("Limb Darkening u2", f"{median_params[3]:.4f}")
