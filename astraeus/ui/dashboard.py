"""Project Astraeus -- Streamlit production dashboard.

Unified visualization surface for the BLS multi-planet discovery pipeline
and the academic manuscript reporting subsystem. Designed to be launched
directly via::

    streamlit run astraeus/ui/dashboard.py
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from astraeus.analysis.reporting import generate_academic_report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Headless environment guard -- detect missing Kaleido / headless deps early
# ---------------------------------------------------------------------------
def _check_headless_prerequisites() -> None:
    """Log and surface a clear warning if headless rendering deps are absent.

    Kaleido (or Orca) is required by the Plotly ``Figure.to_image()`` path that
    the PDF compiler delegates to.  On Linux servers without libX11 / Chromium
    this import will succeed at the Python level but fail at runtime.  We probe
    eagerly and emit an actionable notification so operators know exactly what
    to install.
    """
    try:
        import kaleido  # noqa: F401
    except ImportError:
        logger.warning(
            "Kaleido is not installed. Plotly figure images in the PDF "
            "manuscript will render as styled placeholder canvases.  Install "
            "with 'pip install kaleido==0.2.1' for embedded chart images."
        )


# ---------------------------------------------------------------------------
# Baseline discovery payload (from the recent Kepler-90 sweep)
# ---------------------------------------------------------------------------
BASELINE_PAYLOAD: Dict[str, Any] = {
    "target": "KIC 11442793",
    "total_iterations_executed": 5,
    "candidates": [
        {
            "iteration": 1,
            "period": 266.9361,
            "snr": 16.86,
            "vetting_status": "Verified Planet Candidate",
            "depth": 0.000400,
            "duration": 0.4,
            "t0": 132.289,
        },
        {
            "iteration": 2,
            "period": 211.7070,
            "snr": 17.68,
            "vetting_status": "Verified Planet Candidate",
            "depth": 0.000390,
            "duration": 0.4,
            "t0": 141.522,
        },
        {
            "iteration": 3,
            "period": 238.6614,
            "snr": 15.97,
            "vetting_status": "Verified Planet Candidate",
            "depth": 0.000341,
            "duration": 0.4,
            "t0": 273.521,
        },
        {
            "iteration": 4,
            "period": 663.1439,
            "snr": 16.94,
            "vetting_status": "Verified Planet Candidate",
            "depth": 0.001801,
            "duration": 0.05,
            "t0": 140.369,
        },
    ],
}


# ---------------------------------------------------------------------------
# SVG brand mark -- minimal geometric double-ringed transit path system
# ---------------------------------------------------------------------------
BRAND_SVG = """
<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
<svg width="44" height="44" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" fill="none">
  <circle cx="32" cy="32" r="30" stroke="#475569" stroke-width="1.2" opacity="0.55"/>
  <circle cx="32" cy="32" r="22" stroke="#1E293B" stroke-width="1.6"/>
  <circle cx="32" cy="32" r="3.5" fill="#0F172A"/>
  <circle cx="54" cy="32" r="3" fill="#1E293B"/>
  <circle cx="10" cy="32" r="3" fill="#1E293B"/>
  <path d="M2 32 H62" stroke="#94A3B8" stroke-width="0.8" stroke-dasharray="2 3" opacity="0.8"/>
  <path d="M32 4 V60" stroke="#94A3B8" stroke-width="0.6" stroke-dasharray="1 4" opacity="0.5"/>
</svg>
<div>
  <div style="font-size:15px;font-weight:700;color:#0F172A;letter-spacing:0.5px;">PROJECT ASTRAEUS</div>
  <div style="font-size:10px;color:#64748B;letter-spacing:1.5px;">TRANSIT DISCOVERY Mvp</div>
</div>
</div>
"""


def _initialize_session_state() -> None:
    """Seed baseline discovery data once per session (idempotent)."""
    if "discovery_payload" not in st.session_state:
        # Defensive copy so the module-level constant is never mutated.
        import copy

        st.session_state["discovery_payload"] = copy.deepcopy(BASELINE_PAYLOAD)


def _render_brand_mark() -> None:
    """Render the inline SVG brand vector in the sidebar."""
    st.sidebar.markdown(BRAND_SVG, unsafe_allow_html=True)


def _build_adapted_metrics_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map dashboard payload schema onto the reporting backend schema.

    The academic report compiler expects ``metrics_payload`` with a
    ``star_id`` key and candidate records keyed by ``candidate_id`` /
    ``epoch``. The dashboard payload uses ``target`` / ``t0`` instead, so we
    translate it here -- never mutating the source payload.
    """
    candidates: List[Dict[str, Any]] = []
    for cand in payload.get("candidates", []):
        candidates.append(
            {
                "candidate_id": f"{payload.get('target', 'UNK')}-i{cand.get('iteration', '?')}",
                "period": cand.get("period", 0.0),
                "snr": cand.get("snr", 0.0),
                "depth": cand.get("depth", 0.0),
                "epoch": cand.get("t0", 0.0),
            }
        )
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
        ),
    }


def _render_sidebar(payload: Dict[str, Any]) -> tuple[str, float]:
    """Render sidebar controls and return (selected_target, snr_threshold)."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Control Panel")

    target = st.sidebar.selectbox(
        "Active Target",
        options=[payload["target"]],
        index=0,
        help="Select the discovery target to render in the workspace.",
    )

    snr_threshold = st.sidebar.slider(
        "SNR Vetting Threshold",
        min_value=5.0,
        max_value=25.0,
        value=12.0,
        step=0.1,
        help="Candidates at or above this SNR are flagged as verified.",
    )

    st.sidebar.markdown("")
    st.sidebar.success("Dual-Zone Grid: ACTIVE")
    st.sidebar.info("1.5x Wing Subtraction: ACTIVE")

    # ---- Two-stage non-blocking PDF compilation flow ----
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Manuscript Export")

    if st.sidebar.button("Generate Research Manuscript"):
        with st.spinner("Compiling manuscript components in-memory..."):
            metrics_payload = _build_adapted_metrics_payload(payload)
            # Empty figures dict -> backend routes to native placeholder fallbacks.
            pdf_buffer = generate_academic_report(metrics_payload, figures={})
            st.session_state["compiled_pdf_bytes"] = pdf_buffer

    if "compiled_pdf_bytes" in st.session_state:
        st.sidebar.download_button(
            "Download Document PDF",
            data=st.session_state["compiled_pdf_bytes"].getvalue(),
            mime="application/pdf",
        )

    return target, snr_threshold


def _render_kpi_cards(payload: Dict[str, Any]) -> None:
    """Render the three dynamic KPI cards across the main panel."""
    candidates = payload.get("candidates", [])
    peak_snr = max((c["snr"] for c in candidates), default=0.0)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric(label="Total Iterations", value=payload.get("total_iterations_executed", 0))
    with col_b:
        st.metric(label="Candidates Found", value=len(candidates))
    with col_c:
        st.metric(label="Peak System SNR", value=f"{peak_snr:.2f}")


def _render_candidates_table(payload: Dict[str, Any]) -> None:
    """Render the interactive candidates table from an isolated copy.

    The source payload is never mutated. A local DataFrame copy carries the
    temporary computed ``Transit Depth (PPM)`` column only for display.
    """
    st.markdown("### Candidate Ledger")

    # Isolated copy -- never mutate the source payload.
    display_df = pd.DataFrame(list(payload.get("candidates", []))).copy()
    if display_df.empty:
        st.info("No candidates to display.")
        return

    # Temporary computed column (depth is fractional flux -> PPM).
    display_df["Transit Depth (PPM)"] = (display_df["depth"] * 1_000_000).round(2)

    st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_inspection_panel(payload: Dict[str, Any], snr_threshold: float) -> None:
    """Render one expander per candidate with detail + dynamic status badge."""
    st.markdown("### Advanced Candidate Inspection")

    candidates = payload.get("candidates", [])
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
                # Dynamic color badge driven by the sidebar slider threshold.
                if cand.get("snr", 0.0) >= snr_threshold:
                    st.markdown(":green[**Verified Planet Candidate**]")
                else:
                    st.markdown(":orange[**Low SNR Candidate Baseline**]")

            st.info(
                "Live Plotly phase-folded transit plots will be integrated here in the next "
                "rendering iteration."
            )


def _render_main_panel(payload: Dict[str, Any], target: str, snr_threshold: float) -> None:
    """Compose the main analytical workspace."""
    st.title("Transit Discovery Workspace")
    st.caption(f"Active target: {target}")

    _render_kpi_cards(payload)
    st.markdown("---")
    _render_candidates_table(payload)
    st.markdown("")
    _render_inspection_panel(payload, snr_threshold)


def main() -> None:
    """Render the full dashboard."""
    st.set_page_config(
        layout="wide",
        page_title="Project Astraeus",
        page_icon="chart",
    )

    _check_headless_prerequisites()
    _initialize_session_state()

    payload = st.session_state["discovery_payload"]

    _render_brand_mark()
    target, snr_threshold = _render_sidebar(payload)
    _render_main_panel(payload, target, snr_threshold)


if __name__ == "__main__":
    main()
