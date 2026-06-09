"""Detective module for the dashboard."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from astraeus.analysis.detection import detect_transit_candidate
from astraeus.core.ingestion import RemoteDiscoveryEngine, DataAdapter

# Custom CSS for Minimalist Dark Theme
CSS = """
<style>
/* Unify top-bar widget height, clear gaps, and style layout */
div[data-testid="column"] {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0px 6px !important;
}

div[data-testid="stFileUploader"] {
    margin: 0 auto !important;
    padding: 0 !important;
    width: 80% !important;
    transition: opacity 0.3s ease-in-out !important;
}

.stApp:has(div[data-testid="stTextInput"] input:focus) div[data-testid="stFileUploader"] {
    opacity: 0.3 !important;
}

{opacity_rule}

div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] > button,
div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] > div {
    display: none !important;
}

div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] {
    padding: 0px 12px !important;
    min-height: 42px !important;
    height: 42px !important;
    background-color: #1E293B !important;
    border: 1px dashed rgba(167, 139, 250, 0.4) !important;
    border-radius: 8px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    overflow: hidden !important;
}

div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"]:hover {
    border-color: #A78BFA !important;
    background-color: rgba(167, 139, 250, 0.08) !important;
    box-shadow: 0 0 10px rgba(167, 139, 250, 0.15) !important;
}

div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"]::before {
    content: "Ingest Asset" !important;
    font-family: 'Fira Code', 'Courier New', monospace !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #A78BFA !important;
    display: block !important;
    text-align: center !important;
    white-space: nowrap !important;
}

div[data-testid="stFileUploader"] > section + div {
    margin-top: 6px !important;
    padding: 4px 8px !important;
    background: #0B0E17 !important;
    border-radius: 6px !important;
    border: 1px solid #1E293B !important;
    font-family: 'Fira Code', monospace !important;
    font-size: 11px !important;
    color: #A78BFA !important;
}

div[data-testid="stTextInput"] input {
    background-color: #1E293B !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
    color: #F8FAFC !important;
    height: 42px !important;
    font-family: 'Fira Code', 'Courier New', monospace !important;
    font-size: 13px !important;
    padding-left: 12px !important;
    transition: all 0.25s ease-in-out !important;
}

div[data-testid="stTextInput"] input:focus {
    border-color: #A78BFA !important;
    box-shadow: 0 0 10px rgba(167, 139, 250, 0.2) !important;
}

div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {
    background-color: #1E293B !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
    color: #F8FAFC !important;
    height: 42px !important;
    font-family: 'Fira Code', 'Courier New', monospace !important;
    font-size: 13px !important;
    transition: all 0.25s ease-in-out !important;
}

div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div:hover {
    border-color: #A78BFA !important;
}

/* New telemetry card design */
.telemetry-card {
    background-color: #11151c;
    border: 1px solid #2a313e;
    border-radius: 6px;
    padding: 16px;
    transition: all 0.25s ease-in-out;
    height: 100%;
}
.telemetry-card:hover {
    border-color: #00bcd4;
    box-shadow: 0 0 10px rgba(0, 188, 212, 0.15);
    transform: translateY(-2px);
}
.telemetry-value {
    font-size: 24px;
    font-weight: 600;
    color: #e6edf3;
    margin-top: 8px;
}
.telemetry-label {
    font-size: 12px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-left: 8px;
}
.telemetry-header {
    display: flex;
    align-items: center;
}
</style>
"""

# SVGs
SVG_PLANET_SCALE = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00bcd4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>"""
SVG_JWST = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00bcd4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>"""
SVG_VETTING = """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00bcd4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="12" x2="21" y2="12"></line><line x1="12" y1="3" x2="12" y2="21"></line></svg>"""

def render_discovery_bar() -> tuple[pd.DataFrame | None, str, str]:
    if "search_target" not in st.session_state:
        st.session_state.search_target = ""
    if "data_route" not in st.session_state:
        st.session_state.data_route = "NASA Exoplanet Archive"
    if "uploaded_file_data" not in st.session_state:
        st.session_state.uploaded_file_data = None

    has_target = bool(st.session_state.get('search_target', '').strip())
    opacity_rule = ".stApp div[data-testid='stFileUploader'] { opacity: 0.3 !important; }" if has_target else ""
    
    st.markdown(CSS.replace("{opacity_rule}", opacity_rule), unsafe_allow_html=True)
    
    st.components.v1.html(
        """
        <script>
        const doc = window.parent.document;
        function setupPlaceholderTyping() {
            const input = doc.querySelector('div[data-testid="stTextInput"] input');
            if (!input) {
                setTimeout(setupPlaceholderTyping, 200);
                return;
            }
            const targets = ["WASP-12 b", "Kepler-186 f", "TRAPPIST-1 e", "TOI-560 c", "HD 189733 b"];
            let targetIdx = 0;
            let charIdx = 0;
            let isDeleting = false;
            const prefix = "Search Target Designation (e.g., ";

            function tick() {
                const currentTarget = targets[targetIdx];
                const fullText = prefix + currentTarget + ")...";
                if (!isDeleting) {
                    input.placeholder = fullText.substring(0, prefix.length + charIdx);
                    charIdx++;
                    if (charIdx > currentTarget.length + 4) {
                        isDeleting = true;
                        setTimeout(tick, 2500);
                        return;
                    }
                } else {
                    input.placeholder = fullText.substring(0, prefix.length + charIdx);
                    charIdx--;
                    if (charIdx < 0) {
                        isDeleting = false;
                        targetIdx = (targetIdx + 1) % targets.length;
                        charIdx = 0;
                        setTimeout(tick, 500);
                        return;
                    }
                }
                setTimeout(tick, isDeleting ? 30 : 60);
            }
            tick();
        }
        setupPlaceholderTyping();
        </script>
        """,
        height=0
    )

    col_input, col_selector = st.columns([0.75, 0.25], gap="small")
    with col_input:
        search_target = st.text_input(
            "Target Search",
            value=st.session_state.search_target,
            placeholder="Search Target Designation (e.g., WASP-12 b, Kepler-186 f)...",
            key="search_target",
            label_visibility="collapsed"
        )
    with col_selector:
        routes = ["NASA Exoplanet Archive", "TESS (via Lightkurve)", "Kepler (via Lightkurve)", "Combined Baseline (Kepler + TESS)"]
        default_index = routes.index(st.session_state.data_route) if st.session_state.data_route in routes else 0
        data_route = st.selectbox("Data Route Selection", options=routes, index=default_index, key="data_route", label_visibility="collapsed")

    st.markdown(
        "<div style='text-align: center; margin: 16px 0;'><span style='color: #64748B; font-family: monospace; font-size: 12px; display: inline-flex; align-items: center; width: 100%; justify-content: center;'><hr style='width: 30%; border-color: rgba(51, 65, 85, 0.5); margin-right: 12px;'/>&mdash; OR &mdash;<hr style='width: 30%; border-color: rgba(51, 65, 85, 0.5); margin-left: 12px;'/></span></div>",
        unsafe_allow_html=True
    )

    uploaded_file = st.file_uploader("Upload Asset", type=["csv", "fits"], key="raw_upload_widget", label_visibility="collapsed")
    if uploaded_file is not None:
        try:
            adapter = DataAdapter(uploaded_file.getvalue(), uploaded_file.name)
            st.session_state.uploaded_file_data = adapter.parse()
        except Exception as e:
            st.markdown(f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> Error parsing asset: {e}</div>", unsafe_allow_html=True)
    else:
        st.session_state.uploaded_file_data = None

    return st.session_state.uploaded_file_data, search_target, data_route

def render(main_panel, right_panel) -> None:
    with main_panel:
        st.markdown(
            "<div style='display: flex; align-items: center; gap: 12px; margin-bottom: 2px;'>"
            "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 24 24' fill='none' stroke='#00bcd4' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'></circle><circle cx='12' cy='12' r='2'></circle><line x1='12' y1='2' x2='12' y2='4'></line><line x1='12' y1='20' x2='12' y2='22'></line><line x1='20' y1='12' x2='22' y2='12'></line><line x1='2' y1='12' x2='4' y2='12'></line></svg>"
            "<h2 style='margin: 0; color: #00bcd4;'>Exoplanet Detective</h2>"
            "</div>"
            "<p style='color: #64748B; font-size: 0.9rem; margin-bottom: 20px; margin-top: 6px;'>"
            "Analyze and detect candidate exoplanetary transits using the Box Least Squares (BLS) periodogram method."
            "</p>",
            unsafe_allow_html=True
        )
        
        uploaded_data, target, route = render_discovery_bar()
        
        def run_analysis(data_time, data_flux, t_name, d_source, metadata):
            with st.spinner("Executing optimized sub-harmonic resonant scan & multi-phase binning..."):
                try:
                    results = detect_transit_candidate(
                        data_time, data_flux,
                        target_name=t_name,
                        data_source=d_source,
                        metadata=metadata
                    )
                    if isinstance(results, list) and len(results) > 0:
                        best_candidate = results[0].get('candidate_1', {})
                    else:
                        best_candidate = results if isinstance(results, dict) else {}
                    
                    periodogram_data = best_candidate.pop('periodogram', None)
                    st.session_state['detective_results'] = best_candidate
                    st.session_state['detective_results']['metadata'] = metadata
                    if periodogram_data:
                        st.session_state['detective_plot_data'] = periodogram_data
                        
                    st.session_state['active_time'] = data_time
                    st.session_state['active_flux'] = data_flux
                except Exception as e:
                    st.markdown(f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> BLS Execution failed: {e}</div>", unsafe_allow_html=True)
                    
        if uploaded_data is not None:
            if isinstance(uploaded_data, dict) and 'time' in uploaded_data and 'flux' in uploaded_data:
                st.markdown(f"<div style='color: #10B981; display: flex; align-items: center; gap: 8px; margin-bottom: 12px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'></path><polyline points='22 4 12 14.01 9 11.01'></polyline></svg> Data loaded successfully: {len(uploaded_data['time'])} stellar points.</div>", unsafe_allow_html=True)
                if st.button("Analyze Telemetry & Verify Harmonics", type="primary", use_container_width=True):
                    run_analysis(uploaded_data['time'], uploaded_data['flux'], "Uploaded Asset", "Local Upload", uploaded_data.get('metadata', {}))
            else:
                st.markdown("<div style='color: #0ea5e9; display: flex; align-items: center; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='12' y1='16' x2='12' y2='12'></line><line x1='12' y1='8' x2='12.01' y2='8'></line></svg> Invalid parsed data format detected.</div>", unsafe_allow_html=True)
        elif target:
            if 'last_target' not in st.session_state or st.session_state['last_target'] != target:
                st.session_state['last_target'] = target
                for key in ['detective_plot_data', 'detective_results', 'fetched_target_data', 'active_time', 'active_flux']:
                    if key in st.session_state:
                        del st.session_state[key]
            
            if 'fetched_target_data' not in st.session_state:
                if st.button("Fetch Target Metadata", type="primary", use_container_width=True):
                    SVG_QUERY = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>"""
                    SVG_SERVER = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>"""
                    SVG_GEAR = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>"""
                    SVG_CHECK = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>"""

                    def render_svg(svg_string, text):
                        st.markdown(f"<div style='display: flex; align-items: center; gap: 10px;'>{svg_string} <span>{text}</span></div>", unsafe_allow_html=True)

                    import time
                    import traceback

                    mission = "Kepler"
                    if "Combined Baseline" in route:
                        mission = "Combined Baseline (Kepler + TESS)"
                    elif "TESS" in route:
                        mission = "TESS"

                    try:
                        with st.status("Querying NASA Exoplanet Archive...", expanded=True) as status:
                            render_svg(SVG_QUERY, "Fetching archive data...")
                            time.sleep(0.5)
                            status.update(label="Contacting Space Agency Servers (MAST)...", state="running")
                            render_svg(SVG_SERVER, "Connecting to MAST...")
                            time.sleep(0.5)
                            status.update(label="Normalizing Telemetry Arrays...", state="running")
                            render_svg(SVG_GEAR, "Processing telemetry...")
                            res = RemoteDiscoveryEngine.fetch_data(target, mission=mission)
                            status.update(label="Context Assembly Complete.", state="complete", expanded=False)
                            render_svg(SVG_CHECK, "Assembly complete.")

                        arch_err = res.get("archive_error")
                        if arch_err:
                            st.toast(f"Archive warning for '{target}': {arch_err}")

                        fetch_status = res.get("status")

                        if fetch_status == "no_time_series":
                            st.markdown(
                                f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span>Metadata found, but no time-series data available for <b>{target}</b> on mission <b>{mission}</b>.</span></div>", unsafe_allow_html=True
                            )
                        elif fetch_status == "error":
                            st.markdown(
                                f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span><b>MAST download failed</b> for <code>{target}</code></span></div>", unsafe_allow_html=True
                            )
                        elif fetch_status == "success":
                            st.session_state["active_metadata"] = res["metadata"]
                            st.session_state['fetched_target_data'] = res
                            st.rerun()
                        else:
                            st.markdown(
                                f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span>Unexpected engine status <code>{fetch_status!r}</code></span></div>", unsafe_allow_html=True
                            )
                    except Exception:
                        tb = traceback.format_exc()
                        st.markdown(
                            f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span><b>Unhandled exception</b></span></div>", unsafe_allow_html=True
                        )
            
            if 'fetched_target_data' in st.session_state:
                res = st.session_state['fetched_target_data']
                if "active_metadata" not in st.session_state:
                    st.session_state["active_metadata"] = res.get("metadata", {})
                meta = st.session_state["active_metadata"]
                
                period = meta.get("orbital_period")
                radius = meta.get("stellar_radius")
                depth  = meta.get("transit_depth")
                
                with st.container(border=True):
                    st.markdown("<h3 style='display: flex; align-items: center; gap: 8px; color: #06b6d4;'><svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='8'></circle><line x1='21' y1='21' x2='16.65' y2='16.65'></line></svg> Target Discovery Confirmation</h3>", unsafe_allow_html=True)
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("System Designation", meta.get("pl_name", target))
                    with col2:
                        st.metric("Archival Orbital Period", f"{period:.4f} d" if period is not None else "N/A")
                    with col3:
                        st.metric("Stellar Radius (R☉)", f"{radius:.4f}" if radius is not None else "N/A")
                    with col4:
                        st.metric("Transit Depth (ppm)", f"{depth * 1000000:.2f}" if depth is not None else "N/A")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    if st.button("Analyze Telemetry & Verify Harmonics", type="primary", use_container_width=True):
                        run_analysis(res['time'], res['flux'], target, route, meta)

        # 3-Tier Layout
        if 'detective_results' in st.session_state:
            res = st.session_state['detective_results']
            
            # --- Tier 1: Top Metrics Row ---
            st.markdown("<h3 style='margin-top: 24px; color: #00bcd4; font-size: 1.2rem; margin-bottom: 12px;'>Core Telemetry</h3>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            
            pr_earth = float(res.get('planet_radius_earth', 0.0))
            with col1:
                st.markdown(f"""
                <div class="telemetry-card">
                    <div class="telemetry-header">
                        {SVG_PLANET_SCALE}
                        <span class="telemetry-label">Planet Scale (R_Earth)</span>
                    </div>
                    <div class="telemetry-value">{pr_earth:.4f}</div>
                </div>
                """, unsafe_allow_html=True)
                
            tsm = float(res.get('jwst_tsm_score', 0.0))
            tier = "High" if tsm > 50 else ("Med" if tsm > 10 else "Low")
            with col2:
                st.markdown(f"""
                <div class="telemetry-card">
                    <div class="telemetry-header">
                        {SVG_JWST}
                        <span class="telemetry-label">JWST Feasibility (TSM)</span>
                    </div>
                    <div class="telemetry-value">{tsm:.4f} <span style='font-size: 14px; color: #8b949e;'>| {tier} Tier</span></div>
                </div>
                """, unsafe_allow_html=True)
                
            v_stat = str(res.get('vetting_status', 'Unknown'))
            snr = float(res.get('snr', 0.0))
            with col3:
                st.markdown(f"""
                <div class="telemetry-card">
                    <div class="telemetry-header">
                        {SVG_VETTING}
                        <span class="telemetry-label">Vetting Signal</span>
                    </div>
                    <div class="telemetry-value" style="font-size: 16px; margin-top: 12px;">
                        <span style="color: {'#00bcd4' if 'candidate' in v_stat.lower() else '#EF4444'};">{v_stat.upper()}</span>
                        <div style="font-size: 14px; color: #8b949e; margin-top: 4px;">SNR: {snr:.3f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # --- Tier 2: Middle Row (Phase-Folded Light Curve) ---
            if 'active_time' in st.session_state and 'active_flux' in st.session_state:
                st.markdown("<h3 style='color: #00bcd4; font-size: 1.2rem; margin-bottom: 12px;'>Phase-Folded Light Curve</h3>", unsafe_allow_html=True)
                t0 = float(res.get('t0', 0.0))
                period = float(res.get('period', 1.0))
                if period == 0:
                    period = 1.0
                time_arr = np.array(st.session_state['active_time'])
                flux_arr = np.array(st.session_state['active_flux'])
                
                phase = (time_arr - t0 + 0.5 * period) % period - 0.5 * period
                
                fig_lc = go.Figure()
                fig_lc.add_trace(go.Scatter(
                    x=phase, y=flux_arr,
                    mode='markers',
                    marker=dict(size=3, color='#00bcd4', opacity=0.6),
                    name='Folded Flux'
                ))
                fig_lc.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(15,23,42,0.6)',
                    font_color="#E2E8F0",
                    xaxis=dict(title='Phase (days)', gridcolor='rgba(255,255,255,0.05)', zerolinecolor='rgba(255,255,255,0.2)'),
                    yaxis=dict(title='Relative Flux', gridcolor='rgba(255,255,255,0.05)', zerolinecolor='rgba(255,255,255,0.2)'),
                    margin=dict(l=40, r=40, t=40, b=40),
                    hovermode='closest'
                )
                st.plotly_chart(fig_lc, use_container_width=True)
            
            # --- Tier 3: Bottom Row (Perturbation Matrix) ---
            st.markdown("<h3 style='margin-top: 12px; color: #00bcd4; font-size: 1.2rem; margin-bottom: 12px;'>Diagnostic Summary Matrix</h3>", unsafe_allow_html=True)
            col_bot_l, col_bot_r = st.columns([2, 1])
            
            with col_bot_l:
                ttv_data = res.get('ttv_data', [])
                if ttv_data:
                    epochs = [int(d['epoch']) for d in ttv_data]
                    residuals = [float(d['ttv_residual_min']) for d in ttv_data]
                    
                    fig_ttv = go.Figure()
                    fig_ttv.add_trace(go.Scatter(
                        x=epochs, y=residuals,
                        mode='markers+lines',
                        marker=dict(size=8, color='#00bcd4', line=dict(width=1, color='#e6edf3')),
                        line=dict(color='rgba(0,188,212,0.4)', width=1),
                        name='O-C Residuals'
                    ))
                    fig_ttv.add_hline(y=0, line_dash="dash", line_color="#8b949e", opacity=0.8)
                    fig_ttv.update_layout(
                        title="TTV O-C Diagram (Minutes)",
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(15,23,42,0.6)',
                        font_color="#E2E8F0",
                        xaxis=dict(title='Transit Epoch', gridcolor='rgba(255,255,255,0.05)'),
                        yaxis=dict(title='O-C Residual (min)', gridcolor='rgba(255,255,255,0.05)'),
                        margin=dict(l=40, r=40, t=40, b=40)
                    )
                    st.plotly_chart(fig_ttv, use_container_width=True)
                else:
                    st.markdown("<div style='padding: 24px; text-align: center; color: #8b949e; border: 1px solid #2a313e; border-radius: 6px;'>No TTV data available or insufficient transits.</div>", unsafe_allow_html=True)
            
            with col_bot_r:
                v_shape = float(res.get('v_shape_metric', 0.0))
                flat_bot = float(res.get('flat_bottom_fraction', 0.0))
                sec_dep = float(res.get('secondary_eclipse_depth', 0.0))
                sec_snr = float(res.get('secondary_eclipse_snr', 0.0))
                
                v_status = "Pass" if v_shape < 0.8 and flat_bot >= 0.05 else "Fail (V-Shaped)"
                sec_status = "Pass" if sec_snr <= 3.0 else "Fail (Eclipse Detected)"
                
                v_color = "#10B981" if v_status == "Pass" else "#EF4444"
                sec_color = "#10B981" if sec_status == "Pass" else "#EF4444"
                
                st.markdown(f"""
                <div class="telemetry-card" style="display: flex; flex-direction: column; gap: 16px;">
                    <div>
                        <div style="font-size: 12px; color: #8b949e; text-transform: uppercase;">V-Shape Metric Check</div>
                        <div style="font-size: 16px; font-weight: bold; color: {v_color}; margin-top: 4px;">{v_status}</div>
                        <div style="font-size: 13px; color: #e6edf3; margin-top: 2px;">Curvature: {v_shape:.4f}</div>
                        <div style="font-size: 13px; color: #e6edf3;">Flat Bottom: {flat_bot:.4f}</div>
                    </div>
                    <div style="border-top: 1px solid #2a313e; margin: 4px 0;"></div>
                    <div>
                        <div style="font-size: 12px; color: #8b949e; text-transform: uppercase;">Secondary Eclipse</div>
                        <div style="font-size: 16px; font-weight: bold; color: {sec_color}; margin-top: 4px;">{sec_status}</div>
                        <div style="font-size: 13px; color: #e6edf3; margin-top: 2px;">Depth: {sec_dep:.5f}</div>
                        <div style="font-size: 13px; color: #e6edf3;">SNR: {sec_snr:.3f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
    if right_panel:
        with right_panel:
            st.subheader("Detection Report")
            if 'detective_results' in st.session_state:
                st.json(st.session_state['detective_results'])
            else:
                st.markdown("<div style='color: #0ea5e9; display: flex; align-items: center; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='12' y1='16' x2='12' y2='12'></line><line x1='12' y1='8' x2='12.01' y2='8'></line></svg> Awaiting detection run...</div>", unsafe_allow_html=True)
