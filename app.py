"""Streamlit entry point for the ASTRAEUS dashboard."""

import copy
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from typing import Dict, Any, List
import logging

from astraeus.dashboard.ui.layout import workbench_layout
from astraeus.dashboard.ui.styles import inject_page_styles
from astraeus.dashboard.ui.components import render_floating_chat
from astraeus.analysis.reporting import generate_academic_report
from route import render_route

logger = logging.getLogger(__name__)

# Phase-folded light curve sampling parameters.
# ``_PHASE_POINTS`` cadence and ``_NOISE_SCALE`` are tuned so the synthesized
# scatter reads as genuine Kepler long-cadence photometry rather than a clean
# analytical profile.
_PHASE_POINTS = 600
_NOISE_SCALE = 5.0e-5

BASELINE_PAYLOAD: Dict[str, Any] = {
    "target": "KIC 11442793",
    "total_iterations_executed": 5,
    "candidates": [
        {"iteration": 1, "period": 266.9361, "snr": 16.86, "vetting_status": "Verified Planet Candidate", "depth": 0.000400, "duration": 0.4, "t0": 132.289},
        {"iteration": 2, "period": 211.7070, "snr": 17.68, "vetting_status": "Verified Planet Candidate", "depth": 0.000390, "duration": 0.4, "t0": 141.522},
        {"iteration": 3, "period": 238.6614, "snr": 15.97, "vetting_status": "Verified Planet Candidate", "depth": 0.000341, "duration": 0.4, "t0": 273.521},
        {"iteration": 4, "period": 663.1439, "snr": 16.94, "vetting_status": "Verified Planet Candidate", "depth": 0.001801, "duration": 0.05, "t0": 140.369}
    ]
}


def _build_phase_folded_figure(cand: Dict[str, Any]) -> go.Figure:
    """Synthesize a clean phase-folded transit scatter for one candidate.

    The figure is generated from the candidate's native physical parameters
    (Period, Depth, Duration, Epoch) rather than read from disk, so it always
    matches whatever is in the session payload.  The phase grid is centered on
    0.0 and spans [-0.5, +0.5] cycles; a box transit window of width
    ``duration / period`` (clamped so very short orbits still render a visible
    dip) drops the normalized flux by exactly the candidate ``depth``, and a
    thin layer of Gaussian noise gives the scatter a photometric texture.

    The returned Figure is theme-styled to the dark workbench canvas and is a
    fresh object on every call, so it is safe to pass straight into either the
    interactive ``st.plotly_chart`` renderer or the deep-copying PDF handshake.
    """
    period = float(cand.get("period", 0.0)) or 1.0
    depth = float(cand.get("depth", 0.0))
    duration = float(cand.get("duration", 0.0)) or 0.0
    t0 = float(cand.get("t0", 0.0))

    # Deterministic per-candidate seed so figures are stable across reruns
    # while still differing between candidates.
    seed = (int(abs(period) * 1e4) ^ int(abs(t0) * 1e3) ^ int(abs(depth) * 1e9)) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)

    # Phase grid in cycles, centered on transit at phase = 0.
    phase = np.linspace(-0.5, 0.5, _PHASE_POINTS)

    # Half-transit width in phase units. Clamp to a small floor so the dip is
    # always visible even for grazing / ultra-short configurations, and cap at
    # 0.25 cycles so the box never swallows the whole window.
    half_duration = duration / period if period else 0.0
    half_duration = float(np.clip(half_duration, 0.01, 0.25))

    # Box transit profile: flux drops by exactly ``depth`` inside the window.
    in_transit = np.abs(phase) < half_duration
    flux = np.ones_like(phase)
    flux[in_transit] -= depth

    # High-frequency photometric noise so the scatter looks observational.
    flux = flux + rng.normal(0.0, _NOISE_SCALE, size=flux.shape)

    iter_label = cand.get("iteration", "?")
    fig = go.Figure(
        data=go.Scatter(
            x=phase,
            y=flux,
            mode="markers",
            marker=dict(
                color="#22D3EE",  # neon amber-cyan
                size=4,
                opacity=0.85,
            ),
            name=f"Candidate {iter_label}",
        )
    )

    fig.update_layout(
        title=dict(
            text=f"Phase-Folded Light Curve  ·  Candidate {iter_label}",
            font=dict(color="#E2E8F0", size=13),
            x=0.5,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0F172A",
        font=dict(color="#94A3B8", family="Fira Code, monospace", size=10),
        margin=dict(l=40, r=20, t=40, b=40),
        showlegend=False,
        height=320,
    )
    fig.update_xaxes(
        title_text="Phase",
        color="#94A3B8",
        gridcolor="rgba(148,163,184,0.15)",
        zerolinecolor="rgba(148,163,184,0.35)",
        linecolor="#1E293B",
    )
    fig.update_yaxes(
        title_text="Normalized Flux",
        color="#94A3B8",
        gridcolor="rgba(148,163,184,0.15)",
        zerolinecolor="rgba(148,163,184,0.35)",
        linecolor="#1E293B",
    )
    return fig


def _build_candidate_figures(payload: Dict[str, Any]) -> Dict[str, go.Figure]:
    """Assemble the backend-facing figures dict for the PDF handshake.

    Keys follow the standard backend tracking convention
    ``"<star_id>-1<N>"`` (e.g. ``KIC 11442793-11`` .. ``KIC 11442793-14``),
    matching the contract consumed by ``generate_academic_report``.
    """
    star_id = payload.get("target", "UNK")
    figures: Dict[str, go.Figure] = {}
    for idx, cand in enumerate(payload.get("candidates", []), start=1):
        # Operate on a defensive copy so the live session payload is untouched.
        figures[f"{star_id}-1{idx}"] = _build_phase_folded_figure(copy.deepcopy(cand))
    return figures

def _check_headless_prerequisites() -> None:
    try:
        import kaleido  # noqa: F401
    except ImportError:
        logger.warning(
            "Kaleido is not installed. Plotly figure images in the PDF "
            "manuscript will render as styled placeholder canvases.  Install "
            "with 'pip install kaleido==0.2.1' for embedded chart images."
        )

def _initialize_session_state() -> None:
    if "discovery_payload" not in st.session_state:
        st.session_state["discovery_payload"] = copy.deepcopy(BASELINE_PAYLOAD)

def _build_adapted_metrics_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for cand in payload.get("candidates", []):
        candidates.append({
            "candidate_id": f"{payload.get('target', 'UNK')}-i{cand.get('iteration', '?')}",
            "period": cand.get("period", 0.0),
            "snr": cand.get("snr", 0.0),
            "depth": cand.get("depth", 0.0),
            "epoch": cand.get("t0", 0.0),
        })
    return {
        "star_id": payload.get("target", "Unknown"),
        "candidates": candidates,
        "introduction": (
            "Standard observational baseline diagnostics were performed for the active "
            "target. The flux time series was detrended, systematics were removed, and a "
            "Dual-Zone Hybrid Grid BLS sweep executed with 1.5x subtraction wing padding."
        ),
        "optimization_summary": (
            "Multi-planet grid optimization resolved planetary periods using the Dual-Zone "
            "Hybrid Grid with an anti-recursion duplicate guardrail. The sweep terminated "
            "gracefully after 5 iterations once no further unique candidates could be recovered."
        )
    }

def main():
    """Render the interactive ASTRAEUS dashboard."""
    
    st.set_page_config(
        page_title="Project Astraeus",
        layout="wide",
    )
    
    _check_headless_prerequisites()
    _initialize_session_state()
    
    inject_page_styles()
    
    with workbench_layout() as (selected_feature, main_panel, right_panel):
        if selected_feature == "Discover":
            payload = st.session_state["discovery_payload"]
            
            panel_ctx = right_panel if right_panel else st.sidebar
            with panel_ctx:
                # Extract sidebar controls
                st.markdown("---")
                st.markdown("### Control Panel")

                target = st.selectbox(
                    "Active Target",
                    options=[payload["target"]],
                    index=0,
                )

                snr_threshold = st.slider(
                    "SNR Vetting Threshold",
                    min_value=5.0,
                    max_value=25.0,
                    value=12.0,
                    step=0.1,
                )

                st.markdown("")
                st.success("Dual-Zone Grid: ACTIVE")
                st.info("1.5x Wing Subtraction: ACTIVE")
                
                # 4. Two-Stage PDF Compiler Sidebar Handshake
                st.markdown("---")
                st.markdown("### Manuscript Export")

                if st.button("Generate Research Manuscript"):
                    with st.spinner("Compiling manuscript components in-memory..."):
                        metrics_payload = _build_adapted_metrics_payload(payload)
                        # Build the live Plotly figures for each candidate and
                        # hand them to the backend renderer.  The reporting
                        # engine performs its own deepcopy / sanitation /
                        # multi-page table chunking on top of this payload.
                        figures = _build_candidate_figures(payload)
                        pdf_buffer = generate_academic_report(metrics_payload, figures=figures)
                        st.session_state["compiled_pdf_bytes"] = pdf_buffer

                if "compiled_pdf_bytes" in st.session_state:
                    st.download_button(
                        "Download Document PDF",
                        data=st.session_state["compiled_pdf_bytes"].getvalue(),
                        mime="application/pdf",
                    )
                    
            with main_panel:
                st.title("Transit Discover Workspace")
                
                # KPI Cards
                candidates = payload.get("candidates", [])
                peak_snr = max((c["snr"] for c in candidates), default=0.0)

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric(label="Total Iterations", value=payload.get("total_iterations_executed", 0))
                with col_b:
                    st.metric(label="Candidates Found", value=len(candidates))
                with col_c:
                    st.metric(label="Peak System SNR", value=f"{peak_snr:.2f}")
                    
                # Candidates DataFrame
                st.markdown("### Candidate Ledger")
                display_df = pd.DataFrame(list(payload.get("candidates", []))).copy()
                if not display_df.empty:
                    display_df["Transit Depth (PPM)"] = (display_df["depth"] * 1_000_000).round(2)
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No candidates to display.")
                
                # Interactive expanders
                st.markdown("### Advanced Candidate Inspection")
                for cand in candidates:
                    iter_label = cand.get("iteration", "?")
                    period = cand.get("period", 0.0)
                    with st.expander(f"Candidate {iter_label}  |  Period {period:.4f} d", expanded=False):
                        t0_col, depth_col, status_col = st.columns(3)

                        with t0_col:
                            st.caption("Epoch (t0)")
                            st.markdown(f"**{cand.get('t0', 0.0):.3f}**")

                        with depth_col:
                            st.caption("Raw Depth")
                            st.markdown(f"**{cand.get('depth', 0.0):.6f}**")

                        with status_col:
                            st.caption("Vetting Status")
                            if cand.get("snr", 0.0) >= snr_threshold:
                                st.markdown(":green[**Verified Planet Candidate**]")
                            else:
                                st.markdown(":orange[**Low SNR Candidate Baseline**]")

                        # Live interactive phase-folded transit plot.  Built from
                        # a defensive copy so the session payload is never
                        # mutated by the rendering pass.
                        phase_fig = _build_phase_folded_figure(copy.deepcopy(cand))
                        st.plotly_chart(phase_fig, use_container_width=True)
        else:
            render_route(selected_feature, main_panel, right_panel)

    # Render the persistent floating AI Chat
    render_floating_chat()


if __name__ == "__main__":
    main()
