"""Detective module for the dashboard."""

import streamlit as st
import pandas as pd
import plotly.express as px
from astraeus.analysis.detection import detect_transit_candidate
from astraeus.core.ingestion import RemoteDiscoveryEngine, DataAdapter

def render_discovery_bar() -> tuple[pd.DataFrame | None, str, str]:
    """
    Renders a unified, compact discovery horizontal bar containing:
    1. A styled compact file uploader (CSV/FITS).
    2. A target designation search input with typing-animated placeholder.
    3. A data route selector.
    
    Returns:
        tuple: (uploaded_df_or_bytes, search_target, data_route)
    """
    # Initialize session state keys to cache search targets and inputs stable
    if "search_target" not in st.session_state:
        st.session_state.search_target = ""
        
    if "data_route" not in st.session_state:
        st.session_state.data_route = "NASA Exoplanet Archive"
        
    if "uploaded_file_data" not in st.session_state:
        st.session_state.uploaded_file_data = None

    has_target = bool(st.session_state.get('search_target', '').strip())
    opacity_rule = ".stApp div[data-testid='stFileUploader'] { opacity: 0.3 !important; }" if has_target else ""

    # Inject Premium Dark-SaaS CSS Overrides & Structural Alignments
    st.markdown(
        f"""
        <style>
        /* Unify top-bar widget height, clear gaps, and style layout */
        div[data-testid="column"] {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 0px 6px !important;
        }}

        /* 1. Reset file uploader margins and spacing */
        div[data-testid="stFileUploader"] {{
            margin: 0 auto !important;
            padding: 0 !important;
            width: 80% !important;
            transition: opacity 0.3s ease-in-out !important;
        }}

        /* Focus-Dimming Effect */
        .stApp:has(div[data-testid="stTextInput"] input:focus) div[data-testid="stFileUploader"] {{
            opacity: 0.3 !important;
        }}
        
        {opacity_rule}

        /* 2. Hide all default inner text, buttons, and subtext to prevent squeeze-wrapping */
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] > button,
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] > div {{
            display: none !important;
        }}

        /* 3. Style the dropzone itself as a compact clickable button */
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] {{
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
        }}

        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"]:hover {{
            border-color: #A78BFA !important;
            background-color: rgba(167, 139, 250, 0.08) !important;
            box-shadow: 0 0 10px rgba(167, 139, 250, 0.15) !important;
        }}

        /* 4. Inject a clean, compact label in place of the hidden default text */
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"]::before {{
            content: "Ingest Asset" !important;
            font-family: 'Fira Code', 'Courier New', monospace !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            color: #A78BFA !important;
            display: block !important;
            text-align: center !important;
            white-space: nowrap !important;
        }}

        /* 5. Style the file details widget (shows file name and delete button) when a file is active */
        div[data-testid="stFileUploader"] > section + div {{
            margin-top: 6px !important;
            padding: 4px 8px !important;
            background: #0B0E17 !important;
            border-radius: 6px !important;
            border: 1px solid #1E293B !important;
            font-family: 'Fira Code', monospace !important;
            font-size: 11px !important;
            color: #A78BFA !important;
        }}

        /* Modern Dark-SaaS Inputs (Text & Select) */
        div[data-testid="stTextInput"] input {{
            background-color: #1E293B !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            color: #F8FAFC !important;
            height: 42px !important;
            font-family: 'Fira Code', 'Courier New', monospace !important;
            font-size: 13px !important;
            padding-left: 12px !important;
            transition: all 0.25s ease-in-out !important;
        }}

        div[data-testid="stTextInput"] input:focus {{
            border-color: #A78BFA !important;
            box-shadow: 0 0 10px rgba(167, 139, 250, 0.2) !important;
        }}

        div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {{
            background-color: #1E293B !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            color: #F8FAFC !important;
            height: 42px !important;
            font-family: 'Fira Code', 'Courier New', monospace !important;
            font-size: 13px !important;
            transition: all 0.25s ease-in-out !important;
        }}

        div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div:hover {{
            border-color: #A78BFA !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

    # Dynamic Real-Time typing placeholder Injection inside Streamlit input DOM
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
                        setTimeout(tick, 2500); // Pause on full text
                        return;
                    }
                } else {
                    input.placeholder = fullText.substring(0, prefix.length + charIdx);
                    charIdx--;
                    if (charIdx < 0) {
                        isDeleting = false;
                        targetIdx = (targetIdx + 1) % targets.length;
                        charIdx = 0;
                        setTimeout(tick, 500); // Pause before starting typing next target
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

    # Strict Horizontal Layout using st.columns with the optimized split ratio
    col_input, col_selector = st.columns([0.75, 0.25], gap="small")

    # Top Layer: Dominant text input field with caching
    with col_input:
        search_target = st.text_input(
            "Target Search",
            value=st.session_state.search_target,
            placeholder="Search Target Designation (e.g., WASP-12 b, Kepler-186 f)...",
            key="search_target",
            label_visibility="collapsed"
        )

    # Top Layer: Selectbox tracking data routes
    with col_selector:
        routes = [
            "NASA Exoplanet Archive",
            "TESS (via Lightkurve)",
            "Kepler (via Lightkurve)",
            "Combined Baseline (Kepler + TESS)"
        ]
        
        default_index = routes.index(st.session_state.data_route) if st.session_state.data_route in routes else 0
        
        data_route = st.selectbox(
            "Data Route Selection",
            options=routes,
            index=default_index,
            key="data_route",
            label_visibility="collapsed"
        )

    # Middle Layer: OR Separator
    st.markdown(
        "<div style='text-align: center; margin: 16px 0;'><span style='color: #64748B; font-family: monospace; font-size: 12px; display: inline-flex; align-items: center; width: 100%; justify-content: center;'><hr style='width: 30%; border-color: rgba(51, 65, 85, 0.5); margin-right: 12px;'/>&mdash; OR &mdash;<hr style='width: 30%; border-color: rgba(51, 65, 85, 0.5); margin-left: 12px;'/></span></div>",
        unsafe_allow_html=True
    )

    # Bottom Layer: File Uploader
    uploaded_file = st.file_uploader(
        "Upload Asset",
        type=["csv", "fits"],
        key="raw_upload_widget",
        label_visibility="collapsed"
    )
    
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
    """Render the Detective module."""
    with main_panel:
        st.markdown(
            "<div style='display: flex; align-items: center; gap: 12px; margin-bottom: 2px;'>"
            "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 24 24' fill='none' stroke='#06b6d4' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'></circle><circle cx='12' cy='12' r='2'></circle><line x1='12' y1='2' x2='12' y2='4'></line><line x1='12' y1='20' x2='12' y2='22'></line><line x1='20' y1='12' x2='22' y2='12'></line><line x1='2' y1='12' x2='4' y2='12'></line></svg>"
            "<h2 style='margin: 0; color: #A78BFA;'>Exoplanet Detective</h2>"
            "</div>"
            "<p style='color: #64748B; font-size: 0.9rem; margin-bottom: 20px; margin-top: 6px;'>"
            "Analyze and detect candidate exoplanetary transits using the Box Least Squares (BLS) periodogram method."
            "</p>",
            unsafe_allow_html=True
        )
        
        # Render the Unified Discovery Bar at the absolute top of the content arena
        uploaded_data, target, route = render_discovery_bar()
        
        # Display feedback or perform transit detection depending on data source
        if uploaded_data is not None:
            if isinstance(uploaded_data, dict) and 'time' in uploaded_data and 'flux' in uploaded_data:
                st.markdown(f"<div style='color: #10B981; display: flex; align-items: center; gap: 8px; margin-bottom: 12px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'></path><polyline points='22 4 12 14.01 9 11.01'></polyline></svg> Data loaded successfully: {len(uploaded_data['time'])} stellar points.</div>", unsafe_allow_html=True)
                
                if st.button("Analyze Telemetry & Verify Harmonics", type="primary", use_container_width=True):
                    with st.spinner("Executing optimized sub-harmonic resonant scan & multi-phase binning..."):
                        try:
                            results = detect_transit_candidate(
                                uploaded_data['time'], 
                                uploaded_data['flux'],
                                target_name="Uploaded Asset",
                                data_source="Local Upload",
                                metadata=uploaded_data.get('metadata', {})
                            )
                            # Extract periodogram details
                            periodogram_data = results.pop('periodogram')
                            
                            # Cache results in session state to remain stable across interactions
                            st.session_state['detective_results'] = results
                            st.session_state['detective_plot_data'] = periodogram_data
                        except Exception as e:
                            st.markdown(f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> BLS Execution failed: {e}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='color: #0ea5e9; display: flex; align-items: center; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='12' y1='16' x2='12' y2='12'></line><line x1='12' y1='8' x2='12.01' y2='8'></line></svg> Invalid parsed data format detected.</div>", unsafe_allow_html=True)
        
        elif target:
            # We want to clear plot data if a new target is searched (unless we just successfully queried it)
            if 'last_target' not in st.session_state or st.session_state['last_target'] != target:
                st.session_state['last_target'] = target
                if 'detective_plot_data' in st.session_state:
                    del st.session_state['detective_plot_data']
                if 'detective_results' in st.session_state:
                    del st.session_state['detective_results']
                if 'fetched_target_data' in st.session_state:
                    del st.session_state['fetched_target_data']
            
            if 'fetched_target_data' not in st.session_state:
                if st.button("Fetch Target Metadata", type="primary", use_container_width=True):
                    # Minimal SVG Icons
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

                        # ── Surface any partial archive-layer error even on MAST success ──
                        arch_err = res.get("archive_error")
                        if arch_err:
                            st.toast(f"Archive warning for '{target}': {arch_err}")

                        fetch_status = res.get("status")

                        if fetch_status == "no_time_series":
                            st.markdown(
                                f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span>Metadata found, but no time-series data available for <b>{target}</b> on mission <b>{mission}</b>.</span></div>", unsafe_allow_html=True
                            )
                            if res.get("metadata"):
                                st.json(res["metadata"])

                        elif fetch_status == "error":
                            # Both archive and MAST failed — show full backend trace
                            mast_err = res.get("mast_error", "Unknown MAST error")
                            st.markdown(
                                f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span><b>MAST download failed</b> for <code>{target}</code>:</span></div>", unsafe_allow_html=True
                            )
                            st.code(mast_err)
                            if arch_err:
                                st.markdown(
                                    f"<div style='color: #EF4444; display: flex; gap: 8px; margin-top: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span><b>Archive query also failed</b>:</span></div>", unsafe_allow_html=True
                                )
                                st.code(arch_err)

                        elif fetch_status == "success":
                            # ── Write canonical metadata into active_metadata ──────────
                            st.session_state["active_metadata"] = res["metadata"]
                            st.session_state['fetched_target_data'] = res
                            st.rerun()

                        else:
                            st.markdown(
                                f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span>Unexpected engine status <code>{fetch_status!r}</code> for target <code>{target}</code>. Check backend logs.</span></div>", unsafe_allow_html=True
                            )

                    except Exception:
                        # Catch any unhandled Python exception and show full traceback
                        tb = traceback.format_exc()
                        st.markdown(
                            f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> <span><b>Unhandled exception</b> during fetch for <code>{target}</code>:</span></div>", unsafe_allow_html=True
                        )
                        st.code(tb)
            
            if 'fetched_target_data' in st.session_state:
                res = st.session_state['fetched_target_data']
                # ── Ensure active_metadata is always in sync ──────────────────────────
                # (guards against sessions started before this refactor that
                # stored fetched_target_data but never wrote active_metadata)
                if "active_metadata" not in st.session_state:
                    st.session_state["active_metadata"] = res.get("metadata", {})

                meta = st.session_state["active_metadata"]

                # ── Pull display values from canonical active_metadata keys ───
                period = meta.get("orbital_period")
                radius = meta.get("stellar_radius")
                depth  = meta.get("transit_depth")
                
                with st.container(border=True):
                    st.markdown("<h3 style='display: flex; align-items: center; gap: 8px; color: #06b6d4;'><svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='8'></circle><line x1='21' y1='21' x2='16.65' y2='16.65'></line></svg> Target Discovery Confirmation</h3>", unsafe_allow_html=True)
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("System Designation", meta.get("pl_name", target))
                    with col2:
                        st.metric(
                            "Archival Orbital Period",
                            f"{period:.4f} d" if period is not None else "N/A",
                        )
                    with col3:
                        st.metric(
                            "Stellar Radius (R☉)",
                            f"{radius:.4f}" if radius is not None else "N/A",
                        )
                    with col4:
                        st.metric(
                            "Transit Depth (ppm)",
                            f"{depth:.2f}" if depth is not None else "N/A",
                        )
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    if "raw_row_dump" in meta:
                        with st.expander("Inspect Raw NASA API Response Payload", expanded=False):
                            st.json(meta["raw_row_dump"])
                    
                    if st.button("Analyze Telemetry & Verify Harmonics", type="primary", use_container_width=True):
                        with st.spinner("Executing optimized sub-harmonic resonant scan & multi-phase binning..."):
                            try:
                                results = detect_transit_candidate(
                                    res['time'], 
                                    res['flux'],
                                    target_name=target,
                                    data_source=route,
                                    metadata=meta
                                )
                                periodogram_data = results.pop('periodogram')
                                
                                st.session_state['detective_results'] = results
                                st.session_state['detective_results']['metadata'] = meta
                                st.session_state['detective_plot_data'] = periodogram_data
                            except Exception as e:
                                st.markdown(f"<div style='color: #EF4444; display: flex; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='15' y1='9' x2='9' y2='15'></line><line x1='9' y1='9' x2='15' y2='15'></line></svg> BLS Execution failed: {e}</div>", unsafe_allow_html=True)
        
        # Display Plot if we have results in session state
        if 'detective_plot_data' in st.session_state:
            st.markdown("<h3 style='margin-top: 24px; color: #A78BFA;'>BLS Periodogram</h3>", unsafe_allow_html=True)
            plot_data = st.session_state['detective_plot_data']
            fig = px.line(
                x=plot_data['periods'], 
                y=plot_data['powers'], 
                labels={'x': 'Period (days)', 'y': 'Power'},
                title=f"BLS Power vs. Period for {target or 'Uploaded Asset'}"
            )
            # Apply premium styling to Plotly figures
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(15,23,42,0.6)',
                font_color="#E2E8F0",
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)
            
    if right_panel:
        with right_panel:
            st.subheader("Detection Report")
            if 'detective_results' in st.session_state:
                st.json(st.session_state['detective_results'])
            else:
                st.markdown("<div style='color: #0ea5e9; display: flex; align-items: center; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='12' cy='12' r='10'></circle><line x1='12' y1='16' x2='12' y2='12'></line><line x1='12' y1='8' x2='12.01' y2='8'></line></svg> Awaiting detection run...</div>", unsafe_allow_html=True)
