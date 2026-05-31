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
    st.plotly_chart(make_orbit_figure(simulation), width="stretch")

    st.subheader("Light Curve")
    st.plotly_chart(make_light_curve_figure(simulation), width="stretch")

    st.subheader("Residuals")
    st.plotly_chart(make_residuals_figure(simulation), width="stretch")


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
        mission = col2.selectbox("Telescope Mission", ["Kepler", "K2", "TESS"])
        
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
        st.plotly_chart(fig, width="stretch")
        
        _render_mcmc_analysis_panel(time_array, flux_array, err_array)

def _render_mcmc_analysis_panel(time_array, flux_array, err_array) -> None:
    """Render the MCMC analysis configuration and execution panel."""
    st.markdown("---")
    st.subheader("Run Parameter Retrieval (MCMC)")
    
    st.warning(
        "⚠️ **Computational Warning**: Running an MCMC retrieval is computationally expensive. "
        "Depending on the number of steps and walkers, this process can take several minutes. "
        "You will not be able to interact with the dashboard while the analysis is running."
    )
    
    with st.form("mcmc_config_form"):
        st.write("**Orbital Parameters (Required for phase-folding)**")
        col1, col2 = st.columns(2)
        period = col1.number_input("Orbital Period (days)", value=2.470613, format="%.6f")
        t0 = col2.number_input("Transit Epoch (t0)", value=0.0, format="%.6f", help="Set to 0.0 to auto-estimate from the data.")
        
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
        
    if submitted:
        _execute_mcmc_retrieval(
            time_array, flux_array, err_array,
            period, t0, r_star, a_semi, ecc,
            rp_rs_guess, inc_guess, u1_guess, u2_guess,
            n_steps
        )

def _execute_mcmc_retrieval(
    time_raw, flux_raw, err_raw,
    period_days, t0_user, r_star, a_semi, ecc,
    rp_rs, inc, u1, u2, n_steps
):
    import numpy as np
    from astropy import units as u
    from scipy.signal import savgol_filter
    import time
    
    from astraeus.data.preprocessing import detrend_lightcurve, phase_fold_data
    from astraeus.analysis.optimization import find_best_fit
    from astraeus.analysis.error_analysis import run_mcmc
    from astraeus.core.transit_model import generate_model_flux
    from astraeus.visualization.plots import plot_real_retrieval
    
    st.info("Starting MCMC Analysis Workflow...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 1. Detrending
    status_text.text("Step 1/4: Detrending data...")
    flux_detrended = detrend_lightcurve(time_raw, flux_raw)
    progress_bar.progress(5)
    
    # 2. Phase folding
    status_text.text("Step 2/4: Phase folding data...")
    if t0_user == 0.0:
        smoothed_flux = savgol_filter(flux_detrended, window_length=101, polyorder=2)
        t0_guess = time_raw[np.argmin(smoothed_flux)]
        st.write(f"*Auto-estimated t0: {t0_guess:.4f}*")
    else:
        t0_guess = t0_user
        
    folded_time, folded_flux = phase_fold_data(time_raw, flux_detrended, period_days, t0_guess)
    
    out_of_transit_mask = np.abs(folded_time) > 0.1
    noise_std = np.std(folded_flux[out_of_transit_mask])
    folded_flux_err = np.full_like(folded_flux, noise_std)
    progress_bar.progress(10)
    
    # 3. Optimization
    status_text.text("Step 3/4: Running initial optimization (MAP estimate)...")
    time_u = folded_time * u.day
    fixed_params = {
        "R_star": r_star * u.R_sun,
        "period": period_days * u.day,
        "semi_major_axis": a_semi * u.AU,
        "eccentricity": ecc * u.dimensionless_unscaled,
    }
    initial_guess = (rp_rs, inc, u1, u2)
    param_names = ["radius_ratio", "inclination_deg", "u1", "u2"]
    
    best_fit_theta, success = find_best_fit(
        initial_guess_theta=initial_guess,
        time=time_u,
        flux=folded_flux,
        flux_err=folded_flux_err,
        fixed_params=fixed_params,
        param_names=param_names,
    )
    progress_bar.progress(15)
    
    # 4. MCMC
    status_text.text(f"Step 4/4: Running MCMC sampling ({n_steps} steps)...")
    
    # Setup timing for ETA
    start_time = time.time()
    
    def mcmc_progress(step, total):
        # Progress from 15% to 95%
        prog = 15 + int((step / total) * 80)
        progress_bar.progress(prog)
        
        elapsed = time.time() - start_time
        if step > 10:
            time_per_step = elapsed / step
            eta_seconds = (total - step) * time_per_step
            m, s = divmod(int(eta_seconds), 60)
            status_text.text(f"Step 4/4: Running MCMC sampling ({step}/{total}) - ETA: {m:02d}:{s:02d}")
        else:
            status_text.text(f"Step 4/4: Running MCMC sampling ({step}/{total}) - ETA: Calculating...")
            
    flat_samples, percentiles = run_mcmc(
        best_fit_theta=best_fit_theta,
        time=time_u,
        flux=folded_flux,
        flux_err=folded_flux_err,
        fixed_params=fixed_params,
        param_names=param_names,
        n_walkers=32,
        n_steps=n_steps,
        progress_callback=mcmc_progress
    )
    progress_bar.progress(100)
    status_text.text("Analysis Complete!")
    
    median_params = percentiles[:, 1]
    
    st.success("MCMC Retrieval Completed Successfully!")
    
    st.subheader("Retrieval Results")
    res_cols = st.columns(4)
    res_cols[0].metric("Radius Ratio (Rp/Rs)", f"{median_params[0]:.4f}")
    res_cols[1].metric("Inclination", f"{median_params[1]:.2f}°")
    res_cols[2].metric("Limb Darkening u1", f"{median_params[2]:.4f}")
    res_cols[3].metric("Limb Darkening u2", f"{median_params[3]:.4f}")
    
    # Generate theoretical flux
    params_dict = fixed_params.copy()
    for name, val in zip(param_names, median_params):
        params_dict[name] = val
        
    inclination = params_dict.get("inclination_deg", 90.0) * u.deg
    theoretical_flux = generate_model_flux(
        time=time_u,
        period=params_dict["period"],
        semi_major_axis=params_dict["semi_major_axis"],
        eccentricity=params_dict.get("eccentricity", 0.0 * u.dimensionless_unscaled),
        inclination=inclination,
        R_star=params_dict["R_star"],
        R_planet=params_dict["R_star"] * params_dict["radius_ratio"],
        u1=params_dict.get("u1", 0.0),
        u2=params_dict.get("u2", 0.0),
    )
    
    st.markdown("### Phase-Folded Transit Validation")
    import plotly.graph_objects as go
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=folded_time, y=folded_flux,
        mode='markers',
        marker=dict(size=3, color='rgba(148, 163, 184, 0.4)'),
        name="Phase-folded Data"
    ))
    
    sort_idx = np.argsort(folded_time)
    fig.add_trace(go.Scatter(
        x=folded_time[sort_idx], y=theoretical_flux[sort_idx],
        mode='lines',
        line=dict(color='#ff2a6d', width=3),
        name="MCMC Best Fit Model"
    ))
    
    fig.update_layout(
        xaxis_title="Phase (days from mid-transit)",
        yaxis_title="Relative Flux",
        template="plotly_dark",
        margin=dict(l=40, r=40, t=40, b=40),
        hovermode="x unified"
    )
    st.plotly_chart(fig, width="stretch")


