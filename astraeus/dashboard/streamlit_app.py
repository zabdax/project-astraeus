"""Streamlit composition layer for the ASTRAEUS dashboard."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.figures import (
    make_light_curve_figure,
    make_orbit_figure,
    make_residuals_figure,
)
from astraeus.dashboard.scenario import DashboardTransitScenario
from astraeus.dashboard.simulation import (
    DashboardSimulation,
    generate_dashboard_simulation,
)


def render_dashboard() -> None:
    """Render the interactive ASTRAEUS dashboard."""

    st.set_page_config(
        page_title="ASTRAEUS Transit Dashboard",
        page_icon=".",
        layout="wide",
    )
    _inject_page_styles()
    
    st.title("ASTRAEUS Transit Dashboard")
    tab_data, tab_sim = st.tabs(["Data Ingestion", "Transit Simulation"])
    
    with tab_data:
        _render_data_ingestion_panel()
        
    with tab_sim:
        scenario = _render_sidebar()
        simulation = _cached_simulation(scenario)
        _render_main_panel(simulation)


@st.cache_data(show_spinner=False)
def _cached_simulation(scenario: DashboardTransitScenario) -> DashboardSimulation:
    """Cache deterministic dashboard calculations by scenario."""

    return generate_dashboard_simulation(scenario)


def _render_sidebar() -> DashboardTransitScenario:
    """Render controls and return the selected scenario."""

    with st.sidebar:
        st.title("ASTRAEUS")
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


def _render_main_panel(simulation: DashboardSimulation) -> None:
    """Render metrics and sequential Plotly outputs."""

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Semi-major Axis",
        f"{simulation.semi_major_axis_rsun:.2f} R_sun",
    )
    metric_columns[1].metric("Transit Depth", f"{simulation.max_depth_ppm:.0f} ppm")
    metric_columns[2].metric("Noise Sigma", f"{simulation.noise_sigma:.5f}")
    metric_columns[3].metric("Samples", f"{len(simulation.time_days):,}")

    st.subheader("Orbit View")
    st.plotly_chart(make_orbit_figure(simulation), use_container_width=True)

    st.subheader("Light Curve")
    st.plotly_chart(make_light_curve_figure(simulation), use_container_width=True)

    st.subheader("Residuals")
    st.plotly_chart(make_residuals_figure(simulation), use_container_width=True)


def _inject_page_styles() -> None:
    """Apply small layout refinements without changing Streamlit behavior."""

    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1220px;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(148, 163, 184, 0.25);
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            background: rgba(15, 23, 42, 0.025);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def _render_data_ingestion_panel() -> None:
    """Render data ingestion controls and raw data preview."""
    st.subheader("Data Input Configuration")
    
    source_type = st.radio(
        "Data Input Source", 
        ["NASA Archive API", "Upload Raw CSV", "Upload Raw JSON"],
        horizontal=True
    )
    
    time_array, flux_array, err_array = None, None, None
    
    if source_type == "NASA Archive API":
        col1, col2 = st.columns(2)
        target_id = col1.text_input("Target ID (e.g., 'WASP-12b')", value="WASP-12b")
        mission = col2.selectbox("Telescope Mission", ["Kepler", "TESS"])
        
        if st.button("Load from NASA Archive"):
            with st.spinner(f"Fetching {target_id} from {mission}..."):
                try:
                    from astraeus.data.loader import universal_load_lightcurve
                    time_array, flux_array, err_array = universal_load_lightcurve("api", target_id, mission=mission)
                    st.success("Data loaded successfully.")
                except Exception as e:
                    st.error(f"Error loading data: {e}")
                    
    else:
        file_ext = "csv" if "CSV" in source_type else "json"
        uploaded_file = st.file_uploader(f"Upload .{file_ext} file", type=[file_ext])
        
        st.write("Column Name Overrides (Optional)")
        col1, col2, col3 = st.columns(3)
        time_col = col1.text_input("Time Column Override", help="Leave blank to auto-detect")
        flux_col = col2.text_input("Flux Column Override", help="Leave blank to auto-detect")
        err_col = col3.text_input("Flux Error Column Override", help="Leave blank to auto-detect")
        
        if uploaded_file is not None and st.button("Load Uploaded File"):
            import tempfile
            import os
            from astraeus.data.loader import universal_load_lightcurve
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
                
            column_map = {}
            if time_col: column_map['time'] = time_col
            if flux_col: column_map['flux'] = flux_col
            if err_col: column_map['flux_err'] = err_col
            
            with st.spinner("Processing file..."):
                try:
                    time_array, flux_array, err_array = universal_load_lightcurve(
                        file_ext, tmp_path, column_map=column_map
                    )
                    st.success("Data loaded successfully.")
                except Exception as e:
                    st.error(f"Error parsing file: {e}")
                finally:
                    os.remove(tmp_path)
                    
    if time_array is not None and flux_array is not None and err_array is not None:
        st.subheader("Raw Light Curve Preview")
        from astraeus.dashboard.figures import make_raw_light_curve_figure
        fig = make_raw_light_curve_figure(time_array, flux_array, err_array)
        st.plotly_chart(fig, use_container_width=True)

