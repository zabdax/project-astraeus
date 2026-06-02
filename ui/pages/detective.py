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

    # Inject Premium Dark-SaaS CSS Overrides & Structural Alignments
    st.markdown(
        """
        <style>
        /* Unify top-bar widget height, clear gaps, and style layout */
        div[data-testid="column"] {
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 0px 6px !important;
        }

        /* 1. Reset file uploader margins and spacing */
        div[data-testid="stFileUploader"] {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
        }

        /* 2. Hide all default inner text, buttons, and subtext to prevent squeeze-wrapping */
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] > button,
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] > div {
            display: none !important;
        }

        /* 3. Style the dropzone itself as a compact clickable button */
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

        /* 4. Inject a clean, compact label in place of the hidden default text */
        div[data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"]::before {
            content: "📂 Ingest Asset" !important;
            font-family: 'Fira Code', 'Courier New', monospace !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            color: #A78BFA !important;
            display: block !important;
            text-align: center !important;
            white-space: nowrap !important;
        }

        /* 5. Style the file details widget (shows file name and delete button) when a file is active */
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

        /* Modern Dark-SaaS Inputs (Text & Select) */
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
    col_uploader, col_input, col_selector = st.columns([0.15, 0.55, 0.30], gap="small")

    # Column 1 (Exact Left): Compact local file uploader allowing FITS/CSV assets
    with col_uploader:
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
                st.error(f"Error parsing asset: {e}")
        else:
            st.session_state.uploaded_file_data = None

    # Column 2 (Center Main): Dominant text input field with caching
    with col_input:
        search_target = st.text_input(
            "Target Search",
            value=st.session_state.search_target,
            placeholder="Search Target Designation (e.g., WASP-12 b, Kepler-186 f)...",
            key="search_target",
            label_visibility="collapsed"
        )

    # Column 3 (Right Selection): Selectbox tracking data routes
    with col_selector:
        routes = [
            "NASA Exoplanet Archive",
            "TESS (via Lightkurve)",
            "Kepler (via Lightkurve)"
        ]
        
        default_index = routes.index(st.session_state.data_route) if st.session_state.data_route in routes else 0
        
        data_route = st.selectbox(
            "Data Route Selection",
            options=routes,
            index=default_index,
            key="data_route",
            label_visibility="collapsed"
        )

    return st.session_state.uploaded_file_data, search_target, data_route

def render(main_panel, right_panel) -> None:
    """Render the Detective module."""
    with main_panel:
        st.markdown(
            "<h2 style='margin-bottom: 2px; color: #A78BFA;'>🕵️ Exoplanet Detective</h2>"
            "<p style='color: #64748B; font-size: 0.9rem; margin-bottom: 20px;'>"
            "Analyze and detect candidate exoplanetary transits using the Box Least Squares (BLS) periodogram method."
            "</p>",
            unsafe_allow_html=True
        )
        
        # Render the Unified Discovery Bar at the absolute top of the content arena
        uploaded_data, target, route = render_discovery_bar()
        
        # Display feedback or perform transit detection depending on data source
        if uploaded_data is not None:
            if isinstance(uploaded_data, dict) and 'time' in uploaded_data and 'flux' in uploaded_data:
                st.success(f"Data loaded successfully: {len(uploaded_data['time'])} stellar points.")
                
                if st.button("🚀 Run Anti-Aliased Planet Detection Pass", use_container_width=True):
                    with st.spinner("Running Box Least Squares analysis..."):
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
                            st.error(f"BLS Execution failed: {e}")
            else:
                st.info("Invalid parsed data format detected.")
        
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
                if st.button("🚀 Fetch Target Metadata", use_container_width=True):
                    # Minimal SVG Icons
                    SVG_QUERY = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>"""
                    SVG_SERVER = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>"""
                    SVG_GEAR = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>"""
                    SVG_CHECK = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>"""

                    def render_svg(svg_string, text):
                        st.markdown(f"<div style='display: flex; align-items: center; gap: 10px;'>{svg_string} <span>{text}</span></div>", unsafe_allow_html=True)

                    import time
                    with st.status("Querying NASA Exoplanet Archive...", expanded=True) as status:
                        render_svg(SVG_QUERY, "Fetching archive data...")
                        time.sleep(0.5)
                        
                        status.update(label="Contacting Space Agency Servers (MAST)...", state="running")
                        render_svg(SVG_SERVER, "Connecting to MAST...")
                        time.sleep(0.5)
                        
                        status.update(label="Normalizing Telemetry Arrays...", state="running")
                        render_svg(SVG_GEAR, "Processing telemetry...")
                        
                        mission = "Kepler"
                        if "TESS" in route:
                            mission = "TESS"
                        res = RemoteDiscoveryEngine.fetch_data(target, mission=mission)
                        
                        status.update(label="Context Assembly Complete.", state="complete", expanded=False)
                        render_svg(SVG_CHECK, "Assembly complete.")

                    if res.get("status") == "no_time_series":
                        st.error(f"Metadata found, but no time-series data available for {target} on {mission}.")
                        if res.get("metadata"):
                            st.json(res["metadata"])
                    elif res.get("status") == "success":
                        st.session_state['fetched_target_data'] = res
                        st.rerun()
                    else:
                        st.error(f"Failed to find target {target} in the archive.")
            
            if 'fetched_target_data' in st.session_state:
                res = st.session_state['fetched_target_data']
                meta = res.get("metadata", {})
                period = meta.get("pl_orbper", 0.0)
                radius = meta.get("st_rad", 0.0)
                depth = meta.get("pl_trandep", 0.0)
                
                with st.container(border=True):
                    st.markdown("### Target Discovery Confirmation")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("System Designation", target)
                    with col2:
                        st.metric("Archival Orbital Period", f"{period:.4f}" if period else "N/A")
                    with col3:
                        st.metric("Stellar Radius (R☉)", f"{radius:.2f}" if radius else "N/A")
                    with col4:
                        st.metric("Transit Depth (ppm)", f"{depth}" if depth else "N/A")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    if st.button("🚀 Run Anti-Aliased Planet Detection Pass", type="primary", use_container_width=True):
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
                            st.error(f"BLS Execution failed: {e}")
        
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
                st.info("Awaiting detection run...")
