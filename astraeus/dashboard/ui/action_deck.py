"""Action Deck rendering for retrieval explanation and export."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

from astraeus.dashboard.services.action_deck import (
    explain_retrieval,
    export_retrieval_report,
)


def render_action_deck() -> None:
    """Render the Action Deck for MCMC results."""

    if "mcmc_data" not in st.session_state:
        return

    st.markdown("---")
    st.subheader("Action Deck")

    col1, col2 = st.columns(2)
    with col1:
        _render_explanation_controls(st.session_state["mcmc_data"])
    with col2:
        _render_export_controls(st.session_state["mcmc_data"])


def _render_explanation_controls(retrieval_summary: dict[str, Any]) -> None:
    """Render LLM explanation controls and results."""

    if st.button("Explain Results"):
        with st.spinner("Generating explanation..."):
            explanation = explain_retrieval(
                retrieval_summary,
                provider=st.session_state.get("llm_provider", "google"),
                model_name=st.session_state.get("llm_model", "gemini-1.5-pro-latest"),
                api_key=st.session_state.get("llm_api_key", ""),
            )
            st.session_state["scientific_explanation"] = explanation

    if "scientific_explanation" in st.session_state:
        with st.expander("Scientific Explanation", expanded=True):
            exp = st.session_state["scientific_explanation"]
            st.markdown("#### Physics Interpretation")
            st.write(exp.get("physics_interpretation", ""))
            st.markdown("#### Parameter Breakdown")
            st.write(exp.get("parameter_breakdown", ""))
            st.markdown("#### Uncertainty Analysis")
            st.write(exp.get("uncertainty_analysis", ""))


def _render_export_controls(retrieval_summary: dict[str, Any]) -> None:
    """Render report export controls and download button."""

    export_format = st.radio("Export Format", ["PDF", "Markdown"], horizontal=True)
    if st.button("Export Report"):
        with st.spinner("Generating report..."):
            explanation = st.session_state.get("scientific_explanation", {})
            try:
                report_path = export_retrieval_report(
                    retrieval_summary,
                    explanation,
                    export_format,
                )
            except Exception as exc:
                st.error(f"Error generating report: {exc}")
                return

            st.session_state["report_path"] = report_path
            st.session_state["report_format"] = export_format.lower()

    if "report_path" in st.session_state and os.path.exists(st.session_state["report_path"]):
        with open(st.session_state["report_path"], "rb") as report_file:
            file_data = report_file.read()
        ext = st.session_state["report_format"]
        mime = "application/pdf" if ext == "pdf" else "text/markdown"
        st.download_button(
            label=f"Download {ext.upper()}",
            data=file_data,
            file_name=os.path.basename(st.session_state["report_path"]),
            mime=mime,
        )
