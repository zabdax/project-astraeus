"""Detective module for the dashboard."""

import streamlit as st
import pandas as pd
import plotly.express as px
from astraeus.analysis.detection import detect_transit_candidate

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
            if uploaded_file.name.endswith(".csv"):
                try:
                    df = pd.read_csv(uploaded_file)
                    st.session_state.uploaded_file_data = df
                except Exception as e:
                    st.error(f"Error parsing CSV: {e}")
            else:
                st.session_state.uploaded_file_data = uploaded_file.getvalue()
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
            if isinstance(uploaded_data, pd.DataFrame):
                df = uploaded_data
                if 'time' not in df.columns or 'flux' not in df.columns:
                    st.error("Uploaded CSV must contain 'time' and 'flux' columns.")
                else:
                    st.success(f"Data loaded successfully: {len(df)} stellar points.")
                    
                    if st.button("🚀 Run BLS Detection", use_container_width=True):
                        with st.spinner("Running Box Least Squares analysis..."):
                            try:
                                results = detect_transit_candidate(df['time'], df['flux'])
                                # Extract periodogram details
                                periodogram_data = results.pop('periodogram')
                                
                                # Cache results in session state to remain stable across interactions
                                st.session_state['detective_results'] = results
                                st.session_state['detective_plot_data'] = periodogram_data
                            except Exception as e:
                                st.error(f"BLS Execution failed: {e}")
            else:
                st.info("FITS data format detected. Parsing orbital headers...")
        
        elif target:
            st.info(f"Target locked: **{target}** via routing path: **{route}**. Querying exoplanetary archive...")
        
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
